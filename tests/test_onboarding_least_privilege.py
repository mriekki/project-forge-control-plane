from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class OnboardingLeastPrivilegeTests(unittest.TestCase):
    def test_builder_setup_recommends_selected_repository_installation(self) -> None:
        text = (ROOT / "docs" / "SETUP.md").read_text(encoding="utf-8")
        self.assertIn("Recommended — least privilege", text)
        self.assertIn("select only the repositories Project Forge should operate on", text)
        self.assertIn("Convenience option", text)
        self.assertNotIn("**Simplest:** allow the App for all repositories", text)

    def test_invitation_portal_recommends_selected_repository_installation(self) -> None:
        text = (ROOT / ".github" / "workflows" / "invite-developer.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("Recommended: select only repositories Project Forge should operate on", text)
        self.assertIn("Allowing all repositories remains a convenience option", text)
        self.assertNotIn("For the simplest experience, allow it for all repositories", text)

    def test_admin_setup_explains_outer_installation_boundary(self) -> None:
        text = (ROOT / "docs" / "ADMIN_SETUP.md").read_text(encoding="utf-8")
        self.assertIn("Recommended — least privilege", text)
        self.assertIn("additional outer authorization boundary", text)
        self.assertIn("short-lived installation token scoped to the exact repository", text)


if __name__ == "__main__":
    unittest.main()
