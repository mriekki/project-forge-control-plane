from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RETIRED_AUTOMATION_TOKEN = "PROJECT_FORGE_" + "P" + "OC_AUTOMATION_TOKEN"
SPEC = importlib.util.spec_from_file_location("request", ROOT / "tools" / "request.py")
assert SPEC and SPEC.loader
request = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(request)


class RequestTests(unittest.TestCase):
    def event(
        self,
        *,
        author: str = "mriekki",
        title: str = "[generate-project] mriekki/example-project",
        body: str = "",
    ) -> dict:
        return {
            "issue": {
                "number": 42,
                "title": title,
                "body": body,
                "user": {"login": author},
            }
        }

    def test_valid_owner_request(self) -> None:
        values = request.parse_request(self.event(), {"mriekki"})
        self.assertEqual(values["target_repository"], "mriekki/example-project")
        self.assertEqual(values["request_author"], "mriekki")

    def test_valid_core_sync_request(self) -> None:
        event = self.event(title="[sync-core] mriekki/example-project")
        values = request.parse_sync_request(event, {"mriekki"})
        self.assertEqual(values["target_repository"], "mriekki/example-project")
        self.assertEqual(values["request_author"], "mriekki")

    def test_public_issue_body_must_be_empty(self) -> None:
        for body in ('{"state":"approved"}', "private product definition"):
            with self.subTest(body=body):
                with self.assertRaises(request.RequestError):
                    request.parse_request(self.event(body=body), {"mriekki"})
                with self.assertRaises(request.RequestError):
                    request.parse_sync_request(
                        self.event(title="[sync-core] mriekki/example-project", body=body),
                        {"mriekki"},
                    )

        values = request.parse_request(self.event(body="  \n"), {"mriekki"})
        self.assertEqual(values["target_repository"], "mriekki/example-project")

    def test_author_must_match_target_owner(self) -> None:
        with self.assertRaises(request.RequestError):
            request.parse_request(self.event(author="someone-else"), {"mriekki", "someone-else"})
        with self.assertRaises(request.RequestError):
            request.parse_sync_request(
                self.event(author="someone-else", title="[sync-core] mriekki/example-project"),
                {"mriekki", "someone-else"},
            )

    def test_owner_must_be_allowlisted(self) -> None:
        event = self.event(author="kyle", title="[generate-project] kyle/example-project")
        with self.assertRaises(request.RequestError):
            request.parse_request(event, {"mriekki"})

        sync_event = self.event(author="kyle", title="[sync-core] kyle/example-project")
        with self.assertRaises(request.RequestError):
            request.parse_sync_request(sync_event, {"mriekki"})

    def test_project_forge_repository_namespace_is_reserved(self) -> None:
        for repository in ("project-forge-system", "Project-Forge-Internal"):
            for prefix, parser in (
                ("[generate-project]", request.parse_request),
                ("[sync-core]", request.parse_sync_request),
            ):
                title = f"{prefix} mriekki/{repository}"
                with self.subTest(title=title):
                    with self.assertRaisesRegex(request.RequestError, "reserved Project Forge repository namespace"):
                        parser(self.event(title=title), {"mriekki"})

    def test_title_must_be_exact_owner_repo_shape(self) -> None:
        for title in (
            "generate-project mriekki/example-project",
            "[generate-project] example-project",
            "[generate-project] mriekki/example-project extra",
        ):
            with self.subTest(title=title):
                with self.assertRaises(request.RequestError):
                    request.parse_request(self.event(title=title), {"mriekki"})

        for title in (
            "sync-core mriekki/example-project",
            "[sync-core] example-project",
            "[sync-core] mriekki/example-project extra",
        ):
            with self.subTest(title=title):
                with self.assertRaises(request.RequestError):
                    request.parse_sync_request(self.event(title=title), {"mriekki"})

    def test_allowed_owner_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "owners.json"
            path.write_text(json.dumps({"schemaVersion": 1, "owners": ["mriekki", "Kyle-Example"]}), encoding="utf-8")
            self.assertEqual(request.load_allowed_owners(path), {"mriekki", "kyle-example"})

    def test_generation_workflow_uses_github_app_target_isolation_and_private_seed_manifest(self) -> None:
        workflow = (ROOT / ".github/workflows/generate-project.yml").read_text(encoding="utf-8")
        self.assertIn("actions/create-github-app-token@", workflow)
        self.assertNotIn("actions/create-github-app-token@v3", workflow)
        self.assertIn("APP_PRIVATE_KEY", workflow)
        self.assertIn("APP_CLIENT_ID", workflow)
        self.assertIn("PROJECT_BOOTSTRAP.json", workflow)
        self.assertIn("remote_generation.py validate-manifest", workflow)
        self.assertIn("generate_snapshot.py", workflow)
        self.assertIn("permission-workflows: write", workflow)
        self.assertIn("secrets.BOOTSTRAP_SOURCE_REPOSITORY", workflow)
        self.assertIn("steps.bootstrap-source.outputs.name", workflow)
        self.assertNotIn("project-forge-bootstrap", workflow)
        self.assertNotIn(RETIRED_AUTOMATION_TOKEN, workflow)
        self.assertNotIn("--force", workflow)

    def test_generation_workflow_uses_actual_app_bot_identity_for_commits(self) -> None:
        workflow = (ROOT / ".github/workflows/generate-project.yml").read_text(encoding="utf-8")
        self.assertIn("steps.target-token.outputs.app-slug", workflow)
        self.assertIn('bot_login="${APP_SLUG}[bot]"', workflow)
        self.assertIn('gh api "/users/${bot_login}" --jq', workflow)
        self.assertIn("@users.noreply.github.com", workflow)
        self.assertIn('git -C "$target" config user.name "$BOT_LOGIN"', workflow)
        self.assertIn('git -C "$target" config user.email "$BOT_EMAIL"', workflow)
        self.assertNotIn('config user.name "project-forge-project-control-plane[bot]"', workflow)

    def test_generation_workflow_uses_exact_public_project_forge_artifact(self) -> None:
        workflow = (ROOT / ".github/workflows/generate-project.yml").read_text(encoding="utf-8")
        self.assertIn("actions/setup-node@", workflow)
        self.assertNotIn("actions/setup-node@v6", workflow)
        self.assertIn("steps.manifest.outputs.project_forge_package", workflow)
        self.assertIn("steps.manifest.outputs.project_forge_version", workflow)
        self.assertIn("steps.manifest.outputs.project_forge_profile", workflow)
        self.assertIn("steps.manifest.outputs.project_forge_integrity", workflow)
        self.assertIn('npm pack "${PROJECT_FORGE_PACKAGE}@${PROJECT_FORGE_VERSION}"', workflow)
        self.assertIn("--ignore-scripts", workflow)
        self.assertIn("project_forge_package_generation.verify_integrity", workflow)
        self.assertIn("--project-forge-tarball", workflow)
        self.assertIn("PROJECT_FORGE_BASELINE.json", workflow)
        self.assertIn("check-managed-baselines.py", workflow)
        self.assertIn("CORE_BASELINE.json", workflow)
        self.assertIn("DEPLOYMENT_BASELINE.json", workflow)
        self.assertNotIn("Checkout pinned Project Forge Core source", workflow)
        self.assertNotIn("Checkout pinned Deployment Kit source", workflow)
        self.assertNotIn("--core-path", workflow)
        self.assertNotIn("--deployment-kit-path", workflow)
        self.assertNotIn("PROJECT_FORGE_CORE_READ_TOKEN", workflow)
        self.assertNotIn(RETIRED_AUTOMATION_TOKEN, workflow)

    def test_generation_docs_distinguish_approved_choice_from_resolved_integrity(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        admin_setup = (ROOT / "docs" / "ADMIN_SETUP.md").read_text(encoding="utf-8")
        self.assertIn('generation.project-forge.integrity: "registry"', readme)
        self.assertIn("Humans approve the exact package/version/profile, not npm hash plumbing", readme)
        self.assertIn("resolved exact SHA-512 integrity", readme)
        self.assertNotIn("approved SHA-512 integrity", readme)
        self.assertIn('integrity: "registry"', admin_setup)
        self.assertIn("Humans are not expected to discover or paste npm integrity metadata", admin_setup)
        self.assertIn("separately owned", readme)
        self.assertIn("protected source-repository mappings", admin_setup)

    def test_core_sync_workflow_is_scoped_and_non_force(self) -> None:
        workflow = (ROOT / ".github/workflows/sync-core.yml").read_text(encoding="utf-8")
        self.assertIn("startsWith(github.event.issue.title, '[sync-core] ')", workflow)
        self.assertIn("--request-type sync-core", workflow)
        self.assertIn("secrets.CORE_SOURCE_REPOSITORY", workflow)
        self.assertIn("steps.core-source.outputs.name", workflow)
        self.assertNotIn("project-forge-core", workflow)
        self.assertIn("permission-contents: write", workflow)
        self.assertIn("permission-workflows: write", workflow)
        self.assertIn("permission-pull-requests: write", workflow)
        self.assertIn("permission-checks: read", workflow)
        self.assertIn("core/tools/package/check_baseline.py --root target", workflow)
        self.assertIn("core/tools/package/sync.py", workflow)
        self.assertIn("--apply", workflow)
        self.assertIn("gh pr create", workflow)
        self.assertIn("pulls/$pr_number", workflow)
        self.assertIn("check-runs?per_page=100", workflow)
        self.assertIn("No consumer PR checks registered within 120 seconds.", workflow)
        self.assertIn("Consumer check failed:", workflow)
        self.assertIn("Consumer PR checks are green and stable", workflow)
        self.assertIn("Consumer PR checks did not settle within 30 minutes.", workflow)
        self.assertNotIn("gh pr checks", workflow)
        self.assertNotIn("headRefOid", workflow)
        self.assertIn("CORE_BASELINE.json", workflow)
        self.assertIn("greenfield-workspace", workflow)
        self.assertIn("Refusing direct Core sync for package-managed Project Forge consumer", workflow)
        self.assertIn("PROJECT_FORGE_BASELINE.json is present. Use /project-forge-update", workflow)
        self.assertIn("Sync Project Forge Core to", workflow)
        self.assertNotIn("PROJECT_FORGE_CORE_READ_TOKEN", workflow)
        self.assertNotIn(RETIRED_AUTOMATION_TOKEN, workflow)
        self.assertNotIn("--force", workflow)


if __name__ == "__main__":
    unittest.main()
