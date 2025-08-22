#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
eu_scraper.py
---------------

Functions specific to scraping the European Commission calls for proposals
portal.  This module exposes utilities to load paginated lists of calls
and to extract topic descriptions from individual call pages.  It does
not perform summary generation or classification; those tasks are
handled by the main application.

Functions
~~~~~~~~~
get_calls_page(driver, theme: str, page_number: int) -> list[dict]
    Retrieve metadata for calls on a given page, optionally filtered
    by a theme keyword.

fetch_and_extract_description(driver, url: str) -> str
    Download a call details page and extract all textual content under
    the 'Topic description' card.  Returns an empty string if the
    section cannot be located.

"""

from __future__ import annotations

from urllib.parse import quote, urljoin
from typing import List, Dict

from bs4 import BeautifulSoup  # type: ignore
from selenium.webdriver.common.by import By  # type: ignore
from selenium.webdriver.support.ui import WebDriverWait  # type: ignore
from selenium.webdriver.support import expected_conditions as EC  # type: ignore

from utils import create_driver, accept_cookies

BASE_URL = "https://ec.europa.eu"


def get_calls_page(driver, theme: str, page_number: int) -> List[Dict[str, str]]:
    """Retrieve call metadata from the EU portal for a specific page.

    Parameters
    ----------
    driver : selenium.webdriver.Chrome
        A Chrome WebDriver instance.
    theme : str
        A theme keyword used for quick search on the portal.  If blank,
        no keywords parameter is added.
    page_number : int
        The page number (1-indexed) to retrieve.

    Returns
    -------
    list of dict
        Each dict contains 'title', 'link', 'opening_date' and 'deadline_date'.
    """
    # Build search URL with optional keywords
    base_params = (
        f"order=ASC&pageNumber={page_number}&pageSize=100&sortBy=deadlineDate"
        "&isExactMatch=true&status=31094501,31094502"
    )
    if theme:
        encoded = quote(theme)
        search_url = (
            "https://ec.europa.eu/info/funding-tenders/opportunities/portal/"
            "screen/opportunities/calls-for-proposals?" + base_params + f"&keywords={encoded}"
        )
    else:
        search_url = (
            "https://ec.europa.eu/info/funding-tenders/opportunities/portal/"
            "screen/opportunities/calls-for-proposals?" + base_params
        )
    driver.get(search_url)
    accept_cookies(driver)
    # Wait for call cards
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "eui-card-header-title a.eui-u-text-link")
            )
        )
    except Exception:
        return []
    soup = BeautifulSoup(driver.page_source, "html.parser")
    cards = (
        soup.select("sedia-result-card-calls-for-proposals")
        or soup.select("eui-card[data-e2e='eui-card']")
    )
    meta = []
    for card in cards:
        a = card.select_one("eui-card-header-title a.eui-u-text-link")
        if not a:
            continue
        title = a.get_text(strip=True)
        link = urljoin(BASE_URL, a["href"])
        opening = ""
        deadline = ""
        sub = card.select_one("eui-card-header-subtitle")
        if sub:
            types = sub.select("sedia-result-card-type")
            if len(types) >= 2:
                strongs = types[1].find_all("strong")
                if len(strongs) >= 2:
                    opening = strongs[0].get_text(strip=True)
                    deadline = strongs[1].get_text(strip=True)
        meta.append({
            "title": title,
            "link": link,
            "opening_date": opening,
            "deadline_date": deadline,
        })
    return meta


def fetch_and_extract_description(driver, url: str) -> str:
    """Extract textual content from a call's detail page.

    This function navigates to the given URL, waits for the page
    content to load, then attempts to extract textual content from
    either the "Topic description" card or, if not present, the
    "Further information" section.  It collects paragraphs and list
    items from the topic description; in the fallback case it
    collects the first four paragraphs under the further information
    section, stripping hyperlinks.  The returned string may span
    multiple lines separated by newlines.

    Parameters
    ----------
    driver : selenium.webdriver.Chrome
        A Chrome WebDriver instance.
    url : str
        The full URL of the call's detail page.

    Returns
    -------
    str
        Concatenated text from the selected sections.  Empty if no
        content could be extracted.
    """
    driver.get(url)
    accept_cookies(driver)
    # Wait briefly for either the topic description header or the
    # further information section to load.  We do not return early
    # if one is missing; instead we proceed to parse whichever is
    # available.
    try:
        WebDriverWait(driver, 15).until(
            EC.any_of(
                EC.presence_of_element_located(
                    (By.XPATH, "//eui-card-header-title[contains(., 'Topic description')]")
                ),
                EC.presence_of_element_located((By.ID, "scroll-fi"))
            )
        )
    except Exception:
        # Timeout is not fatal; parsing may still succeed if the
        # page loaded but our expected elements were not found.
        pass
    soup = BeautifulSoup(driver.page_source, "html.parser")
    parts: list[str] = []
    # Attempt to extract from the Topic description card
    header = soup.find(
        "eui-card-header-title", string=lambda t: t and "Topic description" in t
    )
    if header:
        card = header.find_parent("eui-card")
        if card:
            content = card.find("eui-card-content")
            if content:
                for elem in content.find_all(["p", "li"]):
                    text = elem.get_text(" ", strip=True)
                    if text:
                        if elem.name == "li":
                            parts.append(f"- {text}")
                        else:
                            parts.append(text)
    # Fallback: extract paragraphs from the 'Further information' section
    # if the Topic description yields no content.  The further
    # information section lives in a <section> with id="scroll-fi".
    if not parts:
        fi_section = soup.find("section", id="scroll-fi")
        if fi_section:
            data_div = fi_section.find("div", class_=lambda c: c and c.startswith("sedia-base"))
            if data_div:
                count = 0
                for p in data_div.find_all("p"):
                    # Remove any <a> tags to ignore hyperlink text
                    for a in p.find_all("a"):
                        a.decompose()
                    text = p.get_text(" ", strip=True)
                    if text:
                        parts.append(text)
                        count += 1
                    if count >= 4:
                        break
    return "\n".join(parts)


__all__ = ["get_calls_page", "fetch_and_extract_description"]