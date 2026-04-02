"""QuestionExpert – 题目生成."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

from app.sub_agents.base import BaseSubAgent

logger = logging.getLogger(__name__)

QUESTION_PROMPT = """
你是高考英语出题专家。请根据以下文章段落出一道阅读理解题。

## 文章段落
{article_segment}

## 题型要求
题型：{question_type}（detail细节题/inference推理题/vocabulary词义题）
难度：{difficulty}（L1-L4）

## 输出格式（严格JSON，只输出JSON）
{{
  "question": "题目内容",
  "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
  "correct_answer": "A",
  "explanation": "解析（说明答案依据在文章哪里）",
  "evidence": "原文中的依据句子"
}}
"""


def _select_anchor(article: str, question_type: str) -> str:
    """Select a segment of the article to base the question on."""
    sentences = [s.strip() for s in article.split(".") if s.strip()]
    if not sentences:
        return article[:300]
    # For detail: pick middle sentences; for inference: last paragraph; for vocabulary: any
    if question_type == "detail" and len(sentences) >= 3:
        mid = len(sentences) // 2
        return ". ".join(sentences[max(0, mid - 1) : mid + 2]) + "."
    elif question_type == "inference" and len(sentences) >= 2:
        return ". ".join(sentences[-3:]) + "."
    else:
        return sentences[0] + "."


class QuestionExpert(BaseSubAgent):
    name = "question_expert"
    description = "题目生成、选项设计"

    async def execute(
        self, input: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        start = time.time()
        article = input.get("article", "")
        question_type = input.get("question_type", "detail")
        difficulty = input.get("difficulty", "L2")
        count = input.get("count", 3)

        questions: List[Dict[str, Any]] = []
        for _ in range(count):
            q = await self._generate_single_question(article, question_type, difficulty)
            questions.append(q)

        return {
            "questions": questions,
            "metadata": {
                "latency_ms": self._timed(start),
                "agent": self.name,
            },
        }

    async def _generate_single_question(
        self, article: str, question_type: str, difficulty: str
    ) -> Dict[str, Any]:
        anchor = _select_anchor(article, question_type)
        prompt = QUESTION_PROMPT.format(
            article_segment=anchor,
            question_type=question_type,
            difficulty=difficulty,
        )
        result = await self._call_llm(prompt)
        if not result:
            result = {
                "question": "",
                "options": {"A": "", "B": "", "C": "", "D": ""},
                "correct_answer": "A",
                "explanation": "",
                "evidence": "",
            }
        return result
