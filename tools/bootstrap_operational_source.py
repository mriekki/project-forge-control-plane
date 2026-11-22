#!/usr/bin/env python3
"""Default-off operational Bootstrap source materialization.

The exact public logical revision remains the generated Project's identity.
The physical private source locator stays in protected source-only policy.
Neither generated target credentials nor source execution are in this stage.
Fail closed on any unreviewed identity, source bytes, copy drift or artifact.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path

from bootstrap_binding_preview import fetch, resolve_policy, verify_public_bytes, strict_json
from bootstrap_source_binding import SourceBindingError, need
from bootstrap_source_transport import create_jwt, qualify_one, stage, TransportStageError

MAX_FILES = 20000
MAX_BYTES = 128 * 1024 * 1024


def inventory(root):
    root = Path(root)
    need(root.is_dir() and not root.is_symlink(), "Invalid qualified source root")
    result, total, seen = {}, 0, set()
    for directory, directories, files in os.walk(root, followlinks=False):
        cur = Path(directory)
        for name in directories + files:
            p = cur / name
            relative = p.relative_to(root).as_posix()
            need(relative not in seen and not p.is_symlink()
                 and all(seg and seg not in (".", "..") and seg.casefold() != ".git"
                         for seg in relative.split("/")), "Unsafe source content")
            seen.add(relative)
            mode = p.lstat().st_mode
            if name in directories:
                need(stat.S_ISDIR(mode), "Non-directory source entry")
                continue
            need(stat.S_ISREG(mode) and p.stat().st_nlink == 1, "Nonregular source content")
            size = p.stat().st_size
            total += size
            need(len(result) < MAX_FILES and total <= MAX_BYTES,
                 "Qualified source exceeds materialization limits")
            result[relative] = ("100755" if mode & stat.S_IXUSR else "100644",
                                hashlib.sha256(p.read_bytes()).hexdigest())
    need(result, "Empty Bootstrap source")
    return result


def materialize_qualified(policy, descriptor, client_id, key, scratch, destination,
                          *, jwt_fn=create_jwt, qualify_fn=qualify_one):
    destination = Path(destination)
    need(not destination.exists() and not destination.is_symlink(),
         "Refusing to overwrite any source checkout")
    scratch = Path(scratch)
    need(scratch.is_dir() and scratch.resolve() != destination.resolve(),
         "Invalid isolated source scratch")
    created = False
    with tempfile.TemporaryDirectory(prefix="pf-operational-source-", dir=scratch) as tmp:
        root = Path(tmp)
        jwt = stage("app-jwt", jwt_fn, client_id, key, root)
        original = stage("original-binding", qualify_fn, policy["original"], descriptor,
                         jwt, root / "original")
        relocated = stage("candidate-binding", qualify_fn, policy["candidate"], descriptor,
                          jwt, root / "candidate")
        need(original == relocated, "Original and relocated Bootstrap source differ")
        candidate = root / "candidate"
        for seg in policy["candidate"]["sourceRoot"].split("/"):
            candidate = candidate / seg
            need(candidate.is_dir() and not candidate.is_symlink(), "Unsafe relocated source root")
        source = inventory(candidate)
        try:
            shutil.copytree(candidate, destination, symlinks=True, copy_function=shutil.copy2)
            created = True
            need(inventory(destination) == source, "Materialized Bootstrap bytes/modes differ")
        except Exception:
            if created and destination.is_dir() and not destination.is_symlink():
                shutil.rmtree(destination)
            raise
    return {"schemaVersion": 1, "logicalRevision": policy["original"]["logicalRevision"],
            "sourceTree": policy["candidate"]["sourceTree"], "sourceFileCount": len(source),
            "fileInventorySha256": hashlib.sha256(
                json.dumps(source, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "sourceBindingActivated": False, "targetWritten": False, "productionAuthorized": False}


def run_materialize(destination, scratch):
    need(os.environ.get("PF_BOOTSTRAP_MONOREPO_SOURCE_ENABLED") == "true",
         "Operational source migration is disabled")
    need(os.environ.get("GITHUB_REPOSITORY") == "mriekki/project-forge-control-plane",
         "Unexpected operational Control Plane")
    # A new explicitly configured protected secret is mandatory. The
    # existing read-only preview secret is not an activation authorization.
    raw = os.environ.pop("PROTECTED_OPERATIONAL_BINDINGS", "").encode()
    need(bool(raw), "Separately accepted operational source policy missing")
    descriptor_bytes = fetch("https://raw.githubusercontent.com/mriekki/project-forge-platform/main/chatgpt/current.json")
    policy, descriptor = resolve_policy(raw, descriptor_bytes,
                                        os.environ.pop("ORIGINAL_REPOSITORY"))
    verify_public_bytes(descriptor)
    client = os.environ.pop("APP_CLIENT_ID")
    key = os.environ.pop("APP_PRIVATE_KEY")
    result = materialize_qualified(policy, descriptor, client, key, scratch, destination)
    need(result["logicalRevision"] == descriptor["generation"]["bootstrap"]["revision"],
         "Operational logical revision differs")
    proof = Path(scratch) / "pf-bootstrap-operational-source.json"
    fd = os.open(proof, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(result, stream, sort_keys=True)
    print("BOOTSTRAP_OPERATIONAL_SOURCE_QUALIFIED NO_TARGET_TOKEN=true SOURCE_LOGICAL_REVISION_PRESERVED=true")


def verify_proof(scratch, accepted_revision, materialized):
    proof = strict_json((Path(scratch) / "pf-bootstrap-operational-source.json").read_bytes())
    need(isinstance(proof, dict) and proof.get("schemaVersion") == 1
         and proof.get("logicalRevision") == accepted_revision
         and proof.get("sourceBindingActivated") is False
         and proof.get("targetWritten") is False and proof.get("productionAuthorized") is False,
         "Missing authenticated operational source witness")
    actual = inventory(materialized)
    need(len(actual) == proof["sourceFileCount"] and
         hashlib.sha256(json.dumps(actual, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
         == proof["fileInventorySha256"], "Qualified source changed before verification")
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=("materialize", "verify"))
    ap.add_argument("--scratch", required=True, type=Path)
    ap.add_argument("--output", default="bootstrap", type=Path)
    ap.add_argument("--revision")
    args = ap.parse_args()
    try:
        need(args.output == Path("bootstrap"), "Only isolated Bootstrap checkout may be materialized")
        if args.mode == "materialize":
            run_materialize(args.output, args.scratch)
        else:
            need(args.revision is not None, "Exact logical revision missing")
            verify_proof(args.scratch, args.revision, args.output)
        return 0
    except Exception:
        # No protected locator, API response, checkout data or credentials.
        print("Operational Bootstrap source materialization refused", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
