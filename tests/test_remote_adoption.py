from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]

REQUEST_SPEC = importlib.util.spec_from_file_location("request", ROOT / "tools" / "request.py")
assert REQUEST_SPEC and REQUEST_SPEC.loader
request = importlib.util.module_from_spec(REQUEST_SPEC)
REQUEST_SPEC.loader.exec_module(request)

CONTRACT_SPEC = importlib.util.spec_from_file_location(
    "adoption_contract", ROOT / "tools" / "adoption_contract.py"
)
assert CONTRACT_SPEC and CONTRACT_SPEC.loader
adoption_contract = importlib.util.module_from_spec(CONTRACT_SPEC)
CONTRACT_SPEC.loader.exec_module(adoption_contract)


class RemoteAdoptionTests(unittest.TestCase):
    def event(
        self,
        *,
        author: str = "mriekki",
        title: str = "[adopt-project] mriekki/example-project 0123456789abcdef0123456789abcdef",
        body: str = "",
    ) -> dict:
        return {
            "issue": {
                "number": 77,
                "title": title,
                "body": body,
                "user": {"login": author},
            }
        }

    def test_adoption_request_is_owner_scoped_empty_body_and_opaque(self) -> None:
        values = request.parse_adopt_request(self.event(), {"mriekki"})
        self.assertEqual(values["target_repository"], "mriekki/example-project")
        self.assertEqual(values["request_id"], "0123456789abcdef0123456789abcdef")
        self.assertEqual(
            values["seed_branch"],
            "project-forge/adopt-0123456789abcdef0123456789abcdef",
        )

        with self.assertRaises(request.RequestError):
            request.parse_adopt_request(self.event(body="private analysis"), {"mriekki"})
        with self.assertRaises(request.RequestError):
            request.parse_adopt_request(
                self.event(author="someone-else"),
                {"mriekki", "someone-else"},
            )
        with self.assertRaises(request.RequestError):
            request.parse_adopt_request(
                self.event(title="[adopt-project] mriekki/example-project actual-budget"),
                {"mriekki"},
            )

    def test_adoption_request_reserves_foundational_namespace(self) -> None:
        with self.assertRaisesRegex(request.RequestError, "reserved Project Forge repository namespace"):
            request.parse_adopt_request(
                self.event(
                    title=(
                        "[adopt-project] mriekki/project-forge-example "
                        "0123456789abcdef0123456789abcdef"
                    )
                ),
                {"mriekki"},
            )

    def test_public_adoption_contract_is_privacy_safe_and_exact(self) -> None:
        descriptor = {
            "schemaVersion": 1,
            "adoption": {
                "manifestFilename": "PROJECT_ADOPTION.json",
                "kit": {
                    "revision": "a" * 40,
                    "protocolVersion": 1,
                },
            },
        }
        with mock.patch.dict(
            os.environ,
            {"PROJECT_FORGE_ADOPTION_SOURCE_REPOSITORY": "private-owner/private-adoption"},
            clear=False,
        ):
            resolved = adoption_contract.resolve_adoption(descriptor)
        self.assertEqual(resolved["revision"], "a" * 40)
        self.assertEqual(resolved["protocolVersion"], 1)

        descriptor["adoption"]["kit"]["repository"] = "private-owner/private-adoption"
        with mock.patch.dict(
            os.environ,
            {"PROJECT_FORGE_ADOPTION_SOURCE_REPOSITORY": "private-owner/private-adoption"},
            clear=False,
        ):
            with self.assertRaises(adoption_contract.AdoptionContractError):
                adoption_contract.resolve_adoption(descriptor)

    def test_verify_adoption_contract_reads_protocol_and_remote_apply_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "schema").mkdir()
            (root / "installer").mkdir()
            (root / "schema" / "project-adoption.schema.json").write_text(
                json.dumps(
                    {
                        "properties": {
                            "adoptionKit": {
                                "properties": {"protocolVersion": {"const": 1}}
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            (root / "installer" / "apply-project-adoption.py").write_text("# remote apply\n", encoding="utf-8")
            adoption_contract.verify_adoption_source(root, protocol_version=1)
            with self.assertRaises(adoption_contract.AdoptionContractError):
                adoption_contract.verify_adoption_source(root, protocol_version=2)

    def test_adoption_workflow_preserves_exact_base_pr_ci_and_human_merge_boundary(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "adopt-project.yml").read_text(encoding="utf-8")
        for expected in (
            "startsWith(github.event.issue.title, '[adopt-project] ')",
            "--request-type adopt-project",
            "secrets.ADOPTION_SOURCE_REPOSITORY",
            "secrets.BOOTSTRAP_SOURCE_REPOSITORY",
            "python tools/adoption_contract.py resolve",
            "python tools/adoption_contract.py verify",
            "PROJECT_ADOPTION.json",
            "validate-project-adoption.py",
            "apply-project-adoption.py target",
            "steps.request.outputs.seed_branch",
            "permission-pull-requests: write",
            "permission-checks: read",
            "gh pr create",
            "check-runs?per_page=100",
            "CI NOT OBSERVED",
            "Merge remains an explicit human decision",
            "upstream write",
        ):
            self.assertIn(expected, workflow)
        self.assertNotIn("--force", workflow)
        self.assertNotIn("gh pr merge", workflow)
        self.assertNotIn("PROJECT_ADOPTION.json\n          ", workflow.split("Report successful adoption orchestration")[1])

    def test_adoption_workflow_does_not_hardcode_private_source_topology(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "adopt-project.yml").read_text(encoding="utf-8")
        self.assertNotIn("project-forge-adoption-kit", workflow)
        self.assertIn("SOURCE_REPOSITORY", workflow)
        self.assertIn("PROJECT_FORGE_ADOPTION_SOURCE_REPOSITORY", workflow)


if __name__ == "__main__":
    unittest.main()
