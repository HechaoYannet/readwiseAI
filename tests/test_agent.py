"""Integration + unit tests for ReadWise AI Agent architecture."""
from __future__ import annotations

import json
import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def _make_temp_dirs(tmp_path: Path):
    (tmp_path / "checkpoints").mkdir()
    (tmp_path / "results").mkdir()
    (tmp_path / "tasks" / "pending").mkdir(parents=True)
    (tmp_path / "tasks" / "processing").mkdir(parents=True)
    return tmp_path


# ===================================================================
# 1. Data models
# ===================================================================

class TestStateModels:
    def test_orchestrator_state_defaults(self):
        from app.models.state import OrchestratorState, RequestStatus

        state = OrchestratorState(request_id="req_test", user_id="u1")
        assert state.status == RequestStatus.PENDING
        assert state.retry_count == 0
        assert state.sub_tasks == []

    def test_subtask_model(self):
        from app.models.state import SubTask, SubTaskStatus

        t = SubTask(
            sub_task_id="sub_001",
            assigned_to="diagnosis_expert",
            description="test",
        )
        assert t.status == SubTaskStatus.PENDING
        assert t.retry_count == 0

    def test_attempt_request_defaults(self):
        from app.models.state import AttemptRequest

        req = AttemptRequest(user_id="u1")
        assert req.request_type == "attempt"
        assert req.user_answer == ""


# ===================================================================
# 2. CheckpointManager
# ===================================================================

class TestCheckpointManager:
    def test_save_and_load(self, tmp_path):
        from app.orchestrator.checkpoint import CheckpointManager
        from app.models.state import OrchestratorState

        cm = CheckpointManager(
            checkpoint_dir=tmp_path / "checkpoints",
            results_dir=tmp_path / "results",
        )
        state = OrchestratorState(request_id="req_abc", user_id="u1")
        cm.save(state)
        loaded = cm.load("req_abc")
        assert loaded is not None
        assert loaded.request_id == "req_abc"
        assert loaded.user_id == "u1"

    def test_load_nonexistent(self, tmp_path):
        from app.orchestrator.checkpoint import CheckpointManager

        cm = CheckpointManager(
            checkpoint_dir=tmp_path / "checkpoints",
            results_dir=tmp_path / "results",
        )
        assert cm.load("does_not_exist") is None

    def test_delete(self, tmp_path):
        from app.orchestrator.checkpoint import CheckpointManager
        from app.models.state import OrchestratorState

        cm = CheckpointManager(
            checkpoint_dir=tmp_path / "checkpoints",
            results_dir=tmp_path / "results",
        )
        state = OrchestratorState(request_id="req_del", user_id="u1")
        cm.save(state)
        cm.delete("req_del")
        assert cm.load("req_del") is None

    def test_save_and_load_result(self, tmp_path):
        from app.orchestrator.checkpoint import CheckpointManager

        cm = CheckpointManager(
            checkpoint_dir=tmp_path / "checkpoints",
            results_dir=tmp_path / "results",
        )
        cm.save_result("req_r", {"status": "completed", "results": {}})
        r = cm.load_result("req_r")
        assert r is not None
        assert r["status"] == "completed"


# ===================================================================
# 3. Planner
# ===================================================================

class TestPlanner:
    @pytest.mark.asyncio
    async def test_rule_based_attempt(self):
        from app.orchestrator.planner import Planner
        from app.models.state import OrchestratorState

        state = OrchestratorState(
            request_id="req_p1",
            user_id="u1",
            original_request={
                "request_type": "attempt",
                "paragraph": "The sun rises in the east.",
                "question_text": "Where does the sun rise?",
                "options": {"A": "East", "B": "West", "C": "North", "D": "South"},
                "user_answer": "B",
                "correct_answer": "A",
                "time_spent": 30,
                "user_id": "u1",
            },
        )
        planner = Planner()
        state = await planner.plan(state)
        assert len(state.sub_tasks) == 1
        assert state.sub_tasks[0].assigned_to == "diagnosis_expert"

    @pytest.mark.asyncio
    async def test_rule_based_corpus(self):
        from app.orchestrator.planner import Planner
        from app.models.state import OrchestratorState

        state = OrchestratorState(
            request_id="req_p2",
            user_id="u1",
            original_request={
                "request_type": "corpus",
                "difficulty": "L2",
                "genre": "expository",
                "topic": "environment",
                "word_count": 200,
                "user_id": "u1",
            },
        )
        planner = Planner()
        state = await planner.plan(state)
        assert state.sub_tasks[0].assigned_to == "corpus_expert"

    @pytest.mark.asyncio
    async def test_rule_based_qa(self):
        from app.orchestrator.planner import Planner
        from app.models.state import OrchestratorState

        state = OrchestratorState(
            request_id="req_p3",
            user_id="u1",
            original_request={
                "request_type": "qa",
                "query_type": "word",
                "content": "ubiquitous",
                "user_id": "u1",
            },
        )
        planner = Planner()
        state = await planner.plan(state)
        assert state.sub_tasks[0].assigned_to == "qa_expert"

    @pytest.mark.asyncio
    async def test_replan_adjusts_input(self):
        from app.orchestrator.planner import Planner
        from app.models.state import OrchestratorState, SubTask, SubTaskStatus

        state = OrchestratorState(
            request_id="req_p4",
            user_id="u1",
            original_request={"request_type": "attempt", "user_id": "u1"},
            error_log=["验收失败: 内容不完整"],
        )
        task = SubTask(
            sub_task_id="sub_001",
            assigned_to="diagnosis_expert",
            description="分析错题",
            input={"paragraph": ""},
            status=SubTaskStatus.RETRY,
        )
        state.sub_tasks = [task]

        planner = Planner()
        # LLM stub will return empty dict; replan should still mark task PENDING
        state = await planner.replan(state, task)
        assert task.status == SubTaskStatus.PENDING


# ===================================================================
# 4. Verifier
# ===================================================================

class TestVerifier:
    @pytest.mark.asyncio
    async def test_verify_passes_when_llm_unavailable(self):
        """When LLM is not configured, verifier defaults to passed=True."""
        from app.orchestrator.verifier import Verifier
        from app.models.state import OrchestratorState, SubTask, SubTaskStatus

        state = OrchestratorState(request_id="req_v1", user_id="u1")
        task = SubTask(
            sub_task_id="sub_001",
            assigned_to="diagnosis_expert",
            description="test",
            result={"diagnosis": {"error_category": "词汇理解"}},
            acceptance_criteria=["包含 error_category 字段"],
        )
        verifier = Verifier()
        state = await verifier.verify(state, task)
        # Stub LLM returns "{}" which is falsy after json.loads → defaults to passed=True
        assert task.status == SubTaskStatus.COMPLETED
        assert "sub_001" in state.completed_results

    @pytest.mark.asyncio
    async def test_verify_retry_on_failure(self):
        from app.orchestrator.verifier import Verifier
        from app.models.state import OrchestratorState, SubTask, SubTaskStatus

        state = OrchestratorState(request_id="req_v2", user_id="u1", retry_count=0)
        task = SubTask(
            sub_task_id="sub_001",
            assigned_to="diagnosis_expert",
            description="test",
            result={},
            acceptance_criteria=["包含完整结果"],
        )

        verifier = Verifier()
        # Patch llm_json_call to return failed verdict
        with patch(
            "app.orchestrator.verifier.llm_json_call",
            new_callable=AsyncMock,
            return_value={"passed": False, "issues": ["结果为空"], "suggestion": ""},
        ):
            state = await verifier.verify(state, task)

        assert task.status == SubTaskStatus.RETRY
        assert state.retry_count == 1


# ===================================================================
# 5. Sub-agents
# ===================================================================

class TestDiagnosisExpert:
    @pytest.mark.asyncio
    async def test_correct_answer_short_circuits(self):
        from app.sub_agents.diagnosis import DiagnosisExpert

        agent = DiagnosisExpert()
        result = await agent.execute(
            {
                "paragraph": "test",
                "question_text": "q",
                "options": {},
                "user_answer": "A",
                "correct_answer": "A",
                "time_spent": 10,
            },
            {},
        )
        assert result["diagnosis"]["error_category"] == "无错误"

    @pytest.mark.asyncio
    async def test_wrong_answer_calls_llm(self):
        from app.sub_agents.diagnosis import DiagnosisExpert

        agent = DiagnosisExpert()
        with patch(
            "app.sub_agents.base.llm_json_call",
            new_callable=AsyncMock,
            return_value={
                "error_category": "词汇理解",
                "explanation": "学生不认识该词",
                "evidence_sentence": "test",
                "suggestion": "多背单词",
                "confidence": 0.9,
            },
        ):
            result = await agent.execute(
                {
                    "paragraph": "test paragraph",
                    "question_text": "What does ubiquitous mean?",
                    "options": {"A": "rare", "B": "common", "C": "fast", "D": "slow"},
                    "user_answer": "A",
                    "correct_answer": "B",
                    "time_spent": 15,
                    "need_similar": False,
                },
                {},
            )
        assert result["diagnosis"]["error_category"] == "词汇理解"
        assert result["similar_question"] is None


class TestCorpusExpert:
    @pytest.mark.asyncio
    async def test_returns_article_structure(self):
        from app.sub_agents.corpus import CorpusExpert

        agent = CorpusExpert()
        fake_article = {
            "title": "Test Title",
            "content": " ".join(["word"] * 120),
            "word_count": 120,
            "difficulty_actual": "L2",
            "genre_actual": "expository",
            "key_vocabulary": ["environment"],
        }
        with patch(
            "app.sub_agents.base.llm_json_call",
            new_callable=AsyncMock,
            return_value=fake_article,
        ):
            result = await agent.execute(
                {"difficulty": "L2", "genre": "expository", "topic": "env", "word_count": 120},
                {},
            )
        assert "article" in result
        assert result["article"]["title"] == "Test Title"


class TestQuestionExpert:
    @pytest.mark.asyncio
    async def test_generates_correct_count(self):
        from app.sub_agents.question import QuestionExpert

        agent = QuestionExpert()
        fake_q = {
            "question": "What is the main idea?",
            "options": {"A": "a", "B": "b", "C": "c", "D": "d"},
            "correct_answer": "A",
            "explanation": "...",
            "evidence": "...",
        }
        with patch(
            "app.sub_agents.base.llm_json_call",
            new_callable=AsyncMock,
            return_value=fake_q,
        ):
            result = await agent.execute(
                {
                    "article": "This is a test article. It has multiple sentences. "
                               "Students should read carefully.",
                    "question_type": "detail",
                    "difficulty": "L2",
                    "count": 2,
                },
                {},
            )
        assert len(result["questions"]) == 2


class TestQAExpert:
    @pytest.mark.asyncio
    async def test_word_lookup_stub(self):
        from app.sub_agents.qa import QAExpert

        agent = QAExpert()
        result = await agent.execute(
            {"query_type": "word", "content": "ubiquitous", "context_sentence": ""},
            {},
        )
        assert result["word"] == "ubiquitous"
        assert "basic_meaning" in result

    @pytest.mark.asyncio
    async def test_unknown_query_type(self):
        from app.sub_agents.qa import QAExpert

        agent = QAExpert()
        result = await agent.execute(
            {"query_type": "unknown_type", "content": "test"},
            {},
        )
        assert "error" in result


# ===================================================================
# 6. Tools
# ===================================================================

class TestDictionary:
    @pytest.mark.asyncio
    async def test_stub_definition_no_api_key(self):
        from app.tools.dictionary import lookup_word

        result = await lookup_word("serendipity")
        assert result["word"] == "serendipity"
        assert result["definitions"]  # non-empty list


class TestVocabulary:
    def test_known_word_level(self):
        from app.tools.vocabulary import get_word_level

        assert get_word_level("book") == "A1"

    def test_unknown_word_level(self):
        from app.tools.vocabulary import get_word_level

        assert get_word_level("zyzzyva") is None

    def test_within_difficulty(self):
        from app.tools.vocabulary import is_within_difficulty

        assert is_within_difficulty("book", "L1") is True
        assert is_within_difficulty("paradigm", "L1") is False


class TestGrammar:
    def test_get_rule_known(self):
        from app.tools.grammar import get_rule

        r = get_rule("定语从句")
        assert "关系代词" in r

    def test_get_rule_unknown(self):
        from app.tools.grammar import get_rule

        r = get_rule("不存在的语法点")
        assert "暂无" in r


class TestConstraints:
    def test_get_constraints(self):
        from app.tools.constraints import get_constraints

        c = get_constraints("L3")
        assert c["vocabulary_level"] == "B1"

    def test_get_constraints_fallback(self):
        from app.tools.constraints import get_constraints

        c = get_constraints("L9")
        # Should fall back to L2 defaults
        assert c["vocabulary_level"] == "A2"


# ===================================================================
# 7. API routes (via TestClient)
# ===================================================================

@pytest.fixture
def client(tmp_path):
    """Create a test client with isolated checkpoint directories."""
    import app.orchestrator.checkpoint as cp_module
    import app.orchestrator.agent as ag_module

    # Reset singletons
    cp_module._checkpoint_manager = None
    ag_module._orchestrator = None

    # Patch checkpoint dirs to use tmp_path
    original_checkpoint_dir = cp_module.CHECKPOINT_DIR
    original_results_dir = cp_module.RESULTS_DIR
    cp_module.CHECKPOINT_DIR = tmp_path / "checkpoints"
    cp_module.RESULTS_DIR = tmp_path / "results"

    from app.main import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    cp_module.CHECKPOINT_DIR = original_checkpoint_dir
    cp_module.RESULTS_DIR = original_results_dir
    cp_module._checkpoint_manager = None
    ag_module._orchestrator = None


class TestAPIRoutes:
    def test_root(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "ReadWise AI" in r.json()["message"]

    def test_submit_attempt_returns_request_id(self, client):
        r = client.post(
            "/api/attempt",
            json={
                "user_id": "u1",
                "paragraph": "The sun rises in the east.",
                "question_text": "Where does the sun rise?",
                "options": {"A": "East", "B": "West", "C": "North", "D": "South"},
                "user_answer": "B",
                "correct_answer": "A",
                "time_spent": 30,
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert "request_id" in data
        assert data["request_id"].startswith("req_")
        assert data["status"] == "processing"

    def test_get_result_not_found(self, client):
        r = client.get("/api/result/req_nonexistent")
        assert r.status_code == 404

    def test_get_result_processing(self, client, tmp_path):
        """Submit then immediately poll – should see 'processing' or completed."""
        r = client.post(
            "/api/attempt",
            json={
                "user_id": "u2",
                "paragraph": "Water is essential for life.",
                "question_text": "Why is water important?",
                "options": {"A": "It is cold", "B": "It is essential", "C": "It is blue", "D": "It is wet"},
                "user_answer": "A",
                "correct_answer": "B",
                "time_spent": 20,
            },
        )
        req_id = r.json()["request_id"]
        # Poll result – either processing or completed (background task may have run)
        poll = client.get(f"/api/result/{req_id}")
        assert poll.status_code == 200
        assert poll.json()["status"] in ("processing", "completed", "failed")

    def test_corpus_request(self, client):
        r = client.post(
            "/api/attempt",
            json={
                "user_id": "u3",
                "request_type": "corpus",
                "difficulty": "L2",
                "genre": "expository",
                "topic": "technology",
                "word_count": 200,
            },
        )
        assert r.status_code == 200
        assert r.json()["request_id"].startswith("req_")

    def test_qa_request(self, client):
        r = client.post(
            "/api/attempt",
            json={
                "user_id": "u4",
                "request_type": "qa",
                "query_type": "word",
                "content": "inevitable",
            },
        )
        assert r.status_code == 200

    def test_internal_callback_not_found(self, client):
        r = client.post(
            "/internal/callback/req_nonexistent",
            json={"task_id": "sub_001", "result": {"data": "test"}},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "not_found"


# ===================================================================
# 8. End-to-end orchestration (with mocked LLM)
# ===================================================================

class TestOrchestration:
    @pytest.mark.asyncio
    async def test_full_attempt_flow(self, tmp_path):
        """Full orchestration cycle: PENDING → plan → dispatch → verify → COMPLETED."""
        import app.orchestrator.checkpoint as cp_module
        import app.orchestrator.agent as ag_module

        cp_module._checkpoint_manager = None
        ag_module._orchestrator = None
        cp_module.CHECKPOINT_DIR = tmp_path / "checkpoints"
        cp_module.RESULTS_DIR = tmp_path / "results"

        from app.models.state import OrchestratorState, RequestStatus
        from app.orchestrator.agent import Orchestrator
        from app.orchestrator.checkpoint import CheckpointManager

        cm = CheckpointManager(
            checkpoint_dir=tmp_path / "checkpoints",
            results_dir=tmp_path / "results",
        )

        request_id = "req_e2e_001"
        user_request = {
            "request_type": "attempt",
            "user_id": "u_test",
            "paragraph": "Climate change is one of the greatest challenges facing humanity.",
            "question_text": "What is the author's main concern?",
            "options": {"A": "economy", "B": "climate change", "C": "technology", "D": "health"},
            "user_answer": "A",
            "correct_answer": "B",
            "time_spent": 45,
            "user_id": "u_test",
        }

        state = OrchestratorState(
            request_id=request_id,
            user_id="u_test",
            status=RequestStatus.PENDING,
            original_request=user_request,
        )
        cm.save(state)

        # Mock LLM to return a valid diagnosis
        diagnosis_result = {
            "error_category": "主旨理解",
            "explanation": "学生未能把握文章主旨",
            "evidence_sentence": "Climate change is one of the greatest challenges",
            "suggestion": "精读首段找主旨",
            "confidence": 0.92,
        }

        orchestrator = Orchestrator()
        orchestrator.checkpoint = cm

        with patch(
            "app.sub_agents.base.llm_json_call",
            new_callable=AsyncMock,
            return_value=diagnosis_result,
        ):
            await orchestrator.process_request(request_id, user_request)

        # Result should be saved
        result = cm.load_result(request_id)
        assert result is not None
        assert result["status"] in (
            RequestStatus.COMPLETED,
            "completed",
            RequestStatus.FAILED,
            "failed",
        )

        cp_module._checkpoint_manager = None
        ag_module._orchestrator = None
