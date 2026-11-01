#!/usr/bin/env python3
"""Resolve safe target-repository commit/PR presentation for remote adoption."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any

CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
DEFAULT_COMMIT_MESSAGE = "Adopt Project Forge"
DEFAULT_PR_TITLE = "Adopt Project Forge"
DEFAULT_BODY_MODE = "project-forge-summary"
BODY_MODES = {DEFAULT_BODY_MODE, "repository-template"}


class WorkflowPolicyError(RuntimeError):
    pass


def _single_line(value: Any, *, name: str, limit: int) -> str:
    if not isinstance(value, str) or not value or len(value) > limit or CONTROL_RE.search(value):
        raise WorkflowPolicyError(
            f"{name} must be a non-empty single-line string of at most {limit} characters"
        )
    return value


def _safe_repo_path(value: Any, *, name: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value or CONTROL_RE.search(value):
        raise WorkflowPolicyError(f"{name} must be a safe repository-relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise WorkflowPolicyError(f"{name} must be a safe repository-relative path")
    return value


def resolve_repository_workflow(manifest: Any) -> dict[str, str]:
    if not isinstance(manifest, dict):
        raise WorkflowPolicyError("PROJECT_ADOPTION.json root must be an object")
    engineering = manifest.get("engineeringContext")
    if not isinstance(engineering, dict):
        raise WorkflowPolicyError("PROJECT_ADOPTION.json engineeringContext must be an object")

    policy = engineering.get("repositoryWorkflow")
    if policy is None:
        return {
            "commit_message": DEFAULT_COMMIT_MESSAGE,
            "pr_title": DEFAULT_PR_TITLE,
            "pr_body_mode": DEFAULT_BODY_MODE,
            "pr_template_path": "",
        }
    if not isinstance(policy, dict):
        raise WorkflowPolicyError("engineeringContext.repositoryWorkflow must be an object")
    if set(policy) - {"commitMessage", "pullRequest"}:
        raise WorkflowPolicyError("engineeringContext.repositoryWorkflow contains unsupported fields")

    commit_message = _single_line(
        policy.get("commitMessage"),
        name="engineeringContext.repositoryWorkflow.commitMessage",
        limit=200,
    )
    pull_request = policy.get("pullRequest")
    if not isinstance(pull_request, dict) or set(pull_request) - {"title", "body"}:
        raise WorkflowPolicyError("engineeringContext.repositoryWorkflow.pullRequest is invalid")
    pr_title = _single_line(
        pull_request.get("title"),
        name="engineeringContext.repositoryWorkflow.pullRequest.title",
        limit=256,
    )
    body = pull_request.get("body")
    if not isinstance(body, dict) or set(body) - {"mode", "templatePath"}:
        raise WorkflowPolicyError("engineeringContext.repositoryWorkflow.pullRequest.body is invalid")
    mode = body.get("mode")
    if mode not in BODY_MODES:
        raise WorkflowPolicyError(
            "engineeringContext.repositoryWorkflow.pullRequest.body.mode is invalid"
        )

    template_path = body.get("templatePath")
    if mode == "repository-template":
        template_path = _safe_repo_path(
            template_path,
            name="engineeringContext.repositoryWorkflow.pullRequest.body.templatePath",
        )
    elif template_path is not None:
        raise WorkflowPolicyError(
            "engineeringContext.repositoryWorkflow.pullRequest.body.templatePath is only valid for repository-template mode"
        )
    else:
        template_path = ""

    return {
        "commit_message": commit_message,
        "pr_title": pr_title,
        "pr_body_mode": mode,
        "pr_template_path": template_path,
    }


def write_github_output(values: dict[str, str]) -> None:
    destination = Path(str(Path.cwd() / ".project-forge-no-output"))
    github_output = __import__("os").environ.get("GITHUB_OUTPUT")
    if not github_output:
        print(json.dumps(values, sort_keys=True))
        return
    destination = Path(github_output)
    with destination.open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            if CONTROL_RE.search(value):
                raise WorkflowPolicyError(f"unsafe multiline GitHub output: {key}")
            handle.write(f"{key}={value}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args(argv)
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
        values = resolve_repository_workflow(manifest)
        write_github_output(values)
        return 0
    except (OSError, json.JSONDecodeError, WorkflowPolicyError) as exc:
        print(f"Project Forge adoption workflow policy error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
