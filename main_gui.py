#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
main_gui.py
-----------

Entry point for the multi‑page calls scraper application.  This
module defines a Tkinter-based graphical interface that allows the
user to search research funding calls across multiple funding portals.

Two modes of operation are supported:

* **International** – replicates the original functionality for
  scraping calls from international portals such as the European
  Commission, Wellcome Trust, Academy of Finland, ANR, IBRO and IDRC.
  Users may specify a line theme (keyword), an SDG number, an
  arbitrary keyword and a funding portal (or "All") and retrieve up
  to ten calls per portal.  Results are cached on disk under
  ``data/cache`` so that subsequent searches reuse previously
  downloaded summaries and avoid unnecessary scraping.

* **National** – adds the ability to search open calls from several
  Colombian ministries.  The user selects a ministry (or "All") and a
  call type (Regalías, Proyectos or All) and retrieves up to ten
  calls per ministry.  These results are also cached on disk using
  filter‑specific CSV files so that searches across sessions reuse
  existing data.  The national scrapers operate via simple HTTP
  requests (see ``http_utils.py``) and return summaries and ODS
  classifications locally via the ``summarizer`` module.

The international mode remains unmodified from the original version
provided by the user: all GUI elements, caching and sorting behave
exactly as before.  The national mode introduces two new filters
specific to Colombian ministries while hiding the international
filters for clarity.

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

# Import international modules.  These scrapers and helpers are
# unchanged from the original implementation and continue to operate
# on the European Commission and other global funding portals.
from summarizer import summarize_text, classify_ods
from utils import create_driver, accept_cookies, slugify
from eu_scraper import get_calls_page, fetch_and_extract_description
from wellcome_scraper import scrape_wellcome_calls
from aka_scraper import scrape_aka_calls
from anr_scraper import scrape_anr_calls
from ibro_scraper import scrape_ibro_calls
from idrc_scraper import scrape_idrc_calls

# Import national scrapers.  These functions return call dictionaries
# with keys ``title``, ``link``, ``opening_date``, ``deadline_date``,
# ``description``, ``ods_list``, ``site`` and ``type``.  The ``site``
# corresponds to the ministry name for display purposes and ``type``
# indicates whether the call is a regalías or a project.
from minenergia_scraper import scrape_minenergia_calls
from minambiente_scraper import scrape_minambiente_calls
from minciencias_scraper import scrape_minciencias_calls
from mincultura_scraper import scrape_mincultura_calls
from mintic_scraper import scrape_mintic_calls
from mineducacion_scraper import scrape_mineducacion_calls


###############################################################################
# Configuration and constants
###############################################################################

# Directory for cached results and output CSV.  These are located
# relative to this source file so that caches persist regardless of
# where the script is executed from.  When the application starts,
# it ensures the subdirectories exist.  The cache stores a CSV per
# site/theme/ODS combination for international mode (e.g.
# ``cache_european_commission_health_3.csv``) and per
# ministry/calltype combination for national mode (e.g.
# ``cache_national_minenergia_regalias.csv``).
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "data", "cache")
OUTPUT_DIR = os.path.join(BASE_DIR, "data", "scraping_results")
CSV_PATH = os.path.join(OUTPUT_DIR, "calls_for_proposals.csv")

# Ensure directories exist at runtime
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Available line themes (keywords) for international mode.  These are
# suggestions; users may still type arbitrary keywords in the
# keywords field.
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

# Sustainable Development Goals options for international mode
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

# Funding portals (sites) and their corresponding scrapers for
# international mode.  The last entry is "All", which triggers
# scraping from all portals.
SITE_OPTIONS = [
    "European Commission",
    "Wellcome",
    "Academy of Finland",
    "ANR",
    "IBRO",
    "IDRC",
    "All",
]

# Ministry options for national mode.  "All" will query across all
# ministries.  The names are used for display and in the call
# dictionary's ``site`` field.
MINISTRY_OPTIONS = [
    "MinEnergía",
    "MinAmbiente",
    "MinCiencias",
    "MinCultura",
    "MinTIC",
    "MinEducación",
    "All",
]

# Call type options for national mode.  "All" selects both regalías
# and project calls.  Note that not all ministries publish both
# types.
CALLTYPE_OPTIONS = [
    "All",
    "Regalías",
    "Proyectos",
]

# Map human‑readable ministry names to slug values used in cache
# filenames.  Accents and spaces are removed for filesystem safety.
MINISTRY_SLUGS = {
    "MinEnergía": "minenergia",
    "MinAmbiente": "minambiente",
    "MinCiencias": "minciencias",
    "MinCultura": "mincultura",
    "MinTIC": "mintic",
    "MinEducación": "mineducacion",
    "All": "all",
}

# Map call types to slug values
CALLTYPE_SLUGS = {
    "All": "no_select",
    "Regalías": "regalias",
    "Proyectos": "proyectos",
}


###############################################################################
# Helper functions for caching and date parsing (international mode)
###############################################################################

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
    """Load cached calls for a given site, theme and ODS for international mode.

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
    filename = f"cache_{site_slug}_{theme_slug}_{ods}.csv"
    filepath = os.path.join(CACHE_DIR, filename)
    if not os.path.exists(filepath):
        return []
    records: List[Dict] = []
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
    """Save call records to a cache CSV for international mode.

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
# Helper functions for caching (national mode)
###############################################################################

def load_national_cache(ministry_slug: str, calltype_slug: str) -> List[Dict]:
    """Load cached calls for a given ministry and call type in national mode.

    The cache file is named ``cache_national_{ministry_slug}_{calltype_slug}.csv``
    and is stored in ``CACHE_DIR``.  If the file does not exist, an
    empty list is returned.  Each record includes ``type`` and
    ``site`` fields alongside the other call attributes.

    Parameters
    ----------
    ministry_slug : str
        Slugified ministry name (e.g. ``'minenergia'``) or ``'all'``.
    calltype_slug : str
        Slugified call type (``'regalias'``, ``'proyectos'`` or
        ``'no_select'``).

    Returns
    -------
    list of dict
        Loaded call records.
    """
    filename = f"cache_national_{ministry_slug}_{calltype_slug}.csv"
    filepath = os.path.join(CACHE_DIR, filename)
    if not os.path.exists(filepath):
        return []
    records: List[Dict] = []
    try:
        with open(filepath, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # No ODS classification is used for national calls; keep unknown
                records.append({
                    "title": row.get("title", ""),
                    "link": row.get("link", ""),
                    "opening_date": row.get("opening_date", ""),
                    "deadline_date": row.get("deadline_date", ""),
                    "description": row.get("description", ""),
                    "ods_list": row.get("ods_classification", "unknown").split(","),
                    "site": row.get("site", ""),
                    "type": row.get("type", ""),
                })
    except Exception:
        return []
    return records


def save_national_cache(ministry_slug: str, calltype_slug: str, calls: List[Dict]) -> None:
    """Save call records to a cache CSV for national mode.

    Parameters
    ----------
    ministry_slug : str
        Slugified ministry name.
    calltype_slug : str
        Slugified call type.
    calls : list of dict
        Call records to save.  Each dict must contain keys
        ``title``, ``link``, ``opening_date``, ``deadline_date``,
        ``description``, ``site`` and ``type``.
    """
    filename = f"cache_national_{ministry_slug}_{calltype_slug}.csv"
    filepath = os.path.join(CACHE_DIR, filename)
    try:
        with open(filepath, "w", encoding="utf-8", newline="") as f:
            fieldnames = ["title", "link", "opening_date", "deadline_date", "description", "ods_classification", "site", "type"]
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
                    "site": call.get("site", ""),
                    "type": call.get("type", ""),
                })
    except Exception:
        pass


###############################################################################
# Generic caching wrapper for international portals
###############################################################################

def cached_scrape(site_name: str, scraper_func, theme_filter: str, ods_number: str,
                  keyword: str, max_results: int, today: datetime.date) -> List[Dict]:
    """Retrieve calls from cache or scrape from the given portal (international).

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
    site_slug = slugify(site_name)
    theme_slug = slugify(theme_filter) if theme_filter else "no_select"
    ods_slug = ods_number if ods_number else "no_select"
    cached_calls = load_cache(site_slug, theme_slug, ods_slug)
    filtered_cache: List[Dict] = []
    seen_links = set()
    for call in cached_calls:
        d = parse_date_generic(call.get("deadline_date"))
        if d is not None and (d - today).days < 7:
            continue
        if keyword:
            kw = keyword.lower()
            if kw not in call.get("title", "").lower() and kw not in call.get("description", "").lower():
                continue
        if ods_number and ods_number not in call.get("ods_list", []):
            continue
        filtered_cache.append(call)
        seen_links.add(call.get("link"))
        if len(filtered_cache) >= max_results:
            break
    if len(filtered_cache) >= max_results:
        return sorted(
            filtered_cache,
            key=lambda c: (parse_date_generic(c.get("deadline_date")) or datetime.date.max, c.get("title", ""))
        )[:max_results]
    new_calls = scraper_func(theme_filter, ods_number, keyword, max_results, today)
    combined: List[Dict] = filtered_cache.copy()
    for call in new_calls:
        if len(combined) >= max_results:
            break
        link = call.get("link")
        if not link or link in seen_links:
            continue
        d2 = parse_date_generic(call.get("deadline_date"))
        if d2 is not None and (d2 - today).days < 7:
            continue
        if ods_number and ods_number not in call.get("ods_list", []):
            continue
        if keyword:
            kw = keyword.lower()
            if kw not in call.get("title", "").lower() and kw not in call.get("description", "").lower():
                continue
        combined.append(call)
        seen_links.add(link)
    save_cache(site_slug, theme_slug, ods_slug, combined)
    sorted_combined = sorted(
        combined,
        key=lambda c: (parse_date_generic(c.get("deadline_date")) or datetime.date.max, c.get("title", ""))
    )
    return sorted_combined[:max_results]


###############################################################################
# National calls loading helpers
###############################################################################

def get_ministry_scraper(ministry: str):
    """Return the appropriate scraper function for a given ministry.

    Parameters
    ----------
    ministry : str
        The human‑readable ministry name.

    Returns
    -------
    callable or None
        The scraper function or ``None`` if the ministry is unknown.
    """
    mapping = {
        "MinEnergía": scrape_minenergia_calls,
        "MinAmbiente": scrape_minambiente_calls,
        "MinCiencias": scrape_minciencias_calls,
        "MinCultura": scrape_mincultura_calls,
        "MinTIC": scrape_mintic_calls,
        "MinEducación": scrape_mineducacion_calls,
    }
    return mapping.get(ministry)


def load_national_calls(ministry: str, call_type: str, today: datetime.date,
                         scrape_if_needed: bool = True) -> List[Dict]:
    """Load or scrape calls for a single ministry and call type.

    This helper loads calls from a CSV named
    ``cache_national_{ministry_slug}_{calltype_slug}.csv``.  It filters
    expired entries (deadline within seven days), filters by call type,
    and if not enough calls remain, scrapes new ones from the ministry's
    website.  The updated calls are persisted back to the CSV.  The
    returned list is sorted by deadline (earliest first) and truncated
    to ten entries.

    Parameters
    ----------
    ministry : str
        Human‑readable ministry name (e.g. "MinEnergía").  Use
        "All" to indicate all ministries (see ``load_all_national_calls``).
    call_type : str
        The type of call ("Regalías", "Proyectos" or "All").
    today : datetime.date
        Current date used to filter out expired calls.
    scrape_if_needed : bool, optional
        Whether to perform scraping if cached calls are insufficient.

    Returns
    -------
    list of dict
        Up to ten call records for the specified ministry and call type.
    """
    # Determine slugs
    ministry_slug = MINISTRY_SLUGS.get(ministry, "all")
    calltype_slug = CALLTYPE_SLUGS.get(call_type, "no_select")
    # Load cached calls
    cached_calls = load_national_cache(ministry_slug, calltype_slug)
    filtered_calls: List[Dict] = []
    seen_links = set()
    for call in cached_calls:
        # Filter by expiry
        d = parse_date_generic(call.get("deadline_date"))
        if d is not None and (d - today).days < 7:
            continue
        # Filter by call type
        if call_type != "All" and call.get("type", "") != call_type:
            continue
        filtered_calls.append(call)
        seen_links.add(call.get("link"))
        if len(filtered_calls) >= 10:
            break
    if len(filtered_calls) >= 10 or not scrape_if_needed:
        # Sort by deadline and return
        return sorted(
            filtered_calls,
            key=lambda c: (parse_date_generic(c.get("deadline_date")) or datetime.date.max, c.get("title", ""))
        )[:10]
    # Need to scrape more calls
    scraper = get_ministry_scraper(ministry)
    if scraper is None:
        # Unknown ministry: return what we have
        return sorted(
            filtered_calls,
            key=lambda c: (parse_date_generic(c.get("deadline_date")) or datetime.date.max, c.get("title", ""))
        )[:10]
    # Determine how many additional calls are needed
    needed = 10 - len(filtered_calls)
    new_calls = scraper(max_results=needed)
    for call in new_calls:
        if len(filtered_calls) >= 10:
            break
        link = call.get("link")
        if not link or link in seen_links:
            continue
        # Check expiry
        d = parse_date_generic(call.get("deadline_date"))
        if d is not None and (d - today).days < 7:
            continue
        # Filter by call type again
        if call_type != "All" and call.get("type", "") != call_type:
            continue
        filtered_calls.append(call)
        seen_links.add(link)
    # Persist updated calls
    # Combine existing filtered calls with new calls and save
    combined_calls = filtered_calls.copy()
    # Save combined calls back to cache
    save_national_cache(ministry_slug, calltype_slug, combined_calls)
    # Return sorted calls
    return sorted(
        combined_calls,
        key=lambda c: (parse_date_generic(c.get("deadline_date")) or datetime.date.max, c.get("title", ""))
    )[:10]


def load_all_national_calls(call_type: str, today: datetime.date,
                            scrape_if_needed: bool = True) -> List[Dict]:
    """Load or scrape calls for all ministries for a given call type.

    This function iterates over all ministries defined in
    ``MINISTRY_OPTIONS`` (excluding "All"), loads their cached calls,
    applies expiry and call type filters, and scrapes additional
    entries as necessary to ensure each ministry contributes up to
    ten calls.  It returns the combined list of calls across all
    ministries sorted by deadline and title.  The individual caches
    for each ministry and call type are updated accordingly.

    Parameters
    ----------
    call_type : str
        The call type ("All", "Regalías" or "Proyectos").
    today : datetime.date
        Current date used to filter out expired calls.
    scrape_if_needed : bool, optional
        Whether to perform scraping when cached calls are insufficient.

    Returns
    -------
    list of dict
        Combined call records from all ministries.
    """
    aggregated: List[Dict] = []
    for ministry in MINISTRY_OPTIONS:
        if ministry == "All":
            continue
        calls = load_national_calls(ministry, call_type, today, scrape_if_needed)
        aggregated.extend(calls)
    # Sort aggregated calls by deadline and title
    return sorted(
        aggregated,
        key=lambda c: (parse_date_generic(c.get("deadline_date")) or datetime.date.max, c.get("title", ""))
    )


###############################################################################
# EU scraping with caching (international)
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
    theme_slug = slugify(theme_filter) if theme_filter else "no_select"
    ods_slug = ods_number if ods_number else "no_select"
    cached_calls = load_cache(site_slug, theme_slug, ods_slug)
    filtered_cache = []
    seen_links = set()
    for call in cached_calls:
        deadline_str = call.get("deadline_date", "")
        deadline_date = parse_date_generic(deadline_str)
        if deadline_date is not None and (deadline_date - today).days < 7:
            continue
        if keyword:
            kw = keyword.lower()
            if kw not in call["title"].lower() and kw not in call["description"].lower():
                continue
        if ods_number and ods_number not in call.get("ods_list", []):
            continue
        filtered_cache.append(call)
        seen_links.add(call["link"])
        if len(filtered_cache) >= max_results:
            break
    if len(filtered_cache) >= max_results:
        return sorted(
            filtered_cache[:max_results],
            key=lambda c: (parse_date_generic(c.get("deadline_date")) or datetime.date.max, c.get("title", ""))
        )
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
                deadline_obj = parse_date_generic(deadline_date)
                if deadline_obj is not None and (deadline_obj - today).days < 7:
                    continue
                desc = fetch_and_extract_description(driver, link)
                text_for_summary = desc if desc else title
                summary = summarize_text(text_for_summary)
                ods_list = classify_ods(summary)
                if ods_number and ods_number not in ods_list:
                    continue
                lower_title = title.lower()
                lower_summary = summary.lower()
                if keyword:
                    kw = keyword.lower()
                    if kw not in lower_title and kw not in lower_summary:
                        continue
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
        updated_cache = filtered_cache + new_calls
        save_cache(site_slug, theme_slug, ods_slug, updated_cache)
    finally:
        try:
            driver.quit()
        except Exception:
            pass
    combined = filtered_cache + new_calls
    combined_sorted = sorted(
        combined,
        key=lambda c: (parse_date_generic(c.get("deadline_date")) or datetime.date.max, c.get("title", ""))
    )
    return combined_sorted[:max_results]


###############################################################################
# Calls loading helpers (international)
###############################################################################

def load_portal_calls(portal_name: str, scraper_func, theme_filter: str,
                      ods_number: str, keyword: str, today: datetime.date,
                      scrape_if_needed: bool = True) -> List[Dict]:
    """Load or scrape calls for a single portal and filter combination.

    This helper checks for a saved CSV named according to the portal,
    theme and SDG filters.  It loads the calls from disk, filters
    expired entries (deadline less than seven days away), and applies
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
    portal_slug = slugify(portal_name)
    theme_slug = slugify(theme_filter) if theme_filter else "no_select"
    ods_slug = ods_number if ods_number else "no_select"
    portal_calls = load_cache(portal_slug, theme_slug, ods_slug)
    filtered_portal: List[Dict] = []
    seen_links = set()
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
    if len(filtered_portal) >= 10:
        return sorted(
            filtered_portal,
            key=lambda c: (parse_date_generic(c.get("deadline_date")) or datetime.date.max, c.get("title", ""))
        )[:10]
    # Try to reuse calls from aggregated 'all' CSV
    all_calls = load_cache("all", theme_slug, ods_slug)
    for call in all_calls:
        if len(filtered_portal) >= 10:
            break
        if slugify(call.get("site", "")) != portal_slug:
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
        if call.get("link") in seen_links:
            continue
        filtered_portal.append(call)
        seen_links.add(call.get("link"))
    needed = 10 - len(filtered_portal)
    if needed > 0 and scrape_if_needed:
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
    sorted_portal = sorted(
        filtered_portal,
        key=lambda c: (parse_date_generic(c.get("deadline_date")) or datetime.date.max, c.get("title", ""))
    )
    save_cache(portal_slug, theme_slug, ods_slug, sorted_portal)
    all_calls_existing = load_cache("all", theme_slug, ods_slug)
    remaining = [c for c in all_calls_existing if slugify(c.get("site", "")) != portal_slug]
    combined_all = remaining + sorted_portal
    save_cache("all", theme_slug, ods_slug, combined_all)
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
        sorted_portal = sorted(
            filtered_portal,
            key=lambda c: (parse_date_generic(c.get("deadline_date")) or datetime.date.max, c.get("title", ""))
        )[:10]
        save_cache(slugify(portal_name), theme_slug, ods_slug, sorted_portal)
        aggregated.extend(sorted_portal)
    save_cache("all", theme_slug, ods_slug, aggregated)
    aggregated_sorted = sorted(
        aggregated,
        key=lambda c: (parse_date_generic(c.get("deadline_date")) or datetime.date.max, c.get("title", ""))
    )
    return aggregated_sorted


###############################################################################
# GUI implementation
###############################################################################

def run_gui() -> None:
    """Construct and run the Tkinter GUI for both international and national modes."""
    root = tk.Tk()
    root.title("Research Funding Calls Scraper")
    root.geometry("1100x750")

    # Mode selection: International or National
    mode_var = tk.StringVar(value="International")
    tk.Label(root, text="Modo:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
    mode_menu = ttk.Combobox(root, textvariable=mode_var, values=["International", "National"], state="readonly")
    mode_menu.grid(row=0, column=1, padx=5, pady=5, sticky="we")

    # International variables
    theme_var = tk.StringVar(value="Select a theme")
    ods_var = tk.StringVar(value=SDG_OPTIONS[0])
    keyword_var = tk.StringVar()
    site_var = tk.StringVar(value=SITE_OPTIONS[-1])  # Default to "All"

    # National variables
    ministry_var = tk.StringVar(value=MINISTRY_OPTIONS[-1])  # Default to "All"
    calltype_var = tk.StringVar(value=CALLTYPE_OPTIONS[0])   # Default to "All"

    # International frame containing theme, ODS, keyword and portal selectors
    intl_frame = tk.Frame(root)
    # Line theme
    tk.Label(intl_frame, text="Line Theme:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
    theme_menu = ttk.Combobox(intl_frame, textvariable=theme_var, values=THEME_OPTIONS + ["Select a theme"], state="readonly")
    theme_menu.grid(row=0, column=1, padx=5, pady=5, sticky="we")
    # SDG
    tk.Label(intl_frame, text="SDG:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
    ods_menu = ttk.Combobox(intl_frame, textvariable=ods_var, values=SDG_OPTIONS, state="readonly")
    ods_menu.grid(row=1, column=1, padx=5, pady=5, sticky="we")
    # Keywords
    tk.Label(intl_frame, text="Keywords:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
    keyword_entry = tk.Entry(intl_frame, textvariable=keyword_var)
    keyword_entry.grid(row=2, column=1, padx=5, pady=5, sticky="we")
    # Funding portal
    tk.Label(intl_frame, text="Funding portal:").grid(row=3, column=0, padx=5, pady=5, sticky="w")
    site_menu = ttk.Combobox(intl_frame, textvariable=site_var, values=SITE_OPTIONS, state="readonly")
    site_menu.grid(row=3, column=1, padx=5, pady=5, sticky="we")

    # National frame containing ministry and call type selectors
    nat_frame = tk.Frame(root)
    tk.Label(nat_frame, text="Ministerio:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
    ministry_menu = ttk.Combobox(nat_frame, textvariable=ministry_var, values=MINISTRY_OPTIONS, state="readonly")
    ministry_menu.grid(row=0, column=1, padx=5, pady=5, sticky="we")
    tk.Label(nat_frame, text="Tipo de convocatoria:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
    calltype_menu = ttk.Combobox(nat_frame, textvariable=calltype_var, values=CALLTYPE_OPTIONS, state="readonly")
    calltype_menu.grid(row=1, column=1, padx=5, pady=5, sticky="we")

    # Results area and information label (shared between modes)
    results_text = scrolledtext.ScrolledText(root, wrap=tk.WORD, width=120, height=25)
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

    # Function to update visible frame based on selected mode
    def update_mode(*args) -> None:
        mode = mode_var.get()
        if mode == "International":
            nat_frame.grid_forget()
            intl_frame.grid(row=1, column=0, columnspan=3, padx=5, pady=5, sticky="we")
        else:
            intl_frame.grid_forget()
            nat_frame.grid(row=1, column=0, columnspan=3, padx=5, pady=5, sticky="we")
        # Clear results when switching modes
        results_text.configure(state="normal")
        results_text.delete(1.0, tk.END)
        results_text.configure(state="disabled")

    # Attach callback to mode_var changes
    mode_var.trace_add("write", update_mode)

    # Invoke once to show the initial frame
    update_mode()

    # International search functions
    def search_online_international() -> None:
        results_text.configure(state="normal")
        results_text.delete(1.0, tk.END)
        selected_theme = theme_var.get()
        theme_filter = "" if selected_theme == "Select a theme" else selected_theme
        selected_ods = ods_var.get()
        ods_number = ""
        if selected_ods and selected_ods != SDG_OPTIONS[0]:
            ods_number = selected_ods.split("–")[0].strip()
        kw = keyword_var.get().strip().lower()
        selected_site = site_var.get()
        start_time = time.time()
        today = datetime.date.today()
        aggregated: List[Dict] = []
        portal_scrapers = {
            "European Commission": scrape_eu_calls,
            "Wellcome": scrape_wellcome_calls,
            "Academy of Finland": scrape_aka_calls,
            "ANR": scrape_anr_calls,
            "IBRO": scrape_ibro_calls,
            "IDRC": scrape_idrc_calls,
        }
        if selected_site == "All":
            aggregated = load_all_calls(theme_filter, ods_number, kw, today)
        else:
            scraper_func = portal_scrapers.get(selected_site)
            if scraper_func is None:
                aggregated = []
            else:
                portal_slug = slugify(selected_site)
                theme_slug_local = slugify(theme_filter) if theme_filter else "no_select"
                ods_slug_local = ods_number if ods_number else "no_select"
                cached_calls_portal = load_cache(portal_slug, theme_slug_local, ods_slug_local)
                valid_calls = []
                seen_links_single = set()
                for call in cached_calls_portal:
                    d = parse_date_generic(call.get("deadline_date"))
                    if d is not None and (d - today).days < 7:
                        continue
                    if ods_number and ods_number not in call.get("ods_list", []):
                        continue
                    if kw:
                        if kw not in call.get("title", "").lower() and kw not in call.get("description", "").lower():
                            continue
                    valid_calls.append(call)
                    seen_links_single.add(call.get("link"))
                    if len(valid_calls) >= 10:
                        break
                if valid_calls:
                    aggregated = sorted(
                        valid_calls,
                        key=lambda c: (parse_date_generic(c.get("deadline_date")) or datetime.date.max, c.get("title", ""))
                    )[:10]
                else:
                    aggregated = load_portal_calls(selected_site, scraper_func, theme_filter, ods_number, kw, today, scrape_if_needed=True)
        aggregated_sorted = sorted(
            aggregated,
            key=lambda c: (parse_date_generic(c.get("deadline_date")) or datetime.date.max, c.get("title", ""))
        )
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
        if not aggregated_sorted:
            results_text.insert(tk.END, "No calls matched your filters.\n")
        else:
            for i, call in enumerate(aggregated_sorted, 1):
                results_text.insert(tk.END, f"{i}. {call['title']}\n")
                start_index = results_text.index(tk.END)
                link_text = f"   Link: {call['link']}\n"
                results_text.insert(tk.END, link_text)
                tag_name = f"link_{i}"
                results_text.tag_add(tag_name, f"{start_index} linestart", f"{start_index} lineend")
                results_text.tag_bind(tag_name, "<Button-1>", lambda e, url=call['link']: webbrowser.open_new_tab(url))
                results_text.tag_config(tag_name, foreground="blue", underline=True)
                results_text.insert(tk.END, f"   Opening date: {call['opening_date']} | Deadline: {call['deadline_date']}\n")
                results_text.insert(tk.END, f"   Site: {call['site']}\n")
                results_text.insert(tk.END, "   Summary: " + call['description'] + "\n")
                ods_str = ", ".join(call.get("ods_list", []))
                results_text.insert(tk.END, f"   ODS: {ods_str}\n\n")
        elapsed = time.time() - start_time
        results_text.insert(tk.END, f"Search complete in {elapsed:.2f} seconds. {len(aggregated_sorted)} calls shown.\n")
        results_text.configure(state="disabled")

    def search_csv_international() -> None:
        results_text.configure(state="normal")
        results_text.delete(1.0, tk.END)
        selected_theme = theme_var.get()
        theme_filter_local = "" if selected_theme == "Select a theme" else selected_theme
        selected_ods_local = ods_var.get()
        ods_number_local = ""
        if selected_ods_local and selected_ods_local != SDG_OPTIONS[0]:
            ods_number_local = selected_ods_local.split("–")[0].strip()
        kw_local = keyword_var.get().strip().lower()
        selected_site_local = site_var.get()
        today_local = datetime.date.today()
        theme_slug = slugify(theme_filter_local) if theme_filter_local else "no_select"
        ods_slug = ods_number_local if ods_number_local else "no_select"
        aggregated = []
        if selected_site_local == "All":
            cache_filename = f"cache_all_{theme_slug}_{ods_slug}.csv"
            cache_path = os.path.join(CACHE_DIR, cache_filename)
            if not os.path.exists(cache_path):
                results_text.insert(tk.END, "No CSV found for these filters. Please run 'Search Online' first.\n")
                results_text.configure(state="disabled")
                return
            loaded_calls = load_cache("all", theme_slug, ods_slug)
            for call in loaded_calls:
                d = parse_date_generic(call.get("deadline_date"))
                if d is not None and (d - today_local).days < 7:
                    continue
                if ods_number_local and ods_number_local not in call.get("ods_list", []):
                    continue
                if kw_local:
                    kw_low = kw_local.lower()
                    if kw_low not in call.get("title", "").lower() and kw_low not in call.get("description", "").lower():
                        continue
                aggregated.append(call)
        else:
            portal_slug_local = slugify(selected_site_local)
            cache_filename = f"cache_{portal_slug_local}_{theme_slug}_{ods_slug}.csv"
            cache_path = os.path.join(CACHE_DIR, cache_filename)
            if not os.path.exists(cache_path):
                results_text.insert(tk.END, "No CSV found for these filters. Please run 'Search Online' first.\n")
                results_text.configure(state="disabled")
                return
            loaded_calls = load_cache(portal_slug_local, theme_slug, ods_slug)
            for call in loaded_calls:
                d = parse_date_generic(call.get("deadline_date"))
                if d is not None and (d - today_local).days < 7:
                    continue
                if ods_number_local and ods_number_local not in call.get("ods_list", []):
                    continue
                if kw_local:
                    kw_low = kw_local.lower()
                    if kw_low not in call.get("title", "").lower() and kw_low not in call.get("description", "").lower():
                        continue
                aggregated.append(call)
        if not aggregated:
            results_text.insert(tk.END, "No calls match these filters in the existing CSV. Please run 'Search Online' to update.\n")
            results_text.configure(state="disabled")
            return
        aggregated_sorted = sorted(
            aggregated,
            key=lambda c: (parse_date_generic(c.get("deadline_date")) or datetime.date.max, c.get("title", ""))
        )
        for i, call in enumerate(aggregated_sorted, 1):
            results_text.insert(tk.END, f"{i}. {call['title']}\n")
            start_idx = results_text.index(tk.END)
            link_txt = f"   Link: {call['link']}\n"
            results_text.insert(tk.END, link_txt)
            tag_name = f"link_csv_{i}"
            results_text.tag_add(tag_name, f"{start_idx} linestart", f"{start_idx} lineend")
            results_text.tag_bind(tag_name, "<Button-1>", lambda e, url=call['link']: webbrowser.open_new_tab(url))
            results_text.tag_config(tag_name, foreground="blue", underline=True)
            results_text.insert(tk.END, f"   Opening date: {call['opening_date']} | Deadline: {call['deadline_date']}\n")
            results_text.insert(tk.END, f"   Site: {call['site']}\n")
            results_text.insert(tk.END, "   Summary: " + call['description'] + "\n")
            ods_str = ", ".join(call.get("ods_list", []))
            results_text.insert(tk.END, f"   ODS: {ods_str}\n\n")
        results_text.insert(tk.END, f"Displayed {len(aggregated_sorted)} call(s) from CSV.\n")
        results_text.configure(state="disabled")

    # National search functions
    def search_online_national() -> None:
        results_text.configure(state="normal")
        results_text.delete(1.0, tk.END)
        selected_ministry = ministry_var.get()
        selected_type = calltype_var.get()
        start_time = time.time()
        today = datetime.date.today()
        aggregated_n: List[Dict] = []
        if selected_ministry == "All":
            aggregated_n = load_all_national_calls(selected_type, today, scrape_if_needed=True)
        else:
            aggregated_n = load_national_calls(selected_ministry, selected_type, today, scrape_if_needed=True)
        # Save results to CSV
        with open(CSV_PATH, "w", encoding="utf-8", newline="") as f:
            fieldnames = ["title", "link", "opening_date", "deadline_date", "description", "ods_classification", "site", "type"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for call in aggregated_n:
                ods_str = ", ".join(call.get("ods_list", []))
                writer.writerow({
                    "title": call.get("title", ""),
                    "link": call.get("link", ""),
                    "opening_date": call.get("opening_date", ""),
                    "deadline_date": call.get("deadline_date", ""),
                    "description": call.get("description", ""),
                    "ods_classification": ods_str,
                    "site": call.get("site", ""),
                    "type": call.get("type", ""),
                })
        if not aggregated_n:
            results_text.insert(tk.END, "No hay convocatorias que coincidan con estos filtros.\n")
        else:
            for i, call in enumerate(aggregated_n, 1):
                results_text.insert(tk.END, f"{i}. {call['title']}\n")
                start_idx = results_text.index(tk.END)
                link_txt = f"   Link: {call['link']}\n"
                results_text.insert(tk.END, link_txt)
                tag_name = f"nlink_{i}"
                results_text.tag_add(tag_name, f"{start_idx} linestart", f"{start_idx} lineend")
                results_text.tag_bind(tag_name, "<Button-1>", lambda e, url=call['link']: webbrowser.open_new_tab(url))
                results_text.tag_config(tag_name, foreground="blue", underline=True)
                results_text.insert(tk.END, f"   Fecha de apertura: {call['opening_date']} | Fecha de cierre: {call['deadline_date']}\n")
                results_text.insert(tk.END, f"   Ministerio: {call['site']}\n")
                results_text.insert(tk.END, "   Descripción: " + call['description'] + "\n")
                results_text.insert(tk.END, f"   Tipo: {call.get('type', '')}\n\n")
        elapsed = time.time() - start_time
        results_text.insert(tk.END, f"Consulta completada en {elapsed:.2f} segundos. Se muestran {len(aggregated_n)} convocatorias.\n")
        results_text.configure(state="disabled")

    def search_csv_national() -> None:
        results_text.configure(state="normal")
        results_text.delete(1.0, tk.END)
        selected_ministry = ministry_var.get()
        selected_type = calltype_var.get()
        today_local = datetime.date.today()
        ministry_slug = MINISTRY_SLUGS.get(selected_ministry, "all")
        calltype_slug = CALLTYPE_SLUGS.get(selected_type, "no_select")
        aggregated_n = []
        if selected_ministry == "All":
            # Load all ministries individually without scraping
            for m in MINISTRY_OPTIONS:
                if m == "All":
                    continue
                m_slug = MINISTRY_SLUGS.get(m, "")
                cache_calls = load_national_cache(m_slug, calltype_slug)
                for call in cache_calls:
                    d = parse_date_generic(call.get("deadline_date"))
                    if d is not None and (d - today_local).days < 7:
                        continue
                    if selected_type != "All" and call.get("type", "") != selected_type:
                        continue
                    aggregated_n.append(call)
        else:
            cache_calls = load_national_cache(ministry_slug, calltype_slug)
            for call in cache_calls:
                d = parse_date_generic(call.get("deadline_date"))
                if d is not None and (d - today_local).days < 7:
                    continue
                if selected_type != "All" and call.get("type", "") != selected_type:
                    continue
                aggregated_n.append(call)
        if not aggregated_n:
            results_text.insert(tk.END, "No hay convocatorias almacenadas para estos filtros. Ejecute 'Search Online' para actualizar.\n")
            results_text.configure(state="disabled")
            return
        # Sort results by deadline and display
        aggregated_sorted = sorted(
            aggregated_n,
            key=lambda c: (parse_date_generic(c.get("deadline_date")) or datetime.date.max, c.get("title", ""))
        )
        for i, call in enumerate(aggregated_sorted, 1):
            results_text.insert(tk.END, f"{i}. {call['title']}\n")
            start_idx = results_text.index(tk.END)
            link_txt = f"   Link: {call['link']}\n"
            results_text.insert(tk.END, link_txt)
            tag_name = f"nlink_csv_{i}"
            results_text.tag_add(tag_name, f"{start_idx} linestart", f"{start_idx} lineend")
            results_text.tag_bind(tag_name, "<Button-1>", lambda e, url=call['link']: webbrowser.open_new_tab(url))
            results_text.tag_config(tag_name, foreground="blue", underline=True)
            results_text.insert(tk.END, f"   Fecha de apertura: {call['opening_date']} | Fecha de cierre: {call['deadline_date']}\n")
            results_text.insert(tk.END, f"   Ministerio: {call['site']}\n")
            results_text.insert(tk.END, "   Descripción: " + call['description'] + "\n")
            results_text.insert(tk.END, f"   Tipo: {call.get('type', '')}\n\n")
        results_text.insert(tk.END, f"Se muestran {len(aggregated_sorted)} convocatorias desde el CSV.\n")
        results_text.configure(state="disabled")

    # Clear function resets all inputs and results
    def on_clear() -> None:
        theme_var.set("Select a theme")
        ods_var.set(SDG_OPTIONS[0])
        keyword_var.set("")
        site_var.set(SITE_OPTIONS[-1])
        ministry_var.set(MINISTRY_OPTIONS[-1])
        calltype_var.set(CALLTYPE_OPTIONS[0])
        results_text.configure(state="normal")
        results_text.delete(1.0, tk.END)
        results_text.configure(state="disabled")

    # Bind search buttons based on mode
    def search_online() -> None:
        if mode_var.get() == "International":
            search_online_international()
        else:
            search_online_national()

    def search_csv() -> None:
        if mode_var.get() == "International":
            search_csv_international()
        else:
            search_csv_national()

    # Layout for buttons and results
    clear_button = tk.Button(root, text="Clear", command=on_clear)
    clear_button.grid(row=4, column=0, padx=5, pady=10, sticky="we")
    search_online_button = tk.Button(root, text="Search Online", command=search_online)
    search_online_button.grid(row=4, column=1, padx=5, pady=10, sticky="we")
    search_csv_button = tk.Button(root, text="Search CSV", command=search_csv)
    search_csv_button.grid(row=4, column=2, padx=5, pady=10, sticky="we")
    results_text.grid(row=5, column=0, columnspan=3, padx=5, pady=5, sticky="nsew")
    info_label.grid(row=6, column=0, columnspan=3, padx=5, pady=5, sticky="w")
    # Configure row/column weights
    root.grid_rowconfigure(5, weight=1)
    root.grid_columnconfigure(0, weight=0)
    root.grid_columnconfigure(1, weight=1)
    root.grid_columnconfigure(2, weight=1)

    root.mainloop()


###############################################################################
# Entry point
###############################################################################

if __name__ == "__main__":
    run_gui()