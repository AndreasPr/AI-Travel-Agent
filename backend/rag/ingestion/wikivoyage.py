from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from backend.rag.config import get_wikivoyage_user_agent, project_root, read_cities

REQUEST_INTERVAL_SECONDS = 1.0
CACHE_DIR = project_root() / "data" / "raw"


def _cache_path(city: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", city.lower()).strip("-") or "city"
    return CACHE_DIR / f"{slug}.json"


def _request_json(url: str) -> dict[str, Any]:
    response = requests.get(url, headers={"User-Agent": get_wikivoyage_user_agent()}, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_wikivoyage_page(city: str) -> dict[str, Any]:
    cache_path = _cache_path(city)
    if cache_path.exists():
        with cache_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    encoded = quote(city)
    api_url = (
        "https://en.wikivoyage.org/w/api.php"
        f"?action=query&prop=info|extracts&inprop=url&titles={encoded}&explaintext=1&redirects=1&format=json&formatversion=2"
    )
    time.sleep(REQUEST_INTERVAL_SECONDS)
    payload = _request_json(api_url)
    page = (payload.get("query", {}).get("pages") or [{}])[0]
    title = page.get("title") or city
    extracted_text = page.get("extract") or ""
    page_url = page.get("fullurl") or f"https://en.wikivoyage.org/wiki/{quote(title.replace(' ', '_'))}"
    revision_id = page.get("lastrevid") or page.get("pageid")
    retrieved_at = datetime.now(timezone.utc).isoformat()
    metadata = {
        "title": title,
        "city": city,
        "url": page_url,
        "revision_id": revision_id,
        "retrieved_at": retrieved_at,
        "license": "CC BY-SA 4.0",
        "license_attribution": "Content from Wikivoyage is licensed under CC BY-SA 4.0.",
        "text": extracted_text,
    }
    with cache_path.open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, ensure_ascii=False, indent=2)
    return metadata


def fetch_city_pages(cities: list[str] | None = None) -> list[dict[str, Any]]:
    selected = cities or read_cities()
    result: list[dict[str, Any]] = []
    for city in selected:
        page = fetch_wikivoyage_page(city)
        if page.get("text"):
            result.append(page)
    return result


def main() -> None:
    cities = read_cities()
    pages = fetch_city_pages(cities)
    print(json.dumps({"cities": len(cities), "downloaded": len(pages)}, indent=2))


if __name__ == "__main__":
    main()
