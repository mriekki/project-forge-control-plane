#!/usr/bin/env python3
"""Fail closed if generated Project Forge baseline JSON changes across publication handoff boundaries."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any


BASELINE_FILES = (
    "PROJECT_FORGE_BASELINE.json",
    "CORE_BASELINE.json",
    "DEPLOYMENT_BASELINE.json",
)


if __package__:
    from .profile_baselines import PROFILES, ProfileBaselineError, filesystem_read, verify_profile
else:
    from profile_baselines import PROFILES, ProfileBaselineError, filesystem_read, verify_profile


class BaselineHandoffError(RuntimeError):
    pass


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_bytes(root: Path, name: str) -> bytes:
    path = root / name
    if not path.is_file():
        raise BaselineHandoffError(f"Missing baseline file: {path}")
    return path.read_bytes()


def _parse_json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BaselineHandoffError(f"Unable to parse {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise BaselineHandoffError(f"{label} must contain a JSON object")
    return value


def _safe_managed_path(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise BaselineHandoffError(f"{label} must be a non-empty relative path")
    if "\\" in value:
        raise BaselineHandoffError(f"{label} must use forward slashes: {value}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise BaselineHandoffError(f"Unsafe {label}: {value}")
    return pure.as_posix()


def _managed_paths(raw: bytes, baseline_name: str) -> set[str]:
    document = _parse_json(raw, baseline_name)
    managed = document.get("managedPaths")
    if not isinstance(managed, list) or not managed:
        raise BaselineHandoffError(f"{baseline_name} managedPaths is missing or empty")

    paths: set[str] = set()
    for item in managed:
        if not isinstance(item, dict):
            raise BaselineHandoffError(f"Invalid managedPaths entry in {baseline_name}")
        relative = _safe_managed_path(item.get("path"), f"{baseline_name} managed path")
        if relative in paths:
            raise BaselineHandoffError(f"Duplicate managed path in {baseline_name}: {relative}")
        paths.add(relative)
    return paths


def _generated_bytes(generated: Path) -> dict[str, bytes]:
    return {name: _read_bytes(generated, name) for name in BASELINE_FILES}


def validate_generated(generated: Path, *, approved_profile: str | None = None) -> dict[str, bytes]:
    generated = generated.resolve()
    if approved_profile is not None:
        try:
            values, count = verify_profile(approved_profile, *filesystem_read(generated))
        except (ProfileBaselineError, OSError) as exc:
            raise BaselineHandoffError(str(exc)) from exc
        print(f"PASS explicit profile baseline ownership ({count} managed paths)")
        return values
    values = _generated_bytes(generated)

    core = _managed_paths(values["CORE_BASELINE.json"], "CORE_BASELINE.json")
    deployment = _managed_paths(values["DEPLOYMENT_BASELINE.json"], "DEPLOYMENT_BASELINE.json")
    overlap = sorted(core & deployment)
    if overlap:
        raise BaselineHandoffError(
            "generated baseline ownership overlap: " + ", ".join(overlap)
        )

    project_forge = _parse_json(values["PROJECT_FORGE_BASELINE.json"], "PROJECT_FORGE_BASELINE.json")
    components = project_forge.get("components")
    if not isinstance(components, dict) or set(components) != {"core", "deployment"}:
        found = sorted(components) if isinstance(components, dict) else []
        raise BaselineHandoffError(
            f"PROJECT_FORGE_BASELINE.json must contain exactly core and deployment components; found {found}"
        )

    for name in BASELINE_FILES:
        print(f"PASS generated {name} sha256={_sha256(values[name])}")
    print(f"PASS generated component ownership is disjoint ({len(core) + len(deployment)} managed paths)")
    return values


def validate_copied(generated: Path, target: Path, *, approved_profile: str | None = None) -> dict[str, bytes]:
    expected = validate_generated(generated, approved_profile=approved_profile)
    if approved_profile is not None:
        validate_generated(target, approved_profile=approved_profile)
    target = target.resolve()
    for name in expected:
        actual = _read_bytes(target, name)
        if actual != expected[name]:
            raise BaselineHandoffError(
                f"generated→target baseline bytes changed: {name}; "
                f"generated={_sha256(expected[name])} target={_sha256(actual)}"
            )
        print(f"PASS copied {name} sha256={_sha256(actual)}")
    return expected


def _git(root: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).decode("utf-8", errors="replace").strip()
        raise BaselineHandoffError(
            f"Git command failed ({completed.returncode}): git {' '.join(args)}"
            + (f"\n{detail}" if detail else "")
        )
    return completed.stdout


def validate_staged(generated: Path, target: Path, *, approved_profile: str | None = None) -> None:
    expected = validate_copied(generated, target, approved_profile=approved_profile)
    target = target.resolve()
    for name in expected:
        staged = _git(target, "show", f":{name}")
        if staged != expected[name]:
            raise BaselineHandoffError(
                f"target→index baseline bytes changed: {name}; "
                f"generated={_sha256(expected[name])} staged={_sha256(staged)}"
            )
        print(f"PASS staged {name} sha256={_sha256(staged)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    generated = subparsers.add_parser("generated", help="Validate generated native baseline ownership")
    generated.add_argument("--generated", type=Path, required=True)

    copied = subparsers.add_parser("copied", help="Compare copied target baselines with generated originals")
    copied.add_argument("--generated", type=Path, required=True)
    copied.add_argument("--target", type=Path, required=True)

    staged = subparsers.add_parser("staged", help="Compare staged baseline blobs with generated originals")
    staged.add_argument("--generated", type=Path, required=True)
    staged.add_argument("--target", type=Path, required=True)
    for command in (generated, copied, staged):
        command.add_argument("--approved-profile", choices=tuple(PROFILES),
                             help="Independently accepted exact generation profile (not authorization)")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "generated":
            validate_generated(args.generated, approved_profile=args.approved_profile)
        elif args.command == "copied":
            validate_copied(args.generated, args.target, approved_profile=args.approved_profile)
        elif args.command == "staged":
            validate_staged(args.generated, args.target, approved_profile=args.approved_profile)
        else:  # pragma: no cover - argparse enforces the command set.
            raise BaselineHandoffError(f"Unsupported command: {args.command}")
    except BaselineHandoffError as exc:
        print(f"FAIL baseline handoff: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
