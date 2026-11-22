import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from bootstrap_source_binding import SourceBindingError, resolve_binding, verify_checkout


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


class BootstrapSourceBindingTests(unittest.TestCase):
    def fixture(self, nested):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        checkout = Path(folder.name)
        git(checkout, "init", "-q", "-b", "main")
        git(checkout, "config", "user.name", "Fixture")
        git(checkout, "config", "user.email", "fixture@example.invalid")
        relative = "components/foundation" if nested else ""
        root = checkout / relative
        blobs = {
            "catalog/CATALOG.json": json.dumps({"protocol": {"version": 12}, "catalogVersion": 13}),
            "schemas/project-requirements.schema.json": "{}",
            "tools/project_requirements.py": "# synthetic read-only fixture\n",
            "tools/remote_generation.py": "raise AssertionError('must not execute source')\n",
            ".gitignore": "*.ignored\n"
        }
        for name, value in blobs.items():
            file = root / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(value.encode())
        git(checkout, "add", ".")
        git(checkout, "commit", "-qm", "Fixture")
        commit = git(checkout, "rev-parse", "HEAD")
        tree = git(checkout, "rev-parse", "HEAD:" + relative if relative else "HEAD^{tree}")
        revision = "a" * 40 if nested else commit
        repo = {"full_name": "example/private-source", "id": 42,
                "private": True, "archived": False}
        binding = {"schemaVersion": 1, "mode": "nested-source" if nested else "original-owner",
                   "logicalRevision": revision, "repository": repo["full_name"], "repositoryId": 42,
                   "sourceCommit": commit, "sourceTree": tree, "sourceRoot": relative}
        projection = {"bootstrapRevision": revision}
        for label, filename in (("schema", "schemas/project-requirements.schema.json"),
                                ("validator", "tools/project_requirements.py")):
            projection[label] = {"path": filename,
                "url": "https://raw.githubusercontent.com/mriekki/project-forge-platform/" + "b"*40
                       + "/chatgpt/bootstrap-contracts/" + Path(filename).name,
                "sha256": hashlib.sha256(blobs[filename].encode()).hexdigest()}
        descriptor = {"channel": "stable", "generation": {"bootstrap": {
            "revision": revision, "protocolVersion": 12, "catalogVersion": 13,
            "portableRequirements": projection}}}
        return checkout, root, descriptor, binding, repo

    def test_original_and_nested_bindings_preserve_logical_revision_without_executing_source(self):
        for nested in (False, True):
            checkout, root, descriptor, binding, repo = self.fixture(nested)
            proof = verify_checkout(checkout, descriptor, binding, repo)
            self.assertEqual(proof["logicalRevision"], binding["logicalRevision"])
            self.assertEqual(proof["fileCount"], 5)
            for key in ("sourceBindingActivated", "generationAuthorized", "productionAuthorized"):
                self.assertIs(proof[key], False)
            self.assertNotIn("sourceCommit", proof)
            self.assertNotIn("repository", proof)
            self.assertNotIn("sourceRoot", proof)

    def test_reject_unreviewed_mapping_repo_or_public_pin(self):
        for change in (
            {"sourceRoot": "../escape"}, {"sourceRoot": "/absolute"},
            {"sourceRoot": "a//b"}, {"sourceRoot": "a/.git"}, {"repositoryId": True},
            {"logicalRevision": "0"*40}, {"sourceCommit": "main"}, {"mode": "original-owner"},
            {"permission": "write"}
        ):
            checkout, _, descriptor, binding, repo = self.fixture(True)
            binding.update(change)
            with self.assertRaises(SourceBindingError):
                resolve_binding(descriptor, binding, repo)
        for change in ({"id": 43}, {"private": False}, {"archived": True},
                       {"full_name": "example/another"}):
            _, _, descriptor, binding, repo = self.fixture(True)
            repo.update(change)
            with self.assertRaises(SourceBindingError):
                resolve_binding(descriptor, binding, repo)

    def test_reject_wrong_commit_tree_and_catalog_projection(self):
        for key in ("sourceCommit", "sourceTree"):
            checkout, _, descriptor, binding, repo = self.fixture(True)
            binding[key] = "0"*40
            with self.assertRaises(SourceBindingError):
                verify_checkout(checkout, descriptor, binding, repo)
        for field in ("catalogVersion", "protocolVersion"):
            checkout, _, descriptor, binding, repo = self.fixture(True)
            descriptor["generation"]["bootstrap"][field] += 1
            with self.assertRaises(SourceBindingError):
                verify_checkout(checkout, descriptor, binding, repo)
        checkout, _, descriptor, binding, repo = self.fixture(True)
        descriptor["generation"]["bootstrap"]["portableRequirements"]["schema"]["sha256"] = "0"*64
        with self.assertRaises(SourceBindingError):
            verify_checkout(checkout, descriptor, binding, repo)

    def test_reject_dirty_and_ignored_extra_source(self):
        for name in ("extra.txt", "extra.ignored", "tools/project_requirements.py"):
            checkout, root, descriptor, binding, repo = self.fixture(True)
            (root / name).write_text("not reviewed")
            with self.assertRaises(SourceBindingError):
                verify_checkout(checkout, descriptor, binding, repo)

    @unittest.skipUnless(os.name == "posix", "symlink fixture requires POSIX")
    def test_reject_committed_symlink_even_with_matching_tree(self):
        checkout, root, descriptor, binding, repo = self.fixture(True)
        (root / "bad-link").symlink_to("tools/project_requirements.py")
        git(checkout, "add", ".")
        git(checkout, "commit", "-qm", "Unsafe symlink fixture")
        binding["sourceCommit"] = git(checkout, "rev-parse", "HEAD")
        binding["sourceTree"] = git(checkout, "rev-parse", "HEAD:" + binding["sourceRoot"])
        with self.assertRaises(SourceBindingError):
            verify_checkout(checkout, descriptor, binding, repo)


if __name__ == "__main__":
    unittest.main()
