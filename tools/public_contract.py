#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
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
DEFAULT_BASE_URL = "https://raw.githubusercontent.com/mriekki/project-forge-platform/main/"
REQUIRED_DOCUMENTS = {
    "ADMIN.md",
    "EXISTING_PROJECT.md",
    "NEW_PROJECT.md",
    "ONBOARDING.md",
    "PROJECT_INSTRUCTIONS.md",
    "PROJECT_RULES.md",
    "USER_PROFILE.schema.json",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class PublicContractError(RuntimeError):
    pass


def _read_json(source: str) -> dict[str, Any]:
    if source.startswith("https://"):
        with urllib.request.urlopen(source, timeout=20) as response:
            raw = response.read().decode("utf-8")
    else:
        raw = Path(source).read_text(encoding="utf-8")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise PublicContractError("Public contract descriptor must be a JSON object")
    return value


def validate_descriptor(descriptor: dict[str, Any]) -> list[dict[str, str]]:
    if descriptor.get("schemaVersion") != 1:
        raise PublicContractError("Unsupported public contract schemaVersion")
    if descriptor.get("channel") != "stable":
        raise PublicContractError("Public contract channel must be stable")

    version = descriptor.get("contractVersion")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise PublicContractError("contractVersion must be a positive integer")
    snapshot = descriptor.get("snapshotPath")
    expected_snapshot = f"chatgpt/contracts/v{version}"
    if snapshot != expected_snapshot:
        raise PublicContractError(
            f"snapshotPath must be {expected_snapshot!r}; found {snapshot!r}"
        )

    raw_documents = descriptor.get("documents")
    if not isinstance(raw_documents, list):
        raise PublicContractError("documents must be an array")

    documents: list[dict[str, str]] = []
    seen_paths: set[str] = set()
    names: set[str] = set()
    for index, item in enumerate(raw_documents):
        if not isinstance(item, dict):
            raise PublicContractError(f"documents[{index}] must be an object")
        path = item.get("path")
        digest = item.get("sha256")
        if not isinstance(path, str) or not path.startswith(f"{snapshot}/"):
            raise PublicContractError(
                f"documents[{index}].path must be inside the immutable snapshot"
            )
        if path in seen_paths:
            raise PublicContractError(f"Duplicate public contract document: {path}")
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise PublicContractError(f"Invalid SHA-256 for public contract document: {path}")
        seen_paths.add(path)
        names.add(Path(path).name)
        documents.append({"path": path, "sha256": digest})

    missing = sorted(REQUIRED_DOCUMENTS - names)
    if missing:
        raise PublicContractError(
            f"Public contract descriptor is missing required documents: {', '.join(missing)}"
        )
    return documents


def verify_public_contract(
    descriptor: dict[str, Any],
    *,
    base_url: str = DEFAULT_BASE_URL,
) -> int:
    documents = validate_descriptor(descriptor)
    for item in documents:
        with urllib.request.urlopen(base_url + item["path"], timeout=20) as response:
            data = response.read()
        digest = hashlib.sha256(data).hexdigest()
        if digest != item["sha256"]:
            raise PublicContractError(
                f"Public contract hash mismatch: {item['path']}"
            )
    return int(descriptor["contractVersion"])


def _write_output(version: int) -> None:
    destination = os.getenv("GITHUB_OUTPUT")
    if not destination:
        return
    with Path(destination).open("a", encoding="utf-8") as handle:
        handle.write(f"contract_version={version}\n")


def _verify_command(args: argparse.Namespace) -> int:
    descriptor = _read_json(args.descriptor)
    version = verify_public_contract(descriptor, base_url=args.base_url)
    _write_output(version)
    print(f"Project Forge public ChatGPT contract v{version} verified")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify the public Project Forge ChatGPT contract"
    )
    parser.add_argument("--descriptor", default=DEFAULT_DESCRIPTOR_URL)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return _verify_command(args)
    except (OSError, ValueError, json.JSONDecodeError, PublicContractError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
