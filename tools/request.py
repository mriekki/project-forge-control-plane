#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

REQUEST_PREFIX = "[generate-project]"
SYNC_REQUEST_PREFIX = "[sync-core]"
RESERVED_PROJECT_FORGE_REPOSITORY_PREFIX = "project-forge-"


class RequestError(RuntimeError):
    pass


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RequestError(f"File not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RequestError(f"Invalid JSON in {path}: {exc}") from exc


def load_allowed_owners(path: Path) -> set[str]:
    data = read_json(path)
    if data.get("schemaVersion") != 1:
        raise RequestError("Unsupported allowed-owner schemaVersion")
    owners = data.get("owners")
    if not isinstance(owners, list) or not owners:
        raise RequestError("allowed owners must be a non-empty list")
    normalized: set[str] = set()
    for owner in owners:
        value = str(owner or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})", value):
            raise RequestError(f"Invalid allowed GitHub owner: {value!r}")
        normalized.add(value.lower())
    return normalized


def _parse_target_request(
    event: dict[str, Any],
    allowed_owners: set[str],
    *,
    prefix: str,
    request_label: str,
) -> dict[str, str]:
    issue = event.get("issue")
    if not isinstance(issue, dict):
        raise RequestError(f"{request_label} requires a GitHub issue event")

    body = str(issue.get("body") or "")
    if body.strip():
        raise RequestError(
            f"{request_label} request body must be empty; keep private target details in the target repository"
        )

    author = str((issue.get("user") or {}).get("login") or "").strip()
    title = str(issue.get("title") or "").strip()
    match = re.fullmatch(rf"{re.escape(prefix)}\s+([^/\s]+)/([^/\s]+)", title)
    if not match:
        raise RequestError(f"Issue title must be exactly '{prefix} owner/repository'")

    owner, repository_name = match.groups()
    if author.lower() != owner.lower():
        raise RequestError(
            f"{request_label} request author must own the target repository ({owner}); found {author or 'unknown'}"
        )
    if owner.lower() not in allowed_owners:
        raise RequestError(f"Target owner is not enabled for this control plane: {owner}")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", repository_name):
        raise RequestError(f"Invalid target repository name: {repository_name!r}")
    if repository_name.lower().startswith(RESERVED_PROJECT_FORGE_REPOSITORY_PREFIX):
        raise RequestError(
            f"Refusing reserved Project Forge repository namespace as {request_label.lower()} target: {owner}/{repository_name}"
        )

    repository = f"{owner}/{repository_name}"
    number = str(issue.get("number") or "")
    if not number.isdigit():
        raise RequestError("Issue number is missing or invalid")

    return {
        "target_owner": owner,
        "target_name": repository_name,
        "target_repository": repository,
        "request_author": author,
        "issue_number": number,
    }


def parse_request(event: dict[str, Any], allowed_owners: set[str]) -> dict[str, str]:
    return _parse_target_request(
        event,
        allowed_owners,
        prefix=REQUEST_PREFIX,
        request_label="Generation",
    )


def parse_sync_request(event: dict[str, Any], allowed_owners: set[str]) -> dict[str, str]:
    return _parse_target_request(
        event,
        allowed_owners,
        prefix=SYNC_REQUEST_PREFIX,
        request_label="Core sync",
    )


def write_github_output(values: dict[str, str]) -> None:
    destination = os.getenv("GITHUB_OUTPUT")
    if not destination:
        return
    with Path(destination).open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            if "\n" in value or "\r" in value:
                raise RequestError(f"Unsafe multiline output: {key}")
            handle.write(f"{key}={value}\n")


def extract_command(args: argparse.Namespace) -> int:
    allowed = load_allowed_owners(args.allowed_owners)
    event = read_json(args.event)
    if args.request_type == "generate-project":
        values = parse_request(event, allowed)
        label = "generation"
    else:
        values = parse_sync_request(event, allowed)
        label = "Core sync"
    write_github_output(values)
    print(f"Validated public {label} request for {values['target_repository']}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Project Forge control-plane requests")
    sub = parser.add_subparsers(dest="command", required=True)

    extract = sub.add_parser("extract", help="Validate an issue request and emit target metadata")
    extract.add_argument("--event", required=True, type=Path)
    extract.add_argument("--allowed-owners", required=True, type=Path)
    extract.add_argument(
        "--request-type",
        choices=("generate-project", "sync-core"),
        default="generate-project",
        help="Public request contract to validate",
    )
    extract.set_defaults(func=extract_command)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        return args.func(args)
    except RequestError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
