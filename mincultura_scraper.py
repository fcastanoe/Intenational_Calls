"""
mincultura_scraper.py
======================

Scraper for the Colombian Ministry of Culture (MinCultura) project
calls.  The ministry hosts a page containing numerous cultural
programmes and grants at ``https://www.mincultura.gov.co/convocatorias``.

This scraper attempts to extract calls whose titles contain the
phrase ``Programa Nacional`` and which are still open or do not
explicitly close in the first semester of the current year.  Due to
restrictions on HTTP access to some government sites, the parser may
return an empty list when the page cannot be fetched.  Each call
record contains the following fields:

``title``
    The title of the call as provided by the site.

``link``
    A URL to more information about the call.  The link is taken
    directly from the ``BUSCAR`` button when available.

``opening_date``
    The opening date extracted from the call's metadata when
    available.  This value may be an empty string when not provided.

``deadline_date``
    The closing date of the call.  If the closing date references
    ``primer semestre`` or ``segundo semestre`` it is interpreted
    relative to the current date: first‑semester deadlines are
    considered expired after June, second‑semester deadlines are
    considered valid after July.  When no date is present the
    deadline is returned as an empty string.

``description``
    A short description of the call.  The description is summarised
    using the ``summarizer.summarize_text`` function.

``ods_list``
    A list of SDG goal numbers inferred from the description using
    ``summarizer.classify_ods``.  If no SDG keywords are found the
    list contains ``'unknown'``.

Notes
-----
The scraper uses a permissive User‑Agent header via the ``utils``
module to improve the likelihood of successful requests.  Because
MinCultura pages may change structure or employ JavaScript, this
scraper is best effort and may need adjustment if the page layout
changes.

Example
-------

>>> from mincultura_scraper import scrape_mincultura_calls
>>> calls = scrape_mincultura_calls()
>>> for call in calls:
...     print(call["title"], call["deadline_date"])
"""

from __future__ import annotations

import datetime
from typing import List, Dict

from http_utils import fetch_page, parse_html
from summarizer import summarize_text, classify_ods


def _parse_semester_label(label: str) -> bool:
    """Determine whether a semester label represents a valid future closing.

    Parameters
    ----------
    label: str
        The closing label text (e.g. "primer semestre", "segundo semestre").

    Returns
    -------
    bool
        True if the closing should be considered valid relative to the
        current date, False otherwise.
    """
    label = label.lower().strip()
    today = datetime.date.today()
    month = today.month
    # "primer semestre" refers to the first six months of the year.
    if "primer" in label:
        # valid only if current date is within the first half of the year
        return month <= 6
    if "segundo" in label:
        # valid if current date is within the second half
        return month >= 7
    # Unknown label: treat as valid
    return True


def scrape_mincultura_calls(max_results: int = 10) -> List[Dict[str, str]]:
    """Scrape MinCultura cultural calls.

    Parameters
    ----------
    max_results: int, optional
        Maximum number of call entries to return.

    Returns
    -------
    list[dict]
        A list of call dictionaries with the keys ``title``,
        ``link``, ``opening_date``, ``deadline_date``, ``description`` and
        ``ods_list``.
    """
    url = "https://www.mincultura.gov.co/convocatorias"
    try:
        html = fetch_page(url)
    except Exception:
        return []
    soup = parse_html(html)
    calls: List[Dict[str, str]] = []
    # Each call is contained in a div with class 'convocatoria-container'
    containers = soup.find_all("div", class_="convocatoria-container")
    for container in containers:
        # Title appears in span.convocatoria-nombre
        name_span = container.find("span", class_="convocatoria-nombre")
        if not name_span:
            continue
        title_raw = name_span.get_text(strip=True)
        # Filter by "Programa Nacional" in title
        if "programa nacional" not in title_raw.lower():
            continue
        title = title_raw
        # Description text (without summary) in p.convocatoria-texto
        desc_p = container.find("p", class_="convocatoria-texto")
        description_raw = desc_p.get_text(" ", strip=True) if desc_p else ""
        description = summarize_text(description_raw)
        # Dates: inside 'fecha-section-container'
        fecha_section = container.find("div", class_="fecha-section-container")
        opening_date = ""
        deadline_date = ""
        if fecha_section:
            # Each "convocatoria-item-container" holds open/close
            containers_inner = fecha_section.find_all("div", class_="convocatoria-item-container")
            # We expect two: first is opening, second is closing
            if containers_inner:
                # Opening date
                texts = containers_inner[0].find_all("p", class_="convocatoria-item-segundo-texto")
                if texts:
                    opening_date = texts[0].get_text(strip=True)
            if len(containers_inner) > 1:
                closing_texts = containers_inner[1].find_all("p", class_="convocatoria-item-segundo-texto")
                if closing_texts:
                    closing_raw = closing_texts[0].get_text(strip=True)
                    # interpret closing date or semester
                    if "/" in closing_raw:
                        # Format: dd / mm / yyyy -> standardise
                        parts = [p.strip() for p in closing_raw.split("/")]
                        if len(parts) == 3:
                            day, month, year = parts
                            try:
                                dt = datetime.date(int(year), int(month), int(day))
                                # Skip calls closing in less than 7 days
                                if dt < datetime.date.today() + datetime.timedelta(days=7):
                                    continue
                                deadline_date = dt.strftime("%d %B %Y")
                            except Exception:
                                deadline_date = closing_raw
                        else:
                            deadline_date = closing_raw
                    elif "semestre" in closing_raw.lower():
                        # interpret semester
                        valid = _parse_semester_label(closing_raw)
                        if not valid:
                            continue
                        deadline_date = closing_raw
                    else:
                        # Unknown string; treat as deadline
                        deadline_date = closing_raw
        # Link: button with 'BUSCAR' or 'INSCRIPCIÓN', choose first anchor
        link = ""
        button_links = container.find_all("a", href=True)
        if button_links:
            # Use the first link
            link = button_links[0]["href"]
            # Ensure absolute URL if needed
            if link.startswith("/"):
                link = "https://www.mincultura.gov.co" + link
        # Append call
        calls.append({
            "title": title,
            "link": link,
            "opening_date": opening_date,
            "deadline_date": deadline_date,
            "description": description,
            # Classify ODS for the description
            "ods_list": classify_ods(description),
            # Human-readable site name
            "site": "MinCultura",
            # These programmes are cultural projects, not royalties
            "type": "Proyectos",
        })
        if len(calls) >= max_results:
            break
    return calls


__all__ = ["scrape_mincultura_calls"]