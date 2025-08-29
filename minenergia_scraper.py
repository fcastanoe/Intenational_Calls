"""
minenergia_scraper.py
======================

Scraper for the Colombian Ministry of Mines and Energy (MinEnergía)
royalty calls.  The ministry periodically publishes an "Incentivo a
la Producción" (IP) call within the Sistema General de Regalías.  The
URL for the call follows a pattern that includes the biennium year,
e.g. ``https://www.minenergia.gov.co/es/misional/sistema-general-de-
regalias/convocatoria-ip-2025``.

This module provides a function to extract the call information
programmatically.  It attempts to fetch both the main page to obtain
a description and a separate "cronograma" page to determine the
closing date.  If either page is unavailable the function returns
an empty list.

Usage::

    from minenergia_scraper import scrape_minenergia_calls
    calls = scrape_minenergia_calls(year=2025)
    for call in calls:
        print(call["title"], call["deadline_date"])

Each call dictionary contains the keys ``title``, ``link``,
``opening_date``, ``deadline_date``, ``description`` and
``ods_list``.  ``ods_list`` is always ``['unknown']`` for MinEnergía
calls as no specific SDG classification is attempted.
"""

from __future__ import annotations

import datetime
from typing import List, Dict

from http_utils import fetch_page, parse_html
from summarizer import summarize_text, classify_ods


def scrape_minenergia_calls(year: int | None = None, max_results: int = 10) -> List[Dict[str, str]]:
    """Scrape the MinEnergía IP call for the given year.

    Parameters
    ----------
    year: int, optional
        The biennium year to query.  Defaults to the current year if
        omitted.  If the page for the specified year does not exist
        the function returns an empty list.
    max_results: int, optional
        Maximum number of call entries to return.  For MinEnergía
        this is effectively one, but the argument is provided for
        consistency with other scrapers.

    Returns
    -------
    list[dict]
        A list containing at most one call dictionary.  The list is
        empty when no call is available for the given year or when
        the closing date is less than seven days from today.
    """
    if year is None:
        year = datetime.date.today().year
    base_url = f"https://www.minenergia.gov.co/es/misional/sistema-general-de-regalias/convocatoria-ip-{year}"
    cronograma_url = f"{base_url}/cronograma"

    # Attempt to fetch the description page
    try:
        html = fetch_page(base_url)
    except Exception:
        # Page not found or other error
        return []
    soup = parse_html(html)

    # Extract description paragraphs from the intro section
    description = ""
    intro_section = soup.find(id="intro-convocatoria")
    if intro_section:
        paragraphs = intro_section.find_all("p")
        combined = " ".join(p.get_text(strip=True) for p in paragraphs)
        description = summarize_text(combined)

    # Extract closing date from the cronograma page
    deadline_date_str = ""
    try:
        cron_html = fetch_page(cronograma_url)
        cron_soup = parse_html(cron_html)
        # Look for list items containing "Cierre de la convocatoria"
        items = cron_soup.find_all("li")
        for li in items:
            fecha_span = li.find("div", class_="fecha")
            if fecha_span and "cierre" in fecha_span.get_text(strip=True).lower():
                # Find the inner div with the date text
                label = li.find("strong", string=lambda s: s and "Fecha de finalización" in s)
                if label:
                    parent = label.find_parent()
                    if parent:
                        # The date appears after the label inside the paragraph
                        date_text = label.find_next(string=True)
                        if date_text:
                            deadline_date_str = date_text.strip()
                            break
    except Exception:
        # If cronograma page fails, leave deadline empty
        deadline_date_str = ""

    # Convert deadline date from dd/mm/yyyy to a more readable format
    deadline_formatted = ""
    if deadline_date_str:
        try:
            # Dates on cronograma page use dd/mm/yyyy
            day, month, year_str = deadline_date_str.split("/")
            dt = datetime.date(int(year_str), int(month), int(day))
            # Skip calls that close in less than 7 days
            if dt < datetime.date.today() + datetime.timedelta(days=7):
                return []
            deadline_formatted = dt.strftime("%d %B %Y")
        except Exception:
            deadline_formatted = deadline_date_str

    if not description and not deadline_formatted:
        # If we can't extract any meaningful information, skip
        return []

    call = {
        "title": "Convocatoria Regalías Minenergía",
        "link": base_url,
        "opening_date": "",
        "deadline_date": deadline_formatted,
        "description": description,
        # Classify ODS for completeness; however these calls are typically general development projects.
        "ods_list": classify_ods(description),
        # Identify the ministry as the site for display purposes.
        "site": "MinEnergía",
        # Mark the type of call. All MinEnergía calls scraped here are regalías.
        "type": "Regalías",
    }
    return [call]


__all__ = ["scrape_minenergia_calls"]