#!/usr/bin/env python3
"""Read-only prospective Bootstrap transport proof. Never execute source code."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path

from bootstrap_source_binding import (
    DIGEST, SourceBindingError, exact, fields, need, validate_binding_policy, verify_checkout,
)
import public_contract

TITLE = "[project-forge-bootstrap-binding-preview]"
MAX = 1024 * 1024


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, "Duplicate JSON key")
            result[key] = value
        return result
    need(len(raw) <= MAX, "Oversized protected input")
    return json.loads(raw, object_pairs_hook=pairs)


def fetch(url):
    with urllib.request.urlopen(url, timeout=20) as response:
        need(response.geturl() == url, "Unexpected public contract redirect")
        data = response.read(MAX + 1)
        need(0 < len(data) <= MAX, "Unexpected public contract byte size")
        return data


def resolve_policy(raw, descriptor_bytes, original_repository):
    config = strict_json(raw)
    fields(config, {"schemaVersion", "descriptorSha256", "original", "candidate"},
           "protected transport policy")
    need(type(config["schemaVersion"]) is int and config["schemaVersion"] == 1
         and exact(config["descriptorSha256"], DIGEST)
         and hashlib.sha256(descriptor_bytes).hexdigest() == config["descriptorSha256"],
         "Exact reviewed public descriptor differs")
    descriptor = strict_json(descriptor_bytes)
    docs = public_contract.validate_descriptor(descriptor)
    public_contract.validate_generation_descriptor(descriptor)
    expected = {descriptor["snapshotPath"] + "/" + n for n in public_contract.REQUIRED_DOCUMENTS}
    need(len(docs) == len(expected) and {x["path"] for x in docs} == expected,
         "Unexpected immutable contract document set")
    old = validate_binding_policy(descriptor, config["original"])
    new = validate_binding_policy(descriptor, config["candidate"])
    need(old["mode"] == "original-owner" and new["mode"] == "nested-source"
         and old["repository"] == original_repository
         and old["repository"] != new["repository"] and old["repositoryId"] != new["repositoryId"]
         and old["logicalRevision"] == new["logicalRevision"] and old["sourceTree"] == new["sourceTree"],
         "Relocation policy does not preserve the accepted Bootstrap identity")
    return config, descriptor


def validate_event(event, owner):
    issue = event.get("issue", {})
    need(isinstance(owner, str) and bool(owner) and event.get("action") == "opened"
         and issue.get("title") == TITLE and issue.get("state") == "open"
         and issue.get("user", {}).get("login") == owner and event.get("sender", {}).get("login") == owner
         and (issue.get("body") or "").strip() == "", "Owner-opened empty-body preview required")


def verify_public_bytes(descriptor):
    for doc in public_contract.validate_descriptor(descriptor):
        data = fetch(public_contract.DEFAULT_BASE_URL + doc["path"])
        need(hashlib.sha256(data).hexdigest() == doc["sha256"], "Public snapshot bytes differ")
    for key in ("schema", "validator"):
        artifact = descriptor["generation"]["bootstrap"]["portableRequirements"][key]
        need(hashlib.sha256(fetch(artifact["url"])).hexdigest() == artifact["sha256"],
             "Public portable requirements projection differs")


def write_private(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)


def resolve(scratch):
    validate_event(strict_json(Path(os.environ["GITHUB_EVENT_PATH"]).read_bytes()),
                   os.environ["REPOSITORY_OWNER"])
    need(os.environ.get("GITHUB_EVENT_NAME") == "issues"
         and os.environ.get("GITHUB_REF") == "refs/heads/main"
         and os.environ.get("GITHUB_REPOSITORY") == "mriekki/project-forge-control-plane",
         "Unexpected transport preview context")
    raw = os.environ["PROTECTED_BINDINGS"].encode()
    descriptor_bytes = fetch(public_contract.DEFAULT_DESCRIPTOR_URL)
    config, descriptor = resolve_policy(raw, descriptor_bytes, os.environ["ORIGINAL_REPOSITORY"])
    verify_public_bytes(descriptor)
    write_private(scratch / "pf-bootstrap-bindings.json", raw)
    write_private(scratch / "pf-bootstrap-descriptor.json", descriptor_bytes)
    # Protected locators never become Action outputs.
    for label in ("original", "candidate"):
        binding = config[label]
        _, name = binding["repository"].split("/")
        for value in (binding["repository"], name, str(binding["repositoryId"]), binding["sourceTree"]):
            print("::add-mask::" + value)
        if label == "candidate":
            print("::add-mask::" + binding["sourceCommit"])
            print("::add-mask::" + binding["sourceRoot"])
    print("Exact protected relocation policy and public contract bytes verified.")


def verify(scratch):
    from bootstrap_source_transport import qualify_transport
    raw = (scratch / "pf-bootstrap-bindings.json").read_bytes()
    saved = (scratch / "pf-bootstrap-descriptor.json").read_bytes()
    config = strict_json(raw)
    policy, descriptor = resolve_policy(raw, saved, config["original"]["repository"])
    key = os.environ.pop("APP_PRIVATE_KEY")
    client = os.environ.pop("APP_CLIENT_ID")
    result = qualify_transport(policy, descriptor, client, key, scratch)
    need(fetch(public_contract.DEFAULT_DESCRIPTOR_URL) == saved, "Public descriptor changed during preview")
    # Only public logical identity/count/digest match booleans are emitted;
    # never the physical source locator, original/candidate Git trees or tokens.
    print(json.dumps(result, sort_keys=True))
    print("BOOTSTRAP_TRANSPORT_PREVIEW_MATCH SOURCE_BINDING_ACTIVATED=false TARGET_WRITES=false")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("resolve", "verify"))
    parser.add_argument("--scratch", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.mode == "resolve":
            resolve(args.scratch)
        else:
            verify(args.scratch)
        return 0
    except Exception:
        # Never include private locator, policy, source path or raw API body.
        print("Bootstrap source transport preview refused", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
