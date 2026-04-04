"""import_corpus.py – 语料导入脚本.

将原始高考真题/模拟题转换为规范的 Markdown 格式并更新语料库索引。

用法:
    python -m app.scripts.import_corpus --input path/to/raw_article.json

原始JSON格式示例:
{
  "id": "gk_2023_002",
  "source": "2023全国II卷",
  "type": "真题",
  "difficulty": "L3",
  "genre": "expository",
  "word_count": 310,
  "title": "Article Title",
  "content": "Article body text...",
  "questions": [
    {
      "question_text": "...",
      "options": {"A": "...", "B": "...", "C": "...", "D": "..."},
      "correct_answer": "B",
      "question_type": "detail",
      "explanation": "..."
    }
  ],
  "vocabulary": [
    {"word": "spark", "pos": "v.", "definition": "引发", "cefr": "B2"}
  ],
  "complex_sentences": [
    {
      "sentence": "...",
      "structure": "...",
      "translation": "..."
    }
  ]
}
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

_ROOT = Path(__file__).parent.parent.parent
_CORPUS_DIR = _ROOT / "data" / "corpus"
_ARTICLES_DIR = _CORPUS_DIR / "articles"
_INDEX_PATH = _CORPUS_DIR / "index.json"

_QUESTION_TYPE_NAMES = {
    "detail": "细节题",
    "inference": "推理题",
    "vocabulary": "词义题",
    "main_idea": "主旨题",
}


def _load_index() -> Dict[str, Any]:
    if not _INDEX_PATH.exists():
        return {
            "articles": {},
            "indexes": {
                "by_difficulty": {"L1": [], "L2": [], "L3": [], "L4": []},
                "by_genre": {"argumentative": [], "expository": [], "narrative": []},
                "by_type": {"真题": [], "模拟题": []},
            },
        }
    return json.loads(_INDEX_PATH.read_text(encoding="utf-8"))


def _save_index(index: Dict[str, Any]) -> None:
    _INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_markdown(raw: Dict[str, Any]) -> str:
    """Convert a raw article dict to the canonical Markdown format."""
    article_id = raw["id"]
    source = raw.get("source", "未知来源")
    article_type = raw.get("type", "模拟题")
    difficulty = raw.get("difficulty", "L2")
    genre = raw.get("genre", "expository")
    word_count = raw.get("word_count", 0)
    title = raw.get("title", "Untitled")
    content = raw.get("content", "")

    lines = [
        "---",
        f"id: {article_id}",
        f"source: {source}",
        f"type: {article_type}",
        f"difficulty: {difficulty}",
        f"genre: {genre}",
        f"word_count: {word_count}",
        "---",
        "",
        f"# {title}",
        "",
        "## 原文",
        "",
        content,
        "",
        "## 题目",
        "",
    ]

    for i, q in enumerate(raw.get("questions", []), 1):
        qt = q.get("question_type", "detail")
        qt_name = _QUESTION_TYPE_NAMES.get(qt, qt)
        lines += [
            f"### 题{i}",
            f"**题干**: {q.get('question_text', '')}",
            "**选项**: ",
        ]
        for opt_key, opt_val in q.get("options", {}).items():
            lines.append(f"- {opt_key}. {opt_val}")
        lines += [
            f"**答案**: {q.get('correct_answer', '')}",
            f"**类型**: {qt}（{qt_name}）",
            f"**解析**: {q.get('explanation', '')}",
            "",
        ]

    vocabulary = raw.get("vocabulary", [])
    if vocabulary:
        lines += [
            "## 生词表",
            "| 单词 | 词性 | 释义 | CEFR |",
            "|------|------|------|------|",
        ]
        for v in vocabulary:
            lines.append(
                f"| {v.get('word', '')} | {v.get('pos', '')} | {v.get('definition', '')} | {v.get('cefr', '')} |"
            )
        lines.append("")

    complex_sentences = raw.get("complex_sentences", [])
    if complex_sentences:
        lines += ["## 长难句", ""]
        for cs in complex_sentences:
            lines += [
                f"> \"{cs.get('sentence', '')}\"",
                f"**结构**: {cs.get('structure', '')}",
                f"**翻译**: {cs.get('translation', '')}",
                "",
            ]

    return "\n".join(lines)


def _register_in_index(index: Dict[str, Any], raw: Dict[str, Any], filename: str) -> None:
    """Add or update an article entry in the corpus index."""
    article_id = raw["id"]
    difficulty = raw.get("difficulty", "L2")
    genre = raw.get("genre", "expository")
    article_type = raw.get("type", "模拟题")

    metadata = {
        "id": article_id,
        "source": raw.get("source", ""),
        "type": article_type,
        "difficulty": difficulty,
        "genre": genre,
        "word_count": raw.get("word_count", 0),
    }
    index["articles"][article_id] = {"metadata": metadata, "path": filename}

    indexes = index.setdefault("indexes", {})

    by_diff = indexes.setdefault("by_difficulty", {})
    if article_id not in by_diff.setdefault(difficulty, []):
        by_diff[difficulty].append(article_id)

    by_genre = indexes.setdefault("by_genre", {})
    if article_id not in by_genre.setdefault(genre, []):
        by_genre[genre].append(article_id)

    by_type = indexes.setdefault("by_type", {})
    if article_id not in by_type.setdefault(article_type, []):
        by_type[article_type].append(article_id)


def import_article(raw_path: Path) -> None:
    """Import a single raw article JSON file into the corpus."""
    if not raw_path.exists():
        print(f"Error: file not found: {raw_path}", file=sys.stderr)
        sys.exit(1)

    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    article_id = raw.get("id")
    if not article_id:
        print("Error: raw article must have an 'id' field.", file=sys.stderr)
        sys.exit(1)

    _ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{article_id}.md"
    md_content = _build_markdown(raw)
    (_ARTICLES_DIR / filename).write_text(md_content, encoding="utf-8")
    print(f"Written: {_ARTICLES_DIR / filename}")

    index = _load_index()
    _register_in_index(index, raw, filename)
    _save_index(index)
    print(f"Index updated: {_INDEX_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import corpus articles into data/corpus/")
    parser.add_argument("--input", required=True, help="Path to raw article JSON file")
    args = parser.parse_args()
    import_article(Path(args.input))


if __name__ == "__main__":
    main()
