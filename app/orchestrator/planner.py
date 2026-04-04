"""Planner – uses an LLM to decompose a user request into a list of sub-tasks."""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.models.state import OrchestratorState, SubTask, SubTaskStatus
from app.services.llm_service import llm_json_call

logger = logging.getLogger(__name__)

PLANNING_PROMPT = """
你是ReadWise AI的主控Agent。你的职责是将用户请求拆解为可执行的子任务。

## 可用的Sub-agent
1. **diagnosis_expert**: 错因分析专家
   - 能力：分析错题原因、定位证据句、生成修复建议、生成同类题
   - 适用场景：学生做错了题需要分析、需要同类题训练

2. **corpus_expert**: 语料专家
   - 能力：
     a) 普通模式：按难度(L1-L4)、体裁(议论文/说明文/记叙文)、主题生成高考风格文章
     b) 总体规划模式（enable_planning=true）：读取整个语料库 + 学生错题/战力值，
        规划一组4篇文章的训练方案，返回 training_plan 并自动生成后续子任务
     c) 风格化模式（reference_id 指定真题ID）：以真题为参考风格生成文章
   - 适用场景：需要生成新文章、需要难度适配的阅读材料、需要生成完整训练题组

3. **question_expert**: 出题专家
   - 能力：基于文章生成题目、设计选项、生成答案
   - 适用场景：需要为文章配题、需要专项题型训练

4. **qa_expert**: 问答专家
   - 能力：通用专家、查词释义、长难句拆解、语法解释、翻译
   - 适用场景：学生提问单词/句子/语法

## 输出格式（严格JSON）
{
  "overall_goal": "任务总体目标",
  "sub_tasks": [
    {
      "sub_task_id": "sub_001",
      "assigned_to": "diagnosis_expert",
      "description": "具体要做什么",
      "input": {},
      "acceptance_criteria": ["验收标准1", "验收标准2"],
      "depends_on": []
    }
  ]
}

## 用户请求
{user_request}

## 上下文
{context}

请输出JSON格式的规划结果（只输出JSON，不要其他内容）：
"""


def _make_rule_based_plan(user_request: Dict[str, Any]) -> Dict[str, Any]:
    """Fast rule-based planning for well-known request types."""
    request_type = user_request.get("request_type", "attempt")

    if request_type == "attempt":
        return {
            "overall_goal": "分析错题并提供诊断与同类题",
            "sub_tasks": [
                {
                    "sub_task_id": "sub_001",
                    "assigned_to": "diagnosis_expert",
                    "description": "分析学生做错的题目，给出错因分析和同类题",
                    "input": {
                        "paragraph": user_request.get("paragraph", ""),
                        "question_text": user_request.get("question_text", ""),
                        "options": user_request.get("options", {}),
                        "user_answer": user_request.get("user_answer", ""),
                        "correct_answer": user_request.get("correct_answer", ""),
                        "time_spent": user_request.get("time_spent", 0),
                        "need_similar": True,
                    },
                    "acceptance_criteria": [
                        "包含 error_category 字段",
                        "包含 explanation 字段",
                    ],
                    "depends_on": [],
                }
            ],
        }

    if request_type == "corpus":
        return {
            "overall_goal": "生成指定难度和体裁的高考风格文章",
            "sub_tasks": [
                {
                    "sub_task_id": "sub_001",
                    "assigned_to": "corpus_expert",
                    "description": "生成文章",
                    "input": {
                        "difficulty": user_request.get("difficulty", "L2"),
                        "genre": user_request.get("genre", "expository"),
                        "topic": user_request.get("topic", ""),
                        "word_count": user_request.get("word_count", 300),
                        "reference_id": user_request.get("reference_id"),
                        "description": user_request.get("description", ""),
                    },
                    "acceptance_criteria": ["文章字数在目标范围内", "体裁符合要求"],
                    "depends_on": [],
                }
            ],
        }

    if request_type == "question":
        return {
            "overall_goal": "为给定文章生成题目",
            "sub_tasks": [
                {
                    "sub_task_id": "sub_001",
                    "assigned_to": "question_expert",
                    "description": "出题",
                    "input": {
                        "article": user_request.get("article", ""),
                        "question_type": user_request.get("question_type", "detail"),
                        "difficulty": user_request.get("difficulty", "L2"),
                        "count": user_request.get("count", 3),
                    },
                    "acceptance_criteria": ["题目数量符合要求", "答案在原文中有依据"],
                    "depends_on": [],
                }
            ],
        }

    if request_type == "qa":
        return {
            "overall_goal": "回答学生的语言问题",
            "sub_tasks": [
                {
                    "sub_task_id": "sub_001",
                    "assigned_to": "qa_expert",
                    "description": "解答问题",
                    "input": {
                        "query_type": user_request.get("query_type", "word"),
                        "content": user_request.get("content", ""),
                        "context_sentence": user_request.get("context_sentence", ""),
                    },
                    "acceptance_criteria": ["包含释义信息"],
                    "depends_on": [],
                }
            ],
        }

    if request_type == "training_set":
        return {
            "overall_goal": "生成完整训练题组（总体规划 → 语料生成 → 出题）",
            "sub_tasks": [
                {
                    "sub_task_id": "sub_000",
                    "assigned_to": "corpus_expert",
                    "description": (
                        "读取语料库和学生学情，规划本次训练4篇文章（主题、"
                        "参考真题、语法点、难度、字数等），返回训练计划并"
                        "生成语料+出题子任务"
                    ),
                    "input": {
                        "enable_planning": True,
                        "user_level": user_request.get("user_level", "L2"),
                    },
                    "acceptance_criteria": [
                        "包含 training_plan 字段",
                        "training_plan 包含文章规划",
                    ],
                    "depends_on": [],
                }
            ],
        }

    return {}


class Planner:
    async def plan(self, state: OrchestratorState) -> OrchestratorState:
        """Generate a task plan and store sub_tasks in state."""
        user_request = state.original_request

        # Try fast rule-based plan first
        plan = _make_rule_based_plan(user_request)

        if not plan:
            # Fall back to LLM
            prompt = PLANNING_PROMPT.format(
                user_request=str(user_request),
                context="",
            )
            plan = await llm_json_call(prompt)

        if not plan or "sub_tasks" not in plan:
            logger.error("Planner returned empty plan for %s", state.request_id)
            state.error_log.append("Planner failed to generate a plan")
            return state

        state.current_plan = plan
        state.sub_tasks = [SubTask(**st) for st in plan["sub_tasks"]]
        logger.info(
            "Planned %d sub-tasks for %s", len(state.sub_tasks), state.request_id
        )
        return state

    async def replan(
        self, state: OrchestratorState, failed_task: "SubTask"  # noqa: F821
    ) -> OrchestratorState:
        """Adjust input for a failed task and mark it for retry."""
        feedback = state.error_log[-1] if state.error_log else "unknown error"

        prompt = f"""
之前的任务失败了，需要调整输入后重试。

## 原任务
{failed_task.description}

## 原输入
{failed_task.input}

## 失败原因
{feedback}

## 请输出调整后的输入（严格JSON格式，只输出JSON）
"""
        adjusted = await llm_json_call(prompt)
        if adjusted:
            failed_task.input = adjusted
        failed_task.status = SubTaskStatus.PENDING
        failed_task.retry_count += 1
        return state
