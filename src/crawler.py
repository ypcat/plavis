"""Fetch the MND PLA activity bulletin list and detail pages. Stdlib + requests + bs4 only."""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterator

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

BASE = "https://www.mnd.gov.tw"
LIST_URL = BASE + "/news/plaactlist/{page}"
DETAIL_URL = BASE + "/news/plaact/{id}"

# Full desktop-Chrome-looking header set; the MND WAF 403s minimal clients.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Cache-Control": "max-age=0",
    "Connection": "keep-alive",
}

DEBUG_DUMP_DIR: "os.PathLike | None" = None
_PARSER = "html.parser"

_DATE_RE = re.compile(r"(\d{3,4})[/.\-年](\d{1,2})[/.\-月](\d{1,2})")
_ROC_THRESHOLD = 200  # years <= this are ROC民國; add 1911 to convert


@dataclass
class ListEntry:
    id: int
    url: str
    date: date | None
    title: str


@dataclass
class Detail:
    id: int
    url: str
    date: date | None
    title: str
    body_text: str


def new_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def _get(url: str, session: requests.Session, attempts: int = 4) -> tuple[str, int, str]:
    """GET with exponential-backoff retry. Returns ``(body, status, content_type)``."""
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            resp = session.get(url, headers=HEADERS, timeout=30)
            ct = resp.headers.get("content-type", "")
            log.debug("GET %s -> %s (%d bytes, %s)", url, resp.status_code, len(resp.content), ct)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text, resp.status_code, ct
        except Exception as e:
            last_exc = e
            if i == attempts - 1:
                break
            wait = 2 ** (i + 1)
            log.warning("GET %s failed (%s); retry %d/%d in %ds", url, e, i + 1, attempts - 1, wait)
            time.sleep(wait)
    assert last_exc is not None
    raise last_exc


def _dump(name: str, text: str) -> None:
    if DEBUG_DUMP_DIR is None:
        return
    d = Path(DEBUG_DUMP_DIR)
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(text, encoding="utf-8")
    log.info("  dumped %d bytes to %s", len(text), d / name)


def _parse_date(text: str) -> date | None:
    m = _DATE_RE.search(text)
    if not m:
        return None
    y, mo, d = (int(x) for x in m.groups())
    if y <= _ROC_THRESHOLD:
        y += 1911
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def list_entries(page: int, session: requests.Session) -> list[ListEntry]:
    """Return entries on one list page. Empty list if the page is past the end."""
    url = LIST_URL.format(page=page)
    html, status, ct = _get(url, session)
    log.info("list page %d: HTTP %d, %d bytes, ct=%s", page, status, len(html), ct)
    soup = BeautifulSoup(html, _PARSER)
    total_anchors = len(soup.find_all("a"))
    anchors = soup.select("a[href*='news/plaact/']")
    out: list[ListEntry] = []
    seen: set[int] = set()
    for a in anchors:
        href = a.get("href", "")
        m = re.search(r"news/plaact/(\d+)", href)
        if not m:
            continue
        nid = int(m.group(1))
        if nid in seen:
            continue
        seen.add(nid)
        title = a.get_text(" ", strip=True)
        container = a
        for _ in range(4):
            if container and _DATE_RE.search(container.get_text(" ", strip=True) or ""):
                break
            container = container.parent if container else None
        dt = _parse_date((container or a).get_text(" ", strip=True)) or _parse_date(title)
        out.append(ListEntry(id=nid, url=BASE + f"/news/plaact/{nid}", date=dt, title=title))
    log.info(
        "  page %d: %d plaact links (of %d total anchors); %d unique entries",
        page, len(anchors), total_anchors, len(out),
    )
    if not out:
        _dump(f"list_page_{page}.html", html)
        preview = soup.get_text("\n", strip=True)[:500]
        log.warning("  page %d empty. first 500 chars of visible text:\n%s", page, preview)
    return out


def iter_entries(
    session: requests.Session,
    stop_ids: set[int] | None = None,
    earliest: date | None = None,
    max_pages: int = 500,
    grace_pages: int = 3,
) -> Iterator[ListEntry]:
    """Walk pages 1..N, yielding unseen entries until we exhaust them or
    hit ``grace_pages`` consecutive pages with no new IDs."""
    stop_ids = stop_ids or set()
    no_new_streak = 0
    for page in range(1, max_pages + 1):
        try:
            entries = list_entries(page, session)
        except requests.HTTPError as e:
            log.warning("list page %d failed: %s", page, e)
            break
        if not entries:
            break
        new_on_page = 0
        older_than_floor = True
        for e in entries:
            if e.date and earliest and e.date >= earliest:
                older_than_floor = False
            if e.id in stop_ids:
                continue
            if e.date and earliest and e.date < earliest:
                continue
            new_on_page += 1
            yield e
        if new_on_page == 0:
            no_new_streak += 1
            if no_new_streak >= grace_pages:
                log.info("no new entries for %d pages; stopping", grace_pages)
                return
        else:
            no_new_streak = 0
        if older_than_floor:
            log.info("all entries on page %d older than floor; stopping", page)
            return
        time.sleep(1.0)


def fetch_detail(entry_id: int, session: requests.Session) -> Detail:
    url = DETAIL_URL.format(id=entry_id)
    html, status, ct = _get(url, session)
    log.debug("detail %s: HTTP %d, %d bytes", entry_id, status, len(html))
    soup = BeautifulSoup(html, _PARSER)

    title_el = soup.find(["h1", "h2", "h3"])
    title = title_el.get_text(" ", strip=True) if title_el else ""

    article = (
        soup.find("article")
        or soup.find("div", class_=re.compile(r"(content|article|news)"))
        or soup.body
    )
    body_text = article.get_text("\n", strip=True) if article else ""

    dt = _parse_date(title) or _parse_date(body_text[:200])
    return Detail(id=entry_id, url=url, date=dt, title=title, body_text=body_text)
