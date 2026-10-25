from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.check_baseline_handoff import (
    BaselineHandoffError,
    validate_copied,
    validate_generated,
    validate_staged,
)


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def json_bytes(value: object, *, crlf: bool = False) -> bytes:
    text = json.dumps(value, indent=2) + "\n"
    if crlf:
        text = text.replace("\n", "\r\n")
    return text.encode("utf-8")


def baseline_documents(*, overlap: bool = False) -> dict[str, dict]:
    core_path = "shared.txt" if overlap else "core.txt"
    deployment_path = "shared.txt" if overlap else "deployment.txt"
    return {
        "PROJECT_FORGE_BASELINE.json": {
            "schemaVersion": 1,
            "package": "@mriekki/project-forge",
            "version": "0.1.0",
            "profile": "greenfield-project",
            "components": {
                "core": {
                    "repository": "example/private-core-source",
                    "commit": "a" * 40,
                    "version": "1.10.0",
                    "distribution": "greenfield-workspace",
                },
                "deployment": {
                    "repository": "example/private-deployment-source",
                    "commit": "b" * 40,
                    "distribution": "greenfield-project",
                },
            },
        },
        "CORE_BASELINE.json": {
            "schemaVersion": 1,
            "managedPaths": [
                {"source": core_path, "path": core_path, "sha256": "a" * 64}
            ],
        },
        "DEPLOYMENT_BASELINE.json": {
            "schemaVersion": 1,
            "managedPaths": [
                {"source": deployment_path, "path": deployment_path, "sha256": "b" * 64}
            ],
        },
    }


def write_documents(root: Path, documents: dict[str, dict], *, crlf: bool = False) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for name, value in documents.items():
        (root / name).write_bytes(json_bytes(value, crlf=crlf))


def initialize_target(root: Path, attributes: str = "") -> None:
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init")
    git(root, "config", "user.name", "Test")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "core.autocrlf", "false")
    if attributes:
        (root / ".gitattributes").write_text(attributes, encoding="utf-8")


class BaselineHandoffTests(unittest.TestCase):
    def test_disjoint_baselines_pass_generated_copy_and_staged_boundaries(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            generated = root / "generated"
            target = root / "target"
            write_documents(generated, baseline_documents())
            initialize_target(target)
            for name in ("PROJECT_FORGE_BASELINE.json", "CORE_BASELINE.json", "DEPLOYMENT_BASELINE.json"):
                shutil.copy2(generated / name, target / name)

            validate_generated(generated)
            validate_copied(generated, target)
            git(target, "add", "-A")
            validate_staged(generated, target)

    def test_generated_overlap_fails_at_generated_boundary(self):
        with tempfile.TemporaryDirectory() as temporary:
            generated = Path(temporary) / "generated"
            write_documents(generated, baseline_documents(overlap=True))

            with self.assertRaisesRegex(
                BaselineHandoffError,
                "generated baseline ownership overlap: shared.txt",
            ):
                validate_generated(generated)

    def test_copied_baseline_mutation_fails_at_copy_boundary(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            generated = root / "generated"
            target = root / "target"
            write_documents(generated, baseline_documents())
            target.mkdir()
            for name in ("PROJECT_FORGE_BASELINE.json", "CORE_BASELINE.json", "DEPLOYMENT_BASELINE.json"):
                shutil.copy2(generated / name, target / name)
            (target / "CORE_BASELINE.json").write_bytes(
                (target / "CORE_BASELINE.json").read_bytes() + b"\n"
            )

            with self.assertRaisesRegex(
                BaselineHandoffError,
                "generated→target baseline bytes changed: CORE_BASELINE.json",
            ):
                validate_copied(generated, target)

    def test_git_normalization_of_baseline_json_fails_at_staged_boundary(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            generated = root / "generated"
            target = root / "target"
            documents = baseline_documents()
            write_documents(generated, documents, crlf=True)
            initialize_target(target, "*.json text eol=lf\n")
            for name in ("PROJECT_FORGE_BASELINE.json", "CORE_BASELINE.json", "DEPLOYMENT_BASELINE.json"):
                shutil.copy2(generated / name, target / name)

            validate_copied(generated, target)
            git(target, "add", "-A")

            with self.assertRaisesRegex(
                BaselineHandoffError,
                "target→index baseline bytes changed: PROJECT_FORGE_BASELINE.json",
            ):
                validate_staged(generated, target)


class GenerateWorkflowHandoffContractTests(unittest.TestCase):
    def test_workflow_checks_all_handoff_boundaries_before_staged_baseline_validation(self):
        workflow = Path(".github/workflows/generate-project.yml").read_text(encoding="utf-8")
        generated = 'python tools/check_baseline_handoff.py generated --generated "$RUNNER_TEMP/generated"'
        copied = 'python tools/check_baseline_handoff.py copied --generated "$generated" --target "$target"'
        staged = 'python tools/check_baseline_handoff.py staged --generated "$generated" --target "$target"'
        managed = 'python tools/check_staged_baselines.py --root "$target"'
        commit = 'git -C "$target" commit -m "Generate ${PROJECT_SLUG} workspace baseline"'

        for command in (generated, copied, staged, managed, commit):
            self.assertIn(command, workflow)
        self.assertLess(workflow.index(generated), workflow.index(copied))
        self.assertLess(workflow.index(copied), workflow.index(staged))
        self.assertLess(workflow.index(staged), workflow.index(managed))
        self.assertLess(workflow.index(managed), workflow.index(commit))


if __name__ == "__main__":
    unittest.main()
