from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api import deps as deps_module
from app.api.v1 import auth as auth_module
from app.api.v1 import jobs as jobs_module
from app.database.crud import users_db
from app.main import app
from app.schemas.auth_schema import UserCreate, UserRead, UserRole
from app.services import auth_service


def make_user(role: UserRole = UserRole.hr, *, is_active: bool = True) -> UserRead:
    return UserRead(
        id=uuid4(),
        email="hr@example.com",
        full_name="HR Admin",
        role=role,
        is_active=is_active,
        created_at=datetime.now(timezone.utc),
    )


class PasswordHashingTests(TestCase):
    def test_hash_and_verify_roundtrip(self) -> None:
        hashed = auth_service.hash_password("correct-horse-9")
        self.assertTrue(auth_service.verify_password("correct-horse-9", hashed))
        self.assertFalse(auth_service.verify_password("wrong-password", hashed))

    def test_hash_never_returns_plaintext(self) -> None:
        hashed = auth_service.hash_password("some-secret")
        self.assertNotIn("some-secret", hashed)


class LoginRouteTests(TestCase):
    def setUp(self) -> None:
        self.user = make_user(UserRole.hr)
        self.authenticate_patch = patch.object(auth_module, "authenticate_user")
        self.authenticate_mock = self.authenticate_patch.start()
        self.audit_patch = patch("app.services.audit.record_audit")
        self.audit_mock = self.audit_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        self.authenticate_patch.stop()
        self.audit_patch.stop()

    def test_login_success_returns_access_and_refresh_tokens(self) -> None:
        self.authenticate_mock.return_value = self.user

        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": "hr@example.com", "password": "secret123"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["token_type"], "bearer")
        self.assertTrue(payload["access_token"])
        self.assertTrue(payload["refresh_token"])
        self.assertNotEqual(payload["access_token"], payload["refresh_token"])
        self.assertEqual(payload["user"]["email"], "hr@example.com")
        self.assertEqual(payload["user"]["role"], "hr")
        self.assertNotIn("password", payload["user"])
        self.audit_mock.assert_called_once()
        self.assertEqual(self.audit_mock.call_args.kwargs["action"], "login")

    def test_login_failure_returns_401_and_audits(self) -> None:
        self.authenticate_mock.return_value = None

        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": "hr@example.com", "password": "wrong"},
        )

        self.assertEqual(response.status_code, 401)
        self.audit_mock.assert_called_once()
        self.assertEqual(self.audit_mock.call_args.kwargs["action"], "login_failed")

    def test_login_rejects_unknown_fields(self) -> None:
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": "hr@example.com", "password": "x", "extra": "nope"},
        )
        self.assertEqual(response.status_code, 422)


class TokenFlowTests(TestCase):
    def setUp(self) -> None:
        self.user = make_user(UserRole.ceo)
        self.get_user_patch = patch.object(users_db, "get_user_by_id", return_value=self.user)
        self.get_user_patch.start()
        self.audit_patch = patch("app.services.audit.record_audit")
        self.audit_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        self.get_user_patch.stop()
        self.audit_patch.stop()
        app.dependency_overrides.clear()

    def test_refresh_flow_issues_new_tokens(self) -> None:
        refresh_token = auth_service.create_refresh_token(self.user)

        response = self.client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["access_token"])
        self.assertTrue(payload["refresh_token"])

        me_response = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {payload['access_token']}"},
        )
        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.json()["email"], self.user.email)
        self.assertEqual(me_response.json()["role"], "ceo")

    def test_refresh_with_access_token_is_rejected(self) -> None:
        access_token = auth_service.create_access_token(self.user)
        response = self.client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": access_token},
        )
        self.assertEqual(response.status_code, 401)

    def test_refresh_with_garbage_token_is_rejected(self) -> None:
        response = self.client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "not-a-token"},
        )
        self.assertEqual(response.status_code, 401)

    def test_me_without_token_returns_401(self) -> None:
        response = self.client.get("/api/v1/auth/me")
        self.assertEqual(response.status_code, 401)

    def test_me_with_tampered_token_returns_401(self) -> None:
        token = auth_service.create_access_token(self.user)
        tampered = token[:-2] + ("ab" if not token.endswith("ab") else "cd")
        response = self.client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {tampered}"}
        )
        self.assertEqual(response.status_code, 401)


class RBACTests(TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()

    def test_protected_route_without_token_returns_401(self) -> None:
        response = self.client.get("/api/v1/jobs")
        self.assertEqual(response.status_code, 401)

    def test_hr_only_route_rejects_interviewer_with_403(self) -> None:
        app.dependency_overrides[deps_module.get_current_user] = lambda: make_user(UserRole.interviewer)
        response = self.client.post(
            "/api/v1/jobs",
            json={"title": "Data Engineer", "tech_stack": "Python", "seniority": "Senior"},
        )
        self.assertEqual(response.status_code, 403)

    def test_ceo_only_route_rejects_hr_with_403(self) -> None:
        app.dependency_overrides[deps_module.get_current_user] = lambda: make_user(UserRole.hr)
        response = self.client.post(
            f"/api/v1/applications/{uuid4()}/final-decision",
            json={"final_decision": "pass"},
        )
        self.assertEqual(response.status_code, 403)

    def test_any_role_can_list_jobs(self) -> None:
        app.dependency_overrides[deps_module.get_current_user] = lambda: make_user(UserRole.interviewer)
        store = Mock()
        store.list_jobs.return_value = []
        with patch.object(jobs_module, "get_jobs_store", return_value=store):
            response = self.client.get("/api/v1/jobs")
        self.assertEqual(response.status_code, 200)

    def test_ceo_role_can_reach_ceo_only_route(self) -> None:
        app.dependency_overrides[deps_module.get_current_user] = lambda: make_user(UserRole.ceo)
        with patch(
            "app.api.v1.applications.candidates_db.save_final_decision",
            return_value=None,
        ):
            response = self.client.post(
                f"/api/v1/applications/{uuid4()}/final-decision",
                json={"final_decision": "pass"},
            )
        # ceo passes RBAC; the fake DB returns None -> 409 "not ready", not 403
        self.assertEqual(response.status_code, 409)


class AuthenticateUserTests(TestCase):
    def test_authenticate_user_success(self) -> None:
        user = make_user(UserRole.interviewer)
        password_hash = auth_service.hash_password("s3cret-pw")
        with patch.object(
            users_db, "get_user_password_hash_by_email", return_value=(user, password_hash)
        ):
            result = auth_service.authenticate_user("hr@example.com", "s3cret-pw")
        self.assertIsNotNone(result)
        self.assertEqual(result.id, user.id)

    def test_authenticate_user_wrong_password_returns_none(self) -> None:
        user = make_user()
        password_hash = auth_service.hash_password("s3cret-pw")
        with patch.object(
            users_db, "get_user_password_hash_by_email", return_value=(user, password_hash)
        ):
            self.assertIsNone(auth_service.authenticate_user("hr@example.com", "nope"))

    def test_authenticate_user_unknown_email_returns_none(self) -> None:
        with patch.object(users_db, "get_user_password_hash_by_email", return_value=None):
            self.assertIsNone(auth_service.authenticate_user("nobody@example.com", "pw"))

    def test_authenticate_user_inactive_returns_none(self) -> None:
        user = make_user(is_active=False)
        password_hash = auth_service.hash_password("s3cret-pw")
        with patch.object(
            users_db, "get_user_password_hash_by_email", return_value=(user, password_hash)
        ):
            self.assertIsNone(auth_service.authenticate_user("hr@example.com", "s3cret-pw"))


class UsersDbTests(TestCase):
    def test_create_user_lowercases_email(self) -> None:
        captured: dict = {}

        class FakeQuery:
            def insert(self, values):
                captured.update(values)
                return self

            def select(self, *args):
                return self

            def execute(self):
                row = {
                    "id": uuid4(),
                    "email": captured["email"],
                    "full_name": captured["full_name"],
                    "role": captured["role"],
                    "is_active": True,
                    "created_at": datetime.now(timezone.utc),
                }
                return SimpleNamespace(data=[row])

        class FakeClient:
            def table(self, name):
                self.table_name = name
                return FakeQuery()

        with patch("app.database.crud.users_db.supabase_client", FakeClient()):
            created = users_db.create_user(
                UserCreate(
                    email="HR@Example.COM",
                    password="password123",
                    full_name="HR Admin",
                    role=UserRole.hr,
                ),
                password_hash="hashed",
            )
        self.assertEqual(created.email, "hr@example.com")
        self.assertEqual(captured["password_hash"], "hashed")


class AuditServiceTests(TestCase):
    def test_record_audit_swallows_database_errors(self) -> None:
        with patch(
            "app.services.audit.audit_db",
            Mock(insert_audit_log=Mock(side_effect=RuntimeError("db down"))),
        ):
            from app.services import audit

            audit.record_audit(action="login", entity="user", actor_email="a@b.c")
        # no exception raised
