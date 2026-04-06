import json
from pathlib import Path
from typing import List, Optional



def _pop_save(session_id: str, session_type: str) -> None:
    """Helper to maintain a single most recent session ID in _session.json."""

    session_list = load_session_list(session_type)
    if (not session_list) or (session_list[0] != session_id):
        if session_id in session_list:
            session_list.remove(session_id)  # 删除第一个匹配项
            session_list.insert(0, session_id)  # 插入到开头
        else:
            session_list.insert(0, session_id)  # 插入到开头
    if not session_list: session_list.append(session_id)
    path: Path = Path("tests")
    if session_type == "training":
        path = path / f"_session.json"
    elif session_type == "chatting":
        path = path / f"_session_chat.json"
    path.write_text(json.dumps(session_list, indent=2, ensure_ascii=False), encoding="utf-8")

def load_session_list(session_type: str, user_id: str = "default") -> List[str]:
        """List all session IDs for a given user."""
        path: Path = Path("tests")
        if session_type == "training":
            path = path / f"_session.json"
        elif session_type == "chatting":
            path = path / f"_session_chat.json"
        if not path.exists():
            return []
        try:
            session_id = json.loads(path.read_text(encoding="utf-8"))
            if session_id:
                return session_id
            return []
        except Exception as exc:
            print(f"Failed to load session list for user {user_id}: {exc}")
            return []

def test_pop_save():
    _pop_save("session1", "training")
    assert load_session_list("training") == ["session1"]
    _pop_save("session2", "training")
    assert load_session_list("training") == ["session2", "session1"]
    _pop_save("session1", "training")
    assert load_session_list("training") == ["session1", "session2"]
def test_pop_save_chatting():
    _pop_save("sessionA", "chatting")
    assert load_session_list("chatting") == ["sessionA"]
    _pop_save("sessionB", "chatting")
    assert load_session_list("chatting") == ["sessionB", "sessionA"]
    _pop_save("sessionA", "chatting")
    assert load_session_list("chatting") == ["sessionA", "sessionB"]
def test_write_and_load():
    (Path("tests")/f"_session.json").write_text("123")