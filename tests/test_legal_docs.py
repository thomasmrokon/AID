from __future__ import annotations

from app.tools.legal_docs import analyse_baurecht_documents


def test_baurecht_regex_extracts_core_values(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    text = """
    Textliche Festsetzungen: Das Plangebiet ist als GI Industriegebiet festgesetzt.
    GRZ 0,80. GFZ 2,40. Die maximale Gebäudehöhe GH beträgt 18,5 m.
    Stellplatzsatzung: 1 Stellplatz je 100 m² Nutzfläche Büro.
    """

    result = analyse_baurecht_documents([{"name": "bplan.txt", "text": text, "char_count": len(text)}])
    values = result["values"]

    assert values["grz"] == 0.8
    assert values["gfz"] == 2.4
    assert values["max_gebaeudehoehe_m"] == 18.5
    assert values["stellplaetze_je_flaeche"]["anzahl"] == 1.0
    assert values["stellplaetze_je_flaeche"]["flaeche_m2"] == 100.0
    assert result["source"] in {"regex", "llm"}
