# Sprint 8B – Codex: Login-UI + History + Favoriten in Streamlit

## Kontext

Du arbeitest an einem Python-Projekt (LangGraph + Streamlit) zur Industriebau-Planung.
Sprint 8A (Gemini) hat bereits geliefert:
- `app/data/users.yaml` — User-Konfiguration
- `app/tools/persistence.py` — SQLite-CRUD (`init_db`, `save_run`, `list_history`, `get_run`, `mark_favorite`, `unmark_favorite`, `list_favorites`, `delete_run`)

Deine Aufgabe: **nur `streamlit_app.py`** ändern — drei Bereiche:
1. Login-Wrapper (ganz oben, vor allem anderen)
2. Sidebar: History + Favoriten
3. `schritt_ergebnisse()`: Auto-Speichern + Favorit-Button + Laden

---

## Referenz: `persistence.py` API

```python
from app.tools.persistence import (
    init_db,
    save_run,        # (user: str, result: dict) -> int (run_id)
    list_history,    # (user: str, limit=30) -> list[dict]
    get_run,         # (run_id: int) -> dict | None  (enthält "state": dict)
    mark_favorite,   # (user: str, run_id: int, label: str) -> None
    unmark_favorite, # (user: str, run_id: int) -> None
    list_favorites,  # (user: str) -> list[dict]
    delete_run,      # (run_id: int) -> None
)
```

`list_history` / `list_favorites` geben Dicts zurück mit:
`id, created_at, site_name, nutzungstyp, briefing_summary, score_a, score_b, score_c, selected_variant, is_favorite, favorite_label`

---

## Rechte je Rolle

| Rolle | Darf |
|-------|------|
| `viewer` | Favoriten anderer sehen (read-only), kein Pipeline-Start |
| `planner` | Pipeline starten, eigene Läufe speichern/favorisieren |
| `admin` | Alles wie planner + History aller User sehen |

---

## Aufgabe 1: Login-Wrapper (ganz oben in `streamlit_app.py`)

**Einfügeposition:** Direkt nach den bestehenden Imports und `st.set_page_config(...)` — VOR dem Styling-Block und allen anderen Funktionen.

```python
# ---------------------------------------------------------------------------
# Authentifizierung
# ---------------------------------------------------------------------------
import yaml
from pathlib import Path as _Path
import streamlit_authenticator as stauth
from app.tools.persistence import init_db as _init_db

_init_db()  # DB + Tabellen anlegen (idempotent)

_USERS_YAML = _Path(__file__).parent / "app" / "data" / "users.yaml"
with open(_USERS_YAML, encoding="utf-8") as _f:
    _auth_config = yaml.safe_load(_f)

_authenticator = stauth.Authenticate(
    _auth_config["credentials"],
    _auth_config["cookie"]["name"],
    _auth_config["cookie"]["key"],
    _auth_config["cookie"]["expiry_days"],
)

_authenticator.login(location="main")

if st.session_state.get("authentication_status") is False:
    st.error("Benutzername oder Passwort falsch.")
    st.stop()
elif st.session_state.get("authentication_status") is None:
    st.info("Bitte einloggen.")
    st.stop()

# Ab hier ist der User authentifiziert
_current_user: str = st.session_state["username"]
_current_role: str = (
    _auth_config["credentials"]["usernames"]
    .get(_current_user, {})
    .get("role", "viewer")
)
```

**Wichtig:** `st.stop()` verhindert das Rendern der restlichen App. Der `_authenticator.login()` Aufruf rendert das Login-Formular direkt in der `main`-Location (nicht Sidebar).

---

## Aufgabe 2: Sidebar — History + Favoriten

**Einfügeposition:** Am Ende der bestehenden Sidebar-Sektion (nach dem LLM-Konfigurations-Block, ca. am Ende der Datei, vor dem Router).

```python
# ---------------------------------------------------------------------------
# Sidebar: History + Favoriten
# ---------------------------------------------------------------------------

st.sidebar.divider()
_authenticator.logout("Abmelden", location="sidebar", key="logout_btn")
st.sidebar.caption(f"Eingeloggt als **{st.session_state.get('name', _current_user)}** ({_current_role})")

st.sidebar.divider()
st.sidebar.markdown("### Verlauf & Favoriten")

# ── Favoriten ────────────────────────────────────────────────────────────────
with st.sidebar.expander("★ Favoriten", expanded=False):
    from app.tools.persistence import list_favorites as _list_favorites, get_run as _get_run
    _favs = _list_favorites(_current_user)
    if not _favs:
        st.caption("Noch keine Favoriten gespeichert.")
    for fav in _favs:
        fav_label = fav.get("favorite_label") or fav.get("site_name", "Lauf")
        score_best = max(
            filter(None, [fav.get("score_a"), fav.get("score_b"), fav.get("score_c")]),
            default=0.0,
        )
        col_lbl, col_btn = st.columns([3, 1])
        col_lbl.markdown(
            f"**{fav_label}**  \n"
            f"<span style='font-size:0.75rem;color:#888'>"
            f"{fav.get('nutzungstyp', '')} · {fav.get('site_name', '')} · "
            f"Score {score_best:.1f}</span>",
            unsafe_allow_html=True,
        )
        if col_btn.button("Laden", key=f"fav_load_{fav['id']}", use_container_width=True):
            _run = _get_run(fav["id"])
            if _run:
                st.session_state.result = _run["state"]
                st.session_state.schritt = 6
                st.rerun()

# ── Verlauf ──────────────────────────────────────────────────────────────────
with st.sidebar.expander("Verlauf", expanded=False):
    from app.tools.persistence import list_history as _list_history
    _history = _list_history(_current_user, limit=20)
    if not _history:
        st.caption("Noch keine Läufe gespeichert.")
    for run in _history:
        import datetime as _dt
        ts_raw = run.get("created_at", "")
        try:
            ts = _dt.datetime.fromisoformat(ts_raw).strftime("%d.%m. %H:%M")
        except Exception:
            ts = ts_raw[:16]
        score_best = max(
            filter(None, [run.get("score_a"), run.get("score_b"), run.get("score_c")]),
            default=0.0,
        )
        is_fav = bool(run.get("is_favorite"))
        col_info, col_load, col_fav = st.columns([3, 1, 1])
        col_info.markdown(
            f"{'★ ' if is_fav else ''}{ts}  \n"
            f"<span style='font-size:0.75rem;color:#888'>"
            f"{run.get('site_name', '—')} · Score {score_best:.1f}</span>",
            unsafe_allow_html=True,
        )
        if col_load.button("↩", key=f"hist_load_{run['id']}", help="Laden"):
            _run = _get_run(run["id"])
            if _run:
                st.session_state.result = _run["state"]
                st.session_state.schritt = 6
                st.rerun()
        fav_icon = "★" if is_fav else "☆"
        if col_fav.button(fav_icon, key=f"hist_fav_{run['id']}", help="Favorit"):
            from app.tools.persistence import mark_favorite as _mark_fav, unmark_favorite as _unmark_fav
            if is_fav:
                _unmark_fav(_current_user, run["id"])
            else:
                _mark_fav(_current_user, run["id"])
            st.rerun()
```

---

## Aufgabe 3: `schritt_ergebnisse()` — Auto-Speichern + Favorit-Button

### 3a. Auto-Speichern nach Pipeline-Lauf

**Einfügeposition:** In `schritt_ergebnisse()`, direkt nach dem Öffnen der Funktion (erste Zeile nach `result = st.session_state.result`).

```python
    # ── Auto-Speichern (einmalig pro Lauf) ──────────────────────────────────
    if not st.session_state.get("_last_saved_run_id"):
        try:
            from app.tools.persistence import save_run as _save_run
            _rid = _save_run(_current_user, result)
            st.session_state["_last_saved_run_id"] = _rid
        except Exception as _e:
            st.caption(f"Speichern fehlgeschlagen: {_e}")
```

### 3b. Favorit-Button und Favorit-Label

**Einfügeposition:** In `schritt_ergebnisse()`, direkt nach der `st.divider()` am Ende der Varianten-Tabs (vor dem LLM-Analyse-Block, ca. `st.divider()` → `if result.get("rule_change_summary"):`).

```python
    # ── Als Favorit speichern ────────────────────────────────────────────────
    _run_id = st.session_state.get("_last_saved_run_id")
    if _run_id and _current_role in ("planner", "admin"):
        with st.expander("★ Als Favorit speichern", expanded=False):
            _fav_label = st.text_input(
                "Bezeichnung (optional)",
                placeholder=f"{result.get('site_geometry', {}).get('name', 'Lauf')} – {result.get('selected_variant', '')}",
                key="fav_label_input",
            )
            if st.button("Favorit setzen", key="set_favorite_btn", type="primary"):
                from app.tools.persistence import mark_favorite as _mark_fav_here
                _mark_fav_here(_current_user, _run_id, _fav_label)
                st.success("Als Favorit gespeichert.")
```

### 3c. Reset `_last_saved_run_id` bei neuer Berechnung

**Einfügeposition:** In der bestehenden "Neue Berechnung"-Button-Logik (suche nach `st.session_state.schritt = 1`). Die vorhandene Liste der zu löschenden Keys erweitern:

**Bestehender Code** (bereits in der Datei):
```python
        for _k in ("schritt", "result", "user_input", "site_geometry",
                   "custom_gewichtungen", "rule_overrides", "rule_change_request",
                   "projektziele", "adjacency_weights"):
            st.session_state[_k] = None
```

**Ersetzen durch:**
```python
        for _k in ("schritt", "result", "user_input", "site_geometry",
                   "custom_gewichtungen", "rule_overrides", "rule_change_request",
                   "projektziele", "adjacency_weights", "_last_saved_run_id"):
            st.session_state[_k] = None
```

---

## Aufgabe 4: Viewer-Rolle absichern

**Einfügeposition:** In `schritt_ergebnisse()` UND in der Funktion, die den Pipeline-Button rendert (suche nach `st.button("Berechnung starten"` o.ä.).

Viewer dürfen die Pipeline nicht starten. Suche die Stelle wo der Pipeline-Start-Button gerendert wird und ergänze:

```python
if _current_role == "viewer":
    st.info("Als Betrachter können Sie keine neue Berechnung starten.", icon="🔒")
else:
    # bestehender Button-Code
    if st.button("Berechnung starten", ...):
        ...
```

---

## Vollständige Einfügereihenfolge (Zusammenfassung)

```
streamlit_app.py:
  [1] Nach imports + set_page_config:
      → Authentifizierungs-Block (_authenticator.login, st.stop, _current_user, _current_role)

  [2] schritt_ergebnisse():
      Zeile 1: → Auto-Speichern (_last_saved_run_id)
      Nach Varianten-Tabs divider: → Favorit-Expander
      "Neue Berechnung"-Key-Liste: → _last_saved_run_id ergänzen

  [3] Pipeline-Start-Button:
      → if _current_role == "viewer": st.info(...); else: bestehender Code

  [4] Ende Sidebar-Sektion:
      → Logout-Button + History-Expander + Favoriten-Expander
```

---

## Wichtige Hinweise

- `_current_user` und `_current_role` sind modulweit verfügbar (definiert beim Login-Block ganz oben), nicht per Parameter übergeben
- `st.session_state["_last_saved_run_id"]` wird bewusst mit Underscore-Prefix definiert um Kollisionen mit App-Keys zu vermeiden
- `_authenticator.login()` mit `location="main"` zeigt das Formular im Hauptbereich (nicht Sidebar) — das ist korrekt und gewünscht
- Der Logout-Button muss `key="logout_btn"` haben um Streamlit-Widget-Konflikte zu vermeiden
- Viewer-Absicherung: NUR den Pipeline-Start-Button schützen — die Ergebnisseite (`schritt_ergebnisse`) darf Viewer sehen wenn ein Ergebnis in `session_state.result` geladen wurde

---

## Was du NICHT änderst

- Alle anderen Dateien außer `streamlit_app.py`
- Keine Agenten, keine Tools (außer Import von `persistence.py`)
- Bestehende `schritt_*`-Funktionen inhaltlich nicht verändern, nur ergänzen
