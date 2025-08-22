#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
anr_scraper.py
----------------

Scraper for the French National Research Agency (ANR) open calls page.

This module defines a single function, ``scrape_anr_calls``, which
visits the ANR open calls and pre‑announcements page filtered to
international opportunities.  It extracts up to ``max_results`` calls,
parses their opening and closing dates, fetches a description from the
detail page, summarises it using the local summariser and classifies
each call according to the Sustainable Development Goals (SDGs).  The
function also applies optional filters for a quick search theme, SDG
number and keyword.  Calls whose closing date is less than seven days
away from ``today`` are ignored.

The ANR site presents call cards inline on a single page.  Each call
title is embedded in an ``<h2>`` element containing an ``<a>`` child.
Immediately following this heading is a date range in the format
``dd/mm/yyyy - dd/mm/yyyy``.  We parse this range to obtain the
opening and closing dates.  Because the site is largely static, we
render the page with Selenium and then parse the HTML with
BeautifulSoup to simplify DOM traversal.

Functions
~~~~~~~~~
scrape_anr_calls(theme_filter: str, ods_number: str, keyword: str,
                 max_results: int, today: datetime.date) -> list[dict]
    Return a list of calls from ANR matching the provided filters.

"""

from __future__ import annotations

import datetime
import re
from typing import List, Dict

from bs4 import BeautifulSoup  # type: ignore
from selenium.webdriver.common.by import By  # type: ignore
from selenium.webdriver.support.ui import WebDriverWait  # type: ignore
from selenium.webdriver.support import expected_conditions as EC  # type: ignore

# Import local utilities directly to support running as a script.  We avoid
# relative imports so that this module can be imported without a package context.
from utils import create_driver, accept_cookies
from summarizer import summarize_text, classify_ods


def _parse_date(date_str: str) -> datetime.date | None:
    """Parse a date string in various formats into a ``datetime.date``.

    This helper attempts multiple common date formats.  If parsing
    fails, ``None`` is returned.

    Parameters
    ----------
    date_str : str
        A date string such as ``"06/01/2025"`` or ``"15/09/2025"``.

    Returns
    -------
    datetime.date or None
        Parsed date or ``None`` if parsing fails.
    """
    date_str = date_str.strip()
    for fmt in ["%d/%m/%Y", "%d %B %Y", "%d %b %Y", "%d %m %Y"]:
        try:
            return datetime.datetime.strptime(date_str, fmt).date()
        except Exception:
            continue
    # Try with day and month reversed (rare)
    try:
        return datetime.datetime.strptime(date_str.replace('-', '/'), "%Y/%m/%d").date()
    except Exception:
        return None


def scrape_anr_calls(theme_filter: str, ods_number: str, keyword: str,
                     max_results: int, today: datetime.date) -> List[Dict]:
    """Scrape international calls from the ANR portal.

    Parameters
    ----------
    theme_filter : str
        Keyword filter for the call title or summary.  If non‑empty,
        only calls whose title or summary contains this string (case
        insensitive) are returned.  The ANR site does not expose a
        quick search by theme; this parameter therefore acts as a
        post‑filter.
    ods_number : str
        SDG number to filter results by.  Empty string means no ODS
        filtering.
    keyword : str
        Additional keyword to search in title or summary.  Empty
        string means no keyword filter.
    max_results : int
        Maximum number of calls to return.  If zero or negative, an
        empty list is returned.
    today : datetime.date
        The current date used to decide if a call is still open (i.e.,
        closing date at least seven days away).

    Returns
    -------
    list of dict
        A list of call dictionaries with keys ``title``, ``link``,
        ``opening_date``, ``deadline_date``, ``description``,
        ``ods_list`` and ``site``.
    """
    results: List[Dict] = []
    if max_results <= 0:
        return results
    url = (
        "https://anr.fr/en/open-calls-and-preannouncements/?"
        "tx_solr%5Bfilter%5D%5B0%5D=international%253A1"
    )
    driver = create_driver()
    try:
        driver.get(url)
        accept_cookies(driver)
        # Wait for call cards to load
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.card.appel"))
            )
        except Exception:
            return results
        soup = BeautifulSoup(driver.page_source, "html.parser")
        # The ANR portal lists calls in div.card.appel elements.  Use
        # a CSS selector to collect them in document order.  We avoid
        # including non-call cards by requiring the 'appel' class.
        cards = soup.select("div.card.appel")
        seen_links = set()
        for card in cards:
            if len(results) >= max_results:
                break
            # Extract date range or month-year range
            opening_date = ""
            closing_date = ""
            date_div = card.find("div", class_=lambda c: c and "date" in c)
            if date_div:
                date_text = date_div.get_text(" ", strip=True)
                # Pattern: dd/mm/yyyy - dd/mm/yyyy
                m = re.search(r"(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})", date_text)
                if m:
                    opening_date = m.group(1)
                    closing_date = m.group(2)
                else:
                    # Pattern: MonthName YYYY - MonthName YYYY (English or French)
                    m2 = re.search(r"([A-Za-zÀ-ÿ]+\s+\d{4})\s*-\s*([A-Za-zÀ-ÿ]+\s+\d{4})", date_text)
                    if m2:
                        opening_date = m2.group(1).strip()
                        closing_date = m2.group(2).strip()
            # Parse closing date object (if we have dd/mm or spelled months).  For spelled months, we treat as unknown for date comparison.
            closing_date_obj: datetime.date | None = None
            if closing_date:
                # Attempt dd/mm parsing
                closing_date_obj = _parse_date(closing_date)
                if closing_date_obj is None:
                    # Try spelled months (English or French) to parse approximate date (use first day of month)
                    try:
                        parts = closing_date.strip().split()
                        if len(parts) == 2:
                            month_name = parts[0]
                            year = int(parts[1])
                            # Map French month names to english for parsing
                            fr_to_en = {
                                "janvier": "January", "février": "February", "fevrier": "February", "mars": "March",
                                "avril": "April", "mai": "May", "juin": "June", "juillet": "July",
                                "août": "August", "aout": "August", "septembre": "September", "octobre": "October",
                                "novembre": "November", "décembre": "December", "decembre": "December"
                            }
                            month_en = fr_to_en.get(month_name.lower(), month_name)
                            closing_date_obj = datetime.datetime.strptime(f"1 {month_en} {year}", "%d %B %Y").date()
                    except Exception:
                        closing_date_obj = None
            # Skip call if closing date exists and < 7 days from today
            if closing_date_obj is not None and (closing_date_obj - today).days < 7:
                continue
            # Extract title and link
            title = ""
            link = ""
            h2 = card.find("h2")
            if h2:
                a = h2.find("a")
                if a:
                    title = a.get_text(strip=True)
                    link = a.get("href") or ""
                    if link.startswith("/"):
                        link = "https://anr.fr" + link
            if not title or not link:
                continue
            # Skip duplicates
            if link in seen_links:
                continue
            seen_links.add(link)
            # Fetch description: first two paragraphs from detail page
            desc_text = ""
            try:
                detail_driver = create_driver()
                detail_driver.get(link)
                accept_cookies(detail_driver)
                detail_soup = BeautifulSoup(detail_driver.page_source, "html.parser")
                section = detail_soup.find("section", class_="content-style")
                paragraphs = []
                if section:
                    for p in section.find_all("p"):
                        text = p.get_text(" ", strip=True)
                        if text:
                            paragraphs.append(text)
                        if len(paragraphs) >= 2:
                            break
                desc_text = "\n".join(paragraphs)
            except Exception:
                desc_text = ""
            finally:
                try:
                    detail_driver.quit()
                except Exception:
                    pass
            text_for_summary = desc_text if desc_text else title
            summary = summarize_text(text_for_summary)
            ods_list = classify_ods(summary)
            # ODS filter
            if ods_number and ods_number not in ods_list:
                continue
            # Theme filter (post filter) and keyword
            lower_title = title.lower()
            lower_summary = summary.lower()
            if theme_filter:
                t = theme_filter.lower()
                if t not in lower_title and t not in lower_summary:
                    continue
            if keyword:
                k = keyword.lower()
                if k not in lower_title and k not in lower_summary:
                    continue
            # Convert opening and closing dates to day month name year format if needed; if the date string contains letters, convert French to English and keep as Month Year.
            def conv(d: str, prefer_last: bool = False) -> str:
                if not d:
                    return ""
                # dd/mm/yyyy
                obj = _parse_date(d)
                if obj:
                    return obj.strftime("%d %B %Y")
                # MonthName YYYY (French or English)
                parts_d = d.split()
                if len(parts_d) == 2:
                    month_fr = parts_d[0]
                    year = parts_d[1]
                    months_map = {
                        "janvier": "January", "février": "February", "fevrier": "February", "mars": "March",
                        "avril": "April", "mai": "May", "juin": "June", "juillet": "July",
                        "août": "August", "aout": "August", "septembre": "September", "octobre": "October",
                        "novembre": "November", "décembre": "December", "decembre": "December"
                    }
                    month_en = months_map.get(month_fr.lower(), month_fr)
                    return f"{month_en} {year}"
                return d
            opening_date_fmt = conv(opening_date)
            closing_date_fmt = conv(closing_date)
            results.append({
                "title": title,
                "link": link,
                "opening_date": opening_date_fmt,
                "deadline_date": closing_date_fmt,
                "description": summary,
                "ods_list": ods_list if ods_list else ["unknown"],
                "site": "ANR",
            })
    finally:
        try:
            driver.quit()
        except Exception:
            pass
    return results


__all__ = ["scrape_anr_calls"]