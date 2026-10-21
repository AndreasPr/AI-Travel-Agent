from __future__ import annotations

import hashlib
import re
from typing import Any

TOPIC_KEYWORDS = {
    "see": ["museum", "historic", "landmark", "view", "sight", "monument", "architecture"],
    "do": ["activity", "hike", "walk", "bike", "festival", "experience", "tour"],
    "eat": ["food", "restaurant", "cuisine", "eat", "baker", "coffee", "market", "dinner"],
    "drink": ["bar", "beer", "wine", "coffee", "cafe", "cocktail", "pub"],
    "sleep": ["hotel", "hostel", "guesthouse", "sleep", "stay", "accommodation"],
    "get in": ["arrive", "airport", "train", "bus", "flight", "ferry", "transfer"],
    "get around": ["tram", "metro", "taxi", "ride", "walk", "transport"],
    "understand": ["history", "culture", "language", "museum", "guide", "learn"],
    "stay safe": ["safe", "risk", "warning", "police", "scam", "health", "safety"],
    "buy": ["shop", "market", "buy", "book", "tickets", "buying"],
    "connect": ["wifi", "internet", "phone", "connect", "sim", "network"],
}

SECTION_TOPIC_MAP = {
    "see": "see",
    "do": "do",
    "eat": "eat",
    "drink": "drink",
    "sleep": "sleep",
    "get in": "get in",
    "get around": "get around",
    "understand": "understand",
    "stay safe": "stay safe",
    "buy": "buy",
    "connect": "connect",
}


def _clean_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def _infer_season(text: str) -> str | None:
    lowered = text.lower()
    if "winter" in lowered:
        return "winter"
    if "summer" in lowered:
        return "summer"
    if "autumn" in lowered or "fall" in lowered:
        return "autumn"
    if "spring" in lowered:
        return "spring"
    return None


def _sectionize(text: str) -> list[tuple[str, str]]:
    if not text or not text.strip():
        return [("other", "")]

    sections: list[tuple[str, str]] = []
    current_heading = "overview"
    current_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        match = re.match(r"^=+\s*(.+?)\s*=+\s*$", line)
        if match:
            if current_lines or current_heading:
                sections.append((current_heading, "\n".join(current_lines).strip()))
            current_heading = match.group(1).strip() or "overview"
            current_lines = []
            continue
        current_lines.append(line)
    if current_lines or current_heading:
        sections.append((current_heading, "\n".join(current_lines).strip()))
    if not sections:
        return [("other", text.strip())]
    return sections


def _canonical_topic_from_heading(heading: str) -> str | None:
    normalized = re.sub(r"[^a-z]+", " ", (heading or "").lower()).strip()
    return SECTION_TOPIC_MAP.get(normalized)


def _infer_topic(text: str, heading: str) -> str:
    topic = _canonical_topic_from_heading(heading)
    if topic:
        return topic
    haystack = f"{heading} {text}".lower()
    for candidate, keywords in TOPIC_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            return candidate
    return "other"


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\S+", text)


def _chunk_tokens(tokens: list[str], chunk_size: int = 260, overlap: int = 40) -> list[list[str]]:
    if not tokens:
        return []
    chunks: list[list[str]] = []
    start = 0
    while start < len(tokens):
        end = min(len(tokens), start + chunk_size)
        chunks.append(tokens[start:end])
        if end >= len(tokens):
            break
        start += max(1, chunk_size - overlap)
    return chunks


def _slice_text_by_tokens(text: str, start_token_index: int, end_token_index: int, token_spans: list[tuple[int, int]]) -> str:
    if not token_spans:
        return text.strip()
    if start_token_index < 0:
        start_token_index = 0
    if end_token_index > len(token_spans):
        end_token_index = len(token_spans)
    start_pos = token_spans[start_token_index][0]
    end_pos = token_spans[end_token_index - 1][1]
    return text[start_pos:end_pos].strip()


def chunk_document(
    title: str,
    city: str,
    country: str,
    text: str,
    source_url: str,
    license: str,
    season: str | None = None,
    chunk_size: int = 260,
    overlap: int = 40,
) -> list[dict[str, Any]]:
    sections = _sectionize(text)
    chunks: list[dict[str, Any]] = []
    for heading, section_text in sections:
        section_text = section_text.strip()
        if not section_text:
            continue
        tokens = _tokenize(section_text)
        token_spans = [(m.start(), m.end()) for m in re.finditer(r"\S+", section_text)]
        if not tokens:
            continue
        token_groups = _chunk_tokens(tokens, chunk_size=chunk_size, overlap=overlap)
        for chunk_index, token_group in enumerate(token_groups):
            start_token_index = 0
            running = 0
            for idx, group in enumerate(token_groups):
                if idx == chunk_index:
                    break
                running += len(group)
            start_token_index = running
            end_token_index = start_token_index + len(token_group)
            chunk_text = _slice_text_by_tokens(section_text, start_token_index, end_token_index, token_spans)
            if not chunk_text:
                chunk_text = " ".join(token_group)
            chunk_id = hashlib.sha256(
                f"{title}:{city}:{country}:{heading}:{chunk_index}:{chunk_text}".encode("utf-8")
            ).hexdigest()[:16]
            inferred_season = season or _infer_season(chunk_text)
            chunk = {
                "chunk_id": chunk_id,
                "title": title,
                "city": city,
                "country": country,
                "season": inferred_season,
                "topic": _infer_topic(chunk_text, heading),
                "text": chunk_text,
                "source_url": source_url,
                "license": license,
                "chunk_index": chunk_index,
                "heading": heading,
            }
            chunks.append(chunk)
    if not chunks:
        chunk_text = text.strip()
        chunk_id = hashlib.sha256(f"{title}:{city}:{country}:{chunk_text}".encode("utf-8")).hexdigest()[:16]
        chunks.append(
            {
                "chunk_id": chunk_id,
                "title": title,
                "city": city,
                "country": country,
                "season": season or _infer_season(text),
                "topic": "other",
                "text": chunk_text,
                "source_url": source_url,
                "license": license,
                "chunk_index": 0,
                "heading": "overview",
            }
        )
    return chunks
