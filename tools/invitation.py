#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

INVITE_PREFIX = "[invite-project-forge]"
REVOKE_PREFIX = "[revoke-project-forge]"
ACCEPT_COMMAND = "/accept-project-forge"
DECLINE_COMMAND = "/decline-project-forge"
DOCTOR_COMMAND = "/project-forge-doctor"

VALID_ROLES = {"admin", "project-author"}
VALID_STATUSES = {"active", "revoked"}
VALID_CAPABILITIES = {
    "generate-project",
    "sync-core",
    "invite-developer",
    "revoke-developer",
}
LOGIN_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})")


class InvitationError(RuntimeError):
    pass


def read_json(path: Path) -> dict[str, Any] | list[Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise InvitationError(f"File not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise InvitationError(f"Invalid JSON in {path}: {exc}") from exc


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def normalize_login(value: object) -> str:
    login = str(value or "").strip()
    if not LOGIN_RE.fullmatch(login):
        raise InvitationError(f"Invalid GitHub owner: {login!r}")
    return login


def load_policy(path: Path) -> dict[str, int]:
    data = read_json(path)
    if not isinstance(data, dict) or data.get("schemaVersion") != 1:
        raise InvitationError("Unsupported invitation policy schemaVersion")
    days = data.get("expiryDays")
    if not isinstance(days, int) or not 1 <= days <= 365:
        raise InvitationError("invitation expiryDays must be an integer from 1 to 365")
    return {"expiryDays": days}


def load_registry(path: Path) -> dict[str, Any]:
    data = read_json(path)
    if not isinstance(data, dict) or data.get("schemaVersion") != 1:
        raise InvitationError("Unsupported developer registry schemaVersion")
    developers = data.get("developers")
    if not isinstance(developers, list) or not developers:
        raise InvitationError("developer registry must contain a non-empty developers list")

    seen: set[str] = set()
    active_admins = 0
    for record in developers:
        if not isinstance(record, dict):
            raise InvitationError("developer records must be objects")
        owner = normalize_login(record.get("githubOwner"))
        key = owner.lower()
        if key in seen:
            raise InvitationError(f"Duplicate developer: {owner}")
        seen.add(key)

        status = record.get("status")
        role = record.get("role")
        channel = record.get("contractChannel")
        capabilities = record.get("capabilities")
        if status not in VALID_STATUSES:
            raise InvitationError(f"Invalid developer status for {owner}: {status!r}")
        if role not in VALID_ROLES:
            raise InvitationError(f"Invalid developer role for {owner}: {role!r}")
        if channel != "stable":
            raise InvitationError(f"Unsupported contract channel for {owner}: {channel!r}")
        if not isinstance(capabilities, list):
            raise InvitationError(f"Capabilities must be a list for {owner}")
        if len(set(capabilities)) != len(capabilities):
            raise InvitationError(f"Duplicate capabilities for {owner}")
        unknown = set(capabilities) - VALID_CAPABILITIES
        if unknown:
            raise InvitationError(f"Unknown capabilities for {owner}: {sorted(unknown)}")
        if status == "revoked" and capabilities:
            raise InvitationError(f"Revoked developer must have no capabilities: {owner}")
        if role == "project-author" and ({"invite-developer", "revoke-developer"} & set(capabilities)):
            raise InvitationError(f"Project author cannot have admin capabilities: {owner}")
        if status == "active" and role == "admin":
            required = {"generate-project", "sync-core", "invite-developer", "revoke-developer"}
            if not required <= set(capabilities):
                raise InvitationError(f"Active admin is missing required capabilities: {owner}")
            active_admins += 1

    if active_admins < 1:
        raise InvitationError("Developer registry must retain at least one active admin")
    return data


def developer(data: dict[str, Any], owner: str) -> dict[str, Any] | None:
    key = owner.lower()
    for record in data["developers"]:
        if str(record["githubOwner"]).lower() == key:
            return record
    return None


def require_capability(data: dict[str, Any], owner: str, capability: str) -> dict[str, Any]:
    record = developer(data, owner)
    if not record or record["status"] != "active" or capability not in record["capabilities"]:
        raise InvitationError(f"GitHub owner is not authorized for {capability}: {owner}")
    return record


def load_allowed_owners(path: Path) -> list[str]:
    data = read_json(path)
    if not isinstance(data, dict) or data.get("schemaVersion") != 1:
        raise InvitationError("Unsupported allowed-owner schemaVersion")
    owners = data.get("owners")
    if not isinstance(owners, list):
        raise InvitationError("allowed owners must be a list")
    return [normalize_login(item) for item in owners]


def projected_allowed_owners(data: dict[str, Any]) -> list[str]:
    return [
        record["githubOwner"]
        for record in data["developers"]
        if record["status"] == "active" and "generate-project" in record["capabilities"]
    ]


def validate_projection(registry: dict[str, Any], allowed_path: Path) -> None:
    actual = [item.lower() for item in load_allowed_owners(allowed_path)]
    expected = [item.lower() for item in projected_allowed_owners(registry)]
    if actual != expected:
        raise InvitationError(
            "config/allowed-owners.json must exactly mirror active generate-project developers"
        )


def write_projection(registry: dict[str, Any], allowed_path: Path) -> None:
    write_json(
        allowed_path,
        {"schemaVersion": 1, "owners": projected_allowed_owners(registry)},
    )


def issue_from_event(event: dict[str, Any]) -> dict[str, Any]:
    issue = event.get("issue")
    if not isinstance(issue, dict):
        raise InvitationError("Expected a GitHub issue event")
    return issue


def issue_author(issue: dict[str, Any]) -> str:
    return normalize_login((issue.get("user") or {}).get("login"))


def issue_number(issue: dict[str, Any]) -> str:
    number = str(issue.get("number") or "")
    if not number.isdigit():
        raise InvitationError("Issue number is missing or invalid")
    return number


def require_empty_body(issue: dict[str, Any], label: str) -> None:
    if str(issue.get("body") or "").strip():
        raise InvitationError(f"{label} issue body must be empty")


def parse_title(issue: dict[str, Any], prefix: str) -> str:
    title = str(issue.get("title") or "").strip()
    match = re.fullmatch(rf"{re.escape(prefix)}\s+([A-Za-z0-9](?:[A-Za-z0-9-]{{0,38}}))", title)
    if not match:
        raise InvitationError(f"Issue title must be exactly '{prefix} github-owner'")
    return normalize_login(match.group(1))


def parse_github_time(value: object) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise InvitationError("Invitation creation time is missing")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvitationError(f"Invalid invitation creation time: {text!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def invitation_expired(
    issue: dict[str, Any],
    expiry_days: int,
    *,
    now: datetime | None = None,
) -> bool:
    created = parse_github_time(issue.get("created_at") or issue.get("createdAt"))
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return current >= created + timedelta(days=expiry_days)


def extract_invite(event: dict[str, Any], registry: dict[str, Any]) -> dict[str, str]:
    issue = issue_from_event(event)
    require_empty_body(issue, "Invitation")
    target = parse_title(issue, INVITE_PREFIX)
    author = issue_author(issue)
    require_capability(registry, author, "invite-developer")
    existing = developer(registry, target)
    if existing and existing["status"] == "active":
        raise InvitationError(f"Developer is already active: {target}")
    return {
        "target_owner": target,
        "request_author": author,
        "issue_number": issue_number(issue),
    }


def require_open_invitation(issue: dict[str, Any]) -> None:
    if issue.get("state") != "open":
        raise InvitationError("Invitation is not open; ask an admin for a fresh invitation")


def extract_claim(
    event: dict[str, Any],
    registry: dict[str, Any],
    *,
    expiry_days: int = 30,
    now: datetime | None = None,
) -> dict[str, str]:
    issue = issue_from_event(event)
    require_open_invitation(issue)
    require_empty_body(issue, "Invitation")
    target = parse_title(issue, INVITE_PREFIX)
    inviter = issue_author(issue)
    require_capability(registry, inviter, "invite-developer")
    if invitation_expired(issue, expiry_days, now=now):
        raise InvitationError("Invitation has expired; ask an admin to create a new invitation")

    comment = event.get("comment")
    if not isinstance(comment, dict):
        raise InvitationError("Invitation claim requires an issue_comment event")
    body = str(comment.get("body") or "").strip()
    if body != ACCEPT_COMMAND:
        raise InvitationError(f"Invitation claim comment must be exactly '{ACCEPT_COMMAND}'")
    claimant = normalize_login((comment.get("user") or {}).get("login"))
    if claimant.lower() != target.lower():
        raise InvitationError(
            f"Invitation may only be claimed by {target}; found {claimant}"
        )
    existing = developer(registry, target)
    if existing and existing["status"] == "active":
        raise InvitationError(f"Developer is already active: {target}")
    return {
        "target_owner": target,
        "request_author": inviter,
        "claimant": claimant,
        "issue_number": issue_number(issue),
    }


def extract_decline(event: dict[str, Any], registry: dict[str, Any]) -> dict[str, str]:
    issue = issue_from_event(event)
    require_open_invitation(issue)
    require_empty_body(issue, "Invitation")
    target = parse_title(issue, INVITE_PREFIX)
    inviter = issue_author(issue)
    require_capability(registry, inviter, "invite-developer")
    comment = event.get("comment")
    if not isinstance(comment, dict):
        raise InvitationError("Invitation decline requires an issue_comment event")
    if str(comment.get("body") or "").strip() != DECLINE_COMMAND:
        raise InvitationError(f"Invitation decline comment must be exactly '{DECLINE_COMMAND}'")
    actor = normalize_login((comment.get("user") or {}).get("login"))
    if actor.lower() != target.lower():
        raise InvitationError(f"Invitation may only be declined by {target}; found {actor}")
    return {
        "target_owner": target,
        "request_author": inviter,
        "claimant": actor,
        "issue_number": issue_number(issue),
    }


def expired_issue_numbers(
    issues: list[Any],
    expiry_days: int,
    *,
    now: datetime | None = None,
) -> list[int]:
    expired: list[int] = []
    for value in issues:
        if not isinstance(value, dict):
            continue
        title = str(value.get("title") or "").strip()
        if not title.startswith(f"{INVITE_PREFIX} "):
            continue
        try:
            parse_title(value, INVITE_PREFIX)
            if invitation_expired(value, expiry_days, now=now):
                number = int(value.get("number"))
                if number > 0:
                    expired.append(number)
        except (InvitationError, TypeError, ValueError):
            continue
    return expired


def active_admin_count(registry: dict[str, Any]) -> int:
    return sum(
        1
        for record in registry["developers"]
        if record["status"] == "active" and record["role"] == "admin"
    )


def extract_revoke(event: dict[str, Any], registry: dict[str, Any]) -> dict[str, str]:
    issue = issue_from_event(event)
    require_empty_body(issue, "Revocation")
    target = parse_title(issue, REVOKE_PREFIX)
    author = issue_author(issue)
    require_capability(registry, author, "revoke-developer")
    existing = developer(registry, target)
    if not existing or existing["status"] != "active":
        raise InvitationError(f"Developer is not active: {target}")
    if existing["role"] == "admin" and active_admin_count(registry) <= 1:
        raise InvitationError("Refusing to revoke the last active Project Forge admin")
    return {
        "target_owner": target,
        "request_author": author,
        "issue_number": issue_number(issue),
    }


def extract_doctor(event: dict[str, Any], registry: dict[str, Any]) -> dict[str, str]:
    issue = issue_from_event(event)
    target = parse_title(issue, INVITE_PREFIX)
    comment = event.get("comment")
    if not isinstance(comment, dict):
        raise InvitationError("Onboarding doctor requires an issue_comment event")
    if str(comment.get("body") or "").strip() != DOCTOR_COMMAND:
        raise InvitationError(f"Doctor comment must be exactly '{DOCTOR_COMMAND}'")
    actor = normalize_login((comment.get("user") or {}).get("login"))
    if actor.lower() != target.lower():
        require_capability(registry, actor, "invite-developer")
    record = developer(registry, target)
    if not record or record["status"] != "active":
        raise InvitationError(f"Developer is not ACTIVE: {target}")
    return {
        "target_owner": target,
        "request_author": actor,
        "issue_number": issue_number(issue),
    }


def load_registry_from_value(data: dict[str, Any]) -> dict[str, Any]:
    import tempfile
    with tempfile.TemporaryDirectory() as holder:
        path = Path(holder) / "developers.json"
        write_json(path, data)
        return load_registry(path)


def activate(
    registry_path: Path,
    allowed_path: Path,
    *,
    owner: str,
    invited_by: str,
    issue: int,
) -> dict[str, Any]:
    registry = load_registry(registry_path)
    require_capability(registry, invited_by, "invite-developer")
    owner = normalize_login(owner)
    record = developer(registry, owner)
    value = {
        "githubOwner": owner,
        "status": "active",
        "role": "project-author",
        "contractChannel": "stable",
        "capabilities": ["generate-project", "sync-core"],
        "invitedBy": invited_by,
        "activationIssue": issue,
    }
    if record is None:
        registry["developers"].append(value)
    else:
        record.clear()
        record.update(value)
    load_registry_from_value(registry)
    write_json(registry_path, registry)
    write_projection(registry, allowed_path)
    validate_projection(registry, allowed_path)
    return value


def revoke(
    registry_path: Path,
    allowed_path: Path,
    *,
    owner: str,
    revoked_by: str,
    issue: int,
) -> dict[str, Any]:
    registry = load_registry(registry_path)
    require_capability(registry, revoked_by, "revoke-developer")
    owner = normalize_login(owner)
    record = developer(registry, owner)
    if not record or record["status"] != "active":
        raise InvitationError(f"Developer is not active: {owner}")
    if record["role"] == "admin" and active_admin_count(registry) <= 1:
        raise InvitationError("Refusing to revoke the last active Project Forge admin")
    record["status"] = "revoked"
    record["capabilities"] = []
    record["revokedBy"] = revoked_by
    record["revocationIssue"] = issue
    load_registry_from_value(registry)
    write_json(registry_path, registry)
    write_projection(registry, allowed_path)
    validate_projection(registry, allowed_path)
    return record


def write_github_output(values: dict[str, str]) -> None:
    destination = os.getenv("GITHUB_OUTPUT")
    if not destination:
        return
    with Path(destination).open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            if "\n" in value or "\r" in value:
                raise InvitationError(f"Unsafe multiline output: {key}")
            handle.write(f"{key}={value}\n")


def command_extract(args: argparse.Namespace, kind: str) -> int:
    registry = load_registry(args.registry)
    event = read_json(args.event)
    if not isinstance(event, dict):
        raise InvitationError("GitHub event payload must be a JSON object")
    if kind == "claim":
        expiry_days = load_policy(args.policy)["expiryDays"]
        values = extract_claim(event, registry, expiry_days=expiry_days)
    else:
        parser = {
            "invite": extract_invite,
            "decline": extract_decline,
            "revoke": extract_revoke,
            "doctor": extract_doctor,
        }[kind]
        values = parser(event, registry)
    write_github_output(values)
    print(json.dumps(values, indent=2))
    return 0


def command_validate(args: argparse.Namespace) -> int:
    registry = load_registry(args.registry)
    load_policy(args.policy)
    validate_projection(registry, args.allowed_owners)
    print("Developer registry, invitation policy, and authorization projection are valid")
    return 0


def command_activate(args: argparse.Namespace) -> int:
    value = activate(
        args.registry,
        args.allowed_owners,
        owner=args.owner,
        invited_by=args.invited_by,
        issue=args.issue_number,
    )
    print(f"Activated Project Forge developer {value['githubOwner']}")
    return 0


def command_revoke(args: argparse.Namespace) -> int:
    value = revoke(
        args.registry,
        args.allowed_owners,
        owner=args.owner,
        revoked_by=args.revoked_by,
        issue=args.issue_number,
    )
    print(f"Revoked Project Forge developer {value['githubOwner']}")
    return 0


def command_expired(args: argparse.Namespace) -> int:
    issues = read_json(args.issues)
    if not isinstance(issues, list):
        raise InvitationError("Issue listing must be a JSON array")
    expiry_days = load_policy(args.policy)["expiryDays"]
    for number in expired_issue_numbers(issues, expiry_days):
        print(number)
    return 0


def add_extract(sub: argparse._SubParsersAction[argparse.ArgumentParser], name: str) -> None:
    parser = sub.add_parser(name)
    parser.add_argument("--event", required=True, type=Path)
    parser.add_argument("--registry", required=True, type=Path)
    if name == "extract-claim":
        parser.add_argument("--policy", required=True, type=Path)
    parser.set_defaults(func=lambda args, kind=name.removeprefix("extract-"): command_extract(args, kind))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Project Forge developer invitation and registry tooling")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in (
        "extract-invite",
        "extract-claim",
        "extract-decline",
        "extract-revoke",
        "extract-doctor",
    ):
        add_extract(sub, name)

    validate = sub.add_parser("validate-config")
    validate.add_argument("--registry", required=True, type=Path)
    validate.add_argument("--allowed-owners", required=True, type=Path)
    validate.add_argument("--policy", required=True, type=Path)
    validate.set_defaults(func=command_validate)

    activate_parser = sub.add_parser("activate")
    activate_parser.add_argument("--registry", required=True, type=Path)
    activate_parser.add_argument("--allowed-owners", required=True, type=Path)
    activate_parser.add_argument("--owner", required=True)
    activate_parser.add_argument("--invited-by", required=True)
    activate_parser.add_argument("--issue-number", required=True, type=int)
    activate_parser.set_defaults(func=command_activate)

    revoke_parser = sub.add_parser("revoke")
    revoke_parser.add_argument("--registry", required=True, type=Path)
    revoke_parser.add_argument("--allowed-owners", required=True, type=Path)
    revoke_parser.add_argument("--owner", required=True)
    revoke_parser.add_argument("--revoked-by", required=True)
    revoke_parser.add_argument("--issue-number", required=True, type=int)
    revoke_parser.set_defaults(func=command_revoke)

    expired = sub.add_parser("list-expired")
    expired.add_argument("--issues", required=True, type=Path)
    expired.add_argument("--policy", required=True, type=Path)
    expired.set_defaults(func=command_expired)

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        return args.func(args)
    except InvitationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
