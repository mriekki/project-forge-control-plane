import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.disposable_generation_handoff import DisposableHandoffError, qualify, inventory
from tools.profile_baselines import PROFILES, FILES

def write(path, doc):
    path.write_text(json.dumps(doc) + "\n", encoding="utf-8")


class DisposableGenerationHandoffTests(unittest.TestCase):
    def fixture(self, profile):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        scratch = Path(tmp.name)
        root = scratch / "generated"
        root.mkdir()
        selection = {"package": "@mriekki/project-forge", "version": "4.36.0", "profile": profile,
                     "integrity": "sha512-" + base64.b64encode(bytes(64)).decode("ascii")}
        generation = {"project-forge": selection}
        if "authentication" in PROFILES[profile]:
            generation["householdAuth"] = {"mode": "google-invite-only"}
        if "feedback" in PROFILES[profile]:
            generation["feedback"] = {"repository": "example/pf-disposable-generation"}
        seed = {"schemaVersion": 2, "state": "approved",
                "project": {"repository": "example/pf-disposable-generation"}, "generation": generation}
        write(root / "PROJECT_BOOTSTRAP.json", {**seed, "state": "generated"})
        components = {}
        identity = {"consumer": "example", "consumerBaseline": "fixture"}
        for i, component in enumerate(PROFILES[profile], 1):
            meta = {"revision": str(i) * 40, "distribution": profile}
            if component == "core":
                meta["version"] = "4.5.1"
            components[component] = meta
            name = component + ".txt"
            data = (component + "\n").encode()
            (root / name).write_bytes(data)
            write(root / FILES[component], {"schemaVersion": 2, "component": component,
                **meta, **identity, "managedPaths": [{"source": name, "path": name,
                    "sha256": hashlib.sha256(data).hexdigest()}]})
        write(root / "PROJECT_FORGE_BASELINE.json", {"schemaVersion": 2,
              **{k: selection[k] for k in ("package", "version", "profile")},
              **identity, "components": components})
        (root / "README.md").write_text("# Disposable Project\n", encoding="utf-8")
        return root, json.dumps(seed).encode(), selection, scratch

    def test_all_profiles_exact_local_commit_and_fresh_clone(self):
        for profile in PROFILES:
            with self.subTest(profile=profile):
                root, seed, selection, scratch = self.fixture(profile)
                before = inventory(root)
                result = qualify(root, seed, profile, selection, scratch)
                self.assertEqual(result["fileCount"], len(before))
                self.assertTrue(result["freshCloneMatch"])
                self.assertEqual(inventory(root), before)
                self.assertEqual(list(scratch.iterdir()), [root])
                for flag in ("githubTargetWritten", "sourceBindingActivated",
                             "generationAuthorized", "productionAuthorized"):
                    self.assertFalse(result[flag])

    def test_refuses_unapproved_target_manifest_or_profile(self):
        profile = "greenfield-project"
        root, seed, selection, scratch = self.fixture(profile)
        with self.assertRaises(DisposableHandoffError):
            qualify(root, seed.replace(b"example/pf-disposable-generation", b"example/real-project"),
                    profile, selection, scratch)
        with self.assertRaises(DisposableHandoffError):
            qualify(root, seed, profile, {**selection, "version": "4.36.1"}, scratch)
        p = root / "PROJECT_BOOTSTRAP.json"
        value = json.loads(p.read_bytes())
        value["unexpected"] = True
        write(p, value)
        with self.assertRaises(DisposableHandoffError):
            qualify(root, seed, profile, selection, scratch)

    def test_ignored_file_and_index_line_ending_drift_refused(self):
        profile = "greenfield-project"
        for scenario in ("ignored", "normalization"):
            root, seed, selection, scratch = self.fixture(profile)
            if scenario == "ignored":
                (root / ".gitignore").write_text("hidden.txt\n")
                (root / "hidden.txt").write_text("must not silently disappear\n")
            else:
                (root / ".gitattributes").write_text("README.md text eol=lf\n")
                (root / "README.md").write_bytes(b"# CRLF\r\n")
            with self.subTest(scenario=scenario), self.assertRaises(DisposableHandoffError):
                qualify(root, seed, profile, selection, scratch)
            self.assertEqual(list(scratch.iterdir()), [root])

    def test_symlink_case_collision_and_bytecode_refused(self):
        for scenario in ("symlink", "collision", "bytecode"):
            root, seed, selection, scratch = self.fixture("greenfield-project")
            if scenario == "symlink":
                (root / "link").symlink_to(root / "README.md")
            elif scenario == "collision":
                (root / "readme.md").write_text("collision")
            else:
                (root / "unapproved.pyc").write_bytes(b"cache")
            with self.subTest(scenario=scenario), self.assertRaises((DisposableHandoffError, ValueError)):
                qualify(root, seed, "greenfield-project", selection, scratch)
