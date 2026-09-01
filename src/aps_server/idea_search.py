from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from .content_models import IdeaItem, IdeaSearchResult


_TOKEN = re.compile(r"[0-9A-Za-z가-힣]+")


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold().strip()


def _tokens(value: str) -> set[str]:
    return set(_TOKEN.findall(_normalize(value)))


def _coverage(query: set[str], target: set[str]) -> float:
    return len(query & target) / len(query) if query else 0.0


def search_ideas(ideas: list[IdeaItem], query: str, limit: int) -> list[IdeaSearchResult]:
    normalized_query = _normalize(query)
    query_tokens = _tokens(query)
    ranked: list[tuple[float, IdeaSearchResult]] = []
    for idea in ideas:
        title = _normalize(idea.title)
        title_tokens = _tokens(idea.title)
        keyword_tokens = {token for keyword in idea.keywords for token in _tokens(keyword)}
        summary = _normalize(idea.summary)
        summary_tokens = _tokens(idea.summary)

        title_score = max(_coverage(query_tokens, title_tokens), SequenceMatcher(None, normalized_query, title).ratio() * 0.5)
        keyword_score = _coverage(query_tokens, keyword_tokens)
        summary_score = _coverage(query_tokens, summary_tokens)
        score = 0.55 * title_score + 0.3 * keyword_score + 0.15 * summary_score
        if normalized_query and normalized_query in title:
            score += 0.2
        elif normalized_query and normalized_query in summary:
            score += 0.08
        score = min(score, 1.0)
        if score < 0.1:
            continue

        matched_by: list[str] = []
        if title_score > 0:
            matched_by.append("title")
        if keyword_score > 0:
            matched_by.append("keyword")
        if summary_score > 0:
            matched_by.append("summary")
        result = IdeaSearchResult(
            idea_id=idea.idea_id,
            title=idea.title,
            score=round(score, 4),
            matched_by=matched_by,
        )
        ranked.append((score, result))

    ranked.sort(key=lambda item: (-item[0], item[1].title.casefold(), item[1].idea_id))
    return [item[1] for item in ranked[:limit]]


def similar_ideas(ideas: list[IdeaItem], source: IdeaItem, limit: int) -> list[IdeaSearchResult]:
    source_title = _normalize(source.title)
    source_keywords = {token for keyword in source.keywords for token in _tokens(keyword)}
    source_summary = _tokens(source.summary)
    ranked: list[tuple[float, IdeaSearchResult]] = []
    for idea in ideas:
        if idea.idea_id == source.idea_id:
            continue
        target_keywords = {token for keyword in idea.keywords for token in _tokens(keyword)}
        target_summary = _tokens(idea.summary)
        keyword_union = source_keywords | target_keywords
        summary_union = source_summary | target_summary
        title_score = SequenceMatcher(None, source_title, _normalize(idea.title)).ratio()
        keyword_score = len(source_keywords & target_keywords) / len(keyword_union) if keyword_union else 0.0
        summary_score = len(source_summary & target_summary) / len(summary_union) if summary_union else 0.0
        score = 0.45 * title_score + 0.35 * keyword_score + 0.2 * summary_score
        if score < 0.15:
            continue
        matched_by = []
        if title_score >= 0.2:
            matched_by.append("title")
        if keyword_score > 0:
            matched_by.append("keyword")
        if summary_score > 0:
            matched_by.append("summary")
        result = IdeaSearchResult(
            idea_id=idea.idea_id,
            title=idea.title,
            score=round(score, 4),
            matched_by=matched_by,
        )
        ranked.append((score, result))

    ranked.sort(key=lambda item: (-item[0], item[1].title.casefold(), item[1].idea_id))
    return [item[1] for item in ranked[:limit]]
