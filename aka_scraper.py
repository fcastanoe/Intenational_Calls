#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
aka_scraper.py
---------------

Scraper for the Academy of Finland (AKA) funding portal.  This scraper
focuses on the section "International calls" and extracts basic
metadata as well as a local summary and SDG classification for each
call.  Calls whose closing date is less than seven days from the
current date are excluded.

Functions
~~~~~~~~~
scrape_aka_calls(theme_filter: str, ods_number: str, keyword: str,
                 max_results: int, today: datetime.date) -> list[dict]
    Scrape the AKA portal for international calls matching the provided
    filters.

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


def scrape_aka_calls(theme_filter: str, ods_number: str, keyword: str,
                     max_results: int, today: datetime.date) -> List[Dict]:
    """Scrape international calls from the Academy of Finland.

    Parameters
    ----------
    theme_filter : str
        Not used for AKA calls.  Included for consistency.
    ods_number : str
        SDG number to filter results by.  Empty means no filter.
    keyword : str
        Keyword to search in title or summary (lowercase).  Empty means no keyword filter.
    max_results : int
        Maximum number of calls to return.
    today : datetime.date
        Current date for deadline checks.

    Returns
    -------
    list of dict
        List of call metadata and summaries matching the filters.
    """
    results = []
    if max_results <= 0:
        return results
    url = "https://www.aka.fi/en/research-funding/apply-for-funding/calls-for-applications"
    driver = create_driver()
    try:
        driver.get(url)
        # Accept cookies
        try:
            btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Accept all')]")
            btn.click()
        except Exception:
            pass
        # Wait for application-box elements
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.application-box"))
            )
        except Exception:
            return results
        soup = BeautifulSoup(driver.page_source, "html.parser")
        # Find the row following the 'International calls' heading
        int_heading = soup.find(lambda tag: tag.name in ["h2", "h3"] and "international calls" in tag.get_text(strip=True).lower())
        boxes = []
        if int_heading:
            # Gather application boxes under the same row or subsequent rows until next heading
            row = int_heading.find_parent("div", class_="row")
            if row:
                boxes = row.find_all("div", class_="application-box")
                # If no boxes found in this row, look in next sibling rows
                if not boxes:
                    sibling = row.find_next_sibling("div", class_="row")
                    if sibling:
                        boxes = sibling.find_all("div", class_="application-box")
        # Iterate over each call box
        for box in boxes:
            if len(results) >= max_results:
                break
            try:
                a_tag = box.find("a")
                if not a_tag:
                    continue
                title = a_tag.get_text(strip=True)
                link = a_tag.get("href")
                if link and link.startswith("/"):
                    link = "https://www.aka.fi" + link
                # Opening and closing dates
                opening_date = ""
                closing_date = ""
                start_div = box.find("div", class_=lambda c: c and "app-start" in c)
                if start_div:
                    text = start_div.get_text(" ", strip=True)
                    # Remove the label 'Call opens' or 'opens'
                    parts = text.replace("Call opens", "").replace("opens", "").strip().split()
                    if len(parts) >= 3:
                        opening_date = " ".join(parts[-3:])
                end_div = box.find("div", class_=lambda c: c and "app-end" in c)
                if end_div:
                    text = end_div.get_text(" ", strip=True)
                    parts = text.replace("Call closes", "").replace("closes", "").strip().split()
                    if len(parts) >= 3:
                        closing_date = " ".join(parts[-3:])
                # Parse closing date and skip if <7 days away
                closing_date_obj = None
                if closing_date:
                    for fmt in ["%d %b %Y", "%d %B %Y", "%d %m %Y"]:
                        try:
                            closing_date_obj = datetime.datetime.strptime(closing_date, fmt).date()
                            break
                        except Exception:
                            continue
                if closing_date_obj is not None and (closing_date_obj - today).days < 7:
                    continue
                # Fetch description from detail page: take paragraphs until 'More information'
                desc_text = ""
                try:
                    detail_driver = create_driver()
                    detail_driver.get(link)
                    try:
                        d_btn = detail_driver.find_element(By.XPATH, "//button[contains(text(), 'Accept all')]")
                        d_btn.click()
                    except Exception:
                        pass
                    detail_soup = BeautifulSoup(detail_driver.page_source, "html.parser")
                    paragraphs = []
                    for elem in detail_soup.find_all(["p", "h2"]):
                        if elem.name == "h2" and "more information" in elem.get_text(strip=True).lower():
                            break
                        if elem.name == "p":
                            text_p = elem.get_text(" ", strip=True)
                            if text_p:
                                paragraphs.append(text_p)
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
                # Apply ODS filter
                if ods_number and ods_number not in ods_list:
                    continue
                # Apply theme filter: not directly supported on AKA page
                if theme_filter:
                    t = theme_filter.lower()
                    if t not in title.lower() and t not in summary.lower():
                        continue
                # Apply keyword filter
                if keyword:
                    k = keyword.lower()
                    if k not in title.lower() and k not in summary.lower():
                        continue
                results.append({
                    "title": title,
                    "link": link,
                    "opening_date": opening_date,
                    "deadline_date": closing_date,
                    "description": summary,
                    "ods_list": ods_list if ods_list else ["unknown"],
                    "site": "AKA",
                })
            except Exception:
                continue
        return results
    finally:
        try:
            driver.quit()
        except Exception:
            pass


__all__ = ["scrape_aka_calls"]