from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Iterable, Protocol

NEGATION_WORDS = {"no", "not", "never", "none", "without", "cannot", "can't", "isn't", "isnt", "aren't", "arent", "doesn't", "doesnt", "don't", "dont", "wasn't", "wasnt", "weren't", "werent"}


class NLIInterface(Protocol):
    def check(self, claim: str, sentence: str) -> bool:
        ...


class FakeNLI:
    def __init__(self, result: bool = True):
        self.result = result

    def check(self, claim: str, sentence: str) -> bool:
        return self.result


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
    def __init__(self, source_chunks: Iterable[dict[str, Any]], nli_checker: NLIInterface | None = None):
        self.source_chunks = list(source_chunks)
        self.by_id = {str(chunk.get("chunk_id")): chunk for chunk in self.source_chunks if chunk.get("chunk_id")}
        self.nli_checker = nli_checker

    def _tokenize(self, text: str) -> set[str]:
        return {token.lower() for token in re.findall(r"\b[\w-]+\b", (text or "").lower()) if len(token) > 2}

    def _split_sentences(self, text: str) -> list[str]:
        if not text:
            return []
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        return [sentence.strip() for sentence in sentences if sentence.strip()]

    def _contains_number(self, text: str) -> bool:
        return bool(re.search(r"\d", text or ""))

    def _claim_numbers(self, text: str) -> list[str]:
        return re.findall(r"\d+(?:\.\d+)?", text or "")

    def _check_negation(self, claim: str, sentence: str) -> bool:
        claim_lower = claim.lower()
        sentence_lower = sentence.lower()
        has_negation = any(word in claim_lower for word in NEGATION_WORDS)
        if not has_negation:
            return True
        return any(word in sentence_lower for word in NEGATION_WORDS)

    def _best_sentence(self, claim: str, chunk: dict[str, Any]) -> tuple[str, float]:
        sentences = self._split_sentences(str(chunk.get("text", "")))
        if not sentences:
            return "", 0.0
        best_sentence = ""
        best_score = 0.0
        for sentence in sentences:
            claim_tokens = self._tokenize(claim)
            sentence_tokens = self._tokenize(sentence)
            if not claim_tokens:
                score = 0.0
            else:
                overlap = len(claim_tokens & sentence_tokens)
                score = overlap / max(1, len(claim_tokens))
            if score > best_score:
                best_score = score
                best_sentence = sentence
        return best_sentence, best_score

    def _numbers_in_sentence(self, claim: str, sentence: str) -> bool:
        claim_numbers = self._claim_numbers(claim)
        if not claim_numbers:
            return True
        for number in claim_numbers:
            if number not in re.findall(r"\d+(?:\.\d+)?", sentence):
                return False
        return True

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
            sentence, score = self._best_sentence(claim.claim, chunk)
            if not sentence:
                continue
            neg_ok = self._check_negation(claim.claim, sentence)
            number_ok = self._numbers_in_sentence(claim.claim, sentence)
            nli_ok = True
            if self.nli_checker is not None:
                nli_ok = self.nli_checker.check(claim.claim, sentence)
            if score >= 0.35 and neg_ok and number_ok and nli_ok:
                supported_sources.append(chunk)

        claim.is_supported = bool(supported_sources)
        claim.reasons = reasons or (["Claim is substantively supported by the cited chunk(s)."] if claim.is_supported else ["Claim is not supported by the provided sources."])
        claim.verified_sources = supported_sources
        return claim
