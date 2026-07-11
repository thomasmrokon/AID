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

            CREATE TABLE IF NOT EXISTS planning_stands (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user          TEXT NOT NULL,
                planning_type TEXT NOT NULL,
                label         TEXT NOT NULL,
                created_at    TEXT NOT NULL,
                parent_id     INTEGER,
                source_ref    TEXT,
                payload_json  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS teams (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS team_members (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id    INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                user       TEXT NOT NULL,
                role       TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(team_id, user)
            );

            CREATE TABLE IF NOT EXISTS projects (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id     INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                name        TEXT NOT NULL,
                description TEXT,
                created_by  TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                UNIQUE(team_id, name)
            );

            CREATE TABLE IF NOT EXISTS document_library (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id         INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                project_id      INTEGER REFERENCES projects(id) ON DELETE CASCADE,
                uploaded_by     TEXT NOT NULL,
                title           TEXT NOT NULL,
                filename        TEXT NOT NULL,
                mime_type       TEXT,
                scope           TEXT NOT NULL CHECK(scope IN ('team', 'project')),
                planning_blocks TEXT NOT NULL,
                rights_notice   INTEGER NOT NULL DEFAULT 0,
                created_at      TEXT NOT NULL,
                text_json       TEXT NOT NULL,
                meta_json       TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS document_chunks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL REFERENCES document_library(id) ON DELETE CASCADE,
                chunk_index INTEGER NOT NULL,
                content     TEXT NOT NULL,
                token_hint  INTEGER NOT NULL DEFAULT 0,
                meta_json   TEXT NOT NULL,
                UNIQUE(document_id, chunk_index)
            );

            CREATE TABLE IF NOT EXISTS decision_log (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id        INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                project_id     INTEGER REFERENCES projects(id) ON DELETE SET NULL,
                user           TEXT NOT NULL,
                planning_block TEXT NOT NULL,
                phase          TEXT NOT NULL,
                decision       TEXT NOT NULL,
                method         TEXT NOT NULL,
                rationale      TEXT,
                inputs_json    TEXT NOT NULL,
                sources_json   TEXT NOT NULL,
                created_at     TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_runs_user ON runs(user);
            CREATE INDEX IF NOT EXISTS idx_favorites_user ON favorites(user);
            CREATE INDEX IF NOT EXISTS idx_planning_stands_user_type ON planning_stands(user, planning_type);
            CREATE INDEX IF NOT EXISTS idx_team_members_user ON team_members(user);
            CREATE INDEX IF NOT EXISTS idx_projects_team ON projects(team_id);
            CREATE INDEX IF NOT EXISTS idx_docs_scope ON document_library(team_id, project_id, scope);
            CREATE INDEX IF NOT EXISTS idx_chunks_document ON document_chunks(document_id);
            CREATE INDEX IF NOT EXISTS idx_decisions_scope ON decision_log(team_id, project_id, planning_block);
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


# ---------------------------------------------------------------------------
# Planungsstände: Masterplanung, Gebäudeplanung, Prozessplanung
# ---------------------------------------------------------------------------

def save_planning_stand(
    user: str,
    planning_type: str,
    label: str,
    payload: dict[str, Any],
    *,
    parent_id: int | None = None,
    source_ref: str | None = None,
) -> int:
    """Speichert einen abgeschlossenen Planungsstand als wiederverwendbares Artefakt."""
    created_at = datetime.now(timezone.utc).isoformat()
    with _get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO planning_stands
                (user, planning_type, label, created_at, parent_id, source_ref, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user,
                planning_type,
                label,
                created_at,
                parent_id,
                source_ref,
                json.dumps(payload, ensure_ascii=False, default=str),
            ),
        )
        return cursor.lastrowid


def list_planning_stands(user: str, planning_type: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Listet gespeicherte Planungsstände ohne Payload."""
    with _get_db() as conn:
        if planning_type:
            rows = conn.execute(
                """
                SELECT id, user, planning_type, label, created_at, parent_id, source_ref
                FROM planning_stands
                WHERE user = ? AND planning_type = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user, planning_type, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, user, planning_type, label, created_at, parent_id, source_ref
                FROM planning_stands
                WHERE user = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user, limit),
            ).fetchall()
    return [dict(row) for row in rows]


def get_planning_stand(stand_id: int) -> dict[str, Any] | None:
    """Lädt einen gespeicherten Planungsstand inklusive Payload."""
    with _get_db() as conn:
        row = conn.execute("SELECT * FROM planning_stands WHERE id = ?", (stand_id,)).fetchone()
    if not row:
        return None
    result = dict(row)
    result["payload"] = json.loads(result.pop("payload_json"))
    return result


# ---------------------------------------------------------------------------
# Mandantenfaehige Teams, Projekte, Dokumentbibliothek und Decision Log
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def ensure_default_team(user: str, role: str = "admin") -> int:
    """Legt fuer bestehende Einzel-User einen Default-Mandanten an."""
    team_name = f"Team {user}"
    now = _now_iso()
    with _get_db() as conn:
        conn.execute("INSERT OR IGNORE INTO teams (name, created_at) VALUES (?, ?)", (team_name, now))
        team_id = int(conn.execute("SELECT id FROM teams WHERE name = ?", (team_name,)).fetchone()["id"])
        conn.execute(
            """
            INSERT INTO team_members (team_id, user, role, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(team_id, user) DO UPDATE SET role = excluded.role
            """,
            (team_id, user, role, now),
        )
    return team_id


def list_user_teams(user: str) -> list[dict[str, Any]]:
    with _get_db() as conn:
        rows = conn.execute(
            """
            SELECT t.id, t.name, tm.role, t.created_at
            FROM teams t
            JOIN team_members tm ON tm.team_id = t.id
            WHERE tm.user = ?
            ORDER BY t.name
            """,
            (user,),
        ).fetchall()
    return [dict(row) for row in rows]


def create_project(team_id: int, name: str, created_by: str, description: str = "") -> int:
    now = _now_iso()
    clean_name = (name or "Projekt").strip() or "Projekt"
    with _get_db() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO projects (team_id, name, description, created_by, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (team_id, clean_name, description, created_by, now),
        )
        row = conn.execute("SELECT id FROM projects WHERE team_id = ? AND name = ?", (team_id, clean_name)).fetchone()
    return int(row["id"])


def list_projects(team_id: int) -> list[dict[str, Any]]:
    with _get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, team_id, name, description, created_by, created_at
            FROM projects
            WHERE team_id = ?
            ORDER BY created_at DESC, name
            """,
            (team_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _chunk_text(text: str, chunk_size: int = 1800, overlap: int = 250) -> list[str]:
    clean = " ".join((text or "").split())
    if not clean:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(clean):
        end = min(len(clean), start + chunk_size)
        chunks.append(clean[start:end])
        if end >= len(clean):
            break
        start = max(0, end - overlap)
    return chunks


def save_library_document(
    *,
    team_id: int,
    uploaded_by: str,
    title: str,
    filename: str,
    mime_type: str = "",
    text: str = "",
    scope: str = "team",
    planning_blocks: list[str] | None = None,
    rights_notice: bool = False,
    project_id: int | None = None,
    meta: dict[str, Any] | None = None,
) -> int:
    if scope not in {"team", "project"}:
        raise ValueError("scope must be 'team' or 'project'")
    if scope == "project" and not project_id:
        raise ValueError("project_id is required for project documents")
    if not rights_notice:
        raise ValueError("rights_notice must be confirmed before upload")
    blocks = planning_blocks or []
    now = _now_iso()
    text_payload = {"text": text or "", "char_count": len(text or "")}
    with _get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO document_library
                (team_id, project_id, uploaded_by, title, filename, mime_type, scope,
                 planning_blocks, rights_notice, created_at, text_json, meta_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                team_id,
                project_id if scope == "project" else None,
                uploaded_by,
                title or filename,
                filename,
                mime_type,
                scope,
                json.dumps(blocks, ensure_ascii=False),
                1 if rights_notice else 0,
                now,
                json.dumps(text_payload, ensure_ascii=False),
                json.dumps(meta or {}, ensure_ascii=False, default=str),
            ),
        )
        doc_id = int(cursor.lastrowid)
        for idx, chunk in enumerate(_chunk_text(text or "")):
            conn.execute(
                """
                INSERT INTO document_chunks (document_id, chunk_index, content, token_hint, meta_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (doc_id, idx, chunk, max(1, len(chunk) // 4), json.dumps({}, ensure_ascii=False)),
            )
    return doc_id


def _hydrate_document_row(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["planning_blocks"] = _json_loads(item.get("planning_blocks"), [])
    item["meta"] = _json_loads(item.pop("meta_json", None), {})
    text_payload = _json_loads(item.pop("text_json", None), {})
    item["char_count"] = text_payload.get("char_count", len(text_payload.get("text", "")))
    return item


def list_library_documents(team_id: int, project_id: int | None = None, planning_block: str | None = None) -> list[dict[str, Any]]:
    with _get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM document_library
            WHERE team_id = ? AND (scope = 'team' OR project_id = ?)
            ORDER BY created_at DESC
            """,
            (team_id, project_id),
        ).fetchall()
    docs = [_hydrate_document_row(row) for row in rows]
    if planning_block:
        docs = [d for d in docs if planning_block in (d.get("planning_blocks") or [])]
    return docs


def get_library_document(document_id: int, *, team_id: int) -> dict[str, Any] | None:
    with _get_db() as conn:
        row = conn.execute(
            "SELECT * FROM document_library WHERE id = ? AND team_id = ?",
            (document_id, team_id),
        ).fetchone()
    if not row:
        return None
    item = _hydrate_document_row(row)
    with _get_db() as conn:
        full = conn.execute(
            "SELECT text_json FROM document_library WHERE id = ? AND team_id = ?",
            (document_id, team_id),
        ).fetchone()
    payload = _json_loads(full["text_json"] if full else None, {})
    item["text"] = payload.get("text", "")
    return item


def update_library_document_blocks(document_id: int, *, team_id: int, planning_blocks: list[str]) -> bool:
    clean = [b for b in planning_blocks if b in {"master", "layout", "process"}]
    with _get_db() as conn:
        cursor = conn.execute(
            "UPDATE document_library SET planning_blocks = ? WHERE id = ? AND team_id = ?",
            (json.dumps(clean, ensure_ascii=False), document_id, team_id),
        )
        return cursor.rowcount > 0


def delete_library_document(document_id: int, *, team_id: int, user: str | None = None) -> bool:
    """Deletes a library document and its chunks within a team scope."""
    with _get_db() as conn:
        row = conn.execute(
            "SELECT id, uploaded_by FROM document_library WHERE id = ? AND team_id = ?",
            (document_id, team_id),
        ).fetchone()
        if not row:
            return False
        conn.execute("DELETE FROM document_library WHERE id = ? AND team_id = ?", (document_id, team_id))
        return True


def search_library_chunks(
    *,
    team_id: int,
    project_id: int | None,
    planning_block: str,
    query: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    terms = [t.lower() for t in (query or "").replace("/", " ").replace(",", " ").split() if len(t) > 2]
    docs = list_library_documents(team_id, project_id, planning_block)
    if not docs:
        return []
    doc_ids = [d["id"] for d in docs]
    placeholders = ",".join("?" for _ in doc_ids)
    with _get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT c.*, d.title, d.filename, d.scope, d.project_id, d.planning_blocks
            FROM document_chunks c
            JOIN document_library d ON d.id = c.document_id
            WHERE c.document_id IN ({placeholders})
            """,
            doc_ids,
        ).fetchall()
    results: list[dict[str, Any]] = []
    for row in rows:
        content = row["content"] or ""
        lower = content.lower()
        score = sum(lower.count(term) for term in terms) if terms else 1
        if score <= 0:
            continue
        results.append({
            "document_id": row["document_id"],
            "chunk_index": row["chunk_index"],
            "title": row["title"],
            "filename": row["filename"],
            "scope": row["scope"],
            "project_id": row["project_id"],
            "score": score,
            "content": content,
            "excerpt": content[:500] + ("..." if len(content) > 500 else ""),
            "source_ref": f"Quelle: {row['title']} ({row['filename']}), Abschnitt {row['chunk_index'] + 1}",
        })
    results.sort(key=lambda r: (-r["score"], r["title"], r["chunk_index"]))
    return results[:limit]


def save_decision_log(
    *,
    team_id: int,
    user: str,
    planning_block: str,
    phase: str,
    decision: str,
    method: str,
    rationale: str = "",
    inputs: dict[str, Any] | None = None,
    sources: list[dict[str, Any]] | None = None,
    project_id: int | None = None,
) -> int:
    with _get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO decision_log
                (team_id, project_id, user, planning_block, phase, decision, method,
                 rationale, inputs_json, sources_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                team_id,
                project_id,
                user,
                planning_block,
                phase,
                decision,
                method,
                rationale,
                json.dumps(inputs or {}, ensure_ascii=False, default=str),
                json.dumps(sources or [], ensure_ascii=False, default=str),
                _now_iso(),
            ),
        )
        return int(cursor.lastrowid)


def list_decision_log(team_id: int, project_id: int | None = None, limit: int = 200) -> list[dict[str, Any]]:
    params: list[Any] = [team_id]
    where = "team_id = ?"
    if project_id is not None:
        where += " AND (project_id = ? OR project_id IS NULL)"
        params.append(project_id)
    params.append(limit)
    with _get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM decision_log
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["inputs"] = _json_loads(item.pop("inputs_json", None), {})
        item["sources"] = _json_loads(item.pop("sources_json", None), [])
        result.append(item)
    return result


def export_decision_log_markdown(team_id: int, project_id: int | None = None) -> str:
    rows = list_decision_log(team_id, project_id, limit=1000)
    lines = ["# Entscheidungsprotokoll", ""]
    for row in reversed(rows):
        lines.extend([
            f"## {row.get('phase')} · {row.get('decision')}",
            f"- Zeitpunkt: {row.get('created_at')}",
            f"- Baustein: {row.get('planning_block')}",
            f"- Methode: {row.get('method')}",
            f"- Bearbeiter: {row.get('user')}",
        ])
        if row.get("rationale"):
            lines.append(f"- Begründung: {row.get('rationale')}")
        sources = row.get("sources") or []
        if sources:
            lines.append("- Quellen:")
            for src in sources:
                lines.append(f"  - {src.get('source_ref') or src.get('title') or src}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"
