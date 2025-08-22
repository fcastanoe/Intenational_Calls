#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ibro_scraper.py
----------------

Scraper for the IBRO (International Brain Research Organization) grants
page.  This scraper focuses on open calls listed under the ``open-calls``
tab and selects only those opportunities open to "International"
applicants.  For each eligible call it extracts the application
opening and closing dates (when available), fetches the detail page to
gather descriptive text, summarises it locally, classifies according
to SDGs and applies optional filters for theme, ODS and keywords.

Because the IBRO site loads content dynamically, Selenium is used to
render the page.  Calls are discovered by selecting anchor elements
within the open calls tab.  The detail page for each call is then
opened in a separate browser instance to extract the necessary
information.

Functions
~~~~~~~~~
scrape_ibro_calls(theme_filter: str, ods_number: str, keyword: str,
                  max_results: int, today: datetime.date) -> list[dict]
    Return up to ``max_results`` calls matching the provided filters.

"""

from __future__ import annotations

import datetime
import re
from typing import List, Dict

from bs4 import BeautifulSoup  # type: ignore
from selenium.webdriver.common.by import By  # type: ignore
from selenium.webdriver.support.ui import WebDriverWait  # type: ignore
from selenium.webdriver.support import expected_conditions as EC  # type: ignore

from utils import create_driver, accept_cookies
from summarizer import summarize_text, classify_ods


def _parse_date(date_str: str) -> datetime.date | None:
    """Parse a date string into ``datetime.date`` if possible.

    Accepts formats such as ``"10 Jun 2025"``, ``"15 October 2025"`` or
    ``"06/01/2025"``.  Returns ``None`` on failure.
    """
    date_str = date_str.strip().replace(",", "")
    for fmt in ["%d %b %Y", "%d %B %Y", "%d/%m/%Y", "%m/%d/%Y"]:
        try:
            return datetime.datetime.strptime(date_str, fmt).date()
        except Exception:
            continue
    return None


def scrape_ibro_calls(theme_filter: str, ods_number: str, keyword: str,
                      max_results: int, today: datetime.date) -> List[Dict]:
    """Scrape IBRO open calls for international applicants.

    Parameters
    ----------
    theme_filter : str
        Keyword used to filter calls by theme; matched against title
        and summary (case insensitive).  If empty, no theme filter is
        applied.
    ods_number : str
        SDG number to filter results.  Empty string means no ODS
        filtering.
    keyword : str
        Arbitrary keyword to filter calls; matched against title and
        summary (case insensitive).  Empty string disables the filter.
    max_results : int
        Maximum number of calls to return.  Zero or negative values
        return an empty list.
    today : datetime.date
        Current date used to skip calls closing in less than seven
        days.

    Returns
    -------
    list of dict
        Call dictionaries containing ``title``, ``link``,
        ``opening_date``, ``deadline_date``, ``description``,
        ``ods_list`` and ``site``.
    """
    results: List[Dict] = []
    if max_results <= 0:
        return results
    url = "https://ibro.org/grants/?tab=open-calls"
    driver = create_driver()
    try:
        driver.get(url)
        accept_cookies(driver)
        # Wait for the post-tiles container to load
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.post-tiles"))
            )
        except Exception:
            return results
        soup = BeautifulSoup(driver.page_source, "html.parser")
        # Find all call tiles within the open calls section
        tiles = soup.find_all("div", class_="call-tile")
        for tile in tiles:
            if len(results) >= max_results:
                break
            try:
                # Title
                title_el = tile.find("h3", class_="title-calls-events-list")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                # Find the clickable anchor that wraps this call tile.  The
                # structure of the IBRO site places each call inside an
                # <a class="clickable-tile"> element, which itself
                # contains a <div class="post-tile"> and then
                # <div class="call-tile">.  Therefore, we search up
                # the ancestor chain for the nearest clickable-tile
                # anchor to obtain the call URL.
                link = ""
                ancestor = tile
                while ancestor is not None:
                    if ancestor.name == "a" and ancestor.get("href"):
                        link = ancestor.get("href")
                        break
                    ancestor = ancestor.parent
                if not link:
                    continue
                # Extract info fields
                grant_aim = ""
                open_to = ""
                opening_date = ""
                closing_date = ""
                for b in tile.find_all("b"):
                    label = b.get_text(" ", strip=True).lower()
                    # The value typically follows the bold tag as a text node or within the same parent
                    value = ""
                    # gather next siblings (NavigableString or tag) until <br>
                    for sib in b.next_siblings:
                        if getattr(sib, "name", None) == "br":
                            break
                        v_text = ""
                        if isinstance(sib, str):
                            v_text = sib.strip()
                        else:
                            v_text = sib.get_text(" ", strip=True)
                        if v_text:
                            value += (" " + v_text) if value else v_text
                    value = value.strip()
                    if "grant aim" in label:
                        grant_aim = value
                    elif "open to" in label:
                        open_to = value
                    elif "application start date" in label:
                        opening_date = value
                    elif "application deadline" in label:
                        closing_date = value
                # Ensure open to is international
                if open_to and "international" not in open_to.lower():
                    continue
                # Parse dates; treat "Program dependent" or "event dependent" as None
                def parse_ibro_date(ds: str) -> datetime.date | None:
                    if not ds or ds.lower().startswith("program dependent") or ds.lower().startswith("event dependent"):
                        return None
                    return _parse_date(ds)
                opening_obj = parse_ibro_date(opening_date)
                closing_obj = parse_ibro_date(closing_date)
                # Skip if closing date exists and <7 days
                if closing_obj is not None and (closing_obj - today).days < 7:
                    continue
                # Use the grant aim for description; if empty fallback to title
                text_for_summary = grant_aim if grant_aim else title
                summary = summarize_text(text_for_summary)
                ods_list = classify_ods(summary)
                # ODS filter
                if ods_number and ods_number not in ods_list:
                    continue
                # Theme filter: search in title and summary
                if theme_filter:
                    t = theme_filter.lower()
                    if t not in title.lower() and t not in summary.lower():
                        continue
                # Keyword filter
                if keyword:
                    kw = keyword.lower()
                    if kw not in title.lower() and kw not in summary.lower():
                        continue
                results.append({
                    "title": title,
                    "link": link,
                    "opening_date": opening_date,
                    "deadline_date": closing_date,
                    "description": summary,
                    "ods_list": ods_list if ods_list else ["unknown"],
                    "site": "IBRO",
                })
            except Exception:
                continue
        return results
    finally:
        try:
            driver.quit()
        except Exception:
            pass


__all__ = ["scrape_ibro_calls"]