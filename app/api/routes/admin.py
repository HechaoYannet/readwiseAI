"""管理员后台 API."""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from app.auth.dependencies import get_admin_user
from app.auth.models import TokenData
from app.models.user import UserRole, UserStatus, UserStore
from app.models.working_memory import WorkingMemory
from app.models import working_memory as wm_module
from app.services import llm_service, user_service

router = APIRouter(prefix="/admin", tags=["admin"])

_SAFE_ID_PATTERN = re.compile(r"^[\w\-]+$")
_SAFE_INVITE_PATTERN = re.compile(r"^[A-Z0-9]{6,32}$")
_ALLOWED_PROVIDERS = {"", "openai", "deepseek", "stub"}
_MAX_PAGE_LIMIT = 200
_MAX_NOTE_LEN = 200
_MAX_MODEL_LEN = 100
_MAX_BASE_URL_LEN = 200


def _require_safe_id(value: str, field_name: str) -> str:
    if not _SAFE_ID_PATTERN.match(value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} 包含非法字符",
        )
    return value


def _sanitize_user(user: Any) -> Dict[str, Any]:
    data = user.model_dump()
    data.pop("password_hash", None)
    return data


def _sanitize_invite(invite: Any) -> Dict[str, Any]:
    data = invite.model_dump()
    data["is_valid"] = invite.is_valid()
    return data


def _list_session_files(user_id: str) -> List[Path]:
    user_dir = wm_module._safe_user_dir(wm_module._SESSIONS_DIR, user_id)
    if not user_dir.exists():
        return []
    files: List[Path] = []
    for path in user_dir.glob("*.json"):
        if path.name.startswith("_session"):
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.stat().st_mtime, reverse=True)


def _remove_session_from_indexes(user_id: str, session_id: str) -> None:
    for session_type in ("training", "chatting"):
        ids = WorkingMemory.load_session_list(session_type=session_type, user_id=user_id)
        if session_id in ids:
            ids = [item for item in ids if item != session_id]
            user_dir = wm_module._safe_user_dir(wm_module._SESSIONS_DIR, user_id)
            list_file = user_dir / ("_session.json" if session_type == "training" else "_session_chat.json")
            list_file.write_text(json.dumps(ids, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_session_for_admin(user_id: str, session_id: str) -> WorkingMemory:
    _require_safe_id(user_id, "user_id")
    _require_safe_id(session_id, "session_id")
    wm = WorkingMemory.load(session_id=session_id, user_id=user_id)
    if wm is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return wm


class AdminUserUpdateRequest(BaseModel):
    username: Optional[str] = Field(default=None, min_length=1, max_length=50)
    exam_region: Optional[str] = Field(default=None, min_length=1, max_length=50)
    grade: Optional[str] = Field(default=None, max_length=50)
    school: Optional[str] = Field(default=None, max_length=100)
    status: Optional[Literal["active", "disabled"]] = None
    role: Optional[Literal["user", "admin"]] = None


class InviteCreateRequest(BaseModel):
    max_uses: int = Field(default=1, ge=1, le=1000)
    note: str = Field(default="", max_length=_MAX_NOTE_LEN)
    expires_at: Optional[str] = Field(default=None, max_length=64)

    @field_validator("expires_at")
    @classmethod
    def validate_expires_at(cls, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        try:
            datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("expires_at 必须为 ISO 时间格式") from exc
        return value


class LLMConfigUpdateRequest(BaseModel):
    provider: Literal["openai", "deepseek", "stub"]
    model: Optional[str] = Field(default=None, min_length=1, max_length=_MAX_MODEL_LEN)
    temperature: Optional[float] = Field(default=None, ge=0, le=2)
    base_url: Optional[str] = Field(default=None, max_length=_MAX_BASE_URL_LEN)
    api_key: Optional[str] = Field(default=None, min_length=1, max_length=300)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: Optional[str]) -> Optional[str]:
        if value in (None, ""):
            return None
        if not (value.startswith("https://") or value.startswith("http://localhost") or value.startswith("http://127.0.0.1")):
            raise ValueError("base_url 仅允许 https 或本地调试地址")
        return value.rstrip("/")


@router.get("/users", summary="管理员获取用户列表")
async def admin_list_users(
    status_filter: Optional[Literal["active", "disabled"]] = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=_MAX_PAGE_LIMIT),
    _: TokenData = Depends(get_admin_user),
) -> Dict[str, Any]:
    users = user_service.list_users(status=status_filter, limit=limit)
    return {"count": len(users), "users": [_sanitize_user(user) for user in users]}


@router.get("/users/{user_id}", summary="管理员获取用户详情")
async def admin_get_user(
    user_id: str,
    _: TokenData = Depends(get_admin_user),
) -> Dict[str, Any]:
    _require_safe_id(user_id, "user_id")
    user = user_service.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return _sanitize_user(user)


@router.patch("/users/{user_id}", summary="管理员更新用户")
async def admin_update_user(
    user_id: str,
    payload: AdminUserUpdateRequest,
    admin: TokenData = Depends(get_admin_user),
) -> Dict[str, Any]:
    _require_safe_id(user_id, "user_id")
    existing = user_service.get_user(user_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    updates = payload.model_dump(exclude_none=True)
    role_value = updates.pop("role", None)
    status_value = updates.pop("status", None)

    if role_value is not None:
        if user_id == admin.user_id and role_value != UserRole.ADMIN.value:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能降级当前管理员自身权限")
        updated_role = UserStore().update(user_id, role=role_value)
        if updated_role is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    if status_value is not None:
        if user_id == admin.user_id and status_value != UserStatus.ACTIVE.value:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能禁用当前管理员自身账号")
        ok = user_service.enable_user(user_id) if status_value == UserStatus.ACTIVE.value else user_service.disable_user(user_id)
        if not ok:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    if updates:
        updated = user_service.update_user(user_id, **updates)
        if updated is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名已被占用或更新失败")

    user = user_service.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return _sanitize_user(user)


@router.delete("/users/{user_id}", summary="管理员删除用户")
async def admin_delete_user(
    user_id: str,
    admin: TokenData = Depends(get_admin_user),
) -> Dict[str, Any]:
    _require_safe_id(user_id, "user_id")
    if user_id == admin.user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能删除当前管理员自身账号")
    existing = user_service.get_user(user_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    if not user_service.delete_user(user_id):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="删除用户失败")

    try:
        user_dir = wm_module._safe_user_dir(wm_module._SESSIONS_DIR, user_id)
        if user_dir.exists():
            shutil.rmtree(user_dir)
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="用户已删除，但清理会话数据失败")

    return {"message": "用户已删除", "user_id": user_id}


@router.get("/users/{user_id}/sessions", summary="管理员获取指定用户会话列表")
async def admin_list_user_sessions(
    user_id: str,
    limit: int = Query(default=50, ge=1, le=_MAX_PAGE_LIMIT),
    _: TokenData = Depends(get_admin_user),
) -> Dict[str, Any]:
    _require_safe_id(user_id, "user_id")
    if user_service.get_user(user_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    sessions = []
    for path in _list_session_files(user_id)[:limit]:
        wm = WorkingMemory.load(path.stem, user_id=user_id)
        if wm is None:
            continue
        sessions.append(
            {
                "session_id": wm.session_id,
                "session_type": wm.session_type,
                "created_at": wm.created_at,
                "updated_at": wm.updated_at,
                "article_count": len(wm.articles),
                "message_count": len(wm.conversation_history),
                "agent_info_count": len(wm.agent_information),
            }
        )
    return {"user_id": user_id, "count": len(sessions), "sessions": sessions}


@router.get("/users/{user_id}/sessions/{session_id}", summary="管理员获取会话详情")
async def admin_get_user_session(
    user_id: str,
    session_id: str,
    _: TokenData = Depends(get_admin_user),
) -> Dict[str, Any]:
    wm = _load_session_for_admin(user_id, session_id)
    return wm.model_dump()


@router.get("/users/{user_id}/sessions/{session_id}/history", summary="管理员获取会话历史")
async def admin_get_user_session_history(
    user_id: str,
    session_id: str,
    limit: int = Query(default=40, ge=1, le=_MAX_PAGE_LIMIT),
    _: TokenData = Depends(get_admin_user),
) -> Dict[str, Any]:
    wm = _load_session_for_admin(user_id, session_id)
    history = wm.conversation_history[-limit:]
    return {
        "user_id": user_id,
        "session_id": session_id,
        "total_messages": len(wm.conversation_history),
        "returned": len(history),
        "history": history,
    }


@router.delete("/users/{user_id}/sessions/{session_id}", summary="管理员删除指定用户会话")
async def admin_delete_user_session(
    user_id: str,
    session_id: str,
    _: TokenData = Depends(get_admin_user),
) -> Dict[str, Any]:
    _load_session_for_admin(user_id, session_id)
    try:
        user_dir = wm_module._safe_user_dir(wm_module._SESSIONS_DIR, user_id)
        session_file = user_dir / f"{session_id}.json"
        if session_file.exists():
            session_file.unlink()
        _remove_session_from_indexes(user_id, session_id)
        return {"message": "会话已删除", "user_id": user_id, "session_id": session_id}
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="删除会话失败")


@router.get("/invites", summary="管理员获取邀请码列表")
async def admin_list_invites(
    limit: int = Query(default=100, ge=1, le=_MAX_PAGE_LIMIT),
    _: TokenData = Depends(get_admin_user),
) -> Dict[str, Any]:
    invites = user_service.list_invites()[:limit]
    return {"count": len(invites), "invites": [_sanitize_invite(invite) for invite in invites]}


@router.post("/invites", summary="管理员创建邀请码")
async def admin_create_invite(
    payload: InviteCreateRequest,
    admin: TokenData = Depends(get_admin_user),
) -> Dict[str, Any]:
    invite = user_service.create_invite(
        max_uses=payload.max_uses,
        note=payload.note,
        expires_at=payload.expires_at,
        created_by=admin.user_id,
    )
    return _sanitize_invite(invite)


@router.get("/invites/{code}", summary="管理员获取邀请码详情")
async def admin_get_invite(
    code: str,
    _: TokenData = Depends(get_admin_user),
) -> Dict[str, Any]:
    if not _SAFE_INVITE_PATTERN.match(code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邀请码格式非法")
    invite = user_service.get_invite(code)
    if invite is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="邀请码不存在")
    return _sanitize_invite(invite)


@router.post("/invites/{code}/revoke", summary="管理员撤销邀请码")
async def admin_revoke_invite(
    code: str,
    _: TokenData = Depends(get_admin_user),
) -> Dict[str, Any]:
    if not _SAFE_INVITE_PATTERN.match(code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邀请码格式非法")
    if not user_service.revoke_invite(code):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="邀请码不存在")
    invite = user_service.get_invite(code)
    return _sanitize_invite(invite)


@router.get("/llm-config", summary="管理员查看 LLM 配置")
async def admin_get_llm_config(
    _: TokenData = Depends(get_admin_user),
) -> Dict[str, Any]:
    return llm_service.get_public_runtime_llm_config()


@router.put("/llm-config", summary="管理员更新 LLM 配置")
async def admin_update_llm_config(
    payload: LLMConfigUpdateRequest,
    _: TokenData = Depends(get_admin_user),
) -> Dict[str, Any]:
    if payload.provider not in _ALLOWED_PROVIDERS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的 provider")
    llm_service.update_runtime_llm_config(
        provider=payload.provider,
        model=payload.model,
        temperature=payload.temperature,
        base_url=payload.base_url,
        api_key=payload.api_key,
    )
    return llm_service.get_public_runtime_llm_config()
