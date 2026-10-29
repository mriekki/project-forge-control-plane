from __future__ import annotations

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import onboarding_issue_state  # noqa: E402


class OnboardingIssueStateTests(unittest.TestCase):
    def test_state_round_trip_is_compact_and_hidden(self) -> None:
        body = onboarding_issue_state.render_state("invite", "builder-example")
        self.assertEqual(
            body,
            '<!-- project-forge-onboarding-state:v1 {"kind":"invite","targetOwner":"builder-example"} -->',
        )
        self.assertEqual(
            onboarding_issue_state.parse_state(body),
            {"kind": "invite", "target_owner": "builder-example"},
        )

    def test_state_rejects_visible_or_malformed_body(self) -> None:
        marker = onboarding_issue_state.render_state("invite", "builder-example")
        for body in [
            f"visible text\n{marker}",
            '<!-- project-forge-onboarding-state:v1 {"kind":"invite"} -->',
            '<!-- project-forge-onboarding-state:v1 not-json -->',
        ]:
            with self.subTest(body=body):
                with self.assertRaises(onboarding_issue_state.OnboardingIssueStateError):
                    onboarding_issue_state.parse_state(body)

    def test_real_invitation_event_normalizes_to_existing_validator_contract(self) -> None:
        event = {
            "issue": {
                "number": 42,
                "title": "You're invited to Project Forge",
                "body": onboarding_issue_state.render_state("invite", "builder-example"),
                "created_at": "2026-10-29T15:00:00Z",
                "user": {"login": "mriekki"},
            },
            "comment": {
                "body": "/accept-project-forge",
                "user": {"login": "builder-example"},
            },
        }
        normalized = onboarding_issue_state.normalize_event(event, kind="invite")
        self.assertEqual(normalized["issue"]["title"], "[invite-project-forge] builder-example")
        self.assertEqual(normalized["issue"]["body"], "")
        self.assertEqual(event["issue"]["title"], "You're invited to Project Forge")

    def test_test_invitation_event_normalizes_to_existing_test_contract(self) -> None:
        event = {
            "issue": {
                "number": 116,
                "title": "Project Forge onboarding test",
                "body": onboarding_issue_state.render_state("test-invite", "mriekki"),
                "created_at": "2026-10-29T15:00:00Z",
                "user": {"login": "mriekki"},
            }
        }
        normalized = onboarding_issue_state.normalize_event(event, kind="test-invite")
        self.assertEqual(normalized["issue"]["title"], "[test-invite-forge] mriekki")
        self.assertEqual(normalized["issue"]["body"], "")

    def test_expiry_listing_normalizes_only_real_invitations(self) -> None:
        issues = [
            {
                "number": 1,
                "title": "You're invited to Project Forge",
                "body": onboarding_issue_state.render_state("invite", "pending-builder"),
                "createdAt": "2026-08-01T00:00:00Z",
            },
            {
                "number": 2,
                "title": "Project Forge onboarding test",
                "body": onboarding_issue_state.render_state("test-invite", "mriekki"),
                "createdAt": "2026-08-01T00:00:00Z",
            },
            {
                "number": 3,
                "title": "ordinary issue",
                "body": "",
                "createdAt": "2026-08-01T00:00:00Z",
            },
        ]
        normalized = onboarding_issue_state.normalize_issue_listing(issues)
        self.assertEqual(normalized[0]["title"], "[invite-project-forge] pending-builder")
        self.assertEqual(normalized[0]["body"], "")
        self.assertEqual(normalized[1]["title"], "Project Forge onboarding test")
        self.assertEqual(normalized[2]["title"], "ordinary issue")


if __name__ == "__main__":
    unittest.main()
