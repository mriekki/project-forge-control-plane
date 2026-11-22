#!/usr/bin/env python3
"""Dormant, read-only Bootstrap source binding for protected orchestration.

The caller authenticates the public descriptor and reads repository identity
using a source-only installation token. Binding data is protected operator
configuration, never Builder input. This module does not fetch, issue tokens,
run source code, publish a generated Project, or switch the active workflow.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path

SHA = re.compile(r"[0-9a-f]{40}")
DIGEST = re.compile(r"[0-9a-f]{64}")
REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
SEGMENT = re.compile(r"[A-Za-z0-9_.-]+")
FIELDS = {"schemaVersion", "mode", "logicalRevision", "repository", "repositoryId",
          "sourceCommit", "sourceTree", "sourceRoot"}
PROJECTION = {"schema": "schemas/project-requirements.schema.json",
              "validator": "tools/project_requirements.py"}


class SourceBindingError(ValueError):
    """Redacted verification error; never include the protected binding."""


def need(ok, message):
    if not ok:
        raise SourceBindingError(message)


def exact(value, regex):
    return isinstance(value, str) and regex.fullmatch(value) is not None


def fields(value, keys, label):
    need(isinstance(value, dict) and set(value) == keys, "Invalid " + label)


def safe_root(value):
    need(isinstance(value, str)
         and (value == "" or all(SEGMENT.fullmatch(p) and p not in (".", "..")
                                 and p.casefold() != ".git" for p in value.split("/"))),
         "Invalid protected relative source root")
    return value


def positive(value):
    return type(value) is int and value > 0


def validate_binding_policy(descriptor, binding):
    """Validate a protected binding before any authenticated repository read."""
    fields(binding, FIELDS, "protected source binding")
    need(type(binding["schemaVersion"]) is int and binding["schemaVersion"] == 1
         and binding["mode"] in ("original-owner", "nested-source"),
         "Invalid source binding mode")
    for key in ("logicalRevision", "sourceCommit", "sourceTree"):
        need(exact(binding[key], SHA), "Exact protected Git identity required")
    root = safe_root(binding["sourceRoot"])
    if binding["mode"] == "original-owner":
        need(root == "" and binding["sourceCommit"] == binding["logicalRevision"],
             "Original owner binding must preserve exact revision")
    else:
        need(root != "", "Nested source requires an explicitly reviewed relative root")
    need(exact(binding["repository"], REPO) and positive(binding["repositoryId"]),
         "Invalid protected repository identity")

    generation = descriptor.get("generation") if isinstance(descriptor, dict) else None
    bootstrap = generation.get("bootstrap") if isinstance(generation, dict) else None
    need(isinstance(descriptor, dict) and type(descriptor.get("schemaVersion")) is int
         and descriptor["schemaVersion"] == 1 and descriptor.get("channel") == "stable"
         and isinstance(bootstrap, dict)
         and bootstrap.get("revision") == binding["logicalRevision"]
         and "repository" not in bootstrap and "commit" not in bootstrap
         and positive(bootstrap.get("protocolVersion"))
         and positive(bootstrap.get("catalogVersion")), "Accepted public Bootstrap pin differs")
    projection = bootstrap.get("portableRequirements")
    fields(projection, {"bootstrapRevision", "schema", "validator"}, "public requirements projection")
    need(projection["bootstrapRevision"] == binding["logicalRevision"],
         "Requirements projection revision differs")
    for label, relative in PROJECTION.items():
        entry = projection[label]
        fields(entry, {"path", "url", "sha256"}, "public requirements artifact")
        need(entry["path"] == relative and exact(entry["sha256"], DIGEST)
             and isinstance(entry["url"], str)
             and re.fullmatch(
                 r"https://raw\.githubusercontent\.com/mriekki/project-forge-platform/"
                 r"[0-9a-f]{40}/chatgpt/bootstrap-contracts/[A-Za-z0-9_.-]+", entry["url"]),
             "Invalid public requirements artifact pin")
    return dict(binding)


def resolve_binding(descriptor, binding, authenticated_repo):
    """Compare reviewed binding to accepted public revision and GitHub identity."""
    selected = validate_binding_policy(descriptor, binding)
    need(isinstance(authenticated_repo, dict)
         and authenticated_repo.get("full_name") == binding["repository"]
         and positive(authenticated_repo.get("id"))
         and authenticated_repo.get("id") == binding["repositoryId"]
         and authenticated_repo.get("private") is True
         and authenticated_repo.get("archived") is False,
         "Authenticated source repository identity differs")

    return selected


def git(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=30)
    need(result.returncode == 0, "Source checkout Git verification failed")
    return result.stdout


def checked_root(checkout, value):
    root = checkout
    if value:
        for segment in value.split("/"):
            root = root / segment
            need(root.is_dir() and not root.is_symlink(), "Source root is not a regular directory")
    return root


def verify_checkout(checkout, descriptor, binding, authenticated_repo):
    """Verify exact whole source subtree and working bytes without executing it."""
    selected = resolve_binding(descriptor, binding, authenticated_repo)
    checkout = Path(checkout)
    need(checkout.is_dir() and not checkout.is_symlink(), "Invalid source checkout directory")
    checkout = checkout.resolve(strict=True)
    top = Path(git(checkout, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    need(top == checkout, "Unexpected source checkout root")
    need(git(checkout, "rev-parse", "HEAD").decode().strip() == selected["sourceCommit"],
         "Source checkout commit differs")
    need(not git(checkout, "status", "--porcelain", "--untracked-files=all").strip(),
         "Source checkout is not clean")
    relative = selected["sourceRoot"]
    root = checked_root(checkout, relative)
    ref = "HEAD:" + relative if relative else "HEAD^{tree}"
    need(git(checkout, "rev-parse", ref).decode().strip() == selected["sourceTree"]
         and git(checkout, "cat-file", "-t", selected["sourceTree"]).strip() == b"tree",
         "Whole source subtree differs")
    entries = git(checkout, "ls-tree", "-r", "-z", selected["sourceTree"])
    expected = set()
    for entry in entries.split(b"\x00"):
        if not entry:
            continue
        header, name = entry.split(b"\t", 1)
        mode, kind, oid = header.decode("ascii").split(" ")
        name = name.decode("utf-8")
        parts = name.split("/")
        need(name not in expected and all(p and p not in (".", "..") and p.casefold() != ".git"
                                         and "\\" not in p for p in parts)
             and mode in ("100644", "100755") and kind == "blob" and exact(oid, SHA),
             "Unsafe or duplicate source tree entry")
        target = root
        for part in parts:
            target = target / part
            need(not target.is_symlink(), "Symlink in source checkout refused")
        need(target.is_file() and target.resolve().is_relative_to(root.resolve()),
             "Missing or unsafe source file")
        if os.name == "posix":
            need(bool(target.stat().st_mode & stat.S_IXUSR) == (mode == "100755"),
                 "Source executable mode differs from reviewed tree")
        raw = target.read_bytes()
        blob = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
        need(blob == oid, "Source working bytes differ from reviewed tree")
        expected.add(name)
    need(bool(expected), "Empty Bootstrap source subtree")
    actual = set()
    for directory, directories, files in os.walk(root, followlinks=False):
        current = Path(directory)
        if not relative and current == root:
            # Only the actual checkout metadata is outside the source tree.
            if ".git" in directories:
                directories.remove(".git")
            if ".git" in files:
                files.remove(".git")
        for name in directories:
            entry = current / name
            need(entry.is_dir() and not entry.is_symlink(), "Unexpected source directory")
        for name in files:
            entry = current / name
            need(entry.is_file() and not entry.is_symlink(), "Unexpected source entry type")
            actual.add(entry.relative_to(root).as_posix())
    need(actual == expected, "Extra or missing source working files")

    bootstrap = descriptor["generation"]["bootstrap"]
    catalog = json.loads((root / "catalog/CATALOG.json").read_bytes())
    need(isinstance(catalog, dict) and isinstance(catalog.get("protocol"), dict)
         and catalog["protocol"].get("version") == bootstrap["protocolVersion"]
         and catalog.get("catalogVersion") == bootstrap["catalogVersion"],
         "Bootstrap catalog compatibility differs")
    for label, name in PROJECTION.items():
        payload = (root / name).read_bytes()
        need(hashlib.sha256(payload).hexdigest() ==
             bootstrap["portableRequirements"][label]["sha256"],
             "Portable requirements projection bytes differ")
    # No protected repository, root path or physical Git identity leaves this
    # result. The caller separately retains the verified local root in memory.
    return {"result": "BOOTSTRAP_SOURCE_BINDING_MATCH",
            "logicalRevision": selected["logicalRevision"],
            "protocolVersion": bootstrap["protocolVersion"],
            "catalogVersion": bootstrap["catalogVersion"],
            "fileCount": len(expected), "sourceBindingActivated": False,
            "generationAuthorized": False, "productionAuthorized": False}
