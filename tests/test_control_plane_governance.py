from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
DIRECT_MAIN_WRITERS = {"claim-invitation.yml", "revoke-developer.yml"}


class ControlPlaneGovernanceTests(unittest.TestCase):
    def test_ci_exposes_one_stable_required_gate(self):
        workflow = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("pull_request:", workflow)
        self.assertRegex(workflow, r"\n  required:\r?\n    name: required\r?\n")
        self.assertRegex(workflow, r"needs:\r?\n      - validate")
        self.assertIn("needs.validate.result", workflow)

    def test_only_registry_workflows_push_directly_to_control_plane_main(self):
        writers = set()
        for path in WORKFLOWS.glob("*.yml"):
            if "git push origin HEAD:main" in path.read_text(encoding="utf-8"):
                writers.add(path.name)
        self.assertEqual(writers, DIRECT_MAIN_WRITERS)

    def test_direct_registry_writers_use_exact_project_forge_builder_token(self):
        for name in sorted(DIRECT_MAIN_WRITERS):
            workflow = (WORKFLOWS / name).read_text(encoding="utf-8")
            with self.subTest(workflow=name):
                self.assertNotRegex(workflow, r"(?m)^\s+contents:\s*write\s*$")
                self.assertIn("Create Control Plane registry persistence token", workflow)
                self.assertIn("actions/create-github-app-token@", workflow)
                self.assertIn("repositories: ${{ github.event.repository.name }}", workflow)
                self.assertIn("permission-contents: write", workflow)
                self.assertIn("token: ${{ steps.registry-token.outputs.token }}", workflow)
                self.assertIn("git add config/developers.json config/allowed-owners.json", workflow)
                self.assertNotIn("git add -A", workflow)
                self.assertNotIn("git push --force", workflow)
                self.assertNotIn("git push -f", workflow)

    def test_registry_rehearsal_is_non_authorizing_and_ephemeral(self):
        workflow = (WORKFLOWS / "registry-persistence-rehearsal.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("repositories: ${{ github.event.repository.name }}", workflow)
        self.assertIn("permission-contents: write", workflow)
        self.assertIn("createRef", workflow)
        self.assertIn("deleteRef", workflow)
        self.assertIn("project-forge-registry-rehearsal-", workflow)
        self.assertNotIn("git push origin HEAD:main", workflow)
        self.assertNotIn("config/developers.json", workflow)
        self.assertNotIn("config/allowed-owners.json", workflow)

    def test_governance_document_keeps_bypass_narrow(self):
        doc = (ROOT / "docs" / "GITHUB_GOVERNANCE.md").read_text(encoding="utf-8")
        self.assertIn("CI / required", doc)
        self.assertIn("Project Forge Builder", doc)
        self.assertIn("do not grant a repository-role, administrator, or generic GitHub Actions bypass", doc)
        self.assertIn("config/developers.json", doc)
        self.assertIn("config/allowed-owners.json", doc)
        self.assertIn("Registry Persistence Rehearsal", doc)


if __name__ == "__main__":
    unittest.main()
