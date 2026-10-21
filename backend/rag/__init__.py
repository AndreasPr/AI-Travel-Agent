"""Local, free Retrieval-Augmented Generation helpers."""

from .citations import CitedClaim, CitationVerifier
from .ingestion.chunker import chunk_document
from .retrieval.hybrid import DefaultQueryRewriter, apply_metadata_filters, reciprocal_rank_fusion, rewrite_user_query

__all__ = [
    "CitedClaim",
    "CitationVerifier",
    "chunk_document",
    "apply_metadata_filters",
    "reciprocal_rank_fusion",
    "DefaultQueryRewriter",
    "rewrite_user_query",
]
