#!/usr/bin/env python3
"""Disposable Git handoff rehearsal; never publishes to GitHub or runs source.

The caller must have separately authenticated the exact source, package and
approved profile and generated the scratch workspace. This helper checks the
approved manifest, managed content, and every generated file through a local
bare Git remote and fresh clone. It issues no tokens, has no network remote,
and cannot establish operational source authority or actual remote acceptance.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

from tools.check_baseline_handoff import validate_generated, validate_copied, validate_staged
from tools.check_staged_baselines import validate_staged_baselines
from tools.check_staged_diff import check_staged_diff
from tools.profile_baselines import PROFILES, FILES, parse, safe_path

MAX_FILES = 20000
MAX_BYTES = 128 * 1024 * 1024


class DisposableHandoffError(ValueError):
    pass


def need(ok, message):
    if not ok:
        raise DisposableHandoffError(message)


def sha256(payload):
    return hashlib.sha256(payload).hexdigest()


def inventory(root, *, git_metadata=False):
    """Exact file bytes and Git executable modes; no links or case collisions."""
    root = Path(root)
    need(root.is_dir() and not root.is_symlink(), "Unsafe workspace root")
    result, seen, total = {}, set(), 0
    for directory, directories, filenames in os.walk(root, followlinks=False):
        current = Path(directory)
        if git_metadata and current == root and ".git" in directories:
            metadata = current / ".git"
            need(metadata.is_dir() and not metadata.is_symlink(), "Unsafe local Git metadata")
            directories.remove(".git")
        for name in directories + filenames:
            p = current / name
            relative = safe_path(p.relative_to(root).as_posix())
            key = relative.casefold()
            need(key not in seen, "Case-colliding generated paths")
            seen.add(key)
            info = p.lstat()
            need(not p.is_symlink(), "Symlink in generated workspace")
            if name in directories:
                need(stat.S_ISDIR(info.st_mode) and name != "__pycache__", "Unsafe generated directory")
                continue
            need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and p.suffix != ".pyc",
                 "Unsafe generated file or bytecode")
            total += info.st_size
            need(len(result) < MAX_FILES and total <= MAX_BYTES, "Generated workspace exceeds proof limits")
            result[relative] = ("100755" if info.st_mode & stat.S_IXUSR else "100644",
                                sha256(p.read_bytes()))
    need(bool(result), "Empty generated workspace")
    return result


def verify_seed(seed_bytes, generated, approved_profile, expected_generation):
    # expected_generation comes from independent package/profile selection,
    # never a generated baseline or target-controlled change.
    seed = parse(seed_bytes)
    actual = parse((generated / "PROJECT_BOOTSTRAP.json").read_bytes())
    need(type(seed.get("schemaVersion")) is int and seed["schemaVersion"] == 2
         and seed.get("state") == "approved", "Approved schema-v2 seed required")
    need(isinstance(seed.get("project"), dict) and seed["project"].get("repository")
         == "example/pf-disposable-generation", "Only fixed synthetic target is permitted")
    need(approved_profile in PROFILES and isinstance(expected_generation, dict)
         and set(expected_generation) == {"package", "version", "profile", "integrity"}
         and expected_generation["package"] == "@mriekki/project-forge"
         and expected_generation["profile"] == approved_profile, "Exact independent profile required")
    selected = seed.get("generation", {}).get("project-forge")
    need(selected == expected_generation, "Approved package selection differs")
    from base64 import b64decode
    try:
        integrity = expected_generation["integrity"]
        need(isinstance(integrity, str) and integrity.startswith("sha512-")
             and len(b64decode(integrity[7:], validate=True)) == 64, "Exact package SRI required")
    except (TypeError, ValueError) as exc:
        raise DisposableHandoffError("Exact package SRI required") from exc
    expected = {**seed, "state": "generated"}
    need(actual == expected, "Generated manifest differs from exact approved seed")
    return actual


def git(root, *arguments, env):
    completed = subprocess.run(["git", "-C", str(root), *arguments], env=env,
                               stdin=subprocess.DEVNULL, capture_output=True, timeout=60)
    need(completed.returncode == 0, "Disposable Git operation refused")
    return completed.stdout


def index_inventory(root, env):
    result = {}
    entries = git(root, "ls-files", "--stage", "-z", env=env)
    for entry in entries.split(b"\0"):
        if not entry:
            continue
        header, name = entry.split(b"\t", 1)
        mode, oid, stage = header.decode("ascii").split()
        relative = safe_path(name.decode("utf-8"))
        need(mode in ("100644", "100755") and stage == "0" and relative not in result,
             "Unsafe staged file mode or index")
        payload = git(root, "cat-file", "blob", oid, env=env)
        result[relative] = (mode, sha256(payload))
    return result


def qualify(generated, seed_bytes, approved_profile, expected_generation, scratch):
    """Call only after real generation in a credential-free disposable runner."""
    generated, scratch = Path(generated), Path(scratch)
    exact = inventory(generated)
    verify_seed(seed_bytes, generated, approved_profile, expected_generation)
    validate_generated(generated, approved_profile=approved_profile)
    # No user target, URL, provider or remote credential may be supplied.
    # Build a private local bare remote and populate a new checkout.
    with tempfile.TemporaryDirectory(prefix="pf-local-generation-", dir=scratch) as tmp:
        root = Path(tmp).resolve()
        home = root / "home"
        home.mkdir()
        env = {"PATH": os.environ["PATH"], "HOME": str(home), "LANG": "C",
               "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
               "GIT_TERMINAL_PROMPT": "0", "GIT_ALLOW_PROTOCOL": "file",
               "GIT_AUTHOR_NAME": "Project Forge disposable proof",
               "GIT_AUTHOR_EMAIL": "proof@example.invalid",
               "GIT_COMMITTER_NAME": "Project Forge disposable proof",
               "GIT_COMMITTER_EMAIL": "proof@example.invalid"}
        bare, target, fresh = (root / name for name in ("remote.git", "target", "fresh"))
        git(root, "init", "--bare", "--initial-branch=main", str(bare), env=env)
        git(root, "clone", "--no-local", "--", str(bare), str(target), env=env)
        git(target, "config", "core.autocrlf", "false", env=env)
        git(target, "config", "core.filemode", "true", env=env)
        git(target, "config", "core.hooksPath", "/dev/null", env=env)
        for name in generated.iterdir():
            dest = target / name.name
            if name.is_dir():
                shutil.copytree(name, dest)
            else:
                shutil.copy2(name, dest)
        need(inventory(target, git_metadata=True) == exact, "Copied generated files differ")
        validate_copied(generated, target, approved_profile=approved_profile)
        git(target, "add", "-A", env=env)
        need(index_inventory(target, env) == exact,
             "Staged inventory differs (ignored file, filter, mode, or byte drift)")
        validate_staged(generated, target, approved_profile=approved_profile)
        validate_staged_baselines(target, approved_profile=approved_profile)
        need(check_staged_diff(target) == 0, "Staged diff check failed")
        git(target, "commit", "-m", "Disposable generated baseline", env=env)
        git(target, "push", "origin", "HEAD:refs/heads/main", env=env)
        git(root, "clone", "--no-local", "--", str(bare), str(fresh), env=env)
        need(inventory(fresh, git_metadata=True) == exact, "Fresh local clone differs")
        validate_generated(fresh, approved_profile=approved_profile)
        verify_seed(seed_bytes, fresh, approved_profile, expected_generation)
        need(inventory(generated) == exact, "Generated input was mutated")
        canonical = json.dumps(exact, sort_keys=True, separators=(",", ":")).encode()
        return {"result": "DISPOSABLE_LOCAL_GIT_HANDOFF_MATCH", "profile": approved_profile,
                "fileCount": len(exact), "generatedInventorySha256": sha256(canonical),
                "exactManifest": True, "managedBaselines": True, "freshCloneMatch": True,
                "githubTargetWritten": False, "sourceBindingActivated": False,
                "generationAuthorized": False, "productionAuthorized": False}
