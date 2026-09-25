"""Small persistent hybrid index for fixed APS document collections."""

from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .atomic import write_text
from .canonical import canonical_checksum
from .content_models import DocumentSearchRequest, DocumentSearchResponse, DocumentSearchResult, IdeasData
from .content_store import ContentStore
from .idea_service import IdeaService


INDEX_VERSION = 1
EMBEDDING_MODEL = "aps-hash-subword-v1-256"
DIMENSIONS = 256
MAX_DOCUMENTS = 100000
MAX_INDEX_BYTES = 64 * 1024 * 1024
_TOKEN = re.compile(r"[0-9A-Za-z가-힣]+")
_MARKUP = re.compile(r"[`*_>#\[\](){}|~-]+")


class SearchIndexError(RuntimeError):
    pass


@dataclass(frozen=True)
class SearchDocument:
    collection: str
    document_id: str
    title: str
    keywords: tuple[str, ...]
    summary: str
    status: str

    def payload(self) -> dict[str, object]:
        return {
            "collection": self.collection,
            "document_id": self.document_id,
            "title": self.title,
            "keywords": list(self.keywords),
            "summary": self.summary,
            "status": self.status,
        }


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold().strip()


def _tokens(value: str) -> set[str]:
    return set(_TOKEN.findall(_normalize(value)))


def _features(value: str) -> list[str]:
    normalized = _normalize(value)
    tokens = _TOKEN.findall(normalized)
    features = list(tokens)
    for token in tokens:
        padded = f"^{token}$"
        for size in (2, 3):
            features.extend(padded[index:index + size] for index in range(len(padded) - size + 1))
    return features


def _embedding(value: str) -> list[float]:
    vector = [0.0] * DIMENSIONS
    for feature in _features(value):
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8, person=b"apssearch").digest()
        number = int.from_bytes(digest)
        vector[number % DIMENSIONS] += 1.0 if number & 1 else -1.0
    norm = math.sqrt(sum(item * item for item in vector))
    return [round(item / norm, 8) for item in vector] if norm else vector


def _cosine(left: list[float], right: list[float]) -> float:
    return max(0.0, sum(a * b for a, b in zip(left, right, strict=True)))


def _fallback_summary(content: str) -> str:
    cleaned = _MARKUP.sub(" ", content)
    return " ".join(cleaned.split())[:500]


class DocumentSearchIndex:
    def __init__(self, data_path: Path, content_store: ContentStore, ideas: IdeaService) -> None:
        self.path = data_path / "search" / "index.json"
        self.content_store = content_store
        self.ideas = ideas
        self._lock = threading.RLock()

    def _documents(self) -> tuple[list[SearchDocument], dict[str, str | None]]:
        idea_response = self.content_store.ideas_or_empty()
        idea_data: IdeasData = self.ideas.overlay(idea_response.data)
        documents = [
            SearchDocument(
                collection="inbox" if item.storage == "inbox" else "idea",
                document_id=item.idea_id,
                title=item.title,
                keywords=tuple(item.keywords),
                summary=item.summary,
                status=item.status,
            )
            for item in idea_data.ideas
        ]
        documents.extend(
            SearchDocument("idea_set", item.idea_set_id, item.title, tuple(item.keywords), item.summary, item.status)
            for item in idea_data.idea_sets
        )
        try:
            vault = self.content_store.vault_documents()
        except KeyError:
            vault = None
        if vault is not None:
            for collection, items in (("project", vault.data.projects), ("service", vault.data.services)):
                documents.extend(
                    SearchDocument(
                        collection, item.document_id, item.name, (), item.summary or _fallback_summary(item.content), item.status,
                    )
                    for item in items
                )
        documents.sort(key=lambda item: (item.collection, item.document_id))
        inbox_revision = canonical_checksum([
            item.payload() for item in documents if item.collection == "inbox"
        ])
        return documents, {
            "ideas_vault_commit": idea_response.vault_commit,
            "documents_vault_commit": vault.vault_commit if vault is not None else None,
            "inbox_revision": inbox_revision,
        }

    @staticmethod
    def _validate_document(value: object) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise SearchIndexError("stored search document is not an object")
        required_strings = ("collection", "document_id", "title", "summary", "status", "document_hash")
        if any(not isinstance(value.get(key), str) for key in required_strings):
            raise SearchIndexError("stored search document has invalid fields")
        if value["collection"] not in {"inbox", "idea", "idea_set", "project", "service"}:
            raise SearchIndexError("stored search document has an invalid collection")
        keywords = value.get("keywords")
        if not isinstance(keywords, list) or not all(isinstance(item, str) for item in keywords):
            raise SearchIndexError("stored search document has invalid keywords")
        vector = value.get("embedding")
        if vector is not None and (
            not isinstance(vector, list)
            or len(vector) != DIMENSIONS
            or not all(type(item) in (int, float) and math.isfinite(item) for item in vector)
        ):
            raise SearchIndexError("stored search document has an invalid embedding")
        return value

    def _load(self) -> dict[str, Any] | None:
        if not self.path.is_file():
            return None
        if self.path.stat().st_size > MAX_INDEX_BYTES:
            raise SearchIndexError("stored search index exceeds the size limit")
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not isinstance(value.get("documents"), list):
            raise SearchIndexError("stored search index has an invalid structure")
        if value.get("version") != INDEX_VERSION or value.get("embedding_model") != EMBEDDING_MODEL:
            return None
        payload = {key: item for key, item in value.items() if key != "checksum"}
        if value.get("checksum") != canonical_checksum(payload):
            raise SearchIndexError("stored search index checksum is invalid")
        if len(value["documents"]) > MAX_DOCUMENTS:
            raise SearchIndexError("stored search index exceeds the document limit")
        value["documents"] = [self._validate_document(item) for item in value["documents"]]
        keys = {(item["collection"], item["document_id"]) for item in value["documents"]}
        if len(keys) != len(value["documents"]):
            raise SearchIndexError("stored search index contains duplicate documents")
        if not isinstance(value.get("index_revision"), str) or not isinstance(value.get("indexed_at"), str):
            raise SearchIndexError("stored search index has invalid metadata")
        return value

    def _refresh(self) -> tuple[dict, bool]:
        try:
            previous = self._load()
        except (OSError, ValueError, SearchIndexError):
            previous = None
        try:
            documents, source_revisions = self._documents()
            if len(documents) > MAX_DOCUMENTS:
                raise SearchIndexError(f"search catalog exceeds {MAX_DOCUMENTS} documents")
            previous_by_key = {
                (item["collection"], item["document_id"]): item
                for item in (previous or {}).get("documents", [])
            }
            indexed = []
            for document in documents:
                payload = document.payload()
                digest = canonical_checksum(payload)
                old = previous_by_key.get((document.collection, document.document_id))
                if old and old.get("document_hash") == digest and old.get("embedding") is not None:
                    vector = old["embedding"]
                else:
                    try:
                        vector = _embedding(" ".join([document.title, *document.keywords, document.summary]))
                    except Exception:
                        vector = None
                indexed.append({**payload, "document_hash": digest, "embedding": vector})
            revision = canonical_checksum({
                "embedding_model": EMBEDDING_MODEL,
                "sources": source_revisions,
                "documents": [
                    {"collection": item["collection"], "document_id": item["document_id"], "document_hash": item["document_hash"]}
                    for item in indexed
                ],
            })
            if previous and previous.get("index_revision") == revision:
                return previous, False
            value = {
                "version": INDEX_VERSION,
                "embedding_model": EMBEDDING_MODEL,
                "index_revision": revision,
                "indexed_at": datetime.now(UTC).isoformat(),
                "source_revisions": source_revisions,
                "documents": indexed,
            }
            value["checksum"] = canonical_checksum(value)
            write_text(self.path, json.dumps(value, ensure_ascii=False, separators=(",", ":")))
            return value, False
        except Exception as error:
            if previous is not None:
                return previous, True
            if isinstance(error, SearchIndexError):
                raise
            raise SearchIndexError(str(error)) from error

    @staticmethod
    def _lexical(document: dict, query: str) -> tuple[float, list[str]]:
        query_text = _normalize(query)
        query_tokens = _tokens(query)
        scores = []
        matched = []
        for field, weight in (("title", 0.55), ("keywords", 0.3), ("summary", 0.15)):
            raw = " ".join(document[field]) if field == "keywords" else document[field]
            target = _tokens(raw)
            score = len(query_tokens & target) / len(query_tokens) if query_tokens else 0.0
            if query_text and query_text in _normalize(raw):
                score = max(score, 1.0)
            scores.append(weight * score)
            if score > 0:
                matched.append("keyword" if field == "keywords" else field)
        return min(sum(scores), 1.0), matched

    def search(self, request: DocumentSearchRequest) -> DocumentSearchResponse:
        with self._lock:
            index, stale = self._refresh()
            try:
                query_vector = _embedding(request.query)
            except Exception:
                query_vector = None
            hybrid = query_vector is not None and all(item.get("embedding") is not None for item in index["documents"])
            collections = set(request.collections)
            statuses = set(request.statuses)
            ranked = []
            for document in index["documents"]:
                if collections and document["collection"] not in collections:
                    continue
                if statuses and document["status"] not in statuses:
                    continue
                lexical, matched = self._lexical(document, request.query)
                semantic = _cosine(query_vector, document["embedding"]) if hybrid else 0.0
                score = min(1.0, lexical * 0.75 + semantic * 0.25) if hybrid else lexical
                if lexical <= 0 and (not hybrid or semantic < 0.12):
                    continue
                if semantic >= 0.12:
                    matched.append("embedding")
                result = DocumentSearchResult(
                    collection=document["collection"], document_id=document["document_id"], title=document["title"],
                    status=document["status"], summary=document["summary"][:500], score=round(score, 4),
                    matched_by=list(dict.fromkeys(matched)),
                )
                ranked.append((score, result))
            ranked.sort(key=lambda item: (-item[0], item[1].collection, item[1].title.casefold(), item[1].document_id))
            results = [item[1] for item in ranked]
            page = results[request.offset:request.offset + request.limit]
            next_offset = request.offset + request.limit if request.offset + request.limit < len(results) else None
            return DocumentSearchResponse(
                query=request.query, search_mode="hybrid" if hybrid else "lexical_fallback",
                embedding_model=EMBEDDING_MODEL if hybrid else None,
                index_revision=index["index_revision"], indexed_at=index["indexed_at"], stale=stale,
                total=len(results), offset=request.offset, limit=request.limit, next_offset=next_offset, results=page,
            )
