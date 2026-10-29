#!/usr/bin/env python3
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
from typing import Any

import invitation

STATE_PREFIX = "<!-- project-forge-onboarding-state:v1 "
STATE_SUFFIX = " -->"
VALID_KINDS = {"invite", "test-invite"}
TEST_INVITE_PREFIX = "[test-invite-forge]"


class OnboardingIssueStateError(RuntimeError):
    pass


def render_state(kind: str, target_owner: str) -> str:
    if kind not in VALID_KINDS:
        raise OnboardingIssueStateError(f"Unsupported onboarding issue state kind: {kind}")
    target = invitation.normalize_login(target_owner)
    payload = json.dumps(
        {"kind": kind, "targetOwner": target},
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"{STATE_PREFIX}{payload}{STATE_SUFFIX}"


def parse_state(body: object, *, expected_kind: str | None = None) -> dict[str, str]:
    text = str(body or "").strip()
    if not text.startswith(STATE_PREFIX) or not text.endswith(STATE_SUFFIX):
        raise OnboardingIssueStateError("Onboarding issue state marker is missing")
    payload_text = text[len(STATE_PREFIX) : -len(STATE_SUFFIX)]
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise OnboardingIssueStateError("Onboarding issue state marker contains invalid JSON") from exc
    if not isinstance(payload, dict) or set(payload) != {"kind", "targetOwner"}:
        raise OnboardingIssueStateError("Onboarding issue state marker has an invalid schema")
    kind = str(payload.get("kind") or "")
    if kind not in VALID_KINDS:
        raise OnboardingIssueStateError(f"Unsupported onboarding issue state kind: {kind}")
    if expected_kind is not None and kind != expected_kind:
        raise OnboardingIssueStateError(
            f"Onboarding issue state kind mismatch: expected {expected_kind}, found {kind}"
        )
    target = invitation.normalize_login(payload.get("targetOwner"))
    return {"kind": kind, "target_owner": target}


def normalize_event(event: dict[str, Any], *, kind: str) -> dict[str, Any]:
    if kind not in VALID_KINDS:
        raise OnboardingIssueStateError(f"Unsupported onboarding issue state kind: {kind}")
    normalized = deepcopy(event)
    issue = invitation.issue_from_event(normalized)
    state = parse_state(issue.get("body"), expected_kind=kind)
    target = state["target_owner"]
    issue["title"] = (
        f"{invitation.INVITE_PREFIX} {target}"
        if kind == "invite"
        else f"{TEST_INVITE_PREFIX} {target}"
    )
    issue["body"] = ""
    return normalized


def normalize_issue_listing(issues: list[Any]) -> list[Any]:
    normalized = deepcopy(issues)
    for issue in normalized:
        if not isinstance(issue, dict):
            continue
        body = str(issue.get("body") or "")
        if STATE_PREFIX not in body:
            continue
        state = parse_state(body)
        if state["kind"] != "invite":
            continue
        issue["title"] = f"{invitation.INVITE_PREFIX} {state['target_owner']}"
        issue["body"] = ""
    return normalized


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise OnboardingIssueStateError(f"File not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise OnboardingIssueStateError(f"Invalid JSON in {path}: {exc}") from exc


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def command_render(args: argparse.Namespace) -> int:
    print(render_state(args.kind, args.target_owner))
    return 0


def command_normalize_event(args: argparse.Namespace) -> int:
    event = _read_json(args.event)
    if not isinstance(event, dict):
        raise OnboardingIssueStateError("GitHub event payload must be a JSON object")
    _write_json(args.output, normalize_event(event, kind=args.kind))
    return 0


def command_normalize_issues(args: argparse.Namespace) -> int:
    issues = _read_json(args.issues)
    if not isinstance(issues, list):
        raise OnboardingIssueStateError("Issue listing must be a JSON array")
    _write_json(args.output, normalize_issue_listing(issues))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Persist and normalize human-facing Project Forge onboarding issues"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    render = commands.add_parser("render")
    render.add_argument("--kind", choices=sorted(VALID_KINDS), required=True)
    render.add_argument("--target-owner", required=True)
    render.set_defaults(func=command_render)

    normalize = commands.add_parser("normalize-event")
    normalize.add_argument("--kind", choices=sorted(VALID_KINDS), required=True)
    normalize.add_argument("--event", type=Path, required=True)
    normalize.add_argument("--output", type=Path, required=True)
    normalize.set_defaults(func=command_normalize_event)

    listing = commands.add_parser("normalize-issues")
    listing.add_argument("--issues", type=Path, required=True)
    listing.add_argument("--output", type=Path, required=True)
    listing.set_defaults(func=command_normalize_issues)

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        return int(args.func(args))
    except (OnboardingIssueStateError, invitation.InvitationError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
