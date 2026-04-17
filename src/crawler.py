"""Fetch the MND PLA activity bulletin list and detail pages."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import date
from typing import Iterator

import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

log = logging.getLogger(__name__)

BASE = "https://www.mnd.gov.tw"
LIST_URL = BASE + "/news/plaactlist/{page}"
DETAIL_URL = BASE + "/news/plaact/{id}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_DATE_RE = re.compile(r"(\d{4})[/.\-年](\d{1,2})[/.\-月](\d{1,2})")


@dataclass
class ListEntry:
    id: int
    url: str
    date: date | None
    title: str


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, min=2, max=16))
def _get(url: str, session: requests.Session) -> str:
    resp = session.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


def _parse_date(text: str) -> date | None:
    m = _DATE_RE.search(text)
    if not m:
        return None
    y, mo, d = (int(x) for x in m.groups())
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def list_entries(page: int, session: requests.Session) -> list[ListEntry]:
    """Return entries on one list page. Empty list if page is beyond end."""
    html = _get(LIST_URL.format(page=page), session)
    soup = BeautifulSoup(html, "lxml")
    out: list[ListEntry] = []
    seen: set[int] = set()
    for a in soup.select("a[href*='/news/plaact/']"):
        href = a.get("href", "")
        m = re.search(r"/news/plaact/(\d+)", href)
        if not m:
            continue
        nid = int(m.group(1))
        if nid in seen:
            continue
        seen.add(nid)
        title = a.get_text(" ", strip=True)
        # date sometimes lives in a sibling, sometimes in the card parent
        container = a
        for _ in range(4):
            if container and _DATE_RE.search(container.get_text(" ", strip=True) or ""):
                break
            container = container.parent if container else None
        dt = _parse_date((container or a).get_text(" ", strip=True)) or _parse_date(title)
        out.append(
            ListEntry(
                id=nid,
                url=BASE + f"/news/plaact/{nid}",
                date=dt,
                title=title,
            )
        )
    return out


def iter_entries(
    session: requests.Session,
    stop_ids: set[int] | None = None,
    earliest: date | None = None,
    max_pages: int = 500,
    grace_pages: int = 3,
) -> Iterator[ListEntry]:
    """Walk pages 1..N, yielding entries. Stops once we've seen enough
    already-known entries (``grace_pages`` consecutive pages with no new IDs),
    or once every entry on a page is older than ``earliest``."""
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


@dataclass
class Detail:
    id: int
    url: str
    date: date | None
    title: str
    body_text: str
    image_urls: list[str]


def fetch_detail(entry_id: int, session: requests.Session) -> Detail:
    url = DETAIL_URL.format(id=entry_id)
    html = _get(url, session)
    soup = BeautifulSoup(html, "lxml")

    title_el = soup.find(["h1", "h2", "h3"])
    title = title_el.get_text(" ", strip=True) if title_el else ""

    # body lives in an article/section; fall back to whole page text
    article = (
        soup.find("article")
        or soup.find("div", class_=re.compile(r"(content|article|news)"))
        or soup.body
    )
    body_text = article.get_text("\n", strip=True) if article else ""

    img_urls: list[str] = []
    for img in (article.find_all("img") if article else []):
        src = img.get("src") or img.get("data-src") or ""
        if not src:
            continue
        if src.startswith("/"):
            src = BASE + src
        if not src.startswith("http"):
            continue
        img_urls.append(src)

    dt = _parse_date(title) or _parse_date(body_text[:200])
    return Detail(
        id=entry_id,
        url=url,
        date=dt,
        title=title,
        body_text=body_text,
        image_urls=img_urls,
    )


def download_image(url: str, session: requests.Session) -> bytes:
    @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, min=2, max=16))
    def _fetch() -> bytes:
        resp = session.get(url, headers=HEADERS, timeout=60)
        resp.raise_for_status()
        return resp.content

    return _fetch()


def new_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s
