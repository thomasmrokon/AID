"""
AID Demo – Streamlit-UI
Augmented Industrial Design · Drees & Sommer × HS Mainz
"""

import os
import streamlit as st
import streamlit.components.v1 as components
from pathlib import Path
from PIL import Image
import yaml

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from app.graph import graph
from app.state import Nutzungstyp, VARIANTEN_GEWICHTUNGEN, DEMO_MASCHINENPARK
from app.agents.rules import RULES_PATH, TYPE_KEY_MAP
from app.tools.site import compute_building_envelope, get_demo_sites

# ---------------------------------------------------------------------------
# Seitenkonfiguration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="AID – Augmented Industrial Design",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Authentifizierung
# ---------------------------------------------------------------------------
import streamlit_authenticator as stauth
from app.tools.persistence import init_db as _init_db

_init_db()  # DB + Tabellen anlegen (idempotent)

_USERS_YAML = Path(__file__).parent / "app" / "data" / "users.yaml"
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

from app.tools.persistence import ensure_default_team as _ensure_default_team

try:
    _default_team_id = _ensure_default_team(_current_user, _current_role)
    st.session_state.setdefault("team_id", _default_team_id)
except Exception as _team_exc:
    st.session_state.setdefault("team_id", None)
    st.caption(f"Team-Kontext konnte nicht initialisiert werden: {_team_exc}")

# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

st.markdown("""
<style>
    /* ── Typography ───────────────────────────────────────────────────── */
    .aid-header { font-size: 0.85rem; color: #888; margin-bottom: 0.2rem; }
    .step-badge {
        display: inline-block; background: #1C3557; color: white;
        border-radius: 50%; width: 26px; height: 26px;
        text-align: center; line-height: 26px; font-weight: bold;
        margin-right: 8px; font-size: 0.85rem;
    }
    .score-chip {
        display: inline-block; padding: 2px 10px;
        border-radius: 12px; font-size: 0.8rem; font-weight: bold;
        margin: 2px;
    }
    .phase-badge {
        display: inline-block; background: #1C3557; color: white;
        border-radius: 6px; min-width: 36px; padding: 2px 7px;
        text-align: center; font-weight: bold; margin-right: 8px;
        font-size: 0.82rem; line-height: 22px;
    }
    .nav-link, .nav-link:visited {
        display: block;
        width: 100%;
        box-sizing: border-box;
        padding: 8px 10px;
        margin: 4px 0;
        border: 1px solid #D5DEE8;
        border-radius: 7px;
        background: #FFFFFF;
        color: #2D3748 !important;
        text-decoration: none !important;
        text-align: left;
        font-size: 0.88rem;
        line-height: 1.25;
    }
    .nav-link:hover {
        border-color: #90A4B8;
        background: #F2F6FA;
        color: #1C3557 !important;
        text-decoration: none !important;
    }
    .nav-link.active {
        border-color: #1C3557;
        background: #EAF1F8;
        color: #1C3557 !important;
        font-weight: 650;
    }
    .nav-link.disabled {
        color: #9AA5B1 !important;
        background: #F7F8FA;
        border-color: #E2E8F0;
        pointer-events: none;
    }

    section[data-testid="stSidebar"] div.stButton > button {
        display: flex !important;
        justify-content: flex-start !important;
        text-align: left !important;
        padding-left: 10px !important;
    }
    section[data-testid="stSidebar"] div.stButton > button div[data-testid="stMarkdownContainer"],
    section[data-testid="stSidebar"] div.stButton > button div[data-testid="stMarkdownContainer"] > p {
        width: 100% !important;
        text-align: left !important;
    }
    .empfohlen { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }

    /* ── Primary buttons: Anthrazit-Blau statt Streamlit-Rot ─────────── */
    div.stButton > button[kind="primary"] {
        background-color: #1C3557 !important;
        border: 1px solid #1C3557 !important;
        color: #ffffff !important;
        font-weight: 500 !important;
        letter-spacing: 0.02em !important;
    }
    div.stButton > button[kind="primary"]:hover {
        background-color: #24466F !important;
        border-color: #24466F !important;
        color: #ffffff !important;
    }
    div.stButton > button[kind="primary"]:active {
        background-color: #152840 !important;
        border-color: #152840 !important;
    }

    /* ── Secondary buttons: dezenter Rahmen ──────────────────────────── */
    div.stButton > button[kind="secondary"] {
        border-color: #CBD5E0 !important;
        color: #2D3748 !important;
        background-color: #FFFFFF !important;
    }
    div.stButton > button[kind="secondary"]:hover {
        background-color: #F7FAFC !important;
        border-color: #90A4B8 !important;
    }

    /* ── Download-Buttons: Outline-Stil ──────────────────────────────── */
    div.stDownloadButton > button {
        background-color: #F7FAFC !important;
        border: 1px solid #CBD5E0 !important;
        color: #1C3557 !important;
        font-weight: 500 !important;
    }
    div.stDownloadButton > button:hover {
        background-color: #EBF4F8 !important;
        border-color: #1C3557 !important;
    }

    /* ── Sidebar ─────────────────────────────────────────────────────── */
    section[data-testid="stSidebar"] {
        background-color: #F8F9FA !important;
    }
    section[data-testid="stSidebar"] .stMarkdown p {
        font-size: 0.85rem;
        line-height: 1.6;
    }

    section[data-testid="stSidebar"] button[data-testid^="stBaseButton"] {
        justify-content: flex-start !important;
        text-align: left !important;
    }
    section[data-testid="stSidebar"] button[data-testid^="stBaseButton"] div,
    section[data-testid="stSidebar"] button[data-testid^="stBaseButton"] p,
    section[data-testid="stSidebar"] button[data-testid^="stBaseButton"] span {
        text-align: left !important;
        justify-content: flex-start !important;
        width: 100% !important;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Session State initialisieren
# ---------------------------------------------------------------------------

if "schritt" not in st.session_state:
    st.session_state.schritt = -1
if "masterplan" not in st.session_state:
    st.session_state.masterplan = None
if "alignment_angles_cache" not in st.session_state:
    st.session_state.alignment_angles_cache = {}   # site_id → list[dict]
if "result" not in st.session_state:
    st.session_state.result = None
if "user_input" not in st.session_state:
    st.session_state.user_input = None
if "site_geometry" not in st.session_state:
    st.session_state.site_geometry = None  # Layout-Schnittstelle: Gebäudeparzelle aus Masterplanung
if "building_parcels" not in st.session_state:
    st.session_state.building_parcels = []
if "selected_building_parcel_id" not in st.session_state:
    st.session_state.selected_building_parcel_id = None
if "building_parcel" not in st.session_state:
    st.session_state.building_parcel = None
if "mp_completed_subphases" not in st.session_state:
    st.session_state.mp_completed_subphases = []
if "custom_gewichtungen" not in st.session_state:
    st.session_state.custom_gewichtungen = None
if "rule_overrides" not in st.session_state:
    st.session_state.rule_overrides = None
if "rule_change_request" not in st.session_state:
    st.session_state.rule_change_request = None
if "adjacency_weights" not in st.session_state:
    st.session_state.adjacency_weights = {}
if "fg_selected_edge" not in st.session_state:
    st.session_state.fg_selected_edge = None   # "src__tgt" | None
if "fg_pending_node" not in st.session_state:
    st.session_state.fg_pending_node = None    # "NodeA" | "NodeA+NodeB" | None
if "zone_splits" not in st.session_state:
    st.session_state.zone_splits = {}
if "gap_strategy" not in st.session_state:
    st.session_state.gap_strategy = "none"
if "project_id" not in st.session_state:
    st.session_state.project_id = None





def _svg_viewer_html(svg: str, *, element_id: str = "aid_svg_viewer") -> str:
    import json
    svg_json = json.dumps(svg)
    return f"""
<div id="{element_id}" class="aid-svg-viewer">
  <div class="aid-svg-toolbar">
    <button type="button" data-action="zoom-in">+</button>
    <button type="button" data-action="zoom-out">-</button>
    <button type="button" data-action="reset">Reset</button>
    <button type="button" data-action="fullscreen">Vollbild</button>
    <a data-action="download" download="lageplan.svg">SVG</a>
  </div>
  <div class="aid-svg-stage"></div>
</div>
<style>
  #{element_id} {{
    height: 720px;
    border: 1px solid #D5DEE8;
    border-radius: 8px;
    background: #F8FAFC;
    overflow: hidden;
    position: relative;
    font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }}
  #{element_id}:fullscreen {{ height: 100vh; border-radius: 0; }}
  #{element_id} .aid-svg-toolbar {{
    position: absolute;
    z-index: 5;
    top: 12px;
    left: 12px;
    display: flex;
    gap: 8px;
    align-items: center;
    padding: 6px;
    background: rgba(255,255,255,.94);
    border: 1px solid #D5DEE8;
    border-radius: 7px;
    box-shadow: 0 8px 24px rgba(28,53,87,.12);
  }}
  #{element_id} button, #{element_id} a[data-action="download"] {{
    border: 1px solid #C9D5E3;
    background: #FFFFFF;
    color: #1C3557;
    border-radius: 5px;
    min-width: 36px;
    height: 32px;
    padding: 0 10px;
    font-weight: 700;
    cursor: pointer;
    text-decoration: none;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }}
  #{element_id} .aid-svg-stage {{ width: 100%; height: 100%; cursor: grab; }}
  #{element_id} .aid-svg-stage:active {{ cursor: grabbing; }}
  #{element_id} svg {{ width: 100%; height: 100%; display: block; user-select: none; }}
</style>
<script>
(() => {{
  const root = document.getElementById({json.dumps(element_id)});
  const svgMarkup = {svg_json};
  const stage = root.querySelector('.aid-svg-stage');
  stage.innerHTML = svgMarkup;
  const svg = stage.querySelector('svg');
  const initial = svg.getAttribute('viewBox').split(/\\s+/).map(Number);
  let box = initial.slice();
  const apply = () => svg.setAttribute('viewBox', box.map(v => Number(v).toFixed(3)).join(' '));
  const zoom = (factor, cx = box[0] + box[2] / 2, cy = box[1] + box[3] / 2) => {{
    const nw = box[2] * factor;
    const nh = box[3] * factor;
    box[0] = cx - (cx - box[0]) * factor;
    box[1] = cy - (cy - box[1]) * factor;
    box[2] = nw;
    box[3] = nh;
    apply();
  }};
  root.querySelector('[data-action="zoom-in"]').addEventListener('click', () => zoom(0.82));
  root.querySelector('[data-action="zoom-out"]').addEventListener('click', () => zoom(1.22));
  root.querySelector('[data-action="reset"]').addEventListener('click', () => {{ box = initial.slice(); apply(); }});
  root.querySelector('[data-action="fullscreen"]').addEventListener('click', async () => {{
    if (!document.fullscreenElement && root.requestFullscreen) await root.requestFullscreen();
    else if (document.exitFullscreen) await document.exitFullscreen();
  }});
  const download = root.querySelector('[data-action="download"]');
  const blob = new Blob([svgMarkup], {{type: 'image/svg+xml'}});
  download.href = URL.createObjectURL(blob);
  stage.addEventListener('wheel', event => {{
    event.preventDefault();
    const rect = svg.getBoundingClientRect();
    const px = (event.clientX - rect.left) / rect.width;
    const py = (event.clientY - rect.top) / rect.height;
    const cx = box[0] + px * box[2];
    const cy = box[1] + py * box[3];
    zoom(event.deltaY < 0 ? 0.88 : 1.14, cx, cy);
  }}, {{passive: false}});
  let dragging = false;
  let last = null;
  stage.addEventListener('pointerdown', event => {{ dragging = true; last = [event.clientX, event.clientY]; stage.setPointerCapture(event.pointerId); }});
  stage.addEventListener('pointermove', event => {{
    if (!dragging || !last) return;
    const rect = svg.getBoundingClientRect();
    const dx = (event.clientX - last[0]) / rect.width * box[2];
    const dy = (event.clientY - last[1]) / rect.height * box[3];
    box[0] -= dx;
    box[1] -= dy;
    last = [event.clientX, event.clientY];
    apply();
  }});
  stage.addEventListener('pointerup', () => {{ dragging = false; last = null; }});
  stage.addEventListener('pointerleave', () => {{ dragging = false; last = null; }});
  apply();
}})();
</script>
"""


def _render_svg_iframe(svg: str, *, element_id: str = "aid_svg_viewer", height: int = 760) -> None:
    from urllib.parse import quote

    html = _svg_viewer_html(svg, element_id=element_id)
    if hasattr(st, "iframe"):
        data_url = "data:text/html;charset=utf-8," + quote(html)
        st.iframe(data_url, height=height)
    else:
        components.html(html, height=height, scrolling=False)



def _plotly_viewer_html(fig, *, element_id: str = "aid_plotly_viewer") -> str:
    import json
    html = fig.to_html(include_plotlyjs="cdn", full_html=False, config={"responsive": True, "displaylogo": False})
    html_json = json.dumps(html)
    return f"""
<div id="{element_id}" class="aid-plotly-viewer">
  <div class="aid-plotly-toolbar"><button type="button" data-action="fullscreen">Vollbild</button></div>
  <div class="aid-plotly-stage"></div>
</div>
<style>
  #{element_id} {{ height: 720px; border: 1px solid #D5DEE8; border-radius: 8px; background: white; position: relative; overflow: hidden; }}
  #{element_id}:fullscreen {{ height: 100vh; border-radius: 0; }}
  #{element_id} .aid-plotly-toolbar {{ position: absolute; z-index: 5; top: 12px; left: 12px; display: flex; gap: 8px; padding: 6px; background: rgba(255,255,255,.94); border: 1px solid #D5DEE8; border-radius: 7px; box-shadow: 0 8px 24px rgba(28,53,87,.12); }}
  #{element_id} button {{ border: 1px solid #C9D5E3; background: #FFFFFF; color: #1C3557; border-radius: 5px; height: 32px; padding: 0 10px; font-weight: 700; cursor: pointer; }}
  #{element_id} .aid-plotly-stage {{ width: 100%; height: 100%; padding-top: 48px; box-sizing: border-box; }}
</style>
<script>
(() => {{
  const root = document.getElementById({json.dumps(element_id)});
  root.querySelector('.aid-plotly-stage').innerHTML = {html_json};
  root.querySelector('[data-action="fullscreen"]').addEventListener('click', async () => {{
    if (!document.fullscreenElement && root.requestFullscreen) await root.requestFullscreen();
    else if (document.exitFullscreen) await document.exitFullscreen();
  }});
}})();
</script>
"""


def _render_plotly_viewer(title: str, fig, *, key: str) -> None:
    html = _plotly_viewer_html(fig, element_id=f"aid_plotly_viewer_{key}")
    if hasattr(st, "dialog"):
        @st.dialog(title, width="large")
        def _dialog():
            components.html(html, height=760, scrolling=False)
            if st.button("Viewer schließen", key=f"{key}_close"):
                st.session_state[f"{key}_open"] = False
                st.rerun()
        _dialog()
    else:
        components.html(html, height=760, scrolling=False)



def _render_interactive_plotly_viewer(title: str, fig, *, key: str):
    """Plotly viewer inside a Streamlit dialog with selection events."""
    event_key = f"{key}_selection_event"
    if hasattr(st, "dialog"):
        @st.dialog(title, width="large")
        def _dialog():
            st.caption("Knoten oder Kanten direkt im Viewer anklicken. Die Bearbeitung erscheint darunter im Planungsdialog.")
            event = st.plotly_chart(
                fig,
                use_container_width=True,
                key=f"{key}_plotly_select",
                on_select="rerun",
                config={"responsive": True, "displaylogo": False},
            )
            st.session_state[event_key] = event
            c1, c2 = st.columns([1, 1])
            with c1:
                if st.button("Auswahl zurücksetzen", key=f"{key}_clear_selection"):
                    st.session_state.fg_selected_edge = None
                    st.session_state.fg_pending_node = None
                    st.rerun()
            with c2:
                if st.button("Viewer schließen", key=f"{key}_close_interactive"):
                    st.session_state[f"{key}_open"] = False
                    st.rerun()
        _dialog()
        return st.session_state.get(event_key)
    st.warning("Interaktive Dialoge werden von dieser Streamlit-Version nicht unterstützt.", icon=None)
    return None


def _render_svg_viewer(title: str, svg: str, *, key: str) -> None:
    html = _svg_viewer_html(svg, element_id=f"aid_svg_viewer_{key}")
    if hasattr(st, "dialog"):
        @st.dialog(title, width="large")
        def _dialog():
            components.html(html, height=760, scrolling=False)
            if st.button("Viewer schließen", key=f"{key}_close"):
                st.session_state[f"{key}_open"] = False
                st.rerun()
        _dialog()
    else:
        st.warning("Dialoge werden von dieser Streamlit-Version nicht unterstützt; Viewer wird eingebettet angezeigt.", icon=None)
        components.html(html, height=760, scrolling=False)


def _apply_masterplan_variant(mp: dict, variant_id: str | None) -> dict:
    variants = mp.get("variants") or []
    selected = next((v for v in variants if v.get("id") == variant_id), None) or (variants[0] if variants else None)
    if not selected:
        return mp
    for key in ("building_parcels", "selected_building_parcel_id", "building_parcel", "hauptgebaeude", "gebaeude",
                "nebenbauten", "erschliessung", "freizonen", "infrastruktur", "flaechenbilanz", "score"):
        if key in selected:
            mp[key] = selected[key]
    mp["selected_masterplan_variant_id"] = selected.get("id")
    return mp


def _render_legal_doc_panel() -> None:
    st.markdown("#### Baurechtsdokumente auswerten")
    st.caption("Baurechtswerte können aus der Team-/Projektbibliothek oder aus temporären Uploads extrahiert werden.")

    try:
        from app.tools.persistence import get_library_document, list_library_documents, save_decision_log, search_library_chunks
        from app.tools.legal_docs import analyse_baurecht_documents, extract_uploaded_document
        team_id = st.session_state.get("team_id")
        project_id = st.session_state.get("project_id")
        library_docs = list_library_documents(team_id, project_id, "master") if team_id else []
        rag_sources = search_library_chunks(
            team_id=team_id,
            project_id=project_id,
            planning_block="master",
            query="GRZ GFZ Gebäudehöhe Bebauungsplan Baugrenze Baulinie Stellplatzsatzung Abstandsfläche Nutzungsart",
            limit=8,
        ) if team_id else []
    except Exception as exc:
        library_docs = []
        rag_sources = []
        analyse_baurecht_documents = None
        extract_uploaded_document = None
        get_library_document = None
        save_decision_log = None
        st.caption(f"Bibliothekskontext nicht verfügbar: {exc}")

    st.session_state["mp_rag_sources"] = rag_sources
    if library_docs:
        st.markdown("**Verfügbare Masterplanungs-Dokumente**")
        for d in library_docs[:8]:
            st.caption(f"Quelle: {d.get('title')} ({d.get('filename')}) · {d.get('char_count', 0)} Zeichen")
        if st.button("Bibliotheksdokumente für Baurecht analysieren", type="primary", use_container_width=True, key="mp_analyse_library_legal_docs"):
            try:
                docs = []
                for d in library_docs:
                    full = get_library_document(int(d.get("id")), team_id=st.session_state.get("team_id")) if get_library_document else None
                    if full and full.get("text"):
                        docs.append({
                            "name": full.get("title") or full.get("filename"),
                            "text": full.get("text"),
                            "char_count": full.get("char_count", 0),
                            "source_ref": f"Quelle: {full.get('title')} ({full.get('filename')})",
                        })
                analysis = analyse_baurecht_documents(docs) if analyse_baurecht_documents else {}
                analysis["documents_scope"] = "library"
                analysis["sources"] = [{"source_ref": d.get("source_ref"), "title": d.get("name")} for d in docs]
                st.session_state["mp_legal_doc_analysis"] = analysis
                st.session_state["mp_legal_doc_texts"] = docs
                st.rerun()
            except Exception as exc:
                st.error(f"Bibliotheksanalyse fehlgeschlagen: {exc}", icon=None)
    else:
        st.caption("Keine Masterplanungs-Dokumente in der Bibliothek gefunden.")

    if rag_sources:
        with st.expander("Gefundene Quellen aus der Bibliothek", expanded=False):
            for src in rag_sources:
                st.markdown(f"**{src.get('source_ref')}**")
                st.caption(src.get("excerpt", ""))

    uploaded_docs = st.file_uploader(
        "Temporäre Baurechtsdokumente analysieren",
        type=["pdf", "txt", "md", "docx"],
        accept_multiple_files=True,
        key="mp_legal_doc_upload",
    )
    st.caption("Temporäre Uploads werden analysiert, aber nicht automatisch in der Bibliothek gespeichert.")
    if uploaded_docs and st.button("Temporäre Uploads analysieren", use_container_width=True, key="mp_analyse_legal_docs"):
        try:
            docs = [extract_uploaded_document(doc) for doc in uploaded_docs] if extract_uploaded_document else []
            analysis = analyse_baurecht_documents(docs) if analyse_baurecht_documents else {}
            analysis["documents_scope"] = "temporary_upload"
            analysis["sources"] = [{"source_ref": f"Quelle: {d.get('name')} (temporärer Upload)", "title": d.get("name")} for d in docs]
            st.session_state["mp_legal_doc_analysis"] = analysis
            st.session_state["mp_legal_doc_texts"] = docs
            st.rerun()
        except Exception as exc:
            st.error(f"Dokumentanalyse fehlgeschlagen: {exc}", icon=None)

    analysis = st.session_state.get("mp_legal_doc_analysis") or {}
    if not analysis:
        return

    values = analysis.get("values") or {}
    source_label = "LLM" if analysis.get("source") == "llm" else "regelbasierte Texterkennung"
    scope_label = "Bibliothek" if analysis.get("documents_scope") == "library" else "temporärer Upload"
    st.markdown(f"**Analyseergebnis** · {source_label} · {scope_label}")
    a1, a2, a3 = st.columns(3)
    a1.metric("GRZ", values.get("grz", "–"))
    a2.metric("GFZ", values.get("gfz", "–"))
    a3.metric("Gebäudehöhe", f"{values.get('max_gebaeudehoehe_m', '–')} m")

    if st.button("Erkannte Werte in Parameter übernehmen", use_container_width=True, key="mp_apply_legal_doc_values"):
        value_map = {
            "grz": "mp_grz",
            "gfz": "mp_gfz",
            "max_gebaeudehoehe_m": "mp_max_gebaeudehoehe_m",
            "regelgeschoss_hoehe_m": "mp_regelgeschoss_hoehe_m",
            "abstandsfaktor": "mp_abstandsfaktor",
        }
        pending_values = {}
        applied_sources = analysis.get("sources") or st.session_state.get("mp_rag_sources", [])
        for src, dst in value_map.items():
            if values.get(src) is not None:
                pending_values[dst] = float(values[src])
                try:
                    if save_decision_log and st.session_state.get("team_id"):
                        save_decision_log(
                            team_id=st.session_state.get("team_id"),
                            project_id=st.session_state.get("project_id"),
                            user=_current_user,
                            planning_block="master",
                            phase="1.2",
                            decision=f"Baurechtsparameter {src} übernommen",
                            method=f"{source_label} aus {scope_label}",
                            rationale=f"Wert {values.get(src)} wurde aus Baurechtsdokumenten übernommen.",
                            inputs={src: values.get(src)},
                            sources=applied_sources,
                        )
                except Exception as exc:
                    st.caption(f"Decision Log für {src} konnte nicht geschrieben werden: {exc}")
        notes = analysis.get("notes") or []
        hint_parts = list(st.session_state.get("mp_baurecht_hinweise", "").splitlines())
        for note in notes:
            txt = str(note)
            if txt and txt not in hint_parts:
                hint_parts.append(txt)
        sp_rule = values.get("stellplaetze_je_flaeche")
        if isinstance(sp_rule, dict):
            hint_parts.append(f"Stellplatzsatzung: {sp_rule.get('anzahl')} SP je {sp_rule.get('flaeche_m2')} m²")
        for src in applied_sources[:5]:
            ref = src.get("source_ref") if isinstance(src, dict) else str(src)
            if ref and ref not in hint_parts:
                hint_parts.append(ref)
        st.session_state["mp_apply_legal_doc_pending"] = {
            "values": pending_values,
            "hinweise": "\n".join(p for p in hint_parts if p),
        }
        st.rerun()

    with st.expander("Fundstellen und Hinweise", expanded=False):
        for item in (analysis.get("evidence") or [])[:10]:
            st.markdown(f"**{item.get('field', 'Wert')}**: {item.get('excerpt', '')}")
        for src in (analysis.get("sources") or [])[:8]:
            st.caption(src.get("source_ref") or src.get("title"))
        notes = analysis.get("notes") or []
        if notes:
            st.write("Hinweise: " + ", ".join(str(n) for n in notes[:12]))


def _mark_master_subphase_done(subphase: str | None) -> None:
    if not subphase:
        return
    done = list(st.session_state.get("mp_completed_subphases", []))
    if subphase not in done:
        done.append(subphase)
    st.session_state.mp_completed_subphases = done
if "projektziele" not in st.session_state:
    st.session_state.projektziele = []
if "mep_anforderungen" not in st.session_state:
    st.session_state.mep_anforderungen = {}
if "tragwerk_config" not in st.session_state:
    st.session_state.tragwerk_config = {}
if "gis_site" not in st.session_state:
    st.session_state.gis_site = None
if "topology_diagram" not in st.session_state:
    st.session_state.topology_diagram = None
if "fg_edges" not in st.session_state:
    st.session_state.fg_edges = None

# Sidebar-Navigation nutzt Query-Parameter, damit die Einträge echte linksbündige Links sein können.
_query_step = st.query_params.get("step")
_query_mp = st.query_params.get("mp")
if _query_mp is not None:
    st.session_state.mp_subphase = _query_mp
if _query_step is not None and st.session_state.get("_active_query_step") != _query_step:
    try:
        st.session_state.schritt = int(_query_step)
        st.session_state["_active_query_step"] = _query_step
    except (TypeError, ValueError):
        pass


# ---------------------------------------------------------------------------
# Ausrichtungs-UI (Gebäudeflucht)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# UI-Layout-Helfer
# ---------------------------------------------------------------------------

def render_step_header(phase: str, title: str, description: str | None = None) -> None:
    """Einheitlicher Kopfbereich für Bearbeitungsschritte."""
    st.markdown(f'<span class="phase-badge">{phase}</span> **{title}**', unsafe_allow_html=True)
    if description:
        st.caption(description)


def render_step_footer(
    *,
    back_step: int | None = None,
    next_step: int | None = None,
    next_label: str = "Weiter",
    back_label: str = "Zurück",
    next_type: str = "primary",
) -> bool:
    """Einheitliche Zurück/Weiter-Zeile. Gibt True zurück, wenn Weiter geklickt wurde."""
    st.divider()
    col_back, col_next = st.columns([1, 3])
    with col_back:
        if back_step is not None and st.button(f"← {back_label}", use_container_width=True):
            st.session_state.schritt = back_step
            st.rerun()
    with col_next:
        if next_step is not None and st.button(next_label, type=next_type, use_container_width=True):
            st.session_state.schritt = next_step
            st.rerun()
    return False


def render_input_review_columns(ratio: tuple[float, float] = (1, 2)):
    """Standardlayout A: Eingaben links, Prüfung/Preview rechts."""
    return st.columns(list(ratio), gap="large")


def render_workspace_columns(ratio: tuple[float, float] = (2.2, 1)):
    """Standardlayout B: Arbeitsfläche links, Inspector rechts."""
    return st.columns(list(ratio), gap="large")


def _alignment_ui(site: dict, key_prefix: str) -> float | None:
    """Zeigt die Ausrichtungs-Auswahl und gibt den gewählten Winkel zurück.

    None  = geometrische Hauptachse (bisheriges Verhalten).
    float = Winkel in Grad von der West-Ost-Achse, gegen Uhrzeigersinn positiv.
    """
    geo_angle = None  # wird nach Auswahl befüllt

    wgs84 = site.get("polygon_wgs84")
    has_real_location = bool(wgs84 and len(wgs84) >= 3)

    st.divider()
    st.markdown("**Gebäudeausrichtung / Fluchtlinie**")

    mode_options = ["Geometrisch (Grundstücksfläche)", "Benutzerdefiniert"]
    if has_real_location:
        mode_options.insert(1, "Straßenflucht (OSM)")

    mode = st.radio(
        "Ausrichtungsmethode",
        mode_options,
        horizontal=True,
        key=f"{key_prefix}_align_mode",
        label_visibility="collapsed",
        help=(
            "**Geometrisch**: Achse des flächenmaximalen Baufeld-Rechtecks.\n\n"
            "**Straßenflucht**: Gebäudeachse parallel zur angrenzenden Straße (aus OSM).\n\n"
            "**Benutzerdefiniert**: Eigener Winkel, z.B. aus Bebauungsplan."
        ),
    )

    if mode == "Geometrisch (Grundstücksfläche)":
        st.caption("Achse wird automatisch aus der Grundstücksgeometrie berechnet.")
        return None

    if mode == "Straßenflucht (OSM)" and has_real_location:
        # Centroid aus polygon_wgs84 — Format: [[lat, lon], ...]
        lats = [p[0] for p in wgs84]
        lons = [p[1] for p in wgs84]
        clat, clon = sum(lats) / len(lats), sum(lons) / len(lons)
        cache_key = f"{clat:.5f},{clon:.5f}"

        if cache_key not in st.session_state.alignment_angles_cache:
            with st.spinner("Straßenrichtungen aus OSM laden…"):
                from app.tools.gis import fetch_street_angles
                angles = fetch_street_angles(clat, clon, radius_m=150)
            st.session_state.alignment_angles_cache[cache_key] = angles
        else:
            angles = st.session_state.alignment_angles_cache[cache_key]

        if not angles:
            st.caption("Keine Straßen im Umkreis von 150 m gefunden. Bitte Methode wechseln.")
            return None

        def _angle_label(a: dict) -> str:
            deg = a["angle_deg"]
            name = a["name"] or "Straße"
            if deg < 10 or deg > 170:
                orient = "West–Ost"
            elif 80 < deg < 100:
                orient = "Nord–Süd"
            elif deg < 90:
                orient = f"{deg:.0f}° (NE–SW)"
            else:
                orient = f"{deg:.0f}° (NW–SE)"
            return f"{name} · {orient}"

        sel = st.radio(
            "Erkannte Straßen",
            options=list(range(len(angles))),
            format_func=lambda i: _angle_label(angles[i]),
            key=f"{key_prefix}_street_sel",
        )
        chosen = angles[sel]["angle_deg"]
        st.caption(
            f"Gebäudeachse parallel zu **{angles[sel]['name'] or 'Straße'}** "
            f"— {chosen:.0f}° von West–Ost."
        )
        return chosen

    # Benutzerdefiniert
    st.caption(
        "0° = Gebäude liegt West–Ost · 90° = Nord–Süd · "
        "Positive Werte: gegen Uhrzeigersinn."
    )
    custom = st.number_input(
        "Winkel (° von West–Ost-Achse)",
        min_value=-90.0,
        max_value=90.0,
        value=0.0,
        step=5.0,
        key=f"{key_prefix}_custom_angle",
        help="Aus dem Bebauungsplan oder Vermessungsplan ablesen.",
    )
    return float(custom)


# ---------------------------------------------------------------------------
# STARTSEITE
# ---------------------------------------------------------------------------

def schritt_startseite():
    st.markdown("# Augmented Industrial Design")
    st.caption("KI-gestützte Planungsbausteine für Industriebau: vom Grundstück über Gebäudevarianten bis zum Prozesslayout.")
    st.divider()

    st.markdown(
        "Die Anwendung ist in drei eigenständige Planungsbausteine gegliedert. "
        "Jeder Baustein kann mit gespeicherten Planungsständen aus vorgelagerten Bausteinen arbeiten."
    )

    c1, c2, c3 = st.columns(3, gap="large")
    with c1:
        st.markdown("### Masterplanung")
        st.write("Grundstück, Baurecht, Verkehr/Infrastruktur und Gebäudeparzellen auf dem Gesamtgrundstück.")
        if st.button("Masterplanung öffnen", type="primary", use_container_width=True, key="home_master"):
            st.session_state.schritt = 1
            st.rerun()
    with c2:
        st.markdown("### Gebäudeplanung")
        st.write("Auswahl einer Gebäudeparzelle, Flächenprogramm, Funktionsgraph, Regelwerk und Layoutvarianten.")
        if st.button("Gebäudeplanung öffnen", type="primary", use_container_width=True, key="home_building"):
            st.session_state.schritt = 20
            st.rerun()
    with c3:
        st.markdown("### Prozessplanung")
        st.write("Auswahl einer Fläche aus der Gebäudeplanung und Erstellung oder Übertragung eines Prozesslayouts.")
        if st.button("Prozessplanung öffnen", type="primary", use_container_width=True, key="home_process"):
            st.session_state.schritt = 7
            st.rerun()

    st.divider()
    st.markdown("**Administrative Bereiche**")
    a1, a2 = st.columns(2)
    with a1:
        if st.button("Meine Planungsstände anzeigen", use_container_width=True, key="home_profile"):
            st.session_state.schritt = -2
            st.rerun()
    with a2:
        if st.button("Dokumentbibliothek öffnen", use_container_width=True, key="home_library"):
            st.session_state.schritt = -3
            st.rerun()


# ---------------------------------------------------------------------------
# PROFIL / PLANUNGSSTÄNDE
# ---------------------------------------------------------------------------

def schritt_profil():
    render_step_header(
        "Profil",
        "Meine Planungsstände",
        "Übersicht der gespeicherten Masterplanungen, Gebäudeplanungen und Prozessplanungen."
    )
    from app.tools.persistence import list_planning_stands

    if st.button("← Zurück zur Startseite", use_container_width=False, key="profile_back_home"):
        st.session_state.schritt = -1
        st.rerun()

    tabs = st.tabs(["Masterplanungen", "Gebäudeplanungen", "Prozessplanungen"])
    type_specs = [
        ("masterplan", "Masterplanung"),
        ("building_plan", "Gebäudeplanung"),
        ("process_plan", "Prozessplanung"),
    ]
    for tab, (ptype, label) in zip(tabs, type_specs):
        with tab:
            rows = list_planning_stands(_current_user, ptype, limit=100)
            if not rows:
                st.info(f"Noch keine gespeicherten {label}en vorhanden.", icon=None)
                continue
            import pandas as pd
            st.dataframe(
                pd.DataFrame([{
                    "ID": r.get("id"),
                    "Bezeichnung": r.get("label"),
                    "Erstellt": str(r.get("created_at", ""))[:16],
                    "Quelle": r.get("source_ref") or "",
                    "Parent": r.get("parent_id") or "",
                } for r in rows]),
                use_container_width=True,
                hide_index=True,
            )


# ---------------------------------------------------------------------------
# DOKUMENTBIBLIOTHEK / ENTSCHEIDUNGSPROTOKOLL
# ---------------------------------------------------------------------------

def schritt_dokumentbibliothek():
    render_step_header(
        "Admin",
        "Dokumentbibliothek und Entscheidungsprotokoll",
        "Team- und projektbezogene Planungsgrundlagen fuer nachvollziehbare Empfehlungen und Entscheidungen.",
    )
    from app.tools.legal_docs import extract_uploaded_document
    from app.tools.persistence import (
        create_project,
        export_decision_log_markdown,
        list_decision_log,
        list_library_documents,
        get_library_document,
        update_library_document_blocks,
        delete_library_document,
        list_projects,
        list_user_teams,
        save_library_document,
    )

    if st.button("← Zurueck zur Startseite", use_container_width=False, key="library_back_home"):
        st.session_state.schritt = -1
        st.rerun()

    teams = list_user_teams(_current_user)
    if not teams:
        st.warning("Kein Team-Kontext vorhanden.", icon=None)
        return

    team_ids = [t["id"] for t in teams]
    current_team = st.session_state.get("team_id") or team_ids[0]
    team_id = st.selectbox(
        "Team",
        options=team_ids,
        index=max(0, team_ids.index(current_team) if current_team in team_ids else 0),
        format_func=lambda tid: next(t["name"] for t in teams if t["id"] == tid),
        key="library_team_select",
    )
    st.session_state.team_id = team_id

    projects = list_projects(team_id)
    with st.expander("Projekt anlegen", expanded=not bool(projects)):
        p_name = st.text_input("Projektname", key="library_new_project_name")
        p_desc = st.text_area("Beschreibung", height=70, key="library_new_project_desc")
        if st.button("Projekt speichern", type="primary", key="library_create_project"):
            if p_name.strip():
                st.session_state.project_id = create_project(team_id, p_name, _current_user, p_desc)
                st.rerun()
            else:
                st.warning("Bitte einen Projektnamen angeben.", icon=None)

    project_options = [None] + [p["id"] for p in projects]
    current_project = st.session_state.get("project_id") if st.session_state.get("project_id") in project_options else None
    project_id = st.selectbox(
        "Aktives Projekt",
        options=project_options,
        index=project_options.index(current_project),
        format_func=lambda pid: "Kein Projekt / nur Teambibliothek" if pid is None else next(p["name"] for p in projects if p["id"] == pid),
        key="library_project_select",
    )
    st.session_state.project_id = project_id

    tab_docs, tab_log = st.tabs(["Dokumente", "Entscheidungsprotokoll"])

    with tab_docs:
        st.markdown("#### Dokument hochladen")
        st.info(
            "Bitte nur Dokumente hochladen, die frei nutzbar sind oder fuer deren Verarbeitung die erforderlichen Rechte vorliegen.",
            icon=None,
        )
        rights_ok = st.checkbox(
            "Ich bestaetige, dass ich die erforderlichen Nutzungs- und Verarbeitungsrechte fuer die hochgeladenen Dokumente habe.",
            key="library_rights_notice",
        )
        block_labels = {
            "master": "Masterplanung",
            "layout": "Gebäudeplanung",
            "process": "Prozessplanung",
        }
        planning_blocks = st.multiselect(
            "Verwendbar fuer Planungsbausteine",
            options=list(block_labels.keys()),
            default=["master"],
            format_func=block_labels.get,
            key="library_blocks",
        )
        scope = st.radio(
            "Bibliotheksebene",
            options=["team", "project"],
            horizontal=True,
            format_func={"team": "Team-Bibliothek", "project": "Projekt-Bibliothek"}.get,
            key="library_scope",
        )
        upload_disabled = (scope == "project" and project_id is None) or not rights_ok or not planning_blocks
        uploaded = st.file_uploader(
            "PDF, Markdown, Text oder DOCX",
            type=["pdf", "md", "txt", "docx"],
            accept_multiple_files=True,
            key="library_upload",
            disabled=upload_disabled,
        )
        if upload_disabled:
            st.caption("Upload aktiv, sobald Rechtehinweis, Bausteinzuordnung und ggf. Projekt gesetzt sind.")
        if uploaded and st.button("Dokumente speichern", type="primary", use_container_width=True, key="library_save_docs"):
            saved = 0
            for file in uploaded:
                doc = extract_uploaded_document(file)
                save_library_document(
                    team_id=team_id,
                    project_id=project_id if scope == "project" else None,
                    uploaded_by=_current_user,
                    title=doc.get("name") or file.name,
                    filename=file.name,
                    mime_type=doc.get("mime", ""),
                    text=doc.get("text", ""),
                    scope=scope,
                    planning_blocks=planning_blocks,
                    rights_notice=rights_ok,
                    meta={"char_count": doc.get("char_count", 0)},
                )
                saved += 1
            st.success(f"{saved} Dokument(e) gespeichert.", icon=None)
            st.rerun()

        docs = list_library_documents(team_id, project_id)
        st.markdown("#### Vorhandene Dokumente")
        if docs:
            for d in docs:
                c_info, c_meta, c_del = st.columns([4, 3, 1])
                with c_info:
                    st.markdown(f"**{d.get('title')}**")
                    st.caption(f"{d.get('filename')} · {d.get('char_count', 0)} Zeichen")
                with c_meta:
                    st.caption(
                        f"{'Projekt' if d.get('scope') == 'project' else 'Team'} · "
                        f"{', '.join(block_labels.get(b, b) for b in d.get('planning_blocks', []))} · "
                        f"{str(d.get('created_at', ''))[:16]}"
                    )
                with c_del:
                    if st.button("Löschen", key=f"library_delete_doc_{d.get('id')}", use_container_width=True):
                        if delete_library_document(int(d.get("id")), team_id=team_id, user=_current_user):
                            st.success("Dokument gelöscht.", icon=None)
                            st.rerun()
                        else:
                            st.warning("Dokument konnte nicht gelöscht werden.", icon=None)
                with st.expander("Details und Zuordnung", expanded=False):
                    current_blocks = d.get("planning_blocks", [])
                    new_blocks = st.multiselect(
                        "Planungsbausteine",
                        options=list(block_labels.keys()),
                        default=current_blocks,
                        format_func=block_labels.get,
                        key=f"library_blocks_edit_{d.get('id')}",
                    )
                    c_upd, c_status = st.columns([1, 3])
                    with c_upd:
                        if st.button("Zuordnung speichern", key=f"library_update_blocks_{d.get('id')}", use_container_width=True):
                            update_library_document_blocks(int(d.get("id")), team_id=team_id, planning_blocks=new_blocks)
                            st.success("Zuordnung gespeichert.", icon=None)
                            st.rerun()
                    with c_status:
                        st.caption(f"Status: {'analysierbar' if d.get('char_count', 0) else 'kein Text extrahiert'} · Rechtehinweis bestätigt")
                    full_doc = get_library_document(int(d.get("id")), team_id=team_id) or {}
                    preview = (full_doc.get("text") or "").strip()
                    if preview:
                        st.text_area("Textauszug", preview[:3000], height=180, disabled=True, key=f"library_preview_{d.get('id')}")
                    else:
                        st.caption("Kein Textauszug verfügbar.")
                st.divider()
        else:
            st.info("Noch keine Dokumente fuer diesen Kontext vorhanden.", icon=None)

    with tab_log:
        rows = list_decision_log(team_id, project_id, limit=200)
        st.download_button(
            "Entscheidungsprotokoll als Markdown exportieren",
            data=export_decision_log_markdown(team_id, project_id),
            file_name="entscheidungsprotokoll.md",
            mime="text/markdown",
            use_container_width=True,
            key="decision_log_download",
        )
        if rows:
            import pandas as pd
            st.dataframe(
                pd.DataFrame([{
                    "Zeit": str(r.get("created_at", ""))[:16],
                    "Baustein": r.get("planning_block"),
                    "Phase": r.get("phase"),
                    "Entscheidung": r.get("decision"),
                    "Methode": r.get("method"),
                    "Quellen": "; ".join((s.get("source_ref") or s.get("title") or "") for s in r.get("sources", [])),
                } for r in rows]),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Noch keine Entscheidungen protokolliert.", icon=None)


# ---------------------------------------------------------------------------
# SCHRITT 0 – Masterplanung
# ---------------------------------------------------------------------------

def schritt_masterplanung():
    """Sprint R: Masterplan — Gebäude-Ensemble, Erschließung, Freizonen, Flächenbilanz."""
    from app.agents.masterplan import masterplan_agent, NEBENBAU_TYPEN
    from app.tools.svg_masterplan import masterplan_to_svg
    from app.tools.site import get_demo_sites, get_demo_site

    mp_subphase = st.session_state.get("mp_subphase") or "baurecht"
    _mp_titles = {
        "baurecht": ("1.2", "Masterplanung — Baurecht", "Festlegung der planungsrechtlichen Rahmenbedingungen aus Bebauungsplan und Bauordnungsrecht."),
        "infra": ("1.3", "Masterplanung — Verkehr und Infrastruktur", "Erfassung von Straßenanschlüssen, Erschließungslogik und Medien-/Infrastrukturtrassen."),
        "anforderungen": ("1.4", "Masterplanung — Planungsanforderungen", "Definition notwendiger Gebäude, Nebenanlagen und Anforderungen an Erschließung und Versorgung."),
    }
    _phase, _title, _desc = _mp_titles.get(mp_subphase, _mp_titles["baurecht"])
    render_step_header(_phase, _title, _desc)

    demo_sites = get_demo_sites()
    site_ids = [s["id"] for s in demo_sites]
    site_names = {s["id"]: f"{s['name']} — {s['area_m2']} m²" for s in demo_sites}
    real_site = st.session_state.get("gis_site")

    _pending_traffic = st.session_state.pop("mp_traffic_apply_pending", None)
    if _pending_traffic:
        st.session_state["mp_traffic_profile"] = _pending_traffic.get("traffic_profile", st.session_state.get("mp_traffic_profile", "logistik"))
        st.session_state["mp_erschl"] = _pending_traffic.get("erschliessung_typ", st.session_state.get("mp_erschl", "u_foermig"))

    st.divider()
    col_cfg = st.container()
    col_viz = st.container()

    with col_cfg:
        site_source = st.session_state.get("mp_site_source", "Default-Grundstück")
        site = real_site if site_source == "Adresssuche / Flurstück" and real_site else get_demo_site(st.session_state.get("mp_site_id", site_ids[0]))
        st.caption(
            f"Aktuelles Grundstück: {site.get('name', site.get('id', 'Grundstück'))} · "
            f"{float(site.get('area_m2', 0)):.0f} m² · Quelle: {site_source}"
        )

        if mp_subphase == "baurecht":
            pending_legal_values = st.session_state.pop("mp_apply_legal_doc_pending", None)
            if pending_legal_values:
                for _dst, _value in pending_legal_values.get("values", {}).items():
                    st.session_state[_dst] = _value
                if pending_legal_values.get("hinweise") is not None:
                    st.session_state["mp_baurecht_hinweise"] = pending_legal_values["hinweise"]

            st.markdown("#### Bebauungsplan / Bauordnungsrecht")
            b1, b2 = st.columns(2)
            with b1:
                grz = st.number_input(
                    "GRZ",
                    min_value=0.1,
                    max_value=1.0,
                    value=float(st.session_state.get("mp_grz", 0.8)),
                    step=0.05,
                    key="mp_grz",
                    help="Grundflächenzahl aus Bebauungsplan oder BauNVO.",
                )
                gfz = st.number_input(
                    "GFZ",
                    min_value=0.1,
                    max_value=5.0,
                    value=float(st.session_state.get("mp_gfz", 2.4)),
                    step=0.1,
                    key="mp_gfz",
                    help="Geschossflächenzahl aus Bebauungsplan.",
                )
                abstandsfaktor = st.number_input(
                    "Abstandsfaktor",
                    min_value=0.0,
                    max_value=1.0,
                    value=float(st.session_state.get("mp_abstandsfaktor", 0.4)),
                    step=0.05,
                    key="mp_abstandsfaktor",
                )
            with b2:
                max_hoehe = st.number_input(
                    "Max. Gebäudehöhe [m]",
                    min_value=4.0,
                    max_value=40.0,
                    value=float(st.session_state.get("mp_max_gebaeudehoehe_m", 12.0)),
                    step=0.5,
                    key="mp_max_gebaeudehoehe_m",
                )
                regelgeschoss_hoehe = st.number_input(
                    "Regelgeschoss-Höhe [m]",
                    min_value=2.5,
                    max_value=8.0,
                    value=float(st.session_state.get("mp_regelgeschoss_hoehe_m", 3.5)),
                    step=0.1,
                    key="mp_regelgeschoss_hoehe_m",
                )
                geschosse_buero = st.number_input(
                    "Bürogeschosse",
                    min_value=1,
                    max_value=6,
                    value=int(st.session_state.get("mp_geschosse", 2)),
                    key="mp_geschosse",
                )
            st.text_area(
                "Weitere Festsetzungen / Hinweise",
                value=st.session_state.get("mp_baurecht_hinweise", ""),
                height=90,
                key="mp_baurecht_hinweise",
            )

        elif mp_subphase == "infra":
            st.markdown("#### 1.3 Verkehr und Infrastruktur")
            st.selectbox(
                "Nutzungsprofil Verkehr",
                options=["produktion", "anlieferung", "logistik", "datacenter"],
                format_func={
                    "produktion": "Produktion",
                    "anlieferung": "Anlieferung / geringer LKW-Verkehr",
                    "logistik": "Logistik / hoher Lieferverkehr",
                    "datacenter": "Datacenter / redundante Erschließung",
                }.get,
                index=["produktion", "anlieferung", "logistik", "datacenter"].index(st.session_state.get("mp_traffic_profile", "logistik")) if st.session_state.get("mp_traffic_profile", "logistik") in ["produktion", "anlieferung", "logistik", "datacenter"] else 2,
                key="mp_traffic_profile",
            )
            erschl_typ = st.radio(
                "Strategie-Wunsch",
                options=["u_foermig", "l_foermig", "gerade"],
                format_func={"u_foermig": "U-/Ringstruktur prüfen",
                              "l_foermig": "Spange / L-förmige Führung prüfen",
                              "gerade":    "Stichhof / einfache Anbindung prüfen"}.get,
                horizontal=False,
                key="mp_erschl",
                help="Der Entscheidungsbaum bewertet den Wunsch gegen Grundstücksgröße, Zuschnitt, Zufahrten und Nutzungsprofil.",
            )
            st.markdown("**Planungsanforderungen vor dem Verkehrsalgorithmus**")
            ar1, ar2, ar3 = st.columns(3)
            with ar1:
                st.slider(
                    "Anzahl Hauptgebäude / Hallen",
                    min_value=1,
                    max_value=8,
                    value=int(st.session_state.get("mp_main_building_count", 1)),
                    step=1,
                    key="mp_main_building_count",
                )
                st.number_input(
                    "Ziel-Footprint je Hauptgebäude [m²]",
                    min_value=0.0,
                    value=float(st.session_state.get("mp_main_footprint_m2", 0.0)),
                    step=250.0,
                    key="mp_main_footprint_m2",
                    help="0 = automatisch aus GRZ und Grundstücksgröße ableiten.",
                )
            with ar2:
                st.number_input(
                    "LKW-Bewegungen pro Tag",
                    min_value=0,
                    max_value=500,
                    value=int(st.session_state.get("mp_lkw_movements_per_day", 40)),
                    step=5,
                    key="mp_lkw_movements_per_day",
                )
                st.number_input(
                    "Mitarbeiter / Schicht",
                    min_value=0,
                    max_value=5000,
                    value=int(st.session_state.get("mp_employee_count", 120)),
                    step=10,
                    key="mp_employee_count",
                )
            with ar3:
                st.number_input(
                    "Besucher / Tag",
                    min_value=0,
                    max_value=1000,
                    value=int(st.session_state.get("mp_visitor_count", 20)),
                    step=5,
                    key="mp_visitor_count",
                )
                st.checkbox(
                    "Redundante Erschließung erforderlich",
                    value=bool(st.session_state.get("mp_required_redundant_access", st.session_state.get("mp_traffic_profile", "logistik") == "datacenter")),
                    key="mp_required_redundant_access",
                )
            st.number_input(
                "Ziel-Breite Hauptgebäude [m]",
                min_value=0.0,
                value=float(st.session_state.get("mp_main_width_m", 0.0)),
                step=3.0,
                key="mp_main_width_m",
                help="Optional. Zusammen mit Tiefe wird die gewünschte Gebäudeproportion priorisiert.",
            )
            st.number_input(
                "Ziel-Tiefe Hauptgebäude [m]",
                min_value=0.0,
                value=float(st.session_state.get("mp_main_depth_m", 0.0)),
                step=3.0,
                key="mp_main_depth_m",
            )
            infra_anschluesse = st.multiselect(
                "Infrastrukturtrassen / Medien",
                options=["Wasser", "Strom", "Glasfaser", "Gas", "Fernwärme", "Abwasser", "Löschwasser"],
                default=st.session_state.get("mp_infra_anschluesse", ["Wasser", "Strom", "Glasfaser", "Abwasser"]),
                key="mp_infra_anschluesse",
            )
            strassenanschluss_hinweis = st.text_area(
                "Straßenanschlüsse / Verkehrshinweise",
                value=st.session_state.get("mp_strassenanschluss_hinweis", ""),
                height=110,
                key="mp_strassenanschluss_hinweis",
            )
            with st.expander("Fitness-Kriterien des Verkehrsalgorithmus", expanded=True):
                st.caption("Die Gewichtung steuert die Variantenbewertung. 1,0 ist neutral; 0 ignoriert das Kriterium; 2,0 priorisiert es stark.")
                fw1, fw2, fw3 = st.columns(3)
                with fw1:
                    st.slider("Zielzonen verbinden", 0.0, 2.0, float(st.session_state.get("mp_fit_connectivity_weight", 1.0)), 0.1, key="mp_fit_connectivity_weight")
                    st.slider("Strategiewunsch", 0.0, 2.0, float(st.session_state.get("mp_fit_strategy_weight", 1.0)), 0.1, key="mp_fit_strategy_weight")
                with fw2:
                    st.slider("Straßenfläche minimieren", 0.0, 2.0, float(st.session_state.get("mp_fit_road_efficiency_weight", 1.0)), 0.1, key="mp_fit_road_efficiency_weight")
                    st.slider("Restflächen teilbar halten", 0.0, 2.0, float(st.session_state.get("mp_fit_parcel_split_weight", 1.0)), 0.1, key="mp_fit_parcel_split_weight")
                with fw3:
                    st.slider("Rechteckige Baufelder", 0.0, 2.0, float(st.session_state.get("mp_fit_rectangularity_weight", 1.0)), 0.1, key="mp_fit_rectangularity_weight")
                    if st.button("Fitness zurücksetzen", use_container_width=True, key="mp_fit_reset"):
                        for key in ("mp_fit_connectivity_weight", "mp_fit_strategy_weight", "mp_fit_road_efficiency_weight", "mp_fit_parcel_split_weight", "mp_fit_rectangularity_weight"):
                            st.session_state[key] = 1.0
                        st.rerun()
            if st.button("Verkehr und Trassen interaktiv planen", type="primary", use_container_width=True, key="mp_traffic_planner_open_btn"):
                st.session_state["mp_traffic_planner_open"] = True
                st.session_state["mp_dialog_traffic_profile"] = st.session_state.get("mp_traffic_profile", "logistik")
                st.session_state["mp_dialog_erschl"] = st.session_state.get("mp_erschl", "u_foermig")
                st.rerun()

        else:
            st.markdown("#### 1.4 Planungsanforderungen")
            geschosse_buero = int(st.session_state.get("mp_geschosse", 2))
            st.markdown("**Notwendige Gebäude / Nebenbauten**")
            nb_aktiv: dict[str, bool] = {}
            for nb_name, spec in NEBENBAU_TYPEN.items():
                nb_aktiv[nb_name] = st.checkbox(
                    f"{nb_name} ({spec['breite_m']:.0f}×{spec['tiefe_m']:.0f}m)",
                    value=bool(st.session_state.get(f"mp_nb_{nb_name}", spec["prio"] <= 3)),
                    key=f"mp_nb_{nb_name}",
                )
            st.markdown("**Aus 1.3 übernommene Hauptanforderungen**")
            st.caption(
                f"{int(st.session_state.get('mp_main_building_count', 1))} Hauptgebäude · "
                f"{float(st.session_state.get('mp_main_footprint_m2', 0.0)):.0f} m² Ziel-Footprint je Gebäude · "
                f"{int(st.session_state.get('mp_lkw_movements_per_day', 40))} LKW-Bewegungen/Tag · "
                f"{int(st.session_state.get('mp_employee_count', 120))} Mitarbeiter/Schicht"
            )
            st.text_area(
                "Weitere Anforderungen an Gebäude, Verkehr oder Infrastruktur",
                value=st.session_state.get("mp_planungsanforderungen_text", ""),
                height=120,
                key="mp_planungsanforderungen_text",
            )
            grz = float(st.session_state.get("mp_grz", 0.45))
            erschl_typ = st.session_state.get("mp_erschl", "u_foermig")
            infra_anschluesse = st.session_state.get("mp_infra_anschluesse", ["Wasser", "Strom", "Glasfaser", "Abwasser"])
            strassenanschluss_hinweis = st.session_state.get("mp_strassenanschluss_hinweis", "")
            st.checkbox(
                "Interaktiven Vorentwurf automatisch aktualisieren",
                value=bool(st.session_state.get("mp_interactive_preview", True)),
                key="mp_interactive_preview",
                help="Berechnet bei jeder Parameteränderung einen temporären Masterplan. Gespeichert wird erst mit Masterplan berechnen.",
            )

        if mp_subphase != "anforderungen":
            grz = float(st.session_state.get("mp_grz", 0.45))
            geschosse_buero = int(st.session_state.get("mp_geschosse", 2))
            erschl_typ = st.session_state.get("mp_erschl", "u_foermig")
            infra_anschluesse = st.session_state.get("mp_infra_anschluesse", ["Wasser", "Strom", "Glasfaser", "Abwasser"])
            strassenanschluss_hinweis = st.session_state.get("mp_strassenanschluss_hinweis", "")
            nb_aktiv = {k: bool(st.session_state.get(f"mp_nb_{k}", v["prio"] <= 3)) for k, v in NEBENBAU_TYPEN.items()}

        def _masterplan_site_from_inputs() -> dict:
            return {
                **site,
                "planning": {
                    **(site.get("planning") or {}),
                    "grz": float(st.session_state.get("mp_grz", grz)),
                    "gfz": float(st.session_state.get("mp_gfz", 2.4)),
                    "abstandsfaktor": float(st.session_state.get("mp_abstandsfaktor", 0.4)),
                    "max_gebaeudehoehe_m": float(st.session_state.get("mp_max_gebaeudehoehe_m", 12.0)),
                    "regelgeschoss_hoehe_m": float(st.session_state.get("mp_regelgeschoss_hoehe_m", 3.5)),
                },
            }

        def _masterplan_building_targets_from_inputs() -> dict:
            return {
                "main_footprint_m2": float(st.session_state.get("mp_main_footprint_m2", 0.0)),
                "main_width_m": float(st.session_state.get("mp_main_width_m", 0.0)),
                "main_depth_m": float(st.session_state.get("mp_main_depth_m", 0.0)),
                "main_building_count": int(st.session_state.get("mp_main_building_count", 1)),
                "traffic_profile": st.session_state.get("mp_traffic_profile", "logistik"),
                "lkw_movements_per_day": int(st.session_state.get("mp_lkw_movements_per_day", 40)),
                "employee_count": int(st.session_state.get("mp_employee_count", 120)),
                "visitor_count": int(st.session_state.get("mp_visitor_count", 20)),
                "required_redundant_access": bool(st.session_state.get("mp_required_redundant_access", False)),
                "traffic_fitness_weights": {
                    "connectivity": float(st.session_state.get("mp_fit_connectivity_weight", 1.0)),
                    "strategy": float(st.session_state.get("mp_fit_strategy_weight", 1.0)),
                    "road_efficiency": float(st.session_state.get("mp_fit_road_efficiency_weight", 1.0)),
                    "parcel_split": float(st.session_state.get("mp_fit_parcel_split_weight", 1.0)),
                    "rectangularity": float(st.session_state.get("mp_fit_rectangularity_weight", 1.0)),
                },
            }

        def _masterplan_briefing_from_state() -> dict | None:
            if st.session_state.get("result"):
                return st.session_state.result.get("structured_briefing")
            if st.session_state.get("user_input"):
                return st.session_state.user_input
            return None

        if mp_subphase == "anforderungen" and st.session_state.get("mp_interactive_preview", True):
            try:
                preview_result = masterplan_agent(
                    _masterplan_site_from_inputs(),
                    grz_ziel=grz,
                    nebenbauten_aktiv=nb_aktiv,
                    erschliessung_typ=erschl_typ,
                    geschosse_buero=int(geschosse_buero),
                    briefing=_masterplan_briefing_from_state(),
                    building_targets=_masterplan_building_targets_from_inputs(),
                )
                preview_mp = _apply_masterplan_variant(
                    preview_result["masterplan"],
                    preview_result["masterplan"].get("selected_masterplan_variant_id"),
                )
                st.session_state.mp_preview_masterplan = preview_mp
                st.markdown("**Interaktiver Vorentwurf**")
                p_bilanz = preview_mp.get("flaechenbilanz") or {}
                p_gebaeude = [g for g in (preview_mp.get("gebaeude") or []) if g.get("funktion") == "produktion"]
                p_parcels = preview_mp.get("building_parcels") or []
                p_erschl = preview_mp.get("erschliessung") or {}
                st.dataframe(
                    [{
                        "Hauptgebäude": len(p_gebaeude) or 1,
                        "Baufelder": len(p_parcels),
                        "GRZ": f"{float(p_bilanz.get('grz', 0)):.3f}",
                        "Erschließung": f"{float(p_erschl.get('erschliessungsflaeche_m2', 0)):.0f} m²",
                    }],
                    use_container_width=True,
                    hide_index=True,
                )
                if st.button("Interaktiven Lageplan öffnen", use_container_width=True, key="mp_preview_svg_open_btn"):
                    st.session_state["mp_preview_svg_viewer_open"] = True
                if st.session_state.get("mp_preview_svg_viewer_open"):
                    preview_svg = masterplan_to_svg(preview_mp, title="Interaktiver Masterplan-Vorentwurf")
                    _render_svg_viewer("Interaktiver Masterplan-Vorentwurf", preview_svg, key="mp_preview_svg_viewer")
            except Exception as exc:
                st.warning(f"Interaktiver Vorentwurf konnte nicht berechnet werden: {exc}", icon=None)

        def _phase_preview_masterplan() -> dict | None:
            try:
                preview_result = masterplan_agent(
                    _masterplan_site_from_inputs(),
                    grz_ziel=grz,
                    nebenbauten_aktiv=nb_aktiv,
                    erschliessung_typ=erschl_typ,
                    geschosse_buero=int(geschosse_buero),
                    briefing=_masterplan_briefing_from_state(),
                    building_targets=_masterplan_building_targets_from_inputs(),
                )
                return _apply_masterplan_variant(
                    preview_result["masterplan"],
                    preview_result["masterplan"].get("selected_masterplan_variant_id"),
                )
            except Exception:
                return None

        def _phase_limited_masterplan(source_mp: dict, subphase: str) -> dict:
            phase_mp = {**source_mp}
            if subphase == "baurecht":
                phase_mp["hauptgebaeude"] = {}
                phase_mp["gebaeude"] = []
                phase_mp["nebenbauten"] = []
                phase_mp["erschliessung"] = {}
                phase_mp["freizonen"] = []
                phase_mp["infrastruktur"] = {}
                phase_mp["zonierung"] = []
            elif subphase == "infra":
                phase_mp["hauptgebaeude"] = {}
                phase_mp["gebaeude"] = []
                phase_mp["nebenbauten"] = []
                phase_mp["freizonen"] = []
                phase_mp["zonierung"] = [
                    z for z in (source_mp.get("zonierung") or [])
                    if z.get("typ") in (
                        "zielzone_andienung",
                        "zielzone_pkw",
                        "zielzone_sicherheit",
                        "verkehr_lkw",
                        "verkehr_pkw",
                    )
                ]
            elif subphase == "anforderungen":
                phase_mp["freizonen"] = []
                phase_mp["nebenbauten"] = []
                phase_mp["zonierung"] = [
                    z for z in (source_mp.get("zonierung") or [])
                    if z.get("typ") in ("verkehr_lkw", "verkehr_pkw", "building_parcel_candidate")
                ]
            return phase_mp

        def _render_traffic_planner_dialog() -> None:
            if not st.session_state.get("mp_traffic_planner_open"):
                return
            if not hasattr(st, "dialog"):
                st.warning("Interaktive Dialoge werden von dieser Streamlit-Version nicht unterstützt.", icon=None)
                return

            @st.dialog("Verkehr und Trassen interaktiv planen", width="large")
            def _dialog():
                profile_options = ["produktion", "anlieferung", "logistik", "datacenter"]
                profile_labels = {
                    "produktion": "Produktion",
                    "anlieferung": "Anlieferung / geringer LKW-Verkehr",
                    "logistik": "Logistik / hoher Lieferverkehr",
                    "datacenter": "Datacenter / redundante Erschließung",
                }
                pref_options = ["u_foermig", "l_foermig", "gerade"]
                pref_labels = {
                    "u_foermig": "U-/Ringstruktur prüfen",
                    "l_foermig": "Spange / L-förmige Führung prüfen",
                    "gerade": "Stichhof / einfache Anbindung prüfen",
                }
                c1, c2 = st.columns(2)
                with c1:
                    profile = st.selectbox(
                        "Nutzungsprofil Verkehr",
                        options=profile_options,
                        format_func=profile_labels.get,
                        key="mp_dialog_traffic_profile",
                    )
                with c2:
                    pref = st.radio(
                        "Strategie-Wunsch",
                        options=pref_options,
                        format_func=pref_labels.get,
                        horizontal=False,
                        key="mp_dialog_erschl",
                    )
                preview_targets = {**_masterplan_building_targets_from_inputs(), "traffic_profile": profile}
                try:
                    with st.spinner("Verkehrs- und Trassenvariante wird berechnet ..."):
                        preview_result = masterplan_agent(
                            _masterplan_site_from_inputs(),
                            grz_ziel=grz,
                            nebenbauten_aktiv=nb_aktiv,
                            erschliessung_typ=pref,
                            geschosse_buero=int(geschosse_buero),
                            briefing=_masterplan_briefing_from_state(),
                            building_targets=preview_targets,
                        )
                    preview_mp = _apply_masterplan_variant(
                        preview_result["masterplan"],
                        preview_result["masterplan"].get("selected_masterplan_variant_id"),
                    )
                    phase_mp = _phase_limited_masterplan(preview_mp, "infra")
                    concept = preview_mp.get("erschliessungskonzept") or {}
                    traffic_layer = ((preview_mp.get("phasenlayer") or {}).get("1.3") or {})
                    road = (preview_mp.get("erschliessung") or {}).get("erschliessungsflaeche_m2", 0)
                    width = traffic_layer.get("road_width_m", 0)
                    opt_mode = traffic_layer.get("optimization_mode") or concept.get("optimization_mode")
                    evaluated = traffic_layer.get("optimization_evaluated_candidates") or concept.get("optimization_evaluated_candidates")
                    population = traffic_layer.get("optimization_population_size") or concept.get("optimization_population_size")
                    st.dataframe([{
                        "Strategie": concept.get("strategy_type", "-"),
                        "Score": concept.get("strategy_score", "-"),
                        "Optimierung": f"{evaluated or '-'} / {population or '-'} Kandidaten" if opt_mode else "-",
                        "Straßenbreite": f"{float(width):.1f} m",
                        "Straßenfläche": f"{float(road):.0f} m²",
                    }], use_container_width=True, hide_index=True)
                    reasons = concept.get("decision_reasons") or []
                    if reasons:
                        with st.expander("Entscheidungsgründe", expanded=False):
                            for reason in reasons[:8]:
                                st.write(f"- {reason}")
                    target_summary = traffic_layer.get("target_zone_summary") or []
                    if target_summary:
                        st.markdown("**Zielzonen vor der Verkehrsplanung**")
                        st.dataframe(target_summary, use_container_width=True, hide_index=True)
                    graph = traffic_layer.get("traffic_graph") or {}
                    if graph.get("nodes") or graph.get("edges"):
                        g1, g2, g3 = st.columns(3)
                        g1.metric("Graph-Knoten", len(graph.get("nodes") or []))
                        g2.metric("Graph-Kanten", len(graph.get("edges") or []))
                        g3.metric("Zielzonen", len(target_summary))
                    weights = traffic_layer.get("fitness_weights") or concept.get("fitness_weights") or {}
                    if weights:
                        st.markdown("**Aktive Fitness-Gewichtung**")
                        st.dataframe([{
                            "Zielzonen verbinden": weights.get("connectivity", "-"),
                            "Strategiewunsch": weights.get("strategy", "-"),
                            "Straßenfläche minimieren": weights.get("road_efficiency", "-"),
                            "Rechteckige Baufelder": weights.get("rectangularity", "-"),
                            "Restflächen teilbar": weights.get("parcel_split", "-"),
                        }], use_container_width=True, hide_index=True)
                    candidates = concept.get("candidate_strategies") or []
                    if candidates:
                        with st.expander("Bewertete Varianten-Kandidaten", expanded=False):
                            rows = []
                            for cand in candidates[:8]:
                                metrics = cand.get("metrics") or {}
                                chromo = cand.get("chromosome") or {}
                                terms = metrics.get("fitness_terms") or {}
                                rows.append({
                                    "Strategie": cand.get("strategy_type", "-"),
                                    "Score": cand.get("score", "-"),
                                    "Konnektivität": metrics.get("connectivity", "-"),
                                    "Straßenanteil": metrics.get("road_area_pct", "-"),
                                    "Restflächen": metrics.get("residual_components", "-"),
                                    "Rohscore": metrics.get("raw_score", "-"),
                                    "Straßen-Penalty": terms.get("road_efficiency_penalty", "-"),
                                    "Konnektivitäts-Penalty": terms.get("connectivity_penalty", "-"),
                                    "Rechteck-Beitrag": terms.get("rectangularity", "-"),
                                    "Andien-Lage": chromo.get("service_axis_bias", "-"),
                                    "PKW-Lage": chromo.get("parking_axis_bias", "-"),
                                    "Andien-Skalierung": chromo.get("service_scale_factor", "-"),
                                    "PKW-Skalierung": chromo.get("parking_scale_factor", "-"),
                                })
                            st.dataframe(rows, use_container_width=True, hide_index=True)
                    svg = masterplan_to_svg(phase_mp, title="Interaktive Verkehrs- und Trassenplanung")
                    st.markdown("**Lageplan-Vorschau**")
                    if "<svg" not in svg:
                        st.warning("Für diese Variante konnte kein SVG-Lageplan erzeugt werden.", icon=None)
                    else:
                        _render_svg_iframe(svg, element_id="aid_svg_viewer_mp_traffic_planner", height=740)
                except Exception as exc:
                    st.warning(f"Verkehrsvariante konnte nicht berechnet werden: {exc}", icon=None)
                b1, b2 = st.columns(2)
                with b1:
                    if st.button("Einstellungen übernehmen", type="primary", use_container_width=True, key="mp_traffic_planner_apply"):
                        st.session_state["mp_traffic_apply_pending"] = {"traffic_profile": profile, "erschliessung_typ": pref}
                        st.session_state["mp_traffic_planner_open"] = False
                        st.rerun()
                with b2:
                    if st.button("Viewer schließen", use_container_width=True, key="mp_traffic_planner_close"):
                        st.session_state["mp_traffic_planner_open"] = False
                        st.rerun()
            _dialog()

        _render_traffic_planner_dialog()

        _show_inline_calc = mp_subphase == "anforderungen"
        if _show_inline_calc and st.button("🗺 Masterplan berechnen", type="primary", use_container_width=True, key="mp_calc"):
            _mark_master_subphase_done(mp_subphase)
            # Briefing aus vorherigem Lauf übergeben (für LBO-Stellplatznachweis)
            site = _masterplan_site_from_inputs()
            result = masterplan_agent(
                site,
                grz_ziel=grz,
                nebenbauten_aktiv=nb_aktiv,
                erschliessung_typ=erschl_typ,
                geschosse_buero=int(geschosse_buero),
                briefing=_masterplan_briefing_from_state(),
                building_targets=_masterplan_building_targets_from_inputs(),
            )
            result["masterplan"]["requirements"] = {
                "baurecht": {
                    "grz_ziel": grz,
                    "gfz": float(st.session_state.get("mp_gfz", 2.4)),
                    "abstandsfaktor": float(st.session_state.get("mp_abstandsfaktor", 0.4)),
                    "max_gebaeudehoehe_m": float(st.session_state.get("mp_max_gebaeudehoehe_m", 12.0)),
                    "regelgeschoss_hoehe_m": float(st.session_state.get("mp_regelgeschoss_hoehe_m", 3.5)),
                    "buero_geschosse": int(geschosse_buero),
                    "hinweise": st.session_state.get("mp_baurecht_hinweise", ""),
                },
                "verkehr_infrastruktur": {
                    "erschliessung_typ": erschl_typ,
                    "traffic_profile": st.session_state.get("mp_traffic_profile", "logistik"),
                    "infrastrukturtrassen": infra_anschluesse,
                    "strassenanschluss_hinweis": strassenanschluss_hinweis,
                    "lkw_movements_per_day": int(st.session_state.get("mp_lkw_movements_per_day", 40)),
                    "employee_count": int(st.session_state.get("mp_employee_count", 120)),
                    "visitor_count": int(st.session_state.get("mp_visitor_count", 20)),
                    "required_redundant_access": bool(st.session_state.get("mp_required_redundant_access", False)),
                },
                "planungsanforderungen": {
                    "nebenbauten_aktiv": nb_aktiv,
                    "hauptgebaeude_ziel": {
                        "footprint_m2": float(st.session_state.get("mp_main_footprint_m2", 0.0)),
                        "breite_m": float(st.session_state.get("mp_main_width_m", 0.0)),
                        "tiefe_m": float(st.session_state.get("mp_main_depth_m", 0.0)),
                        "anzahl": int(st.session_state.get("mp_main_building_count", 1)),
                    },
                },
            }
            result["masterplan"] = _apply_masterplan_variant(
                result["masterplan"],
                result["masterplan"].get("selected_masterplan_variant_id"),
            )
            st.session_state.masterplan = result["masterplan"]
            st.session_state.building_parcels = result["masterplan"].get("building_parcels") or []
            st.session_state.selected_building_parcel_id = result["masterplan"].get("selected_building_parcel_id")
            st.session_state.building_parcel = result["masterplan"].get("building_parcel")
            st.session_state.site_geometry = st.session_state.building_parcel
            if _current_role in ("planner", "admin"):
                try:
                    from app.tools.persistence import save_planning_stand as _save_stand
                    _label = f"Masterplanung · {site.get('name', site.get('id', 'Grundstück'))}"
                    st.session_state["_last_masterplan_stand_id"] = _save_stand(
                        _current_user,
                        "masterplan",
                        _label,
                        result["masterplan"],
                        source_ref=str(site.get("id", "")),
                    )
                except Exception as _e:
                    st.caption(f"Masterplanung konnte nicht gespeichert werden: {_e}")
            try:
                from app.tools.persistence import save_decision_log as _save_decision_log
                _decision_sources = list(st.session_state.get("mp_rag_sources", []) or []) + list(result["masterplan"].get("regelquellen") or [])
                _save_decision_log(
                    team_id=st.session_state.get("team_id"),
                    project_id=st.session_state.get("project_id"),
                    user=_current_user,
                    planning_block="master",
                    phase="1.4",
                    decision="Masterplan berechnet",
                    method="deterministischer Masterplan-Algorithmus mit optionalen Bibliotheksquellen",
                    rationale="Varianten, Gebäudeparzellen, Erschließung, Infrastruktur und Flächenbilanz wurden aus Grundstück, Baurecht und Anforderungen abgeleitet.",
                    inputs=result["masterplan"].get("requirements") or {},
                    sources=_decision_sources,
                )
            except Exception as _e:
                st.caption(f"Entscheidung konnte nicht protokolliert werden: {_e}")
            st.rerun()

        st.divider()
        _mp_flow = ["baurecht", "infra", "anforderungen"]
        _mp_labels = {"baurecht": "1.2 Baurecht", "infra": "1.3 Verkehr & Infrastruktur", "anforderungen": "1.4 Planungsanforderungen"}
        _idx = _mp_flow.index(mp_subphase) if mp_subphase in _mp_flow else 0
        _bcol, _ncol = st.columns([1, 3])
        with _bcol:
            if _idx > 0 and st.button("← Zurück", use_container_width=True, key="mp_sub_back"):
                st.session_state.mp_subphase = _mp_flow[_idx - 1]
                st.rerun()
        with _ncol:
            if _idx < len(_mp_flow) - 1:
                if st.button(f"Weiter zu {_mp_labels[_mp_flow[_idx + 1]]} →", type="primary", use_container_width=True, key="mp_sub_next"):
                    _mark_master_subphase_done(mp_subphase)
                    st.session_state.mp_subphase = _mp_flow[_idx + 1]
                    st.rerun()

    # ── Ergebnisse ─────────────────────────────────────────────────────────────
    mp = st.session_state.get("masterplan")

    with col_viz:
        if mp_subphase == "baurecht":
            _render_legal_doc_panel()
            st.divider()
        if mp:
            variants = mp.get("variants") or []
            if variants:
                selected_variant_id = st.selectbox(
                    "Masterplan-Variante",
                    options=[v["id"] for v in variants],
                    index=max(0, next((i for i, v in enumerate(variants) if v.get("id") == mp.get("selected_masterplan_variant_id")), 0)),
                    format_func=lambda vid: next(
                        f"{v.get('label', vid)} · Score {v.get('score', {}).get('gesamt', '–')}"
                        for v in variants if v.get("id") == vid
                    ),
                    key="mp_variant_select",
                )
                if selected_variant_id != mp.get("selected_masterplan_variant_id"):
                    st.session_state.masterplan = _apply_masterplan_variant(mp, selected_variant_id)
                    st.session_state.building_parcels = st.session_state.masterplan.get("building_parcels") or []
                    st.session_state.selected_building_parcel_id = st.session_state.masterplan.get("selected_building_parcel_id")
                    st.session_state.building_parcel = st.session_state.masterplan.get("building_parcel")
                    st.session_state.site_geometry = st.session_state.building_parcel
                    st.rerun()

                sc1, sc2, sc3, sc4 = st.columns(4)
                score = mp.get("score") or {}
                infra = mp.get("infrastruktur") or {}
                sc1.metric("Masterplan-Score", f"{score.get('gesamt', 0):.1f}")
                sc2.metric("GRZ-Qualität", f"{score.get('grz_qualitaet', 0):.0f}%")
                sc3.metric("Versiegelung", f"{score.get('versiegelung', 0):.0f}%")
                sc4.metric("Trassen", f"{infra.get('trassenlaenge_m', 0):.0f} m")

            tab_plan, tab_bilanz, tab_varianten = st.tabs(["🗺 Lageplan", "📊 Flächenbilanz", "🔀 Varianten"])

            with tab_plan:
                svg = masterplan_to_svg(mp, title="Masterplan Lageplan")
                if st.button("Lageplan im SVG-Viewer öffnen", type="primary", use_container_width=True, key="mp_svg_open_btn"):
                    st.session_state["mp_svg_viewer_open"] = True
                st.caption("Der Lageplan wird als skalierbare SVG-Zeichnung im Viewer geöffnet. Im Arbeitsbereich bleibt die Phase text- und parameterorientiert.")
                if st.session_state.get("mp_svg_viewer_open"):
                    _render_svg_viewer("Masterplan Lageplan", svg, key="mp_svg_viewer")

            with tab_bilanz:
                b = mp.get("flaechenbilanz") or {}
                grz_val = b.get("grz", 0)
                grz_lim = b.get("grz_grenzwert", 0.60)
                vs_val  = b.get("versiegelungsgrad", 0)

                km1, km2, km3, km4 = st.columns(4)
                km1.metric(
                    "GRZ",
                    f"{grz_val:.3f}",
                    delta=f"Grenzwert {grz_lim:.2f}",
                    delta_color="inverse" if grz_val > grz_lim else "normal",
                )
                km2.metric("GFZ", f"{b.get('gfz', 0):.3f}")
                km3.metric("Versiegelungsgrad", f"{vs_val:.0%}")
                sp_ist  = b.get("stellplaetze_anzahl", 0)
                sp_soll = b.get("stellplaetze_soll", 0)
                sp_deck = b.get("stellplaetze_deckung_pct", 100)
                sp_label = f"{sp_ist} / {sp_soll} SP" if sp_soll else f"{sp_ist} SP"
                km4.metric(
                    "Stellplätze (Ist/Soll)",
                    sp_label,
                    delta=f"{sp_deck}% Deckung" if sp_soll else None,
                    delta_color="inverse" if sp_ist < sp_soll else "normal",
                )

                st.markdown("**Flächenaufteilung**")
                import pandas as pd
                gst = b.get("grundstueck_m2", 1) or 1
                rows = [
                    {"Bereich": "Produktionshalle",  "Fläche [m²]": b.get("hauptgebaeude_m2", 0), "Anteil": f"{b.get('hauptgebaeude_m2', 0)/gst:.1%}"},
                    {"Bereich": "Nebenbauten",        "Fläche [m²]": b.get("nebenbauten_m2", 0),   "Anteil": f"{b.get('nebenbauten_m2', 0)/gst:.1%}"},
                    {"Bereich": "Erschließung (LKW)", "Fläche [m²]": b.get("erschliessung_m2", 0), "Anteil": f"{b.get('erschliessung_m2', 0)/gst:.1%}"},
                    {"Bereich": "Rangierzone",        "Fläche [m²]": b.get("rangierzone_m2", 0),   "Anteil": f"{b.get('rangierzone_m2', 0)/gst:.1%}"},
                    {"Bereich": "Stellplätze PKW",    "Fläche [m²]": b.get("stellplatz_m2", 0),    "Anteil": f"{b.get('stellplatz_m2', 0)/gst:.1%}"},
                    {"Bereich": "Grünflächen",        "Fläche [m²]": b.get("gruenflaeche_m2", 0),  "Anteil": f"{b.get('gruenflaeche_m2', 0)/gst:.1%}"},
                    {"Bereich": "Grundstück gesamt",  "Fläche [m²]": b.get("grundstueck_m2", 0),   "Anteil": "100%"},
                ]
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

                # Stellplatz-Nachweis nach LBO
                if sp_soll:
                    aufschl = b.get("stellplaetze_aufschluessel") or {}
                    with st.expander("📋 Stellplatz-Nachweis (LBO)", expanded=False):
                        st.markdown(
                            f"| Bereich | Schlüssel | Soll SP |\n"
                            f"|---------|-----------|--------|\n"
                            f"| Produktion | 1 SP / 100 m² | {aufschl.get('produktion', 0)} |\n"
                            f"| Lager | 1 SP / 200 m² | {aufschl.get('lager', 0)} |\n"
                            f"| Büro | 1 SP / 30 m² | {aufschl.get('buero', 0)} |\n"
                            f"| **Gesamt** | | **{sp_soll}** |\n"
                            f"| Nachgewiesen | | {sp_ist} |"
                        )
                        if sp_ist < sp_soll:
                            st.warning(f"⚠ Stellplatz-Defizit: {sp_soll - sp_ist} SP fehlen (LBO-Nachweis).", icon=None)
                        else:
                            st.success(f"✅ Stellplatz-Nachweis erfüllt ({sp_ist}/{sp_soll} SP).", icon=None)

                # GRZ-Compliance
                if grz_val > grz_lim:
                    st.warning(
                        f"⚠ GRZ {grz_val:.3f} überschreitet den Grenzwert {grz_lim:.2f} (§ 17 BauNVO GI). "
                        "GRZ-Ziel verringern oder Gebäudefläche reduzieren.",
                        icon=None,
                    )
                else:
                    st.success(f"✅ GRZ {grz_val:.3f} ≤ {grz_lim:.2f} — BauNVO-konform.", icon=None)

                st.caption("✅ Deterministischer Modus — regelbasierter Algorithmus, kein LLM.")

                parcels = mp.get("building_parcels") or []
                if parcels:
                    st.markdown("**Gebäudeparzelle für Layoutplanung**")
                    selected_pid = st.selectbox(
                        "Parzelle wählen",
                        options=[p["id"] for p in parcels],
                        index=max(0, next((i for i, p in enumerate(parcels) if p["id"] == st.session_state.get("selected_building_parcel_id")), 0)),
                        format_func=lambda pid: next(
                            f"{p['id']} · {p.get('name', '')} · {p.get('width_m', 0):.0f} x {p.get('depth_m', 0):.0f} m"
                            for p in parcels if p["id"] == pid
                        ),
                        key="mp_selected_building_parcel_id",
                    )
                    selected_parcel = next((p for p in parcels if p["id"] == selected_pid), parcels[0])
                    st.session_state.selected_building_parcel_id = selected_pid
                    st.session_state.building_parcel = selected_parcel
                    st.session_state.site_geometry = selected_parcel

            with tab_varianten:
                variants = mp.get("variants") or []
                if variants:
                    import pandas as pd
                    st.dataframe(
                        pd.DataFrame([{
                            "Variante": v.get("label"),
                            "Fokus": v.get("focus"),
                            "Score": v.get("score", {}).get("gesamt"),
                            "GRZ": v.get("flaechenbilanz", {}).get("grz"),
                            "Versiegelung": v.get("flaechenbilanz", {}).get("versiegelungsgrad"),
                            "Stellplätze": f"{v.get('flaechenbilanz', {}).get('stellplaetze_anzahl', 0)} / {v.get('flaechenbilanz', {}).get('stellplaetze_soll', 0)}",
                            "Gebäudeparzelle": (v.get("building_parcel") or {}).get("id", ""),
                            "Parzellengröße": f"{(v.get('building_parcel') or {}).get('width_m', 0):.0f} x {(v.get('building_parcel') or {}).get('depth_m', 0):.0f} m",
                        } for v in variants]),
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.info("Noch keine Varianten berechnet.", icon=None)
        else:
            preview_mp = _phase_preview_masterplan()
            if preview_mp:
                phase_titles = {
                    "baurecht": "Zwischenstand 1.2 Baurecht",
                    "infra": "Zwischenstand 1.3 Verkehr und Infrastruktur",
                    "anforderungen": "Zwischenstand 1.4 Parzellierung",
                }
                preview_title = phase_titles.get(mp_subphase, "Zwischenstand Masterplanung")
                st.markdown(f"**{preview_title}**")
                phase_mp = _phase_limited_masterplan(preview_mp, mp_subphase)
                layer = (phase_mp.get("phasenlayer") or {}).get("1.2" if mp_subphase == "baurecht" else "1.3" if mp_subphase == "infra" else "1.4") or {}
                rule_refs = layer.get("rule_refs") or []
                if rule_refs:
                    src_preview = "; ".join(f"{r.get('title')} ({r.get('source_ref')})" for r in rule_refs[:3])
                    st.caption(f"Quellen: {src_preview}")
                    with st.expander("Regelquellen anzeigen", expanded=False):
                        st.dataframe(rule_refs, use_container_width=True, hide_index=True)
                if mp_subphase == "baurecht":
                    st.caption("Darstellung von Grundstück, Baugrenze, Baulinie und Höhenzone als aktueller Arbeitsstand.")
                elif mp_subphase == "infra":
                    road = (preview_mp.get("erschliessung") or {}).get("erschliessungsflaeche_m2", 0)
                    nodes = len(((preview_mp.get("infrastruktur") or {}).get("knoten") or []))
                    concept = preview_mp.get("erschliessungskonzept") or {}
                    strategy = concept.get("strategy_type") or "–"
                    score = concept.get("strategy_score")
                    target_count = len(layer.get("target_zone_summary") or [])
                    graph_edges = len((layer.get("traffic_graph") or {}).get("edges") or [])
                    st.caption(f"Strategie: {strategy} · Score: {score if score is not None else '–'} · Straßenkorridor: {float(road):.0f} m² · Zielzonen: {target_count} · Graph-Kanten: {graph_edges} · Knoten: {nodes}")
                    target_summary = layer.get("target_zone_summary") or []
                    if target_summary:
                        st.dataframe(target_summary, use_container_width=True, hide_index=True)
                    reasons = concept.get("decision_reasons") or []
                    if reasons:
                        with st.expander("Entscheidungsgründe", expanded=False):
                            for reason in reasons[:6]:
                                st.write(f"- {reason}")
                    candidates = concept.get("candidate_strategies") or []
                    if candidates:
                        rows = []
                        for cand in candidates[:5]:
                            metrics = cand.get("metrics") or {}
                            chromo = cand.get("chromosome") or {}
                            rows.append({
                                "Strategie": cand.get("strategy_type", "-"),
                                "Score": cand.get("score", "-"),
                                "Konnektivität": metrics.get("connectivity", "-"),
                                "Straßenanteil": metrics.get("road_area_pct", "-"),
                                "Andien-Lage": chromo.get("service_axis_bias", "-"),
                                "PKW-Lage": chromo.get("parking_axis_bias", "-"),
                            })
                        st.dataframe(rows, use_container_width=True, hide_index=True)
                else:
                    parcels = (layer.get("building_parcels") or preview_mp.get("building_parcels") or [])
                    st.caption(f"Darstellung der Restflächen-Parzellierung. Parzellen: {len(parcels)}")
                open_key = f"mp_phase_preview_{mp_subphase}_open"
                if st.button("Zwischenstand im SVG-Viewer öffnen", type="primary", use_container_width=True, key=f"{open_key}_btn"):
                    st.session_state[open_key] = True
                if st.session_state.get(open_key):
                    svg = masterplan_to_svg(phase_mp, title=preview_title)
                    _render_svg_viewer(preview_title, svg, key=f"mp_phase_preview_{mp_subphase}")
            else:
                st.caption("Zwischenstand kann erst angezeigt werden, sobald ein Grundstück ausgewählt ist.")

    # ── Navigation ─────────────────────────────────────────────────────────────
    if mp_subphase == "anforderungen":
        st.divider()
        _nav1, _nav2 = st.columns([1, 2])
        with _nav1:
            if st.button("Ohne Masterplan weiter →", use_container_width=True, key="mp_skip"):
                st.session_state.schritt = 2
                st.rerun()
        with _nav2:
            if mp:
                if st.button("Weiter zur Layoutplanung →", type="primary",
                             use_container_width=True, key="mp_next"):
                    parcels = mp.get("building_parcels") or []
                    selected_pid = st.session_state.get("selected_building_parcel_id")
                    selected_parcel = next((p for p in parcels if p["id"] == selected_pid), None)
                    selected_parcel = selected_parcel or mp.get("building_parcel")
                    st.session_state.building_parcels = parcels
                    st.session_state.building_parcel = selected_parcel
                    st.session_state.site_geometry = selected_parcel
                    st.session_state.schritt = 20
                    st.rerun()
            else:
                st.caption("Erst Masterplan berechnen, dann weiter.")


# ---------------------------------------------------------------------------
# SCHRITT 1 – Grundstück
# ---------------------------------------------------------------------------

def schritt_grundstueck():
    st.markdown('<span class="phase-badge">1.1</span> **Masterplanung — Grundstück / Kataster**', unsafe_allow_html=True)
    st.caption("Alternativ zu den Default-Grundstücken kann hier ein reales Flurstück gesucht oder gezeichnet werden.")

    if st.button("← Zurück zur Masterplanung", use_container_width=False, key="gis_back_master"):
        st.session_state.schritt = 0
        st.rerun()

    tab_demo, tab_adresse = st.tabs(["Demo-Grundstücke", "Adresssuche (Beta)"])

    with tab_demo:
        st.caption("Wähle eines von drei reproduzierbar generierten Grundstücken in unterschiedlichen Größen.")

        sites = get_demo_sites()
        selected_id = st.radio(
            "Grundstück",
            options=[site["id"] for site in sites],
            format_func=lambda site_id: next(site["name"] for site in sites if site["id"] == site_id),
            horizontal=True,
            label_visibility="collapsed",
        )
        selected_site = next(site for site in sites if site["id"] == selected_id)

        demo_align_angle = _alignment_ui(selected_site, key_prefix="demo")

        from app.tools.svg_masterplan import site_to_svg

        cols = st.columns(3)
        for col, site in zip(cols, sites):
            with col:
                st.markdown(f"**{site['name']}**")
                st.caption(site["beschreibung"])
                if st.button("Grundstücksskizze öffnen", key=f"site_svg_open_{site['id']}", use_container_width=True):
                    st.session_state[f"site_svg_open_{site['id']}"] = True
                if st.session_state.get(f"site_svg_open_{site['id']}"):
                    _render_svg_viewer(site["name"], site_to_svg(site, title=site["name"]), key=f"site_svg_{site['id']}")
                st.metric("Fläche", f"{site['area_m2']:,} m²".replace(",", "."))
                st.caption(
                    f"{site['width_m']:.0f} × {site['depth_m']:.0f} m · "
                    f"{len(site['access_points'])} Zufahrt(en) · Seed {site['seed']}"
                )

        st.markdown("---")
        try:
            from app.agents.masterplan import _analyze_site_for_masterplanning, _polygon_from_site, _site_geometry_metrics
            _poly = _polygon_from_site(selected_site)
            _analysis = _analyze_site_for_masterplanning(
                selected_site,
                selected_site.get("access_points") or [],
                float(selected_site.get("width_m", 0)),
                float(selected_site.get("depth_m", 0)),
                float(selected_site.get("area_m2", 0)),
            )
            if _poly is not None:
                _analysis = _site_geometry_metrics(selected_site, _poly, _analysis)
            st.markdown("**Grundstückskennzahlen**")
            km1, km2, km3, km4 = st.columns(4)
            km1.metric("Fläche", f"{float(selected_site.get('area_m2', 0)):.0f} m²")
            km2.metric("Umfang", f"{float(_analysis.get('perimeter_m', 0)):.0f} m")
            km3.metric("Kompaktheit", f"{float(_analysis.get('compactness', 0)):.2f}")
            km4.metric("Schlankheit", f"{float(_analysis.get('aspect_ratio', 0)):.2f}")
            km5, km6, km7, km8 = st.columns(4)
            km5.metric("Konkavität", f"{float(_analysis.get('concavity_pct', 0)):.1f}%")
            km6.metric("Zufahrten", str(int(_analysis.get('access_count', 0))))
            km7.metric("Hauptachse", str(_analysis.get('long_axis', '–')).upper())
            km8.metric("Topographie", "offen")
            st.caption("Topographie ist als spätere Ebene vorbereitet; aktuell sind noch keine DGM/DEM-Höhendaten angebunden.")
        except Exception as _e:
            st.caption(f"Grundstückskennzahlen konnten nicht berechnet werden: {_e}")

        if st.button("Grundstück in Masterplanung übernehmen →", type="primary", use_container_width=True):
            site_to_save = {**selected_site}
            if demo_align_angle is not None:
                site_to_save["alignment_angle_deg"] = demo_align_angle
            st.session_state.site_geometry = site_to_save
            st.session_state.gis_site = site_to_save
            st.session_state.mp_site_source = "Default-Grundstück"
            st.session_state.mp_site_id = selected_id
            st.session_state.masterplan = None
            st.session_state.building_parcels = []
            st.session_state.selected_building_parcel_id = None
            st.session_state.building_parcel = None
            _mark_master_subphase_done("kataster")
            st.session_state.schritt = 0
            st.rerun()

    with tab_adresse:
        st.caption("Klicke auf die Karte oder suche eine Adresse, um Grundstücke zu laden.")

        # ── Session-State initialisieren ──────────────────────────────────────
        for _k, _v in [
            ("gis_center", [51.0, 10.0]),
            ("gis_zoom", 6),
            ("gis_candidates", []),
            ("gis_selected", 0),
            ("gis_map_click", None),
            ("gis_wgs84_cache", {}),
            ("gis_drawing_count", 0),
        ]:
            if _k not in st.session_state:
                st.session_state[_k] = _v

        # ── Adress-Suche zum Zentrieren ───────────────────────────────────────
        st.info(
            "**ALKIS-Flurstücksdaten (amtliche Geometrien)** stehen aktuell für "
            "**Nordrhein-Westfalen** zur Verfügung. "
            "Für andere Bundesländer wird automatisch auf OSM-Daten zurückgegriffen.",
            icon="ℹ️",
        )

        col_adr, col_btn = st.columns([4, 1])
        with col_adr:
            address = st.text_input(
                "Adresse / Standort",
                placeholder="z.B. Duisburger Straße 100, Düsseldorf oder Industriepark Essen",
                key="gis_address_input",
                label_visibility="collapsed",
            )
        with col_btn:
            search_btn = st.button("Suchen", type="primary", key="gis_search_btn")

        if search_btn and address:
            with st.spinner("Geocoding…"):
                try:
                    from app.tools.gis import geocode_address, fetch_all_parcels_alkis
                    coords = geocode_address(address)
                except ImportError:
                    coords = None
                    st.warning("GIS-Modul nicht verfügbar (pyproj / requests fehlen).")
            if coords:
                lat, lon = coords
                st.session_state.gis_center = [lat, lon]
                st.session_state.gis_zoom = 15
                with st.spinner("Grundstücke laden (ALKIS NRW)…"):
                    parcels = fetch_all_parcels_alkis(lat, lon, radius_m=250, bundesland="NW")
                st.session_state.gis_candidates = parcels
                st.session_state.gis_selected = 0
                st.rerun()
            else:
                st.error("Adresse konnte nicht gefunden werden.")

        candidates = st.session_state.gis_candidates
        map_col, list_col = st.columns([1.05, 0.95], gap="large")

        for _k, _v in [("gis_last_tooltip", None)]:
            if _k not in st.session_state:
                st.session_state[_k] = _v

        with map_col:
            st.markdown("**Karte**")
            try:
                import folium
                from streamlit_folium import st_folium

                m = folium.Map(
                    location=st.session_state.gis_center,
                    zoom_start=st.session_state.gis_zoom,
                    tiles="CartoDB Positron",
                )

                # NRW ALKIS WMS — vollständiger Flurstück-Teppich als Hintergrund
                folium.WmsTileLayer(
                    url="https://www.wms.nrw.de/geobasis/wms_nw_alkis",
                    name="Flurstücke (ALKIS NRW)",
                    layers="adv_alkis_flurstuecke",
                    fmt="image/png",
                    transparent=True,
                    version="1.3.0",
                    attr="© Geobasis NRW / dl-de/by-2-0",
                    overlay=True,
                    control=False,
                    show=True,
                    opacity=0.6,
                ).add_to(m)

                # Alle Kandidaten auf der Karte anzeigen — ausgewählt blau, andere grau
                all_bounds: list[list[float]] = []
                for i, cand in enumerate(candidates):
                    wgs84 = cand.get("polygon_wgs84", [])  # [[lat, lon], ...]
                    if not wgs84:
                        continue
                    is_sel = (i == min(st.session_state.gis_selected, len(candidates) - 1))
                    folium.Polygon(
                        locations=wgs84,
                        color="#1A73E8" if is_sel else "#888888",
                        fill=True,
                        fill_opacity=0.28 if is_sel else 0.10,
                        weight=3 if is_sel else 1.2,
                        tooltip=folium.Tooltip(
                            f"__idx_{i}__ {cand.get('name', 'Grundstück')} – "
                            f"{cand.get('area_m2', 0):.0f} m²"
                        ),
                    ).add_to(m)
                    all_bounds.extend(wgs84)

                if all_bounds:
                    lats_b = [c[0] for c in all_bounds]
                    lons_b = [c[1] for c in all_bounds]
                    m.fit_bounds([[min(lats_b), min(lons_b)], [max(lats_b), max(lons_b)]])

                # Draw-Tool: Rechteck + Polygon zeichnen
                from folium.plugins import Draw
                Draw(
                    draw_options={
                        "polyline": False,
                        "polygon": True,
                        "rectangle": True,
                        "circle": False,
                        "marker": False,
                        "circlemarker": False,
                    },
                    edit_options={"edit": False, "remove": True},
                ).add_to(m)

                map_result = st_folium(
                    m,
                    width="100%",
                    height=560,
                    returned_objects=["all_drawings", "last_object_clicked_tooltip", "last_clicked"],
                    key="gis_folium_map",
                )

                # ── Gezeichnete Polygone → Kandidat hinzufügen ──────────────────
                drawings_raw = (map_result or {}).get("all_drawings")
                drawn_features: list[dict] = []
                if isinstance(drawings_raw, list):
                    drawn_features = drawings_raw
                elif isinstance(drawings_raw, dict):
                    drawn_features = drawings_raw.get("features", [])

                current_drawing_count = len(drawn_features)
                if current_drawing_count > st.session_state.gis_drawing_count:
                    st.session_state.gis_drawing_count = current_drawing_count
                    latest = drawn_features[-1]
                    from app.tools.gis import drawn_feature_to_site as _drawn_feature_to_site
                    drawn_site = _drawn_feature_to_site(latest)
                    if drawn_site:
                        # Bestehende drawn-Einträge ersetzen, OSM-Kandidaten behalten
                        filtered = [c for c in st.session_state.gis_candidates
                                    if not str(c.get("id", "")).startswith("drawn_")]
                        filtered.append(drawn_site)
                        st.session_state.gis_candidates = filtered
                        st.session_state.gis_selected = len(filtered) - 1
                        st.rerun()

                # ── Klick auf eine OSM-Parzelle → Auswahl ändern ────────────────
                tooltip_val = str((map_result or {}).get("last_object_clicked_tooltip") or "")
                if "__idx_" in tooltip_val and tooltip_val != st.session_state.gis_last_tooltip:
                    st.session_state.gis_last_tooltip = tooltip_val
                    try:
                        raw = tooltip_val.split("__idx_")[1].split("__")[0].strip()
                        new_idx = int(raw.split()[0])
                        if 0 <= new_idx < len(candidates) and new_idx != st.session_state.gis_selected:
                            st.session_state.gis_selected = new_idx
                            st.rerun()
                    except (ValueError, IndexError):
                        pass

                # ── Klick auf Kartenfläche (nicht auf geladenes WFS-Polygon) → ALKIS laden
                click = (map_result or {}).get("last_clicked")
                _tooltip_is_idx = "__idx_" in tooltip_val and bool(tooltip_val)
                if click and click != st.session_state.gis_map_click and not _tooltip_is_idx:
                    st.session_state.gis_map_click = click
                    click_lat, click_lon = click["lat"], click["lng"]
                    st.session_state.gis_center = [click_lat, click_lon]
                    load_r = 200
                    with st.spinner("Grundstücke an Klick-Position laden (ALKIS NRW)…"):
                        try:
                            from app.tools.gis import fetch_all_parcels_alkis
                            parcels = fetch_all_parcels_alkis(
                                click_lat, click_lon, radius_m=load_r, bundesland="NW"
                            )
                        except ImportError:
                            parcels = []
                    if parcels:
                        st.session_state.gis_candidates = parcels
                        st.session_state.gis_selected = 0
                        if not candidates:
                            st.session_state.gis_zoom = 15
                    st.rerun()

                if not candidates:
                    st.caption("Adresse suchen · auf die Karte klicken · oder Grundstück einzeichnen (Rechteck/Polygon-Tool).")

            except ImportError:
                st.info("Folium nicht installiert. Bitte `pip install streamlit-folium` ausführen.")
                st.caption("Fallback: Adresssuche ohne interaktive Karte.")

        with list_col:
            if candidates:
                st.markdown("**Gefundene Grundstücke**")
                st.caption(f"{len(candidates)} Flurstücke · Karte anklicken für mehr")
                new_sel = st.selectbox(
                    "Parzelle auswählen:",
                    options=list(range(len(candidates))),
                    format_func=lambda i: (
                        f"{candidates[i].get('name', 'Grundstück')}  —  "
                        f"{candidates[i].get('area_m2', 0):.0f} m²"
                    ),
                    index=min(st.session_state.gis_selected, len(candidates) - 1),
                    key="gis_selectbox",
                    label_visibility="collapsed",
                )
                if new_sel != st.session_state.gis_selected:
                    st.session_state.gis_selected = new_sel
                    st.rerun()

                selected_parcel = candidates[st.session_state.gis_selected]

                # Kompakte Kennzahlen-Karte
                _src = selected_parcel.get("source", "osm")
                _src_info = {
                    "alkis": ("🟢", "ALKIS (amtlich)"),
                    "drawn": ("✏️", "Manuell"),
                }.get(_src, ("🟡", "OSM (Fallback)"))
                mc1, mc2, mc3 = st.columns(3)
                mc1.metric("Fläche", f"{selected_parcel.get('area_m2', 0):.0f} m²")
                mc2.metric("Breite", f"{selected_parcel.get('width_m', 0):.0f} m")
                mc3.metric("Tiefe", f"{selected_parcel.get('depth_m', 0):.0f} m")
                st.caption(f"{_src_info[0]} {_src_info[1]}")

                gis_align_angle = _alignment_ui(selected_parcel, key_prefix="gis")

                st.markdown("---")
                if st.button(
                    "✓ Dieses Grundstück verwenden →",
                    type="primary",
                    key="gis_use_btn",
                    use_container_width=True,
                ):
                    parcel_to_save = {**selected_parcel}
                    if gis_align_angle is not None:
                        parcel_to_save["alignment_angle_deg"] = gis_align_angle
                    st.session_state.site_geometry = parcel_to_save
                    st.session_state.gis_site = parcel_to_save
                    st.session_state.mp_site_source = "Adresssuche / Flurstück"
                    st.session_state.masterplan = None
                    st.session_state.building_parcels = []
                    st.session_state.selected_building_parcel_id = None
                    st.session_state.building_parcel = None
                    _mark_master_subphase_done("kataster")
                    st.session_state.schritt = 0
                    st.rerun()
            else:
                st.markdown("**Gefundene Grundstücke**")
                st.info("Klicke auf die Karte oder suche eine Adresse, um Grundstücke zu finden.")






# ---------------------------------------------------------------------------
# BAUSTEIN 2.0 – Gebäudeplanung: Parzelle aus Masterplanung wählen
# ---------------------------------------------------------------------------

def schritt_gebaeudeplanung_start():
    st.markdown('<span class="phase-badge">2.0</span> **Gebäudeplanung — Parzelle wählen**', unsafe_allow_html=True)
    st.caption("Auswahl der zu planenden Gebäudeparzelle aus gespeicherten Masterplanungen.")

    from app.tools.persistence import get_planning_stand, list_planning_stands

    stands = list_planning_stands(_current_user, "masterplan", limit=50)
    current_mp = st.session_state.get("masterplan")

    if not stands and not current_mp:
        st.info("Noch keine gespeicherte Masterplanung vorhanden. Starte zuerst Baustein 1.", icon=None)
        if st.button("Zur Masterplanung", type="primary"):
            st.session_state.schritt = 0
            st.rerun()
        return

    source_options = []
    if current_mp:
        source_options.append("Aktuelle Masterplanung")
    source_options.extend([str(s["id"]) for s in stands])

    selected_source = st.selectbox(
        "Masterplanung",
        options=source_options,
        format_func=lambda v: "Aktuelle Masterplanung" if v == "Aktuelle Masterplanung" else next(
            f"#{s['id']} · {s['label']}" for s in stands if str(s["id"]) == v
        ),
        key="bp_masterplan_source",
    )

    if selected_source == "Aktuelle Masterplanung":
        mp = current_mp
        masterplan_stand_id = st.session_state.get("_last_masterplan_stand_id")
    else:
        loaded = get_planning_stand(int(selected_source))
        mp = (loaded or {}).get("payload") or {}
        masterplan_stand_id = int(selected_source)

    parcels = mp.get("building_parcels") or []
    if not parcels:
        st.warning("Diese Masterplanung enthält keine Gebäudeparzellen.", icon=None)
        return

    selected_pid = st.selectbox(
        "Gebäudeparzelle",
        options=[p["id"] for p in parcels],
        format_func=lambda pid: next(
            f"{p['id']} · {p.get('name', '')} · {p.get('width_m', 0):.0f} x {p.get('depth_m', 0):.0f} m"
            for p in parcels if p["id"] == pid
        ),
        key="bp_selected_parcel_id",
    )
    selected_parcel = next((p for p in parcels if p["id"] == selected_pid), parcels[0])

    c1, c2, c3 = st.columns(3)
    c1.metric("Parzellen-ID", selected_parcel.get("id", "-"))
    c2.metric("Fläche", f"{selected_parcel.get('area_m2', 0):.0f} m²")
    c3.metric("Abmessungen", f"{selected_parcel.get('width_m', 0):.0f} x {selected_parcel.get('depth_m', 0):.0f} m")

    if st.button("Parzelle übernehmen und Gebäude planen →", type="primary", use_container_width=True):
        st.session_state.masterplan = mp
        st.session_state.building_parcels = parcels
        st.session_state.selected_building_parcel_id = selected_pid
        st.session_state.building_parcel = selected_parcel
        st.session_state.site_geometry = selected_parcel
        st.session_state["_last_masterplan_stand_id"] = masterplan_stand_id
        st.session_state.schritt = 2
        st.rerun()

# ---------------------------------------------------------------------------
# SCHRITT 2 – Eingabe
# ---------------------------------------------------------------------------

def schritt_eingabe():
    st.markdown('<span class="phase-badge">2.1</span> **Gebäudeplanung — Nutzung & Flächenprogramm**', unsafe_allow_html=True)
    st.caption("Wähle den Nutzungstyp und gib die Flächenangaben gemäß DIN 277 ein.")

    typ = st.radio(
        "Nutzungstyp",
        options=["Produktion", "Logistik", "Data Center"],
        horizontal=True,
        label_visibility="collapsed",
    )

    st.markdown("---")

    # --- Gemeinsame Felder ---
    col1, col2 = st.columns(2)
    with col1:
        buero = st.number_input("Büro / Verwaltung (NUF 2) m²", min_value=50, max_value=5000,
                                value=250, step=50)
        buero_geschosse = st.number_input("Büro / Verwaltung Geschosse", min_value=1, max_value=6,
                                          value=2, step=1)
    with col2:
        sonder = st.text_area("Besondere Anforderungen (optional)",
                              placeholder="z. B. Erweiterung nach Osten, akustische Trennung…",
                              height=80)

    st.markdown("---")

    # --- Typspezifische Felder ---
    user_input = {
        "buero_nuf2": float(buero),
        "buero_geschosse": int(buero_geschosse),
        "sonderbedingungen": sonder or None,
    }
    _mep_defaults = {
        "Produktion":   {"lueftung": "mechanisch", "sprinkler": True,  "druckluft": True,  "kaelte": False, "usv": False, "it": "basis"},
        "Logistik":     {"lueftung": "mechanisch", "sprinkler": True,  "druckluft": False, "kaelte": False, "usv": False, "it": "basis"},
        "Data Center":  {"lueftung": "klima",      "sprinkler": False, "druckluft": False, "kaelte": True,  "usv": True,  "it": "rechenzentrum"},
    }
    _def = _mep_defaults.get(typ, _mep_defaults["Produktion"])

    if typ == "Produktion":
        user_input["nutzungstyp"] = Nutzungstyp.PRODUKTION
        c1, c2, c3 = st.columns(3)
        with c1:
            user_input["produktionsflaeche"] = float(
                st.number_input("Produktion (NUF 3) m²", 500, 20000, 1200, 100))
            user_input["lager_rohstoffe"] = float(
                st.number_input("Lager Rohstoffe (NUF 4) m²", 200, 5000, 400, 50))
        with c2:
            user_input["lager_fertigwaren"] = float(
                st.number_input("Lager Fertigwaren (NUF 4) m²", 200, 5000, 400, 50))
            user_input["wareneingang"] = float(
                st.number_input("Wareneingang (NUF 4) m²", 100, 2000, 200, 50))
        with c3:
            user_input["versand"] = float(
                st.number_input("Versand (NUF 4) m²", 100, 2000, 200, 50))
            user_input["qualitaetssicherung"] = float(
                st.number_input("Qualitätssicherung (NUF 3) m²", 50, 1000, 150, 25))
        user_input["kranbahn_erforderlich"] = st.checkbox("Kranbahn erforderlich")

    elif typ == "Logistik":
        user_input["nutzungstyp"] = Nutzungstyp.LOGISTIK
        c1, c2, c3 = st.columns(3)
        with c1:
            user_input["lagerflaeche"] = float(
                st.number_input("Lagerfläche (NUF 4) m²", 2000, 50000, 5000, 500))
            user_input["kommissionierung"] = float(
                st.number_input("Kommissionierung (NUF 4) m²", 500, 10000, 1200, 100))
        with c2:
            user_input["wareneingang_rampen"] = float(
                st.number_input("Wareneingang mit Rampen (NUF 4) m²", 300, 3000, 600, 50))
            user_input["warenausgang_rampen"] = float(
                st.number_input("Warenausgang mit Rampen (NUF 4) m²", 300, 3000, 600, 50))
        with c3:
            ret = st.number_input("Retouren (NUF 4) m² (optional)", 0, 2000, 300, 50)
            user_input["retouren"] = float(ret) if ret > 0 else None
        user_input["hochregallager"] = st.checkbox("Hochregallager (Raster 24×12 m, h ≥ 18 m)")

    elif typ == "Data Center":
        user_input["nutzungstyp"] = Nutzungstyp.DATA_CENTER
        c1, c2, c3 = st.columns(3)
        with c1:
            user_input["whitespace_it"] = float(
                st.number_input("Whitespace IT (NUF 3) m²", 500, 10000, 1500, 100))
            user_input["noc_buero"] = float(
                st.number_input("NOC / Büro (NUF 2) m²", 100, 1000, 250, 25))
        with c2:
            user_input["usv_trafo_pct"] = st.slider("USV / Trafo (% Whitespace)", 15, 25, 20) / 100
            user_input["kuehlung_chiller_pct"] = st.slider("Kühlung (% Whitespace)", 20, 30, 25) / 100
        with c3:
            user_input["notstrom_generatoren_pct"] = st.slider("Notstrom (% Whitespace)", 10, 15, 12) / 100
            tier = st.selectbox("Tier-Level", ["I", "II", "III", "IV"], index=2)
            user_input["tier_level"] = tier
            stag = st.number_input("Staging-Lager m² (optional)", 0, 500, 150, 25)
            user_input["staging_lager"] = float(stag) if stag > 0 else None

    # ---- Technische Anforderungen ----------------------------------------
    st.divider()
    st.markdown("#### Technische Anforderungen")
    st.caption("Die Vorauswahl entspricht dem Mindeststandard je Nutzungstyp (ArbStättV, DGUV V3).")

    col_mep1, col_mep2 = st.columns(2)
    with col_mep1:
        lueftung = st.radio(
            "Lüftungskonzept",
            options=["fenster", "mechanisch", "klima"],
            format_func=lambda x: {"fenster": "Fensterlüftung", "mechanisch": "Mechanische Lüftung",
                                    "klima": "Klimaanlage / RLT"}[x],
            index=["fenster", "mechanisch", "klima"].index(_def["lueftung"]),
            horizontal=True,
            help="ArbStättV §12: In Arbeitsräumen >100 m² ist mechanische Lüftung empfohlen.",
        )
    with col_mep2:
        lastklasse = st.radio(
            "Lastkategorie Boden",
            options=["leicht", "mittel", "schwer", "kran"],
            format_func=lambda x: {"leicht": "Leicht ≤5 kN/m²", "mittel": "Mittel ≤10 kN/m²",
                                    "schwer": "Schwer ≤20 kN/m²", "kran": "Kranbahn"}[x],
            index=["leicht", "mittel", "schwer", "kran"].index(
                "kran" if user_input.get("kranbahn_erforderlich") else "mittel"),
            horizontal=True,
            help="Beeinflusst Fundament- und Tragwerkstyp (DIN EN 1991).",
        )

    col_c1, col_c2, col_c3, col_c4 = st.columns(4)
    with col_c1:
        sprinkler = st.checkbox("Sprinkleranlage",  value=_def["sprinkler"],
                                help="VdS CEA 4001: Pflicht bei Lagerhöhe >7,5 m oder Lagergut B2/B3.")
        druckluft = st.checkbox("Druckluftversorgung", value=_def["druckluft"],
                                help="Betriebsüberdruck 6–10 bar, Ringleitung durch Produktionshalle.")
    with col_c2:
        kaelte    = st.checkbox("Kälteanlage",      value=_def["kaelte"],
                                help="Kältemaschine in TF, Leitungsführung zu Verbrauchern.")
        usv       = st.checkbox("USV / Notstrom",   value=_def["usv"],
                                help="Unterbrechungsfreie Stromversorgung + Dieselaggregat in TF.")
    with col_c3:
        it_kat = st.radio(
            "IT-Infrastruktur",
            options=["basis", "erweitert", "rechenzentrum"],
            format_func=lambda x: {"basis": "Basis (LAN)", "erweitert": "Erweitert (Serverraum)",
                                    "rechenzentrum": "Rechenzentrum"}[x],
            index=["basis", "erweitert", "rechenzentrum"].index(_def["it"]),
            help="Bestimmt IT-Trassendichte und ggf. eigene NUF-3-Zone.",
        )
    with col_c4:
        tragwerk_typ = st.selectbox(
            "Tragwerktypologie",
            options=["stahl", "stahlbeton", "holz", "hybrid"],
            format_func=lambda x: {"stahl": "Stahlbau", "stahlbeton": "Stahlbetonbau",
                                    "holz": "Holzbau", "hybrid": "Hybrid (Stahl+Holz)"}[x],
            index=0,
            help="Beeinflusst Spannweite, Höhe und Kostenstruktur.",
        )

    # MEP + Tragwerk in user_input schreiben
    user_input["mep_lueftung"]        = lueftung
    user_input["mep_sprinkler"]       = sprinkler
    user_input["mep_druckluft"]       = druckluft
    user_input["mep_kaelte"]          = kaelte
    user_input["mep_usv_notstrom"]    = usv
    user_input["mep_it_kategorie"]    = it_kat
    user_input["tragwerk_lastklasse"] = lastklasse
    user_input["tragwerk_typologie"]  = tragwerk_typ

    with st.expander("Was bewirken diese Angaben?", expanded=False):
        st.markdown("""
| Eingabe | Auswirkung im Layout |
|---------|---------------------|
| Lüftungskonzept | RLT-Trassengröße im Technikraum + Kanalquerschnitt |
| Lastkategorie | Tragwerktypologie, Stützenquerschnitt, Fundamenttyp |
| Sprinkleranlage | Wasserleitung (DN 100+) im Technikraum |
| Druckluftversorgung | Ringleitung NUF 3, Kompressorfläche in TF |
| Kälteanlage | Kältemittelleitung TF → Verbraucher |
| USV / Notstrom | Erweiterung TF, Batterieraum |
| IT-Kategorie | IT-Trasse Dichte, ggf. separater Serverraum |
| Tragwerktypologie | Stützenraster, Trauf-/Firsthöhe, Dachform |
        """)

    st.markdown("---")
    col_back, col_next = st.columns([1, 3])
    with col_back:
        if st.button("← Zurück", use_container_width=True):
            st.session_state.schritt = 0
            st.rerun()
    with col_next:
        if st.button("Weiter zum Funktionsgraph →", type="primary", use_container_width=True):
            st.session_state.user_input = user_input
            # Topology vorab berechnen, damit Schritt 3 echte Knoten/Kanten zeigt
            with st.spinner("Berechne Funktionsgraph…"):
                from app.agents.briefing import briefing_agent as _ba
                from app.agents.rules import rule_agent as _ra
                from app.agents.topology import topology_agent as _ta
                _tmp = {"user_input": user_input}
                _tmp.update(_ba(_tmp))
                _tmp.update(_ra(_tmp))
                _topo = _ta(_tmp)
                st.session_state.topology_diagram = _topo.get("topology_diagram")
            # fg_edges zurücksetzen damit Schritt 3 die neuen Kanten übernimmt
            st.session_state.fg_edges = None
            st.session_state.adjacency_weights = {}
            st.session_state.schritt = 3
            st.rerun()


# ---------------------------------------------------------------------------
# SCHRITT 5 – Projektziele (ersetzt Parametergewichtung)
# ---------------------------------------------------------------------------

_ZIELKATALOG = {
    "materialfluss": {
        "label": "Materialfluss-Effizienz",
        "icon": "🔄",
        "beschreibung": "Kurze Transportwege entlang der Prozesskette. Prozesskette bestimmt die Zonenreihenfolge.",
        "gewichtung": {"materialfluss": 0.70, "erweiterbarkeit": 0.20, "tragwerk": 0.10},
        "split_priority": "process_sequence",
        "variante_key": "A_Materialfluss",
        "variante_beschr": "Optimiert auf kurze Transportwege entlang der Prozesskette",
    },
    "erweiterbarkeit": {
        "label": "Erweiterbarkeit",
        "icon": "📐",
        "beschreibung": "Maximale Erweiterungsreserve an der freisten Fassade. Kompakter Block + freie Fassade.",
        "gewichtung": {"materialfluss": 0.20, "erweiterbarkeit": 0.70, "tragwerk": 0.10},
        "split_priority": "reserve_free",
        "variante_key": "B_Erweiterbarkeit",
        "variante_beschr": "Maximale Erweiterungsreserve an der freisten Fassade",
    },
    "tragwerk": {
        "label": "Tragwerk-Wirtschaftlichkeit",
        "icon": "🏗️",
        "beschreibung": "Reguläres Stützenraster, minimale Spannweiten, rechteckige Zonengeometrien.",
        "gewichtung": {"materialfluss": 0.20, "erweiterbarkeit": 0.20, "tragwerk": 0.60},
        "split_priority": "balanced_cut",
        "variante_key": "C_Ausgewogen",
        "variante_beschr": "Reguläres Tragwerksraster, minimale Spannweiten",
    },
    "techniktrassen": {
        "label": "Techniktrassen kurz",
        "icon": "⚡",
        "beschreibung": "Technikraum zentral positioniert, MEP-Trassen minimiert.",
        "gewichtung": {"materialfluss": 0.40, "erweiterbarkeit": 0.20, "tragwerk": 0.40},
        "split_priority": "mep_central",
        "variante_key": "C_Ausgewogen",
        "variante_beschr": "Technikraum zentral, kurze MEP-Trassen",
    },
    "kompaktheit": {
        "label": "Kompaktheit",
        "icon": "🔲",
        "beschreibung": "Minimierter A/V-Wert, energetisch effiziente Hülle, quadratische Grundform.",
        "gewichtung": {"materialfluss": 0.30, "erweiterbarkeit": 0.10, "tragwerk": 0.60},
        "split_priority": "compact",
        "variante_key": "C_Ausgewogen",
        "variante_beschr": "Kompakte quadratische Grundform, minimierter Perimeter",
    },
    "tageslicht": {
        "label": "Tageslicht & Arbeitsqualität",
        "icon": "☀️",
        "beschreibung": "Büro- und Sozialzonen an Außenfassaden mit Tageslichtbezug.",
        "gewichtung": {"materialfluss": 0.30, "erweiterbarkeit": 0.40, "tragwerk": 0.30},
        "split_priority": "balanced_cut",
        "variante_key": "A_Materialfluss",
        "variante_beschr": "Büro/Sozial an Außenfassaden, optimierter Tageslichtbezug",
    },
}

_VARIANTE_KEYS = ["A_Materialfluss", "B_Erweiterbarkeit", "C_Ausgewogen"]


def _auto_vorschlaege(fg_edges: list) -> list[str]:
    """Leitet Ziel-Vorschläge aus den Funktionsgraph-Kanten ab."""
    vorschlaege: list[str] = []
    if not fg_edges:
        return ["materialfluss", "erweiterbarkeit", "tragwerk"]
    prozess_weights = [w for _, _, w, cat in fg_edges if cat == "Prozess"]
    betrieb_tf = [w for src, tgt, w, cat in fg_edges if cat == "Betrieb"
                  and ("Technik" in src or "Technik" in tgt)]
    personal_weights = [w for _, _, w, cat in fg_edges if cat == "Personal"]
    if prozess_weights and sum(prozess_weights) / len(prozess_weights) > 0.65:
        vorschlaege.append("materialfluss")
    if betrieb_tf and sum(betrieb_tf) / len(betrieb_tf) > 0.45:
        vorschlaege.append("techniktrassen")
    if personal_weights and sum(personal_weights) / len(personal_weights) > 0.5:
        vorschlaege.append("tageslicht")
    if "materialfluss" not in vorschlaege:
        vorschlaege.append("materialfluss")
    if "erweiterbarkeit" not in vorschlaege:
        vorschlaege.append("erweiterbarkeit")
    return vorschlaege[:4]


def schritt_projektziele():
    st.markdown('<span class="phase-badge">2.4</span> **Gebäudeplanung — Projektziele & Varianten-Konfiguration**',
                unsafe_allow_html=True)
    st.caption(
        "Wähle 2–4 Projektziele. Jedes Ziel bestimmt eine Optimierungsrichtung für eine Layoutvariante. "
        "Vorschläge werden aus dem Funktionsgraph und dem Regelwerk abgeleitet."
    )
    st.markdown("---")

    # Auto-Vorschläge aus Funktionsgraph
    fg_edges = st.session_state.get("fg_edges") or []
    vorschlaege = _auto_vorschlaege(fg_edges)

    st.markdown("**Vorgeschlagene Ziele** *(aus Funktionsgraph abgeleitet)*")
    vorschlag_text = " · ".join(
        f"{_ZIELKATALOG[k]['icon']} {_ZIELKATALOG[k]['label']}" for k in vorschlaege if k in _ZIELKATALOG
    )
    st.info(vorschlag_text or "Keine Vorschläge — Ziele manuell auswählen.")

    st.markdown("**Zielauswahl**")
    selected: list[str] = []
    cols = st.columns(3)
    for idx, (key, ziel) in enumerate(_ZIELKATALOG.items()):
        with cols[idx % 3]:
            vorgeschlagen = key in vorschlaege
            default = vorgeschlagen or key in (st.session_state.projektziele or [])
            checked = st.checkbox(
                f"{ziel['icon']} **{ziel['label']}**",
                value=default,
                key=f"ziel_{key}",
                help=ziel["beschreibung"],
            )
            if checked:
                selected.append(key)
                st.caption(ziel["beschreibung"])

    if len(selected) < 2:
        st.warning("Bitte mindestens 2 Ziele auswählen.")
    elif len(selected) > 4:
        st.warning("Maximal 4 Ziele möglich — bitte Auswahl reduzieren.")

    # Vorschau: welche Varianten werden generiert?
    st.markdown("---")
    st.markdown("**Varianten-Vorschau**")
    selected_valid = selected[:4] if len(selected) >= 2 else []
    if selected_valid:
        variant_cols = st.columns(min(3, len(selected_valid)))
        var_labels = ["Variante A", "Variante B", "Variante C", "Variante D"]
        for i, key in enumerate(selected_valid[:3]):
            ziel = _ZIELKATALOG[key]
            with variant_cols[i % 3]:
                st.markdown(f"**{var_labels[i]}** {ziel['icon']}")
                st.caption(ziel["variante_beschr"])

    # Mapping selected → custom_gewichtungen + split_priority_map (3 feste Varianten-Keys)
    _DEFAULT_SPLITS = ["process_sequence", "reserve_east", "balanced_cut"]

    def _build_gewichtungen(selected_keys: list[str]) -> dict:
        custom = {}
        for i, vkey in enumerate(_VARIANTE_KEYS):
            if i < len(selected_keys):
                g = _ZIELKATALOG[selected_keys[i]]["gewichtung"]
            else:
                g = {"materialfluss": 0.34, "erweiterbarkeit": 0.33, "tragwerk": 0.33}
            custom[vkey] = g
        return custom

    def _build_split_priority_map(selected_keys: list[str]) -> dict:
        result = {}
        for i, vkey in enumerate(_VARIANTE_KEYS):
            if i < len(selected_keys):
                result[vkey] = _ZIELKATALOG[selected_keys[i]].get("split_priority", _DEFAULT_SPLITS[i])
            else:
                result[vkey] = _DEFAULT_SPLITS[i]
        return result

    st.markdown("---")
    col_back, col_gen = st.columns([1, 3])
    with col_back:
        if st.button("← Zurück", use_container_width=True, key="pz_back"):
            st.session_state.schritt = 4
            st.rerun()
    with col_gen:
        btn_label = "🏭 Layouts generieren" if len(selected_valid) >= 2 else "🏭 Layouts generieren (mind. 2 Ziele wählen)"
        if _current_role == "viewer":
            st.info("Als Betrachter können Sie keine neue Berechnung starten.", icon="🔒")
        else:
            if st.button(btn_label, type="primary", use_container_width=True,
                         disabled=len(selected_valid) < 2):
                st.session_state.projektziele = selected_valid
                st.session_state.custom_gewichtungen = _build_gewichtungen(selected_valid)
                split_priority_map = _build_split_priority_map(selected_valid)

                with st.spinner("Pipeline läuft… Briefing → Regelwerk → Layouts → Bewertung → Analyse → Report"):
                    # adjacency_weights: "__"-Format → "|"-Format für layout.py
                    # layout.py liest: graph_weights.get(f"{name}|{halle_name}", 0)
                    _aw_raw = st.session_state.adjacency_weights or {}
                    _aw_pipe: dict[str, float] = {}
                    for k, v in _aw_raw.items():
                        pipe_key = k.replace("__", "|")
                        _aw_pipe[pipe_key] = v
                        # Auch Gegenrichtung eintragen
                        parts = pipe_key.split("|", 1)
                        if len(parts) == 2:
                            _aw_pipe[f"{parts[1]}|{parts[0]}"] = v
                    _layout_site_geometry = st.session_state.building_parcel or st.session_state.site_geometry
                    result = graph.invoke({
                        "user_input":          st.session_state.user_input,
                        "site_geometry":       _layout_site_geometry,
                        "masterplan":          st.session_state.masterplan,
                        "building_parcels":    st.session_state.building_parcels,
                        "selected_building_parcel_id": st.session_state.selected_building_parcel_id,
                        "building_parcel":     st.session_state.building_parcel,
                        "custom_gewichtungen": st.session_state.custom_gewichtungen,
                        "rule_overrides":      st.session_state.rule_overrides,
                        "rule_change_request": st.session_state.rule_change_request,
                        "projektziele":        selected_valid,
                        "split_priority_map":  split_priority_map,
                        "adjacency_weights":   _aw_pipe,
                        "zone_splits":         st.session_state.zone_splits,
                        "gap_strategy":        st.session_state.gap_strategy,
                    })
                st.session_state.result = result
                st.session_state.schritt = 6
                st.rerun()


# ---------------------------------------------------------------------------
# SCHRITT 4 – Funktionsgraph
# ---------------------------------------------------------------------------

def _get_graph_config(nutzungstyp):
    from app.state import Nutzungstyp
    if nutzungstyp == Nutzungstyp.PRODUKTION:
        nodes = [
            {"id": "Wareneingang",     "farbe": "#4A90D9"},
            {"id": "Lager_Rohstoffe",  "farbe": "#5BA85B"},
            {"id": "Produktion",       "farbe": "#E8834A"},
            {"id": "QS",               "farbe": "#E84A6B"},
            {"id": "Lager_FW",         "farbe": "#5BA85B"},
            {"id": "Versand",          "farbe": "#4A90D9"},
            {"id": "Buero",            "farbe": "#9B59B6"},
            {"id": "Technik",          "farbe": "#95A5A6"},
            {"id": "Sozial",           "farbe": "#F1C40F"},
        ]
        edges = [
            ("Wareneingang",   "Lager_Rohstoffe", 0.9, "Prozess"),
            ("Lager_Rohstoffe","Produktion",       0.9, "Prozess"),
            ("Produktion",     "QS",               0.8, "Prozess"),
            ("QS",             "Lager_FW",         0.7, "Prozess"),
            ("Lager_FW",       "Versand",           0.9, "Prozess"),
            ("Wareneingang",   "Versand",           0.2, "Extern"),
            ("Produktion",     "Technik",           0.5, "Betrieb"),
            ("Buero",          "Produktion",        0.4, "Supervision"),
            ("Sozial",         "Buero",             0.5, "Personal"),
            ("Technik",        "Buero",             0.2, "Betrieb"),
        ]
        process_order = ["Wareneingang", "Lager_Rohstoffe", "Produktion", "QS", "Lager_FW", "Versand"]
    elif nutzungstyp == Nutzungstyp.LOGISTIK:
        nodes = [
            {"id": "Wareneingang",     "farbe": "#4A90D9"},
            {"id": "Lager",            "farbe": "#5BA85B"},
            {"id": "Kommissionierung", "farbe": "#E8834A"},
            {"id": "Warenausgang",     "farbe": "#4A90D9"},
            {"id": "Retouren",         "farbe": "#E84A6B"},
            {"id": "Buero",            "farbe": "#9B59B6"},
            {"id": "Sozial",           "farbe": "#F1C40F"},
            {"id": "Technik",          "farbe": "#95A5A6"},
        ]
        edges = [
            ("Wareneingang",   "Lager",           0.9, "Prozess"),
            ("Lager",          "Kommissionierung", 0.8, "Prozess"),
            ("Kommissionierung","Warenausgang",    0.9, "Prozess"),
            ("Retouren",       "Lager",            0.6, "Prozess"),
            ("Wareneingang",   "Warenausgang",     0.2, "Extern"),
            ("Lager",          "Technik",          0.4, "Betrieb"),
            ("Buero",          "Kommissionierung", 0.4, "Supervision"),
            ("Sozial",         "Buero",            0.5, "Personal"),
        ]
        process_order = ["Wareneingang", "Lager", "Kommissionierung", "Warenausgang"]
    else:  # Data Center
        nodes = [
            {"id": "Whitespace", "farbe": "#4A90D9"},
            {"id": "USV_Trafo",  "farbe": "#E8834A"},
            {"id": "Kuehlung",   "farbe": "#5BA85B"},
            {"id": "Notstrom",   "farbe": "#E84A6B"},
            {"id": "NOC_Buero",  "farbe": "#9B59B6"},
            {"id": "Staging",    "farbe": "#95A5A6"},
        ]
        edges = [
            ("USV_Trafo", "Whitespace", 0.9, "Betrieb"),
            ("Kuehlung",  "Whitespace", 0.9, "Betrieb"),
            ("Notstrom",  "USV_Trafo",  0.8, "Betrieb"),
            ("Notstrom",  "Whitespace", 0.7, "Betrieb"),
            ("Staging",   "Whitespace", 0.5, "Prozess"),
            ("NOC_Buero", "Whitespace", 0.6, "Supervision"),
        ]
        process_order = ["USV_Trafo", "Whitespace", "Kuehlung", "Notstrom"]
    return nodes, edges, process_order


def _topology_to_fg_edges(topo: dict) -> tuple[list[dict], list[tuple], list[str]]:
    """Konvertiert topology_diagram in das interne fg-Format.

    Returns:
        nodes:        [{id, farbe, din}]  — echte Zonennamen (mit Leerzeichen)
        edges:        [(src, tgt, weight, kategorie)]
        process_order: [str]
    """
    _KIND_LABEL: dict[str, str] = {
        "process":    "Prozess",
        "adjacency":  "Adjacency",
        "separation": "Separation",
        "compliance": "Compliance",
    }
    nodes_raw     = topo.get("nodes", [])
    edges_raw     = topo.get("edges", [])
    process_order = topo.get("process_order", [])

    nodes = [
        {
            "id":    n["name"],
            "farbe": n.get("farbe", "#AAAAAA"),
            "din":   n.get("din_kategorie", ""),
        }
        for n in nodes_raw
    ]
    edges = [
        (
            e["source"],
            e["target"],
            float(e.get("weight", 0.5)),
            _KIND_LABEL.get(e.get("kind", "adjacency"), "Adjacency"),
        )
        for e in edges_raw
        if e.get("source") and e.get("target")
    ]
    return nodes, edges, process_order


def schritt_funktionsgraph():
    st.markdown('<span class="phase-badge">2.2</span> **Gebäudeplanung — Funktionsgraph & Abhängigkeiten**',
                unsafe_allow_html=True)
    st.caption("Passe die Verbindungsgewichte an. Höhere Werte = stärkere räumliche Nähe im Layout.")

    user_input = st.session_state.user_input
    nutzungstyp = user_input["nutzungstyp"]

    # Datenquelle: topology_diagram bevorzugen, _get_graph_config als Fallback
    topo = st.session_state.get("topology_diagram")
    if topo and topo.get("nodes") and topo.get("edges"):
        nodes, base_edges, process_order = _topology_to_fg_edges(topo)
    else:
        nodes, base_edges, process_order = _get_graph_config(nutzungstyp)

    # fg_edges initialisieren wenn noch nicht gesetzt
    if not st.session_state.get("fg_edges"):
        st.session_state.fg_edges = list(base_edges)

    active_edges = st.session_state.fg_edges

    # Separation-Kanten sind nicht editierbar
    editable_edges   = [(s, t, w, c) for s, t, w, c in active_edges if c != "Separation"]
    separation_edges = [(s, t, w, c) for s, t, w, c in active_edges if c == "Separation"]
    all_edge_keys    = {f"{s}__{t}" for s, t, _, _ in editable_edges}

    if not st.session_state.adjacency_weights:
        st.session_state.adjacency_weights = {
            f"{s}__{t}": abs(w) for s, t, w, _ in editable_edges
        }
    weights: dict[str, float] = {
        k: st.session_state.adjacency_weights.get(k, 0.5) for k in all_edge_keys
    }
    # Separation-Gewichte (negativ) unveränderlich einmischen
    for s, t, w, _ in separation_edges:
        weights[f"{s}__{t}"] = w

    # Area lookup direkt aus topology_diagram.nodes
    area_lookup: dict[str, float] = {}
    if topo and topo.get("nodes"):
        for n in topo["nodes"]:
            area_lookup[n["name"]] = float(n.get("area_m2", 100.0))
    else:
        for src, tgt, _, _ in active_edges:
            area_lookup.setdefault(src, 100.0)
            area_lookup.setdefault(tgt, 100.0)
        for area_key, field in [
            ("Produktion", "produktionsflaeche"), ("Lager_Rohstoffe", "lager_rohstoffe"),
            ("Lager_FW", "lager_fertigwaren"),    ("Wareneingang", "wareneingang"),
            ("Versand", "versand"),               ("Buero", "buero_nuf2"),
            ("Lager", "lagerflaeche"),            ("Kommissionierung", "kommissionierung"),
        ]:
            if field in user_input:
                area_lookup[area_key] = float(user_input[field])

    st.markdown("---")

    tab_fg, tab_eg = st.tabs(["Funktionsgraph", "Erschließungsgraph"])

    with tab_fg:
        from app.tools.graph_viz import build_funktionsgraph_figure, EDGE_COLORS, EDGE_READONLY
        import pandas as pd

        # ── Vollbreite-Graph mit Klick-Interaktion ────────────────────────
        _sel_edge   = st.session_state.fg_selected_edge
        _pend_node  = st.session_state.fg_pending_node

        fig_fg = build_funktionsgraph_figure(
            nodes=nodes, edges=active_edges, weights=weights,
            area_lookup=area_lookup,
            selected_edge=_sel_edge,
            selected_node=_pend_node,
            process_order=process_order, layout_mode="layered",
        )

        if st.button("Funktionsgraph interaktiv öffnen", type="primary", use_container_width=True, key="fg_viewer_open_btn"):
            st.session_state["fg_viewer_open"] = True
        if st.session_state.get("fg_viewer_open"):
            _fg_event = _render_interactive_plotly_viewer("Gebäudeplanung · Funktionsgraph", fig_fg, key="fg_viewer")
        else:
            _fg_event = None

        # ── Event-Parsing: Klick auf Kante oder Knoten ───────────────────
        _sel_pts = []
        try:
            _sel_pts = (_fg_event.selection.points or []) if _fg_event and _fg_event.selection else []
        except Exception:
            _sel_pts = []

        if _sel_pts:
            _pt = _sel_pts[0]
            _cd = _pt.get("customdata") or []
            if len(_cd) >= 2:
                _id, _type = _cd[0], _cd[1]
                if _type == "edge":
                    # Kant angeklickt → als selected_edge setzen, Knoten-Selektion löschen
                    st.session_state.fg_selected_edge = _id
                    st.session_state.fg_pending_node  = None
                elif _type == "node":
                    # Knoten angeklickt
                    _cur_pend = st.session_state.fg_pending_node
                    _had_two  = _cur_pend and "+" in _cur_pend
                    if _had_two or _cur_pend is None:
                        # Neuer erster Knoten (oder nach abgeschlossener Aktion)
                        st.session_state.fg_pending_node  = _id
                        st.session_state.fg_selected_edge = None
                    elif _cur_pend == _id:
                        # Gleicher Knoten → deselektieren
                        st.session_state.fg_pending_node  = None
                    else:
                        # Zweiter Knoten → Verbindungs-Dialog aktivieren
                        st.session_state.fg_pending_node  = f"{_cur_pend}+{_id}"
                        st.session_state.fg_selected_edge = None

        # ── Kontextuelles Panel ───────────────────────────────────────────
        _sel_edge  = st.session_state.fg_selected_edge
        _pend_node = st.session_state.fg_pending_node

        if _sel_edge and _sel_edge in weights:
            # ── Kante ausgewählt: Gewicht-Slider + Löschen-Button ─────────
            _e_data = next((e for e in active_edges if f"{e[0]}__{e[1]}" == _sel_edge), None)
            if _e_data:
                _esrc, _etgt, _ew_def, _ecat = _e_data
                _cur_w = float(weights.get(_sel_edge, _ew_def))
                _is_readonly = _ecat in EDGE_READONLY
                _esrc_d = _esrc.replace("_", " ")
                _etgt_d = _etgt.replace("_", " ")

                _c1, _c2, _c3, _c4, _c5 = st.columns([4, 1, 1, 1, 1])
                with _c1:
                    _new_w = st.slider(
                        f"**{_esrc_d}** → **{_etgt_d}** (`{_ecat}`)",
                        0.0, 1.0, _cur_w, 0.05,
                        key="fg_sel_slider",
                        disabled=_is_readonly,
                    )
                    if not _is_readonly:
                        st.session_state.adjacency_weights[_sel_edge] = _new_w
                with _c2:
                    st.markdown("&nbsp;", unsafe_allow_html=True)  # vertical spacer
                    if not _is_readonly and st.button("−", key="fg_minus", help="−0.1"):
                        st.session_state.adjacency_weights[_sel_edge] = round(max(0.0, _cur_w - 0.1), 2)
                        st.rerun()
                with _c3:
                    st.markdown("&nbsp;", unsafe_allow_html=True)
                    if not _is_readonly and st.button("+", key="fg_plus", help="+0.1"):
                        st.session_state.adjacency_weights[_sel_edge] = round(min(1.0, _cur_w + 0.1), 2)
                        st.rerun()
                with _c4:
                    st.markdown("&nbsp;", unsafe_allow_html=True)
                    if not _is_readonly and st.button("🗑", key="fg_del_sel_btn", help="Verbindung entfernen"):
                        st.session_state.fg_edges = [
                            e for e in active_edges if f"{e[0]}__{e[1]}" != _sel_edge
                        ]
                        st.session_state.adjacency_weights.pop(_sel_edge, None)
                        st.session_state.fg_selected_edge = None
                        st.rerun()
                with _c5:
                    st.markdown("&nbsp;", unsafe_allow_html=True)
                    if st.button("✕", key="fg_desel_edge", help="Auswahl aufheben"):
                        st.session_state.fg_selected_edge = None
                        st.rerun()
                if _is_readonly:
                    st.caption("🔴 Trennkante — vom Regelwerk gesetzt, nicht editierbar.")

        elif _pend_node and "+" in _pend_node:
            # ── Zwei Knoten ausgewählt: Verbindungs-Dialog ────────────────
            _n1, _n2 = _pend_node.split("+", 1)
            _n1d, _n2d = _n1.replace("_", " "), _n2.replace("_", " ")
            st.info(f"📍 **{_n1d}** → **{_n2d}** — Neue Verbindung definieren:")
            _da1, _da2, _da3, _da4 = st.columns([2, 1, 1, 1])
            with _da1:
                _new_cat_add = st.selectbox(
                    "Verbindungstyp", ["Prozess", "Adjacency", "Betrieb", "Personal", "Extern"],
                    key="fg_add2_cat",
                )
            with _da2:
                _new_w_add = st.number_input("Gewicht", 0.0, 1.0, 0.5, 0.05, key="fg_add2_w")
            with _da3:
                st.markdown("&nbsp;", unsafe_allow_html=True)
                if st.button("Hinzufügen", key="fg_add2_btn", type="primary"):
                    _nk = f"{_n1}__{_n2}"
                    if _nk not in {f"{e[0]}__{e[1]}" for e in active_edges}:
                        st.session_state.fg_edges = active_edges + [(_n1, _n2, _new_w_add, _new_cat_add)]
                        st.session_state.adjacency_weights[_nk] = _new_w_add
                    st.session_state.fg_pending_node = None
                    st.rerun()
            with _da4:
                st.markdown("&nbsp;", unsafe_allow_html=True)
                if st.button("Abbrechen", key="fg_add2_cancel"):
                    st.session_state.fg_pending_node = None
                    st.rerun()

        elif _pend_node and "+" not in _pend_node:
            # ── Ein Knoten ausgewählt: Hinweis ───────────────────────────
            _nd = _pend_node.replace("_", " ")
            _cx1, _cx2 = st.columns([5, 1])
            with _cx1:
                st.info(f"📍 **{_nd}** ausgewählt — zweiten Knoten anklicken um Verbindung zu erstellen.")
            with _cx2:
                if st.button("✕ Aufheben", key="fg_desel_node"):
                    st.session_state.fg_pending_node = None
                    st.rerun()

        else:
            st.caption("💡 Kante anklicken zum Bearbeiten · Knoten anklicken zum Verbinden")

        # ── Alle Verbindungen (kollabierbar, als Fallback-Editor) ─────────
        with st.expander("📋 Alle Verbindungen bearbeiten", expanded=False):
            _table_rows = [
                {
                    "Von":     src,
                    "Nach":    tgt,
                    "Typ":     cat,
                    "Gewicht": round(float(weights.get(f"{src}__{tgt}", w)), 2),
                }
                for src, tgt, w, cat in editable_edges
            ]
            _edited_df = st.data_editor(
                pd.DataFrame(_table_rows),
                column_config={
                    "Von":    st.column_config.TextColumn(disabled=True, width="small"),
                    "Nach":   st.column_config.TextColumn(disabled=True, width="small"),
                    "Typ":    st.column_config.TextColumn(disabled=True, width="small"),
                    "Gewicht": st.column_config.NumberColumn(
                        min_value=0.0, max_value=1.0, step=0.05, format="%.2f", width="small"
                    ),
                },
                hide_index=True,
                use_container_width=True,
                key="fg_data_editor",
                num_rows="fixed",
            )
            _new_weights: dict[str, float] = {}
            for _, _row in _edited_df.iterrows():
                _ekey = f"{_row['Von']}__{_row['Nach']}"
                _new_weights[_ekey] = float(_row["Gewicht"])
            for s, t, w, _ in separation_edges:
                _new_weights[f"{s}__{t}"] = w
            st.session_state.adjacency_weights = _new_weights

            # Trennkanten (read-only Anzeige)
            if separation_edges:
                st.caption("🔴 **Trennkanten** (nicht editierbar): "
                           + " · ".join(f"{s} → {t}" for s, t, _, _ in separation_edges))

            # Verbindung manuell hinzufügen (Fallback für non-Touch)
            with st.expander("➕ Verbindung hinzufügen"):
                _node_ids_all = [n["id"] for n in nodes]
                _nc1, _nc2 = st.columns(2)
                with _nc1:
                    _new_src = st.selectbox("Von", _node_ids_all, key="fg_new_src")
                    _new_cat = st.selectbox("Typ", ["Prozess", "Adjacency", "Betrieb", "Personal", "Extern"],
                                            key="fg_new_cat")
                with _nc2:
                    _new_tgt = st.selectbox("Nach", _node_ids_all, key="fg_new_tgt")
                    _new_weight = st.number_input("Gewicht", 0.0, 1.0, 0.5, 0.05, key="fg_new_w")
                if st.button("Hinzufügen", key="fg_add_edge", type="secondary"):
                    _new_key = f"{_new_src}__{_new_tgt}"
                    if _new_src != _new_tgt and _new_key not in all_edge_keys:
                        st.session_state.fg_edges = active_edges + [(_new_src, _new_tgt, _new_weight, _new_cat)]
                        st.session_state.adjacency_weights[_new_key] = _new_weight
                        st.rerun()
                    elif _new_src == _new_tgt:
                        st.warning("Quelle und Ziel müssen verschieden sein.")
                    else:
                        st.info("Verbindung existiert bereits.")

    with tab_eg:
        from app.tools.graph_viz import build_erschliessungsgraph_figure
        _variants = (st.session_state.get("result") or {}).get("variants")
        fig_eg = build_erschliessungsgraph_figure(
            user_input,
            st.session_state.site_geometry,
            variants=_variants,
        )
        if st.button("Erschließungsgraph im Viewer öffnen", type="primary", use_container_width=True, key="eg_viewer_open_btn"):
            st.session_state["eg_viewer_open"] = True
        if st.session_state.get("eg_viewer_open"):
            _render_plotly_viewer("Gebäudeplanung · Erschließungsgraph", fig_eg, key="eg_viewer")
        st.caption("Schematische Draufsicht der Erschließungsrouten (nicht editierbar).")

    # ── Zonensplitting ────────────────────────────────────────────────────────
    st.markdown("---")
    with st.expander("Zonensplitting (optional)", expanded=False):
        st.caption("Große Zonen in gleich große Teilbereiche aufteilen — z. B. Produktion in zwei unabhängige Fertigungslinien.")
        zone_splits: dict[str, int] = dict(st.session_state.zone_splits)
        _split_options = {1: "Keine", 2: "2 Teile", 3: "3 Teile", 4: "4 Teile"}
        # area_lookup aus topology_diagram wenn verfügbar
        _area_lookup: dict[str, float] = dict(area_lookup)
        _splittable = {name: a for name, a in _area_lookup.items() if a > 600}
        if not _splittable:
            st.info("Keine Zone groß genug für Splitting (> 600 m²).")
        else:
            for zone_name, area in sorted(_splittable.items(), key=lambda x: -x[1]):
                current = zone_splits.get(zone_name, 1)
                cols = st.columns([2, 3])
                with cols[0]:
                    st.markdown(f"**{zone_name}** ({area:,.0f} m²)")
                with cols[1]:
                    sel = st.radio(
                        f"split_{zone_name}",
                        options=list(_split_options.keys()),
                        format_func=lambda x: _split_options[x],
                        index=list(_split_options.keys()).index(current) if current in _split_options else 0,
                        horizontal=True,
                        label_visibility="collapsed",
                        key=f"zone_split_{zone_name}",
                    )
                    zone_splits[zone_name] = int(sel)
        st.session_state.zone_splits = {k: v for k, v in zone_splits.items() if v > 1}

    # ── Lückenbehandlung ─────────────────────────────────────────────────────
    st.markdown("---")
    with st.expander("🔗 Lückenbehandlung — Fehlende Wandkontakte", expanded=False):
        st.caption(
            "Wenn zwei Funktionsbereiche verbunden sein sollen, im Layout aber keine gemeinsame Wand haben, "
            "gibt es drei Strategien zur Behandlung."
        )
        _GAP_OPTS = {
            "none":     ("Keine Anpassung",             "Lücken werden nur in der Bewertung als Penalty (-0.4×Gewicht) erfasst."),
            "sort":     ("📐 Prozessketten-Sortierung",  "Zonen werden nach Prozessreihenfolge angeordnet: Pre-Halle links, Post-Halle rechts — maximiert direkte Wandkontakte."),
            "corridor": ("🚪 Flur-Generator",            "Nach der Zonenerzeugung werden schmale Erschließungskorridore (3 m) für kritische Lücken eingefügt."),
            "all":      ("⚡ Kombiniert (Sort + Flur)", "Prozessketten-Sortierung UND Flur-Generator werden kombiniert angewendet."),
        }
        current_gap = st.session_state.gap_strategy or "none"
        _cols_g = st.columns(len(_GAP_OPTS))
        for i, (key, (label, desc)) in enumerate(_GAP_OPTS.items()):
            with _cols_g[i]:
                selected = current_gap == key
                border_style = "2px solid #005A8E" if selected else "1px solid #DDD"
                bg_color     = "#EAF4FC" if selected else "#FAFAFA"
                st.markdown(
                    f"""<div style="border:{border_style};border-radius:8px;padding:10px;
                        background:{bg_color};min-height:120px;cursor:pointer">
                        <b>{label}</b><br/><small style="color:#555">{desc}</small>
                        </div>""",
                    unsafe_allow_html=True,
                )
                if st.button(
                    "✓ Auswählen" if selected else "Auswählen",
                    key=f"gap_select_{key}",
                    use_container_width=True,
                    type="primary" if selected else "secondary",
                ):
                    st.session_state.gap_strategy = key
                    st.rerun()

        # Penalty-Hinweis immer sichtbar
        st.info(
            "📊 **Score-Penalty** (Ansatz 2) ist immer aktiv: "
            "Jede fehlende Wand bei einer Prozess-Kante mit Gewicht ≥ 0.5 "
            "reduziert den Materialfluss-Score um `0.4 × Gewicht`.",
            icon=None,
        )

    st.markdown("---")
    col_back, col_next = st.columns([1, 3])
    with col_back:
        if st.button("← Zurück", use_container_width=True, key="fg_back"):
            st.session_state.schritt = 2
            st.rerun()
    with col_next:
        if st.button("Weiter zum Regelwerk →", type="primary", use_container_width=True):
            st.session_state.schritt = 4
            st.rerun()


# ---------------------------------------------------------------------------
# SCHRITT 5 – Regelwerk
# ---------------------------------------------------------------------------

def schritt_regelwerk():
    st.markdown('<span class="phase-badge">2.3</span> **Gebäudeplanung — Regelwerk prüfen & anpassen**',
                unsafe_allow_html=True)

    from app.tools.rules_ui import render_rule_catalog

    st.markdown("---")

    # Regelwerk-Katalog (Zwei-Phasen-UI)
    rule_overrides = render_rule_catalog(st, existing_overrides=st.session_state.rule_overrides)

    # Optionaler Freitext-Änderungswunsch für den LLM-Rule-Agent
    st.markdown("---")
    st.markdown("**Ergänzende Anforderungen (optional)**")
    rule_change_request = st.text_area(
        "Änderungswunsch in natürlicher Sprache",
        value=st.session_state.rule_change_request or "",
        placeholder="z. B. Kranbahnerfordernis, akustische Trennung zwischen Büro und Produktion…",
        height=80,
        help="Wird per LLM in Regel-Overrides übersetzt, wenn OPENAI_API_KEY gesetzt ist.",
        label_visibility="collapsed",
    )

    st.markdown("---")
    col_back, col_gen = st.columns([1, 3])
    with col_back:
        if st.button("← Zurück", use_container_width=True, key="rw_back"):
            st.session_state.schritt = 3
            st.rerun()
    with col_gen:
        if st.button("Weiter zu Projektzielen →", type="primary", use_container_width=True):
            st.session_state.rule_overrides = rule_overrides
            st.session_state.rule_change_request = rule_change_request.strip() or None
            st.session_state.schritt = 5
            st.rerun()


# ---------------------------------------------------------------------------
# SCHRITT 6 – Ergebnisse
# ---------------------------------------------------------------------------

def schritt_ergebnisse():
    result = st.session_state.result
    # ── Auto-Speichern (einmalig pro Lauf) ──────────────────────────────────
    if _current_role in ("planner", "admin") and not st.session_state.get("_last_saved_run_id"):
        try:
            from app.tools.persistence import save_run as _save_run
            _rid = _save_run(_current_user, result)
            st.session_state["_last_saved_run_id"] = _rid
            try:
                from app.tools.persistence import save_planning_stand as _save_stand
                _briefing = result.get("structured_briefing") or {}
                _site = result.get("site_geometry") or {}
                _label = f"Gebäudeplanung · {_site.get('name', 'Parzelle')} · {_briefing.get('nutzungstyp', '')}"
                st.session_state["_last_building_plan_stand_id"] = _save_stand(
                    _current_user,
                    "building_plan",
                    _label,
                    result,
                    parent_id=st.session_state.get("_last_masterplan_stand_id"),
                    source_ref=str(result.get("selected_building_parcel_id") or (_site.get("id") or "")),
                )
            except Exception as _e:
                st.caption(f"Gebäudeplanung konnte nicht als Planungsstand gespeichert werden: {_e}")
        except Exception as _e:
            st.caption(f"Speichern fehlgeschlagen: {_e}")

    st.markdown('<span class="phase-badge">2.5</span> **Gebäudeplanung — Varianten & Bewertung**',
                unsafe_allow_html=True)

    site = result.get("site_geometry") or st.session_state.site_geometry
    if site:
        st.caption(
            f"Grundstück: {site['name']} · {site['area_m2']} m² · "
            f"{site['width_m']:.0f} × {site['depth_m']:.0f} m · "
            f"{len(site['access_points'])} Zufahrt(en)"
        )

    # ── Kurzinfo: Kapazitäts-Anpassung als Badge (keine volle Warning-Box) ────
    variants_list = result.get("variants") or []
    cap_warn = next((v.get("capacity_warning") for v in variants_list if v.get("capacity_warning")), None)
    if cap_warn:
        rf = cap_warn.get("reduction_factor", 1.0)
        st.info(
            f"ℹ️ Flächenanpassung aktiv (Reduktionsfaktor {rf:.0%}) — "
            "Details im Tab **⚠ Hinweise**.",
            icon=None,
        )

    # ── Determinismus-Badge ────────────────────────────────────────────────────
    llm_agents = result.get("llm_used_agents") or []
    _planning_llm_agents = [a for a in llm_agents if a in ("rules", "topology", "strategy")]
    if _planning_llm_agents:
        _agent_labels = {
            "rules":    "Planungsrat (Regelwerk)",
            "topology": "Topologie-Anpassung",
            "strategy": "Layoutstrategie",
        }
        _names = ", ".join(_agent_labels.get(a, a) for a in _planning_llm_agents)
        st.warning(
            f"🟡 **KI-Vorschlag aktiv** — Sonderbedingungen aktivierten LLM-Planung: "
            f"{_names}. Ergebnisse können bei gleichen Eingaben leicht variieren.",
            icon=None,
        )
    else:
        st.caption(
            "✅ Deterministischer Modus — alle Planungsentscheidungen sind regelbasiert "
            "und bei gleichen Eingaben vollständig reproduzierbar."
        )

    # Kurzübersicht
    evals     = result["evaluations"]
    selected  = result["selected_variant"]
    eval_map  = {e["variante"]: e for e in evals}

    col_a, col_b, col_c = st.columns(3)
    for col, ev in zip([col_a, col_b, col_c], evals):
        empfohlen = ev["variante"] == selected
        with col:
            label = ev["variante"].replace("_", " ")
            badge = " ★ Empfohlen" if empfohlen else ""
            st.metric(
                label=f"{label}{badge}",
                value=f"{ev['gesamtscore']:.1f} / 10",
                delta=f"MF {ev['materialfluss_score']:.1f} · EB {ev['erweiterbarkeit_score']:.1f} · TW {ev['tragwerk_score']:.1f}",
            )
    st.divider()

    # ── Haupt-Tabs ──────────────────────────────────────────────────────────
    variante_keys = ["A_Materialfluss", "B_Erweiterbarkeit", "C_Ausgewogen"]
    projektziele  = result.get("projektziele") or []
    _tab_defaults = [
        "Variante A – Materialfluss",
        "Variante B – Erweiterbarkeit",
        "Variante C – Ausgewogen",
    ]
    var_tab_labels = []
    for i, vkey in enumerate(variante_keys):
        star = "★ " if vkey == selected else ""
        if i < len(projektziele):
            ziel = _ZIELKATALOG.get(projektziele[i])
            if ziel:
                var_tab_labels.append(f"{star}Variante {chr(65+i)} – {ziel['icon']} {ziel['label']}")
                continue
        var_tab_labels.append(f"{star}{_tab_defaults[i]}")

    # Zähle Hinweise für Tab-Badge
    _all_issues = result.get("compliance_issues") or []
    _hinw_count = len(_all_issues)
    _hinw_label = f"⚠ Hinweise ({_hinw_count})" if _hinw_count else "✅ Hinweise"

    tab_var_a, tab_var_b, tab_var_c, tab_hinw, tab_nachh, tab_bericht, tab_ki, tab_dl = st.tabs(
        var_tab_labels + [_hinw_label, "🌱 Nachhaltigkeit", "📄 Bericht", "🤖 KI-Analyse", "⬇ Downloads"]
    )

    artifacts     = result.get("artifacts", {})
    variants_data = {v["name"]: v for v in result.get("variants", [])}

    _sp_labels = {
        "process_sequence": "⟶ Prozessfolge",
        "reserve_east":     "⟶ Ost-Reserve",
        "reserve_free":     "⟶ Erweiterungsreserve",
        "balanced_cut":     "⟶ Ausgewogen",
        "mep_central":      "⟶ MEP-Zentral",
        "compact":          "⟶ Kompakt",
    }

    _MEP_FARBEN = {
        "elektro_stark": "#FFD700",
        "lueftung_rlt": "#90EE90",
        "druckluft": "#FFA07A",
        "kaelte": "#87CEEB",
        "sprinkler": "#FF6347",
        "daten_it": "#00BFFF",
        "wasser_trinkwasser": "#4169E1",
        "abwasser": "#8B4513",
    }

    def _render_variant_tab(key: str):
        ev      = eval_map.get(key, {})
        vdata_z = variants_data.get(key)

        # Empfehlungs-Banner
        if key == selected:
            st.success(
                f"★ **Empfohlene Variante** — Gesamtscore {ev.get('gesamtscore', 0):.1f}/10 "
                f"(höchster Wert aller drei Varianten)",
                icon=None,
            )

        # Score-Zeile
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Materialfluss",   f"{ev.get('materialfluss_score', 0):.1f}/10")
        c2.metric("Erweiterbarkeit", f"{ev.get('erweiterbarkeit_score', 0):.1f}/10")
        c3.metric("Tragwerk",        f"{ev.get('tragwerk_score', 0):.1f}/10")
        c4.metric("Gesamt",          f"{ev.get('gesamtscore', 0):.1f}/10")

        sp = (result.get("split_priority_map") or {}).get(key)
        if sp:
            st.caption(f"Layout-Algorithmus: **{_sp_labels.get(sp, sp)}**")

        # Sub-Tabs
        sub_grundriss, sub_3d, sub_tech, sub_kosten = st.tabs(
            ["Grundriss", "3D-Modell", "Zonen & MEP", "Kosten"]
        )

        # ── Grundriss ──────────────────────────────────────────────────────
        with sub_grundriss:
            # Aktionszeile: Overlay-Toggle | Legende-Popover | Hinweise-Popover
            _col_tog, _col_leg, _col_warn = st.columns([5, 1, 1])
            with _col_tog:
                show_overlay = st.toggle(
                    "Funktionsgraph-Overlay",
                    key=f"graph_overlay_{key}",
                    help="Zeigt Knoten und gewichtete Kanten des Funktionsgraphen als Overlay.",
                )
            with _col_leg:
                with st.popover("📋 Legende", use_container_width=True):
                    # ── Zonen ──────────────────────────────────────────────
                    _zonen_leg = [z for z in (vdata_z or {}).get("zonen", []) if not z.get("schraffur")]
                    if _zonen_leg:
                        for _z in sorted(_zonen_leg, key=lambda x: x.get("din_kategorie", "")):
                            _color = _z.get("farbe", "#CCCCCC")
                            _delta = _z.get("delta_pct", 0.0) or 0.0
                            _delta_str = (
                                f' <span style="color:#888;font-size:0.72rem">Δ{_delta:+.0f}%</span>'
                                if abs(_delta) > 1 else ""
                            )
                            _swatch = (
                                f'<span style="display:inline-block;width:13px;height:13px;'
                                f'background:{_color};border-radius:3px;margin-right:6px;'
                                f'vertical-align:middle;border:1px solid #ccc;"></span>'
                            )
                            _area = _z.get("flaeche_m2", 0)
                            _din  = _z.get("din_kategorie", "")
                            st.markdown(
                                f'{_swatch} **{_z["name"]}** '
                                f'<span style="color:#888;font-size:0.78rem">{_din} · {_area:.0f} m²</span>'
                                f'{_delta_str}',
                                unsafe_allow_html=True,
                            )
                    else:
                        st.caption("Keine Zonen-Daten.")
                    # ── MEP-Gewerke ─────────────────────────────────────────
                    _mep_v = (result.get("mep_trassennetz") or {}).get(key) or {}
                    _aktive_gw = _mep_v.get("aktive_gewerke", [])
                    if _aktive_gw:
                        st.divider()
                        st.caption("**MEP-Gewerke (Techniktrassen)**")
                        _GW_FARBEN = {
                            "elektro_stark": "#FFD700", "daten_it": "#00BFFF",
                            "lueftung_rlt": "#90EE90", "druckluft": "#FFA07A",
                            "wasser_trinkwasser": "#4169E1", "abwasser": "#8B4513",
                            "sprinkler": "#FF6347", "kaelte": "#87CEEB",
                            "usv_notstrom": "#DA70D6",
                        }
                        _GW_LABELS = {
                            "elektro_stark": "Elektro (Starkstrom)",
                            "daten_it": "Daten / IT",
                            "lueftung_rlt": "Lüftung RLT",
                            "druckluft": "Druckluft",
                            "wasser_trinkwasser": "Wasser / Trinkwasser",
                            "abwasser": "Abwasser",
                            "sprinkler": "Sprinkler",
                            "kaelte": "Kälte",
                            "usv_notstrom": "USV / Notstrom",
                        }
                        for _gw in _aktive_gw:
                            _gc = _GW_FARBEN.get(_gw, "#AAAAAA")
                            _gl = _GW_LABELS.get(_gw, _gw)
                            _gs = (
                                f'<span style="display:inline-block;width:13px;height:13px;'
                                f'background:{_gc};border-radius:2px;margin-right:6px;'
                                f'vertical-align:middle;border:1px solid #ccc;"></span>'
                            )
                            st.markdown(f'{_gs} {_gl}', unsafe_allow_html=True)
            with _col_warn:
                _issues_v    = [i for i in _all_issues if i.get("variant") == key]
                _regelviol_v = [r for r in (ev.get("regelverletzungen") or []) if r]
                _cap_v = cap_warn
                _total_w = len(_issues_v) + len(_regelviol_v) + (1 if _cap_v else 0)
                _wlabel = f"⚠ {_total_w}" if _total_w else "✅"
                with st.popover(_wlabel, use_container_width=True):
                    if _cap_v:
                        _wt = _cap_v.get("type", "")
                        _orig = _cap_v.get("original_fp_m2", 0)
                        _cap  = _cap_v.get("capacity_m2", 0)
                        _stacked = _cap_v.get("stacked_zones", [])
                        _rf   = _cap_v.get("reduction_factor", 1.0)
                        if _wt == "stacking":
                            _adj = _cap_v.get("adjusted_fp_m2", 0)
                            st.warning(
                                f"**Flächenanpassung:** {_orig} m² > {_cap} m². "
                                f"Stapelung: {', '.join(_stacked)}. Footprint: {_adj} m².",
                                icon="⚠️",
                            )
                        elif _wt == "stacking_and_reduction":
                            st.warning(
                                f"**Flächenanpassung:** {_orig} m² > {_cap} m². "
                                f"Stapelung ({', '.join(_stacked)}) + Reduktion {_rf:.0%}.",
                                icon="⚠️",
                            )
                    # Regelverletzungen aus Evaluation (früher im PNG als roter Text)
                    if _regelviol_v:
                        for _rv in _regelviol_v:
                            st.warning(_rv, icon="⚠️")
                    # Compliance-Issues aus strukturierter Evaluation
                    if _issues_v:
                        if _regelviol_v:
                            st.divider()
                        _sev_ic = {"high": "🔴", "medium": "🟡", "low": "🔵"}
                        for _iss in _issues_v:
                            _sev = _iss.get("severity", "medium")
                            _ic  = _sev_ic.get(_sev, "⚠️")
                            st.markdown(f"{_ic} **{_iss.get('message', '')}**")
                            st.caption(_iss.get("rule_ref", ""))
                    if not _cap_v and not _issues_v and not _regelviol_v:
                        st.success("Keine Compliance-Hinweise.", icon="✅")

            png_name = f"variant_{key}.png"
            png_path = artifacts.get(png_name)

            if show_overlay:
                vdata_ov = vdata_z
                if vdata_ov and vdata_ov.get("zonen"):
                    try:
                        import tempfile
                        from app.tools.geometry import Zone as ZoneOv
                        from app.tools.drawing import zeichne_layout
                        zonen_ov = [
                            ZoneOv(
                                name=z["name"], x=z["x"], y=z["y"],
                                breite=z["breite"], tiefe=z["tiefe"],
                                flaeche_m2=z["flaeche_m2"],
                                din_kategorie=z["din_kategorie"],
                                farbe=z["farbe"], schraffur=z.get("schraffur", False),
                                floors=z.get("floors", 1),
                                planned_area_m2=z.get("planned_area_m2"),
                                delta_m2=z.get("delta_m2", 0.0),
                                delta_pct=z.get("delta_pct", 0.0),
                            )
                            for z in vdata_ov["zonen"]
                        ]
                        ev_ov = next((e for e in result.get("evaluations", []) if e.get("variante") == key), {})
                        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                            tmp_path = Path(tmp.name)
                        zeichne_layout(
                            variante_name=key,
                            beschreibung=vdata_ov.get("beschreibung", ""),
                            zonen=zonen_ov,
                            site_breite=vdata_ov.get("site_breite", 0),
                            site_tiefe=vdata_ov.get("site_tiefe", 0),
                            raster_x=vdata_ov.get("raster_x", 18.0),
                            raster_y=vdata_ov.get("raster_y", 9.0),
                            scores=ev_ov,
                            gewichtung=vdata_ov.get("gewichtung", {}),
                            output_path=tmp_path,
                            nutzungstyp=st.session_state.user_input.get("nutzungstyp", ""),
                            site_geometry=vdata_ov.get("site_geometry"),
                            topology=result.get("topology_diagram"),
                            adjacency_weights=st.session_state.adjacency_weights,
                            tragwerk_config=result.get("tragwerk_config"),
                            mep_variant_data=(result.get("mep_trassennetz") or {}).get(key),
                            building_envelope=vdata_ov.get("building_envelope"),
                            show_legend=False,
                            show_violations=False,
                            typology_key=(result.get("typology_assignments") or {}).get(key),
                        )
                        st.image(str(tmp_path), use_container_width=True)
                        tmp_path.unlink(missing_ok=True)
                    except Exception as e:
                        st.warning(f"Overlay-Rendering fehlgeschlagen: {e}")
                else:
                    st.info("Keine Zonen-Daten für Overlay verfügbar.")
            elif png_path and Path(png_path).exists():
                st.image(Image.open(png_path), use_container_width=True)
            else:
                st.warning("PNG nicht gefunden.")

        # ── 3D-Modell ──────────────────────────────────────────────────────
        with sub_3d:
            vdata = vdata_z
            if vdata and vdata.get("zonen"):
                try:
                    from app.tools.geometry import Zone
                    from app.tools.viewer3d import build_3d_figure
                    zonen_3d = [
                        Zone(
                            name=z["name"], x=z["x"], y=z["y"],
                            breite=z["breite"], tiefe=z["tiefe"],
                            flaeche_m2=z["flaeche_m2"],
                            din_kategorie=z["din_kategorie"],
                            farbe=z["farbe"], schraffur=z.get("schraffur", False),
                            floors=z.get("floors", 1),
                            planned_area_m2=z.get("planned_area_m2"),
                            delta_m2=z.get("delta_m2", 0.0),
                            delta_pct=z.get("delta_pct", 0.0),
                        )
                        for z in vdata["zonen"]
                    ]
                    fig3d = build_3d_figure(
                        zonen=zonen_3d,
                        site_geometry={
                            **(vdata.get("site_geometry") or {}),
                            "building_envelope": vdata.get("building_envelope"),
                        },
                        raster_x=vdata.get("raster_x", 18.0),
                        raster_y=vdata.get("raster_y", 9.0),
                        tragwerk_config=result.get("tragwerk_config"),
                        variante_name=key.replace("_", " "),
                        mep_variant_data=(result.get("mep_trassennetz") or {}).get(key),
                        erschliessungsgraph=(result.get("erschliessungsgraphen") or {}).get(key),
                    )
                    if st.button("3D-Ansicht im Viewer öffnen", type="primary", use_container_width=True, key=f"viewer3d_open_{key}"):
                        st.session_state[f"viewer3d_open_{key}"] = True
                    if st.session_state.get(f"viewer3d_open_{key}"):
                        _render_plotly_viewer("Gebäudeplanung · 3D-Ansicht", fig3d, key=f"viewer3d_{key}")
                    st.caption("Layer über die Legende ein-/ausblenden. "
                               "Orbit: Linksklick + Ziehen · Zoom: Mausrad · Pan: Rechtsklick")
                except Exception as e:
                    st.warning(f"3D-Viewer konnte nicht geladen werden: {e}")
            else:
                st.info("Keine Zonen-Daten für 3D-Ansicht verfügbar.")

        # ── Zonen & MEP ────────────────────────────────────────────────────
        with sub_tech:
            zonen_list = (vdata_z or {}).get("zonen", [])
            if zonen_list:
                st.markdown("**Zonen-Flächenvergleich (Soll / Ist / Δ)**")
                import pandas as pd
                rows = []
                for z in zonen_list:
                    if z.get("schraffur"):
                        continue
                    soll_m2 = z.get("flaeche_m2", 0)
                    ist_m2  = z.get("planned_area_m2") or z.get("flaeche_m2", 0)
                    delta   = z.get("delta_m2", round(ist_m2 - soll_m2, 1))
                    dpct    = z.get("delta_pct", 0)
                    rows.append({
                        "Zone":      z["name"].replace("_", " "),
                        "DIN":       z.get("din_kategorie", ""),
                        "Soll m²":   int(soll_m2) if soll_m2 else "—",
                        "Ist m²":    int(ist_m2),
                        "Δ m²":      f"{delta:+.0f}",
                        "Δ %":       f"{dpct:+.1f}",
                        "Geschosse": z.get("floors", 1),
                    })
                if rows:
                    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

            mep_data = (result.get("mep_trassennetz") or {}).get(key, {})
            if mep_data:
                st.markdown("**MEP-Anforderungen**")
                import html, pandas as pd
                aktive = mep_data.get("aktive_gewerke", [])
                if aktive:
                    tags = []
                    for gewerk in aktive:
                        color = _MEP_FARBEN.get(gewerk, "#DDDDDD")
                        text_color = "#111111" if color not in {"#4169E1", "#8B4513"} else "#FFFFFF"
                        label = html.escape(str(gewerk).replace("_", " "))
                        tags.append(
                            f'<span style="display:inline-block;background:{color};color:{text_color};'
                            f'padding:3px 8px;border-radius:999px;margin:0 6px 6px 0;'
                            f'font-size:0.78rem;font-weight:600;">{label}</span>'
                        )
                    st.markdown("".join(tags), unsafe_allow_html=True)
                mep_rows = []
                for zone in mep_data.get("zonen", []):
                    zone_name = str(zone.get("zone_name", "")).replace("_", " ")
                    for gewerk_id, gewerk_data in (zone.get("gewerke") or {}).items():
                        ergebnis = gewerk_data.get("auslegung_ergebnis")
                        einheit  = gewerk_data.get("einheit") or ""
                        auslegung = f"{ergebnis} {einheit}".strip() if ergebnis is not None else "—"
                        mep_rows.append({
                            "Zone":     zone_name,
                            "Gewerk":   gewerk_data.get("label", gewerk_id),
                            "Stufe":    gewerk_data.get("stufe", ""),
                            "Auslegung": auslegung,
                        })
                if mep_rows:
                    st.dataframe(pd.DataFrame(mep_rows), hide_index=True, use_container_width=True)

        # ── Kosten ─────────────────────────────────────────────────────────
        with sub_kosten:
            try:
                from app.tools.cost import estimate_costs
                cost_data = estimate_costs(
                    vdata_z or {},
                    result.get("structured_briefing") or {},
                )
                kc1, kc2, kc3 = st.columns(3)
                kc1.metric(
                    "Baukosten (Mitte)",
                    f"{cost_data['baukosten_mid'] / 1_000_000:.2f} Mio. €",
                    help=f"Spanne: {cost_data['baukosten_min']/1e6:.2f} – "
                         f"{cost_data['baukosten_max']/1e6:.2f} Mio. €",
                )
                kc2.metric(
                    "Gesamtkosten inkl. NK",
                    f"{cost_data['gesamtkosten_mid'] / 1_000_000:.2f} Mio. €",
                    help=f"Nebenkosten (18 %): {cost_data['nebenkosten_mid']/1e6:.2f} Mio. €",
                )
                kc3.metric(
                    "Kosten je m² BGF",
                    f"{cost_data['kosten_je_m2_bgf']:,.0f} €/m²",
                )
                import pandas as pd
                aufschl = cost_data.get("zonen_aufschluesselung", [])
                if aufschl:
                    df_cost = pd.DataFrame([
                        {
                            "Zone": r["zone"],
                            "DIN": r["din_kategorie"],
                            "Fläche m²": f"{r['flaeche_m2']:,.0f}",
                            "Kosten min €": f"{r['kosten_min']:,.0f}",
                            "Kosten mid €": f"{r['kosten_mid']:,.0f}",
                            "Kosten max €": f"{r['kosten_max']:,.0f}",
                        }
                        for r in aufschl
                    ])
                    st.dataframe(df_cost, hide_index=True, use_container_width=True)
                    st.caption(
                        "Richtwerte nach BKI / BMVBS-Kostenkennwerten (Preisstand 2024). "
                        "Keine Gewähr. Nur für Planungszwecke."
                    )
            except Exception as _cost_err:
                st.caption(f"Kostenschätzung nicht verfügbar: {_cost_err}")

    # ── Varianten-Tabs befüllen ────────────────────────────────────────────
    with tab_var_a:
        _render_variant_tab("A_Materialfluss")
    with tab_var_b:
        _render_variant_tab("B_Erweiterbarkeit")
    with tab_var_c:
        _render_variant_tab("C_Ausgewogen")

    # ── Hinweise-Tab: konsolidierte Warnmatrix ─────────────────────────────
    with tab_hinw:
        import pandas as pd

        # Kapazitäts-Warnung (gilt für alle Varianten)
        cap_warn_h = next(
            (v.get("capacity_warning") for v in variants_list if v.get("capacity_warning")), None
        )
        if cap_warn_h:
            wt = cap_warn_h.get("type", "")
            orig_h = cap_warn_h.get("original_fp_m2", 0)
            cap_h  = cap_warn_h.get("capacity_m2", 0)
            stacked_h = cap_warn_h.get("stacked_zones", [])
            rf_h   = cap_warn_h.get("reduction_factor", 1.0)
            if wt == "stacking":
                adj_h = cap_warn_h.get("adjusted_fp_m2", 0)
                st.warning(
                    f"**Flächenanpassung:** Briefing-Footprint {orig_h} m² überschritt "
                    f"Baufeld-Kapazität {cap_h} m². Automatische Stapelung für: "
                    f"{', '.join(stacked_h)}. Neuer Footprint: {adj_h} m².",
                    icon="⚠️",
                )
            elif wt == "stacking_and_reduction":
                st.warning(
                    f"**Flächenanpassung:** Briefing-Footprint {orig_h} m² überschritt "
                    f"Baufeld-Kapazität {cap_h} m². Stapelung ({', '.join(stacked_h)}) + "
                    f"Reduktionsfaktor {rf_h:.0%} auf alle Flächen angewendet.",
                    icon="⚠️",
                )

        st.markdown("#### Compliance-Matrix")

        _sev_icon = {"high": "🔴", "medium": "🟡", "low": "🔵"}
        _var_short = {
            "A_Materialfluss":  "Var. A",
            "B_Erweiterbarkeit": "Var. B",
            "C_Ausgewogen":     "Var. C",
        }

        if _all_issues:
            # Zeilen: eindeutige Prüfpunkte (rule_ref + zone + action)
            seen_keys: list[tuple] = []
            rows_matrix = []
            for issue in _all_issues:
                key = (issue.get("rule_ref", ""), issue.get("zone") or "", issue.get("action", ""))
                if key not in seen_keys:
                    seen_keys.append(key)

            for key in seen_keys:
                rule_ref, zone, action = key
                # Beschreibung aus dem ersten passenden Issue
                sample = next(
                    (i for i in _all_issues
                     if i.get("rule_ref") == rule_ref
                     and (i.get("zone") or "") == zone
                     and i.get("action") == action),
                    {},
                )
                label_parts = []
                if zone:
                    label_parts.append(zone)
                label_parts.append(sample.get("message", rule_ref)[:60])
                pruefpunkt = " · ".join(label_parts)

                row = {"Prüfpunkt": pruefpunkt, "Regelreferenz": rule_ref}
                for vk, vs in _var_short.items():
                    matching = [
                        i for i in _all_issues
                        if i.get("variant") == vk
                        and i.get("rule_ref") == rule_ref
                        and (i.get("zone") or "") == zone
                        and i.get("action") == action
                    ]
                    if matching:
                        sev = matching[0].get("severity", "medium")
                        row[vs] = f"{_sev_icon.get(sev, '⚠️')} {sev.upper()}"
                    else:
                        row[vs] = "✅"
                rows_matrix.append(row)

            df_matrix = pd.DataFrame(rows_matrix)
            st.dataframe(df_matrix, hide_index=True, use_container_width=True)

            # Legende
            st.caption(
                "🔴 HIGH – kritisch · 🟡 MEDIUM – zu prüfen · 🔵 LOW – Hinweis · ✅ kein Befund"
            )

            # Detailliste nach Variante
            st.markdown("#### Details nach Variante")
            det_a, det_b, det_c = st.columns(3)
            for col, vkey, vshort in zip(
                [det_a, det_b, det_c],
                ["A_Materialfluss", "B_Erweiterbarkeit", "C_Ausgewogen"],
                ["Var. A", "Var. B", "Var. C"],
            ):
                issues_v = [i for i in _all_issues if i.get("variant") == vkey]
                with col:
                    ev_v = eval_map.get(vkey, {})
                    st.markdown(
                        f"**{vshort}** — {ev_v.get('gesamtscore', 0):.1f}/10"
                        + (" ★" if vkey == selected else "")
                    )
                    if issues_v:
                        for iss in issues_v:
                            sev = iss.get("severity", "medium")
                            icon = _sev_icon.get(sev, "⚠️")
                            msg  = iss.get("message", "")
                            ref  = iss.get("rule_ref", "")
                            st.markdown(
                                f"{icon} **{msg}**  \n"
                                f"<small style='color:#888'>{ref}</small>",
                                unsafe_allow_html=True,
                            )
                    else:
                        st.success("Keine Compliance-Hinweise.", icon="✅")
        else:
            st.success(
                "Alle Varianten sind regelkonform — keine Compliance-Hinweise.", icon="✅"
            )

    # ── Nachhaltigkeits-Tab ─────────────────────────────────────────────────
    with tab_nachh:
        try:
            from app.tools.sustainability import calc_pv, calc_co2, building_roof_area

            briefing_n   = result.get("structured_briefing") or {}
            bgf_n        = float(briefing_n.get("bgf_gesamt", 0))
            nutztyp_n    = briefing_n.get("nutzungstyp", "Produktion")

            # Dachfläche aus empfohlener Variante (genauer als reine BGF-Schätzung)
            sel_vdata    = variants_data.get(selected)
            roof_m2      = building_roof_area(sel_vdata) if sel_vdata else bgf_n * 0.85

            pv  = calc_pv(roof_m2)
            co2 = calc_co2(bgf_n, nutztyp_n, pv_annual_kwh=pv["annual_kwh"])

            st.caption(
                f"Basis: Empfohlene Variante **{selected.replace('_', ' ')}** · "
                f"BGF {bgf_n:,.0f} m² · Dachfläche {roof_m2:,.0f} m² · {nutztyp_n}"
            )
            st.markdown("---")

            # ── PV-Anlage ──────────────────────────────────────────────────
            st.markdown("#### Photovoltaik-Dachanlage")
            pv_c1, pv_c2, pv_c3, pv_c4 = st.columns(4)
            pv_c1.metric("Installierte Leistung",
                         f"{pv['kwp_installed']:,.0f} kWp",
                         help=f"Nutzbare PV-Fläche: {pv['pv_area_m2']:,.0f} m² (60 % des Dachs)")
            pv_c2.metric("Jahresertrag",
                         f"{pv['annual_kwh'] / 1000:,.0f} MWh/Jahr",
                         help=f"{pv['annual_kwh_m2']} kWh/m² Dach · 960 kWh/kWp Deutschlandmittel")
            pv_c3.metric("CO₂-Einsparung",
                         f"{pv['co2_offset_kg_year'] / 1000:,.0f} t/Jahr",
                         help=f"über 30 Jahre: {pv['co2_offset_t_life']:,.0f} t CO₂e")
            pv_c4.metric("Amortisation",
                         f"{pv['payback_years']:.1f} Jahre",
                         help=f"Investition ~{pv['invest_eur'] / 1000:,.0f} k€ · "
                              f"Einsparung {pv['annual_savings_eur']:,.0f} €/Jahr")

            pv_d1, pv_d2 = st.columns(2)
            with pv_d1:
                st.markdown(
                    f"**Eigenverbrauch:** {pv['self_use_kwh'] / 1000:,.0f} MWh/Jahr "
                    f"*(60 % · Gutschrift {pv['self_use_kwh'] * 0.22:,.0f} €/Jahr)*  \n"
                    f"**Einspeisung:** {pv['feed_kwh'] / 1000:,.0f} MWh/Jahr "
                    f"*(40 % · Vergütung {pv['feed_kwh'] * 0.082:,.0f} €/Jahr)*"
                )
            with pv_d2:
                pv_pct = min(pv['annual_kwh'] / (float(briefing_n.get('bgf_gesamt', 1)) *
                             115) * 100, 100) if bgf_n else 0
                st.markdown(
                    f"**Deckungsquote:** {pv_pct:.0f} % des betrieblichen Strombedarfs  \n"
                    f"*(Annahme: 60 % Eigenverbrauch, kein Speicher)*"
                )
            st.caption(
                "Fraunhofer ISE 2024 · EEG 2024 · Modullebensdauer 30 Jahre · "
                "Bifaziale Module, 10° Südneigung, 0,5 %/Jahr Degradation"
            )

            st.markdown("---")

            # ── CO2-Bilanz ─────────────────────────────────────────────────
            st.markdown("#### CO₂-Bilanz (Lebenszyklus)")
            co2_c1, co2_c2, co2_c3, co2_c4 = st.columns(4)
            co2_c1.metric("Graue Energie (Bau)",
                          f"{co2['embodied_co2_t']:,.0f} t CO₂e",
                          help=f"{co2['embodied_kg_m2']} kg CO₂e/m² BGF · "
                               f"Quelle: DGNB/ÖkoBauDat 2024")
            co2_c2.metric("Betrieb (Strom, jährl.)",
                          f"{co2['annual_op_co2_t']:,.1f} t CO₂e/Jahr",
                          help=f"{co2['annual_op_kwh_m2']} kWh/m²·Jahr · "
                               f"0,38 kg CO₂/kWh DE Netzmix")
            co2_c3.metric("PV-Gutschrift",
                          f"−{co2['pv_offset_co2_t']:,.1f} t CO₂e/Jahr",
                          delta=f"−{co2['pv_offset_co2_t']:,.1f} t",
                          delta_color="normal")
            co2_c4.metric("Netto-Betrieb",
                          f"{co2['net_annual_co2_t']:,.1f} t CO₂e/Jahr",
                          delta=f"−{co2['pv_offset_co2_t']:,.1f} t durch PV",
                          delta_color="normal")

            st.markdown(
                f"**Lebenszyklusbilanz ({co2['lifespan_years']} Jahre):**  \n"
                f"Graue Energie **{co2['embodied_co2_t']:,.0f} t** + "
                f"Betrieb **{co2['lifecycle_op_co2_t']:,.0f} t** = "
                f"**{co2['lifecycle_total_co2_t']:,.0f} t CO₂e gesamt**  \n"
                f"Spezifischer GWP: **{co2['gwp_kg_m2_year']:.1f} kg CO₂e/(m²·Jahr)**"
            )

            # Einordnung nach DGNB-Benchmarks Nutzungsprofil 14 (Produktion/Industrie)
            gwp = co2["gwp_kg_m2_year"]
            if gwp < 10:
                bench_label, bench_color = "DGNB Platin (<10 kg)", "#2E7D32"
            elif gwp < 15:
                bench_label, bench_color = "DGNB Gold (<15 kg)", "#F9A825"
            elif gwp < 23:
                bench_label, bench_color = "DGNB Silber (<23 kg)", "#546E7A"
            else:
                bench_label, bench_color = "Unterhalb DGNB-Silber", "#C62828"

            st.markdown(
                f'<span style="display:inline-block;background:{bench_color};color:#fff;'
                f'padding:4px 12px;border-radius:6px;font-size:0.85rem;font-weight:600;">'
                f'GWP-Einordnung: {bench_label}</span>',
                unsafe_allow_html=True,
            )
            st.caption(
                "Richtwerte nach DGNB Nutzungsprofil 14 (Produktionsgebäude) / "
                "BNB Industriebau · UBA Emissionsfaktor Strom 0,38 kg CO₂e/kWh (2024) · "
                "Graue Energie nach ÖkoBauDat / DGNB-Steckbrief. Keine Gewähr, nur Planungsindikation."
            )

        except Exception as _nachh_err:
            st.warning(f"Nachhaltigkeitsberechnung nicht verfügbar: {_nachh_err}")

    # ── Bericht-Tab ────────────────────────────────────────────────────────
    with tab_bericht:
        if result.get("rule_change_summary"):
            st.info(f"Regelwerk: {result['rule_change_summary']}", icon=None)

        report_md = result.get("report_markdown", "")

        def _split_at_heading(md: str, heading: str) -> tuple[str, str]:
            for sep in [f"\n---\n\n## {heading}", f"\n\n## {heading}", f"\n## {heading}"]:
                if sep in md:
                    before, _, rest = md.partition(sep)
                    return before.rstrip(), f"## {heading}" + rest
            return md, ""

        # Trenne bekannte technische Abschnitte vom narrativen Hauptteil
        md_no_wp, whitebox_md  = _split_at_heading(report_md,  "Entscheidungsprotokoll")
        md_no_mep, mep_md      = _split_at_heading(md_no_wp,   "MEP-Konzept")

        # Qualitative Analyse aus Hauptteil entfernen — steht im KI-Analyse-Tab
        if "\n## Qualitative Analyse" in md_no_mep:
            md_no_mep = md_no_mep.split("\n## Qualitative Analyse")[0].rstrip()

        bericht_sub_labels = ["Planungsempfehlung"]
        if mep_md:
            bericht_sub_labels.append("MEP-Konzept")
        if whitebox_md:
            bericht_sub_labels.append("Entscheidungsprotokoll")

        if len(bericht_sub_labels) > 1:
            bericht_sub_tabs = st.tabs(bericht_sub_labels)
            with bericht_sub_tabs[0]:
                st.markdown(md_no_mep)
            idx = 1
            if mep_md:
                with bericht_sub_tabs[idx]:
                    st.markdown(mep_md)
                idx += 1
            if whitebox_md:
                with bericht_sub_tabs[idx]:
                    st.markdown(whitebox_md)
        else:
            st.markdown(md_no_mep)

    # ── KI-Analyse-Tab ─────────────────────────────────────────────────────
    with tab_ki:
        llm_analyse = result.get("llm_analyse")
        if llm_analyse:
            st.markdown(llm_analyse)
        else:
            st.info(
                "ℹ️ Kein OpenAI API-Key gesetzt – KI-Analyse nicht verfügbar. "
                "OPENAI_API_KEY in der .env setzen, um die qualitative Analyse zu aktivieren.",
                icon=None,
            )

    # ── Downloads-Tab ──────────────────────────────────────────────────────
    with tab_dl:
        for key in variante_keys:
            label_short = key.replace("_", " ")
            st.markdown(f"**{label_short}**")
            dl_cols = st.columns(4)

            dm_path = artifacts.get(f"variant_{key}.3dm")
            if dm_path and Path(dm_path).exists():
                with dl_cols[0]:
                    with open(dm_path, "rb") as fh:
                        st.download_button(
                            "📦 3DM (Rhino)",
                            data=fh,
                            file_name=f"variant_{key}.3dm",
                            mime="application/octet-stream",
                            key=f"dl_3dm_{key}",
                            use_container_width=True,
                        )

            json_path = artifacts.get(f"zones_{key}.json")
            if json_path and Path(json_path).exists():
                with dl_cols[1]:
                    with open(json_path, "rb") as fh:
                        st.download_button(
                            "📋 Zonen-JSON",
                            data=fh,
                            file_name=f"zones_{key}.json",
                            mime="application/json",
                            key=f"dl_json_{key}",
                            use_container_width=True,
                        )

            vdata_dl = variants_data.get(key)
            if vdata_dl and vdata_dl.get("zonen"):
                with dl_cols[2]:
                    if st.button("📄 PDF-Lageplan", key=f"btn_pdf_{key}", use_container_width=True):
                        try:
                            import tempfile
                            from app.tools.geometry import Zone as ZonePDF
                            from app.tools.drawing import zeichne_lageplan_pdf
                            ev_pdf = next(
                                (e for e in result.get("evaluations", []) if e.get("variante") == key), {}
                            )
                            zonen_pdf = [
                                ZonePDF(
                                    name=z["name"], x=z["x"], y=z["y"],
                                    breite=z["breite"], tiefe=z["tiefe"],
                                    flaeche_m2=z["flaeche_m2"],
                                    din_kategorie=z["din_kategorie"],
                                    farbe=z["farbe"], schraffur=z.get("schraffur", False),
                                    floors=z.get("floors", 1),
                                    planned_area_m2=z.get("planned_area_m2"),
                                    delta_m2=z.get("delta_m2", 0.0),
                                    delta_pct=z.get("delta_pct", 0.0),
                                )
                                for z in vdata_dl["zonen"]
                            ]
                            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                                tmp_path = Path(tmp.name)
                            pdf_path = zeichne_lageplan_pdf(
                                variante_name=key,
                                beschreibung=vdata_dl.get("beschreibung", ""),
                                zonen=zonen_pdf,
                                site_breite=vdata_dl.get("site_breite", 0),
                                site_tiefe=vdata_dl.get("site_tiefe", 0),
                                raster_x=vdata_dl.get("raster_x", 18.0),
                                raster_y=vdata_dl.get("raster_y", 9.0),
                                scores=ev_pdf,
                                gewichtung=vdata_dl.get("gewichtung", {}),
                                output_path=tmp_path,
                                nutzungstyp=st.session_state.user_input.get("nutzungstyp", ""),
                                site_geometry=vdata_dl.get("site_geometry"),
                                tragwerk_config=result.get("tragwerk_config"),
                                mep_variant_data=(result.get("mep_trassennetz") or {}).get(key),
                                building_envelope=vdata_dl.get("building_envelope"),
                                projektname=st.session_state.user_input.get("projektname", "AID Demo"),
                                plannummer=f"L-{key[:1]}-001",
                            )
                            with open(pdf_path, "rb") as fh:
                                st.download_button(
                                    "⬇ Lageplan PDF",
                                    data=fh.read(),
                                    file_name=f"lageplan_{key}.pdf",
                                    mime="application/pdf",
                                    key=f"dl_pdf_{key}",
                                )
                            tmp_path.unlink(missing_ok=True)
                            pdf_path.unlink(missing_ok=True)
                        except Exception as e:
                            st.warning(f"PDF-Erzeugung fehlgeschlagen: {e}")

                with dl_cols[3]:
                    if st.button("📐 DXF-Export", key=f"btn_dxf_{key}", use_container_width=True):
                        try:
                            from app.tools.dxf_export import export_layout_to_dxf
                            dxf_bytes = export_layout_to_dxf(
                                variant=vdata_dl,
                                site_geometry=vdata_dl.get("site_geometry") or {},
                                briefing=result.get("structured_briefing") or {},
                            )
                            st.download_button(
                                "⬇ DXF (AutoCAD)",
                                data=dxf_bytes,
                                file_name=f"layout_{key}.dxf",
                                mime="application/dxf",
                                key=f"dl_dxf_{key}",
                            )
                        except Exception as e:
                            st.warning(f"DXF-Export fehlgeschlagen: {e}")

            gh_path_art = artifacts.get(f"gh_result_{key}.json")
            if gh_path_art and Path(gh_path_art).exists():
                st.caption("✅ GH-Geometrie generiert")

            st.divider()

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

    # Neue Berechnung + Prozessplanung
    st.markdown("---")
    _nav_col1, _nav_col2 = st.columns([1, 2])
    with _nav_col1:
        if st.button("← Neue Berechnung", use_container_width=True):
            for _k in ("schritt", "result", "user_input", "site_geometry", "building_parcel",
                       "building_parcels", "selected_building_parcel_id",
                       "custom_gewichtungen", "rule_overrides", "rule_change_request",
                       "projektziele", "adjacency_weights", "_last_saved_run_id",
                       "masterplan", "pp_result"):
                st.session_state[_k] = None
            st.session_state.schritt = 0
            st.rerun()
    with _nav_col2:
        # Prozessplanung nur für Produktionsnutzung
        _briefing_pp = (result.get("structured_briefing") or {})
        _nutztyp_pp  = _briefing_pp.get("nutzungstyp", "")
        if _nutztyp_pp == "Produktion":
            if st.button(
                "⚙ Weiter zur Prozessplanung →",
                type="primary",
                use_container_width=True,
                help="Maschinenlayout und Materialfluss für die Produktionszone planen",
            ):
                st.session_state.schritt = 7
                st.rerun()
        else:
            st.info("Prozessplanung (Schritt 7) ist nur für Nutzungstyp *Produktion* verfügbar.")


# ---------------------------------------------------------------------------
# Schritt 7: Prozessplanung
# ---------------------------------------------------------------------------

def schritt_prozessplanung():
    """Sprint Q: Maschinenlayout + Materialfluss-Sankey innerhalb der Produktionszone."""
    from app.agents.process import process_layout_agent
    from app.tools.process_viz import build_sankey_figure
    from app.tools.svg_process import process_layout_to_svg, utilization_to_svg

    st.markdown('<span class="phase-badge">3.1</span> **Prozessplanung — Maschinenlayout**',
                unsafe_allow_html=True)
    st.caption(
        "Eigenständiger Planungsbaustein 3: Prozessplanung innerhalb einer Funktionsfläche. "
        "Es stehen ein KI-/regelgestützter Vorschlag und ein adaptiver Transfer eines Vorgabelayouts zur Verfügung."
    )

    result = st.session_state.get("result") or {}
    try:
        from app.tools.persistence import get_planning_stand, list_planning_stands
        building_stands = list_planning_stands(_current_user, "building_plan", limit=50)
    except Exception:
        get_planning_stand = None
        building_stands = []

    if building_stands:
        source_options = ["Aktuelle Gebäudeplanung"] if result else []
        source_options.extend([str(s["id"]) for s in building_stands])
        selected_bp = st.selectbox(
            "Gebäudeplanung als Grundlage",
            options=source_options,
            format_func=lambda v: "Aktuelle Gebäudeplanung" if v == "Aktuelle Gebäudeplanung" else next(
                f"#{s['id']} · {s['label']}" for s in building_stands if str(s["id"]) == v
            ),
            key="pp_building_plan_source",
        )
        if selected_bp != "Aktuelle Gebäudeplanung" and get_planning_stand:
            loaded = get_planning_stand(int(selected_bp))
            if loaded and loaded.get("payload"):
                result = loaded["payload"]
                st.session_state.result = result

    variants_data = {v["name"]: v for v in result.get("variants", [])}
    variante_keys = [k for k in ["A_Materialfluss", "B_Erweiterbarkeit", "C_Ausgewogen"] if k in variants_data]
    if not variante_keys:
        st.info("Keine Gebäudeplanung mit auswertbaren Flächen gefunden. Wähle oder erstelle zuerst Baustein 2.", icon=None)
        return

    col_back, col_spacer = st.columns([1, 4])
    with col_back:
        if st.button("← Zurück zu Ergebnissen", use_container_width=True):
            st.session_state.schritt = 6
            st.rerun()

    st.divider()

    # ── Konfiguration ──────────────────────────────────────────────────────────
    with st.expander("⚙ Konfiguration", expanded=True):
        col_cfg1, col_cfg2 = st.columns(2)

        with col_cfg1:
            # Welche Produktionszone auswählen?
            selected_variant = st.selectbox(
                "Basis-Layoutvariante",
                options=variante_keys,
                format_func=lambda k: k.replace("_", " "),
                key="pp_variant",
            )

            # Produktionszone aus der Variante extrahieren
            vdata = variants_data.get(selected_variant, {})
            zonen = vdata.get("zonen", [])
            prod_zonen = [
                z for z in zonen
                if z.get("din_kategorie") in ("NUF3", "NUF 3") or
                   "produktion" in z.get("name", "").lower()
            ]
            zone_opts = [z["name"] for z in prod_zonen] if prod_zonen else ["Produktion (Standard)"]
            selected_zone_name = st.selectbox(
                "Produktionszone",
                options=zone_opts,
                key="pp_zone",
            )

            # Abmessungen der Zone
            zone_obj = next((z for z in prod_zonen if z["name"] == selected_zone_name), None)
            if zone_obj:
                zone_breite = float(zone_obj.get("breite") or zone_obj.get("breite_m") or 40.0)
                zone_tiefe  = float(zone_obj.get("tiefe") or zone_obj.get("tiefe_m") or 75.0)
            else:
                zone_breite = 40.0
                zone_tiefe  = 75.0

            st.caption(f"Zonenabmessungen: **{zone_breite:.0f} × {zone_tiefe:.0f} m**")

        with col_cfg2:
            # Planungsweg: Vorschlag oder adaptiver Transfer
            pp_mode_label = st.radio(
                "Planungsweg",
                options=["KI-gestützter Vorschlag", "Adaptiver Transfer Vorgabelayout"],
                horizontal=False,
                key="pp_mode_label",
            )
            pp_mode = "adaptive_transfer" if pp_mode_label.startswith("Adaptiver") else "ai_suggestion"

            # Maschinenpark: Demo oder Custom
            park_mode = st.radio(
                "Maschinenpark",
                options=["Demo (Fertigung Metallbau)", "Eigene Eingabe"],
                horizontal=True,
                key="pp_park_mode",
            )

    # ── Maschinenpark-Editor ────────────────────────────────────────────────────
    if park_mode == "Demo (Fertigung Metallbau)":
        maschinenpark = DEMO_MASCHINENPARK
        st.caption(f"Demo-Maschinenpark: **{len(maschinenpark)} Maschinen** in 5 Prozessschritten")
    else:
        st.markdown("**Maschinenpark definieren** (eine Zeile = eine Maschinen*gruppe*)")

        # Tabellen-Editor
        import pandas as pd

        default_df = pd.DataFrame([{
            "ID":        m["id"],
            "Name":      m["name"],
            "Schritt":   m["schritt"],
            "Breite [m]":m["breite_m"],
            "Tiefe [m]": m["tiefe_m"],
            "Anzahl":    m["anzahl"],
            "Takt [s]":  m["taktzeit_s"],
            "Kategorie": m["kategorie"],
        } for m in DEMO_MASCHINENPARK])

        edited_df = st.data_editor(
            default_df,
            num_rows="dynamic",
            use_container_width=True,
            key="pp_machine_editor",
            column_config={
                "Kategorie": st.column_config.SelectboxColumn(
                    options=["Bearbeitung", "Montage", "Prüfung", "Lager", "Transport"]
                )
            },
        )

        _FARBEN_KATEGORIEN = {
            "Bearbeitung": "#2E86AB", "Montage": "#C73E1D",
            "Prüfung": "#3B1F2B", "Lager": "#8B9E6F", "Transport": "#F18F01",
        }
        maschinenpark = []
        for _, row in edited_df.iterrows():
            try:
                maschinenpark.append({
                    "id":         str(row["ID"]),
                    "name":       str(row["Name"]),
                    "schritt":    int(row["Schritt"]),
                    "breite_m":   float(row["Breite [m]"]),
                    "tiefe_m":    float(row["Tiefe [m]"]),
                    "anzahl":     int(row["Anzahl"]),
                    "taktzeit_s": float(row["Takt [s]"]),
                    "kategorie":  str(row.get("Kategorie", "Bearbeitung")),
                    "farbe":      _FARBEN_KATEGORIEN.get(str(row.get("Kategorie", "")), "#888888"),
                })
            except Exception:
                pass

    reference_layout = None
    if pp_mode == "adaptive_transfer":
        st.markdown("**Vorgabelayout übertragen**")
        col_ref1, col_ref2 = st.columns(2)
        with col_ref1:
            ref_breite = st.number_input(
                "Breite Vorgabefläche [m]",
                min_value=5.0,
                value=float(max(zone_breite, 40.0)),
                step=1.0,
                key="pp_ref_breite",
            )
        with col_ref2:
            ref_tiefe = st.number_input(
                "Tiefe Vorgabefläche [m]",
                min_value=5.0,
                value=float(max(zone_tiefe, 75.0)),
                step=1.0,
                key="pp_ref_tiefe",
            )

        import pandas as pd
        ref_rows = []
        x_cursor = 2.0
        y_cursor = 2.0
        last_step = None
        for m in maschinenpark:
            step = int(m.get("schritt", 1))
            if last_step is not None and step != last_step:
                x_cursor = 2.0
                y_cursor += 8.0
            ref_rows.append({
                "ID": m.get("id"),
                "Name": m.get("name"),
                "Schritt": step,
                "X [m]": x_cursor,
                "Y [m]": y_cursor,
                "Breite [m]": float(m.get("breite_m", 3.0)),
                "Tiefe [m]": float(m.get("tiefe_m", 2.0)),
            })
            x_cursor += float(m.get("breite_m", 3.0)) + 2.0
            last_step = step

        ref_df = st.data_editor(
            pd.DataFrame(ref_rows),
            use_container_width=True,
            num_rows="dynamic",
            key="pp_reference_layout_editor",
        )
        reference_layout = {
            "zone_breite_m": float(ref_breite),
            "zone_tiefe_m": float(ref_tiefe),
            "maschinen": [
                {
                    "id": str(row["ID"]),
                    "name": str(row["Name"]),
                    "schritt": int(row["Schritt"]),
                    "x": float(row["X [m]"]),
                    "y": float(row["Y [m]"]),
                    "breite_m": float(row["Breite [m]"]),
                    "tiefe_m": float(row["Tiefe [m]"]),
                }
                for _, row in ref_df.iterrows()
            ],
        }

    # ── Berechnung ─────────────────────────────────────────────────────────────
    if st.button("⚙ Prozesslayout berechnen", type="primary", use_container_width=False, key="pp_calc"):
        spinner_text = "Vorgabelayout wird adaptiv übertragen …" if pp_mode == "adaptive_transfer" else "Prozesslayout-Vorschlag wird berechnet …"
        with st.spinner(spinner_text):
            pp_state: dict = {
                "process_input": {
                    "mode":          pp_mode,
                    "zone_name":     selected_zone_name,
                    "zone_breite_m": zone_breite,
                    "zone_tiefe_m":  zone_tiefe,
                    "maschinenpark": maschinenpark,
                    "reference_layout": reference_layout,
                }
            }
            pp_result = process_layout_agent(pp_state)
            process_layout = pp_result.get("process_layout", {})
            st.session_state["pp_result"] = process_layout
            if _current_role in ("planner", "admin"):
                try:
                    from app.tools.persistence import save_planning_stand as _save_stand

                    _source = st.session_state.get("pp_building_plan_source", "Aktuelle Gebäudeplanung")
                    _parent_id = int(_source) if str(_source).isdigit() else st.session_state.get("_last_building_plan_stand_id")
                    _label = f"Prozessplanung · {selected_zone_name} · {process_layout.get('mode_label', pp_mode)}"
                    st.session_state["_last_process_plan_stand_id"] = _save_stand(
                        _current_user,
                        "process_plan",
                        _label,
                        {
                            "process_layout": process_layout,
                            "building_plan_source": _source,
                            "zone_name": selected_zone_name,
                            "mode": pp_mode,
                        },
                        parent_id=_parent_id,
                        source_ref=str(selected_zone_name),
                    )
                except Exception as _e:
                    st.caption(f"Prozessplanung konnte nicht gespeichert werden: {_e}")
        st.rerun()

    # ── Ergebnisse ─────────────────────────────────────────────────────────────
    pp_layout = st.session_state.get("pp_result")

    if not pp_layout:
        st.info("Konfiguration wählen und **Maschinenlayout berechnen** drücken.")
        return

    kpis = pp_layout.get("kpis") or {}

    # KPI-Metriken
    kc1, kc2, kc3, kc4 = st.columns(4)
    kc1.metric("Durchsatz", f"{kpis.get('durchsatz_teile_pro_schicht', '—')} T/Schicht")
    kc2.metric("Engpass", f"Schritt {kpis.get('engpass_schritt', '—')}")
    kc3.metric("Materialflussweg", f"{kpis.get('materialflussweg_m', 0):.0f} m")
    auslastung_werte = list((kpis.get("auslastung_je_schritt") or {}).values())
    avg_ausl = sum(auslastung_werte) / len(auslastung_werte) if auslastung_werte else 0
    kc4.metric("Ø Auslastung", f"{avg_ausl:.0f}%")

    transfer = pp_layout.get("transfer") or {}
    if transfer:
        if transfer.get("status") == "transferred":
            st.info(
                "Adaptiver Transfer: "
                f"Skalierung X {transfer.get('scale_x')} / Y {transfer.get('scale_y')} | "
                f"Formabweichung {transfer.get('aspect_ratio_change_pct')} % | "
                f"Korrekturen {len(transfer.get('violations') or [])}"
            )
        else:
            st.warning(transfer.get("hinweis", "Adaptiver Transfer konnte nicht vollständig angewendet werden."))

    st.divider()

    # Tabs: Layout | Sankey | Auslastung | Daten
    tab_layout, tab_sankey, tab_auslast, tab_daten = st.tabs([
        "📐 Maschinenlayout", "🔀 Materialfluss-Sankey",
        "📊 Auslastung", "📋 Maschinendaten",
    ])

    with tab_layout:
        st.caption(
            f"Zone: **{pp_layout.get('zone_name')}** | "
            f"{pp_layout.get('zone_breite_m'):.0f} × {pp_layout.get('zone_tiefe_m'):.0f} m | "
            f"{len(pp_layout.get('maschinen', []))} Maschineninstanzen in "
            f"{len(pp_layout.get('strips', []))} Strips"
        )
        if st.button("Maschinenlayout im SVG-Viewer öffnen", type="primary", use_container_width=True, key="pp_layout_svg_open_btn"):
            st.session_state["pp_layout_svg_open"] = True
        if st.session_state.get("pp_layout_svg_open"):
            _render_svg_viewer("Prozessplanung · Maschinenlayout", process_layout_to_svg(pp_layout), key="pp_layout_svg")

    with tab_sankey:
        fig_sankey = build_sankey_figure(pp_layout)
        if st.button("Materialfluss-Sankey im Viewer öffnen", type="primary", use_container_width=True, key="pp_sankey_open_btn"):
            st.session_state["pp_sankey_open"] = True
        if st.session_state.get("pp_sankey_open"):
            _render_plotly_viewer("Prozessplanung · Materialfluss-Sankey", fig_sankey, key="pp_sankey")

    with tab_auslast:
        if st.button("Auslastung im SVG-Viewer öffnen", type="primary", use_container_width=True, key="pp_util_svg_open_btn"):
            st.session_state["pp_util_svg_open"] = True
        if st.session_state.get("pp_util_svg_open"):
            _render_svg_viewer("Prozessplanung · Auslastung", utilization_to_svg(pp_layout), key="pp_util_svg")

        # Auslastungs-Tabelle
        auslastung_dict = kpis.get("auslastung_je_schritt") or {}
        kap_dict        = kpis.get("kapazitaet_je_schritt") or {}
        engpass_s       = str(kpis.get("engpass_schritt", ""))
        tbl_rows = []
        for s_str in sorted(auslastung_dict.keys(), key=lambda x: int(x)):
            tbl_rows.append({
                "Schritt": int(s_str),
                "Auslastung (%)": auslastung_dict[s_str],
                "Kapazität (T/Schicht)": kap_dict.get(s_str, "—"),
                "Engpass": "⚠ Ja" if s_str == engpass_s else "—",
            })
        if tbl_rows:
            import pandas as pd
            st.dataframe(pd.DataFrame(tbl_rows), use_container_width=True, hide_index=True)

    with tab_daten:
        maschinen = pp_layout.get("maschinen") or []
        if maschinen:
            import pandas as pd
            df_m = pd.DataFrame([{
                "ID":           m["id"],
                "Name":         m["name"],
                "Schritt":      m["schritt"],
                "Instanz":      m.get("instance_idx", 0) + 1,
                "X [m]":        m["x"],
                "Y [m]":        m["y"],
                "Breite [m]":   m["breite_m"],
                "Tiefe [m]":    m["tiefe_m"],
                "Takt [s]":     m.get("taktzeit_s", "—"),
                "Kategorie":    m.get("kategorie", "—"),
            } for m in maschinen])
            st.dataframe(df_m, use_container_width=True, hide_index=True)

    # ── Determinismus-Hinweis ──────────────────────────────────────────────────
    st.caption(f"Planungsweg: {pp_layout.get('mode_label', 'Prozesslayout')}.")


# ---------------------------------------------------------------------------
# Fortschrittsanzeige & Router
# ---------------------------------------------------------------------------

PLANUNGSBAUSTEINE = [
    ("Masterplanung", [
        (1, "1.1", "Grundstück / Kataster", "kataster"),
        (0, "1.2", "Baurecht", "baurecht"),
        (0, "1.3", "Verkehr & Infrastruktur", "infra"),
        (0, "1.4", "Planungsanforderungen", "anforderungen"),
    ]),
    ("Gebäudeplanung", [
        (20, "2.0", "Parzelle wählen", None),
        (2, "2.1", "Nutzung & Flächen", None),
        (3, "2.2", "Funktionsgraph", None),
        (4, "2.3", "Regelwerk", None),
        (5, "2.4", "Projektziele", None),
        (6, "2.5", "Varianten & Bewertung", None),
    ]),
    ("Prozessplanung", [(7, "3.1", "Fläche / Raum wählen & Prozesslayout", None)]),
]
_PHASE_ORDER = {1: 0, 0: 1, 20: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 7, 7: 8}

def _phase_icon(step_id: int, mp_subphase: str | None = None) -> str:
    if mp_subphase:
        if _phase_active(step_id, mp_subphase):
            return "●"
        if mp_subphase in st.session_state.get("mp_completed_subphases", []):
            return "✅"
        return "○"
    current = int(st.session_state.schritt or 0)
    current_order = _PHASE_ORDER.get(current, current)
    step_order = _PHASE_ORDER.get(step_id, step_id)
    if step_order < current_order:
        return "✅"
    if step_order == current_order:
        return "▶"
    return "○"

def _phase_disabled(step_id: int) -> bool:
    if step_id in (3, 4, 5) and not st.session_state.get("user_input"):
        return True
    if step_id == 6 and not st.session_state.get("result"):
        return True
    if step_id == 7 and not st.session_state.get("result"):
        return True
    return False

def _phase_active(step_id: int, mp_subphase: str | None = None) -> bool:
    current = int(st.session_state.schritt or 0)
    active = _PHASE_ORDER.get(step_id, step_id) == _PHASE_ORDER.get(current, current)
    if step_id == 0 and mp_subphase:
        return active and st.session_state.get("mp_subphase", "baurecht") == mp_subphase
    return active

def _current_block_name() -> str | None:
    step = int(st.session_state.schritt or 0)
    if step in (0, 1):
        return "Masterplanung"
    if step in (20, 2, 3, 4, 5, 6):
        return "Gebäudeplanung"
    if step == 7:
        return "Prozessplanung"
    return None

if int(st.session_state.schritt or 0) not in (-1, -2, -3):
    if st.sidebar.button("Startseite", key="nav_home", use_container_width=True):
        st.session_state.schritt = -1
        st.rerun()
    if st.sidebar.button("Meine Planungsstände", key="nav_profile", use_container_width=True):
        st.session_state.schritt = -2
        st.rerun()
    if st.sidebar.button("Dokumentbibliothek", key="nav_library", use_container_width=True):
        st.session_state.schritt = -3
        st.rerun()
    current_block = _current_block_name()
    st.sidebar.markdown(f"### {current_block or 'Planung'}")
    for block_name, phases in PLANUNGSBAUSTEINE:
        if block_name != current_block:
            continue
        for step_id, phase_no, label, mp_subphase in phases:
            disabled = _phase_disabled(step_id)
            prefix = _phase_icon(step_id, mp_subphase)
            active_marker = prefix
            if st.sidebar.button(
                f"{active_marker} {phase_no} {label}",
                key=f"nav_phase_{phase_no.replace('.', '_')}_{step_id}_{mp_subphase or 'main'}",
                use_container_width=True,
                disabled=disabled,
            ):
                if mp_subphase:
                    st.session_state.mp_subphase = mp_subphase
                st.session_state.schritt = step_id
                st.rerun()
    st.sidebar.divider()
elif int(st.session_state.schritt or 0) in (-2, -3):
    if st.sidebar.button("Startseite", key="nav_home_profile", use_container_width=True):
        st.session_state.schritt = -1
        st.rerun()
    if int(st.session_state.schritt or 0) != -2 and st.sidebar.button("Meine Planungsstände", key="nav_profile_from_admin", use_container_width=True):
        st.session_state.schritt = -2
        st.rerun()
    if int(st.session_state.schritt or 0) != -3 and st.sidebar.button("Dokumentbibliothek", key="nav_library_from_admin", use_container_width=True):
        st.session_state.schritt = -3
        st.rerun()

st.sidebar.markdown("**AID Demo v0.1**")
st.sidebar.caption(
    "Hochschule Mainz – Fachrichtung Architektur\n"
    "Prof. Thomas Mrokon\n\n"
    "in Kooperation mit Drees & Sommer\n"
    "EPCM.I"
)

# ---------------------------------------------------------------------------
# Sidebar: LLM-Konfiguration
# ---------------------------------------------------------------------------

st.sidebar.divider()
with st.sidebar:
    with st.expander("🔧 Systemstatus", expanded=False):
        try:
            from app.tools.rhino_inside_runner import ist_verfuegbar as _rhinoinside_ok
            if _rhinoinside_ok():
                st.markdown("🟢 **rhinoinside** aktiv (Rhino 8)")
            else:
                st.markdown("🔵 **rhinoinside** inaktiv — Fallback: rhino3dm")
        except Exception as _e:
            st.caption(f"rhinoinside: {_e}")

        try:
            from app.tools.rhino_compute import is_running as _compute_running
            if _compute_running():
                st.markdown("🟢 **Rhino.Compute** aktiv (localhost:5000)")
            else:
                st.markdown("⚪ **Rhino.Compute** nicht aktiv")
                if st.button("Compute starten", key="sidebar_compute_start"):
                    from app.tools.rhino_compute import start_server as _start
                    with st.spinner("Starte Rhino.Compute..."):
                        ok = _start(wait_seconds=12)
                    if ok:
                        st.success("Server gestartet!", icon="✅")
                        st.rerun()
                    else:
                        st.error("Start fehlgeschlagen")
        except Exception as _e:
            st.caption(f"Compute: {_e}")

st.sidebar.divider()
st.sidebar.markdown("**Modell**")

_MODELLE = ["gpt-4o-mini", "gpt-4o", "claude-sonnet-4-6", "claude-opus-4-7"]
modell = st.sidebar.selectbox(
    "Modell",
    _MODELLE,
    index=0,
    help="gpt-4o-mini: schnell & günstig · claude-sonnet-4-6: hohe Qualität",
    label_visibility="collapsed",
)
os.environ["OPENAI_MODEL"] = modell

_is_claude = modell.startswith("claude-")
if _is_claude:
    if os.getenv("ANTHROPIC_API_KEY"):
        st.sidebar.markdown("🟢 Claude aktiv")
    else:
        st.sidebar.markdown("🔴 ANTHROPIC_API_KEY fehlt")
else:
    if os.getenv("OPENAI_API_KEY"):
        st.sidebar.markdown("🟢 OpenAI aktiv")
    else:
        st.sidebar.markdown("⚪ Kein API-Key — Demo-Modus")

# ---------------------------------------------------------------------------
# Sidebar: History + Favoriten
# ---------------------------------------------------------------------------

st.sidebar.divider()
_authenticator.logout("Abmelden", location="sidebar", key="logout_btn")
st.sidebar.caption(f"Eingeloggt als **{st.session_state.get('name', _current_user)}** ({_current_role})")

st.sidebar.divider()
st.sidebar.markdown("### Verlauf & Favoriten")
_all_auth_users = list(_auth_config.get("credentials", {}).get("usernames", {}).keys())

# ── Favoriten ────────────────────────────────────────────────────────────────
with st.sidebar.expander("★ Favoriten", expanded=False):
    from app.tools.persistence import list_favorites as _list_favorites, get_run as _get_run
    _fav_users = _all_auth_users if _current_role in ("viewer", "admin") else [_current_user]
    _favs = []
    for _fav_user in _fav_users:
        for _fav in _list_favorites(_fav_user):
            _favs.append({**_fav, "_owner": _fav_user})
    _favs.sort(key=lambda r: r.get("favorited_at") or r.get("created_at") or "", reverse=True)
    if not _favs:
        st.caption("Noch keine Favoriten gespeichert.")
    for fav in _favs:
        fav_label = fav.get("favorite_label") or fav.get("label") or fav.get("site_name", "Lauf")
        owner_note = f" · {fav.get('_owner')}" if fav.get("_owner") != _current_user else ""
        score_best = max(
            filter(None, [fav.get("score_a"), fav.get("score_b"), fav.get("score_c")]),
            default=0.0,
        )
        col_lbl, col_btn = st.columns([3, 1])
        col_lbl.markdown(
            f"**{fav_label}**  \n"
            f"<span style='font-size:0.75rem;color:#888'>"
            f"{fav.get('nutzungstyp', '')} · {fav.get('site_name', '')} · "
            f"Score {score_best:.1f}{owner_note}</span>",
            unsafe_allow_html=True,
        )
        if col_btn.button("Laden", key=f"fav_load_{fav['id']}", use_container_width=True):
            _run = _get_run(fav["id"])
            if _run:
                st.session_state.result = _run["state"]
                st.session_state["_last_saved_run_id"] = fav["id"]
                st.session_state.schritt = 6
                st.rerun()

# ── Verlauf ──────────────────────────────────────────────────────────────────
with st.sidebar.expander("Verlauf", expanded=False):
    from app.tools.persistence import list_history as _list_history
    _history_users = _all_auth_users if _current_role == "admin" else [_current_user]
    _history = []
    for _hist_user in _history_users:
        for _run in _list_history(_hist_user, limit=20):
            _history.append({**_run, "_owner": _hist_user})
    _history.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    _history = _history[:20]
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
        owner_note = f" · {run.get('_owner')}" if run.get("_owner") != _current_user else ""
        col_info, col_load, col_fav = st.columns([3, 1, 1])
        col_info.markdown(
            f"{'★ ' if is_fav else ''}{ts}  \n"
            f"<span style='font-size:0.75rem;color:#888'>"
            f"{run.get('site_name', '—')} · Score {score_best:.1f}{owner_note}</span>",
            unsafe_allow_html=True,
        )
        if col_load.button("↩", key=f"hist_load_{run['id']}", help="Laden"):
            _run = _get_run(run["id"])
            if _run:
                st.session_state.result = _run["state"]
                st.session_state["_last_saved_run_id"] = run["id"]
                st.session_state.schritt = 6
                st.rerun()
        fav_icon = "★" if is_fav else "☆"
        if col_fav.button(
            fav_icon,
            key=f"hist_fav_{run['id']}",
            help="Favorit",
            disabled=_current_role == "viewer" or run.get("_owner") != _current_user,
        ):
            from app.tools.persistence import mark_favorite as _mark_fav, unmark_favorite as _unmark_fav
            if is_fav:
                _unmark_fav(_current_user, run["id"])
            else:
                _mark_fav(_current_user, run["id"], "")
            st.rerun()

# Router
if st.session_state.schritt == -1:
    schritt_startseite()
elif st.session_state.schritt == -2:
    schritt_profil()
elif st.session_state.schritt == -3:
    schritt_dokumentbibliothek()
elif st.session_state.schritt == 0:
    schritt_masterplanung()
elif st.session_state.schritt == 1:
    schritt_grundstueck()
elif st.session_state.schritt == 20:
    schritt_gebaeudeplanung_start()
elif st.session_state.schritt == 2:
    schritt_eingabe()
elif st.session_state.schritt == 3:
    schritt_funktionsgraph()
elif st.session_state.schritt == 4:
    schritt_regelwerk()
elif st.session_state.schritt == 5:
    schritt_projektziele()
elif st.session_state.schritt == 6:
    schritt_ergebnisse()
elif st.session_state.schritt == 7:
    schritt_prozessplanung()
