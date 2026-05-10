from __future__ import annotations

import json

from fastapi.testclient import TestClient


class TestAdminAPI:
    def setup_method(self):
        import app.models.user as user_module
        import app.models.invite as invite_module
        import app.services.user_service as user_service_module
        import app.services.runtime_config as runtime_config_module
        import app.models.working_memory as wm_module

        self._orig_users_file = user_module._USERS_FILE
        self._orig_invites_file = invite_module._INVITES_FILE
        self._orig_runtime_config = runtime_config_module._CONFIG_FILE
        self._orig_sessions_dir = wm_module._SESSIONS_DIR
        self._user_service_module = user_service_module

    def teardown_method(self):
        import app.models.user as user_module
        import app.models.invite as invite_module
        import app.services.user_service as user_service_module
        import app.services.runtime_config as runtime_config_module
        import app.models.working_memory as wm_module
        import app.services.llm_service as llm_service_module

        user_module._USERS_FILE = self._orig_users_file
        invite_module._INVITES_FILE = self._orig_invites_file
        runtime_config_module._CONFIG_FILE = self._orig_runtime_config
        wm_module._SESSIONS_DIR = self._orig_sessions_dir
        user_service_module._user_store = user_module.UserStore()
        user_service_module._invite_store = invite_module.InviteStore()
        llm_service_module.reset_llm()

    def _setup_tmp(self, tmp_path):
        import app.models.user as user_module
        import app.models.invite as invite_module
        import app.services.user_service as user_service_module
        import app.services.runtime_config as runtime_config_module
        import app.models.working_memory as wm_module
        import app.services.llm_service as llm_service_module

        user_module._USERS_FILE = tmp_path / "users.json"
        invite_module._INVITES_FILE = tmp_path / "invites.json"
        runtime_config_module._CONFIG_FILE = tmp_path / "runtime_config.json"
        wm_module._SESSIONS_DIR = tmp_path / "sessions"
        user_service_module._user_store = user_module.UserStore()
        user_service_module._invite_store = invite_module.InviteStore()
        llm_service_module.reset_llm()

    def _create_client_and_tokens(self):
        from app.main import app
        from app.auth.jwt_handler import create_access_token

        return (
            TestClient(app),
            create_access_token("admin-1", role="admin"),
            create_access_token("user-1", role="user"),
        )

    def _seed_users(self):
        from app.models.user import User, UserRole
        self._user_service_module._user_store.create(
            User(
                id="admin-1",
                username="admin",
                invite_code="ADM1N000",
                exam_region="全国",
                role=UserRole.ADMIN,
            )
        )
        self._user_service_module._user_store.create(
            User(
                id="user-1",
                username="normal-user",
                invite_code="USER0001",
                exam_region="北京",
            )
        )

    def test_admin_guard_blocks_non_admin(self, tmp_path):
        self._setup_tmp(tmp_path)
        self._seed_users()
        client, _, user_token = self._create_client_and_tokens()
        response = client.get("/api/admin/users", headers={"Authorization": f"Bearer {user_token}"})
        assert response.status_code == 403

    def test_list_users_hides_password_hash(self, tmp_path):
        self._setup_tmp(tmp_path)
        self._seed_users()
        client, admin_token, _ = self._create_client_and_tokens()
        response = client.get("/api/admin/users", headers={"Authorization": f"Bearer {admin_token}"})
        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 2
        assert "password_hash" not in body["users"][0]

    def test_update_user_role_and_status(self, tmp_path):
        self._setup_tmp(tmp_path)
        self._seed_users()
        client, admin_token, _ = self._create_client_and_tokens()
        response = client.patch(
            "/api/admin/users/user-1",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"role": "admin", "status": "disabled", "grade": "高三"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["role"] == "admin"
        assert body["status"] == "disabled"
        assert body["grade"] == "高三"

    def test_admin_cannot_disable_self(self, tmp_path):
        self._setup_tmp(tmp_path)
        self._seed_users()
        client, admin_token, _ = self._create_client_and_tokens()
        response = client.patch(
            "/api/admin/users/admin-1",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"status": "disabled"},
        )
        assert response.status_code == 400

    def test_invite_create_and_revoke(self, tmp_path):
        self._setup_tmp(tmp_path)
        self._seed_users()
        client, admin_token, _ = self._create_client_and_tokens()
        create_response = client.post(
            "/api/admin/invites",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"max_uses": 2, "note": "batch-a"},
        )
        assert create_response.status_code == 200
        code = create_response.json()["code"]

        revoke_response = client.post(
            f"/api/admin/invites/{code}/revoke",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert revoke_response.status_code == 200
        assert revoke_response.json()["revoked"] is True

    def test_admin_can_manage_other_user_session(self, tmp_path):
        self._setup_tmp(tmp_path)
        self._seed_users()
        from app.models.working_memory import WorkingMemory
        wm = WorkingMemory(session_id="sess-1", user_id="user-1", session_type="training")
        wm.add_message("user", "hello")
        wm.add_message("assistant", "world")

        client, admin_token, _ = self._create_client_and_tokens()
        response = client.get(
            "/api/admin/users/user-1/sessions/sess-1/history",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert response.json()["total_messages"] == 2

        delete_response = client.delete(
            "/api/admin/users/user-1/sessions/sess-1",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert delete_response.status_code == 200

    def test_admin_can_update_llm_runtime_config_without_leaking_key(self, tmp_path):
        self._setup_tmp(tmp_path)
        self._seed_users()
        client, admin_token, _ = self._create_client_and_tokens()
        response = client.put(
            "/api/admin/llm-config",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "provider": "openai",
                "model": "gpt-4o-mini",
                "temperature": 0.7,
                "base_url": "https://api.openai.com/v1",
                "api_key": "secret-test-key",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["provider"] == "openai"
        assert body["has_api_key"] is True
        assert "api_key" not in body

        import app.services.runtime_config as runtime_config_module
        saved = json.loads(runtime_config_module._CONFIG_FILE.read_text(encoding="utf-8"))
        assert saved["llm"]["api_key"] == "secret-test-key"
