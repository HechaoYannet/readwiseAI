"""QAExpert – 查词、长难句拆解、语法解释、翻译."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict

from app.sub_agents.base import BaseSubAgent
from app.tools.dictionary import lookup_word

logger = logging.getLogger(__name__)

SENTENCE_PARSE_PROMPT = """
你是英语语言学专家。请拆解以下英语长难句的句子结构。

## 句子
{sentence}

## 输出格式（严格JSON，只输出JSON）
{{
  "main_clause": "主句",
  "subordinate_clauses": ["从句1", "从句2"],
  "translation": "中文翻译",
  "structure_analysis": "句子结构分析",
  "key_grammar_points": ["语法点1", "语法点2"]
}}
"""

GRAMMAR_PROMPT = """
你是英语语法专家。请解释以下语法现象。

## 语法问题
{grammar_query}

## 输出格式（严格JSON，只输出JSON）
{{
  "grammar_point": "语法要点名称",
  "explanation": "详细解释",
  "examples": ["例句1", "例句2"],
  "common_mistakes": ["常见错误1"]
}}
"""

TRANSLATE_PROMPT = """
请将以下英文翻译成地道的中文。

## 原文
{content}

## 输出格式（严格JSON，只输出JSON）
{{
  "translation": "中文翻译",
  "notes": "翻译说明（可选）"
}}
"""


class QAExpert(BaseSubAgent):
    name = "qa_expert"
    description = "查词、长难句拆解、语法解释、翻译"

    async def execute(
        self, input: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        start = time.time()
        query_type = input.get("query_type", "word")
        content = input.get("content", "")
        context_sentence = input.get("context_sentence", "")

        if query_type == "word":
            result = await self._handle_word(content, context_sentence)
        elif query_type == "sentence":
            result = await self._handle_sentence(content)
        elif query_type == "grammar":
            result = await self._handle_grammar(content)
        elif query_type == "translate":
            result = await self._handle_translate(content)
        else:
            result = {"error": f"Unknown query_type: {query_type}"}

        result["metadata"] = {"latency_ms": self._timed(start), "agent": self.name}
        return result

    async def _handle_word(self, word: str, ctx: str) -> Dict[str, Any]:
        basic = await lookup_word(word)
        if ctx:
            extra = await self._call_llm(
                f"单词'{word}'在以下上下文中的具体含义是什么？\n上下文：{ctx}\n基础释义：{basic}\n"
                f"输出JSON：{{\"context_meaning\": \"...\", \"usage_notes\": \"...\"}}"
            )
            return {
                "word": word,
                "basic_meaning": basic,
                "context_meaning": extra.get("context_meaning", ""),
                "usage_notes": extra.get("usage_notes", ""),
            }
        return {"word": word, "basic_meaning": basic}

    async def _handle_sentence(self, sentence: str) -> Dict[str, Any]:
        prompt = SENTENCE_PARSE_PROMPT.format(sentence=sentence)
        result = await self._call_llm(prompt)
        return result or {"error": "解析失败"}

    async def _handle_grammar(self, query: str) -> Dict[str, Any]:
        prompt = GRAMMAR_PROMPT.format(grammar_query=query)
        result = await self._call_llm(prompt)
        return result or {"error": "解释失败"}

    async def _handle_translate(self, content: str) -> Dict[str, Any]:
        prompt = TRANSLATE_PROMPT.format(content=content)
        result = await self._call_llm(prompt)
        return result or {"error": "翻译失败"}
