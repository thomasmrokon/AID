"""
Indikative PV-Ertragsschätzung und CO2-Bilanzierung für Industriegebäude.

Alle Kennwerte sind Richtwerte für die frühe Planungsphase (Leistungsphase 1–2).
Quellen: DIN V 18599, BDEW Strompreisentwicklung, UBA Emissionsfaktoren 2024,
         BKI Energieverbrauchskennwerte, Fraunhofer ISE Photovoltaics Report.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

# PV
_YIELD_KWH_KWP   = 960    # kWh/kWp·Jahr — Deutschlandmittel Flachdach, 10° Südneigung
_M2_PER_KWP      = 6.5    # m² Modulfläche je kWp (bifaziale Module, 400–430 Wp)
_ROOF_PV_FRAC    = 0.60   # nutzbare Dachfläche (Abstand Attika, Lüftung, Wartung)
_CO2_GRID        = 0.380  # kg CO2e/kWh DE Netzmix 2024 (UBA)
_SELF_USE_FRAC   = 0.60   # Eigenverbrauchsquote (ohne Speicher, tagsüber Betrieb)
_FEED_TARIFF_EUR = 0.082  # €/kWh Einspeisevergütung EEG 2024 (>100 kWp)
_ELEC_PRICE_EUR  = 0.22   # €/kWh Industriestrom (inkl. Netzentgelte, 2024)

# Graue Energie (Embodied Carbon), kg CO2e/m² BGF — Strukturtyp je Nutzungstyp
_EMBODIED_KG_M2: dict[str, int] = {
    "Produktion":   275,   # Stahlbeton-Skelett, EPS-Sandwichhülle
    "Logistik":     215,   # Stahlrahmen, Trapezblech + Mineralwolle
    "Data Center":  430,   # Stahl + intensive TGA/IT-Infrastruktur
}

# Betriebsenergie kWh/(m²·Jahr) nach DIN V 18599 / BDEW-Kennwerte
_OPERATIONAL_KWH_M2: dict[str, int] = {
    "Produktion":   115,   # Beleuchtung, Druckluft, Klimatisierung Büro
    "Logistik":      55,   # Beleuchtung, Fördertechnik, Kälte
    "Data Center":  400,   # IT-Last (PUE ~1.4)
}

# Nutzungsdauer Gebäude (für Amortisationsberechnung)
_LIFESPAN_YEARS = 50

# PV-Modullebensdauer und Degradation
_PV_LIFESPAN_YEARS = 30
_PV_DEGR_PA        = 0.005   # 0.5 % Leistungsabfall je Jahr


# ---------------------------------------------------------------------------
# Berechnungsfunktionen
# ---------------------------------------------------------------------------

def calc_pv(roof_area_m2: float) -> dict:
    """PV-Potenzial aus Dachfläche.

    Args:
        roof_area_m2: Tatsächliche Gebäudefootprint-Fläche (m²).
    Returns:
        Dict mit Leistung, Jahresertrag, CO2-Einsparung, Wirtschaftlichkeit.
    """
    pv_area       = roof_area_m2 * _ROOF_PV_FRAC
    kwp           = pv_area / _M2_PER_KWP
    annual_kwh    = kwp * _YIELD_KWH_KWP

    # Degradation: mittlerer Jahresertrag über PV-Lebensdauer
    avg_factor       = 1 - (_PV_DEGR_PA * _PV_LIFESPAN_YEARS / 2)
    lifetime_kwh     = annual_kwh * avg_factor * _PV_LIFESPAN_YEARS

    # CO2-Einsparung
    co2_offset_kg    = annual_kwh * _CO2_GRID
    co2_lifetime_t   = (lifetime_kwh * _CO2_GRID) / 1000

    # Wirtschaftlichkeit
    self_use_kwh     = annual_kwh * _SELF_USE_FRAC
    feed_kwh         = annual_kwh * (1 - _SELF_USE_FRAC)
    annual_savings   = self_use_kwh * _ELEC_PRICE_EUR + feed_kwh * _FEED_TARIFF_EUR

    # Investitionskosten: ~1.000 €/kWp (ab 100 kWp, schlüsselfertig 2024)
    invest_eur       = kwp * 1_000
    payback_years    = invest_eur / annual_savings if annual_savings > 0 else 0

    return {
        "pv_area_m2":         round(pv_area),
        "kwp_installed":      round(kwp, 1),
        "annual_kwh":         round(annual_kwh),
        "annual_kwh_m2":      round(annual_kwh / roof_area_m2, 1) if roof_area_m2 else 0,
        "co2_offset_kg_year": round(co2_offset_kg),
        "co2_offset_t_life":  round(co2_lifetime_t, 1),
        "self_use_kwh":       round(self_use_kwh),
        "feed_kwh":           round(feed_kwh),
        "annual_savings_eur": round(annual_savings),
        "invest_eur":         round(invest_eur),
        "payback_years":      round(payback_years, 1),
    }


def calc_co2(bgf_m2: float, nutzungstyp: str, pv_annual_kwh: float = 0) -> dict:
    """Grobe CO2-Bilanz: Graue Energie + Betrieb − PV-Gutschrift.

    Args:
        bgf_m2:         Brutto-Geschossfläche gesamt.
        nutzungstyp:    "Produktion" | "Logistik" | "Data Center".
        pv_annual_kwh:  Jahres-PV-Ertrag für CO2-Gutschrift.
    Returns:
        Dict mit Einzel- und Gesamtbilanz.
    """
    embodied_kg_m2   = _EMBODIED_KG_M2.get(nutzungstyp, 275)
    op_kwh_m2        = _OPERATIONAL_KWH_M2.get(nutzungstyp, 115)

    embodied_t       = (embodied_kg_m2 * bgf_m2) / 1000
    annual_op_kwh    = op_kwh_m2 * bgf_m2
    annual_op_t      = (annual_op_kwh * _CO2_GRID) / 1000

    pv_offset_t_year = (pv_annual_kwh * _CO2_GRID) / 1000
    net_op_t_year    = annual_op_t - pv_offset_t_year

    # Lebenszyklusbilanz über _LIFESPAN_YEARS
    lifecycle_op_t   = net_op_t_year * _LIFESPAN_YEARS
    lifecycle_total_t = embodied_t + lifecycle_op_t

    # GWP (Global Warming Potential) je m² BGF über Lebenszyklus
    gwp_kg_m2_year   = (lifecycle_total_t * 1000) / bgf_m2 / _LIFESPAN_YEARS if bgf_m2 else 0

    return {
        "embodied_co2_t":      round(embodied_t, 1),
        "embodied_kg_m2":      embodied_kg_m2,
        "annual_op_co2_t":     round(annual_op_t, 1),
        "annual_op_kwh":       round(annual_op_kwh),
        "annual_op_kwh_m2":    op_kwh_m2,
        "pv_offset_co2_t":     round(pv_offset_t_year, 1),
        "net_annual_co2_t":    round(net_op_t_year, 1),
        "lifecycle_op_co2_t":  round(lifecycle_op_t, 1),
        "lifecycle_total_co2_t": round(lifecycle_total_t, 1),
        "gwp_kg_m2_year":      round(gwp_kg_m2_year, 1),
        "lifespan_years":      _LIFESPAN_YEARS,
    }


def building_roof_area(variant_data: dict) -> float:
    """Berechnet die tatsächliche Gebäudefootprint-Fläche aus den Zonendaten.

    Gestapelte Zonen (floors > 1) tragen nur einmalig zur Dachfläche bei.
    Schraffierte Zonen (Erschließung, Außenflächen) werden ausgeschlossen.
    """
    total = 0.0
    for z in variant_data.get("zonen", []):
        if z.get("schraffur"):
            continue
        floors = max(z.get("floors", 1), 1)
        area   = z.get("planned_area_m2") or z.get("flaeche_m2", 0)
        total += area / floors
    return round(total, 1)
