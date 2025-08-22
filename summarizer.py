#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
summarizer.py
---------------

This module provides local summarisation and Sustainable Development Goal (SDG)
classification utilities.  It attempts to use external libraries like
gensim or sumy for better summaries when available, but falls back to a
simple word-slicing method when these packages are not installed.  The
classification function maps a summary to one or more SDG numbers based on
keyword matches.

Functions
~~~~~~~~~
summarize_text(text: str, word_limit: int = 100) -> str
    Produce a concise summary of the input text.  Uses gensim or sumy
    when available, otherwise returns the first ``word_limit`` words.

classify_ods(summary: str) -> list[str]
    Classify a summary into zero or more SDG numbers (as strings) using
    keyword matching.  Returns ``['unknown']`` if no SDG can be identified.

"""

from __future__ import annotations

try:
    # Try gensim for TextRank-based summarisation
    from gensim.summarization import summarize as gensim_summarize  # type: ignore
    _HAS_GENSIM = True
except Exception:
    gensim_summarize = None  # type: ignore
    _HAS_GENSIM = False

# We intentionally avoid using the sumy library for summarisation.
PlaintextParser = None  # type: ignore
Tokenizer = None  # type: ignore
LsaSummarizer = None  # type: ignore
_HAS_SUMY = False


def summarize_text(text: str, word_limit: int = 100) -> str:
    """Return a concise summary of ``text``.

    This function attempts to use gensim's TextRank implementation first.
    If gensim is unavailable or fails, it falls back to sumy's LSA
    summariser.  If that also fails, it returns the first ``word_limit``
    words of the input as a simple summary.

    Parameters
    ----------
    text : str
        The input text to summarise.
    word_limit : int, optional
        Maximum number of words in the summary when no external
        summariser is available (default is 100).

    Returns
    -------
    str
        A concise summary of the input text.

    """
    if not text:
        return ""
    # Use gensim if installed
    if _HAS_GENSIM and gensim_summarize is not None:
        try:
            summary = gensim_summarize(text, word_count=word_limit)
            if summary:
                return summary.strip()
        except Exception:
            pass
    # Fallback: take first ``word_limit`` words
    tokens = text.split()
    if len(tokens) <= word_limit:
        return text.strip()
    return " ".join(tokens[:word_limit]).strip() + " …"


def classify_ods(summary: str) -> list[str]:
    """Classify a summary into one or more SDG numbers.

    This function lowers the summary and searches for keywords associated
    with each SDG.  Keywords are defined in English and can be extended
    as needed.  If no keyword is found for any SDG, ``['unknown']`` is
    returned.

    Parameters
    ----------
    summary : str
        The summary to classify.

    Returns
    -------
    list[str]
        A list of SDG numbers (strings).  If no SDG matches, returns
        ``['unknown']``.
    """
    if not summary:
        return ["unknown"]
    text = summary.lower()
    ods_keywords = {
        "1": ["poverty", "poor", "income", "social protection", "financial", "eradicate poverty"],
        "2": ["hunger", "food", "nutrition", "agriculture", "farmers", "food security", "malnutrition"],
        "3": ["health", "well-being", "disease", "medical", "medicine", "healthcare", "infection", "mental"],
        "4": ["education", "learning", "school", "literacy", "training", "academic", "skills"],
        "5": ["gender", "women", "girls", "equality", "empower", "discrimination", "violence against women"],
        "6": ["water", "sanitation", "clean water", "wastewater", "hygiene", "drinking water"],
        "7": ["energy", "renewable", "clean energy", "electricity", "power", "affordable energy"],
        "8": ["employment", "jobs", "work", "economic growth", "productivity", "labor", "business", "entrepreneurship"],
        "9": ["industry", "innovation", "infrastructure", "technology", "engineering", "development", "transport", "communication", "manufacturing"],
        "10": ["inequality", "marginalized", "equal opportunity", "income disparity", "discrimination", "disabled"],
        "11": ["urban", "city", "community", "housing", "transport", "infrastructure", "public space", "resilience", "urbanization"],
        "12": ["consumption", "production", "sustainable", "recycling", "waste", "supply chain", "resource efficiency"],
        "13": ["climate", "global warming", "greenhouse", "carbon", "emissions", "resilience", "climate change", "mitigation", "adaptation"],
        "14": ["oceans", "sea", "marine", "fish", "aquatic", "marine biodiversity", "overfishing", "coral"],
        "15": ["forests", "land", "biodiversity", "ecosystems", "flora", "fauna", "wildlife", "conservation", "soil", "deforestation", "desertification"],
        "16": ["peace", "justice", "institutions", "rule of law", "human rights", "transparency", "corruption", "violence", "democracy"],
        "17": ["partnership", "cooperation", "international", "finance", "capacity-building", "technology transfer", "policy", "global", "collaboration", "alliances"],
    }
    matched = []
    for num, keys in ods_keywords.items():
        for kw in keys:
            if kw in text:
                matched.append(num)
                break
    if not matched:
        return ["unknown"]
    return sorted(set(matched), key=lambda x: int(x))


__all__ = ["summarize_text", "classify_ods"]