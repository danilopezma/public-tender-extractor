"""Fields that live in prose, not in tables, and the local LLM that reads them.

The meeting date is parsed deterministically. The expediente fields and the
abnormally-low-offer statements need interpretation, so they go through the LLM
(Ollama), and every value it returns must appear verbatim in the source text or it is
discarded.
"""

import json
import os
import re
from datetime import date
from typing import Dict, List, Optional

import requests

DEFAULT_MODEL = "hf.co/bartowski/Qwen2.5-7B-Instruct-GGUF:Q4_K_M"
DEFAULT_HOST = "http://localhost:11434"

TENDER_SCHEMA = {
    "type": "object",
    "properties": {
        "file_number": {"type": ["string", "null"]},
        "subject": {"type": ["string", "null"]},
        "contracting_authority": {"type": ["string", "null"]},
    },
    "required": ["file_number", "subject", "contracting_authority"],
}
ABNORMAL_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "bidder_name": {"type": "string"},
                    "positions": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["bidder_name", "positions"],
            },
        }
    },
    "required": ["findings"],
}

_ORDINALS = ("PRIMERO", "SEGUNDO", "TERCERO", "CUARTO", "QUINTO", "SEXTO", "SÉPTIMO",
             "SEPTIMO", "OCTAVO", "NOVENO", "DÉCIMO", "DECIMO")
_ORDINAL_START = re.compile(r"(?m)^(?=(?:%s)\b)" % "|".join(_ORDINALS))
_ABNORMAL = re.compile(r"baja\s+(?:anormal|temeraria|desproporcionada)|desproporcionad", re.I)
_DATE = re.compile(r"(\d{1,2})\s+de\s+([a-záéíóú]+)\s+de\s+(\d{4})", re.IGNORECASE)
_MONTHS = {name: number for number, name in enumerate(
    ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
     "septiembre", "octubre", "noviembre", "diciembre"], start=1)}


class LLMError(RuntimeError):
    """The local model could not be reached or did not return valid JSON."""


def tender_fields(text: str) -> Dict[str, Optional[str]]:
    """Read the expediente fields from the first page of the meeting record.

    Args:
        text: Text of the first page(s).

    Returns:
        file_number, subject and contracting_authority; a value that is not found
        verbatim in the text becomes None.

    Raises:
        LLMError: The model could not be reached.
    """
    # 1. Ask the model ---------------------------------------------------------
    answer = chat_json(
        "You extract data from the first page of Spanish public procurement meeting records (actas). "
        "Copy values exactly as written in the text; never rephrase. Use null when absent.",
        "Extract: file_number (número de expediente, full code), subject (objeto del contrato), "
        "contracting_authority (órgano de contratación).\n\nTEXT:\n" + text,
        TENDER_SCHEMA,
    )

    # 2. Keep only values written in the text ----------------------------------
    haystack = _normalize(text)
    fields = {}
    for key in TENDER_SCHEMA["properties"]:
        value = answer.get(key)
        written = isinstance(value, str) and _normalize(value) in haystack
        fields[key] = " ".join(value.split()) if written else None
    return fields


def abnormal_findings(paragraph: str) -> List[Dict[str, object]]:
    """Find who is presumed to have an abnormally low offer, and at which positions.

    Args:
        paragraph: A paragraph that talks about abnormally low offers.

    Returns:
        One {"bidder_name", "positions"} per bidder named in the paragraph. Positions
        are lot.order labels (e.g. "8.4"); any not written in the paragraph is dropped.

    Raises:
        LLMError: The model could not be reached.
    """
    # 1. Ask the model ---------------------------------------------------------
    answer = chat_json(
        "You read a paragraph of Spanish public procurement meeting records (actas). List only the companies "
        "the text says are presumed to have an abnormally low or reckless offer, and the "
        "lot/order positions it names for each, copied exactly (e.g. 'Lotes 1.1, 8.4 y 9.4' "
        "-> ['1.1','8.4','9.4']). Do not infer anything that is not written.",
        paragraph,
        ABNORMAL_SCHEMA,
    )

    # 2. Keep only names and positions written in the paragraph ---------------
    haystack = _normalize(paragraph)
    findings = []
    for item in answer.get("findings", []):
        name = item.get("bidder_name", "")
        if _normalize(name) not in haystack:
            continue
        # The model may keep words around the number ("Lotes 1.1"): keep only the position.
        positions = [
            position
            for raw in item.get("positions", [])
            for position in re.findall(r"\d+(?:\.\d+)?", raw)
            if position in paragraph
        ]
        findings.append({"bidder_name": name, "positions": positions})
    return findings


def abnormal_paragraphs(text: str) -> List[str]:
    """Select the paragraphs that talk about abnormally low offers.

    Args:
        text: Text of the meeting record, whose paragraphs start with PRIMERO, SEGUNDO...

    Returns:
        The matching paragraphs.
    """
    return [p.strip() for p in _ORDINAL_START.split(text) if _ABNORMAL.search(p)]


def meeting_date(text: str) -> Optional[date]:
    """Find the date of the meeting after the label 'Día y hora de la reunión'.

    The label can wrap over several lines.

    Args:
        text: Text of the first page(s).

    Returns:
        The first date written like '23 de julio de 2026' after the label, or None.
    """
    label = re.search(r"d[ií]a\s+y\s+hora.{0,120}", text, re.I | re.S)
    found = _DATE.search(label.group(0)) if label else None
    if not found or found.group(2).lower() not in _MONTHS:
        return None
    return date(int(found.group(3)), _MONTHS[found.group(2).lower()], int(found.group(1)))


def chat_json(
    system: str,
    user: str,
    schema: dict,
    model: Optional[str] = None,
    host: Optional[str] = None,
    timeout: float = 600,
) -> dict:
    """Ask the local Ollama model for JSON that matches a schema (temperature 0).

    Args:
        system: System prompt.
        user: User prompt.
        schema: JSON schema of the answer (Ollama structured output).
        model: Model name; TENDER_LLM_MODEL or DEFAULT_MODEL if omitted.
        host: Ollama address; OLLAMA_HOST or DEFAULT_HOST if omitted.
        timeout: Seconds to wait for the answer.

    Returns:
        The parsed JSON answer.

    Raises:
        LLMError: Ollama could not be reached or did not return valid JSON.
    """
    model = model or os.environ.get("TENDER_LLM_MODEL", DEFAULT_MODEL)
    host = (host or os.environ.get("OLLAMA_HOST") or DEFAULT_HOST).rstrip("/")
    if not host.startswith("http"):
        host = "http://" + host
    try:
        response = requests.post(
            f"{host}/api/chat",
            json={
                "model": model,
                "stream": False,
                "format": schema,
                "options": {"temperature": 0},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=timeout,
        )
        response.raise_for_status()
        return json.loads(response.json()["message"]["content"])
    except (requests.RequestException, KeyError, ValueError) as exc:
        raise LLMError(f"Ollama request to {host} failed ({type(exc).__name__})") from exc


def _normalize(text: str) -> str:
    """Lowercase the text and collapse its whitespace, to compare it with the source."""
    return re.sub(r"\s+", " ", text).strip().casefold()
