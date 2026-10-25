from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "project_forge_contract",
    ROOT / "tools" / "project_forge_contract.py",
)
assert SPEC and SPEC.loader
project_forge_contract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(project_forge_contract)


class ProjectForgeContractTests(unittest.TestCase):
    PRIVATE_ENV = {
        "PROJECT_FORGE_BOOTSTRAP_SOURCE_REPOSITORY": "example/private-bootstrap-source",
        "PROJECT_FORGE_BOOTSTRAP_SOURCE_COMMIT": "a" * 40,
        "PROJECT_FORGE_BOOTSTRAP_RELEASE_ID": "bootstrap-stable-12",
    }

    def descriptor(self) -> dict:
        return {
            "schemaVersion": 1,
            "generation": {
                "bootstrap": {
                    "releaseId": "bootstrap-stable-12",
                    "protocolVersion": 12,
                    "catalogVersion": 11,
                },
                "package": "@mriekki/project-forge",
                "packageVersion": "4.3.0",
                "profile": "greenfield-project",
            },
        }

    def legacy_descriptor(self) -> dict:
        value = self.descriptor()
        value["generation"]["bootstrap"] = {
            "repository": self.PRIVATE_ENV["PROJECT_FORGE_BOOTSTRAP_SOURCE_REPOSITORY"],
            "commit": self.PRIVATE_ENV["PROJECT_FORGE_BOOTSTRAP_SOURCE_COMMIT"],
            "protocolVersion": 12,
            "catalogVersion": 11,
        }
        return value

    def resolve(self, descriptor: dict) -> dict:
        with mock.patch.dict(os.environ, self.PRIVATE_ENV, clear=False):
            return project_forge_contract.resolve_bootstrap_generation(descriptor)

    def test_resolves_opaque_public_generation_bootstrap_pin(self) -> None:
        self.assertEqual(
            self.resolve(self.descriptor()),
            {
                "releaseId": "bootstrap-stable-12",
                "protocolVersion": 12,
                "catalogVersion": 11,
            },
        )

    def test_legacy_v11_pin_is_accepted_only_when_it_matches_protected_config(self) -> None:
        result = self.resolve(self.legacy_descriptor())
        self.assertEqual(result["releaseId"], "bootstrap-stable-12")

        descriptor = self.legacy_descriptor()
        descriptor["generation"]["bootstrap"]["commit"] = "b" * 40
        with self.assertRaisesRegex(
            project_forge_contract.ProjectForgeContractError,
            "does not match protected Control Plane configuration",
        ):
            self.resolve(descriptor)

    def test_missing_generation_bootstrap_fails_closed(self) -> None:
        descriptor = self.descriptor()
        descriptor["generation"].pop("bootstrap")
        with self.assertRaisesRegex(
            project_forge_contract.ProjectForgeContractError,
            r"generation\.bootstrap pin is required",
        ):
            self.resolve(descriptor)

    def test_malformed_or_wrong_opaque_bootstrap_pin_fails_closed(self) -> None:
        cases = [
            ("releaseId", "wrong-release"),
            ("protocolVersion", 0),
            ("catalogVersion", True),
        ]
        for key, value in cases:
            descriptor = self.descriptor()
            descriptor["generation"]["bootstrap"][key] = value
            with self.subTest(key=key, value=value):
                with self.assertRaises(project_forge_contract.ProjectForgeContractError):
                    self.resolve(descriptor)

    def test_opaque_pin_rejects_source_topology_fields(self) -> None:
        descriptor = self.descriptor()
        descriptor["generation"]["bootstrap"]["repository"] = "example/private-bootstrap-source"
        with self.assertRaisesRegex(
            project_forge_contract.ProjectForgeContractError,
            "must not be combined with source repository/commit fields",
        ):
            self.resolve(descriptor)

    def test_missing_protected_source_config_fails_closed(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                project_forge_contract.ProjectForgeContractError,
                "Protected Bootstrap source repository configuration",
            ):
                project_forge_contract.resolve_bootstrap_generation(self.descriptor())

    def test_checked_out_bootstrap_catalog_must_match_public_compatibility(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog = root / "catalog"
            catalog.mkdir()
            (catalog / "CATALOG.json").write_text(
                json.dumps(
                    {
                        "repository": "private-value-not-used-by-public-contract",
                        "catalogVersion": 11,
                        "protocol": {"version": 12},
                    }
                ),
                encoding="utf-8",
            )
            value = project_forge_contract.verify_bootstrap_catalog(
                root,
                protocol_version=12,
                catalog_version=11,
            )
            self.assertEqual(value["catalogVersion"], 11)

            with self.assertRaises(project_forge_contract.ProjectForgeContractError):
                project_forge_contract.verify_bootstrap_catalog(
                    root,
                    protocol_version=12,
                    catalog_version=12,
                )

    def test_generation_workflow_keeps_private_source_mapping_out_of_public_code(self) -> None:
        workflow = (ROOT / ".github/workflows/generate-project.yml").read_text(encoding="utf-8")
        resolve = "python tools/project_forge_contract.py resolve-bootstrap"
        verify = "python tools/project_forge_contract.py verify-bootstrap"
        manifest = "remote_generation.py validate-manifest"
        self.assertIn(resolve, workflow)
        self.assertIn("secrets.BOOTSTRAP_SOURCE_OWNER", workflow)
        self.assertIn("secrets.BOOTSTRAP_SOURCE_REPOSITORY_NAME", workflow)
        self.assertIn("secrets.BOOTSTRAP_SOURCE_COMMIT", workflow)
        self.assertIn("secrets.BOOTSTRAP_RELEASE_ID", workflow)
        self.assertNotIn("project-forge-bootstrap", workflow)
        self.assertNotIn("bootstrap_commit || 'main'", workflow)
        self.assertLess(workflow.index(resolve), workflow.index(verify))
        self.assertLess(workflow.index(verify), workflow.index(manifest))
        self.assertIn('--expected-bootstrap-commit "${{ steps.bootstrap.outputs.sha }}"', workflow)


if __name__ == "__main__":
    unittest.main()
