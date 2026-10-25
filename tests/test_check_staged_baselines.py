from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.check_staged_baselines import StagedBaselineError, validate_staged_baselines


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def initialize_repo(root: Path, attributes: str) -> None:
    git(root, "init")
    git(root, "config", "user.name", "Test")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "core.autocrlf", "false")
    (root / ".gitattributes").write_text(attributes, encoding="utf-8")


def component_metadata() -> dict[str, dict[str, str]]:
    return {
        "core": {
            "repository": "example/private-core-source",
            "commit": "a" * 40,
            "version": "2.0.0",
            "distribution": "greenfield-workspace",
        },
        "deployment": {
            "repository": "example/private-deployment-source",
            "commit": "b" * 40,
            "distribution": "greenfield-project",
        },
    }


def write_manifest_and_project_forge_baseline(root: Path, components: dict[str, dict[str, str]]) -> None:
    write_json(
        root / "PROJECT_BOOTSTRAP.json",
        {
            "generation": {
                "project-forge": {
                    "package": "@mriekki/project-forge",
                    "version": "1.0.0",
                    "profile": "greenfield-project",
                    "integrity": "sha512-test",
                }
            }
        },
    )
    write_json(
        root / "PROJECT_FORGE_BASELINE.json",
        {
            "schemaVersion": 1,
            "package": "@mriekki/project-forge",
            "version": "1.0.0",
            "profile": "greenfield-project",
            "components": components,
        },
    )


def write_core_baseline(root: Path, path: str, content: bytes) -> str:
    expected_hash = hashlib.sha256(content).hexdigest()
    write_json(
        root / "CORE_BASELINE.json",
        {
            "schemaVersion": 1,
            "coreRepository": "example/private-core-source",
            "coreCommit": "a" * 40,
            "coreVersion": "2.0.0",
            "distribution": "greenfield-workspace",
            "managedPaths": [
                {
                    "source": path,
                    "path": path,
                    "sha256": expected_hash,
                }
            ],
        },
    )
    return expected_hash


def write_deployment_baseline(root: Path, path: str, content: bytes) -> str:
    expected_hash = hashlib.sha256(content).hexdigest()
    write_json(
        root / "DEPLOYMENT_BASELINE.json",
        {
            "schemaVersion": 1,
            "deploymentKitRepository": "example/private-deployment-source",
            "deploymentKitCommit": "b" * 40,
            "distribution": "greenfield-project",
            "managedPaths": [
                {
                    "source": path,
                    "path": path,
                    "sha256": expected_hash,
                }
            ],
        },
    )
    return expected_hash


def make_single_component_repo(root: Path, attributes: str) -> tuple[bytes, str]:
    initialize_repo(root, attributes)
    managed = b"line one\r\nline two\r\n"
    (root / "managed.txt").write_bytes(managed)
    write_manifest_and_project_forge_baseline(root, {"core": component_metadata()["core"]})
    expected_hash = write_core_baseline(root, "managed.txt", managed)
    git(root, "add", "-A")
    return managed, expected_hash


class StagedBaselineTests(unittest.TestCase):
    def test_rejects_git_normalized_managed_blob(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            managed, _ = make_single_component_repo(root, "* text=auto eol=lf\n")

            staged = subprocess.run(
                ["git", "-C", str(root), "show", ":managed.txt"],
                check=True,
                capture_output=True,
            ).stdout
            self.assertNotEqual(managed, staged)

            with self.assertRaisesRegex(StagedBaselineError, "Staged managed file drift in CORE_BASELINE.json: managed.txt"):
                validate_staged_baselines(root)

    def test_accepts_byte_preserved_managed_blob(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            managed, _ = make_single_component_repo(root, "* text=auto eol=lf\nmanaged.txt -text\n")

            staged = subprocess.run(
                ["git", "-C", str(root), "show", ":managed.txt"],
                check=True,
                capture_output=True,
            ).stdout
            self.assertEqual(managed, staged)
            self.assertEqual(1, validate_staged_baselines(root))

    def test_accepts_distinct_core_and_deployment_baselines(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            initialize_repo(root, "* text=auto eol=lf\ncore.txt -text\ndeployment.txt -text\n")
            core = b"core\r\n"
            deployment = b"deployment\r\n"
            (root / "core.txt").write_bytes(core)
            (root / "deployment.txt").write_bytes(deployment)
            write_manifest_and_project_forge_baseline(root, component_metadata())
            write_core_baseline(root, "core.txt", core)
            write_deployment_baseline(root, "deployment.txt", deployment)
            git(root, "add", "-A")

            self.assertEqual(2, validate_staged_baselines(root))

    def test_duplicate_reports_both_component_baselines(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            initialize_repo(root, "shared.txt -text\n")
            shared = b"shared\r\n"
            (root / "shared.txt").write_bytes(shared)
            write_manifest_and_project_forge_baseline(root, component_metadata())
            write_core_baseline(root, "shared.txt", shared)
            write_deployment_baseline(root, "shared.txt", shared)
            git(root, "add", "-A")

            expected = (
                r"Managed path is owned by multiple staged components: shared.txt; "
                r"core \(CORE_BASELINE.json\) and deployment \(DEPLOYMENT_BASELINE.json\)"
            )
            with self.assertRaisesRegex(StagedBaselineError, expected):
                validate_staged_baselines(root)


class GenerateWorkflowContractTests(unittest.TestCase):
    def test_generation_checks_staged_managed_baselines_before_commit(self):
        workflow = Path(".github/workflows/generate-project.yml").read_text(encoding="utf-8")
        staged_check = 'python tools/check_staged_baselines.py --root "$target"'
        commit = 'git -C "$target" commit -m "Generate ${PROJECT_SLUG} workspace baseline"'

        self.assertIn(staged_check, workflow)
        self.assertIn(commit, workflow)
        self.assertLess(workflow.index(staged_check), workflow.index(commit))


if __name__ == "__main__":
    unittest.main()
