"""Non-activating, explicit generation profile baseline verification.

An independently accepted profile must be supplied by the protected caller.
This does not authorize optional profiles, providers, or target publication.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath

PROFILES = {
    "greenfield-project": ("core", "deployment"),
    "greenfield-household-project": ("core", "deployment", "authentication"),
    "greenfield-household-feedback-project": ("core", "deployment", "authentication", "feedback"),
}
FILES = {
    "core": "CORE_BASELINE.json",
    "deployment": "DEPLOYMENT_BASELINE.json",
    "authentication": "AUTHENTICATION_BASELINE.json",
    "feedback": "FEEDBACK_BASELINE.json",
    "release-notes": "RELEASE_NOTES_BASELINE.json",
}
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


class ProfileBaselineError(ValueError):
    pass


def need(ok, message):
    if not ok:
        raise ProfileBaselineError(message)


def exact(value, regex):
    return isinstance(value, str) and regex.fullmatch(value) is not None


def safe_path(value):
    need(isinstance(value, str) and bool(value) and len(value) <= 1024,
         "Expected managed relative path")
    parts = value.split("/")
    need(all(p not in ("", ".", "..") and p.casefold() != ".git"
             and not re.search(r'[\\:\x00-\x1f<>|?*"]', p)
             and not p.endswith((" ", ".")) for p in parts)
         and not PurePosixPath(value).is_absolute(), "Unsafe managed path")
    return value


def parse(raw):
    def pairs(values):
        obj = {}
        for key, value in values:
            need(key not in obj, "Duplicate baseline field")
            obj[key] = value
        return obj
    try:
        obj = json.loads(raw, object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProfileBaselineError("Invalid baseline JSON") from exc
    need(isinstance(obj, dict), "Expected baseline object")
    return obj


def verify_profile(approved_profile, read, exists):
    """Check schema-v2 baselines and every managed byte via the caller's reader.

    Read and existence callbacks must address the same boundary (filesystem
    or Git index). The protected caller separately validates the approved
    manifest's canonical capability schema and authentic package/archive.
    """
    need(isinstance(approved_profile, str) and approved_profile in PROFILES,
         "Unsupported independently selected generation profile")
    components = PROFILES[approved_profile]
    umbrella_name = "PROJECT_FORGE_BASELINE.json"
    baseline_names = (umbrella_name, *(FILES[c] for c in components))
    expected = {name: read(name) for name in baseline_names}
    umbrella = parse(expected[umbrella_name])
    manifest = parse(read("PROJECT_BOOTSTRAP.json"))
    generation = manifest.get("generation")
    need(isinstance(generation, dict), "Missing generation selection")
    selected = generation.get("project-forge")
    need(isinstance(selected, dict) and selected.get("package") == "@mriekki/project-forge"
         and exact(selected.get("version"), VERSION) and selected.get("profile") == approved_profile,
         "Manifest package/profile differs from protected selection")
    for capability, component in (("householdAuth", "authentication"), ("feedback", "feedback")):
        value = generation.get(capability)
        need((isinstance(value, dict) and bool(value)) if component in components else value is None,
             "Manifest capability differs from protected profile")
    need(type(umbrella.get("schemaVersion")) is int and umbrella["schemaVersion"] == 2
         and all(umbrella.get(k) == selected[k] for k in ("package", "version", "profile"))
         and isinstance(umbrella.get("components"), dict)
         and set(umbrella["components"]) == set(components), "Exact selected component inventory differs")
    for c, name in FILES.items():
        need(exists(name) == (c in components), "Missing or unauthorized component baseline")
    for k in ("consumer", "consumerBaseline"):
        need(isinstance(umbrella.get(k), str) and bool(umbrella[k]), "Missing umbrella consumer identity")
    # No manually installed profile variants are selectable in this remote
    # generation contract. A new variant requires explicit separate review.
    need(umbrella.get("componentVariants", {}) == {}, "Unapproved generation component variants")
    owned = {}
    for component in components:
        metadata = umbrella["components"][component]
        keys = {"revision", "distribution"} | ({"version"} if component == "core" else set())
        need(isinstance(metadata, dict) and set(metadata) == keys
             and exact(metadata["revision"], HEX40)
             and isinstance(metadata["distribution"], str) and bool(metadata["distribution"])
             and (component != "core" or exact(metadata["version"], VERSION)),
             "Invalid selected component identity")
        doc = parse(expected[FILES[component]])
        need(type(doc.get("schemaVersion")) is int and doc["schemaVersion"] == 2
             and doc.get("component") == component
             and all(doc.get(k) == metadata[k] for k in keys)
             and all(doc.get(k) == umbrella[k] for k in ("consumer", "consumerBaseline")),
             "Component baseline provenance differs")
        paths = doc.get("managedPaths")
        need(isinstance(paths, list) and bool(paths), "Empty managed component baseline")
        for item in paths:
            need(isinstance(item, dict) and set(item) == {"source", "path", "sha256"}
                 and exact(item["sha256"], HEX64), "Invalid managed file record")
            safe_path(item["source"])
            path = safe_path(item["path"])
            canonical = path.casefold()
            need(canonical not in owned and canonical not in
                 {n.casefold() for n in (*FILES.values(), umbrella_name, "PROJECT_BOOTSTRAP.json")},
                 "Managed ownership collision or reserved baseline path")
            need(hashlib.sha256(read(path)).hexdigest() == item["sha256"], "Managed file bytes differ")
            owned[canonical] = component
    return expected, len(owned)


def filesystem_read(root):
    root = Path(root).resolve(strict=True)

    def checked(name):
        current = root
        for part in safe_path(name).split("/"):
            current = current / part
            need(not current.is_symlink(), "Symlink at generated/copy boundary")
        return current

    def read(name):
        path = checked(name)
        need(path.is_file(), "Missing managed file or baseline")
        return path.read_bytes()

    def exists(name):
        path = checked(name)
        return path.exists()

    return read, exists
