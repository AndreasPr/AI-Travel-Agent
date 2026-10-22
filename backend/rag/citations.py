from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Iterable, Protocol

NEGATION_WORDS = {
    "no",
    "not",
    "never",
    "none",
    "nothing",
    "nobody",
    "without",
    "cannot",
    "can't",
    "isn't",
    "isnt",
    "aren't",
    "arent",
    "doesn't",
    "doesnt",
    "don't",
    "dont",
    "wasn't",
    "wasnt",
    "weren't",
    "werent",
}


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

    def _number_tokens(self, text: str) -> list[float]:
        matches = re.findall(r"(?:€|£|\$)?\d{1,3}(?:,\d{3})*(?:\.\d+)?|(?:€|£|\$)?\d+(?:\.\d+)?", text or "")
        numbers: list[float] = []
        for match in matches:
            cleaned = match.replace(",", "").replace("€", "").replace("£", "").replace("$", "")
            if cleaned:
                try:
                    numbers.append(float(cleaned))
                except ValueError:
                    continue
        return numbers

    def _claim_numbers(self, text: str) -> list[float]:
        return self._number_tokens(text)

    def _has_negation(self, text: str) -> bool:
        lowered = (text or "").lower()
        pattern = re.compile(
            r"\b(?:no|not|never|none|nothing|nobody|without|cannot|can\'t|can't|isn\'t|isnt|aren\'t|arent|doesn\'t|doesnt|don\'t|dont|wasn\'t|wasnt|weren\'t|werent|free of)\b|n\'t\b",
            re.IGNORECASE,
        )
        return bool(pattern.search(lowered))

    def _check_negation(self, claim: str, sentence: str) -> bool:
        return self._has_negation(claim) == self._has_negation(sentence)

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
        sentence_numbers = self._number_tokens(sentence)
        for number in claim_numbers:
            if number not in sentence_numbers:
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

        claim_sentences = self._split_sentences(claim.claim)
        if not claim_sentences:
            claim.is_supported = False
            claim.reasons = ["Claim text was empty or unparsable."]
            claim.verified_sources = []
            return claim

        sentence_support: list[bool] = []
        for sentence in claim_sentences:
            sentence_supported = False
            for chunk_id in claim.source_chunk_ids:
                chunk = self.by_id.get(str(chunk_id))
                if not chunk:
                    continue
                sentence_match, score = self._best_sentence(sentence, chunk)
                if not sentence_match:
                    continue
                neg_ok = self._check_negation(sentence, sentence_match)
                number_ok = self._numbers_in_sentence(sentence, sentence_match)
                nli_ok = True
                if self.nli_checker is not None:
                    nli_ok = self.nli_checker.check(sentence, sentence_match)
                if score >= 0.35 and neg_ok and number_ok and nli_ok:
                    sentence_supported = True
                    if chunk not in supported_sources:
                        supported_sources.append(chunk)
                    break
            sentence_support.append(sentence_supported)

        if not all(sentence_support):
            reasons.append("At least one sentence in the claim is not supported by the cited source(s).")

        claim.is_supported = bool(supported_sources) and all(sentence_support)
        claim.reasons = reasons or (["Claim is substantively supported by the cited chunk(s)."] if claim.is_supported else ["Claim is not supported by the provided sources."])
        claim.verified_sources = supported_sources if claim.is_supported else []
        return claim
