"""
minambiente_scraper.py
======================

Scraper for the Colombian Ministry of Environment (MinAmbiente) calls
financed with royalties.  The page ``invitacion-2025-2026`` lists
project invitations without explicit opening or closing dates.  Each
invitation appears as a column containing a title and a link to a
detail page.  The scraper extracts a short description from the
heading and uses the heading text as both title and description.

If there are multiple invitations on the page they will be enumerated
as "Convocatoria 1", "Convocatoria 2" and so on.  All entries are
returned since there is no date to filter by.
"""

from __future__ import annotations

from typing import List, Dict

from http_utils import fetch_page, parse_html
from summarizer import summarize_text, classify_ods


def scrape_minambiente_calls(max_results: int = 10) -> List[Dict[str, str]]:
    """Scrape project invitations from the MinAmbiente royalties site.

    Parameters
    ----------
    max_results: int, optional
        Maximum number of entries to return.  The page typically
        contains only a handful of invitations.

    Returns
    -------
    list[dict]
        A list of call dictionaries.  Each dictionary includes the
        keys ``title``, ``link``, ``opening_date``, ``deadline_date``,
        ``description`` and ``ods_list``.
    """
    url = "https://regalias.minambiente.gov.co/invitacion-2025-2026"
    try:
        html = fetch_page(url)
    except Exception:
        return []
    soup = parse_html(html)
    calls = []
    # Invitations are contained in columns with class 'vc_column-inner'
    columns = soup.find_all("div", class_=lambda c: c and c.startswith("vc_column-inner"))
    count = 1
    for col in columns:
        h3 = col.find("h3")
        link_tag = col.find("a", href=True)
        if h3 and link_tag:
            title = f"Convocatoria {count}"
            desc_text = h3.get_text(strip=True)
            description = summarize_text(desc_text)
            link = link_tag["href"]
            calls.append({
                "title": title,
                "link": link,
                "opening_date": "",
                "deadline_date": "",
                "description": description,
                # Infer ODS classification
                "ods_list": classify_ods(description),
                # Use human-friendly ministry name for the site field
                "site": "MinAmbiente",
                # All MinAmbiente invitations on this page are royalty-funded
                "type": "Regalías",
            })
            count += 1
            if len(calls) >= max_results:
                break
    return calls


__all__ = ["scrape_minambiente_calls"]