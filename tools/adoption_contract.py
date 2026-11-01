#!/usr/bin/env python3
"""Resolve Project Forge remote-adoption compatibility without exposing private source topology."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_DESCRIPTOR_URL = (
    "https://raw.githubusercontent.com/mriekki/project-forge-platform/main/chatgpt/current.json"
)
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class AdoptionContractError(RuntimeError):
    pass


def load_json_source(source: str) -> dict[str, Any]:
    if source.startswith("https://"):
        with urllib.request.urlopen(source, timeout=20) as response:
            raw = response.read().decode("utf-8")
    elif source.startswith("http://"):
        raise AdoptionContractError("Remote Project Forge descriptors must use HTTPS")
    else:
        raw = Path(source).read_text(encoding="utf-8")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise AdoptionContractError("Project Forge descriptor must be a JSON object")
    return value


def protected_source_repository() -> str:
    repository = os.getenv("PROJECT_FORGE_ADOPTION_SOURCE_REPOSITORY", "").strip()
    if not _REPOSITORY_RE.fullmatch(repository):
        raise AdoptionContractError(
            "Protected Adoption source repository configuration is missing or invalid"
        )
    return repository


def resolve_adoption(descriptor: dict[str, Any]) -> dict[str, Any]:
    adoption = descriptor.get("adoption")
    if not isinstance(adoption, dict):
        raise AdoptionContractError("Project Forge descriptor adoption must be an object")
    if adoption.get("manifestFilename") != "PROJECT_ADOPTION.json":
        raise AdoptionContractError(
            "Project Forge descriptor adoption.manifestFilename must be PROJECT_ADOPTION.json"
        )
    kit = adoption.get("kit")
    if not isinstance(kit, dict):
        raise AdoptionContractError("Project Forge descriptor adoption.kit pin is required")
    revision = kit.get("revision")
    protocol_version = kit.get("protocolVersion")
    if not isinstance(revision, str) or not _SHA_RE.fullmatch(revision):
        raise AdoptionContractError(
            "adoption.kit.revision must be an exact lowercase 40-character revision"
        )
    if not isinstance(protocol_version, int) or isinstance(protocol_version, bool) or protocol_version < 1:
        raise AdoptionContractError("adoption.kit.protocolVersion must be a positive integer")
    if "repository" in kit or "commit" in kit:
        raise AdoptionContractError(
            "Privacy-safe adoption.kit.revision must not expose source repository/commit fields"
        )
    protected_source_repository()
    return {"revision": revision, "protocolVersion": protocol_version}


def verify_adoption_source(root: Path, *, protocol_version: int) -> None:
    schema = json.loads((root / "schema" / "project-adoption.schema.json").read_text(encoding="utf-8"))
    properties = schema.get("properties") or {}
    adoption_kit = (properties.get("adoptionKit") or {}).get("properties") or {}
    actual_protocol = (adoption_kit.get("protocolVersion") or {}).get("const")
    if actual_protocol != protocol_version:
        raise AdoptionContractError(
            f"Adoption protocol mismatch: expected {protocol_version!r}, found {actual_protocol!r}"
        )
    if not (root / "installer" / "apply-project-adoption.py").is_file():
        raise AdoptionContractError("Accepted Adoption source is missing remote apply entrypoint")


def write_github_output(values: dict[str, str]) -> None:
    destination = os.getenv("GITHUB_OUTPUT")
    if not destination:
        return
    with Path(destination).open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            if "\n" in value or "\r" in value:
                raise AdoptionContractError(f"Unsafe multiline GitHub output: {key}")
            handle.write(f"{key}={value}\n")


def resolve_command(args: argparse.Namespace) -> int:
    adoption = resolve_adoption(load_json_source(args.descriptor))
    values = {
        "adoption_revision": str(adoption["revision"]),
        "adoption_protocol_version": str(adoption["protocolVersion"]),
    }
    write_github_output(values)
    print(json.dumps(values, sort_keys=True))
    return 0


def verify_command(args: argparse.Namespace) -> int:
    verify_adoption_source(args.root, protocol_version=args.protocol_version)
    print("Accepted Adoption source matches public adoption compatibility")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="adoption_contract.py")
    commands = parser.add_subparsers(dest="command", required=True)
    resolve = commands.add_parser("resolve")
    resolve.add_argument("--descriptor", default=DEFAULT_DESCRIPTOR_URL)
    resolve.set_defaults(func=resolve_command)
    verify = commands.add_parser("verify")
    verify.add_argument("--root", type=Path, required=True)
    verify.add_argument("--protocol-version", type=int, required=True)
    verify.set_defaults(func=verify_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (OSError, ValueError, AdoptionContractError) as exc:
        print(f"Project Forge adoption contract error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
