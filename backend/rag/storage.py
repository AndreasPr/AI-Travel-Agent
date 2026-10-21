from __future__ import annotations

from typing import Any

from sqlalchemy import func

from backend.db.connect import SessionLocal
from backend.db.models import Document, DocumentChunk


def store_document_chunks(
    chunks: list[dict[str, Any]],
    city: str,
    country: str,
    source_url: str,
    title: str,
) -> list[dict[str, Any]]:
    inserted: list[dict[str, Any]] = []
    with SessionLocal() as session:
        document = Document(
            source_url=source_url,
            title=title,
            license="CC BY-SA 4.0",
            city=city,
            country=country,
            season=None,
            topic="other",
            text="\n\n".join(chunk["text"] for chunk in chunks),
        )
        session.add(document)
        session.flush()
        for index, chunk in enumerate(chunks):
            chunk_text = chunk["text"]
            chunk_id = chunk["chunk_id"]
            embedding = chunk.get("embedding")
            db_chunk = DocumentChunk(
                document_id=document.id,
                chunk_index=index,
                text=chunk_text,
                embedding=embedding,
                search_vector=func.to_tsvector("english", chunk_text),
            )
            session.add(db_chunk)
            inserted.append({"chunk_id": chunk_id, "document_id": document.id, "chunk_index": index, "text": chunk_text})
        session.commit()
    return inserted
