import json
with open('outputs/evaluation.json') as f:
    data = json.load(f)
if isinstance(data, list):
    for e in data:
        star = ' (empfohlen)' if e.get('empfohlen') else ''
        print(f"{e['variante']}: {e['gesamtscore']:.2f}{star}  MF={e.get('materialfluss_score','?')}  EB={e.get('erweiterbarkeit_score','?')}")
else:
    print(data)
