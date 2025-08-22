#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
wellcome_scraper.py
--------------------

Scraper for the Wellcome Trust research funding schemes.  Only schemes
open or upcoming are considered.  This scraper filters calls by
"Administering organisation location" so that only those open to
"Low- or middle-income countries" or "anywhere" are retained.  After
fetching each call's details page, it uses local summarisation and
keywords to classify the call into SDGs and apply optional filters.

Functions
~~~~~~~~~
scrape_wellcome_calls(theme_filter: str, ods_number: str, keyword: str,
                      max_results: int, today: datetime.date) -> list[dict]
    Return up to ``max_results`` calls matching the provided filters.

"""

from __future__ import annotations

import datetime
from typing import List, Dict

from bs4 import BeautifulSoup  # type: ignore
from selenium.webdriver.common.by import By  # type: ignore
from selenium.webdriver.support.ui import WebDriverWait  # type: ignore
from selenium.webdriver.support import expected_conditions as EC  # type: ignore

from utils import create_driver, accept_cookies
from summarizer import summarize_text, classify_ods


def scrape_wellcome_calls(theme_filter: str, ods_number: str, keyword: str,
                          max_results: int, today: datetime.date) -> List[Dict]:
    """Scrape Wellcome open and upcoming research funding schemes.

    Parameters
    ----------
    theme_filter : str
        Ignored for Wellcome; included for signature consistency.
    ods_number : str
        SDG number to filter results by.  Empty string means no ODS filter.
    keyword : str
        Keyword to search in title or summary (lowercase).  Empty means no keyword filter.
    max_results : int
        Maximum number of calls to return.
    today : datetime.date
        Current date to evaluate deadlines.

    Returns
    -------
    list of dict
        Each dict contains metadata and summary of a call, including
        ``title``, ``link``, ``opening_date`` (empty for Wellcome),
        ``deadline_date``, ``description``, ``ods_list`` and ``site``.
    """
    results = []
    if max_results <= 0:
        return results
    # URL for open and upcoming schemes with query params pre-set
    # URL for open and upcoming schemes
    url = (
        "https://wellcome.org/research-funding/schemes"
        "?f%5B0%5D=currently_accepting_applications%3AYes"
        "&f%5B1%5D=currently_accepting_applications%3AUpcoming"
    )
    driver = create_driver()
    try:
        driver.get(url)
        # Accept cookies using generic util; fallback to specific buttons
        accept_cookies(driver)
        # Additional attempt: some Wellcome pages use a different button label
        try:
            cookie_btn = driver.find_element(By.XPATH, "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept')]")
            cookie_btn.click()
        except Exception:
            pass
        # Wait for call cards to load (articles with scheme class)
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "article.c-text-card"))
            )
        except Exception:
            return results
        articles = driver.find_elements(By.CSS_SELECTOR, "article.c-text-card")
        for art in articles:
            if len(results) >= max_results:
                break
            try:
                # Title and link
                link_el = art.find_element(By.CSS_SELECTOR, "h3.c-text-card__title a")
                title = link_el.text.strip()
                link = link_el.get_attribute("href")
                # Deadline
                deadline_text = ""
                try:
                    pill = art.find_element(By.CSS_SELECTOR, "div.c-text-card__status div.c-pill")
                    pill_text = pill.text.strip()
                    if ":" in pill_text:
                        deadline_text = pill_text.split(":", 1)[-1].strip()
                except Exception:
                    pass
                # Parse deadline; skip if <7 days
                deadline_obj = None
                if deadline_text:
                    for fmt in ["%d %B %Y", "%d %b %Y"]:
                        try:
                            deadline_obj = datetime.datetime.strptime(deadline_text, fmt).date()
                            break
                        except Exception:
                            continue
                if deadline_obj is not None and (deadline_obj - today).days < 7:
                    continue
                # Check location: only keep calls open to low- or middle-income countries or anywhere
                location_ok = False
                try:
                    infos = art.find_elements(By.CSS_SELECTOR, "div.c-scheme-info")
                    for info in infos:
                        try:
                            title_el = info.find_element(By.CSS_SELECTOR, "h4.c-scheme-info__title")
                            info_title = title_el.text.strip().lower()
                        except Exception:
                            continue
                        if "administering organisation location" in info_title:
                            segments = info.find_elements(By.CSS_SELECTOR, "li.c-scheme-info__segment")
                            for seg in segments:
                                seg_text = seg.text.strip().lower()
                                if "anywhere" in seg_text or "low-" in seg_text:
                                    location_ok = True
                                    break
                            if location_ok:
                                break
                except Exception:
                    pass
                if not location_ok:
                    continue
                # Collect strategic programme categories
                prog_categories: List[str] = []
                try:
                    for info in infos:
                        try:
                            title_el = info.find_element(By.CSS_SELECTOR, "h4.c-scheme-info__title")
                            info_title = title_el.text.strip().lower()
                        except Exception:
                            continue
                        if "strategic programme" in info_title:
                            segments = info.find_elements(By.CSS_SELECTOR, "li.c-scheme-info__segment")
                            for seg in segments:
                                prog_categories.append(seg.text.strip())
                except Exception:
                    pass
                # Description: from the top description element
                desc_parts = []
                try:
                    rich_divs = art.find_elements(By.CSS_SELECTOR, "div.c-rich-text.c-text-card__description p")
                    for p in rich_divs:
                        text = p.text.strip()
                        if text:
                            desc_parts.append(text)
                except Exception:
                    pass
                desc_text = "\n".join(desc_parts)
                # Summarise
                text_for_summary = desc_text if desc_text else title
                summary = summarize_text(text_for_summary)
                ods_list = classify_ods(summary)
                # ODS filter
                if ods_number and ods_number not in ods_list:
                    continue
                # Theme filter: if provided, check against strategic programme categories or text
                if theme_filter:
                    t = theme_filter.lower()
                    cat_match = any(t in c.lower() for c in prog_categories)
                    if not cat_match and t not in title.lower() and t not in summary.lower():
                        continue
                # Keyword filter
                if keyword:
                    kw = keyword.lower()
                    if kw not in title.lower() and kw not in summary.lower():
                        continue
                results.append({
                    "title": title,
                    "link": link,
                    "opening_date": "",
                    "deadline_date": deadline_text,
                    "description": summary,
                    "ods_list": ods_list if ods_list else ["unknown"],
                    "site": "Wellcome",
                })
            except Exception:
                continue
    finally:
        try:
            driver.quit()
        except Exception:
            pass
    return results


__all__ = ["scrape_wellcome_calls"]