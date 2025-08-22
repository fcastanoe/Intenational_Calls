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
import datetime
import re

# Try to import gensim or sumy for more advanced summarisation.  If neither
# library is available, the code will fall back to a simple summariser.  We
# attempt imports here so that the presence of these packages can be
# detected at runtime.  Users running this script locally can install
# gensim or sumy via pip to enable more sophisticated summaries.
try:
    # gensim.summarization.summarize returns a summarised string based on
    # algorithm TextRank.  We import the function under a specific name
    # so that the fallback logic in summarize_text can detect it.
    from gensim.summarization import summarize as gensim_summarize  # type: ignore
    _HAS_GENSIM = True
except Exception:
    gensim_summarize = None  # type: ignore
    _HAS_GENSIM = False

try:
    # sumy library provides various summarizers.  We'll pick the LSA
    # summarizer as a default.  If sumy is available, these imports
    # succeed; otherwise they will raise ImportError.
    from sumy.parsers.plaintext import PlaintextParser  # type: ignore
    from sumy.nlp.tokenizers import Tokenizer  # type: ignore
    from sumy.summarizers.lsa import LsaSummarizer  # type: ignore
    _HAS_SUMY = True
except Exception:
    PlaintextParser = None  # type: ignore
    Tokenizer = None  # type: ignore
    LsaSummarizer = None  # type: ignore
    _HAS_SUMY = False
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
    # Si se dispone de sumy, usar el LSA summarizer.  Definimos un
    # analizador y un tokenizador para inglés por defecto.  Si el texto
    # está en otro idioma, el resumen será menos preciso pero no se
    # interrumpirá la ejecución.
    if _HAS_SUMY and PlaintextParser is not None:
        try:
            parser = PlaintextParser.from_string(text, Tokenizer("english"))
            summarizer = LsaSummarizer()
            # Obtenemos las primeras 5 frases del resumen
            summary_sentences = summarizer(parser.document, 5)
            summary = " ".join(str(sentence) for sentence in summary_sentences)
            summary = summary.strip()
            if summary:
                return summary
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
# Additional scrapers for non‑EU sources
###############################################################################

def scrape_wellcome_calls(theme_filter: str, ods_number: str, keyword: str, max_results: int, today):
    """
    Scrape research funding schemes from Wellcome's funding page.

    Only calls whose "Administering organisation location" includes
    "Low- or middle-income countries" or "anywhere" will be considered.
    This function attempts to extract the title, link, deadline and a short
    description for each call.  It summarises the description locally and
    classifies the summary into SDGs.  Results whose deadlines are within 7
    days of the current date are skipped.  The theme_filter is not used by
    Wellcome (no direct mapping), but keyword and ODS filters are applied
    after summarisation.

    Parameters
    ----------
    theme_filter : str
        Selected theme from the GUI.  Ignored for Wellcome calls.
    ods_number : str
        Selected SDG number to filter by.  An empty string means no filter.
    keyword : str
        Lowercase keyword for matching titles or summaries.  Empty means no keyword filter.
    max_results : int
        Maximum number of calls to return.
    today : datetime.date
        The current date used to check deadline thresholds.

    Returns
    -------
    list[dict]
        A list of call dictionaries with keys 'title', 'link', 'opening_date',
        'deadline_date', 'description' and 'ods_list'.  The opening_date
        field is left empty because the Wellcome listing does not expose
        explicit opening dates.
    """
    results = []
    # Wellcome open/upcoming funding schemes URL with filters for currently
    # accepting and upcoming applications.
    url = (
        "https://wellcome.org/research-funding/schemes"
        "?f%5B0%5D=currently_accepting_applications%3AYes"
        "&f%5B1%5D=currently_accepting_applications%3AUpcoming"
    )
    driver = create_driver()
    try:
        driver.get(url)
        # Attempt to accept a cookie banner if present
        try:
            cookie_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Accept all')]")
            cookie_btn.click()
        except Exception:
            pass
        # Wait for articles representing individual calls.  We expect the
        # page to list at most ~20 calls; each call is rendered within an
        # <article> element containing a heading and other details.
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "article"))
            )
        except Exception:
            return results
        articles = driver.find_elements(By.TAG_NAME, "article")
        for art in articles:
            if len(results) >= max_results:
                break
            try:
                # Each article should contain an <a> with the call title
                link_elem = art.find_element(By.TAG_NAME, "a")
                title = link_elem.text.strip()
                link = link_elem.get_attribute("href")
                # Deadline: look for any element containing the word 'Deadline'
                deadline_text = ""
                try:
                    deadline_elem = art.find_element(By.XPATH, ".//*[contains(text(), 'Deadline')]")
                    # The text might look like 'Deadline: 30 September 2025'
                    deadline_text = deadline_elem.text.split(':')[-1].strip()
                except Exception:
                    pass
                # Parse deadline into date if possible; skip if too soon
                deadline_date_obj = None
                if deadline_text:
                    try:
                        deadline_date_obj = datetime.datetime.strptime(deadline_text, "%d %B %Y").date()
                    except Exception:
                        deadline_date_obj = None
                if deadline_date_obj is not None and (deadline_date_obj - today).days < 7:
                    continue
                # Locate the administering organisation location; it is
                # specified under a <dt> with that label followed by a <dd>
                location_ok = False
                try:
                    loc_label = art.find_element(By.XPATH, ".//*[contains(text(), 'Administering organisation location')]")
                    loc_value = loc_label.find_element(By.XPATH, "following-sibling::*").text
                    loc_value_lower = loc_value.lower()
                    if "low-" in loc_value_lower or "anywhere" in loc_value_lower:
                        location_ok = True
                except Exception:
                    pass
                if not location_ok:
                    continue
                # Fetch the detailed call page to extract a description
                desc_text = ""
                try:
                    detail_driver = create_driver()
                    detail_driver.get(link)
                    # Accept cookies on the detail page if needed
                    try:
                        detail_cookie = detail_driver.find_element(By.XPATH, "//button[contains(text(), 'Accept all')]")
                        detail_cookie.click()
                    except Exception:
                        pass
                    # Extract paragraphs from the main content
                    detail_soup = BeautifulSoup(detail_driver.page_source, "html.parser")
                    paragraphs = detail_soup.find_all("p")
                    parts = [p.get_text(" ", strip=True) for p in paragraphs]
                    desc_text = "\n".join(parts)
                except Exception:
                    desc_text = ""
                finally:
                    try:
                        detail_driver.quit()
                    except Exception:
                        pass
                # Use title if no description
                text_for_summary = desc_text if desc_text else title
                summary = summarize_text(text_for_summary)
                ods_list = classify_ods(summary)
                # Apply ODS filter if requested
                if ods_number and ods_number not in ods_list:
                    continue
                # Apply keyword filter if provided
                if keyword and keyword not in title.lower() and keyword not in summary.lower():
                    continue
                results.append({
                    "title": title,
                    "link": link,
                    "opening_date": "",
                    "deadline_date": deadline_text,
                    "description": summary,
                    "ods_list": ods_list if ods_list else ["unknown"],
                })
            except Exception:
                # Ignore any errors parsing an individual call
                continue
    finally:
        try:
            driver.quit()
        except Exception:
            pass
    return results


def scrape_aka_calls(theme_filter: str, ods_number: str, keyword: str, max_results: int, today):
    """
    Scrape international calls from the Academy of Finland (aka.fi) page.

    The function navigates to the calls page and selects calls listed under
    "International calls".  It extracts the call title, opening date, closing
    date and a short summary from the individual call page.  Only calls with
    deadlines at least 7 days away are considered.  Keywords and ODS
    classifications are applied similarly to other scrapers.

    Parameters
    ----------
    theme_filter : str
        Not used for AKA calls.  Provided for consistency.
    ods_number : str
        Selected SDG number to filter by.
    keyword : str
        Lowercase keyword filter.
    max_results : int
        Maximum number of calls to return (capped at 5 by the GUI).
    today : datetime.date
        The current date used for deadline checking.

    Returns
    -------
    list[dict]
        List of call dictionaries containing metadata and summary.
    """
    results = []
    url = "https://www.aka.fi/en/research-funding/apply-for-funding/calls-for-applications"
    driver = create_driver()
    try:
        driver.get(url)
        # Accept cookie pop-up if present (look for button labelled 'Accept all')
        try:
            cookie_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Accept all')]")
            cookie_btn.click()
        except Exception:
            pass
        # Wait until the International calls section is present
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, "//h2[contains(translate(text(), 'INTERNATIONAL CALLS', 'international calls'), 'international calls')]")
                )
            )
        except Exception:
            return results
        # Locate call containers under the "International calls" heading
        call_links = []
        try:
            call_section = driver.find_element(By.XPATH, "//h2[contains(translate(text(), 'INTERNATIONAL CALLS', 'international calls'), 'international calls')]/following-sibling::*")
            # Find all <a> elements within the section (call titles)
            call_links = call_section.find_elements(By.TAG_NAME, "a")
        except Exception:
            call_links = []
        for link_elem in call_links:
            if len(results) >= max_results:
                break
            try:
                title = link_elem.text.strip()
                link = link_elem.get_attribute("href")
                # The parent container may have open/close dates; search within ancestor
                date_container = link_elem.find_element(By.XPATH, "ancestor::*[contains(@class, 'call') or contains(@class, 'Call')]")
            except Exception:
                continue
            opening_date = ""
            closing_date = ""
            # Try to extract dates from the container
            try:
                # Find text like 'Call opens' and 'Call closes'
                opens_elem = date_container.find_element(By.XPATH, ".//*[contains(text(), 'Call opens') or contains(text(), 'opens')]")
                opening_date = opens_elem.text.split()[-3:]
                opening_date = " ".join(opening_date)
            except Exception:
                opening_date = ""
            try:
                closes_elem = date_container.find_element(By.XPATH, ".//*[contains(text(), 'Call closes') or contains(text(), 'closes')]")
                closing_date = closes_elem.text.split()[-3:]
                closing_date = " ".join(closing_date)
            except Exception:
                closing_date = ""
            # Parse closing date and skip if too soon
            closing_date_obj = None
            if closing_date:
                try:
                    closing_date_obj = datetime.datetime.strptime(closing_date, "%d %b %Y").date()
                except Exception:
                    try:
                        closing_date_obj = datetime.datetime.strptime(closing_date, "%d %B %Y").date()
                    except Exception:
                        closing_date_obj = None
            if closing_date_obj is not None and (closing_date_obj - today).days < 7:
                continue
            # Open details page to extract description
            desc_text = ""
            try:
                detail_driver = create_driver()
                detail_driver.get(link)
                # Accept cookies on detail page if necessary
                try:
                    d_cookie = detail_driver.find_element(By.XPATH, "//button[contains(text(), 'Accept all')]")
                    d_cookie.click()
                except Exception:
                    pass
                detail_soup = BeautifulSoup(detail_driver.page_source, "html.parser")
                paragraphs = detail_soup.find_all("p")
                parts = [p.get_text(" ", strip=True) for p in paragraphs]
                desc_text = "\n".join(parts)
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
            # Keyword filter
            if keyword and keyword not in title.lower() and keyword not in summary.lower():
                continue
            results.append({
                "title": title,
                "link": link,
                "opening_date": opening_date,
                "deadline_date": closing_date,
                "description": summary,
                "ods_list": ods_list if ods_list else ["unknown"],
            })
        return results
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def scrape_anr_calls(theme_filter: str, ods_number: str, keyword: str, max_results: int, today):
    """
    Scrape international calls from the French ANR portal.

    Only the first `max_results` calls are considered.  For each call,
    the opening and closing dates are parsed from the card's header (if
    available).  The summary and ODS classification are extracted from
    the detailed call page when possible.  Calls with deadlines within
    7 days are skipped.  Keyword and ODS filters apply to the title and
    summary.

    Parameters
    ----------
    theme_filter : str
        Not used for ANR calls; provided for consistency.
    ods_number : str
        Selected SDG number to filter by.
    keyword : str
        Lowercase keyword filter.
    max_results : int
        Maximum number of calls to return (capped at 5 by GUI).
    today : datetime.date
        The current date used for deadline checking.

    Returns
    -------
    list[dict]
        List of call dictionaries containing metadata and summary.
    """
    results = []
    url = "https://anr.fr/en/open-calls-and-preannouncements/?tx_solr%5Bfilter%5D%5B0%5D=international%253A1"
    driver = create_driver()
    try:
        driver.get(url)
        # Accept possible pop-up or cookie banner
        try:
            accept_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Accept')]")
            accept_btn.click()
        except Exception:
            pass
        # Wait for call cards to load (they have a date range at top)
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, "//div[contains(@class,'card') and .//h3]"))
            )
        except Exception:
            return results
        cards = driver.find_elements(By.XPATH, "//div[contains(@class,'card') and .//h3]")
        for card in cards:
            if len(results) >= max_results:
                break
            try:
                title_elem = card.find_element(By.TAG_NAME, "h3")
                title = title_elem.text.strip()
                # Extract date range (e.g., '02/07/2025 - 12/03/2026')
                date_range = ""
                try:
                    date_range = card.find_element(By.XPATH, ".//div[contains(@class,'date') or contains(@class,'Date')]").text
                except Exception:
                    pass
                opening_date = ""
                deadline_date = ""
                if date_range and ' - ' in date_range:
                    parts = [p.strip() for p in date_range.split('-')]
                    opening_date_raw = parts[0]
                    closing_date_raw = parts[1]
                    # Convert date strings like '02/07/2025' to '02 July 2025'
                    try:
                        dt_open = datetime.datetime.strptime(opening_date_raw, "%d/%m/%Y")
                        opening_date = dt_open.strftime("%d %B %Y")
                    except Exception:
                        opening_date = opening_date_raw
                    try:
                        dt_close = datetime.datetime.strptime(closing_date_raw, "%d/%m/%Y")
                        deadline_date = dt_close.strftime("%d %B %Y")
                    except Exception:
                        deadline_date = closing_date_raw
                # Skip if deadline within 7 days
                deadline_obj = None
                if deadline_date:
                    try:
                        deadline_obj = datetime.datetime.strptime(deadline_date, "%d %B %Y").date()
                    except Exception:
                        deadline_obj = None
                if deadline_obj is not None and (deadline_obj - today).days < 7:
                    continue
                # Link (arrow icon), we assume the first anchor inside card
                link = ""
                try:
                    link_elem = card.find_element(By.TAG_NAME, "a")
                    link = link_elem.get_attribute("href")
                except Exception:
                    link = ""
                # Fetch description from detail page
                desc_text = ""
                if link:
                    try:
                        detail_driver = create_driver()
                        detail_driver.get(link)
                        detail_soup = BeautifulSoup(detail_driver.page_source, "html.parser")
                        paragraphs = detail_soup.find_all("p")
                        parts = [p.get_text(" ", strip=True) for p in paragraphs]
                        desc_text = "\n".join(parts)
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
                if ods_number and ods_number not in ods_list:
                    continue
                if keyword and keyword not in title.lower() and keyword not in summary.lower():
                    continue
                results.append({
                    "title": title,
                    "link": link,
                    "opening_date": opening_date,
                    "deadline_date": deadline_date,
                    "description": summary,
                    "ods_list": ods_list if ods_list else ["unknown"],
                })
            except Exception:
                continue
        return results
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def scrape_ibro_calls(theme_filter: str, ods_number: str, keyword: str, max_results: int, today):
    """
    Scrape open calls from the IBRO grants page.  Only calls whose
    "Open to" field contains 'International' are retained.  For each
    qualifying call, extract its title, application period (as opening
    and closing dates) and a summary from the detailed page.  Calls with
    deadlines within 7 days are skipped.

    Parameters
    ----------
    theme_filter : str
        Unused for IBRO calls.
    ods_number : str
        Selected SDG number to filter by.
    keyword : str
        Lowercase keyword to filter titles and summaries.
    max_results : int
        Maximum number of calls to return.
    today : datetime.date
        Current date for deadline checking.

    Returns
    -------
    list[dict]
        List of call dictionaries containing metadata and summary.
    """
    results = []
    url = "https://ibro.org/grants/?tab=open-calls"
    driver = create_driver()
    try:
        driver.get(url)
        # Accept any cookies banner that might appear
        try:
            accept_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Accept') or contains(text(), 'Got it')]")
            accept_btn.click()
        except Exception:
            pass
        # Wait for call cards to load (they appear as article or div under 'Open calls')
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[class*='call'] a"))
            )
        except Exception:
            return results
        # Find all anchors within the open calls section
        anchors = driver.find_elements(By.CSS_SELECTOR, "div a")
        # Use a set to avoid duplicates
        seen_links = set()
        for a in anchors:
            if len(results) >= max_results:
                break
            try:
                href = a.get_attribute("href")
                if not href or href in seen_links or not href.startswith("https://ibro.org/grant/"):
                    continue
                seen_links.add(href)
                title = a.text.strip()
                # Open detail page to check 'Open to'
                detail_driver = create_driver()
                detail_driver.get(href)
                # Extract 'Open to:' value and application dates
                page_soup = BeautifulSoup(detail_driver.page_source, "html.parser")
                # Determine open_to value
                open_to = ""
                for dt in page_soup.find_all('div'):
                    text = dt.get_text(" ", strip=True)
                    if 'Open to:' in text:
                        open_to = text.split(':', 1)[-1].strip()
                        break
                if 'international' not in open_to.lower():
                    detail_driver.quit()
                    continue
                # Extract application dates: search for 'Applications:' pattern
                apply_text = ""
                for dt in page_soup.find_all('div'):
                    if 'Applications:' in dt.get_text():
                        apply_text = dt.get_text()
                        break
                opening_date = ""
                closing_date = ""
                if apply_text and ' - ' in apply_text:
                    # Example: 'Applications: 10 Jun 2025 - 15 Oct 2025'
                    parts = apply_text.split(':', 1)[-1].split('-')
                    if len(parts) == 2:
                        opening_date = parts[0].strip()
                        closing_date = parts[1].strip()
                # Parse closing_date for deadline check
                deadline_obj = None
                if closing_date:
                    try:
                        deadline_obj = datetime.datetime.strptime(closing_date, "%d %b %Y").date()
                    except Exception:
                        try:
                            deadline_obj = datetime.datetime.strptime(closing_date, "%d %B %Y").date()
                        except Exception:
                            deadline_obj = None
                if deadline_obj is not None and (deadline_obj - today).days < 7:
                    detail_driver.quit()
                    continue
                # Extract description: get first few paragraphs under the main content area
                paragraphs = page_soup.find_all("p")
                desc_parts = [p.get_text(" ", strip=True) for p in paragraphs]
                desc_text = "\n".join(desc_parts)
                text_for_summary = desc_text if desc_text else title
                summary = summarize_text(text_for_summary)
                ods_list = classify_ods(summary)
                if ods_number and ods_number not in ods_list:
                    detail_driver.quit()
                    continue
                if keyword and keyword not in title.lower() and keyword not in summary.lower():
                    detail_driver.quit()
                    continue
                results.append({
                    "title": title,
                    "link": href,
                    "opening_date": opening_date,
                    "deadline_date": closing_date,
                    "description": summary,
                    "ods_list": ods_list if ods_list else ["unknown"],
                })
                detail_driver.quit()
            except Exception:
                continue
        return results
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def scrape_idrc_calls(theme_filter: str, ods_number: str, keyword: str, max_results: int, today):
    """
    Scrape open calls from the IDRC funding page.  This page is mostly
    static and lists open and closed calls with their deadlines.  We
    consider only the open calls section.  For each call we try to
    retrieve its title, deadline, and description from the detailed
    page (when accessible).  The IDRC site sometimes returns 502 errors
    on detail pages; in that case we summarise only the title.

    Parameters
    ----------
    theme_filter : str
        Unused for IDRC calls.
    ods_number : str
        Selected SDG number to filter by.
    keyword : str
        Lowercase keyword filter.
    max_results : int
        Maximum number of calls to return.
    today : datetime.date
        Current date for deadline checking.

    Returns
    -------
    list[dict]
        List of call dictionaries containing metadata and summary.
    """
    results = []
    url = "https://idrc-crdi.ca/en/funding"
    driver = create_driver()
    try:
        driver.get(url)
        # Accept any cookie banner
        try:
            cookie_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Got it')]")
            cookie_btn.click()
        except Exception:
            pass
        # Use BeautifulSoup on page source to parse static open calls
        soup = BeautifulSoup(driver.page_source, "html.parser")
        open_calls_section = soup.find('h2', string=lambda t: t and 'Open calls' in t)
        if not open_calls_section:
            return results
        # Following siblings (links) until the next heading
        # Collect call links under open calls
        call_links = []
        for sibling in open_calls_section.find_all_next(['a', 'h2']):
            if sibling.name == 'h2':
                break
            if sibling.name == 'a' and sibling.get('href'):
                call_links.append((sibling.text.strip(), sibling['href']))
        for title, href in call_links:
            if len(results) >= max_results:
                break
            # Determine deadline from following text after link
            deadline_text = ""
            link_tag = soup.find('a', href=href)
            if link_tag:
                next_sibling = link_tag.find_next(string=lambda t: isinstance(t, str) and 'Deadline:' in t)
                if next_sibling:
                    # Example: 'Deadline: September 17, 2025'
                    deadline_text = next_sibling.split(':', 1)[-1].strip()
            # Parse deadline and skip if too soon
            deadline_obj = None
            if deadline_text:
                try:
                    deadline_obj = datetime.datetime.strptime(deadline_text, "%B %d, %Y").date()
                except Exception:
                    try:
                        deadline_obj = datetime.datetime.strptime(deadline_text, "%d %B %Y").date()
                    except Exception:
                        deadline_obj = None
            if deadline_obj is not None and (deadline_obj - today).days < 7:
                continue
            # Resolve absolute URL if relative
            full_link = href
            if href.startswith('/'):
                full_link = "https://idrc-crdi.ca" + href
            # Try to fetch description from detail page
            desc_text = ""
            try:
                detail_driver = create_driver()
                detail_driver.get(full_link)
                detail_soup = BeautifulSoup(detail_driver.page_source, "html.parser")
                paragraphs = detail_soup.find_all('p')
                desc_parts = [p.get_text(" ", strip=True) for p in paragraphs]
                desc_text = "\n".join(desc_parts)
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
            if ods_number and ods_number not in ods_list:
                continue
            if keyword and keyword not in title.lower() and keyword not in summary.lower():
                continue
            results.append({
                "title": title,
                "link": full_link,
                "opening_date": "",
                "deadline_date": deadline_text,
                "description": summary,
                "ods_list": ods_list if ods_list else ["unknown"],
            })
        return results
    finally:
        try:
            driver.quit()
        except Exception:
            pass


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

        # Load cached results if they exist and filter out expired ones.  Each
        # cached entry also stores its source site so we can enforce a maximum
        # of 5 results per site when reading from cache and when adding new
        # entries.
        cached_results = []
        source_count = {"EU": 0, "Wellcome": 0, "AKA": 0, "ANR": 0, "IBRO": 0, "IDRC": 0}
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
                        # Determine source site; default to EU if missing
                        site = row.get("site", "EU")
                        # Respect site-specific maximum of 5 results when loading cache
                        if source_count.get(site, 0) >= 5:
                            continue
                        source_count[site] = source_count.get(site, 0) + 1
                        # Append to cached results
                        cached_results.append({
                            "title": row.get("title"),
                            "link": row.get("link"),
                            "opening_date": row.get("opening_date"),
                            "deadline_date": row.get("deadline_date"),
                            "description": row.get("description"),
                            "ods_list": ods_list if ods_list else ["unknown"],
                            "site": site,
                        })
            except Exception:
                pass

        # Add cached results to final_data up to the limit (avoid duplicates) and track titles
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
        # Scrape and aggregate calls from EU and other sources if needed
        # Limit per site
        site_order = ["EU", "Wellcome", "AKA", "ANR", "IBRO", "IDRC"]
        # Define a local helper to append a call to final_data and update counters
        def append_call(item, site_name):
            nonlocal needed
            if needed <= 0:
                return False
            if source_count.get(site_name, 0) >= 5:
                return False
            if item["title"] in seen_titles:
                return False
            final_data.append(item)
            seen_titles.add(item["title"])
            source_count[site_name] = source_count.get(site_name, 0) + 1
            needed -= 1
            cached_results.append(item)
            return True
        # 1) Scrape EU calls if needed
        if needed > 0 and source_count["EU"] < 5:
            page_number = 1
            max_batch = results_limit * 3 if results_limit > 0 else 30
            candidates_to_process = []
            while needed > 0 and source_count["EU"] < 5:
                driver = create_driver()
                try:
                    meta = get_calls_page(driver, selected_theme if has_theme_filter else "", page_number)
                finally:
                    driver.quit()
                if not meta:
                    break
                for item in meta:
                    if needed <= 0 or source_count["EU"] >= 5:
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
                    candidates_to_process.append({
                        "title": title,
                        "link": link,
                        "opening_date": opening_date,
                        "deadline_date": deadline_str,
                    })
                    if len(candidates_to_process) >= max_batch:
                        break
                # Summarise and classify when batch is ready or page ends
                if candidates_to_process and (len(candidates_to_process) >= max_batch or needed <= 0 or source_count["EU"] >= 5):
                    # Fetch descriptions sequentially
                    for cand in candidates_to_process:
                        detail_driver = create_driver()
                        try:
                            desc = fetch_and_extract_description(detail_driver, cand["link"])
                        finally:
                            detail_driver.quit()
                        cand["text_for_summary"] = desc if desc else cand["title"]
                    # Summarise and classify concurrently
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
                            # Apply ODS filter
                            if has_ods_filter and selected_ods_number not in ods_list:
                                continue
                            # Apply keyword filter when combined with theme or ODS
                            if has_keyword_filter and (has_theme_filter or has_ods_filter):
                                if not (keywords in cand["title"].lower() or keywords in summary.lower()):
                                    continue
                            # Create call item
                            call_item = {
                                "title": cand["title"],
                                "link": cand["link"],
                                "opening_date": cand["opening_date"],
                                "deadline_date": cand["deadline_date"],
                                "description": summary,
                                "ods_list": ods_list if ods_list else ["unknown"],
                                "site": "EU",
                            }
                            # Append call respecting limits
                            append_call(call_item, "EU")
                            if needed <= 0 or source_count["EU"] >= 5:
                                break
                    candidates_to_process = []
                page_number += 1
                if not meta:
                    break
        # 2) Scrape other sources sequentially if still needed
        # Helper to scrape other sites
        import datetime as dt_mod
        for site_name, scraper in [("Wellcome", scrape_wellcome_calls), ("AKA", scrape_aka_calls),
                                   ("ANR", scrape_anr_calls), ("IBRO", scrape_ibro_calls),
                                   ("IDRC", scrape_idrc_calls)]:
            if needed <= 0 or source_count.get(site_name, 0) >= 5:
                continue
            # Determine maximum we can fetch from this site
            max_site_results = min(5 - source_count.get(site_name, 0), needed)
            try:
                results = scraper(
                    selected_theme if has_theme_filter else "",
                    selected_ods_number if has_ods_filter else "",
                    keywords,
                    max_site_results,
                    today,
                )
            except Exception:
                results = []
            for r in results:
                if needed <= 0 or source_count.get(site_name, 0) >= 5:
                    break
                # r already contains summary and ods_list
                # Append only if it matches filters
                if has_ods_filter and selected_ods_number not in r.get("ods_list", []):
                    continue
                if has_keyword_filter and (has_theme_filter or has_ods_filter):
                    if not (keywords in r["title"].lower() or keywords in r["description"].lower()):
                        continue
                # Add site name
                r["site"] = site_name
                append_call(r, site_name)
                if needed <= 0:
                    break

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
        fieldnames = ["title", "link", "opening_date", "deadline_date", "description", "ods_classification", "site"]
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
                    "site": item.get("site", "EU"),
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
                # Site
                results_text.insert(tk.END, f"   Fuente: {item.get('site','EU')}\n")
                # Summary
                results_text.insert(tk.END, "   Resumen (es): " + item['description'] + "\n")
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
            "La clasificación ODS se determina localmente utilizando coincidencias de palabras clave "
            "en el resumen de cada convocatoria. Si no se detecta ninguna coincidencia, se marcará como 'unknown'."
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