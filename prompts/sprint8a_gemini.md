# Sprint 8A – Gemini: Persistenz-Schicht (SQLite + User-Config)

## Kontext

Du arbeitest an einem Python-Projekt (LangGraph + Streamlit) zur KI-gestützten Industriebau-Planung.
Deine Aufgabe: **drei neue Dateien + eine Zeile in pyproject.toml**. Keine anderen Dateien werden angefasst.

1. `pyproject.toml` — eine Dependency ergänzen
2. `app/data/users.yaml` — User-Konfiguration für Demo-Login
3. `app/tools/persistence.py` — SQLite-Persistenz für History + Favoriten
4. `scripts/setup_users.py` — Hilfsskript zum Generieren der bcrypt-Hashes

---

## Aufgabe 1: `pyproject.toml`

Im `[project]` → `dependencies`-Array hinzufügen:

```toml
"streamlit-authenticator>=0.3",
```

---

## Aufgabe 2: `scripts/setup_users.py`

Erstelle dieses Hilfsskript (einmalig ausführen, um `app/data/users.yaml` mit echten Hashes zu generieren):

```python
#!/usr/bin/env python
"""Einmalig ausführen: generiert app/data/users.yaml mit bcrypt-Hashes."""
import yaml
from pathlib import Path
import streamlit_authenticator as stauth

DEMO_USERS = {
    "admin": {
        "name": "Administrator",
        "email": "admin@aid-demo.de",
        "password": "Admin2024!",
        "role": "admin",
    },
    "planner": {
        "name": "Planer",
        "email": "planner@aid-demo.de",
        "password": "Plan2024!",
        "role": "planner",
    },
    "viewer": {
        "name": "Betrachter",
        "email": "viewer@aid-demo.de",
        "password": "View2024!",
        "role": "viewer",
    },
}

passwords = [u["password"] for u in DEMO_USERS.values()]
hashed = stauth.Hasher(passwords).generate()

credentials = {"usernames": {}}
for (username, user_data), hashed_pw in zip(DEMO_USERS.items(), hashed):
    credentials["usernames"][username] = {
        "name": user_data["name"],
        "email": user_data["email"],
        "password": hashed_pw,
        "role": user_data["role"],
    }

config = {
    "credentials": credentials,
    "cookie": {
        "expiry_days": 1,
        "key": "aid_demo_secret_key_2024",
        "name": "aid_demo_cookie",
    },
}

out = Path(__file__).parent.parent / "app" / "data" / "users.yaml"
with open(out, "w", encoding="utf-8") as f:
    yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
print(f"users.yaml geschrieben: {out}")
```

---

## Aufgabe 3: `app/data/users.yaml`

Erstelle diese Datei als **Platzhalter** (wird durch `setup_users.py` mit echten Hashes überschrieben).
Die Struktur muss exakt stimmen — `streamlit-authenticator` liest sie direkt ein:

```yaml
credentials:
  usernames:
    admin:
      name: Administrator
      email: admin@aid-demo.de
      password: PLACEHOLDER_RUN_SETUP_USERS_PY
      role: admin
    planner:
      name: Planer
      email: planner@aid-demo.de
      password: PLACEHOLDER_RUN_SETUP_USERS_PY
      role: planner
    viewer:
      name: Betrachter
      email: viewer@aid-demo.de
      password: PLACEHOLDER_RUN_SETUP_USERS_PY
      role: viewer
cookie:
  expiry_days: 1
  key: aid_demo_secret_key_2024
  name: aid_demo_cookie
```

---

## Aufgabe 4: `app/tools/persistence.py`

Vollständige neue Datei:

```python
"""
AID Demo – Persistenz-Schicht
SQLite-basierte History + Favoriten für Planungsläufe.
"""
from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DB_PATH = Path(__file__).parent.parent.parent / "data" / "aid_demo.db"


def _get_db() -> sqlite3.Connection:
    """Öffnet SQLite-Verbindung mit Row-Factory für dict-Zugriff."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Erstellt Tabellen falls nicht vorhanden (idempotent)."""
    with _get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                user             TEXT NOT NULL,
                created_at       TEXT NOT NULL,
                site_name        TEXT,
                nutzungstyp      TEXT,
                briefing_summary TEXT,
                score_a          REAL,
                score_b          REAL,
                score_c          REAL,
                selected_variant TEXT,
                state_json       TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS favorites (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user       TEXT NOT NULL,
                run_id     INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                label      TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(user, run_id)
            );

            CREATE INDEX IF NOT EXISTS idx_runs_user ON runs(user);
            CREATE INDEX IF NOT EXISTS idx_favorites_user ON favorites(user);
        """)


def save_run(
    user: str,
    result: dict[str, Any],
) -> int:
    """Speichert einen Pipeline-Lauf. Gibt die neue run_id zurück.

    Args:
        user:   Username aus st.session_state["username"]
        result: Vollständiges PlanningState-Ergebnis aus st.session_state.result
    """
    briefing = result.get("structured_briefing") or {}
    site     = result.get("site_geometry") or {}
    evals    = {e["variante"]: e["gesamtscore"] for e in (result.get("evaluations") or [])}

    # Kurze Textbeschreibung des Briefings
    nutzungstyp = briefing.get("nutzungstyp", "")
    bgf = briefing.get("bgf_gesamt", 0)
    briefing_summary = f"{nutzungstyp}, {bgf:,.0f} m² BGF" if bgf else nutzungstyp

    created_at = datetime.now(timezone.utc).isoformat()

    with _get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO runs
                (user, created_at, site_name, nutzungstyp, briefing_summary,
                 score_a, score_b, score_c, selected_variant, state_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user,
                created_at,
                site.get("name", "Unbekannt"),
                nutzungstyp,
                briefing_summary,
                evals.get("A_Materialfluss"),
                evals.get("B_Erweiterbarkeit"),
                evals.get("C_Ausgewogen"),
                result.get("selected_variant"),
                json.dumps(result, ensure_ascii=False, default=str),
            ),
        )
        return cursor.lastrowid


def list_history(user: str, limit: int = 30) -> list[dict]:
    """Gibt die letzten `limit` Läufe des Users zurück (ohne state_json).

    Returns:
        Liste von Dicts mit: id, created_at, site_name, nutzungstyp,
        briefing_summary, score_a, score_b, score_c, selected_variant, is_favorite
    """
    with _get_db() as conn:
        rows = conn.execute(
            """
            SELECT r.id, r.created_at, r.site_name, r.nutzungstyp,
                   r.briefing_summary, r.score_a, r.score_b, r.score_c,
                   r.selected_variant,
                   CASE WHEN f.run_id IS NOT NULL THEN 1 ELSE 0 END AS is_favorite,
                   f.label AS favorite_label
            FROM runs r
            LEFT JOIN favorites f ON f.run_id = r.id AND f.user = r.user
            WHERE r.user = ?
            ORDER BY r.created_at DESC
            LIMIT ?
            """,
            (user, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def get_run(run_id: int) -> dict | None:
    """Lädt einen vollständigen Lauf (inkl. state_json). Gibt None zurück wenn nicht gefunden."""
    with _get_db() as conn:
        row = conn.execute(
            "SELECT * FROM runs WHERE id = ?", (run_id,)
        ).fetchone()
    if not row:
        return None
    result = dict(row)
    result["state"] = json.loads(result.pop("state_json"))
    return result


def mark_favorite(user: str, run_id: int, label: str = "") -> None:
    """Markiert einen Lauf als Favorit. Idempotent (UPDATE OR INSERT)."""
    created_at = datetime.now(timezone.utc).isoformat()
    with _get_db() as conn:
        conn.execute(
            """
            INSERT INTO favorites (user, run_id, label, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user, run_id) DO UPDATE SET label = excluded.label
            """,
            (user, run_id, label, created_at),
        )


def unmark_favorite(user: str, run_id: int) -> None:
    """Entfernt Favoriten-Markierung."""
    with _get_db() as conn:
        conn.execute(
            "DELETE FROM favorites WHERE user = ? AND run_id = ?",
            (user, run_id),
        )


def list_favorites(user: str) -> list[dict]:
    """Gibt alle Favoriten des Users zurück (ohne state_json, nach Favorit-Datum sortiert)."""
    with _get_db() as conn:
        rows = conn.execute(
            """
            SELECT r.id, r.created_at, r.site_name, r.nutzungstyp,
                   r.briefing_summary, r.score_a, r.score_b, r.score_c,
                   r.selected_variant, f.label, f.created_at AS favorited_at
            FROM favorites f
            JOIN runs r ON r.id = f.run_id
            WHERE f.user = ?
            ORDER BY f.created_at DESC
            """,
            (user,),
        ).fetchall()
    return [dict(row) for row in rows]


def delete_run(run_id: int) -> None:
    """Löscht einen Lauf (inkl. Favoriten-Einträge via CASCADE)."""
    with _get_db() as conn:
        conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
```

---

## Verifikation

```python
# Nicht als Datei speichern — nur lokal testen:
from app.tools.persistence import init_db, save_run, list_history, mark_favorite, list_favorites

init_db()

# Dummy-Result
dummy = {
    "structured_briefing": {"nutzungstyp": "Produktion", "bgf_gesamt": 4000},
    "site_geometry": {"name": "Testgrundstück"},
    "evaluations": [
        {"variante": "A_Materialfluss", "gesamtscore": 7.4},
        {"variante": "B_Erweiterbarkeit", "gesamtscore": 6.8},
        {"variante": "C_Ausgewogen", "gesamtscore": 7.1},
    ],
    "selected_variant": "A_Materialfluss",
}
run_id = save_run("planner", dummy)
print(f"run_id: {run_id}")
history = list_history("planner")
print(f"History: {len(history)} Einträge")
mark_favorite("planner", run_id, "Testlauf")
favs = list_favorites("planner")
print(f"Favoriten: {len(favs)}")
assert history[0]["site_name"] == "Testgrundstück"
assert favs[0]["label"] == "Testlauf"
print("OK")
```

---

## Was du NICHT änderst

- Alle anderen Dateien im Projekt
- `app/state.py`, `app/graph.py`, `streamlit_app.py`
