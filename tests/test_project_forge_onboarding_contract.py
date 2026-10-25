from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ProjectForgeOnboardingContractTests(unittest.TestCase):
    def test_invitation_is_two_step_product_facing_flow(self):
        text = (ROOT / ".github" / "workflows" / "invite-developer.yml").read_text(encoding="utf-8")
        self.assertIn("Welcome to Project Forge", text)
        self.assertIn("Project Builder", text)
        self.assertIn("Install Project Forge Builder", text)
        self.assertIn("Accept this invitation", text)
        self.assertIn("add a new comment", text)
        self.assertIn("/accept-project-forge", text)
        self.assertNotIn("After activation, comment \\`/project-forge-doctor\\`", text)

    def test_invitation_derives_app_install_url_without_admin_doc_fallback(self):
        text = (ROOT / ".github" / "workflows" / "invite-developer.yml").read_text(encoding="utf-8")
        self.assertIn("actions/create-github-app-token@", text)
        self.assertNotIn("actions/create-github-app-token@v3", text)
        self.assertIn("outputs.app-slug", text)
        self.assertIn("/installations/new", text)
        self.assertNotIn("APP_INSTALL_URL", text)
        self.assertNotIn("docs/SETUP.md#installations", text)

    def test_builder_setup_contains_only_builder_actions(self):
        text = (ROOT / "docs" / "SETUP.md").read_text(encoding="utf-8")
        self.assertIn("Project Forge Builder Setup", text)
        self.assertIn("Install Project Forge Builder", text)
        self.assertIn("/accept-project-forge", text)
        self.assertIn("More about Project Forge", text)
        self.assertNotIn("GitHub App registration", text)
        self.assertNotIn("Control Plane Actions configuration", text)
        self.assertNotIn("APP_CLIENT_ID", text)
        self.assertNotIn("APP_PRIVATE_KEY", text)

    def test_admin_setup_owns_control_plane_configuration(self):
        text = (ROOT / "docs" / "ADMIN_SETUP.md").read_text(encoding="utf-8")
        self.assertIn("Administrator Setup", text)
        self.assertIn("APP_CLIENT_ID", text)
        self.assertIn("APP_PRIVATE_KEY", text)
        self.assertNotIn("APP_INSTALL_URL", text)

    def test_claim_runs_readiness_automatically(self):
        text = (ROOT / ".github" / "workflows" / "claim-invitation.yml").read_text(encoding="utf-8")
        self.assertIn("Automatically verify public Project Forge contract", text)
        self.assertIn("Project Forge is ready", text)
        self.assertIn("New Project: <your idea>", text)
        self.assertIn("/project-forge-doctor", text)

    def test_doctor_is_retry_path_with_new_project_language(self):
        text = (ROOT / ".github" / "workflows" / "onboarding-doctor.yml").read_text(encoding="utf-8")
        self.assertIn("Project Forge readiness check", text)
        self.assertIn("READY FOR PROJECT FORGE", text)
        self.assertIn("New Project: <idea>", text)

    def test_invitation_docs_use_canonical_identifiers(self):
        text = (ROOT / "docs" / "INVITATIONS.md").read_text(encoding="utf-8")
        retired_trigger = "New " + "P" + "OC:"
        self.assertIn("Project Forge Developer Invitations", text)
        self.assertIn("project-author", text)
        self.assertIn("[invite-project-forge]", text)
        self.assertNotIn(retired_trigger, text)

    def test_test_mode_has_clear_preview_and_non_authorizing_result(self):
        invite = (ROOT / ".github" / "workflows" / "invite-developer.yml").read_text(encoding="utf-8")
        claim = (ROOT / ".github" / "workflows" / "claim-invitation.yml").read_text(encoding="utf-8")

        self.assertIn("[test-invite-forge]", invite)
        self.assertIn("startsWith(github.event.issue.title, '[test-invite-forge]')", invite)
        self.assertIn("Invitation message preview", invite)
        self.assertIn("Open your invitation issue", invite)
        self.assertIn("add a new comment containing exactly: /accept-project-forge", invite)
        self.assertIn("TEST MODE — no access or authorization will be granted or changed", invite)
        self.assertIn("[test-invite-forge]", claim)
        self.assertIn("TEST READY FOR PROJECT FORGE", claim)
        self.assertIn("Developer registry mutation: NOT PERFORMED", claim)
        self.assertIn("Compatibility allowlist mutation: NOT PERFORMED", claim)
        self.assertIn("Project generation: NOT PERFORMED", claim)

    def test_invalid_self_test_posts_recovery_instructions(self):
        invite = (ROOT / ".github" / "workflows" / "invite-developer.yml").read_text(encoding="utf-8")

        self.assertIn("continue-on-error: true", invite)
        self.assertIn("Explain invalid self-test request", invite)
        self.assertIn("Project Forge onboarding test request invalid", invite)
        self.assertIn("keep the issue body completely empty", invite)
        self.assertIn("Editing this issue will not rerun the issue-opened workflow", invite)
        self.assertIn("core.setFailed(", invite)

    def test_test_claim_job_is_repository_read_only_and_has_no_activation_steps(self):
        claim = (ROOT / ".github" / "workflows" / "claim-invitation.yml").read_text(encoding="utf-8")
        marker = "  test-claim:\n"
        self.assertIn(marker, claim)
        test_job = claim.split(marker, 1)[1]
        self.assertIn("contents: read", test_job)
        self.assertIn("issues: write", test_job)
        self.assertNotIn("tools/invitation.py activate", test_job)
        self.assertNotIn("git push", test_job)
        self.assertNotIn("config/allowed-owners.json", test_job)
        self.assertNotIn("Commit operational registry update", test_job)


if __name__ == "__main__":
    unittest.main()
