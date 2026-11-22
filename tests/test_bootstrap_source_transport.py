import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from bootstrap_source_transport import qualify_one, validate_scope, PERMISSIONS, stage, TransportStageError
from bootstrap_source_binding import SourceBindingError
from test_bootstrap_binding_preview import BindingPreviewTests


class ImmutableSourceTokenTests(unittest.TestCase):
    def scenario(self):
        raw, policy = BindingPreviewTests().fixture()
        descriptor = json.loads(raw)
        binding = policy["candidate"]
        repo = {"full_name": binding["repository"], "id": binding["repositoryId"],
                "private": True, "archived": False}
        token = "t" * 30
        minted = {"token": token, "permissions": dict(PERMISSIONS), "repositories": [repo]}
        scope = {"total_count": 1, "repositories": [repo]}
        calls = []
        def request(method, endpoint, credential, body=None):
            calls.append((method, endpoint, credential, body))
            if endpoint.endswith("/installation") and method == "GET":
                return {"id": 11, "account": {"login": "example"}, "suspended_at": None}
            if method == "POST":
                return minted
            if endpoint.startswith("/installation/repositories"):
                return scope
            if method == "DELETE":
                return None
            return repo
        return descriptor, binding, repo, minted, scope, request, calls

    def run_scenario(self, setup=lambda *a: None, fail=False, checkout_behavior=None):
        descriptor, binding, repo, minted, scope, request, calls = self.scenario()
        setup(repo, minted, scope)
        def checkout(*args):
            calls.append(("checkout", "", "", None))
            if checkout_behavior:
                checkout_behavior(repo, minted, scope)
        validator = Mock(return_value={"same": True})
        with tempfile.TemporaryDirectory() as tmp:
            if fail:
                with self.assertRaises(SourceBindingError):
                    qualify_one(binding, descriptor, "JWT", Path(tmp) / "source",
                                request=request, checkout=checkout, verify=validator)
            else:
                self.assertEqual(qualify_one(binding, descriptor, "JWT", Path(tmp) / "source",
                                   request=request, checkout=checkout, verify=validator), {"same": True})
        return calls, validator

    def test_exact_id_token_and_permission_verified_before_any_checkout(self):
        calls, validator = self.run_scenario()
        self.assertEqual(calls[1][3], {"repository_ids": [2], "permissions": {"contents": "read"}})
        self.assertEqual(calls[2][1], "/installation/repositories?per_page=100")
        self.assertEqual(calls[4][0], "checkout")
        self.assertEqual(calls[-1][:2], ("DELETE", "/installation/token"))
        validator.assert_called_once()

    def test_wrong_id_wrong_permissions_and_extra_scope_refused_before_checkout(self):
        for mutation in (
            lambda repo, mint, scope: repo.update(id=999),
            lambda repo, mint, scope: mint.update(permissions={"contents": "write", "metadata": "read"}),
            lambda repo, mint, scope: mint.update(permissions={**PERMISSIONS, "workflows": "write"}),
            lambda repo, mint, scope: scope.update(total_count=2, repositories=[repo, repo]),
            lambda repo, mint, scope: repo.update(full_name="example/renamed"),
        ):
            calls, validator = self.run_scenario(mutation, fail=True)
            self.assertNotIn("checkout", [k[0] for k in calls])
            self.assertEqual(calls[-1][0], "DELETE")
            validator.assert_not_called()

    def test_rename_between_read_and_checkout_rejected_and_revoked(self):
        calls, validator = self.run_scenario(fail=True,
            checkout_behavior=lambda repo, mint, scope: repo.update(full_name="example/renamed"))
        self.assertIn("checkout", [k[0] for k in calls])
        self.assertEqual(calls[-1][0], "DELETE")
        validator.assert_not_called()


if __name__ == "__main__":
    unittest.main()

class SafeStageDiagnosticTests(unittest.TestCase):
    def test_never_records_sensitive_exception_or_http_url(self):
        sentinel = "REDACT-ME"
        def fail():
            raise RuntimeError(sentinel)
        def http_fail():
            raise urllib.error.HTTPError("https://example.invalid/" + sentinel, 403,
                                        sentinel, {}, None)
        for fn, expected in ((fail, "app-jwt: refused"), (http_fail, "app-jwt: http-403")):
            with self.assertRaises(TransportStageError) as ctx:
                stage("app-jwt", fn)
            self.assertEqual(str(ctx.exception), expected)
            self.assertNotIn(sentinel, str(ctx.exception))
