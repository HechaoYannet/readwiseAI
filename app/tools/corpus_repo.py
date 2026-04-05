"""CorpusRepository – 结构化语料库检索工具.

提供对 data/corpus/ 目录下高考真题语料的搜索和随机抽样功能。
"""
from __future__ import annotations

import json
import logging
import random
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_CORPUS_DIR = Path(__file__).parent.parent.parent / "data" / "corpus"
_INDEX_PATH = _CORPUS_DIR / "index.json"
_ARTICLES_DIR = _CORPUS_DIR / "articles"

# Maximum characters returned per article to avoid overly long context
_MAX_ARTICLE_CHARS = 2000


def _load_index() -> Dict[str, Any]:
    """Load the corpus index from disk. Returns empty structure if missing."""
    try:
        return json.loads(_INDEX_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning("Corpus index not found at %s", _INDEX_PATH)
        return {"articles": {}, "indexes": {}}
    except json.JSONDecodeError as exc:
        logger.error("Corpus index is malformed: %s", exc)
        return {"articles": {}, "indexes": {}}


def _read_article(article_id: str) -> Optional[str]:
    """Read an article's Markdown content by its ID."""
    index = _load_index()
    entry = index.get("articles", {}).get(article_id)
    if not entry:
        return None
    path = _ARTICLES_DIR / entry["path"]
    try:
        content = path.read_text(encoding="utf-8")
        return content[:_MAX_ARTICLE_CHARS]
    except FileNotFoundError:
        logger.warning("Article file not found: %s", path)
        return None


class CorpusRepository:
    """High-level interface for accessing the structured exam corpus."""

    def search(
        self,
        difficulty: Optional[str] = None,
        genre: Optional[str] = None,
        article_type: Optional[str] = None,
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        """Search for articles matching the given filters.

        Args:
            difficulty: One of L1/L2/L3/L4.
            genre: One of argumentative/expository/narrative.
            article_type: One of 真题/模拟题.
            limit: Maximum number of results to return.

        Returns:
            A list of article metadata dicts (without full content).
        """
        index = _load_index()
        candidates: Optional[set] = None

        def _intersect(ids: List[str]) -> None:
            nonlocal candidates
            if candidates is None:
                candidates = set(ids)
            else:
                candidates &= set(ids)

        indexes = index.get("indexes", {})
        if difficulty:
            _intersect(indexes.get("by_difficulty", {}).get(difficulty, []))
        if genre:
            _intersect(indexes.get("by_genre", {}).get(genre, []))
        if article_type:
            _intersect(indexes.get("by_type", {}).get(article_type, []))

        if candidates is None:
            # No filters applied – return all
            candidates = set(index.get("articles", {}).keys())

        articles_meta = index.get("articles", {})
        results = [
            articles_meta[aid]["metadata"]
            for aid in list(candidates)[:limit]
            if aid in articles_meta
        ]
        return results

    def get_random_examples(
        self,
        difficulty: Optional[str] = None,
        genre: Optional[str] = None,
        count: int = 1,
        include_content: bool = True,
    ) -> List[Dict[str, Any]]:
        """Return random example articles, optionally with full content.

        Args:
            difficulty: Filter by difficulty level.
            genre: Filter by genre.
            count: Number of examples to return.
            include_content: Whether to include the full Markdown content.

        Returns:
            A list of article dicts with metadata and optionally content.
        """
        candidates = self.search(difficulty=difficulty, genre=genre, limit=100)
        if not candidates:
            return []

        selected = random.sample(candidates, min(count, len(candidates)))
        results = []
        for meta in selected:
            entry: Dict[str, Any] = {"metadata": meta}
            if include_content:
                content = _read_article(meta["id"])
                entry["content"] = content or ""
            results.append(entry)
        return results

    def get_article(self, article_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single article by its ID.

        Args:
            article_id: The unique identifier of the article.

        Returns:
            A dict with 'metadata' and 'content' keys, or None if not found.
        """
        index = _load_index()
        meta = index.get("articles", {}).get(article_id, {}).get("metadata")
        if not meta:
            return None
        content = _read_article(article_id)
        return {"metadata": meta, "content": content or ""}

    def get_all_metadata(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return metadata for all articles in the corpus index.

        Args:
            limit: Maximum number of entries to return (safety cap).

        Returns:
            A list of article metadata dicts (without full content).
        """
        index = _load_index()
        articles = index.get("articles", {})
        results = []
        for aid, entry in list(articles.items())[:limit]:
            meta = entry.get("metadata")
            if meta:
                results.append(meta)
        return results

    def format_examples_for_prompt(
        self,
        difficulty: Optional[str] = None,
        genre: Optional[str] = None,
        count: int = 1,
    ) -> str:
        """Return a formatted string of example articles suitable for injection into a prompt.

        Args:
            difficulty: Filter by difficulty level.
            genre: Filter by genre.
            count: Number of examples.

        Returns:
            A Markdown-formatted string, or a placeholder if no examples found.
        """
        examples = self.get_random_examples(
            difficulty=difficulty, genre=genre, count=count, include_content=True
        )
        if not examples:
            return "（暂无相关语料库参考样例）"

        parts = []
        for ex in examples:
            meta = ex.get("metadata", {})
            content = ex.get("content", "")
            parts.append(
                f"**来源**: {meta.get('source', '未知')} | "
                f"**难度**: {meta.get('difficulty', '?')} | "
                f"**体裁**: {meta.get('genre', '?')}\n\n"
                f"{content}"
            )
        return "\n\n---\n\n".join(parts)


# Module-level singleton
_corpus_repo: Optional[CorpusRepository] = None


def get_corpus_repo() -> CorpusRepository:
    """Return the shared CorpusRepository singleton."""
    global _corpus_repo
    if _corpus_repo is None:
        _corpus_repo = CorpusRepository()
    return _corpus_repo
