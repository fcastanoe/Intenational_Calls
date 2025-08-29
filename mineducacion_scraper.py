"""
mineducacion_scraper.py
========================

Scraper for project calls issued by the Colombian Ministry of
Education (MinEducación).  The portal segment for calls is located
at ``https://www.mineducacion.gov.co/1780/w3-multipropertyvalues-
55249-69679.html#data=%7B"orfilter":"56678","page":1%7D``.  Each
call is presented as a row inside a ``div`` with classes
``recuadro row border-bottom py-5``.  Calls list the title,
publication date, description, and a link to an article with
additional details.  Since the site does not provide a closing
deadline, the ``deadline_date`` field is set to ``"mirar anexos"``.

This scraper extracts up to ``max_results`` calls from the first
page.  Calls are not filtered by date since no deadline is
available; all entries are returned.  Summarisation of the
description uses the fallback summariser.
"""

from __future__ import annotations

from typing import List, Dict

from http_utils import fetch_page, parse_html
from summarizer import summarize_text, classify_ods


def scrape_mineducacion_calls(max_results: int = 10) -> List[Dict[str, str]]:
    """Scrape open calls from the MinEducación site.

    Parameters
    ----------
    max_results: int, optional
        Maximum number of call entries to return.

    Returns
    -------
    list[dict]
        A list of call dictionaries.  Fields include ``title``,
        ``link``, ``opening_date``, ``deadline_date`` (always
        ``"mirar anexos"``), ``description`` and ``ods_list``.
    """
    base_url = "https://www.mineducacion.gov.co"
    url = (
        "https://www.mineducacion.gov.co/1780/w3-multipropertyvalues-"
        "55249-69679.html#data=%7B\"orfilter\":\"56678\",\"page\":1%7D"
    )
    try:
        html = fetch_page(url)
    except Exception:
        return []
    soup = parse_html(html)
    calls: List[Dict[str, str]] = []
    entries = soup.find_all("div", class_="recuadro")
    for entry in entries:
        # Title and link
        h3 = entry.find("h3", class_="titulo")
        if not h3:
            continue
        link_tag = h3.find("a", href=True)
        if not link_tag:
            continue
        title = link_tag.get_text(strip=True)
        link = base_url + "/1780/" + link_tag["href"] if not link_tag["href"].startswith("http") else link_tag["href"]
        # Opening date
        date_tag = entry.find("h6", class_="fecha")
        opening_date = date_tag.get_text(strip=True) if date_tag else ""
        # Description
        desc_p = entry.find("p", class_="abstract")
        description_raw = desc_p.get_text(" ", strip=True) if desc_p else ""
        description = summarize_text(description_raw)
        call = {
            "title": title,
            "link": link,
            "opening_date": opening_date,
            "deadline_date": "mirar anexos",
            "description": description,
            # Classify ODS based on the description
            "ods_list": classify_ods(description),
            # Human-readable site name
            "site": "MinEducación",
            # These calls are project-based calls (not royalties)
            "type": "Proyectos",
        }
        calls.append(call)
        if len(calls) >= max_results:
            break
    return calls


__all__ = ["scrape_mineducacion_calls"]