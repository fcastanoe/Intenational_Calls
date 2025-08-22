#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
utils.py
--------

This module provides utility functions for configuring Selenium WebDriver
instances and handling common actions like accepting cookie banners.  All
scrapers import these functions so that browser configuration remains
consistent across the project.

Functions
~~~~~~~~~
create_driver() -> selenium.webdriver.Chrome
    Create and return a headless Chrome WebDriver configured with
    sensible defaults for scraping.

accept_cookies(driver) -> None
    Attempt to click the standard OneTrust cookie banner if present.

"""

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def create_driver() -> webdriver.Chrome:
    """Create a new headless Chrome WebDriver.

    The returned driver is configured to run headless, disable GPU
    acceleration, avoid using the Chrome sandbox, and attempt to mask
    automation signals.  These options help ensure stability when
    scraping sites that might detect automated browsers.

    Returns
    -------
    selenium.webdriver.Chrome
        A configured headless Chrome driver instance.
    """
    chrome_opts = Options()
    chrome_opts.add_argument("--headless")
    chrome_opts.add_argument("--disable-gpu")
    chrome_opts.add_argument("--no-sandbox")
    chrome_opts.add_argument("--disable-blink-features=AutomationControlled")
    driver = webdriver.Chrome(options=chrome_opts)
    return driver


def accept_cookies(driver: webdriver.Chrome) -> None:
    """Click the OneTrust cookie acceptance button if it is present.

    Many websites present a cookie banner on first load.  This helper
    waits up to five seconds for the standard OneTrust accept button
    (id='onetrust-accept-btn-handler') to become clickable and clicks
    it.  If the element is not found within the timeout, the function
    simply returns without error.

    Parameters
    ----------
    driver : selenium.webdriver.Chrome
        The WebDriver instance to operate on.
    """
    try:
        btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
        )
        btn.click()
    except Exception:
        pass


__all__ = ["create_driver", "accept_cookies"]