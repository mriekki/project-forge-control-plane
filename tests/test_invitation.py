from __future__ import annotations

from datetime import datetime, timezone
import json
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import invitation  # noqa: E402

NOW = datetime(2026, 10, 17, 14, 0, tzinfo=timezone.utc)


def registry_value() -> dict:
    return {
        "schemaVersion": 1,
        "developers": [
            {
                "githubOwner": "mriekki",
                "status": "active",
                "role": "admin",
                "contractChannel": "stable",
                "capabilities": [
                    "generate-project",
                    "sync-core",
                    "invite-developer",
                    "revoke-developer",
                ],
            },
            {
                "githubOwner": "kyleriekki-89",
                "status": "active",
                "role": "project-author",
                "contractChannel": "stable",
                "capabilities": ["generate-project", "sync-core"],
            },
        ],
    }


def issue_event(
    title: str,
    author: str = "mriekki",
    body: str = "",
    number: int = 12,
    created_at: str = "2026-10-10T12:00:00Z",
) -> dict:
    return {
        "issue": {
            "number": number,
            "state": "open",
            "title": title,
            "body": body,
            "created_at": created_at,
            "user": {"login": author},
        }
    }


class InvitationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.registry_path = self.root / "developers.json"
        self.allowed_path = self.root / "allowed-owners.json"
        self.policy_path = self.root / "invitation-policy.json"
        self.registry_path.write_text(json.dumps(registry_value(), indent=2) + "\n", encoding="utf-8")
        self.allowed_path.write_text(
            json.dumps({"schemaVersion": 1, "owners": ["mriekki", "kyleriekki-89"]}, indent=2) + "\n",
            encoding="utf-8",
        )
        self.policy_path.write_text(
            json.dumps({"schemaVersion": 1, "expiryDays": 30}, indent=2) + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def registry(self) -> dict:
        return invitation.load_registry(self.registry_path)

    def test_config_projection_and_policy_are_valid(self) -> None:
        value = self.registry()
        invitation.validate_projection(value, self.allowed_path)
        self.assertEqual(invitation.load_policy(self.policy_path)["expiryDays"], 30)

    def test_only_active_admin_can_invite(self) -> None:
        event = issue_event("[invite-project-forge] daniel-example", author="mriekki")
        values = invitation.extract_invite(event, self.registry())
        self.assertEqual(values["target_owner"], "daniel-example")

        with self.assertRaises(invitation.InvitationError):
            invitation.extract_invite(
                issue_event("[invite-project-forge] daniel-example", author="kyleriekki-89"),
                self.registry(),
            )

    def test_invitation_body_must_be_empty(self) -> None:
        with self.assertRaises(invitation.InvitationError):
            invitation.extract_invite(
                issue_event("[invite-project-forge] daniel-example", body="private details"),
                self.registry(),
            )

    def test_claimant_identity_must_match_invited_owner(self) -> None:
        event = issue_event("[invite-project-forge] daniel-example")
        event["comment"] = {"body": "/accept-project-forge", "user": {"login": "someone-else"}}
        with self.assertRaises(invitation.InvitationError):
            invitation.extract_claim(event, self.registry(), expiry_days=30, now=NOW)

        event["comment"]["user"]["login"] = "daniel-example"
        values = invitation.extract_claim(event, self.registry(), expiry_days=30, now=NOW)
        self.assertEqual(values["claimant"], "daniel-example")

    def test_closed_or_unknown_state_cannot_be_claimed_or_declined(self) -> None:
        for state in ("closed", None):
            event = issue_event("[invite-project-forge] daniel-example")
            event["issue"]["state"] = state
            event["comment"] = {"body": "/accept-project-forge", "user": {"login": "daniel-example"}}
            with self.assertRaisesRegex(invitation.InvitationError, "not open"):
                invitation.extract_claim(event, self.registry(), expiry_days=30, now=NOW)
            event["comment"]["body"] = "/decline-project-forge"
            with self.assertRaisesRegex(invitation.InvitationError, "not open"):
                invitation.extract_decline(event, self.registry())

    def test_expired_invitation_cannot_be_claimed(self) -> None:
        event = issue_event(
            "[invite-project-forge] daniel-example",
            created_at="2026-08-01T12:00:00Z",
        )
        event["comment"] = {"body": "/accept-project-forge", "user": {"login": "daniel-example"}}
        with self.assertRaisesRegex(invitation.InvitationError, "expired"):
            invitation.extract_claim(event, self.registry(), expiry_days=30, now=NOW)

    def test_invited_owner_can_decline_without_registry_change(self) -> None:
        event = issue_event("[invite-project-forge] daniel-example")
        event["comment"] = {"body": "/decline-project-forge", "user": {"login": "daniel-example"}}
        values = invitation.extract_decline(event, self.registry())
        self.assertEqual(values["target_owner"], "daniel-example")
        self.assertIsNone(invitation.developer(self.registry(), "daniel-example"))

        event["comment"]["user"]["login"] = "someone-else"
        with self.assertRaises(invitation.InvitationError):
            invitation.extract_decline(event, self.registry())

    def test_expired_issue_listing_only_returns_old_invites(self) -> None:
        issues = [
            {"number": 1, "title": "[invite-project-forge] one-user", "createdAt": "2026-08-01T00:00:00Z"},
            {"number": 2, "title": "[invite-project-forge] two-user", "createdAt": "2026-10-10T00:00:00Z"},
            {"number": 3, "title": "ordinary issue", "createdAt": "2026-01-01T00:00:00Z"},
        ]
        self.assertEqual(
            invitation.expired_issue_numbers(issues, 30, now=NOW),
            [1],
        )

    def test_activation_updates_registry_and_compatibility_allowlist(self) -> None:
        invitation.activate(
            self.registry_path,
            self.allowed_path,
            owner="daniel-example",
            invited_by="mriekki",
            issue=12,
        )
        registry = invitation.load_registry(self.registry_path)
        record = invitation.developer(registry, "daniel-example")
        self.assertEqual(record["status"], "active")
        self.assertEqual(record["role"], "project-author")
        self.assertEqual(record["capabilities"], ["generate-project", "sync-core"])
        self.assertEqual(record["activationIssue"], 12)
        allowed = invitation.load_allowed_owners(self.allowed_path)
        self.assertEqual(allowed, ["mriekki", "kyleriekki-89", "daniel-example"])
        invitation.validate_projection(registry, self.allowed_path)

    def test_revocation_removes_future_generation_authorization_only(self) -> None:
        invitation.activate(
            self.registry_path,
            self.allowed_path,
            owner="daniel-example",
            invited_by="mriekki",
            issue=12,
        )
        invitation.revoke(
            self.registry_path,
            self.allowed_path,
            owner="daniel-example",
            revoked_by="mriekki",
            issue=13,
        )
        registry = invitation.load_registry(self.registry_path)
        record = invitation.developer(registry, "daniel-example")
        self.assertEqual(record["status"], "revoked")
        self.assertEqual(record["capabilities"], [])
        self.assertNotIn("daniel-example", invitation.load_allowed_owners(self.allowed_path))

    def test_public_onboarding_surfaces_use_canonical_platform_urls(self) -> None:
        paths = [
            ROOT / ".github" / "workflows" / "invite-developer.yml",
            ROOT / ".github" / "workflows" / "claim-invitation.yml",
            ROOT / "docs" / "INVITATIONS.md",
            ROOT / "docs" / "SETUP.md",
        ]
        for path in paths:
            with self.subTest(path=path):
                content = path.read_text(encoding="utf-8")
                self.assertIn("mriekki/project-forge-platform", content)
    def test_last_admin_cannot_be_revoked(self) -> None:
        event = issue_event("[revoke-project-forge] mriekki", author="mriekki")
        with self.assertRaises(invitation.InvitationError):
            invitation.extract_revoke(event, self.registry())

    def test_doctor_is_allowed_for_active_owner_or_admin(self) -> None:
        invitation.activate(
            self.registry_path,
            self.allowed_path,
            owner="daniel-example",
            invited_by="mriekki",
            issue=12,
        )
        registry = invitation.load_registry(self.registry_path)
        event = issue_event("[invite-project-forge] daniel-example", author="mriekki")
        event["comment"] = {"body": "/project-forge-doctor", "user": {"login": "daniel-example"}}
        values = invitation.extract_doctor(event, registry)
        self.assertEqual(values["target_owner"], "daniel-example")

        event["comment"]["user"]["login"] = "mriekki"
        values = invitation.extract_doctor(event, registry)
        self.assertEqual(values["request_author"], "mriekki")


if __name__ == "__main__":
    unittest.main()
