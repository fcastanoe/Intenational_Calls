#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Graphical scraper for the EU calls-for-proposals portal.

This script builds on the basic scraping logic by providing a small user
interface built with Tkinter.  Users can select a "Line Theme" from a
predefined list of research areas, choose one of the 17 United Nations
Sustainable Development Goals (SDGs), and supply arbitrary keywords.
Pressing the "Search" button triggers a headless Selenium session that
applies the selected filters on the EU portal, retrieves matching calls,
extrae el texto completo de la descripción de cada una y luego lo
resume de forma local (sin usar servicios externos) antes de mostrarlo
en la interfaz.  The
"Clear" button resets all input fields and clears the output area.

La selección de ODS se aplica de forma local: después de resumir una
convocatoria, se clasifican sus temas mediante coincidencias de palabras
clave asociadas a cada uno de los 17 Objetivos de Desarrollo Sostenible.

This script requires the following Python packages:

- selenium
- beautifulsoup4
- tkinter (usually included with standard Python installs)

The script also assumes Google Chrome is installed and available
together with the appropriate ChromeDriver.  The Selenium driver is
configured to run in headless mode so the scraping can occur without
opening a visible browser window.
"""

import os
import time
import csv
from urllib.parse import urljoin
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed

import re

# Try to import gensim for more advanced summarisation.  If neither
# library is available, the code will fall back to a simple summariser.  We
# attempt imports here so that the presence of these packages can be
# detected at runtime.  Users running this script locally can install
# gensim via pip to enable more sophisticated summaries.
try:
    # gensim.summarization.summarize returns a summarised string based on
    # algorithm TextRank.  We import the function under a specific name
    # so that the fallback logic in summarize_text can detect it.
    from gensim.summarization import summarize as gensim_summarize  # type: ignore
    _HAS_GENSIM = True
except Exception:
    gensim_summarize = None  # type: ignore
    _HAS_GENSIM = False

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup

# Tkinter is used for the GUI; if not installed it will raise an
# ImportError when starting the script.  Tkinter is part of the
# standard library on most systems.
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox


###############################################################################
# Configuration
###############################################################################

# Directory and filename where results will be stored.  The CSV file will be
# overwritten on each search.
OUTPUT_DIR = "data/scraping_results"
CSV_PATH = os.path.join(OUTPUT_DIR, "calls_for_proposals.csv")

# OpenAI API key – ensure this environment variable or a secret key
# exists on your machine.  You may choose to set it here directly, but
# for security reasons storing it in an environment variable is more
# advisable.
# No API key needed for local summarisation and classification.  The key
# was previously used for OpenAI, but local summarisation no longer
# requires it.

BASE_URL = "https://ec.europa.eu"
# Base URL without keywords parameter.  When a theme is selected, a
# 'keywords' query string will be appended to this URL.  Results are
# sorted by deadline date and include both open (31094501) and
# forthcoming (31094502) statuses.  See user instructions for
# encoding spaces with %20 via urllib.parse.quote.
URL_1 = (
    "https://ec.europa.eu/info/funding-tenders/opportunities/portal/"
    "screen/opportunities/calls-for-proposals?"
    "order=ASC&pageNumber=1&pageSize=100&sortBy=deadlineDate"
    "&isExactMatch=true&status=31094501,31094502"
)

# A list of research topics that users can choose from in the GUI.  These
# correspond to many of the "Quick search" options visible on the EU portal.
# While the portal exposes dozens of categories, this list contains a
# representative subset of themes encountered during manual exploration.
THEME_OPTIONS = [
    "Artificial Intelligence",
    "Robotics",
    "Cybersecurity",
    "Biotechnology",
    "Health",
    "Medical Research",
    "Climate Change",
    "Renewable Energy",
    "Sustainable Agriculture",
    "Smart Cities",
    "Digital Transformation",
    "Green Technologies",
    "Environmental Conservation",
    "Water Management",
    "Urban Mobility",
    "Clean Technologies",
    "Space Research",
    "Transport Innovation",
    "Food Security",
    "Social Innovation",
    "Inclusive Society",
    "Cultural Heritage",
    "Climate Action",
    "Education and Skills",
    "Public Safety",
    "Manufacturing and Industry",
    "Waste Management",
    "Energy Efficiency",
    "Digital Economy",
    "Public Health",
    # Additional options observed on the portal's quick search list
    "Social sciences and humanities",
    "International cooperation",
    "Gender",
    "Digital Agenda",
    "Social sciences, interdisciplinary",
    "Environment, resources and sustainability",
    "Political systems and institutions / governance",
    "Circular economy",
    "Responsible Research and Innovation",
    "Entrepreneurship",
    "Climate change adaptation",
    "Technological innovation",
    "Renewable energy sources - general",
    "Societal Engagement",
    "Accelerating Clean Energy Innovation",
    "Chemical engineering",
    "Energy efficiency - general",
    "Technology development",
    "Hydrogen",
    "Mechanical engineering",
    "Agriculture, Rural Development, Fisheries",
    "Internet of Things",
    "Energy",
    "Rail Transport",
    "Sustainable transport",
    "Climatology and climate change",
    "Public health",  # duplicate but ensures presence
    "Bioprocessing technologies",
    "Environmental change and society",
    "Sustainability",
    "Agronomy",
    "Clinical trials",
    "Big data",
    "Environment, Pollution & Climate",
    "Higher education",
    "Regulatory framework for innovation",
    "Technology management",
    "Sociology",
    "Education",
    "Energy efficient buildings",
    "SME support",
    "Industrial biotechnology",
    "Circular economy",
]

# Sustainable Development Goals (SDGs) options for the GUI.  Users can
# pick one of these, although the script does not currently filter
# results by SDG; it simply records the choice for future use.
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


###############################################################################
# Selenium utilities
###############################################################################

def create_driver():
    """Configure and return a headless Selenium WebDriver."""
    chrome_opts = Options()
    chrome_opts.add_argument("--headless")
    chrome_opts.add_argument("--disable-gpu")
    chrome_opts.add_argument("--no-sandbox")
    # Some websites detect headless Chrome; using these arguments can
    # sometimes mitigate detection.
    chrome_opts.add_argument("--disable-blink-features=AutomationControlled")
    driver = webdriver.Chrome(options=chrome_opts)
    return driver


def accept_cookies(driver):
    """Click the cookie consent button if present."""
    try:
        btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
        )
        btn.click()
    except Exception:
        pass


def filter_by_theme(driver, theme):
    """
    Filter calls for proposals by theme and return metadata for the
    first ten results.  Metadata includes title, link, opening date
    and deadline.

    Parameters
    ----------
    driver : selenium.webdriver
        A web driver instance.
    theme : str
        The research theme to use as the keywords filter.  If blank
        or None, no filter is applied and the default page is loaded.

    Returns
    -------
    list[dict]
        A list of dictionaries with keys 'title', 'link',
        'opening_date' and 'deadline_date'.
    """
    # Build the search URL.  When a theme is provided, append the
    # 'keywords' parameter to the base URL, encoding any spaces or
    # special characters.  Without a theme the base URL is used.  The
    # resulting page sorts calls by deadline date.
    from urllib.parse import quote

    if theme:
        encoded = quote(theme)
        search_url = URL_1 + f"&keywords={encoded}"
    else:
        search_url = URL_1

    # Navigate to the search page and accept cookies
    driver.get(search_url)
    accept_cookies(driver)

    # Wait until at least one call card is present
    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, "eui-card-header-title a.eui-u-text-link")
        )
    )

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


def get_calls_page(driver, theme: str, page_number: int) -> list:
    """
    Retrieve call metadata from a specific page number and optional theme.

    Parameters
    ----------
    driver : selenium.webdriver
        A web driver instance.
    theme : str
        The research theme used as the keywords filter.  If blank, no
        keywords parameter is added.
    page_number : int
        The page number to request (1-indexed).

    Returns
    -------
    list[dict]
        A list of call metadata dictionaries containing title, link,
        opening_date, and deadline_date.
    """
    from urllib.parse import quote
    # Build the URL with the desired page number
    base_params = (
        f"order=ASC&pageNumber={page_number}&pageSize=100&sortBy=deadlineDate"
        "&isExactMatch=true&status=31094501,31094502"
    )
    if theme:
        encoded = quote(theme)
        search_url = (
            "https://ec.europa.eu/info/funding-tenders/opportunities/portal/"
            "screen/opportunities/calls-for-proposals?"
            + base_params
            + f"&keywords={encoded}"
        )
    else:
        search_url = (
            "https://ec.europa.eu/info/funding-tenders/opportunities/portal/"
            "screen/opportunities/calls-for-proposals?" + base_params
        )
    driver.get(search_url)
    accept_cookies(driver)
    # Wait for cards to load
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


def fetch_and_extract_description(driver, url):
    """
    Given a call's details page, extract the "Expected Outcome" section.

    We navigate to the given URL, wait for the section to load and then
    parse out paragraphs and bullet items until another section begins.

    Parameters
    ----------
    driver : selenium.webdriver
        A web driver instance.
    url : str
        The full URL of the call's details page.

    Returns
    -------
    str
        The concatenated contents of the Expected Outcome section.  If
        not found, returns an empty string.
    """
    driver.get(url)
    accept_cookies(driver)
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located(
                (
                    By.XPATH,
                    "//eui-card-header-title[contains(., 'Topic description')]",
                )
            )
        )
    except TimeoutException:
        return ""
    soup = BeautifulSoup(driver.page_source, "html.parser")
    header = soup.find(
        "eui-card-header-title",
        string=lambda t: t and "Topic description" in t,
    )
    if not header:
        return ""
    card = header.find_parent("eui-card")
    if not card:
        return ""
    content = card.find("eui-card-content")
    if not content:
        return ""
    # Collect all paragraphs and list items under the Topic description content.
    # Some calls subdivide their topic descriptions into Expected Outcome,
    # Scope, Activities, etc.  Instead of limiting to one section, we
    # extract all textual content contained in <p> and <li> elements
    # found within the card's content.
    parts = []
    for elem in content.find_all(["p", "li"]):
        text = elem.get_text(" ", strip=True)
        if text:
            if elem.name == "li":
                parts.append(f"- {text}")
            else:
                parts.append(text)
    return "\n".join(parts)


def summarize_text(text: str, max_tokens: int = 200) -> str:
    """
    Produce un resumen conciso del texto proporcionado sin usar servicios externos.

    Este resumidor local simplemente extrae las primeras `word_limit` palabras del
    texto para formar un resumen.  Si el texto contiene menos palabras, se
    devuelve intacto.

    Parameters
    ----------
    text : str
        El texto a resumir.  Si está vacío, se devuelve una cadena vacía.
    max_tokens : int
        No utilizado en la versión local, pero mantenido por compatibilidad.

    Returns
    -------
    str
        Un resumen breve del texto, utilizando las primeras 100 palabras.
    """
    if not text:
        return ""
    # Si se dispone de gensim, usar su algoritmo TextRank para generar un resumen.
    # Este método intenta generar un resumen basado en importancia de frases.  Se
    # utiliza 'word_count' para limitar la extensión del resumen.  Si gensim
    # devuelve una cadena vacía (sucede con textos muy cortos), continuamos.
    if _HAS_GENSIM and gensim_summarize is not None:
        try:
            # Utilizamos word_count en lugar de ratio para tener más control
            summary = gensim_summarize(text, word_count=100)
            if summary:
                # gensim devuelve una cadena; aseguramos que se recorta
                return summary.strip()
        except Exception:
            pass
    # Si no hay librerías avanzadas, o fallan, se recurre a un resumen simple.
    # Limitar el número de palabras en el resumen.  Ajusta word_limit si
    # necesitas resúmenes más largos o más cortos.
    word_limit = 100
    tokens = text.split()
    if len(tokens) <= word_limit:
        return text.strip()
    else:
        summary_tokens = tokens[:word_limit]
        return " ".join(summary_tokens).strip() + " …"


def classify_ods(summary: str) -> list:
    """
    Clasifica un resumen en uno o más Objetivos de Desarrollo Sostenible (ODS)
    utilizando coincidencias de palabras clave.

    Esta función no depende de ninguna API externa.  Se analiza el resumen
    en minúsculas y se buscan palabras clave asociadas a cada ODS.  Si una
    palabra clave aparece, el ODS correspondiente se añade a la lista.
    Si no se encuentran coincidencias, se devuelve ['unknown'].

    Parameters
    ----------
    summary : str
        El resumen del que extraer palabras clave.

    Returns
    -------
    list[str]
        Una lista con los números de ODS relevantes, como strings.  Si no se
        identifica ninguno, se devuelve ['unknown'].
    """
    if not summary:
        return ["unknown"]
    text = summary.lower()
    # Diccionario de palabras clave para cada ODS.  Las palabras clave deben
    # mantenerse en minúsculas para la comparación.  Puedes ampliar este
    # diccionario con más sinónimos según sea necesario.
    ods_keywords = {
        "1": ["poverty", "poor", "income", "social protection", "financial", "eradicate poverty"],
        "2": ["hunger", "food", "nutrition", "agriculture", "farmers", "food security", "malnutrition"],
        "3": ["health", "well-being", "disease", "medical", "medicine", "healthcare", "infection", "mental"],
        "4": ["education", "learning", "school", "literacy", "training", "academic", "skills"],
        "5": ["gender", "women", "girls", "equality", "empower", "discrimination", "violence against women"],
        "6": ["water", "sanitation", "clean water", "wastewater", "hygiene", "drinking water"],
        "7": ["energy", "renewable", "clean energy", "electricity", "power", "affordable energy"],
        "8": ["employment", "jobs", "work", "economic growth", "productivity", "labor", "business", "entrepreneurship"],
        "9": ["industry", "innovation", "infrastructure", "technology", "engineering", "development", "transport", "communication", "manufacturing"],
        "10": ["inequality", "marginalized", "equal opportunity", "income disparity", "discrimination", "disabled"],
        "11": ["urban", "city", "community", "housing", "transport", "infrastructure", "public space", "resilience", "urbanization"],
        "12": ["consumption", "production", "sustainable", "recycling", "waste", "supply chain", "resource efficiency"],
        "13": ["climate", "global warming", "greenhouse", "carbon", "emissions", "resilience", "climate change", "mitigation", "adaptation"],
        "14": ["oceans", "sea", "marine", "fish", "aquatic", "marine biodiversity", "overfishing", "coral"],
        "15": ["forests", "land", "biodiversity", "ecosystems", "flora", "fauna", "wildlife", "conservation", "soil", "deforestation", "desertification"],
        "16": ["peace", "justice", "institutions", "rule of law", "human rights", "transparency", "corruption", "violence", "democracy"],
        "17": ["partnership", "cooperation", "international", "finance", "capacity-building", "technology transfer", "policy", "global", "collaboration", "alliances"],
    }
    matched_ods = []
    for ods_num, keywords in ods_keywords.items():
        for kw in keywords:
            if kw in text:
                matched_ods.append(ods_num)
                break
    if not matched_ods:
        return ["unknown"]
    # Eliminar duplicados y ordenar
    unique_ods = sorted(set(matched_ods), key=lambda x: int(x))
    return unique_ods


###############################################################################
# GUI definition
###############################################################################

def run_gui():
    """Create the GUI and start the Tkinter main loop."""
    # Ensure the output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    root = tk.Tk()
    root.title("EU Calls for Proposals Scraper")
    root.geometry("900x600")

    # Variables to hold the selected options
    theme_var = tk.StringVar()
    theme_var.set("Select a theme")
    ods_var = tk.StringVar()
    ods_var.set(SDG_OPTIONS[0])  # default 'No selection'
    keyword_var = tk.StringVar()
    # How many calls the user wants to retrieve (1,3,5,10,15,20,25,30)
    results_limit_var = tk.StringVar()
    results_limit_var.set("10")  # default number of calls to retrieve

    # Function invoked when user clicks "Search"
    def on_search():
        # Clear previous results from the text area
        results_text.delete(1.0, tk.END)

        # Record start time for performance measurement
        start_time = time.time()

        # Retrieve the selections
        selected_theme = theme_var.get()
        selected_ods = ods_var.get()
        keywords = keyword_var.get().strip().lower()
        # Limit on number of calls to display
        try:
            results_limit = int(results_limit_var.get())
        except ValueError:
            results_limit = 10

        # Provide some feedback in the GUI
        results_text.insert(tk.END, "Buscando convocatorias...\n")
        results_text.update()

        # Determine filter flags
        has_theme_filter = selected_theme and selected_theme != "Select a theme"
        has_ods_filter = selected_ods and selected_ods != SDG_OPTIONS[0]
        has_keyword_filter = bool(keywords)

        # Parse SDG number from selected ODS string, if applicable
        selected_ods_number = None
        if has_ods_filter:
            selected_ods_number = selected_ods.split("–")[0].strip()

        # Prepare variables for scraping and caching
        import datetime
        today = datetime.date.today()
        final_data = []
        page_number = 1

        # Construct cache file name based on theme and ODS
        import re
        def slugify(value: str) -> str:
            value = value.lower().strip()
            value = re.sub(r"\s+", "_", value)
            value = re.sub(r"[^a-z0-9_]+", "", value)
            return value

        theme_slug = slugify(selected_theme) if has_theme_filter else "general"
        ods_slug = selected_ods_number if selected_ods_number else ""
        cache_filename = f"cache_{theme_slug}_{ods_slug}.csv"
        cache_path = os.path.join(OUTPUT_DIR, cache_filename)

        # Load cached results if they exist and filter out expired ones
        cached_results = []
        if os.path.isfile(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as cf:
                    reader = csv.DictReader(cf)
                    for row in reader:
                        # Convert deadline date to datetime for expiry check
                        deadline_str = row.get("deadline_date", "")
                        parsed_date = None
                        if deadline_str:
                            try:
                                parsed_date = datetime.datetime.strptime(deadline_str, "%d %B %Y").date()
                            except ValueError:
                                parsed_date = None
                        # Skip expired entries (within 7 days of deadline)
                        if parsed_date is not None and (parsed_date - today).days < 7:
                            continue
                        # When ODS filter exists, ensure cached entry matches
                        ods_list = row.get("ods_classification", "").replace(" ", "").split(",") if row.get("ods_classification") else []
                        if has_ods_filter and selected_ods_number not in ods_list:
                            continue
                        # When keyword filter exists, filter by keyword in title or description
                        if has_keyword_filter and not (
                            (keywords in row.get("title", "").lower()) or
                            (keywords in row.get("description", "").lower())
                        ):
                            continue
                        # Append to cached results
                        cached_results.append({
                            "title": row.get("title"),
                            "link": row.get("link"),
                            "opening_date": row.get("opening_date"),
                            "deadline_date": row.get("deadline_date"),
                            "description": row.get("description"),
                            "ods_list": ods_list if ods_list else ["unknown"],
                        })
            except Exception:
                pass

        # Add cached results to final_data up to the limit (avoid duplicates)
        seen_titles = set()
        for item in cached_results:
            if len(final_data) >= results_limit:
                break
            if item["title"] in seen_titles:
                continue
            final_data.append(item)
            seen_titles.add(item["title"])

        # Determine how many additional calls we need to fetch
        needed = results_limit - len(final_data)

        # Scrape additional calls if needed
        # The scraping process fetches pages sequentially and collects candidates until
        # enough results are available.  To improve performance, we gather a batch
        # of candidates, then summarise and classify them concurrently.  This avoids
        # blocking on individual OpenAI calls and reduces overall execution time.
        # We attempt to collect up to (results_limit * 3) candidates before
        # summarising them; this heuristic balances the number of summarisation
        # tasks versus the likelihood of meeting all filters (ODS, keyword, etc.).
        max_batch = results_limit * 3 if results_limit > 0 else 30
        candidates_to_process = []
        # When we need more calls than available in cache, keep scraping pages
        while needed > 0:
            # Fetch metadata for the current page
            driver = create_driver()
            try:
                meta = get_calls_page(driver, selected_theme if has_theme_filter else "", page_number)
            finally:
                driver.quit()
            if not meta:
                break  # no more pages

            for item in meta:
                if needed <= 0:
                    break
                # Skip duplicates based on title
                title = item["title"]
                if title in seen_titles:
                    continue
                link = item["link"]
                opening_date = item["opening_date"]
                deadline_str = item.get("deadline_date", "")
                parsed_date = None
                if deadline_str:
                    try:
                        parsed_date = datetime.datetime.strptime(deadline_str, "%d %B %Y").date()
                    except ValueError:
                        parsed_date = None
                # Skip calls that expire within 7 days
                if parsed_date is not None and (parsed_date - today).days < 7:
                    continue
                # If only keyword filter (no theme, no ODS), ensure keyword is in title
                if has_keyword_filter and not has_theme_filter and not has_ods_filter:
                    if keywords not in title.lower():
                        continue
                # Candidate qualifies for further processing
                candidates_to_process.append({
                    "title": title,
                    "link": link,
                    "opening_date": opening_date,
                    "deadline_date": deadline_str,
                })
                # When we collect a large batch of candidates, break to summarise them
                if len(candidates_to_process) >= max_batch:
                    break
            # Summarise and classify collected candidates if batch size reached or end of page
            if candidates_to_process and (len(candidates_to_process) >= max_batch or needed <= 0):
                # Process each candidate: fetch description, summarise and classify concurrently
                processed = []
                # Fetch descriptions sequentially (driver for each) to avoid stale elements
                for cand in candidates_to_process:
                    detail_driver = create_driver()
                    try:
                        desc = fetch_and_extract_description(detail_driver, cand["link"])
                    finally:
                        detail_driver.quit()
                    cand["text_for_summary"] = desc if desc else cand["title"]
                # Use ThreadPoolExecutor to summarise and classify in parallel
                # Prepare a helper to summarise and classify a single candidate
                def summarise_and_classify(c):
                    summary_local = summarize_text(c["text_for_summary"])
                    ods_local = classify_ods(summary_local)
                    return summary_local, ods_local

                with ThreadPoolExecutor(max_workers=min(5, len(candidates_to_process))) as executor:
                    future_to_cand = {
                        executor.submit(summarise_and_classify, cand): cand
                        for cand in candidates_to_process
                    }
                    for future in as_completed(future_to_cand):
                        cand = future_to_cand[future]
                        try:
                            summary, ods_list = future.result()
                        except Exception:
                            summary, ods_list = "", ["unknown"]
                        # If ODS filter, ensure match
                        if has_ods_filter and selected_ods_number not in ods_list:
                            continue
                        # Additional keyword filter for theme/ODS combination: check keyword in title or summary
                        if has_keyword_filter and (has_theme_filter or has_ods_filter):
                            if not (keywords in cand["title"].lower() or keywords in summary.lower()):
                                continue
                        # Qualify candidate and append
                        candidate = {
                            "title": cand["title"],
                            "link": cand["link"],
                            "opening_date": cand["opening_date"],
                            "deadline_date": cand["deadline_date"],
                            "description": summary,
                            "ods_list": ods_list if ods_list else ["unknown"],
                        }
                        final_data.append(candidate)
                        seen_titles.add(cand["title"])
                        needed -= 1
                        cached_results.append(candidate)
                        if needed <= 0:
                            break
                # Clear candidates list for next batch
                candidates_to_process = []
            # Move to next page
            page_number += 1
            # If after processing this page we still don't have enough, continue; else break out of loop automatically by condition

        # Update cache file with new results if necessary
        try:
            with open(cache_path, "w", newline="", encoding="utf-8") as cf:
                fieldnames_cache = ["title", "link", "opening_date", "deadline_date", "description", "ods_classification"]
                writer = csv.DictWriter(cf, fieldnames=fieldnames_cache)
                writer.writeheader()
                for item in cached_results:
                    writer.writerow({
                        "title": item["title"],
                        "link": item["link"],
                        "opening_date": item["opening_date"],
                        "deadline_date": item["deadline_date"],
                        "description": item["description"],
                        "ods_classification": ",".join(item.get("ods_list", [])),
                    })
        except Exception:
            pass

        # End timing and compute elapsed time
        elapsed_time = time.time() - start_time

        # Save results to CSV
        fieldnames = ["title", "link", "opening_date", "deadline_date", "description", "ods_classification"]
        with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for item in final_data:
                writer.writerow({
                    "title": item["title"],
                    "link": item["link"],
                    "opening_date": item["opening_date"],
                    "deadline_date": item["deadline_date"],
                    "description": item["description"],
                    "ods_classification": ", ".join(item.get("ods_list", [])),
                })

        # Display results in the GUI
        if not final_data:
            results_text.insert(tk.END, "No se encontraron convocatorias que coincidan con los filtros.\n")
        else:
            for i, item in enumerate(final_data, 1):
                # Title
                results_text.insert(tk.END, f"{i}. {item['title']}\n")
                # Link: insert as clickable hyperlink
                start_index = results_text.index(tk.END)
                results_text.insert(tk.END, f"   Enlace: {item['link']}\n")
                end_index = results_text.index(tk.END)
                tag = f"link_{i}"
                results_text.tag_add(tag, start_index, end_index)
                results_text.tag_config(tag, foreground="blue", underline=True)
                # Use lambda to capture current URL
                results_text.tag_bind(tag, "<Button-1>", lambda e, url=item['link']: webbrowser.open(url))
                # Dates
                results_text.insert(tk.END, f"   Inicio: {item['opening_date']} | Cierre: {item['deadline_date']}\n")
                # Summary
                results_text.insert(tk.END, "   Resumen (en): " + item['description'] + "\n")
                # ODS classification
                ods_display = ", ".join(item.get("ods_list", []))
                results_text.insert(tk.END, f"   ODS clasificado: {ods_display}\n\n")

        # Show scraping time
        results_text.insert(tk.END, f"Búsqueda completada en {elapsed_time:.2f} segundos.\n")

    # Function invoked when user clicks "Clear"
    def on_clear():
        theme_var.set("Select a theme")
        ods_var.set(SDG_OPTIONS[0])
        keyword_var.set("")
        results_text.delete(1.0, tk.END)

    # Layout: we organise the widgets using grid geometry manager
    # Theme selector
    theme_label = tk.Label(root, text="Line Theme:")
    theme_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")
    theme_menu = ttk.Combobox(root, textvariable=theme_var, values=THEME_OPTIONS, state="readonly")
    theme_menu.grid(row=0, column=1, padx=5, pady=5, sticky="we")

    # SDG selector
    ods_label = tk.Label(root, text="SDG:")
    ods_label.grid(row=1, column=0, padx=5, pady=5, sticky="w")
    ods_menu = ttk.Combobox(root, textvariable=ods_var, values=SDG_OPTIONS, state="readonly")
    ods_menu.grid(row=1, column=1, padx=5, pady=5, sticky="we")

    # Keyword entry
    keyword_label = tk.Label(root, text="Keywords:")
    keyword_label.grid(row=2, column=0, padx=5, pady=5, sticky="w")
    keyword_entry = tk.Entry(root, textvariable=keyword_var, width=30)
    keyword_entry.grid(row=2, column=1, padx=5, pady=5, sticky="we")

    # Row 3: Results limit selector
    results_limit_label = tk.Label(root, text="Number of calls:")
    results_limit_label.grid(row=3, column=0, padx=5, pady=5, sticky="w")
    results_limit_menu = ttk.Combobox(root, textvariable=results_limit_var, values=["1", "3", "5", "10", "15", "20", "25", "30"], state="readonly")
    results_limit_menu.grid(row=3, column=1, padx=5, pady=5, sticky="we")

    # Search and clear buttons on row 4
    search_button = tk.Button(root, text="Search", command=on_search)
    search_button.grid(row=4, column=0, padx=5, pady=10, sticky="we")
    clear_button = tk.Button(root, text="Clear", command=on_clear)
    clear_button.grid(row=4, column=1, padx=5, pady=10, sticky="we")

    # Results display: scrolled text widget (row 6)
    results_text = scrolledtext.ScrolledText(root, wrap=tk.WORD, width=100, height=20)
    results_text.grid(row=6, column=0, columnspan=2, padx=5, pady=5, sticky="nsew")

    # Informational label explaining how SDG classification is obtained (row 5)
    classification_info = tk.Label(
        root,
        text=(
            "La clasificación ODS se determina automáticamente usando palbras claves "
            "que analiza el resumen de cada convocatoria. Si el modelo "
            "no puede asignar un ODS, se marcará como 'unknown'."
        ),
        wraplength=800,
        justify="left",
    )
    classification_info.grid(row=5, column=0, columnspan=2, padx=5, pady=5, sticky="w")

    # Configure row/column weights so the text area expands with window
    root.grid_rowconfigure(6, weight=1)
    root.grid_columnconfigure(1, weight=1)

    # Start the Tk event loop
    root.mainloop()


###############################################################################
# Entry point
###############################################################################

if __name__ == "__main__":
    run_gui()