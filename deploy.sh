#!/usr/bin/env bash
# Deploy AID (Streamlit) on a Debian/Ubuntu root server behind nginx + Let's Encrypt.
#
# Usage: run as root on the target server.
#   DOMAIN=raumsyntax.de EMAIL=you@example.com ./deploy.sh
#
# Idempotent: safe to re-run. Does not touch other nginx vhosts or services.
set -euo pipefail

DOMAIN="${DOMAIN:-raumsyntax.de}"
WWW_DOMAIN="www.${DOMAIN}"
EMAIL="${EMAIL:-}"                                    # required for --enable-tls
APP_USER="${APP_USER:-raumsyntax}"
APP_DIR="${APP_DIR:-/opt/raumsyntax}"
APP_PORT="${APP_PORT:-8501}"
REPO_URL="${REPO_URL:-https://github.com/thomasmrokon/AID.git}"
BRANCH="${BRANCH:-main}"
ENABLE_TLS="${ENABLE_TLS:-0}"                          # set to 1 to also run certbot

log() { printf '\n\033[1;32m==> %s\033[0m\n' "$1"; }
die() { printf '\n\033[1;31mERROR: %s\033[0m\n' "$1" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Bitte als root ausführen (sudo ./deploy.sh)."

log "Prüfe Systemvoraussetzungen"
PYTHON_BIN="${PYTHON_BIN:-python3}"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || die \
  "${PYTHON_BIN} nicht gefunden. Installieren mit: apt-get update && apt-get install -y python3"
PY_VER="$("$PYTHON_BIN" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
PY_MAJOR="${PY_VER%%.*}"; PY_MINOR="${PY_VER##*.}"
if [[ "$PY_MAJOR" -lt 3 || ( "$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 11 ) ]]; then
  die "Python >=3.11 erforderlich, gefunden: ${PY_VER} (${PYTHON_BIN}). Anderen Interpreter setzen mit PYTHON_BIN=python3.xx"
fi
"$PYTHON_BIN" -m venv --help >/dev/null 2>&1 || die \
  "${PYTHON_BIN} -m venv nicht verfügbar. Installieren mit: apt-get update && apt-get install -y python3-venv"
command -v nginx >/dev/null 2>&1 || die \
  "nginx nicht gefunden. Installieren mit: apt-get update && apt-get install -y nginx"
command -v git >/dev/null 2>&1 || die "git nicht gefunden. Installieren mit: apt-get install -y git"

if ss -ltn 2>/dev/null | grep -q ":${APP_PORT} "; then
  die "Port ${APP_PORT} ist bereits belegt. Anderen Port setzen: APP_PORT=xxxx ./deploy.sh"
fi

log "Lege Systemnutzer '${APP_USER}' an (falls nicht vorhanden)"
id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin "$APP_USER"

log "Hole/aktualisiere Code in ${APP_DIR}"
if [[ -d "${APP_DIR}/.git" ]]; then
  sudo -u "$APP_USER" git -C "$APP_DIR" fetch origin "$BRANCH"
  sudo -u "$APP_USER" git -C "$APP_DIR" reset --hard "origin/${BRANCH}"
else
  mkdir -p "$APP_DIR"
  chown "$APP_USER":"$APP_USER" "$APP_DIR"
  sudo -u "$APP_USER" git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
fi

log "Erstelle/aktualisiere Python-venv und installiere Abhängigkeiten"
sudo -u "$APP_USER" "$PYTHON_BIN" -m venv "${APP_DIR}/.venv"
sudo -u "$APP_USER" "${APP_DIR}/.venv/bin/pip" install --upgrade pip --quiet
sudo -u "$APP_USER" "${APP_DIR}/.venv/bin/pip" install --quiet "${APP_DIR}" streamlit

if [[ ! -f "${APP_DIR}/.env" ]]; then
  log "Lege .env aus .env.example an — BITTE ANSCHLIESSEND API-KEY EINTRAGEN"
  sudo -u "$APP_USER" cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
  chmod 600 "${APP_DIR}/.env"
  echo "  -> vim ${APP_DIR}/.env"
fi

log "Erstelle systemd-Service raumsyntax.service"
cat > /etc/systemd/system/raumsyntax.service <<EOF
[Unit]
Description=AID (raumsyntax.de) - Streamlit app
After=network.target

[Service]
Type=simple
User=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/.venv/bin/streamlit run streamlit_app.py \\
    --server.port ${APP_PORT} \\
    --server.address 127.0.0.1 \\
    --server.baseUrlPath app \\
    --server.headless true \\
    --browser.gatherUsageStats false
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now raumsyntax.service
systemctl restart raumsyntax.service

log "Erstelle nginx-vhost für ${DOMAIN} (bestehende vhosts bleiben unangetastet)"
NGINX_SITE_AVAILABLE="/etc/nginx/sites-available/${DOMAIN}.conf"
NGINX_SITE_ENABLED="/etc/nginx/sites-enabled/${DOMAIN}.conf"
if [[ ! -d /etc/nginx/sites-available ]]; then
  NGINX_SITE_AVAILABLE="/etc/nginx/conf.d/${DOMAIN}.conf"
  NGINX_SITE_ENABLED=""
fi

cat > "$NGINX_SITE_AVAILABLE" <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN} ${WWW_DOMAIN};

    root ${APP_DIR}/web;
    index index.html;

    # Landingpage (Teaser) für alles außerhalb von /app/
    location / {
        try_files \$uri \$uri/ =404;
    }

    location = /app {
        return 301 /app/;
    }

    # AID-Login/App (Streamlit, läuft mit --server.baseUrlPath app)
    location /app/ {
        proxy_pass http://127.0.0.1:${APP_PORT};
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 86400;
    }
}
EOF

if [[ -n "$NGINX_SITE_ENABLED" && ! -e "$NGINX_SITE_ENABLED" ]]; then
  ln -s "$NGINX_SITE_AVAILABLE" "$NGINX_SITE_ENABLED"
fi

nginx -t
systemctl reload nginx

if [[ "$ENABLE_TLS" == "1" ]]; then
  [[ -n "$EMAIL" ]] || die "ENABLE_TLS=1 erfordert EMAIL=you@example.com (für Let's Encrypt)."
  command -v certbot >/dev/null 2>&1 || die \
    "certbot nicht gefunden. Installieren mit: apt-get install -y certbot python3-certbot-nginx"
  log "Beantrage TLS-Zertifikat via certbot (nur für ${DOMAIN}/${WWW_DOMAIN})"
  certbot --nginx -d "$DOMAIN" -d "$WWW_DOMAIN" --non-interactive --agree-tos -m "$EMAIL" --redirect
fi

log "Fertig"
PUBLIC_IP="$(curl -fsS -m 5 https://ifconfig.me || echo '<server-ip>')"
cat <<EOF

Landingpage: http://${DOMAIN}
AID-Login:   http://${DOMAIN}/app/  (Port ${APP_PORT} intern via nginx-Proxy)
Service:     systemctl status raumsyntax.service
Logs:        journalctl -u raumsyntax.service -f

Nächste Schritte, falls noch offen:
  1. DNS: A-Record ${DOMAIN} und ${WWW_DOMAIN} -> ${PUBLIC_IP}
  2. API-Key eintragen: ${APP_DIR}/.env, danach: systemctl restart raumsyntax.service
  3. TLS aktivieren: EMAIL=you@example.com ENABLE_TLS=1 ./deploy.sh
EOF
