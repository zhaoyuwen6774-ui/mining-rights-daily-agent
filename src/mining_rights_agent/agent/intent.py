from __future__ import annotations

import re

from mining_rights_agent.common.models import BriefIntent, Commodity

PROJECT_ALIASES: dict[str, tuple[str, str, Commodity]] = {
    "pilbara": ("Pilbara", "Pilbara Minerals", "lithium"),
    "皮尔巴拉": ("Pilbara", "Pilbara Minerals", "lithium"),
    "newmont": ("Newmont", "Newmont", "gold"),
    "纽蒙特": ("Newmont", "Newmont", "gold"),
    "barrick": ("Barrick", "Barrick Gold", "gold"),
    "巴里克": ("Barrick", "Barrick Gold", "gold"),
}

COMMODITY_ALIASES: dict[str, Commodity] = {
    "copper": "copper",
    "铜": "copper",
    "zinc": "zinc",
    "锌": "zinc",
    "nickel": "nickel",
    "镍": "nickel",
    "lithium": "lithium",
    "锂": "lithium",
    "iron ore": "iron_ore",
    "铁矿石": "iron_ore",
}


def parse_intent(request: str) -> BriefIntent:
    lowered = request.casefold()
    project = request.strip()
    company: str | None = None
    commodity: Commodity = "unknown"

    for alias, (known_project, known_company, known_commodity) in PROJECT_ALIASES.items():
        if alias in lowered:
            project = known_project
            company = known_company
            commodity = known_commodity
            break
    for alias, known_commodity in COMMODITY_ALIASES.items():
        if alias in lowered:
            commodity = known_commodity
            break

    days_match = re.search(r"(?:近\s*)?(\d{1,2})\s*(?:天|日|days?)", lowered)
    days = int(days_match.group(1)) if days_match else 7
    return BriefIntent(
        project=project,
        company=company,
        commodity=commodity,
        days=min(max(days, 1), 90),
    )
