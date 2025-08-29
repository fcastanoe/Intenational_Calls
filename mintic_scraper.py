"""
mintic_scraper.py
===================

Scraper for project calls published by the Colombian Ministry of
Information and Communication Technologies (MinTIC).  The calls are
listed on the ministry's press room page under the Convocatorias
section: ``https://www.mintic.gov.co/portal/inicio/Sala-de-prensa/
Convocatorias``.

Each call appears as a card within a ``div`` of class ``recuadro``.
Cards include a title, publication date and a status indicator (for
example ``Abierta`` or ``Cerrada``).  This scraper returns only
those calls whose status contains ``Abierta``.  Because the page
does not provide closing dates, the ``deadline_date`` field is
left empty.  A basic description is unavailable, so the "description"
field is returned as an empty string.

Due to network restrictions some pages may not be accessible and the
scraper may return an empty list.
"""

from __future__ import annotations

from typing import List, Dict

from http_utils import fetch_page, parse_html
from summarizer import classify_ods


def scrape_mintic_calls(max_results: int = 10) -> List[Dict[str, str]]:
    """Scrape open calls from the MinTIC press room.

    Parameters
    ----------
    max_results: int, optional
        Maximum number of call entries to return.

    Returns
    -------
    list[dict]
        A list of call dictionaries.  Each dictionary contains
        ``title``, ``link``, ``opening_date``, ``deadline_date`` (empty),
        ``description`` (empty) and ``ods_list`` (always ``['unknown']``).
    """
    url = "https://www.mintic.gov.co/portal/inicio/Sala-de-prensa/Convocatorias"
    try:
        html = fetch_page(url)
    except Exception:
        return []
    soup = parse_html(html)
    calls: List[Dict[str, str]] = []
    # Each call is inside div.recuadro
    cards = soup.find_all("div", class_="recuadro")
    for card in cards:
        # Check status: look for span containing 'Abierta'
        status_span = card.find("span", string=lambda s: s and "abierta" in s.lower())
        if not status_span:
            continue
        # Title and link
        title_div = card.find("div", class_="titulo")
        if not title_div:
            continue
        link_tag = title_div.find("a", href=True)
        if not link_tag:
            continue
        title = link_tag.get_text(strip=True)
        link = "https://www.mintic.gov.co" + link_tag["href"]
        # Publication date: div.fecha
        date_div = card.find("div", class_="fecha")
        opening_date = date_div.get_text(strip=True) if date_div else ""
        call = {
            "title": title,
            "link": link,
            "opening_date": opening_date,
            "deadline_date": "",
            "description": "",
            # MinTIC calls have no clear SDG classification
            "ods_list": classify_ods(""),
            # Name of the ministry for display
            "site": "MinTIC",
            # These calls are projects (not royalty funded)
            "type": "Proyectos",
        }
        calls.append(call)
        if len(calls) >= max_results:
            break
    return calls


__all__ = ["scrape_mintic_calls"]