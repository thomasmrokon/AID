from __future__ import annotations

import json
import re
from io import BytesIO
from typing import Any


def extract_uploaded_document(uploaded_file: Any) -> dict[str, Any]:
    """Extract text from a Streamlit UploadedFile-like object."""
    name = getattr(uploaded_file, "name", "dokument")
    mime = getattr(uploaded_file, "type", "") or ""
    data = uploaded_file.getvalue()
    suffix = name.rsplit(".", 1)[-1].lower() if "." in name else ""

    if suffix == "pdf" or mime == "application/pdf":
        text = _extract_pdf(data)
    elif suffix == "docx" or mime.endswith("wordprocessingml.document"):
        text = _extract_docx(data)
    else:
        text = _decode_text(data)

    return {
        "name": name,
        "mime": mime,
        "text": text.strip(),
        "char_count": len(text.strip()),
    }


def analyse_baurecht_documents(documents: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract planning law parameters from uploaded documents.

    Uses an LLM when configured; otherwise applies deterministic regex extraction.
    """
    combined = "\n\n".join(
        f"### {doc.get('name', 'Dokument')}\n{doc.get('text', '')[:12000]}"
        for doc in documents
        if doc.get("text")
    )
    fallback = _regex_extract(combined)
    llm_result = _llm_extract(combined) if combined else None
    result = _merge_analysis(fallback, llm_result or {})
    result["documents"] = [
        {"name": d.get("name"), "char_count": d.get("char_count", 0)}
        for d in documents
    ]
    result["source"] = "llm" if llm_result else "regex"
    return result


def _extract_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except Exception as exc:  # pragma: no cover - dependency/environment specific
        raise RuntimeError("PDF-Textextraktion benötigt pypdf.") from exc
    reader = PdfReader(BytesIO(data))
    pages = []
    for page in reader.pages[:80]:
        pages.append(page.extract_text() or "")
    return "\n".join(pages)


def _extract_docx(data: bytes) -> str:
    try:
        from docx import Document
    except Exception as exc:  # pragma: no cover - dependency/environment specific
        raise RuntimeError("DOCX-Textextraktion benötigt python-docx.") from exc
    doc = Document(BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs)


def _decode_text(data: bytes) -> str:
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def _num(value: str) -> float | None:
    try:
        return float(value.replace(" ", "").replace(",", "."))
    except Exception:
        return None


def _regex_extract(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {"values": {}, "notes": [], "evidence": []}
    patterns = {
        "grz": r"\bGRZ\b\s*(?:[:=]|von|max\.?|bis)?\s*(0?[,\.]\d{1,2}|1[,\.]0)",
        "gfz": r"\bGFZ\b\s*(?:[:=]|von|max\.?|bis)?\s*(\d?[,\.]\d{1,2})",
        "max_gebaeudehoehe_m": r"(?:Gebäudehöhe|Gebaeudehoehe|GH|max(?:imale)?\s*Höhe|Traufhöhe|Firsthöhe)\D{0,35}(\d{1,2}(?:[,\.]\d+)?)\s*m",
        "regelgeschoss_hoehe_m": r"(?:Regelgeschoss|Geschosshöhe|Geschosshoehe)\D{0,35}(\d{1,2}(?:[,\.]\d+)?)\s*m",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = _num(match.group(1))
            if value is not None:
                result["values"][key] = value
                result["evidence"].append({"field": key, "excerpt": _excerpt(text, match.start(), match.end())})

    sp_match = re.search(r"(\d+(?:[,\.]\d+)?)\s*(?:Stellplatz|Stellplätze|Stellplaetze|SP)\s*(?:je|/|pro)\s*(\d+(?:[,\.]\d+)?)\s*m", text, re.IGNORECASE)
    if sp_match:
        result["values"]["stellplaetze_je_flaeche"] = {
            "anzahl": _num(sp_match.group(1)),
            "flaeche_m2": _num(sp_match.group(2)),
        }
        result["evidence"].append({"field": "stellplaetze_je_flaeche", "excerpt": _excerpt(text, sp_match.start(), sp_match.end())})

    for token in ("Baugrenze", "Baulinie", "Industriegebiet", "Gewerbegebiet", "GI", "GE", "Stellplatzsatzung", "Abstandsfläche"):
        if re.search(rf"\b{re.escape(token)}\b", text, re.IGNORECASE):
            result["notes"].append(token)
    return result


def _llm_extract(text: str) -> dict[str, Any] | None:
    if not text.strip():
        return None
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from app.llm import invoke_messages, is_llm_configured
        if not is_llm_configured():
            return None
        response = invoke_messages([
            SystemMessage(content=(
                "Du extrahierst planungsrechtliche Parameter aus deutschen Bebauungsplaenen, "
                "Stellplatzsatzungen und baurechtlichen Dokumenten. Antworte ausschliesslich als JSON. "
                "Nutze null, wenn ein Wert nicht belastbar erkennbar ist. Gib kurze Evidenzstellen an."
            )),
            HumanMessage(content=(
                "Extrahiere dieses Schema: {values:{grz,gfz,max_gebaeudehoehe_m,"
                "regelgeschoss_hoehe_m,abstandsfaktor,stellplaetze_je_flaeche}, "
                "notes:[string], evidence:[{field,excerpt}], confidence:0..1}.\n\n"
                f"DOKUMENTTEXT:\n{text[:24000]}"
            )),
        ], temperature=0.0)
        if not response:
            return None
        raw = response.strip()
        raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.IGNORECASE | re.MULTILINE).strip()
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _merge_analysis(fallback: dict[str, Any], llm_result: dict[str, Any]) -> dict[str, Any]:
    merged = {
        "values": dict(fallback.get("values") or {}),
        "notes": list(fallback.get("notes") or []),
        "evidence": list(fallback.get("evidence") or []),
        "confidence": fallback.get("confidence", 0.45),
    }
    if llm_result:
        merged["values"].update({k: v for k, v in (llm_result.get("values") or {}).items() if v is not None})
        merged["notes"] = _dedupe(merged["notes"] + list(llm_result.get("notes") or []))
        merged["evidence"] = list(llm_result.get("evidence") or []) or merged["evidence"]
        merged["confidence"] = llm_result.get("confidence", 0.75)
    return merged


def _dedupe(items: list[Any]) -> list[Any]:
    seen = set()
    out = []
    for item in items:
        key = str(item)
        if key not in seen:
            out.append(item)
            seen.add(key)
    return out


def _excerpt(text: str, start: int, end: int, radius: int = 100) -> str:
    return re.sub(r"\s+", " ", text[max(0, start - radius): min(len(text), end + radius)]).strip()
