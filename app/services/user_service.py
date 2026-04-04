"""User service layer – business logic for user management."""
from __future__ import annotations
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.models.invite import InviteCode, InviteStore
from app.models.user import User, UserStatus, UserStore

logger = logging.getLogger(__name__)

_user_store = UserStore()
_invite_store = InviteStore()


def verify_invite_code(code: str) -> Tuple[bool, str]:
    """Check if an invite code is valid.

    Returns:
        (is_valid, message)
    """
    invite = _invite_store.get_by_code(code)
    if invite is None:
        return False, "邀请码不存在"
    if not invite.is_valid():
        if invite.revoked:
            return False, "邀请码已被撤销"
        if invite.used_count >= invite.max_uses:
            return False, "邀请码已达到最大使用次数"
        return False, "邀请码已过期"
    return True, "邀请码有效"


def register_user(
    invite_code: str,
    username: str,
    exam_region: str,
    grade: str = "",
    school: str = "",
    client_ip: str = "",
) -> Tuple[Optional[User], str]:
    """Register a new user with an invite code.

    Returns:
        (user, error_message) – user is None if registration failed.
    """
    valid, msg = verify_invite_code(invite_code)
    if not valid:
        return None, msg

    # Check username uniqueness
    if _user_store.get_by_username(username) is not None:
        return None, "用户名已被占用"

    user = User(
        username=username,
        invite_code=invite_code,
        exam_region=exam_region,
        grade=grade,
        school=school,
        last_login_ip=client_ip,
    )
    _user_store.create(user)

    # Record invite use
    _invite_store.record_use(invite_code, user.id)

    # Initialize long-term memory directory
    try:
        from app.models.long_term_memory import LongTermMemory
        LongTermMemory(user_id=user.id)
    except Exception as exc:
        logger.warning("Could not init long-term memory for %s: %s", user.id, exc)

    return user, ""


def get_user(user_id: str) -> Optional[User]:
    return _user_store.get_by_id(user_id)


def update_user(user_id: str, **kwargs: Any) -> Optional[User]:
    """Update allowed user fields."""
    allowed = {"username", "exam_region", "grade", "school"}
    filtered = {k: v for k, v in kwargs.items() if k in allowed}
    if not filtered:
        return get_user(user_id)
    # Check username uniqueness if being changed
    if "username" in filtered:
        existing = _user_store.get_by_username(filtered["username"])
        if existing is not None and existing.id != user_id:
            return None  # username taken
    return _user_store.update(user_id, **filtered)


def disable_user(user_id: str) -> bool:
    return _user_store.update(user_id, status=UserStatus.DISABLED.value) is not None


def enable_user(user_id: str) -> bool:
    return _user_store.update(user_id, status=UserStatus.ACTIVE.value) is not None


def delete_user(user_id: str) -> bool:
    return _user_store.delete(user_id)


def list_users(status: Optional[str] = None, limit: int = 100) -> List[User]:
    users = _user_store.get_all()
    if status:
        users = [u for u in users if u.status == status]
    return users[:limit]


def update_last_login(user_id: str, client_ip: str = "") -> None:
    _user_store.update(
        user_id,
        last_login_at=datetime.now().isoformat(),
        last_login_ip=client_ip,
    )


# Invite code management
def create_invite(
    max_uses: int = 1,
    note: str = "",
    expires_at: Optional[str] = None,
    created_by: str = "admin",
) -> InviteCode:
    invite = InviteCode(
        max_uses=max_uses,
        note=note,
        expires_at=expires_at,
        created_by=created_by,
    )
    return _invite_store.create(invite)


def list_invites() -> List[InviteCode]:
    return _invite_store.get_all()


def get_invite(code: str) -> Optional[InviteCode]:
    return _invite_store.get_by_code(code)


def revoke_invite(code: str) -> bool:
    return _invite_store.revoke(code)
