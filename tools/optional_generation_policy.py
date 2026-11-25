"""Select a reviewed optional generation profile, never authorize a target write.

Standard generation remains unchanged. Optional generation requires a reviewed
exact Bootstrap/package/profile tuple AND advertisement in the same stable
public descriptor. Target ownership and approved manifests are still mandatory.
Legacy schema-1 pilot policy is retained only for rollback compatibility.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys

STANDARD = "greenfield-project"
OPTIONAL = {"greenfield-household-project", "greenfield-household-feedback-project"}
SHA = re.compile(r"[0-9a-f]{40}")
VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
REPOSITORY = re.compile(r"[A-Za-z0-9-]+/[A-Za-z0-9][A-Za-z0-9_.-]*")
KEYS = {"targetRepository", "bootstrapRevision", "packageVersion", "profile"}


class PolicyError(ValueError):
    pass


def need(condition, message):
    if not condition:
        raise PolicyError(message)


def load(path):
    def pairs(values):
        result = {}
        for key, value in values:
            need(key not in result, "Duplicate JSON field")
            result[key] = value
        return result
    return json.loads(Path(path).read_bytes(), object_pairs_hook=pairs)


def exact(value, regex):
    return isinstance(value, str) and regex.fullmatch(value) is not None


def select(policy, manifest, *, revision, stable_version, repository, author,
           advertised_profiles=()):
    need(isinstance(policy, dict), "Invalid optional generation policy")
    if type(policy.get("schemaVersion")) is int and policy["schemaVersion"] == 2:
        need(set(policy) == {"schemaVersion", "qualifiedProfiles"}
             and isinstance(policy["qualifiedProfiles"], list), "Invalid qualified profile policy")
        qualified = set()
        for item in policy["qualifiedProfiles"]:
            need(isinstance(item, dict) and set(item) == {"bootstrapRevision", "packageVersion", "profile"}
                 and exact(item["bootstrapRevision"], SHA) and exact(item["packageVersion"], VERSION)
                 and isinstance(item["profile"], str) and item["profile"] in OPTIONAL,
                 "Invalid qualified profile")
            key = (item["bootstrapRevision"], item["packageVersion"], item["profile"])
            need(key not in qualified, "Duplicate qualified profile")
            qualified.add(key)
        need(isinstance(advertised_profiles, (list, tuple))
             and all(isinstance(p, str) and p in OPTIONAL for p in advertised_profiles)
             and len(set(advertised_profiles)) == len(advertised_profiles),
             "Invalid public optional profile advertisement")
        approvals = {}
    else:
        qualified = None
        approvals = _pilot_approvals(policy)
    return _select(policy, manifest, revision=revision, stable_version=stable_version,
                   repository=repository, author=author, qualified=qualified,
                   approvals=approvals, advertised_profiles=advertised_profiles)


def _pilot_approvals(policy):
    need(isinstance(policy, dict) and set(policy) == {"schemaVersion", "approvals"}
         and type(policy["schemaVersion"]) is int and policy["schemaVersion"] == 1
         and isinstance(policy["approvals"], list), "Invalid optional generation policy")
    approvals = {}
    for item in policy["approvals"]:
        need(isinstance(item, dict) and set(item) == KEYS
             and exact(item["targetRepository"], REPOSITORY)
             and exact(item["bootstrapRevision"], SHA)
             and exact(item["packageVersion"], VERSION)
             and isinstance(item["profile"], str) and item["profile"] in OPTIONAL,
             "Invalid optional generation approval")
        key = item["targetRepository"].lower()
        need(key not in approvals, "Duplicate target approval")
        approvals[key] = item

    return approvals


def _select(policy, manifest, *, revision, stable_version, repository, author,
            qualified, approvals, advertised_profiles):
    need(isinstance(manifest, dict), "Invalid approved generation manifest")
    generation = manifest.get("generation")
    need(isinstance(generation, dict), "Missing generation selection")
    selected = generation.get("project-forge")
    need(isinstance(selected, dict), "Missing package selection")
    profile = selected.get("profile")
    if profile == STANDARD:
        return {"profile": STANDARD, "package_version": ""}

    need(isinstance(profile, str) and profile in OPTIONAL, "Unsupported optional profile")
    need(exact(repository, REPOSITORY) and isinstance(author, str)
         and repository.split("/")[0].lower() == author.lower(),
         "Optional target owner differs from request author")
    project = manifest.get("project")
    bootstrap = manifest.get("bootstrap")
    need(type(manifest.get("schemaVersion")) is int and manifest["schemaVersion"] == 2
         and manifest.get("state") == "approved"
         and isinstance(project, dict) and isinstance(project.get("repository"), str)
         and project["repository"].lower() == repository.lower()
         and isinstance(bootstrap, dict) and exact(revision, SHA)
         and bootstrap.get("commit") == revision
         and exact(stable_version, VERSION)
         and selected.get("package") == "@mriekki/project-forge"
         and selected.get("version") == stable_version,
         "Optional request does not match exact approved target and stable contract")
    if qualified is not None:
        need((revision, stable_version, profile) in qualified
             and profile in advertised_profiles,
             "Optional profile is not qualified and advertised for this exact stable release")
    else:
        approval = approvals.get(repository.lower())
        need(approval is not None and approval["bootstrapRevision"] == revision
             and approval["packageVersion"] == stable_version and approval["profile"] == profile,
             "Optional generation has no matching independently reviewed approval")
    return {"profile": profile, "package_version": stable_version}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("policy", "manifest", "bootstrap-revision", "stable-package-version",
                 "target-repository", "request-author"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--advertised-profiles", default="[]")
    args = parser.parse_args()
    try:
        values = select(load(args.policy), load(args.manifest),
                        revision=args.bootstrap_revision, stable_version=args.stable_package_version,
                        repository=args.target_repository, author=args.request_author,
                        advertised_profiles=json.loads(args.advertised_profiles))
        if os.getenv("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
                for key, value in values.items():
                    output.write(f"{key}={value}\n")
        print("Reviewed profile selection verified:", values["profile"])
        return 0
    except (OSError, ValueError, TypeError):
        # Never echo a private manifest, malformed JSON or configuration.
        print("FAIL generation profile policy: missing, invalid or unmatched reviewed selection.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
