"""Schnell-Test der Pipeline ohne LLM (Fallback-Pfad)."""
from app.graph import graph
from app.state import ProduktionInput, Nutzungstyp

inp = ProduktionInput(
    nutzungstyp=Nutzungstyp.PRODUKTION,
    produktionsflaeche=1200,
    lager_rohstoffe=400,
    lager_fertigwaren=400,
    wareneingang=200,
    versand=200,
    buero_nuf2=250,
    sozialraeume_nuf7=84,
    technikflaeche_tf=168,
)

result = graph.invoke({"user_input": inp.model_dump()})
variants = result.get("variants", [])
typology_assignments = result.get("typology_assignments", {})
reasoning_log = result.get("reasoning_log", [])
interpreted_rules = result.get("interpreted_rules", {})

print(f"\nVarianten: {len(variants)}")
for v in variants:
    name = v["name"]
    typology = typology_assignments.get(name, "unbekannt")
    zone_count = len(v["zonen"])
    print(f"  {name}: {zone_count} Zonen, Typologie={typology}")

print(f"\ninterpreted_rules: {list(interpreted_rules.keys())}")
for vname, cfg in interpreted_rules.items():
    trag = cfg.get("tragwerk", {})
    print(f"  {vname}: raster_x={trag.get('raster_x_m')}m, traufhoehe={trag.get('traufhoehe_m')}m")

print(f"\nReasoning Log: {len(reasoning_log)} Eintraege")
for entry in reasoning_log[:5]:
    print(f"  [{entry.get('agent')}] {entry.get('disziplin')}: {entry.get('entscheidung')}")
