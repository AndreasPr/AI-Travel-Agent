from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Iterable


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

    def _coverage_score(self, claim: str, chunk: dict[str, Any]) -> float:
        claim_tokens = self._tokenize(claim)
        chunk_tokens = self._tokenize(chunk.get("text", ""))
        if not claim_tokens or not chunk_tokens:
            return 0.0
        overlap = len(claim_tokens & chunk_tokens)
        if overlap >= 2:
            return 1.0
        return overlap / max(1, len(claim_tokens))

    def verify(self, claim: CitedClaim) -> CitedClaim:
        supported_sources: list[dict[str, Any]] = []
        reasons: list[str] = []
        for chunk_id in claim.source_chunk_ids:
            chunk = self.by_id.get(str(chunk_id))
            if not chunk:
                reasons.append(f"Missing supporting chunk: {chunk_id}")
                continue
            score = self._coverage_score(claim.claim, chunk)
            if score >= 0.5:
                supported_sources.append(chunk)
        claim.is_supported = bool(supported_sources)
        claim.reasons = reasons or (["Claim is substantively supported by the cited chunk(s)."] if claim.is_supported else ["Claim is not supported by the provided sources."])
        claim.verified_sources = supported_sources
        return claim
