import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.check_baseline_handoff import (
    BaselineHandoffError, validate_generated, validate_copied, validate_staged,
)
from tools.check_staged_baselines import StagedBaselineError, validate_staged_baselines
from tools.profile_baselines import FILES, PROFILES

HOUSEHOLD = "greenfield-household-project"
FEEDBACK = "greenfield-household-feedback-project"


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def write(root, name, doc):
    (root / name).write_text(json.dumps(doc) + "\n", encoding="utf-8")


class OptionalProfileHandoffTests(unittest.TestCase):
    def fixture(self, profile=FEEDBACK):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        generated = Path(tmp.name) / "generated"
        generated.mkdir()
        package = {"package": "@mriekki/project-forge", "version": "4.36.0", "profile": profile}
        gen = {"project-forge": package}
        ids = PROFILES[profile]
        if "authentication" in ids:
            gen["householdAuth"] = {"mode": "google-invite-only"}
        if "feedback" in ids:
            gen["feedback"] = {"repository": "example/project"}
        write(generated, "PROJECT_BOOTSTRAP.json", {"generation": gen})
        components = {}
        identity = {"consumer": "example", "consumerBaseline": "fixture"}
        for i, component in enumerate(ids, 1):
            metadata = {"revision": str(i) * 40, "distribution": profile}
            if component == "core":
                metadata["version"] = "4.5.1"
            components[component] = metadata
            data = (component + "\n").encode()
            filename = component + ".txt"
            (generated / filename).write_bytes(data)
            write(generated, FILES[component], {"schemaVersion": 2, "component": component,
                **metadata, **identity, "managedPaths": [{"source": filename, "path": filename,
                "sha256": hashlib.sha256(data).hexdigest()}]})
        write(generated, "PROJECT_FORGE_BASELINE.json", {
            "schemaVersion": 2, **package, **identity, "components": components})
        target = Path(tmp.name) / "target"
        shutil.copytree(generated, target)
        git(target, "init", "-q")
        git(target, "config", "core.autocrlf", "false")
        git(target, "add", "-A")
        return generated, target

    def test_all_three_profiles_cross_generated_copy_and_staged_boundaries(self):
        for profile in PROFILES:
            generated, target = self.fixture(profile)
            with self.subTest(profile=profile):
                kwargs = {"approved_profile": profile}
                validate_generated(generated, **kwargs)
                validate_copied(generated, target, **kwargs)
                validate_staged(generated, target, **kwargs)
                self.assertEqual(validate_staged_baselines(target, **kwargs), len(PROFILES[profile]))

    def test_default_legacy_validators_do_not_enable_optional_profiles(self):
        generated, target = self.fixture()
        with self.assertRaises(BaselineHandoffError):
            validate_generated(generated)
        with self.assertRaises(StagedBaselineError):
            validate_staged_baselines(target)
        with self.assertRaises(BaselineHandoffError):
            validate_generated(generated, approved_profile=HOUSEHOLD)
        with self.assertRaises(BaselineHandoffError):
            validate_generated(generated, approved_profile="greenfield-release-notes-project")

    def test_wrong_optional_metadata_missing_or_extra_baseline_refused(self):
        for scenario in ("missing", "extra", "revision", "collision", "unapproved capability"):
            generated, target = self.fixture()
            if scenario == "missing":
                (generated / FILES["feedback"]).unlink()
            elif scenario == "extra":
                (generated / FILES["release-notes"]).write_text("{}")
            elif scenario == "unapproved capability":
                p = generated / "PROJECT_BOOTSTRAP.json"
                doc = json.loads(p.read_bytes())
                doc["generation"].pop("householdAuth")
                write(generated, p.name, doc)
            else:
                p = generated / FILES["feedback"]
                doc = json.loads(p.read_bytes())
                if scenario == "revision":
                    doc["revision"] = "0" * 40
                else:
                    doc["managedPaths"] = json.loads((generated / FILES["authentication"]).read_bytes())["managedPaths"]
                write(generated, p.name, doc)
            with self.subTest(scenario=scenario), self.assertRaises(BaselineHandoffError):
                validate_generated(generated, approved_profile=FEEDBACK)

    def test_copy_and_index_reject_optional_baseline_byte_mutation(self):
        generated, target = self.fixture()
        p = target / FILES["feedback"]
        p.write_bytes(p.read_bytes() + b"\n")
        with self.assertRaisesRegex(BaselineHandoffError, "baseline bytes changed"):
            validate_copied(generated, target, approved_profile=FEEDBACK)
        git(target, "add", "-A")
        shutil.copy2(generated / p.name, p)
        with self.assertRaisesRegex(BaselineHandoffError, "baseline bytes changed"):
            validate_staged(generated, target, approved_profile=FEEDBACK)

    def test_managed_file_mutation_rejected_at_copy_and_index(self):
        generated, target = self.fixture()
        p = target / "authentication.txt"
        p.write_bytes(b"changed")
        with self.assertRaises(BaselineHandoffError):
            validate_copied(generated, target, approved_profile=FEEDBACK)
        git(target, "add", "-A")
        shutil.copy2(generated / p.name, p)
        with self.assertRaises(StagedBaselineError):
            validate_staged_baselines(target, approved_profile=FEEDBACK)

    def test_workflow_gates_all_optional_profile_switches_on_reviewed_policy(self):
        path = Path(__file__).resolve().parents[1] / ".github/workflows/generate-project.yml"
        workflow = path.read_text()
        self.assertLess(workflow.index("Select independently reviewed generation profile"),
                        workflow.index("Validate private approved manifest"))
        self.assertIn("APPROVED_PROFILE: ${{ steps.profile-policy.outputs.profile }}", workflow)
        self.assertIn('--approved-generation-profile "$APPROVED_PROFILE"', workflow)
        self.assertEqual(workflow.count('if [ "$APPROVED_PROFILE" != \'greenfield-project\' ]; then'), 3)
        for command in ("check_baseline_handoff.py generated", "check_baseline_handoff.py copied",
                        "check_baseline_handoff.py staged", "check_staged_baselines.py --root"):
            line = next(line for line in workflow.splitlines() if command in line)
            self.assertIn('"${profile_args[@]}"', line)


if __name__ == "__main__":
    unittest.main()
