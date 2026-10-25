from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import invitation  # noqa: E402
import onboarding_doctor  # noqa: E402


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


def issue_event(title: str, *, author: str, body: str = "", number: int = 44) -> dict:
    return {
        "issue": {
            "number": number,
            "title": title,
            "body": body,
            "created_at": "2026-10-17T12:00:00Z",
            "user": {"login": author},
        }
    }


class OnboardingDoctorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.registry_path = Path(self.temp.name) / "developers.json"
        self.registry_path.write_text(json.dumps(registry_value(), indent=2) + "\n", encoding="utf-8")
        self.registry = invitation.load_registry(self.registry_path)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_active_developer_can_open_standalone_doctor_issue(self) -> None:
        values = onboarding_doctor.extract_request(
            issue_event("[project-forge-doctor] kyleriekki-89", author="kyleriekki-89"),
            self.registry,
        )
        self.assertEqual(values["target_owner"], "kyleriekki-89")
        self.assertEqual(values["request_author"], "kyleriekki-89")
        self.assertEqual(values["issue_number"], "44")

    def test_admin_can_open_standalone_doctor_issue_for_active_developer(self) -> None:
        values = onboarding_doctor.extract_request(
            issue_event("[project-forge-doctor] kyleriekki-89", author="mriekki"),
            self.registry,
        )
        self.assertEqual(values["target_owner"], "kyleriekki-89")
        self.assertEqual(values["request_author"], "mriekki")

    def test_standalone_doctor_rejects_unknown_target_or_nonempty_body(self) -> None:
        with self.assertRaises(onboarding_doctor.DoctorError):
            onboarding_doctor.extract_request(
                issue_event("[project-forge-doctor] unknown-user", author="mriekki"),
                self.registry,
            )
        with self.assertRaises(onboarding_doctor.DoctorError):
            onboarding_doctor.extract_request(
                issue_event("[project-forge-doctor] kyleriekki-89", author="kyleriekki-89", body="details"),
                self.registry,
            )

    def test_standalone_doctor_can_be_retried_with_exact_comment(self) -> None:
        event = issue_event("[project-forge-doctor] kyleriekki-89", author="kyleriekki-89")
        event["comment"] = {"body": "/project-forge-doctor", "user": {"login": "kyleriekki-89"}}
        values = onboarding_doctor.extract_request(event, self.registry)
        self.assertEqual(values["target_owner"], "kyleriekki-89")

        event["comment"]["body"] = "please doctor"
        with self.assertRaises(onboarding_doctor.DoctorError):
            onboarding_doctor.extract_request(event, self.registry)

    def test_invitation_issue_doctor_path_remains_supported(self) -> None:
        event = issue_event("[invite-project-forge] kyleriekki-89", author="mriekki")
        event["comment"] = {"body": "/project-forge-doctor", "user": {"login": "kyleriekki-89"}}
        values = onboarding_doctor.extract_request(event, self.registry)
        self.assertEqual(values["target_owner"], "kyleriekki-89")

    def test_workflow_supports_standalone_open_and_comment_retry(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "onboarding-doctor.yml").read_text(encoding="utf-8")
        self.assertIn("issues:\n    types: [opened]", workflow)
        self.assertIn("[project-forge-doctor] ", workflow)
        self.assertIn("[invite-project-forge] ", workflow)
        self.assertIn("python tools/onboarding_portal.py validate", workflow)
        self.assertIn("--kind doctor", workflow)
        self.assertIn("issue_number: Number(process.env.ISSUE_NUMBER)", workflow)
        self.assertIn("mriekki/project-forge-platform", workflow)


if __name__ == "__main__":
    unittest.main()