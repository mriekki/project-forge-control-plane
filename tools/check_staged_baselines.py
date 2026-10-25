#!/usr/bin/env python3
"""Validate staged Project Forge/component baseline hashes against Git index blobs.

Generation validates package-managed bytes before copying them into the target checkout.
This checker validates the *staged Git tree* immediately before commit/push so Git clean
filters, line-ending normalization, or other index-time transformations cannot silently
change content-addressed managed files after generation-time validation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any


class StagedBaselineError(RuntimeError):
    pass


def _git(root: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).decode("utf-8", errors="replace").strip()
        raise StagedBaselineError(
            f"Git command failed ({completed.returncode}): git {' '.join(args)}"
            + (f"\n{detail}" if detail else "")
        )
    return completed.stdout


def _safe_path(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise StagedBaselineError(f"{label} must be a non-empty relative path")
    if "\\" in value:
        raise StagedBaselineError(f"{label} must use forward slashes: {value}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise StagedBaselineError(f"Unsafe {label}: {value}")
    return pure.as_posix()


def _staged_bytes(root: Path, path: str) -> bytes:
    safe = _safe_path(path, "staged path")
    return _git(root, "show", f":{safe}")


def _staged_json(root: Path, path: str) -> dict[str, Any]:
    raw = _staged_bytes(root, path)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StagedBaselineError(f"Unable to parse staged {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise StagedBaselineError(f"Staged {path} must contain a JSON object")
    return value


def _project_component_metadata(
    component: str,
    metadata: dict[str, Any],
    schema_version: int,
) -> dict[str, Any]:
    if schema_version == 1:
        result = {
            "revision": metadata.get("commit"),
            "distribution": metadata.get("distribution"),
        }
        if component == "core":
            result["version"] = metadata.get("version")
        return result
    if schema_version == 2:
        result = {
            "revision": metadata.get("revision"),
            "distribution": metadata.get("distribution"),
        }
        if component == "core":
            result["version"] = metadata.get("version")
        return result
    raise StagedBaselineError("Unsupported staged PROJECT_FORGE_BASELINE.json schemaVersion")


def _component_baseline_metadata(
    component: str,
    baseline: dict[str, Any],
    baseline_name: str,
) -> dict[str, Any]:
    schema_version = baseline.get("schemaVersion")
    if schema_version == 1:
        if component == "core":
            return {
                "revision": baseline.get("coreCommit"),
                "version": baseline.get("coreVersion"),
                "distribution": baseline.get("distribution"),
            }
        if component == "deployment":
            return {
                "revision": baseline.get("deploymentKitCommit"),
                "distribution": baseline.get("distribution"),
            }
    elif schema_version == 2:
        if baseline.get("component") != component:
            raise StagedBaselineError(
                f"Staged {baseline_name} component does not match staged PROJECT_FORGE_BASELINE.json"
            )
        result = {
            "revision": baseline.get("revision"),
            "distribution": baseline.get("distribution"),
        }
        if component == "core":
            result["version"] = baseline.get("version")
        return result
    else:
        raise StagedBaselineError(f"Unsupported staged {baseline_name} schemaVersion")
    raise StagedBaselineError(
        f"Unsupported Project Forge component in staged baseline: {component}"
    )


def _validate_component(
    root: Path,
    component: str,
    project_forge_component: dict[str, Any],
    baseline_name: str,
    project_schema_version: int,
    global_seen: dict[str, tuple[str, str]],
) -> int:
    baseline = _staged_json(root, baseline_name)
    if baseline.get("schemaVersion") != project_schema_version:
        raise StagedBaselineError(
            f"Staged {baseline_name} schemaVersion does not match staged PROJECT_FORGE_BASELINE.json"
        )

    expected = _project_component_metadata(
        component,
        project_forge_component,
        project_schema_version,
    )
    actual = _component_baseline_metadata(component, baseline, baseline_name)
    for key, expected_value in expected.items():
        if expected_value is not None and actual.get(key) != expected_value:
            raise StagedBaselineError(
                f"Staged {baseline_name} {key} does not match staged PROJECT_FORGE_BASELINE.json"
            )

    managed = baseline.get("managedPaths")
    if not isinstance(managed, list) or not managed:
        raise StagedBaselineError(f"Staged {baseline_name} managedPaths is missing or empty")

    local_seen: set[str] = set()
    count = 0
    for item in managed:
        if not isinstance(item, dict):
            raise StagedBaselineError(f"Invalid managedPaths entry in staged {baseline_name}")
        relative = _safe_path(item.get("path"), f"{baseline_name} managed path")
        expected_hash = item.get("sha256")
        if not isinstance(expected_hash, str) or len(expected_hash) != 64:
            raise StagedBaselineError(f"Invalid managed hash in staged {baseline_name}: {relative}")
        if relative in local_seen:
            raise StagedBaselineError(f"Duplicate managed path in staged {baseline_name}: {relative}")
        prior = global_seen.get(relative)
        if prior is not None:
            prior_component, prior_baseline = prior
            raise StagedBaselineError(
                f"Managed path is owned by multiple staged components: {relative}; "
                f"{prior_component} ({prior_baseline}) and {component} ({baseline_name})"
            )
        local_seen.add(relative)
        global_seen[relative] = (component, baseline_name)

        actual_hash = hashlib.sha256(_staged_bytes(root, relative)).hexdigest()
        if actual_hash != expected_hash:
            raise StagedBaselineError(
                f"Staged managed file drift in {baseline_name}: {relative}; "
                f"expected {expected_hash}, found {actual_hash}"
            )
        count += 1

    return count


def validate_staged_baselines(root: Path) -> int:
    root = root.resolve()
    manifest = _staged_json(root, "PROJECT_BOOTSTRAP.json")
    approved = (manifest.get("generation") or {}).get("project-forge") or {}
    project_forge = _staged_json(root, "PROJECT_FORGE_BASELINE.json")

    project_schema_version = project_forge.get("schemaVersion")
    if project_schema_version not in {1, 2}:
        raise StagedBaselineError("Unsupported staged PROJECT_FORGE_BASELINE.json schemaVersion")
    for key in ("package", "version", "profile"):
        if project_forge.get(key) != approved.get(key):
            raise StagedBaselineError(
                f"Staged PROJECT_FORGE_BASELINE.json {key} does not match staged PROJECT_BOOTSTRAP.json"
            )

    components = project_forge.get("components")
    if not isinstance(components, dict) or not components:
        raise StagedBaselineError("Staged PROJECT_FORGE_BASELINE.json components is missing or empty")

    global_seen: dict[str, tuple[str, str]] = {}
    total = 0
    for component, metadata in sorted(components.items()):
        if not isinstance(metadata, dict):
            raise StagedBaselineError(f"Invalid staged Project Forge component metadata: {component}")
        if component == "core":
            baseline_name = "CORE_BASELINE.json"
        elif component == "deployment":
            baseline_name = "DEPLOYMENT_BASELINE.json"
        else:
            raise StagedBaselineError(f"Unsupported staged Project Forge component: {component}")
        total += _validate_component(
            root,
            component,
            metadata,
            baseline_name,
            project_schema_version,
            global_seen,
        )

    return total


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Git worktree root")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        total = validate_staged_baselines(args.root)
    except StagedBaselineError as exc:
        print(f"FAIL staged Project Forge managed baselines: {exc}", file=sys.stderr)
        return 2
    print(f"PASS staged Project Forge managed baselines ({total} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
