import copy
import json
from pathlib import Path
import tempfile
import unittest

from tools.optional_generation_policy import PolicyError, load, select

ROOT = Path(__file__).resolve().parents[1]
STANDARD = "greenfield-project"
AUTH = "greenfield-household-project"
FEEDBACK = "greenfield-household-feedback-project"


class OptionalGenerationPolicyTests(unittest.TestCase):
    def fixture(self, profile=FEEDBACK):
        approval = {"targetRepository": "builder-example/disposable-project",
                    "bootstrapRevision": "a" * 40, "packageVersion": "4.36.3",
                    "profile": profile}
        policy = {"schemaVersion": 1, "approvals": [approval]}
        manifest = {"schemaVersion": 2, "state": "approved",
                    "project": {"repository": approval["targetRepository"]},
                    "bootstrap": {"commit": approval["bootstrapRevision"]},
                    "generation": {"project-forge": {
                        "package": "@mriekki/project-forge", "version": "4.36.3", "profile": profile}}}
        inputs = dict(revision="a" * 40, stable_version="4.36.3",
                      repository=approval["targetRepository"], author="builder-example")
        return policy, manifest, inputs

    def test_default_policy_does_not_activate_optional_profiles(self):
        policy = load(ROOT / "config/optional-generation-approvals.json")
        self.assertEqual(policy, {"schemaVersion": 1, "approvals": []})
        for profile in (AUTH, FEEDBACK):
            _, manifest, inputs = self.fixture(profile)
            with self.assertRaises(PolicyError):
                select(policy, manifest, **inputs)
        _, manifest, inputs = self.fixture(STANDARD)
        self.assertEqual(select(policy, manifest, **inputs),
                         {"profile": STANDARD, "package_version": ""})

    def test_exact_independently_reviewed_optional_profiles(self):
        for profile in (AUTH, FEEDBACK):
            policy, manifest, inputs = self.fixture(profile)
            self.assertEqual(select(policy, manifest, **inputs),
                             {"profile": profile, "package_version": "4.36.3"})

    def test_wrong_owner_target_revision_version_and_profile_refused(self):
        for field, value in (("author", "other-owner"),
                             ("repository", "builder-example/other-project"),
                             ("revision", "b" * 40), ("stable_version", "4.36.4")):
            policy, manifest, inputs = self.fixture()
            with self.subTest(field=field), self.assertRaises(PolicyError):
                select(policy, manifest, **{**inputs, field: value})
        for field, value in (("profile", AUTH), ("profile", "greenfield-release-notes-project"),
                             ("version", "latest"), ("package", "other-package")):
            policy, manifest, inputs = self.fixture()
            manifest["generation"]["project-forge"][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(PolicyError):
                select(policy, manifest, **inputs)

    def test_invalid_or_duplicate_policy_refused_even_for_standard(self):
        policy, manifest, inputs = self.fixture()
        for bad in ({**policy, "schemaVersion": True},
                    {**policy, "approvals": policy["approvals"] * 2},
                    {**policy, "approvals": [{"profile": FEEDBACK}]},
                    {**policy, "extra": True}):
            with self.assertRaises(PolicyError):
                select(bad, manifest, **inputs)
        manifest["generation"]["project-forge"]["profile"] = STANDARD
        with self.assertRaises(PolicyError):
            select({**policy, "approvals": [None]}, manifest, **inputs)

    def test_duplicate_json_fields_refused(self):
        with tempfile.TemporaryDirectory() as holder:
            path = Path(holder) / "duplicate.json"
            path.write_text('{"profile":"greenfield-project","profile":"greenfield-household-project"}')
            with self.assertRaises(PolicyError):
                load(path)


if __name__ == "__main__":
    unittest.main()
