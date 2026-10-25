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
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$")
PROFILE_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")


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


def _positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise PublicContractError(f"{label} must be a positive integer")
    return value


def validate_descriptor(descriptor: dict[str, Any]) -> list[dict[str, str]]:
    if descriptor.get("schemaVersion") != 1:
        raise PublicContractError("Unsupported public contract schemaVersion")
    if descriptor.get("channel") != "stable":
        raise PublicContractError("Public contract channel must be stable")

    version = _positive_int(descriptor.get("contractVersion"), "contractVersion")
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


def validate_generation_descriptor(descriptor: dict[str, Any]) -> dict[str, Any]:
    control_plane = descriptor.get("controlPlane")
    if not isinstance(control_plane, dict):
        raise PublicContractError("controlPlane must be an object")
    if control_plane.get("repository") != "mriekki/project-forge-control-plane":
        raise PublicContractError("Unexpected public Control Plane repository")

    generation = descriptor.get("generation")
    if not isinstance(generation, dict):
        raise PublicContractError("generation must be an object")
    if generation.get("manifestFilename") != "PROJECT_BOOTSTRAP.json":
        raise PublicContractError("generation.manifestFilename must be PROJECT_BOOTSTRAP.json")

    bootstrap = generation.get("bootstrap")
    if not isinstance(bootstrap, dict):
        raise PublicContractError("generation.bootstrap must be an object")
    forbidden = {
        "repository",
        "commit",
        "sourceRepository",
        "sourceRepositoryUrl",
    }
    leaked = sorted(forbidden & set(bootstrap))
    if leaked:
        raise PublicContractError(
            "generation.bootstrap must not expose private source topology fields: "
            + ", ".join(leaked)
        )

    revision = bootstrap.get("revision")
    if not isinstance(revision, str) or not SHA40_RE.fullmatch(revision):
        raise PublicContractError(
            "generation.bootstrap.revision must be an exact lowercase 40-character revision"
        )
    protocol_version = _positive_int(
        bootstrap.get("protocolVersion"),
        "generation.bootstrap.protocolVersion",
    )
    catalog_version = _positive_int(
        bootstrap.get("catalogVersion"),
        "generation.bootstrap.catalogVersion",
    )

    if generation.get("package") != "@mriekki/project-forge":
        raise PublicContractError(
            "generation.package must be @mriekki/project-forge"
        )
    package_version = generation.get("packageVersion")
    if not isinstance(package_version, str) or not SEMVER_RE.fullmatch(package_version):
        raise PublicContractError(
            "generation.packageVersion must be one exact semantic version"
        )
    profile = generation.get("profile")
    if not isinstance(profile, str) or not PROFILE_RE.fullmatch(profile):
        raise PublicContractError("generation.profile must be a canonical profile identifier")

    legacy_protocol = generation.get("bootstrapProtocolVersion")
    if legacy_protocol != protocol_version:
        raise PublicContractError(
            "generation.bootstrapProtocolVersion must match generation.bootstrap.protocolVersion"
        )

    if descriptor.get("bootstrapUrl") != DEFAULT_DESCRIPTOR_URL:
        raise PublicContractError("bootstrapUrl must point to the canonical stable descriptor")

    return {
        "bootstrapRevision": revision,
        "bootstrapProtocolVersion": protocol_version,
        "bootstrapCatalogVersion": catalog_version,
        "package": generation["package"],
        "packageVersion": package_version,
        "profile": profile,
    }


def verify_public_contract(
    descriptor: dict[str, Any],
    *,
    base_url: str = DEFAULT_BASE_URL,
) -> int:
    documents = validate_descriptor(descriptor)
    validate_generation_descriptor(descriptor)
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
