from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Iterable, Protocol

from backend.rag.config import get_nli_model_name, get_nli_threshold

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
STOPWORDS = {
    "a", "an", "and", "are", "at", "be", "been", "being", "for", "from", "great",
    "has", "have", "in", "is", "it", "its", "of", "on", "the", "their",
    "this", "to", "with", "without", "your", "there", "these", "those", "we", "you",
    "our", "they", "them", "he", "she", "his", "her", "as", "by", "about", "into",
    "over", "under", "after", "before", "between", "through", "during", "if", "or",
    "than", "then", "so", "too", "very", "but", "can", "could", "should", "would",
    "will", "do", "does", "did", "had", "was", "were", "also", "only", "most",
}


class NLIInterface(Protocol):
    def check(self, claim: str, sentence: str) -> bool:
        ...


class FakeNLI:
    def __init__(self, result: bool = True):
        self.result = result

    def check(self, claim: str, sentence: str) -> bool:
        return self.result


class CrossEncoderNLI:
    def __init__(self, model_name: str | None = None, threshold: float | None = None):
        self.model_name = model_name or get_nli_model_name()
        self.threshold = float(threshold if threshold is not None else get_nli_threshold())
        self._model: Any | None = None

    def _load(self) -> Any:
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name)
        return self._model

    def check(self, claim: str, sentence: str) -> bool:
        if not claim or not sentence:
            return False
        model = self._load()
        result = model.predict([(claim, sentence)], show_progress_bar=False)
        scores = result[0] if isinstance(result, list) and result and isinstance(result[0], (list, tuple)) else result
        if isinstance(scores, dict):
            label_scores = scores
        else:
            label_scores = {
                "contradiction": float(scores[0]) if len(scores) > 0 else 0.0,
                "entailment": float(scores[1]) if len(scores) > 1 else 0.0,
                "neutral": float(scores[2]) if len(scores) > 2 else 0.0,
            }
        if hasattr(model, "config") and hasattr(model.config, "id2label"):
            mapped: dict[str, float] = {}
            for index, label in getattr(model.config, "id2label", {}).items():
                key = str(label).lower()
                if key.startswith("label_"):
                    key = key[6:]
                mapped[key] = float(label_scores.get(key, 0.0)) if key in label_scores else float(label_scores.get(str(index), 0.0))
            if mapped:
                label_scores = mapped
        best_label = max(label_scores, key=lambda item: float(label_scores[item]))
        if best_label == "entailment":
            return float(label_scores.get(best_label, 0.0)) >= self.threshold
        return False


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
    def __init__(self, source_chunks: Iterable[dict[str, Any]], nli_checker: NLIInterface | None = None, use_nli: bool = False):
        self.source_chunks = list(source_chunks)
        self.by_id = {str(chunk.get("chunk_id")): chunk for chunk in self.source_chunks if chunk.get("chunk_id")}
        self.nli_checker = nli_checker or (CrossEncoderNLI() if use_nli else None)

    def _stem(self, token: str) -> str:
        word = token.lower().strip("'\"")
        if len(word) <= 3:
            return word
        if word.endswith("ies") and len(word) > 4:
            return word[:-3] + "y"
        if word.endswith("es") and len(word) > 4:
            return word[:-2]
        if word.endswith("s") and not word.endswith("ss"):
            return word[:-1]
        return word

    def _content_tokens(self, text: str, ignored_tokens: set[str] | None = None) -> list[str]:
        ignored = ignored_tokens or set()
        words = re.findall(r"(?:\d+(?:[.,]\d+)*|[A-Za-z0-9][A-Za-z0-9'-]*)", (text or ""))
        tokens: list[str] = []
        for raw in words:
            token = self._stem(raw.replace(",", ""))
            if not token or token in STOPWORDS or token in ignored:
                continue
            tokens.append(token)
        return tokens

    def _ignore_tokens(self, chunk: dict[str, Any] | None = None) -> set[str]:
        ignored: set[str] = set()
        for source_text in [chunk.get("title") if chunk else "", chunk.get("city") if chunk else "", chunk.get("country") if chunk else ""]:
            if not source_text:
                continue
            for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", str(source_text)):
                ignored.add(self._stem(token))
        return ignored

    def _tokenize(self, text: str) -> set[str]:
        return set(self._content_tokens(text))

    def _split_sentences(self, text: str) -> list[str]:
        if not text:
            return []
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        return [sentence.strip() for sentence in sentences if sentence.strip()]

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
        ignored = self._ignore_tokens(chunk)
        best_sentence = ""
        best_score = 0.0
        for sentence in sentences:
            claim_tokens = self._content_tokens(claim)
            sentence_tokens = self._content_tokens(sentence, ignored)
            if not claim_tokens:
                score = 0.0
            else:
                overlap = len(set(claim_tokens) & set(sentence_tokens))
                score = overlap / max(1, len(set(claim_tokens)))
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
                ignore_tokens = self._ignore_tokens(chunk)
                cover_tokens = self._content_tokens(sentence, ignore_tokens)
                ref_tokens = self._content_tokens(sentence_match, ignore_tokens)
                matched = len(set(cover_tokens) & set(ref_tokens))
                coverage = (matched / max(1, len(set(cover_tokens)))) if cover_tokens else 0.0
                required_matches = min(2, len(set(cover_tokens)))
                neg_ok = self._check_negation(sentence, sentence_match)
                number_ok = self._numbers_in_sentence(sentence, sentence_match)
                nli_ok = True
                if self.nli_checker is not None:
                    nli_ok = self.nli_checker.check(sentence, sentence_match)
                if coverage >= 0.6 and matched >= required_matches and neg_ok and number_ok and nli_ok:
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
