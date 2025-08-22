#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
idrc_scraper.py
----------------

Scraper for the International Development Research Centre (IDRC) funding
page.  The page lists open calls as well as closed calls; this
scraper extracts only the open calls, parses deadlines, fetches
details from each call page, summarises the content and classifies
according to SDGs.  Calls with deadlines less than seven days from
``today`` are skipped.  Optional filters by theme, SDG number and
keyword can be applied.

The IDRC funding page is relatively static, so BeautifulSoup suffices
to parse most information.  Selenium is used here for consistency
with other scrapers and to handle any potential client‑side
rendering.

Functions
~~~~~~~~~
scrape_idrc_calls(theme_filter: str, ods_number: str, keyword: str,
                  max_results: int, today: datetime.date) -> list[dict]
    Return a list of calls from IDRC matching the provided filters.

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
    """Attempt to parse a date from various common formats.

    Recognised formats include ``"September 17, 2025"``,
    ``"17 September 2025"`` and their abbreviations.  Returns
    ``None`` if parsing fails.
    """
    date_str = date_str.strip().replace(",", "")
    for fmt in ["%B %d %Y", "%d %B %Y", "%d %b %Y", "%d/%m/%Y"]:
        try:
            return datetime.datetime.strptime(date_str, fmt).date()
        except Exception:
            continue
    return None


def scrape_idrc_calls(theme_filter: str, ods_number: str, keyword: str,
                      max_results: int, today: datetime.date) -> List[Dict]:
    """Scrape open calls from the IDRC funding page.

    Parameters
    ----------
    theme_filter : str
        Keyword for theme filtering; matched against title and
        summary (case insensitive).  If empty, no theme filter is
        applied.
    ods_number : str
        SDG number to filter results by.  Empty string disables
        filtering.
    keyword : str
        Arbitrary keyword to filter calls by.  Case insensitive.  If
        empty, no keyword filter is applied.
    max_results : int
        Maximum number of calls to return.  Zero or negative
        returns an empty list.
    today : datetime.date
        Current date used to skip calls closing soon (within 7 days).

    Returns
    -------
    list of dict
        Call dictionaries containing ``title``, ``link``,
        ``opening_date`` (empty for IDRC), ``deadline_date``,
        ``description``, ``ods_list`` and ``site``.
    """
    results: List[Dict] = []
    if max_results <= 0:
        return results
    url = "https://idrc-crdi.ca/en/funding"
    driver = create_driver()
    try:
        driver.get(url)
        accept_cookies(driver)
        # Wait for view rows to load
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.views-row"))
            )
        except Exception:
            return results
        soup = BeautifulSoup(driver.page_source, "html.parser")
        # Find all rows representing calls
        rows = soup.find_all("div", class_="views-row")
        for row in rows:
            if len(results) >= max_results:
                break
            try:
                title_div = row.find("div", class_="views-field-title")
                if not title_div:
                    continue
                a_tag = title_div.find("a")
                if not a_tag:
                    continue
                title = a_tag.get_text(strip=True)
                link = a_tag.get("href", "")
                if link.startswith("/"):
                    link = "https://idrc-crdi.ca" + link
                # Deadline
                deadline_div = row.find("div", class_="views-field-field-award-deadline")
                deadline_text = ""
                if deadline_div:
                    time_tag = deadline_div.find("time")
                    if time_tag and time_tag.has_attr("datetime"):
                        # datetime attribute like 2025-09-18T03:59:00Z
                        date_attr = time_tag.get("datetime")
                        # parse as YYYY-MM-DD and convert
                        try:
                            date_obj = datetime.datetime.fromisoformat(date_attr.replace("Z", "")).date()
                            deadline_text = date_obj.strftime("%d %B %Y")
                        except Exception:
                            pass
                    else:
                        # fallback to text
                        deadline_text = deadline_div.get_text(" ", strip=True).replace("Deadline:", "").strip()
                # Skip if deadline is too soon
                deadline_date_obj = _parse_date(deadline_text) if deadline_text else None
                if deadline_date_obj is not None and (deadline_date_obj - today).days < 7:
                    continue
                # Fetch description from detail page: get first three paragraphs after Scope
                desc_text = ""
                try:
                    detail_driver = create_driver()
                    detail_driver.get(link)
                    accept_cookies(detail_driver)
                    detail_soup = BeautifulSoup(detail_driver.page_source, "html.parser")
                    body_div = detail_soup.find("div", class_="field field--name-field-body field--type-text-long field--label-hidden field__item")
                    paragraphs = []
                    if body_div:
                        # Find <h3> Scope and collect next siblings paragraphs
                        h3_scope = body_div.find("h3", string=lambda t: t and "scope" in t.lower())
                        if h3_scope:
                            # iterate siblings after h3_scope
                            for sib in h3_scope.find_all_next():
                                if sib.name == "p":
                                    text = sib.get_text(" ", strip=True)
                                    if text:
                                        paragraphs.append(text)
                                if len(paragraphs) >= 3:
                                    break
                        # If not enough paragraphs collected, fallback to first three <p> in body
                        if not paragraphs:
                            for p in body_div.find_all("p"):
                                text = p.get_text(" ", strip=True)
                                if text:
                                    paragraphs.append(text)
                                if len(paragraphs) >= 3:
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
                # Theme filter (search in title and summary)
                if theme_filter:
                    t = theme_filter.lower()
                    if t not in title.lower() and t not in summary.lower():
                        continue
                # Keyword filter
                if keyword:
                    k = keyword.lower()
                    if k not in title.lower() and k not in summary.lower():
                        continue
                results.append({
                    "title": title,
                    "link": link,
                    "opening_date": "",
                    "deadline_date": deadline_text,
                    "description": summary,
                    "ods_list": ods_list if ods_list else ["unknown"],
                    "site": "IDRC",
                })
            except Exception:
                continue
        return results
    finally:
        try:
            driver.quit()
        except Exception:
            pass


__all__ = ["scrape_idrc_calls"]