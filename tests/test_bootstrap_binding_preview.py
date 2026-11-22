import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from bootstrap_binding_preview import resolve_policy, validate_event, TITLE
from bootstrap_source_binding import SourceBindingError
from public_contract import REQUIRED_DOCUMENTS, DEFAULT_DESCRIPTOR_URL


class BindingPreviewTests(unittest.TestCase):
    def fixture(self):
        p = "chatgpt/contracts/v19"
        rev = "a" * 40
        projection = {"bootstrapRevision": rev}
        for label, filename in (("schema", "schemas/project-requirements.schema.json"),
                                ("validator", "tools/project_requirements.py")):
            projection[label] = {"path": filename, "sha256": "b" * 64,
                "url": "https://raw.githubusercontent.com/mriekki/project-forge-platform/" + "c"*40
                       + "/chatgpt/bootstrap-contracts/" + Path(filename).name}
        descriptor = {"schemaVersion": 1, "channel": "stable", "contractVersion": 19,
            "snapshotPath": p, "documents": [{"path": p + "/" + n, "sha256": "d"*64}
                for n in sorted(REQUIRED_DOCUMENTS)],
            "controlPlane": {"repository": "mriekki/project-forge-control-plane"},
            "generation": {"manifestFilename": "PROJECT_BOOTSTRAP.json", "bootstrap": {
                "revision": rev, "protocolVersion": 12, "catalogVersion": 13,
                "portableRequirements": projection}, "package": "@mriekki/project-forge",
                "packageVersion": "4.36.0", "profile": "greenfield-project", "bootstrapProtocolVersion": 12},
            "bootstrapUrl": DEFAULT_DESCRIPTOR_URL}
        raw = json.dumps(descriptor).encode()
        common = {"schemaVersion": 1, "logicalRevision": rev, "sourceTree": "e"*40}
        policy = {"schemaVersion": 1, "descriptorSha256": hashlib.sha256(raw).hexdigest(),
            "original": {**common, "mode": "original-owner", "repository": "example/original", "repositoryId": 1,
                         "sourceCommit": rev, "sourceRoot": ""},
            "candidate": {**common, "mode": "nested-source", "repository": "example/candidate", "repositoryId": 2,
                          "sourceCommit": "f"*40, "sourceRoot": "components/bootstrap"}}
        return raw, policy

    def test_exact_protected_relocation_preserves_logical_revision_and_tree(self):
        raw, policy = self.fixture()
        result, _ = resolve_policy(json.dumps(policy).encode(), raw, "example/original")
        self.assertEqual(result, policy)

    def test_reject_changed_tree_original_locator_revision_and_descriptor(self):
        for change in ({"sourceTree": "0"*40}, {"logicalRevision": "0"*40},
                       {"repositoryId": 1}, {"repository": "example/original"}, {"sourceCommit": "main"},
                       {"sourceRoot": "../escape"}):
            raw, policy = self.fixture()
            policy["candidate"].update(change)
            with self.assertRaises(SourceBindingError):
                resolve_policy(json.dumps(policy).encode(), raw, "example/original")
        raw, policy = self.fixture()
        for data, original in ((raw + b" ", "example/original"), (raw, "example/other")):
            with self.assertRaises(SourceBindingError):
                resolve_policy(json.dumps(policy).encode(), data, original)

    def test_only_empty_owner_request(self):
        e = {"action": "opened", "sender": {"login": "owner"}, "issue": {
             "title": TITLE, "state": "open", "user": {"login": "owner"}, "body": ""}}
        validate_event(e, "owner")
        for change in ({"body": "private/source"}, {"state": "closed"}, {"title": "[generate-project]"},
                       {"user": {"login": "other"}}):
            with self.assertRaises(SourceBindingError):
                validate_event({**e, "issue": {**e["issue"], **change}}, "owner")
        with self.assertRaises(SourceBindingError):
            validate_event({**e, "sender": {"login": "other"}}, "owner")

    def test_preview_is_default_off_source_only_and_nonpublishing(self):
        body = (ROOT / ".github/workflows/bootstrap-source-transport-preview.yml").read_text()
        for value in ("vars.PF_BOOTSTRAP_BINDING_PREVIEW_ENABLED == 'true'", "Qualify exact immutable-ID source-only App grants and sanitized transport",
                      "BOOTSTRAP_SOURCE_BINDING_PREVIEW", "GENERATION_AUTHORIZED=false",
                      "PRODUCTION_CHANGED=false", "persist-credentials: false"):
            self.assertIn(value, body)
        self.assertNotIn("actions/create-github-app-token@", body)
        transport = (ROOT / "tools/bootstrap_source_transport.py").read_text()
        self.assertIn('"repository_ids": [binding["repositoryId"]]', transport)
        self.assertIn('"permissions": {"contents": "read"}', transport)
        self.assertIn('stage("scope-before-fetch", observe_scope, binding, descriptor, token, request)', transport)
        self.assertIn('stage("scope-after-fetch", observe_scope, binding, descriptor, token, request)', transport)
        self.assertIn('stage("scope-after-verify", observe_scope, binding, descriptor, token, request)', transport)
        for forbidden in ("permission-contents: write", "permission-workflows: write", "issues: write",
                          "git push", "generate_snapshot.py", "npm publish", "id-token: write",
                          "upload-artifact", "target-token"):
            self.assertNotIn(forbidden, body)


if __name__ == "__main__":
    unittest.main()
