#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
main_gui.py
-----------

Entry point for the multi‑page calls scraper application.  This
module defines a Tkinter-based graphical interface that allows the
user to search research funding calls across multiple funding portals:

* European Commission calls for proposals (EU)
* Wellcome Trust research funding schemes (Wellcome)
* Academy of Finland international calls (AKA)
* French ANR international calls (ANR)
* International Brain Research Organization grants (IBRO)
* International Development Research Centre open calls (IDRC)

The user can select a line theme (quick search keyword used mainly
for the EU portal but also as a post‑filter on other sites), an SDG
number, an arbitrary keyword, the number of results to display, and a
specific funding portal to query or "All" to query every portal.

The application caches results for the European Commission portal
based on the chosen theme and SDG to avoid repeatedly scraping and
summarising the same calls.  Caches are stored under
``data/cache/``.  For other portals the number of calls is limited
and caching is omitted.

Summary generation and SDG classification are performed locally via
the ``summarizer`` module, avoiding reliance on external APIs.

"""

from __future__ import annotations

import os
import csv
import time
import datetime
import re
import webbrowser
from typing import List, Dict, Tuple

import tkinter as tk
from tkinter import ttk, scrolledtext

# Import local modules directly to support running as a script.  We avoid
# relative imports so that this file can be executed without setting
# __package__.
from summarizer import summarize_text, classify_ods
from utils import create_driver, accept_cookies
from eu_scraper import get_calls_page, fetch_and_extract_description
from wellcome_scraper import scrape_wellcome_calls
from aka_scraper import scrape_aka_calls
from anr_scraper import scrape_anr_calls
from ibro_scraper import scrape_ibro_calls
from idrc_scraper import scrape_idrc_calls

# Bring in the generic cached scrape helper so that non‑EU sites
# persist results across application restarts.  This helper
# encapsulates loading, filtering, scraping and saving cache files
# under data/cache/ for each combination of portal, theme and SDG.
# ``cached_scrape`` is defined in this module below.  It is used
# to wrap scrapers for non‑EU sites so that their results are
# persisted across sessions via CSV caches in ``data/cache``.


###############################################################################
# Configuration and constants
###############################################################################

# Directory for cached results and output CSV.  These are located
# relative to this source file so that caches persist regardless of
# where the script is executed from.  When the application starts,
# it ensures the subdirectories exist.  The cache stores a CSV per
# site/theme/ODS combination (e.g. ``cache_european_commission_health_3.csv``).
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "data", "cache")
OUTPUT_DIR = os.path.join(BASE_DIR, "data", "scraping_results")
CSV_PATH = os.path.join(OUTPUT_DIR, "calls_for_proposals.csv")

# Ensure directories exist at runtime
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Available line themes (keywords).  These are suggestions; users may
# still type arbitrary keywords in the keywords field.
THEME_OPTIONS = [
    "Artificial Intelligence", "Robotics", "Cybersecurity",
    "Biotechnology", "Health", "Medical Research", "Climate Change",
    "Renewable Energy", "Sustainable Agriculture", "Smart Cities",
    "Digital Transformation", "Green Technologies",
    "Environmental Conservation", "Water Management", "Urban Mobility",
    "Clean Technologies", "Space Research", "Transport Innovation",
    "Food Security", "Social Innovation", "Inclusive Society",
    "Cultural Heritage", "Climate Action", "Education and Skills",
    "Public Safety", "Manufacturing and Industry", "Waste Management",
    "Energy Efficiency", "Digital Economy", "Public Health",
    # Additional categories encountered in portal quick search
    "Social sciences and humanities", "International cooperation",
    "Gender", "Digital Agenda", "Social sciences, interdisciplinary",
    "Environment, resources and sustainability",
    "Political systems and institutions / governance",
    "Circular economy", "Responsible Research and Innovation",
    "Entrepreneurship", "Climate change adaptation", "Technological innovation",
    "Renewable energy sources - general", "Societal Engagement",
    "Accelerating Clean Energy Innovation", "Chemical engineering",
    "Energy efficiency - general", "Technology development", "Hydrogen",
    "Mechanical engineering", "Agriculture, Rural Development, Fisheries",
    "Internet of Things", "Energy", "Rail Transport", "Sustainable transport",
    "Climatology and climate change", "Bioprocessing technologies",
    "Environmental change and society", "Sustainability", "Agronomy",
    "Clinical trials", "Big data", "Environment, Pollution & Climate",
    "Higher education", "Regulatory framework for innovation", "Technology management",
    "Sociology", "Education", "Energy efficient buildings", "SME support",
    "Industrial biotechnology", "Circular economy"
]

# Sustainable Development Goals options
SDG_OPTIONS = [
    "No selection",
    "1 – No Poverty",
    "2 – Zero Hunger",
    "3 – Good Health and Well-being",
    "4 – Quality Education",
    "5 – Gender Equality",
    "6 – Clean Water and Sanitation",
    "7 – Affordable and Clean Energy",
    "8 – Decent Work and Economic Growth",
    "9 – Industry, Innovation and Infrastructure",
    "10 – Reduced Inequalities",
    "11 – Sustainable Cities and Communities",
    "12 – Responsible Consumption and Production",
    "13 – Climate Action",
    "14 – Life Below Water",
    "15 – Life on Land",
    "16 – Peace, Justice and Strong Institutions",
    "17 – Partnerships for the Goals",
]

# Number of results options
RESULT_OPTIONS = [1, 3, 5, 10, 15, 20, 25, 30]

# Funding portals (sites) and their corresponding scrapers
SITE_OPTIONS = [
    "European Commission",
    "Wellcome",
    "Academy of Finland",
    "ANR",
    "IBRO",
    "IDRC",
    "All",
]


###############################################################################
# Helper functions for caching and date parsing
###############################################################################

def slugify(value: str) -> str:
    """Return a filesystem-safe slug of the input string.

    Converts the string to lowercase, replaces non-alphanumeric
    characters with underscores and strips leading/trailing
    underscores.

    Parameters
    ----------
    value : str
        Input string to slugify.

    Returns
    -------
    str
        Slugified version of the input.
    """
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def parse_date_generic(date_str: str) -> datetime.date | None:
    """Parse many common date formats into a ``datetime.date``.

    This helper is used to sort calls by deadline date and to
    evaluate expiry.  It attempts numerous formats including
    European and American styles.

    Parameters
    ----------
    date_str : str
        Date string, e.g. ``"23 February 2026"``, ``"02/07/2025"`` or
        ``"September 17, 2025"``.

    Returns
    -------
    datetime.date or None
        Parsed date or ``None`` if parsing fails.
    """
    if not date_str:
        return None
    ds = date_str.replace(",", "").strip()
    formats = [
        "%d %B %Y",
        "%d %b %Y",
        "%B %d %Y",
        "%b %d %Y",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            return datetime.datetime.strptime(ds, fmt).date()
        except Exception:
            continue
    return None


def load_cache(site_slug: str, theme_slug: str, ods: str) -> List[Dict]:
    """Load cached calls for a given site, theme and ODS.

    If the cache file does not exist, returns an empty list.  The
    cache file is expected to be a CSV with columns matching the
    output keys of the scraper functions.

    Parameters
    ----------
    site_slug : str
        Slugified name of the funding portal (e.g. ``'european_commission'``).
    theme_slug : str
        Slugified line theme or ``'any'`` if no theme.
    ods : str
        SDG number or ``'any'`` if none.

    Returns
    -------
    list of dict
        Loaded call records.
    """
    # Compose a filename based on the site, theme and ODS.  We use
    # the prefix ``calls_`` instead of ``cache_`` so that the user
    # recognises these files as persistent call datasets rather than
    # temporary caches.
    # Compose a filename based on the site, theme and ODS.  We use the
    # prefix ``cache_`` so that each combination of filters has its own
    # CSV and persists across sessions.  The caller should pass
    # ``'no_select'`` for theme_slug or ods when not specified.
    filename = f"cache_{site_slug}_{theme_slug}_{ods}.csv"
    filepath = os.path.join(CACHE_DIR, filename)
    if not os.path.exists(filepath):
        return []
    records = []
    try:
        with open(filepath, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ods_list = [x.strip() for x in row.get("ods_classification", "").split(",") if x.strip()] or ["unknown"]
                records.append({
                    "title": row.get("title", ""),
                    "link": row.get("link", ""),
                    "opening_date": row.get("opening_date", ""),
                    "deadline_date": row.get("deadline_date", ""),
                    "description": row.get("description", ""),
                    "ods_list": ods_list,
                    "site": row.get("site", "EU"),
                })
    except Exception:
        return []
    return records


def save_cache(site_slug: str, theme_slug: str, ods: str, calls: List[Dict]) -> None:
    """Save call records to a cache CSV for a given site/theme/ODS.

    Parameters
    ----------
    site_slug : str
        Slugified site name.
    theme_slug : str
        Slugified theme name or ``'any'``.
    ods : str
        SDG number or ``'any'``.
    calls : list of dict
        Call records to save.  Each dict must contain keys
        ``title``, ``link``, ``opening_date``, ``deadline_date``,
        ``description``, ``ods_list`` and ``site``.
    """
    filename = f"cache_{site_slug}_{theme_slug}_{ods}.csv"
    filepath = os.path.join(CACHE_DIR, filename)
    try:
        with open(filepath, "w", encoding="utf-8", newline="") as f:
            fieldnames = ["title", "link", "opening_date", "deadline_date", "description", "ods_classification", "site"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for call in calls:
                ods_str = ", ".join(call.get("ods_list", []))
                writer.writerow({
                    "title": call.get("title", ""),
                    "link": call.get("link", ""),
                    "opening_date": call.get("opening_date", ""),
                    "deadline_date": call.get("deadline_date", ""),
                    "description": call.get("description", ""),
                    "ods_classification": ods_str,
                    "site": call.get("site", "EU"),
                })
    except Exception:
        pass

###############################################################################
# Generic caching wrapper for other portals
###############################################################################

def cached_scrape(site_name: str, scraper_func, theme_filter: str, ods_number: str,
                  keyword: str, max_results: int, today: datetime.date) -> List[Dict]:
    """Retrieve calls from cache or scrape from the given portal.

    This helper function provides caching behaviour for sites that do not
    implement their own caching (e.g. Wellcome, AKA, ANR, IBRO, IDRC).  It
    looks up a CSV in ``data/cache`` named according to the site slug,
    theme slug and ODS slug, loads any previously stored calls, filters
    out those whose deadline is less than seven days away, and applies
    keyword and ODS filters.  If there are fewer than ``max_results``
    calls after filtering, the function invokes the provided
    ``scraper_func`` to fetch additional calls from the portal.  New
    calls are merged with the cache and saved back to disk.  The
    returned list is sorted by deadline date (earliest first) and
    truncated to ``max_results`` entries.

    Parameters
    ----------
    site_name : str
        Human‑readable name of the portal (e.g. ``"Wellcome"``).
    scraper_func : callable
        Function to call for scraping new calls; must accept
        parameters (theme_filter, ods_number, keyword, max_results,
        today) and return a list of call dicts.
    theme_filter : str
        Filter for quick search or categories; used in slug and passed
        directly to ``scraper_func``.
    ods_number : str
        SDG number used for filtering and slug.  Empty string means no
        ODS filter.
    keyword : str
        Additional keyword filter; matched against title and summary.
    max_results : int
        Number of calls to return (up to this limit).  A value less
        than or equal to zero returns an empty list.
    today : datetime.date
        Current date used to filter out calls closing soon.

    Returns
    -------
    list of dict
        Call records matching the filters, up to ``max_results`` in
        length.
    """
    if max_results <= 0:
        return []
    # Determine slugs
    site_slug = slugify(site_name)
    # Normalise slugs: use 'no_select' when no theme or ODS is provided.
    theme_slug = slugify(theme_filter) if theme_filter else "no_select"
    ods_slug = ods_number if ods_number else "no_select"
    # Load from cache
    cached_calls = load_cache(site_slug, theme_slug, ods_slug)
    filtered_cache: List[Dict] = []
    seen_links = set()
    # Filter out expired calls and apply keyword/ODS filters
    for call in cached_calls:
        # Parse deadline date
        d = parse_date_generic(call.get("deadline_date"))
        # Skip if deadline exists and is less than 7 days away
        if d is not None and (d - today).days < 7:
            continue
        # Keyword filter
        if keyword:
            kw = keyword.lower()
            if kw not in call.get("title", "").lower() and kw not in call.get("description", "").lower():
                continue
        # ODS filter: if ods_number provided, ensure it is in ods_list
        if ods_number and ods_number not in call.get("ods_list", []):
            continue
        # Keep this call
        filtered_cache.append(call)
        seen_links.add(call.get("link"))
        if len(filtered_cache) >= max_results:
            break
    # If enough cached calls, sort and return
    if len(filtered_cache) >= max_results:
        sorted_calls = sorted(
            filtered_cache,
            key=lambda c: (
                parse_date_generic(c.get("deadline_date")) or datetime.date.max,
                c.get("title", "")
            )
        )
        return sorted_calls[:max_results]
    # Need additional calls from the portal
    # Scrape new calls; request at least ``max_results`` calls
    new_calls = scraper_func(theme_filter, ods_number, keyword, max_results, today)
    combined: List[Dict] = filtered_cache.copy()
    # Append new calls, avoiding duplicates and expired ones
    for call in new_calls:
        if len(combined) >= max_results:
            break
        link = call.get("link")
        if not link or link in seen_links:
            continue
        # Skip expired calls
        d2 = parse_date_generic(call.get("deadline_date"))
        if d2 is not None and (d2 - today).days < 7:
            continue
        # ODS filter again
        if ods_number and ods_number not in call.get("ods_list", []):
            continue
        # Keyword filter again
        if keyword:
            kw = keyword.lower()
            if kw not in call.get("title", "").lower() and kw not in call.get("description", "").lower():
                continue
        combined.append(call)
        seen_links.add(call.get("link"))
    # Save updated cache
    save_cache(site_slug, theme_slug, ods_slug, combined)
    # Sort and return up to max_results
    sorted_combined = sorted(
        combined,
        key=lambda c: (
            parse_date_generic(c.get("deadline_date")) or datetime.date.max,
            c.get("title", "")
        )
    )
    return sorted_combined[:max_results]


###############################################################################
# EU scraping with caching
###############################################################################

def scrape_eu_calls(theme_filter: str, ods_number: str, keyword: str,
                    max_results: int, today: datetime.date) -> List[Dict]:
    """Scrape calls from the European Commission portal with caching.

    Parameters
    ----------
    theme_filter : str
        Quick search keyword used in the portal's URL.  If empty,
        the portal is queried without a keywords parameter.
    ods_number : str
        SDG number to filter results by.  Empty means no ODS filter.
    keyword : str
        Arbitrary keyword filter applied to title and summary.
    max_results : int
        Maximum number of calls to return.
    today : datetime.date
        Current date used to filter out calls closing in less than
        seven days.

    Returns
    -------
    list of dict
        Call records matching the filters, sorted by deadline date.
    """
    results: List[Dict] = []
    if max_results <= 0:
        return results
    site_slug = "european_commission"
    # Normalise slugs: use 'no_select' when no theme or ODS is provided.
    theme_slug = slugify(theme_filter) if theme_filter else "no_select"
    ods_slug = ods_number if ods_number else "no_select"
    # Load cache
    cached_calls = load_cache(site_slug, theme_slug, ods_slug)
    # Filter out expired calls (deadline < today + 7 days)
    filtered_cache = []
    seen_links = set()
    for call in cached_calls:
        deadline_str = call.get("deadline_date", "")
        deadline_date = parse_date_generic(deadline_str)
        if deadline_date is not None and (deadline_date - today).days < 7:
            continue
        # Apply keyword filter
        if keyword:
            kw = keyword.lower()
            if kw not in call["title"].lower() and kw not in call["description"].lower():
                continue
        # Apply ODS filter (cache loaded has already been filtered by ods_slug)
        # So we can simply include
        # but we also ensure call has ods_number if ods_number provided
        if ods_number and ods_number not in call.get("ods_list", []):
            continue
        filtered_cache.append(call)
        seen_links.add(call["link"])
        if len(filtered_cache) >= max_results:
            break
    # If we already have enough, sort and return.  Use a fallback for
    # unparsable or missing deadlines so that None values do not
    # break sorting comparisons.  ``datetime.date.max`` is used for
    # calls without a known deadline.
    if len(filtered_cache) >= max_results:
        return sorted(
            filtered_cache[:max_results],
            key=lambda c: (
                parse_date_generic(c.get("deadline_date")) or datetime.date.max,
                c.get("title", "")
            ),
        )
    # Otherwise, scrape additional calls
    needed = max_results - len(filtered_cache)
    new_calls: List[Dict] = []
    driver = create_driver()
    try:
        page_num = 1
        consecutive_empty = 0
        while len(new_calls) < needed and consecutive_empty < 5 and page_num <= 10:
            page_calls = get_calls_page(driver, theme_filter, page_num)
            if not page_calls:
                consecutive_empty += 1
                page_num += 1
                continue
            for call in page_calls:
                if len(new_calls) >= needed:
                    break
                link = call.get("link")
                if not link or link in seen_links:
                    continue
                title = call.get("title", "")
                opening_date = call.get("opening_date", "")
                deadline_date = call.get("deadline_date", "")
                # Skip if deadline too close
                deadline_obj = parse_date_generic(deadline_date)
                if deadline_obj is not None and (deadline_obj - today).days < 7:
                    continue
                # Fetch description and summarise
                desc = fetch_and_extract_description(driver, link)
                text_for_summary = desc if desc else title
                summary = summarize_text(text_for_summary)
                ods_list = classify_ods(summary)
                # Filter by ODS
                if ods_number and ods_number not in ods_list:
                    continue
                # Filter by keyword
                lower_title = title.lower()
                lower_summary = summary.lower()
                if keyword:
                    kw = keyword.lower()
                    if kw not in lower_title and kw not in lower_summary:
                        continue
                # Append new call
                record = {
                    "title": title,
                    "link": link,
                    "opening_date": opening_date,
                    "deadline_date": deadline_date,
                    "description": summary,
                    "ods_list": ods_list if ods_list else ["unknown"],
                    "site": "European Commission",
                }
                new_calls.append(record)
                seen_links.add(link)
            page_num += 1
        # Save updated cache (filtered_cache + new_calls)
        # Only include those matching ODS filter because cache is namespaced by ods_slug
        updated_cache = filtered_cache + new_calls
        save_cache(site_slug, theme_slug, ods_slug, updated_cache)
    finally:
        try:
            driver.quit()
        except Exception:
            pass
    # Combine and sort by deadline
    combined = filtered_cache + new_calls
    combined_sorted = sorted(
        combined,
        key=lambda c: (
            parse_date_generic(c.get("deadline_date")) or datetime.date.max,
            c.get("title", "")
        ),
    )
    return combined_sorted[:max_results]


###############################################################################
# Calls loading helpers
###############################################################################

def load_portal_calls(portal_name: str, scraper_func, theme_filter: str,
                      ods_number: str, keyword: str, today: datetime.date) -> List[Dict]:
    """Load or scrape calls for a single portal and filter combination.

    This helper checks for a saved CSV named according to the portal,
    theme and SDG filters.  It loads the calls from disk, filters
    expired entries (deadline less than 7 days away), and applies
    keyword and ODS filters.  If fewer than 10 calls remain, it will
    fall back to the aggregated "all" CSV (if present) to reuse calls
    scraped by the "All" filter.  If still not enough calls are
    available, it invokes the portal's scraper to fetch additional
    calls.  The updated call list is then persisted both in the
    portal-specific CSV and in the aggregated CSV for future reuse.

    Parameters
    ----------
    portal_name : str
        Human‑readable portal name (e.g. "Wellcome").
    scraper_func : callable
        Function to scrape new calls for this portal.  It should
        accept (theme_filter, ods_number, keyword, max_results, today)
        and return a list of call dicts.
    theme_filter : str
        The line theme filter or empty string.
    ods_number : str
        The SDG number filter or empty string.
    keyword : str
        Additional keyword filter (case insensitive) applied to the
        title and description.
    today : datetime.date
        The current date used to filter out calls closing in less
        than 7 days.

    Returns
    -------
    list of dict
        Up to 10 call records matching the filters for the given
        portal.
    """
    # Determine slugs for filenames
    portal_slug = slugify(portal_name)
    theme_slug = slugify(theme_filter) if theme_filter else "no_select"
    ods_slug = ods_number if ods_number else "no_select"
    # Load calls from portal-specific CSV
    portal_calls = load_cache(portal_slug, theme_slug, ods_slug)
    filtered_portal: List[Dict] = []
    seen_links = set()
    # Apply expiry, ODS and keyword filters to portal calls
    for call in portal_calls:
        # Expiry check: skip if deadline exists and less than 7 days away
        deadline_date = parse_date_generic(call.get("deadline_date", ""))
        if deadline_date is not None and (deadline_date - today).days < 7:
            continue
        # ODS filter
        if ods_number and ods_number not in call.get("ods_list", []):
            continue
        # Keyword filter
        if keyword:
            kw = keyword.lower()
            if kw not in call.get("title", "").lower() and kw not in call.get("description", "").lower():
                continue
        filtered_portal.append(call)
        seen_links.add(call.get("link"))
        if len(filtered_portal) >= 10:
            break
    # If enough calls found, sort and return
    if len(filtered_portal) >= 10:
        return sorted(
            filtered_portal[:10],
            key=lambda c: (parse_date_generic(c.get("deadline_date")) or datetime.date.max, c.get("title", ""))
        )
    # Otherwise, try to reuse calls from the aggregated 'all' CSV
    all_calls = load_cache("all", theme_slug, ods_slug)
    for call in all_calls:
        if len(filtered_portal) >= 10:
            break
        # Only reuse calls matching this portal
        if slugify(call.get("site", "")) != portal_slug:
            continue
        # Apply expiry, keyword and ODS filters
        deadline_date = parse_date_generic(call.get("deadline_date", ""))
        if deadline_date is not None and (deadline_date - today).days < 7:
            continue
        if ods_number and ods_number not in call.get("ods_list", []):
            continue
        if keyword:
            kw = keyword.lower()
            if kw not in call.get("title", "").lower() and kw not in call.get("description", "").lower():
                continue
        if call.get("link") in seen_links:
            continue
        filtered_portal.append(call)
        seen_links.add(call.get("link"))
    # If still not enough calls, scrape new ones
    needed = 10 - len(filtered_portal)
    if needed > 0:
        new_calls = scraper_func(theme_filter, ods_number, keyword, needed, today)
        for call in new_calls:
            if len(filtered_portal) >= 10:
                break
            # Skip duplicates
            link = call.get("link")
            if not link or link in seen_links:
                continue
            # Apply expiry, ODS and keyword filters again (should already be applied in scraper)
            deadline_date = parse_date_generic(call.get("deadline_date", ""))
            if deadline_date is not None and (deadline_date - today).days < 7:
                continue
            if ods_number and ods_number not in call.get("ods_list", []):
                continue
            if keyword:
                kw = keyword.lower()
                if kw not in call.get("title", "").lower() and kw not in call.get("description", "").lower():
                    continue
            filtered_portal.append(call)
            seen_links.add(link)
    # Persist updated calls to portal-specific CSV
    # Sort by deadline and title for consistency
    sorted_portal = sorted(
        filtered_portal,
        key=lambda c: (parse_date_generic(c.get("deadline_date")) or datetime.date.max, c.get("title", ""))
    )
    save_cache(portal_slug, theme_slug, ods_slug, sorted_portal)
    # Also update the aggregated 'all' CSV: remove existing calls of this portal and add the updated ones
    all_calls_existing = load_cache("all", theme_slug, ods_slug)
    remaining = [c for c in all_calls_existing if slugify(c.get("site", "")) != portal_slug]
    combined_all = remaining + sorted_portal
    # Save the combined calls into the aggregated CSV
    save_cache("all", theme_slug, ods_slug, combined_all)
    # Return up to 10 calls
    return sorted_portal[:10]


def load_all_calls(theme_filter: str, ods_number: str, keyword: str,
                   today: datetime.date) -> List[Dict]:
    """Load or scrape calls for all portals for a given filter combination.

    This function iterates over all individual portals, loads their
    portal‑specific CSVs, applies filters and scrapes additional
    entries to ensure each portal contributes up to 10 calls.  After
    processing all portals, the union of these calls is saved to an
    aggregated CSV named ``cache_all_{theme_slug}_{ods_slug}.csv`` for
    reuse in future searches.  It returns the combined list of
    calls sorted by deadline and title.

    Parameters
    ----------
    theme_filter : str
        The line theme filter or empty string.
    ods_number : str
        The SDG number filter or empty string.
    keyword : str
        Additional keyword filter.
    today : datetime.date
        The current date used to filter out calls closing in less
        than 7 days.

    Returns
    -------
    list of dict
        Combined call records from all portals.
    """
    theme_slug = slugify(theme_filter) if theme_filter else "no_select"
    ods_slug = ods_number if ods_number else "no_select"
    aggregated: List[Dict] = []
    # Iterate over portals (excluding 'All') defined in SITE_OPTIONS
    # Map site name to its scraper
    portal_map = {
        "European Commission": scrape_eu_calls,
        "Wellcome": scrape_wellcome_calls,
        "Academy of Finland": scrape_aka_calls,
        "ANR": scrape_anr_calls,
        "IBRO": scrape_ibro_calls,
        "IDRC": scrape_idrc_calls,
    }
    for portal_name, scraper_func in portal_map.items():
        portal_calls = load_cache(slugify(portal_name), theme_slug, ods_slug)
        filtered_portal: List[Dict] = []
        seen_links = set()
        # Apply expiry, ODS and keyword filters
        for call in portal_calls:
            deadline_date = parse_date_generic(call.get("deadline_date", ""))
            if deadline_date is not None and (deadline_date - today).days < 7:
                continue
            if ods_number and ods_number not in call.get("ods_list", []):
                continue
            if keyword:
                kw = keyword.lower()
                if kw not in call.get("title", "").lower() and kw not in call.get("description", "").lower():
                    continue
            filtered_portal.append(call)
            seen_links.add(call.get("link"))
            if len(filtered_portal) >= 10:
                break
        # If not enough calls, scrape additional
        if len(filtered_portal) < 10:
            needed = 10 - len(filtered_portal)
            new_calls = scraper_func(theme_filter, ods_number, keyword, needed, today)
            for call in new_calls:
                if len(filtered_portal) >= 10:
                    break
                link = call.get("link")
                if not link or link in seen_links:
                    continue
                deadline_date = parse_date_generic(call.get("deadline_date", ""))
                if deadline_date is not None and (deadline_date - today).days < 7:
                    continue
                if ods_number and ods_number not in call.get("ods_list", []):
                    continue
                if keyword:
                    kw = keyword.lower()
                    if kw not in call.get("title", "").lower() and kw not in call.get("description", "").lower():
                        continue
                filtered_portal.append(call)
                seen_links.add(link)
        # Sort portal calls and truncate to 10
        sorted_portal = sorted(
            filtered_portal,
            key=lambda c: (parse_date_generic(c.get("deadline_date")) or datetime.date.max, c.get("title", ""))
        )[:10]
        # Persist portal-specific calls
        save_cache(slugify(portal_name), theme_slug, ods_slug, sorted_portal)
        # Add to aggregated list
        aggregated.extend(sorted_portal)
    # Persist aggregated calls under the 'all' slug
    save_cache("all", theme_slug, ods_slug, aggregated)
    # Sort aggregated calls by deadline and title
    aggregated_sorted = sorted(
        aggregated,
        key=lambda c: (parse_date_generic(c.get("deadline_date")) or datetime.date.max, c.get("title", ""))
    )
    return aggregated_sorted


###############################################################################
# GUI implementation
###############################################################################

def run_gui() -> None:
    """Construct and run the Tkinter GUI."""
    root = tk.Tk()
    root.title("Research Funding Calls Scraper")
    root.geometry("1000x700")

    # Variables for widgets
    theme_var = tk.StringVar(value="Select a theme")
    ods_var = tk.StringVar(value=SDG_OPTIONS[0])
    keyword_var = tk.StringVar()
    # We no longer let the user specify the number of calls; each portal
    # returns up to 10 calls automatically.  The site selector allows
    # choosing a single portal or "All" for all portals.
    site_var = tk.StringVar(value=SITE_OPTIONS[-1])  # Default to "All"

    # Row 0: Line theme selector
    tk.Label(root, text="Line Theme:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
    theme_menu = ttk.Combobox(root, textvariable=theme_var, values=THEME_OPTIONS + ["Select a theme"], state="readonly")
    theme_menu.grid(row=0, column=1, padx=5, pady=5, sticky="we")
    # Row 1: SDG selector
    tk.Label(root, text="SDG:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
    ods_menu = ttk.Combobox(root, textvariable=ods_var, values=SDG_OPTIONS, state="readonly")
    ods_menu.grid(row=1, column=1, padx=5, pady=5, sticky="we")
    # Row 2: Keywords entry
    tk.Label(root, text="Keywords:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
    keyword_entry = tk.Entry(root, textvariable=keyword_var)
    keyword_entry.grid(row=2, column=1, padx=5, pady=5, sticky="we")
    # Row 3: Funding portal selector (site)
    tk.Label(root, text="Funding portal:").grid(row=3, column=0, padx=5, pady=5, sticky="w")
    site_menu = ttk.Combobox(root, textvariable=site_var, values=SITE_OPTIONS, state="readonly")
    site_menu.grid(row=3, column=1, padx=5, pady=5, sticky="we")

    # Row 5: Search and clear buttons
    def on_search() -> None:
        # Clear previous results
        results_text.configure(state="normal")
        results_text.delete(1.0, tk.END)
        # Read filters
        selected_theme = theme_var.get()
        theme_filter = "" if selected_theme == "Select a theme" else selected_theme
        selected_ods = ods_var.get()
        ods_number = ""
        if selected_ods and selected_ods != SDG_OPTIONS[0]:
            # Extract the number before the dash
            ods_number = selected_ods.split("–")[0].strip()
        kw = keyword_var.get().strip().lower()
        # Determine site selection
        selected_site = site_var.get()
        start_time = time.time()
        today = datetime.date.today()
        aggregated: List[Dict] = []
        # Determine which calls to load based on the selected portal.
        # Each portal returns up to 10 calls.  Calls are persisted in
        # ``data/cache`` files keyed by site, theme and ODS.  When
        # selecting "All", calls from every portal are loaded via
        # ``load_all_calls``.  For a single portal, calls are loaded via
        # ``load_portal_calls``.
        # Mapping of human‑readable portal names to scraper functions.  These
        # functions accept (theme_filter, ods_number, keyword,
        # max_results, today) and return a list of calls.
        portal_scrapers = {
            "European Commission": scrape_eu_calls,
            "Wellcome": scrape_wellcome_calls,
            "Academy of Finland": scrape_aka_calls,
            "ANR": scrape_anr_calls,
            "IBRO": scrape_ibro_calls,
            "IDRC": scrape_idrc_calls,
        }
        if selected_site == "All":
            # Load or scrape calls from all portals, persisting results
            # across sessions.  This returns up to 10 calls per portal.
            aggregated = load_all_calls(theme_filter, ods_number, kw, today)
        else:
            # Load or scrape calls for a single portal.  Persist the
            # results in portal-specific and aggregated CSVs so that
            # subsequent runs reuse the stored data.  The portal name
            # should correspond exactly to keys in portal_scrapers.
            scraper_func = portal_scrapers.get(selected_site)
            if scraper_func is None:
                aggregated = []
            else:
                aggregated = load_portal_calls(selected_site, scraper_func, theme_filter, ods_number, kw, today)
        # Sort aggregated by deadline date
        # Sort aggregated calls by deadline date (earliest first).  Calls with
        # unknown or unparsable deadlines are sorted last by using
        # ``datetime.date.max`` as a fallback.  Secondary sort by title.
        aggregated_sorted = sorted(
            aggregated,
            key=lambda c: (
                parse_date_generic(c.get("deadline_date")) or datetime.date.max,
                c.get("title", "")
            )
        )
        # Save results to CSV (update OUTPUT_DIR)
        with open(CSV_PATH, "w", encoding="utf-8", newline="") as f:
            fieldnames = ["title", "link", "opening_date", "deadline_date", "description", "ods_classification", "site"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for call in aggregated_sorted:
                ods_str = ", ".join(call.get("ods_list", []))
                writer.writerow({
                    "title": call.get("title", ""),
                    "link": call.get("link", ""),
                    "opening_date": call.get("opening_date", ""),
                    "deadline_date": call.get("deadline_date", ""),
                    "description": call.get("description", ""),
                    "ods_classification": ods_str,
                    "site": call.get("site", ""),
                })
        # Display results in the GUI
        if not aggregated_sorted:
            results_text.insert(tk.END, "No calls matched your filters.\n")
        else:
            for i, call in enumerate(aggregated_sorted, 1):
                results_text.insert(tk.END, f"{i}. {call['title']}\n")
                # Insert clickable link
                start_index = results_text.index(tk.END)
                link_text = f"   Link: {call['link']}\n"
                results_text.insert(tk.END, link_text)
                end_index = results_text.index(tk.END)
                # Tag the link and bind a click event
                tag_name = f"link_{i}"
                results_text.tag_add(tag_name, f"{start_index} linestart", f"{start_index} lineend")
                results_text.tag_bind(tag_name, "<Button-1>", lambda e, url=call['link']: webbrowser.open_new_tab(url))
                results_text.tag_config(tag_name, foreground="blue", underline=True)
                # Opening and deadline dates
                results_text.insert(tk.END, f"   Opening date: {call['opening_date']} | Deadline: {call['deadline_date']}\n")
                # Site name
                results_text.insert(tk.END, f"   Site: {call['site']}\n")
                # Summary
                results_text.insert(tk.END, "   Summary: " + call['description'] + "\n")
                # ODS classification
                ods_str = ", ".join(call.get("ods_list", []))
                results_text.insert(tk.END, f"   ODS: {ods_str}\n\n")
        elapsed = time.time() - start_time
        results_text.insert(tk.END, f"Search complete in {elapsed:.2f} seconds. {len(aggregated_sorted)} calls shown.\n")
        results_text.configure(state="disabled")

    def on_clear() -> None:
        theme_var.set("Select a theme")
        ods_var.set(SDG_OPTIONS[0])
        keyword_var.set("")
        site_var.set(SITE_OPTIONS[-1])
        results_text.configure(state="normal")
        results_text.delete(1.0, tk.END)
        results_text.configure(state="disabled")

    search_button = tk.Button(root, text="Search", command=on_search)
    search_button.grid(row=4, column=0, padx=5, pady=10, sticky="we")
    clear_button = tk.Button(root, text="Clear", command=on_clear)
    clear_button.grid(row=4, column=1, padx=5, pady=10, sticky="we")

    # Row 5: Results area
    results_text = scrolledtext.ScrolledText(root, wrap=tk.WORD, width=120, height=25)
    results_text.grid(row=5, column=0, columnspan=2, padx=5, pady=5, sticky="nsew")
    results_text.configure(state="disabled")

    # Row 6: Info label
    info_label = tk.Label(
        root,
        text=(
            "The ODS classification is determined locally using keyword heuristics. "
            "If no SDG is matched, the call is classified as 'unknown'. "
            "Links are clickable for convenience."
        ),
        wraplength=900,
        justify="left",
    )
    info_label.grid(row=6, column=0, columnspan=2, padx=5, pady=5, sticky="w")

    # Configure row/column weights so that the results area (row 5) expands
    root.grid_rowconfigure(5, weight=1)
    root.grid_columnconfigure(1, weight=1)

    root.mainloop()


###############################################################################
# Entry point
###############################################################################

if __name__ == "__main__":
    run_gui()