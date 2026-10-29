from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class HumanFacingInvitationNotificationTests(unittest.TestCase):
    def test_real_invite_keeps_machine_trigger_but_renames_before_mention(self) -> None:
        text = (ROOT / ".github" / "workflows" / "invite-developer.yml").read_text(encoding="utf-8")
        self.assertIn("startsWith(github.event.issue.title, '[invite-project-forge] ')", text)
        self.assertIn("tools/onboarding_issue_state.py render --kind invite", text)
        self.assertIn('title: "You\'re invited to Project Forge"', text)
        self.assertLess(
            text.index('title: "You\'re invited to Project Forge"'),
            text.index("Publish Project Forge onboarding instructions"),
        )

    def test_self_test_renames_before_preview_comment(self) -> None:
        text = (ROOT / ".github" / "workflows" / "invite-developer.yml").read_text(encoding="utf-8")
        self.assertIn("tools/onboarding_issue_state.py render --kind test-invite", text)
        self.assertIn("title: 'Project Forge onboarding test'", text)
        self.assertLess(
            text.index("title: 'Project Forge onboarding test'"),
            text.index("Publish onboarding simulation and invitation message preview"),
        )

    def test_invitation_lifecycle_reads_persisted_state_with_legacy_fallback(self) -> None:
        claim = (ROOT / ".github" / "workflows" / "claim-invitation.yml").read_text(encoding="utf-8")
        decline = (ROOT / ".github" / "workflows" / "decline-invitation.yml").read_text(encoding="utf-8")
        doctor = (ROOT / ".github" / "workflows" / "onboarding-doctor.yml").read_text(encoding="utf-8")

        for text in [claim, decline, doctor]:
            with self.subTest(workflow=text.splitlines()[0]):
                self.assertIn("project-forge-onboarding-state:v1", text)
                self.assertIn("tools/onboarding_issue_state.py normalize-event", text)
                self.assertIn("startsWith(github.event.issue.title, '[invite-project-forge] ')", text)

        self.assertIn('"kind":"test-invite"', claim)
        self.assertIn("startsWith(github.event.issue.title, '[test-invite-forge]')", claim)

    def test_expiry_normalizes_human_facing_open_issues(self) -> None:
        text = (ROOT / ".github" / "workflows" / "expire-invitations.yml").read_text(encoding="utf-8")
        self.assertIn("{number, title, body, createdAt: .created_at}", text)
        self.assertIn("tools/onboarding_issue_state.py normalize-issues", text)
        self.assertIn("normalized-open-issues.json", text)

    def test_invitation_docs_explain_human_and_machine_surfaces(self) -> None:
        text = (ROOT / "docs" / "INVITATIONS.md").read_text(encoding="utf-8")
        self.assertIn("You're invited to Project Forge", text)
        self.assertIn("Project Forge onboarding test", text)
        self.assertIn("hidden machine-readable onboarding marker", text)
        self.assertIn("rather than depending on the visible title", text)


if __name__ == "__main__":
    unittest.main()
