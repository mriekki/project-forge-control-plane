from __future__ import annotations

import copy
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import public_contract


def descriptor_value() -> dict:
    return {
        "schemaVersion": 1,
        "channel": "stable",
        "contractVersion": 13,
        "snapshotPath": "chatgpt/contracts/v13",
        "documents": [
            {
                "path": f"chatgpt/contracts/v13/{name}",
                "sha256": "0" * 64,
            }
            for name in sorted(public_contract.REQUIRED_DOCUMENTS)
        ],
        "controlPlane": {
            "repository": "mriekki/project-forge-control-plane",
        },
        "generation": {
            "manifestFilename": "PROJECT_BOOTSTRAP.json",
            "bootstrap": {
                "revision": "a" * 40,
                "protocolVersion": 12,
                "catalogVersion": 12,
            },
            "package": "@mriekki/project-forge",
            "packageVersion": "4.5.0",
            "profile": "greenfield-project",
            "bootstrapProtocolVersion": 12,
        },
        "bootstrapUrl": public_contract.DEFAULT_DESCRIPTOR_URL,
    }


class PublicContractGenerationTests(unittest.TestCase):
    def test_valid_generation_descriptor_exposes_only_public_compatibility_identity(self) -> None:
        descriptor = descriptor_value()
        result = public_contract.validate_generation_descriptor(descriptor)
        self.assertEqual(result["bootstrapRevision"], "a" * 40)
        self.assertEqual(result["packageVersion"], "4.5.0")
        self.assertEqual(result["profile"], "greenfield-project")

    def test_private_bootstrap_repository_or_commit_fields_are_rejected(self) -> None:
        for field, value in [
            ("repository", "private/bootstrap"),
            ("commit", "b" * 40),
            ("sourceRepository", "private/bootstrap"),
            ("sourceRepositoryUrl", "https://github.com/private/bootstrap"),
        ]:
            with self.subTest(field=field):
                descriptor = descriptor_value()
                descriptor["generation"]["bootstrap"][field] = value
                with self.assertRaisesRegex(
                    public_contract.PublicContractError,
                    "must not expose private source topology",
                ):
                    public_contract.validate_generation_descriptor(descriptor)

    def test_generation_requires_exact_package_version(self) -> None:
        for version in ["latest", "^4.5.0", "~4.5.0", ">=4.5.0", "v4.5.0"]:
            with self.subTest(version=version):
                descriptor = descriptor_value()
                descriptor["generation"]["packageVersion"] = version
                with self.assertRaisesRegex(
                    public_contract.PublicContractError,
                    "exact semantic version",
                ):
                    public_contract.validate_generation_descriptor(descriptor)

    def test_generation_requires_exact_lowercase_bootstrap_revision(self) -> None:
        for revision in ["main", "A" * 40, "a" * 39, "a" * 41]:
            with self.subTest(revision=revision):
                descriptor = descriptor_value()
                descriptor["generation"]["bootstrap"]["revision"] = revision
                with self.assertRaisesRegex(
                    public_contract.PublicContractError,
                    "exact lowercase 40-character revision",
                ):
                    public_contract.validate_generation_descriptor(descriptor)

    def test_legacy_protocol_alias_must_match_bootstrap_protocol(self) -> None:
        descriptor = descriptor_value()
        descriptor["generation"]["bootstrapProtocolVersion"] = 11
        with self.assertRaisesRegex(
            public_contract.PublicContractError,
            "must match",
        ):
            public_contract.validate_generation_descriptor(descriptor)

    def test_bootstrap_url_must_remain_canonical(self) -> None:
        descriptor = descriptor_value()
        descriptor["bootstrapUrl"] = "https://example.test/current.json"
        with self.assertRaisesRegex(
            public_contract.PublicContractError,
            "canonical stable descriptor",
        ):
            public_contract.validate_generation_descriptor(descriptor)

    def test_document_validation_remains_separate_and_complete(self) -> None:
        descriptor = descriptor_value()
        self.assertEqual(
            len(public_contract.validate_descriptor(copy.deepcopy(descriptor))),
            len(public_contract.REQUIRED_DOCUMENTS),
        )


if __name__ == "__main__":
    unittest.main()
