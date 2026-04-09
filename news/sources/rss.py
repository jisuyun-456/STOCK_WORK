"""Generic RSS/Atom feed parser using xml.etree.ElementTree (stdlib)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

# Common Atom namespace
_ATOM_NS = "http://www.w3.org/2005/Atom"


def parse_rss_feed(url: str, timeout: int = 10) -> list[dict]:
    """Parse an RSS or Atom feed and return article metadata.

    Returns:
        [{"title": str, "url": str, "published": str, "description": str}, ...]
        Empty list on any error.
    """
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=timeout)
        resp.raise_for_status()
    except Exception:
        return []

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError:
        return []

    articles: list[dict] = []

    # Try RSS 2.0 format (<channel><item>)
    items = root.findall(".//item")
    if items:
        for item in items:
            articles.append(_parse_rss_item(item))
        return articles

    # Try Atom format (<entry>)
    entries = root.findall(f".//{{{_ATOM_NS}}}entry")
    if not entries:
        entries = root.findall(".//entry")
    for entry in entries:
        articles.append(_parse_atom_entry(entry))

    return articles


def _parse_rss_item(item: ET.Element) -> dict:
    """Parse a single RSS <item> element."""
    title = _text(item, "title")
    link = _text(item, "link")
    pub_date = _text(item, "pubDate")
    description = _text(item, "description")

    published = _parse_date(pub_date) if pub_date else ""

    return {
        "title": title,
        "url": link,
        "published": published,
        "description": _strip_html(description),
    }


def _parse_atom_entry(entry: ET.Element) -> dict:
    """Parse a single Atom <entry> element."""
    title = _text_ns(entry, "title")
    link_el = entry.find(f"{{{_ATOM_NS}}}link")
    if link_el is None:
        link_el = entry.find("link")
    link = link_el.get("href", "") if link_el is not None else ""

    published = _text_ns(entry, "published") or _text_ns(entry, "updated")
    summary = _text_ns(entry, "summary") or _text_ns(entry, "content")

    return {
        "title": title,
        "url": link,
        "published": published,
        "description": _strip_html(summary),
    }


def _text(el: ET.Element, tag: str) -> str:
    """Get text content of a child element."""
    child = el.find(tag)
    return (child.text or "").strip() if child is not None else ""


def _text_ns(el: ET.Element, tag: str) -> str:
    """Get text content with Atom namespace fallback."""
    child = el.find(f"{{{_ATOM_NS}}}{tag}")
    if child is None:
        child = el.find(tag)
    return (child.text or "").strip() if child is not None else ""


def _strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    if not text:
        return ""
    import re
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:1000]  # cap description length


def _parse_date(date_str: str) -> str:
    """Parse RFC 2822 date to ISO format. Returns raw string on failure."""
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.isoformat()
    except Exception:
        return date_str
