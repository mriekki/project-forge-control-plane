from __future__ import annotations

import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import invitation  # noqa: E402
import onboarding_portal  # noqa: E402
import public_contract  # noqa: E402


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
                "githubOwner": "active-builder",
                "status": "active",
                "role": "project-author",
                "contractChannel": "stable",
                "capabilities": ["generate-project", "sync-core"],
            },
        ],
    }


def issue(
    number: int,
    title: str,
    *,
    author: str = "mriekki",
    body: str = "",
    created_at: str = "2026-08-01T00:00:00Z",
) -> dict:
    return {
        "number": number,
        "title": title,
        "body": body,
        "created_at": created_at,
        "user": {"login": author},
    }


class OnboardingHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.registry_path = Path(self.temp.name) / "developers.json"
        self.registry_path.write_text(
            json.dumps(registry_value(), indent=2) + "\n",
            encoding="utf-8",
        )
        self.registry = invitation.load_registry(self.registry_path)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_active_builder_cannot_decline_completed_invitation(self) -> None:
        event = {"issue": issue(1, "[invite-project-forge] active-builder")}
        event["comment"] = {
            "body": "/decline-project-forge",
            "user": {"login": "active-builder"},
        }
        result = onboarding_portal.validate_event(
            "decline",
            event,
            self.registry,
            expiry_days=30,
        )
        self.assertEqual(result["valid"], "false")
        self.assertIn("already ACTIVE", result["error"])

    def test_expiration_only_returns_still_pending_invitations(self) -> None:
        issues = [
            issue(1, "[invite-project-forge] active-builder"),
            issue(2, "[invite-project-forge] pending-builder"),
        ]
        with patch(
            "onboarding_portal.invitation.invitation_expired",
            return_value=True,
        ):
            expired = onboarding_portal.expired_pending_issue_numbers(
                issues,
                self.registry,
                30,
            )
        self.assertEqual(expired, [2])

    def test_public_descriptor_requires_complete_immutable_snapshot(self) -> None:
        docs = [
            {
                "path": f"chatgpt/contracts/v11/{name}",
                "sha256": "0" * 64,
            }
            for name in sorted(public_contract.REQUIRED_DOCUMENTS)
        ]
        descriptor = {
            "schemaVersion": 1,
            "channel": "stable",
            "contractVersion": 11,
            "snapshotPath": "chatgpt/contracts/v11",
            "documents": docs,
        }
        self.assertEqual(
            len(public_contract.validate_descriptor(descriptor)),
            len(public_contract.REQUIRED_DOCUMENTS),
        )

        descriptor["documents"] = docs[:-1]
        with self.assertRaises(public_contract.PublicContractError):
            public_contract.validate_descriptor(descriptor)

    def test_workflows_route_likely_command_intent_to_validation(self) -> None:
        claim = (ROOT / ".github/workflows/claim-invitation.yml").read_text(encoding="utf-8")
        decline = (ROOT / ".github/workflows/decline-invitation.yml").read_text(encoding="utf-8")
        doctor = (ROOT / ".github/workflows/onboarding-doctor.yml").read_text(encoding="utf-8")
        self.assertIn("contains(github.event.comment.body, '/accept-project-forge')", claim)
        self.assertIn("contains(github.event.comment.body, '/decline-project-forge')", decline)
        self.assertIn("contains(github.event.comment.body, '/project-forge-doctor')", doctor)

    def test_real_onboarding_failures_have_issue_recovery(self) -> None:
        invite = (ROOT / ".github/workflows/invite-developer.yml").read_text(encoding="utf-8")
        claim = (ROOT / ".github/workflows/claim-invitation.yml").read_text(encoding="utf-8")
        doctor = (ROOT / ".github/workflows/onboarding-doctor.yml").read_text(encoding="utf-8")
        self.assertIn("Explain invalid invitation request", invite)
        self.assertIn("Verify invited GitHub user exists", invite)
        self.assertIn("Explain invalid invitation claim", claim)
        self.assertIn("Explain registry persistence failure", claim)
        self.assertIn("Explain invalid doctor request", doctor)

    def test_app_recovery_repeats_direct_install_url(self) -> None:
        claim = (ROOT / ".github/workflows/claim-invitation.yml").read_text(encoding="utf-8")
        doctor = (ROOT / ".github/workflows/onboarding-doctor.yml").read_text(encoding="utf-8")
        self.assertIn("/installations/new", claim)
        self.assertIn("/installations/new", doctor)

    def test_doctor_closes_successful_readiness_issue(self) -> None:
        doctor = (ROOT / ".github/workflows/onboarding-doctor.yml").read_text(encoding="utf-8")
        self.assertIn("if (ready)", doctor)
        self.assertIn("state_reason: 'completed'", doctor)

    def test_expiration_is_paginated_and_pending_only(self) -> None:
        workflow = (ROOT / ".github/workflows/expire-invitations.yml").read_text(encoding="utf-8")
        self.assertIn("gh api --paginate", workflow)
        self.assertIn("list-expired-pending", workflow)
        self.assertNotIn("--limit 200", workflow)


if __name__ == "__main__":
    unittest.main()
