from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Iterable

NEGATION_WORDS = {"no", "not", "never", "none", "without"}


@dataclass
class CitedClaim:
    claim: str
    source_chunk_ids: list[str]
    is_supported: bool = False
    reasons: list[str] = field(default_factory=list)
    verified_sources: list[dict[str, Any]] = field(default_factory=list)

    def render_sources(self) -> list[dict[str, Any]]:
        return [
            {
                "title": source.get("title"),
                "url": source.get("url"),
                "license": source.get("license"),
                "excerpt": source.get("text", ""),
            }
            for source in self.verified_sources
        ]


class CitationVerifier:
    def __init__(self, source_chunks: Iterable[dict[str, Any]]):
        self.source_chunks = list(source_chunks)
        self.by_id = {str(chunk.get("chunk_id")): chunk for chunk in self.source_chunks if chunk.get("chunk_id")}

    def _tokenize(self, text: str) -> set[str]:
        return {token.lower() for token in re.findall(r"\b[\w-]+\b", (text or "").lower()) if len(token) > 2}

    def _contains_number(self, text: str) -> bool:
        return bool(re.search(r"\d", text or ""))

    def _check_negation(self, claim: str, chunk: dict[str, Any]) -> bool:
        claim_lower = claim.lower()
        chunk_lower = str(chunk.get("text", "")).lower()
        has_negation = any(word in claim_lower for word in NEGATION_WORDS)
        if not has_negation:
            return True
        if any(word in chunk_lower for word in NEGATION_WORDS):
            return True
        return False

    def _coverage_score(self, claim: str, chunk: dict[str, Any]) -> float:
        claim_tokens = self._tokenize(claim)
        chunk_tokens = self._tokenize(chunk.get("text", ""))
        if not claim_tokens or not chunk_tokens:
            return 0.0
        overlap = len(claim_tokens & chunk_tokens)
        if not overlap:
            return 0.0
        return overlap / max(1, len(claim_tokens))

    def verify(self, claim: CitedClaim) -> CitedClaim:
        supported_sources: list[dict[str, Any]] = []
        reasons: list[str] = []
        if not claim.source_chunk_ids:
            claim.is_supported = False
            claim.reasons = ["No supporting chunk IDs were provided."]
            claim.verified_sources = []
            return claim

        for chunk_id in claim.source_chunk_ids:
            chunk = self.by_id.get(str(chunk_id))
            if not chunk:
                reasons.append(f"Missing supporting chunk: {chunk_id}")
                continue
            score = self._coverage_score(claim.claim, chunk)
            number_ok = True
            if self._contains_number(claim.claim):
                number_ok = self._contains_number(str(chunk.get("text", "")))
            neg_ok = self._check_negation(claim.claim, chunk)
            if score >= 0.35 and number_ok and neg_ok:
                supported_sources.append(chunk)
        claim.is_supported = bool(supported_sources)
        claim.reasons = reasons or (["Claim is substantively supported by the cited chunk(s)."] if claim.is_supported else ["Claim is not supported by the provided sources."])
        claim.verified_sources = supported_sources
        return claim
