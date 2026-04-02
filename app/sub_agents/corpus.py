"""CorpusExpert – 高考风格文章生成."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

from app.sub_agents.base import BaseSubAgent

logger = logging.getLogger(__name__)

ARTICLE_PROMPT = """
你是高考英语阅读材料专家。请生成一篇符合高考风格的英语文章。

## 要求
难度等级：{difficulty}（L1最简单，L4最难）
体裁：{genre}（argumentative议论文/expository说明文/narrative记叙文）
主题：{topic}
目标字数：{word_count}词

## 难度对照
- L1：初中水平，词汇简单，句型短
- L2：高中低年级，词汇较丰富，含简单从句
- L3：高考主流难度，词汇多样，含复杂句型
- L4：高考压轴难度，词汇高级，句式复杂

## 输出格式（严格JSON，只输出JSON）
{{
  "title": "文章标题",
  "content": "文章正文（英文）",
  "word_count": 305,
  "difficulty_actual": "L2",
  "genre_actual": "expository",
  "key_vocabulary": ["word1", "word2"]
}}
"""

DIFFICULTY_CONSTRAINTS = {
    "L1": {"max_sentence_len": 15, "avg_word_len": 5},
    "L2": {"max_sentence_len": 25, "avg_word_len": 6},
    "L3": {"max_sentence_len": 35, "avg_word_len": 7},
    "L4": {"max_sentence_len": 50, "avg_word_len": 8},
}


def _validate_article(article: Dict[str, Any], difficulty: str) -> Dict[str, Any]:
    """Basic validation of the generated article."""
    issues: List[str] = []
    content = article.get("content", "")
    wc = len(content.split())
    if wc < 50:
        issues.append(f"字数太少: {wc}")
    if not article.get("title"):
        issues.append("缺少标题")
    return {"passed": len(issues) == 0, "issues": issues}


class CorpusExpert(BaseSubAgent):
    name = "corpus_expert"
    description = "高考风格文章生成"

    async def execute(
        self, input: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        start = time.time()
        difficulty = input.get("difficulty", "L2")
        genre = input.get("genre", "expository")
        topic = input.get("topic", "technology")
        word_count = input.get("word_count", 300)

        article: Dict[str, Any] = {}
        validation: Dict[str, Any] = {"passed": False, "issues": []}

        for attempt in range(3):
            prompt = ARTICLE_PROMPT.format(
                difficulty=difficulty,
                genre=genre,
                topic=topic,
                word_count=word_count,
            )
            article = await self._call_llm(prompt)
            if not article:
                article = {"title": "", "content": "", "word_count": 0}

            validation = _validate_article(article, difficulty)
            if validation["passed"]:
                return {
                    "article": article,
                    "validation": validation,
                    "metadata": {
                        "attempts": attempt + 1,
                        "latency_ms": self._timed(start),
                        "agent": self.name,
                    },
                }
            logger.warning(
                "CorpusExpert attempt %d failed validation: %s",
                attempt + 1,
                validation["issues"],
            )

        return {
            "article": article,
            "validation": validation,
            "metadata": {
                "attempts": 3,
                "partial": True,
                "latency_ms": self._timed(start),
                "agent": self.name,
            },
        }
