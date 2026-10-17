"""Vector index of answer steps: Chroma (local folder) + bge-m3 through Ollama. Free, no Docker.

One entry per step per language: English plus every translation that has text.
Metadata on every entry: question_id, answer_id, teacher_id, step_no, language.

Indexing never blocks saving an answer: any failure is logged and the answer is still saved.
Put this file in app/ (next to image_service.py).
"""
import logging
import threading
from typing import List

import chromadb
import requests

from app.config import settings

logger = logging.getLogger(__name__)

COLLECTION = "st_answer_steps"
EMBED_MODEL = "bge-m3"
BATCH = 32  # texts sent to Ollama per request

_lock = threading.Lock()
_client = None
_collection_obj = None


def _collection():
    """Open (or create) the Chroma collection once. Vectors come from Ollama, not from Chroma."""
    global _client, _collection_obj
    with _lock:
        if _collection_obj is None:
            _client = chromadb.PersistentClient(path=settings.chroma_path)
            _collection_obj = _client.get_or_create_collection(
                name=COLLECTION,
                metadata={"hnsw:space": "cosine"},
                embedding_function=None,
            )
        return _collection_obj


def reset_collection() -> None:
    """Delete everything in the index (used by the rebuild script with --reset)."""
    global _collection_obj
    _collection()  # makes sure the client exists
    with _lock:
        _client.delete_collection(COLLECTION)
        _collection_obj = None


def embed(texts: List[str]) -> List[List[float]]:
    """Text -> vectors, using bge-m3 running in Ollama."""
    url = f"{settings.ollama_url.rstrip('/')}/api/embed"
    out: List[List[float]] = []
    for i in range(0, len(texts), BATCH):
        r = requests.post(url, json={"model": EMBED_MODEL, "input": texts[i:i + BATCH]}, timeout=120)
        r.raise_for_status()
        out.extend(r.json()["embeddings"])
    return out


def answer_to_docs(answer) -> List[dict]:
    """Plain data for one answer (so it can be indexed after the DB session is closed).

    `answer` is an Answer with its steps and step translations loaded.
    """
    docs: List[dict] = []
    for s in answer.steps:
        base = {
            "question_id": int(answer.question_id),
            "answer_id": int(answer.answer_id),
            "teacher_id": int(answer.teacher_id or 0),
            "step_no": int(s.step_no),
        }
        text = (s.step_text or "").strip()
        if text:
            docs.append({"id": f"{answer.answer_id}:{s.step_no}:en", "text": text,
                         "meta": {**base, "language": "en"}})
        for t in s.translations or []:
            tt = (t.step_text or "").strip()
            if tt:
                docs.append({"id": f"{answer.answer_id}:{s.step_no}:{t.language_code}", "text": tt,
                             "meta": {**base, "language": t.language_code}})
    return docs


def index_answer_docs(answer_id: int, docs: List[dict]) -> None:
    """Replace everything indexed for this answer. Safe to call from a background task."""
    try:
        vectors = embed([d["text"] for d in docs]) if docs else []  # first: if Ollama is down, the old index stays
        col = _collection()
        col.delete(where={"answer_id": answer_id})
        if docs:
            col.upsert(
                ids=[d["id"] for d in docs],
                embeddings=vectors,
                documents=[d["text"] for d in docs],
                metadatas=[d["meta"] for d in docs],
            )
    except Exception as exc:
        logger.warning("could not index answer %s: %s", answer_id, exc)


def delete_answer_index(answer_id: int) -> None:
    try:
        _collection().delete(where={"answer_id": answer_id})
    except Exception as exc:
        logger.warning("could not remove answer %s from the index: %s", answer_id, exc)


def search_steps(question_id: int, language: str, text: str, k: int = 3) -> List[dict]:
    """Closest teacher steps for one question, in one language. score: 1.0 = identical meaning.

    Used for testing now and by the practice page's check endpoint next.
    """
    vector = embed([text])[0]
    res = _collection().query(
        query_embeddings=[vector],
        n_results=k,
        where={"$and": [{"question_id": question_id}, {"language": language}]},
    )
    hits = []
    for i in range(len(res["ids"][0])):
        meta = res["metadatas"][0][i]
        hits.append({
            "answer_id": meta["answer_id"],
            "teacher_id": meta["teacher_id"],
            "step_no": meta["step_no"],
            "text": res["documents"][0][i],
            "score": round(1 - res["distances"][0][i], 3),
        })
    return hits
