"""
http_utils.py
-------------

HTTP utility functions used by scrapers that do not rely on Selenium.
This module provides simple wrappers around the ``requests`` library
and BeautifulSoup for fetching and parsing web pages.  A default
``User-Agent`` header is included on each request to minimise the
likelihood of a 403 (Forbidden) response from sites that expect
browser‑like clients.

Functions
~~~~~~~~~
fetch_page(url, timeout=30) -> str
    Retrieve the contents of a URL as a Unicode string.

parse_html(html) -> BeautifulSoup
    Parse an HTML document into a BeautifulSoup object using the
    'html.parser' backend.
"""

from __future__ import annotations

import requests
from bs4 import BeautifulSoup


def fetch_page(url: str, *, timeout: int = 30) -> str:
    """Fetch the contents of a URL and return it as text.

    A default ``User-Agent`` header is supplied to appear as a
    mainstream browser.  The function raises ``HTTPError`` when
    the response status indicates an error.

    Parameters
    ----------
    url: str
        The URL to retrieve.
    timeout: int, optional
        Seconds to wait for a response before aborting.

    Returns
    -------
    str
        The response body as text.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/115.0 Safari/537.36"
        )
    }
    response = requests.get(url, timeout=timeout, headers=headers)
    response.raise_for_status()
    return response.text


def parse_html(html: str) -> BeautifulSoup:
    """Parse an HTML document into a BeautifulSoup object.

    Parameters
    ----------
    html: str
        The raw HTML string to parse.

    Returns
    -------
    bs4.BeautifulSoup
        A parsed representation of the HTML document.
    """
    return BeautifulSoup(html, "html.parser")


__all__ = ["fetch_page", "parse_html"]