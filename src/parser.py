"""Extract daily totals from the MND bulletin body text.

The body appears in Chinese and sometimes English. Both variants share a
rough shape:

    自今(16)日上午6時起,截至今日上午6時止,偵獲共機27架次、共艦7艘……
    其中22架次逾越海峽中線及進入我北部、中部、西南部空域,詳如附圖。

or the English equivalent on /en/news/plaact/.

We extract what we can and leave missing fields as ``None`` (which becomes an
empty cell in the CSV) rather than inventing zeros.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Totals:
    total_aircraft: int | None = None
    median_crossings: int | None = None
    sw_adiz: int | None = None
    n_adiz: int | None = None
    e_adiz: int | None = None
    se_adiz: int | None = None
    plan_vessels: int | None = None
    official_ships: int | None = None
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, int | None]:
        d = {
            "total_aircraft": self.total_aircraft,
            "median_crossings": self.median_crossings,
            "sw_adiz": self.sw_adiz,
            "n_adiz": self.n_adiz,
            "e_adiz": self.e_adiz,
            "se_adiz": self.se_adiz,
            "plan_vessels": self.plan_vessels,
            "official_ships": self.official_ships,
        }
        return d


def _int(m: re.Match | None, group: int = 1) -> int | None:
    if not m:
        return None
    try:
        return int(m.group(group))
    except (ValueError, IndexError):
        return None


# --- Chinese patterns ---
_ZH_TOTAL_AC = re.compile(r"偵獲[^。\n]*?共機\s*(\d+)\s*架次")
_ZH_TOTAL_AC_ALT = re.compile(r"共機\s*(\d+)\s*架次")
_ZH_PLAN = re.compile(r"共艦\s*(\d+)\s*艘")
_ZH_OFFICIAL = re.compile(r"公務船\s*(\d+)\s*艘")
# Require the number to sit directly in front of 逾越/越過/跨越 (<=4 chars
# of whitespace/punctuation between) so we don't pick up the overall total
# from the leading clause.
_ZH_MEDIAN = re.compile(r"(\d+)\s*架次[\s、,，]{0,4}(?:逾越|越過|跨越)[^。\n]{0,12}(?:海峽)?中線")
# ADIZ quadrants (Chinese uses 北部/中部/西南部/東部/東南部 空域).
# MND always writes ``<quadrant> <N>架次`` and lists the quadrants with no
# number only in the post-2024 simplified summary. Require the quadrant name
# to directly precede the number within ~8 chars; otherwise leave ``None``.
_ZH_SW = re.compile(r"西南(?:部)?(?:空域)?\s*(\d+)\s*架次")
_ZH_N = re.compile(r"(?<![東西南])北(?:部)?(?:空域)?\s*(\d+)\s*架次")
_ZH_E = re.compile(r"(?<![南北西])東(?:部)?(?:空域)?\s*(\d+)\s*架次")
_ZH_SE = re.compile(r"東南(?:部)?(?:空域)?\s*(\d+)\s*架次")

# --- English patterns ---
_EN_TOTAL_AC = re.compile(r"(\d+)\s+(?:sorties of\s+)?PLA\s+aircraft", re.I)
_EN_PLAN = re.compile(r"(\d+)\s+PLAN\s+(?:vessels|ships)", re.I)
_EN_OFFICIAL = re.compile(r"(\d+)\s+(?:official|China\s+Coast\s+Guard)\s+(?:vessels|ships)", re.I)
_EN_MEDIAN = re.compile(r"(\d+)[^.\n]*?(?:crossed|crossing)[^.\n]*?median line", re.I)
_EN_SW = re.compile(r"(\d+)[^.\n]*?south[- ]?west(?:ern)?\s+(?:and|&|or|,|ADIZ)", re.I)
_EN_N = re.compile(r"(\d+)[^.\n]*?\bnorth(?:ern)?\s+(?:and|&|or|,|ADIZ)", re.I)
_EN_E = re.compile(r"(\d+)[^.\n]*?\beast(?:ern)?\s+(?:and|&|or|,|ADIZ)", re.I)
_EN_SE = re.compile(r"(\d+)[^.\n]*?south[- ]?east(?:ern)?\s+(?:and|&|or|,|ADIZ)", re.I)


def _first_group(m: re.Match | None) -> int | None:
    if not m:
        return None
    for g in m.groups():
        if g is not None:
            try:
                return int(g)
            except ValueError:
                continue
    return None


def parse_body(text: str) -> Totals:
    """Extract totals from the bulletin body text. Best-effort; missing fields
    stay ``None``."""
    if not text:
        return Totals()
    t = Totals()

    # Aircraft total (Chinese preferred, English fallback)
    t.total_aircraft = _int(_ZH_TOTAL_AC.search(text)) or _int(_ZH_TOTAL_AC_ALT.search(text))
    if t.total_aircraft is None:
        t.total_aircraft = _int(_EN_TOTAL_AC.search(text))

    t.plan_vessels = _int(_ZH_PLAN.search(text)) or _int(_EN_PLAN.search(text))
    t.official_ships = _int(_ZH_OFFICIAL.search(text)) or _int(_EN_OFFICIAL.search(text))

    t.median_crossings = _int(_ZH_MEDIAN.search(text)) or _int(_EN_MEDIAN.search(text))

    t.sw_adiz = _int(_ZH_SW.search(text)) or _int(_EN_SW.search(text))
    t.n_adiz = _int(_ZH_N.search(text)) or _int(_EN_N.search(text))
    t.e_adiz = _int(_ZH_E.search(text)) or _int(_EN_E.search(text))
    t.se_adiz = _int(_ZH_SE.search(text)) or _int(_EN_SE.search(text))

    return t
