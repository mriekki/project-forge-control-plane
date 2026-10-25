from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_FILES = [
    ROOT / "README.md",
    ROOT / "docs" / "SETUP.md",
    ROOT / "docs" / "INVITATIONS.md",
    ROOT / "docs" / "ADMIN_SETUP.md",
    ROOT / "tools" / "request.py",
    ROOT / "tools" / "project_forge_contract.py",
    ROOT / ".github" / "workflows" / "invite-developer.yml",
    ROOT / ".github" / "workflows" / "claim-invitation.yml",
    ROOT / ".github" / "workflows" / "generate-project.yml",
    ROOT / ".github" / "workflows" / "sync-core.yml",
]


class ProjectForgePublicIdentityTests(unittest.TestCase):
    def test_public_surfaces_use_project_forge_builder_app_name(self) -> None:
        retired_generator_name = "Project Forge " + "P" + "OC Generator"
        onboarding_files = [
            ROOT / "README.md",
            ROOT / "docs" / "SETUP.md",
            ROOT / "docs" / "INVITATIONS.md",
            ROOT / ".github" / "workflows" / "invite-developer.yml",
            ROOT / ".github" / "workflows" / "claim-invitation.yml",
        ]
        for path in onboarding_files:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(retired_generator_name, text, str(path))
            self.assertIn("Project Forge Builder", text, str(path))

    def test_public_surfaces_only_name_intentionally_public_project_forge_repositories(self) -> None:
        pattern = re.compile(r"mriekki/project-forge-([a-z0-9-]+)")
        allowed = {"platform", "control-plane"}
        for path in PUBLIC_FILES:
            text = path.read_text(encoding="utf-8")
            for suffix in pattern.findall(text):
                self.assertIn(suffix, allowed, f"private Project Forge repository topology leaked by {path}")

    def test_source_workflows_do_not_hard_code_private_project_forge_repository_names(self) -> None:
        workflows = [
            ROOT / ".github" / "workflows" / "generate-project.yml",
            ROOT / ".github" / "workflows" / "sync-core.yml",
        ]
        for path in workflows:
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"repositories:\s+project-forge-(?!platform\b|control-plane\b)")
            self.assertIn("SOURCE_REPOSITORY", text)

    def test_request_safety_reserves_project_forge_namespace(self) -> None:
        request = (ROOT / "tools" / "request.py").read_text(encoding="utf-8")
        self.assertIn('RESERVED_PROJECT_FORGE_REPOSITORY_PREFIX = "project-forge-"', request)

    def test_canonical_commands_are_present(self) -> None:
        combined = "\n".join(path.read_text(encoding="utf-8") for path in PUBLIC_FILES)
        self.assertIn("[invite-project-forge]", combined)
        self.assertIn("/accept-project-forge", combined)
        self.assertIn("[generate-project]", combined)


if __name__ == "__main__":
    unittest.main()
