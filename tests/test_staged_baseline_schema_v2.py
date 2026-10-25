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


def managed(path: Path) -> dict[str, str]:
    return {
        "source": path.name,
        "path": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def initialize(root: Path, *, mixed: bool = False) -> None:
    git(root, "init")
    git(root, "config", "user.name", "Test")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "core.autocrlf", "false")

    core = root / "core.txt"
    deployment = root / "deployment.txt"
    core.write_text("core\n", encoding="utf-8")
    deployment.write_text("deployment\n", encoding="utf-8")

    write_json(
        root / "PROJECT_BOOTSTRAP.json",
        {
            "generation": {
                "project-forge": {
                    "package": "@mriekki/project-forge",
                    "version": "4.5.0",
                    "profile": "greenfield-project",
                }
            }
        },
    )
    write_json(
        root / "PROJECT_FORGE_BASELINE.json",
        {
            "schemaVersion": 2,
            "package": "@mriekki/project-forge",
            "version": "4.5.0",
            "profile": "greenfield-project",
            "components": {
                "core": {
                    "revision": "a" * 40,
                    "version": "4.0.0",
                    "distribution": "greenfield-workspace",
                },
                "deployment": {
                    "revision": "b" * 40,
                    "distribution": "greenfield-project",
                },
            },
        },
    )
    if mixed:
        write_json(
            root / "CORE_BASELINE.json",
            {
                "schemaVersion": 1,
                "coreRepository": "legacy/private-core",
                "coreCommit": "a" * 40,
                "coreVersion": "4.0.0",
                "distribution": "greenfield-workspace",
                "managedPaths": [managed(core)],
            },
        )
    else:
        write_json(
            root / "CORE_BASELINE.json",
            {
                "schemaVersion": 2,
                "component": "core",
                "revision": "a" * 40,
                "version": "4.0.0",
                "distribution": "greenfield-workspace",
                "managedPaths": [managed(core)],
            },
        )
    write_json(
        root / "DEPLOYMENT_BASELINE.json",
        {
            "schemaVersion": 2,
            "component": "deployment",
            "revision": "b" * 40,
            "distribution": "greenfield-project",
            "managedPaths": [managed(deployment)],
        },
    )
    git(root, "add", "-A")


class StagedBaselineSchemaV2Tests(unittest.TestCase):
    def test_accepts_privacy_safe_schema_v2(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            initialize(root)
            self.assertEqual(validate_staged_baselines(root), 2)

    def test_rejects_mixed_schema_versions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            initialize(root, mixed=True)
            with self.assertRaisesRegex(StagedBaselineError, "schemaVersion does not match"):
                validate_staged_baselines(root)


if __name__ == "__main__":
    unittest.main()
