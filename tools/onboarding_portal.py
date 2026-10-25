#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import invitation
import onboarding_doctor


def _write_output(values: dict[str, str]) -> None:
    destination = os.getenv("GITHUB_OUTPUT")
    if not destination:
        return
    with Path(destination).open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            safe = str(value).replace("\r", " ").replace("\n", " ").strip()
            handle.write(f"{key}={safe}\n")


def _success(values: dict[str, str]) -> dict[str, str]:
    result = {"valid": "true", "error": ""}
    result.update({key: str(value) for key, value in values.items()})
    return result


def _failure(exc: Exception) -> dict[str, str]:
    return {"valid": "false", "error": str(exc)}


def validate_event(
    kind: str,
    event: dict[str, Any],
    registry: dict[str, Any],
    *,
    expiry_days: int,
) -> dict[str, str]:
    try:
        if kind == "invite":
            return _success(invitation.extract_invite(event, registry))
        if kind == "claim":
            return _success(
                invitation.extract_claim(
                    event,
                    registry,
                    expiry_days=expiry_days,
                )
            )
        if kind == "decline":
            values = invitation.extract_decline(event, registry)
            existing = invitation.developer(registry, values["target_owner"])
            if existing and existing["status"] == "active":
                raise invitation.InvitationError(
                    f"Invitation is no longer pending; developer is already ACTIVE: {values['target_owner']}"
                )
            return _success(values)
        if kind == "doctor":
            return _success(onboarding_doctor.extract_request(event, registry))
        raise invitation.InvitationError(f"Unsupported onboarding validation kind: {kind}")
    except (invitation.InvitationError, onboarding_doctor.DoctorError) as exc:
        return _failure(exc)


def expired_pending_issue_numbers(
    issues: list[Any],
    registry: dict[str, Any],
    expiry_days: int,
) -> list[int]:
    expired: list[int] = []
    for value in issues:
        if not isinstance(value, dict):
            continue
        title = str(value.get("title") or "").strip()
        if not title.startswith(f"{invitation.INVITE_PREFIX} "):
            continue
        try:
            target = invitation.parse_title(value, invitation.INVITE_PREFIX)
            existing = invitation.developer(registry, target)
            if existing and existing["status"] == "active":
                continue
            if invitation.invitation_expired(value, expiry_days):
                number = int(value.get("number"))
                if number > 0:
                    expired.append(number)
        except (invitation.InvitationError, TypeError, ValueError):
            continue
    return expired


def _validate_command(args: argparse.Namespace) -> int:
    event = invitation.read_json(args.event)
    if not isinstance(event, dict):
        raise invitation.InvitationError("GitHub event payload must be a JSON object")
    registry = invitation.load_registry(args.registry)
    expiry_days = (
        invitation.load_policy(args.policy)["expiryDays"] if args.policy else 30
    )
    values = validate_event(
        args.kind,
        event,
        registry,
        expiry_days=expiry_days,
    )
    _write_output(values)
    print(json.dumps(values, sort_keys=True))
    return 0


def _expired_command(args: argparse.Namespace) -> int:
    issues = invitation.read_json(args.issues)
    if not isinstance(issues, list):
        raise invitation.InvitationError("Issue listing must be a JSON array")
    registry = invitation.load_registry(args.registry)
    expiry_days = invitation.load_policy(args.policy)["expiryDays"]
    for number in expired_pending_issue_numbers(issues, registry, expiry_days):
        print(number)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Project Forge onboarding portal validation and lifecycle helpers"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate")
    validate.add_argument(
        "--kind",
        choices=["invite", "claim", "decline", "doctor"],
        required=True,
    )
    validate.add_argument("--event", required=True, type=Path)
    validate.add_argument("--registry", required=True, type=Path)
    validate.add_argument("--policy", type=Path)
    validate.set_defaults(func=_validate_command)

    expired = commands.add_parser("list-expired-pending")
    expired.add_argument("--issues", required=True, type=Path)
    expired.add_argument("--registry", required=True, type=Path)
    expired.add_argument("--policy", required=True, type=Path)
    expired.set_defaults(func=_expired_command)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return int(args.func(args))
    except (OSError, ValueError, invitation.InvitationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
