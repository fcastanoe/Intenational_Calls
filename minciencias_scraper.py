"""
minciencias_scraper.py
======================

Scraper for the Colombian Ministry of Science, Technology and
Innovation (MinCiencias) calls financed with royalties.  The page
``https://minciencias.gov.co/convocatorias/todas`` contains a table
with multiple rows; each row corresponds to a call.  The table lists
the call number, title (with a link to the detailed page), a brief
description, the funding amount and the opening date.  To obtain the
deadline, the scraper visits the detail page and searches for a row
where the first cell contains the text ``Cierre``.

Only the first five rows of the table are considered; calls whose
closing date is less than seven days from the current date are
discarded.  Descriptions are summarised and ODS classification is
performed using the summariser module.
"""

from __future__ import annotations

import datetime
from typing import List, Dict

from http_utils import fetch_page, parse_html
from summarizer import summarize_text, classify_ods


def _parse_date_spanish(date_str: str) -> datetime.date | None:
    """Parse a Spanish date string like 'jueves 25 septiembre 2025 07:00 pm'.

    Returns None if parsing fails.
    """
    try:
        parts = date_str.split()
        # The day number is the second element
        # e.g. jueves 25 septiembre 2025 07:00 pm
        day = int(parts[1])
        month_name = parts[2].lower()
        year = int(parts[3])
        # Map Spanish month names to month numbers
        month_map = {
            'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5,
            'junio': 6, 'julio': 7, 'agosto': 8, 'septiembre': 9,
            'octubre': 10, 'noviembre': 11, 'diciembre': 12,
        }
        month = month_map.get(month_name)
        if month is None:
            return None
        return datetime.date(year, month, day)
    except Exception:
        return None


def scrape_minciencias_calls(max_results: int = 10) -> List[Dict[str, str]]:
    """Scrape MinCiencias calls from the first page of the table.

    Parameters
    ----------
    max_results: int, optional
        Maximum number of entries to return; capped at 5 due to page
        structure.

    Returns
    -------
    list[dict]
        A list of call dictionaries.  The list may contain fewer
        entries if not enough valid calls are available.
    """
    url = "https://minciencias.gov.co/convocatorias/todas"
    try:
        html = fetch_page(url)
    except Exception:
        return []
    soup = parse_html(html)
    tbody = soup.find("tbody")
    if not tbody:
        return []
    rows = tbody.find_all("tr")
    calls = []
    for row in rows[:5]:  # Only consider the first five calls
        cells = row.find_all("td")
        if len(cells) < 5:
            continue
        title_cell = cells[1]
        link_tag = title_cell.find("a", href=True)
        if not link_tag:
            continue
        title = link_tag.get_text(strip=True)
        link = "https://minciencias.gov.co" + link_tag["href"]
        description_raw = cells[2].get_text(" ", strip=True)
        description = summarize_text(description_raw)
        opening_date = cells[4].get_text(" ", strip=True)
        # Fetch detail page to get closing date
        deadline_date = ""
        try:
            detail_html = fetch_page(link)
            detail_soup = parse_html(detail_html)
            detail_rows = detail_soup.find_all("tr")
            for drow in detail_rows:
                header_cell = drow.find("td", class_="views-field-field-numero")
                if header_cell and 'Cierre' in header_cell.get_text(strip=True):
                    value_cell = drow.find("td", class_="views-field-body")
                    if value_cell:
                        date_text = value_cell.get_text(strip=True)
                        deadline_date = date_text
                        break
        except Exception:
            deadline_date = ""
        # Convert closing date string to date object for comparison
        valid = True
        if deadline_date:
            parsed = _parse_date_spanish(deadline_date)
            if parsed and parsed < datetime.date.today() + datetime.timedelta(days=7):
                valid = False
        if valid:
            calls.append({
                "title": title,
                "link": link,
                "opening_date": opening_date,
                "deadline_date": deadline_date,
                "description": description,
                # Classify ODS based on the description
                "ods_list": classify_ods(description),
                # Human-friendly ministry name for display
                "site": "MinCiencias",
                # These calls are financed with royalties
                "type": "Regalías",
            })
        if len(calls) >= max_results:
            break
    return calls


__all__ = ["scrape_minciencias_calls"]