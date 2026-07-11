"""
AID Demo – Regelwerk-Katalog UI
Rendert den strukturierten Zwei-Phasen-Regelkatalog in Streamlit.
Gibt rule_overrides-Dict zurück, kompatibel mit der Pipeline.
"""
from __future__ import annotations
from pathlib import Path
import yaml

DATA_DIR = Path(__file__).parent.parent / "data"
HARD_RULES_PATH  = DATA_DIR / "rules_hard.yaml"
CONV_RULES_PATH  = DATA_DIR / "rules_conventions.yaml"

# ---------------------------------------------------------------------------
# Disziplin-Metadaten für die UI
# ---------------------------------------------------------------------------

DISZIPLINEN = [
    {
        "key":   "tragwerk",
        "label": "Tragwerk",
        "icon":  "🏗️",
        "beschreibung": "Stützenraster, Traufhöhe, Bodenbelastung",
        "hard_key": None,
        "conv_key": "tragwerk",
    },
    {
        "key":   "brandschutz",
        "label": "Brandschutz",
        "icon":  "🔥",
        "beschreibung": "Fluchtwege, Brandabschnitte, Feuerwehrzufahrt",
        "hard_key": "brandschutz",
        "conv_key": None,
    },
    {
        "key":   "arbeitsstaetten",
        "label": "Arbeitsschutz",
        "icon":  "👷",
        "beschreibung": "Raumhöhen, Lichtstärken, Gangbreiten",
        "hard_key": "arbeitsstaetten",
        "conv_key": None,
    },
    {
        "key":   "logistik",
        "label": "Logistik & Materialfluss",
        "icon":  "📦",
        "beschreibung": "Materialflussweg, Andockstellen, Rangierbereich",
        "hard_key": None,
        "conv_key": "logistik",
    },
    {
        "key":   "erschliessung",
        "label": "Erschließung",
        "icon":  "🚚",
        "beschreibung": "Stellplätze, Erschließungsbreite",
        "hard_key": None,
        "conv_key": "erschliessung",
    },
    {
        "key":   "erweiterbarkeit",
        "label": "Erweiterbarkeit",
        "icon":  "📐",
        "beschreibung": "Freie Fassade, Erweiterungsrichtung",
        "hard_key": None,
        "conv_key": "erweiterbarkeit",
    },
]


def _load_rules() -> tuple[dict, dict]:
    with open(HARD_RULES_PATH, encoding="utf-8") as f:
        hard = yaml.safe_load(f) or {}
    with open(CONV_RULES_PATH, encoding="utf-8") as f:
        conv = yaml.safe_load(f) or {}
    return hard, conv


def render_rule_catalog(st, existing_overrides: dict | None = None) -> dict:
    """
    Rendert den interaktiven Regelwerk-Katalog.
    Gibt ein rule_overrides-Dict zurück.
    """
    hard, conv = _load_rules()
    overrides: dict = {}

    st.caption(
        "Wähle und passe die Planungsregeln an. "
        "HARD-Regeln sind gesetzlich bindend (nur zur Information). "
        "KONVENTION-Regeln können im Rahmen des Wertespektrums angepasst werden."
    )

    for disziplin in DISZIPLINEN:
        dkey  = disziplin["key"]
        label = disziplin["label"]
        icon  = disziplin["icon"]
        hard_rules_d = hard.get(disziplin["hard_key"] or "", {})
        conv_rules_d = conv.get(disziplin["conv_key"] or "", {})

        if not hard_rules_d and not conv_rules_d:
            continue

        with st.expander(f"{icon} {label} — {disziplin['beschreibung']}", expanded=False):

            # ── Hard Rules (read-only) ─────────────────────────────────────
            if hard_rules_d:
                st.markdown("**Gesetzliche Anforderungen (nicht änderbar)**")
                for regel_name, regel_data in hard_rules_d.items():
                    if not isinstance(regel_data, dict):
                        continue
                    wert = regel_data.get("wert", "–")
                    quelle = regel_data.get("quelle", "")
                    komp = regel_data.get("kompensation")
                    einheit = regel_data.get("einheit", "")
                    label_text = regel_name.replace("_", " ")
                    col_l, col_v, col_q = st.columns([3, 1, 3])
                    with col_l:
                        st.markdown(
                            f'<span style="background:#EEE;padding:2px 8px;border-radius:4px;'
                            f'font-size:0.75rem;font-weight:bold">HARD</span> {label_text}',
                            unsafe_allow_html=True,
                        )
                    with col_v:
                        st.markdown(f"**{wert}** {einheit}")
                    with col_q:
                        st.caption(quelle)
                    if komp:
                        st.caption(
                            f"Kompensation: {komp.get('massnahme', '')} "
                            f"→ {komp.get('wert_mit_kompensation', '')} {einheit}"
                        )
                st.markdown("---")

            # ── Convention Rules (editierbar) ─────────────────────────────
            if conv_rules_d:
                st.markdown("**Planungskonventionen**")
                disziplin_overrides: dict = {}

                for regel_name, regel_data in conv_rules_d.items():
                    if not isinstance(regel_data, dict):
                        continue

                    beschreibung = regel_data.get("beschreibung", regel_name.replace("_", " "))
                    quelle       = regel_data.get("quelle", "")
                    einheit      = regel_data.get("einheit", "")
                    default_val  = regel_data.get("default")
                    ranges       = regel_data.get("range")
                    optionen     = regel_data.get("optionen")

                    # Aktuellen Wert aus existing_overrides oder Default
                    current = (existing_overrides or {}).get(dkey, {}).get(regel_name, default_val)

                    c_label, c_ctrl, c_src = st.columns([3, 2, 2])
                    with c_label:
                        st.markdown(
                            f'<span style="background:#D6EAF8;padding:2px 8px;border-radius:4px;'
                            f'font-size:0.75rem;font-weight:bold;color:#1A5276">KONVENTION</span> '
                            f'{beschreibung}',
                            unsafe_allow_html=True,
                        )
                    with c_src:
                        st.caption(quelle)

                    with c_ctrl:
                        widget_key = f"rule_{dkey}_{regel_name}"
                        if ranges:
                            # Diskrete Auswahl aus Wertebereich
                            ranges_str = [str(r) for r in ranges]
                            current_str = str(current) if current is not None else ranges_str[0]
                            if current_str not in ranges_str:
                                current_str = ranges_str[0]
                            chosen_str = st.radio(
                                f"{beschreibung} {einheit}",
                                options=ranges_str,
                                index=ranges_str.index(current_str),
                                horizontal=True,
                                key=widget_key,
                                label_visibility="collapsed",
                            )
                            # Parse back to number if applicable
                            try:
                                chosen = float(chosen_str) if "." in chosen_str else int(chosen_str)
                            except ValueError:
                                chosen = chosen_str
                            disziplin_overrides[regel_name] = chosen

                        elif optionen:
                            # Auswahl aus Optionen (z.B. Erweiterungsrichtung)
                            current_opt = current if current in optionen else optionen[0]
                            chosen_opt = st.radio(
                                beschreibung,
                                options=optionen,
                                index=optionen.index(current_opt),
                                horizontal=True,
                                key=widget_key,
                                label_visibility="collapsed",
                            )
                            disziplin_overrides[regel_name] = chosen_opt

                        elif isinstance(default_val, bool):
                            # Boolean
                            chosen_bool = st.checkbox(
                                beschreibung,
                                value=bool(current) if current is not None else bool(default_val),
                                key=widget_key,
                                label_visibility="collapsed",
                            )
                            disziplin_overrides[regel_name] = chosen_bool

                        else:
                            # Freitext / Fallback
                            st.caption(f"Wert: {current}")
                            disziplin_overrides[regel_name] = current

                if disziplin_overrides:
                    overrides[dkey] = disziplin_overrides

    return overrides
