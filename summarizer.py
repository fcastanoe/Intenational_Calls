"""
summarizer.py
===============

This module provides simple text summarisation and ODS (Objetivos de
Desarrollo Sostenible) classification functions used by both the
international and national scrapers.  Due to limited library
availability in the execution environment, the summarisation falls
back to a naive approach of truncating to the first ``word_limit``
words when more sophisticated methods such as Gensim are not
available.

The ODS classifier is a keyword‑based mapper.  It scans the summary
for tokens associated with each of the 17 SDGs and returns a list of
matching goal numbers.  If no keywords are found the classifier
returns ``['unknown']``.
"""

from __future__ import annotations

from typing import List


def summarize_text(text: str, word_limit: int = 100) -> str:
    """Produce a concise summary of ``text``.

    If third‑party summarisation libraries are unavailable this
    function truncates the input to the first ``word_limit`` words.

    Parameters
    ----------
    text: str
        The original text to summarise.
    word_limit: int, optional
        The maximum number of words to include in the summary.

    Returns
    -------
    str
        A summary of the input text.  If the input is empty an empty
        string is returned.  If the original text contains more than
        ``word_limit`` words an ellipsis is appended to indicate
        truncation.
    """
    if not text:
        return ""
    words = text.split()
    if len(words) <= word_limit:
        return text.strip()
    return " ".join(words[:word_limit]) + "..."


# Simple Spanish keyword lists for each SDG.  These lists are not
# exhaustive but provide a basic mapping between common topics and
# SDG numbers.  Additional terms can be added as needed to refine
# classification.  The keys correspond to SDG numbers represented as
# strings.
_SDG_KEYWORDS = {
    "1": ["pobreza", "pobres", "desigualdad"],
    "2": ["hambre", "alimentación", "agricultura"],
    "3": ["salud", "bienestar", "enfermedad"],
    "4": ["educación", "escuela", "universidad"],
    "5": ["igualdad de género", "mujer", "género"],
    "6": ["agua", "saneamiento", "hidráulica"],
    "7": ["energía", "renovable", "electrificación"],
    "8": ["trabajo", "empleo", "economía"],
    "9": ["industria", "innovación", "infraestructura", "tecnología"],
    "10": ["desigualdad", "inclusión", "migración"],
    "11": ["ciudades", "comunidades", "urbanismo"],
    "12": ["consumo", "producción", "residuos"],
    "13": ["clima", "cambio climático", "carbono"],
    "14": ["océano", "mar", "pesca"],
    "15": ["ecosistema", "bosque", "biodiversidad"],
    "16": ["paz", "justicia", "instituciones"],
    "17": ["alianzas", "cooperación", "financiación"]
}


def classify_ods(summary: str) -> List[str]:
    """Classify a summary into one or more Sustainable Development Goals.

    The function searches for Spanish keywords associated with each
    SDG.  If at least one keyword is found the corresponding goal
    number is added to the result list.  If no keywords are found
    ``['unknown']`` is returned.

    Parameters
    ----------
    summary: str
        A concise description of the project or call.

    Returns
    -------
    list[str]
        A list of SDG numbers.  Returns ['unknown'] when no keywords
        are matched.
    """
    if not summary:
        return ["unknown"]
    summary_lower = summary.lower()
    matched = []
    for goal, keywords in _SDG_KEYWORDS.items():
        if any(k in summary_lower for k in keywords):
            matched.append(goal)
    return matched if matched else ["unknown"]


__all__ = ["summarize_text", "classify_ods"]