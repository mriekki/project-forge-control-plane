#!/usr/bin/env python3
"""Source-only GitHub App transport. Exact immutable ID scope before any Git read.

Only the protected Control Plane caller supplies an accepted binding. No
provider/target token, repository mutation, source code execution or public
private-source log is authorized. Standard GitHub App JWT issuance and REST
installation-token API are intentionally used so repository_ids AND returned
permissions can be verified, rather than trusting a name-scoped action output.
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.request
import urllib.error
from pathlib import Path

from bootstrap_source_binding import SourceBindingError, exact, need, positive, resolve_binding, verify_checkout

API = "https://api.github.com"
MAX = 2 * 1024 * 1024
PERMISSIONS = {"contents": "read", "metadata": "read"}


class TransportStageError(SourceBindingError):
    """Only fixed stage names and numeric HTTP status may be logged."""


def stage(label, operation, *args):
    try:
        return operation(*args)
    except TransportStageError:
        raise
    except urllib.error.HTTPError as exc:
        status = exc.code if type(exc.code) is int and 400 <= exc.code <= 599 else 0
        raise TransportStageError(f"{label}: http-{status}") from None
    except Exception:
        raise TransportStageError(f"{label}: refused") from None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SourceBindingError("Authenticated API redirect refused")


def api(method, endpoint, credential, body=None):
    need(endpoint.startswith("/") and not endpoint.startswith("//") and
         not any(x in endpoint for x in ("\r", "\n", "\\", "#")), "Invalid GitHub API endpoint")
    data = None if body is None else json.dumps(body, separators=(",", ":")).encode()
    request = urllib.request.Request(API + endpoint, method=method, data=data, headers={
        "Authorization": "Bearer " + credential, "Accept": "application/vnd.github+json",
        "Content-Type": "application/json", "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Project-Forge-source-transport-preview"})
    opener = urllib.request.build_opener(NoRedirect())
    with opener.open(request, timeout=30) as response:
        payload = response.read(MAX + 1)
        need(len(payload) <= MAX and response.geturl() == API + endpoint, "Unexpected GitHub API response")
        if method == "DELETE":
            need(response.status == 204 and not payload, "Source token revocation not confirmed")
            return None
        return json.loads(payload)


def child_env():
    # No GitHub token, App key, runner credentials, proxy config, checkout
    # credential helper, shell startup file, or candidate-local executable.
    env = {k: os.environ[k] for k in ("PATH", "HOME", "LANG", "LC_ALL", "SSL_CERT_FILE")
           if k in os.environ}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null",
               GIT_TERMINAL_PROMPT="0", GIT_LFS_SKIP_SMUDGE="1")
    return env


def b64(data):
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def create_jwt(client_id, private_key, scratch):
    need(isinstance(client_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", client_id) is not None
         and isinstance(private_key, str) and 0 < len(private_key) <= 32768, "Missing protected App identity")
    now = int(time.time())
    header = b64(b'{"alg":"RS256","typ":"JWT"}')
    claims = b64(json.dumps({"iat": now-60, "exp": now+300, "iss": client_id},
                           separators=(",", ":")).encode())
    signing = f"{header}.{claims}".encode()
    with tempfile.TemporaryDirectory(prefix="app-key-", dir=scratch) as tmp:
        key = Path(tmp) / "key.pem"
        fd = os.open(key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(private_key)
        result = subprocess.run(["openssl", "dgst", "-sha256", "-sign", str(key)],
                                input=signing, capture_output=True, env=child_env(), timeout=10)
        need(result.returncode == 0 and bool(result.stdout), "GitHub App JWT signing failed")
    return signing.decode("ascii") + "." + b64(result.stdout)


def validate_scope(binding, response):
    need(isinstance(response, dict) and type(response.get("total_count")) is int
         and response["total_count"] == 1 and isinstance(response.get("repositories"), list)
         and len(response["repositories"]) == 1, "Source token is not restricted to one repository")
    repo = response["repositories"][0]
    need(isinstance(repo, dict) and repo.get("id") == binding["repositoryId"]
         and type(repo.get("id")) is int and repo.get("full_name") == binding["repository"]
         and repo.get("private") is True and repo.get("archived") is False,
         "Source token repository identity changed")
    return repo


def observe_scope(binding, descriptor, token, request=api):
    # Check the token's complete inventory before touching source bytes.
    scope = request("GET", "/installation/repositories?per_page=100", token)
    listed = validate_scope(binding, scope)
    resolve_binding(descriptor, binding, listed)
    repo = request("GET", "/repos/" + binding["repository"], token)
    resolve_binding(descriptor, binding, repo)
    return repo


def git_checkout(binding, token, destination):
    # Git never receives App key/JWT/API token outside this exact read step.
    # No private paths, stderr, remote refs, or raw Git errors reach Actions logs.
    destination.mkdir(mode=0o700)
    env = child_env()
    base = ["git", "-C", str(destination), "-c", "core.hooksPath=/dev/null",
            "-c", "protocol.file.allow=never", "-c", "http.followRedirects=false",
            "-c", "credential.helper="]

    def run(args, environment):
        status = subprocess.run([*base, *args], env=environment, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                timeout=180)
        need(status.returncode == 0, "Private source Git transport refused")

    run(["init", "-q"], env)
    authorized = dict(env, GIT_CONFIG_COUNT="1",
                      GIT_CONFIG_KEY_0="http.https://github.com/.extraheader",
                      GIT_CONFIG_VALUE_0="AUTHORIZATION: basic " +
                      base64.b64encode(("x-access-token:" + token).encode()).decode("ascii"))
    # Exactly the reviewed Git commit on the single immutable-ID scoped
    # repository. Shallow download, no tags, no submodule fetch or redirects.
    run(["fetch", "--quiet", "--no-tags", "--depth=1", "--no-recurse-submodules",
         "https://github.com/" + binding["repository"] + ".git", binding["sourceCommit"]], authorized)
    del authorized
    run(["checkout", "--quiet", "--detach", "--no-recurse-submodules", binding["sourceCommit"]], env)


def qualify_one(binding, descriptor, jwt, destination, request=api, checkout=git_checkout,
                verify=verify_checkout):
    install = stage("installation-lookup", request, "GET", "/repos/" + binding["repository"] + "/installation", jwt)
    owner = binding["repository"].split("/")[0]
    stage("installation-identity", need, isinstance(install, dict) and positive(install.get("id"))
          and install.get("account", {}).get("login") == owner
          and install.get("suspended_at") is None, "Unexpected source App installation")
    minted = stage("token-mint", request, "POST", f"/app/installations/{install['id']}/access_tokens", jwt,
                   {"repository_ids": [binding["repositoryId"]], "permissions": {"contents": "read"}})
    token = minted.get("token") if isinstance(minted, dict) else None
    stage("token-format", need, isinstance(token, str) and re.fullmatch(r"[A-Za-z0-9_-]{16,512}", token) is not None,
          "Exact source installation token missing")
    try:
        stage("token-permissions", need, minted.get("permissions") == PERMISSIONS,
              "Source token permissions exceed or differ from policy")
        repos = minted.get("repositories")
        stage("mint-repository-identity", need, isinstance(repos, list) and len(repos) == 1
              and isinstance(repos[0], dict) and type(repos[0].get("id")) is int
              and repos[0]["id"] == binding["repositoryId"]
              and repos[0].get("full_name") == binding["repository"], "Source mint repository differs")
        stage("scope-before-fetch", observe_scope, binding, descriptor, token, request)
        stage("exact-git-checkout", checkout, binding, token, destination)
        repo = stage("scope-after-fetch", observe_scope, binding, descriptor, token, request)
        result = stage("source-tree-verification", verify, destination, descriptor, binding, repo)
        stage("scope-after-verify", observe_scope, binding, descriptor, token, request)
        return result
    finally:
        stage("token-revocation", request, "DELETE", "/installation/token", token)


def qualify_transport(policy, descriptor, client_id, key, scratch):
    # One source-only token at a time; no source checkout survives success or
    # failure, and no source code is executed at any point.
    with tempfile.TemporaryDirectory(prefix="pf-bootstrap-source-", dir=scratch) as tmp:
        root = Path(tmp)
        jwt = stage("app-jwt", create_jwt, client_id, key, root)
        original = stage("original-binding", qualify_one, policy["original"], descriptor, jwt, root / "original")
        candidate = stage("candidate-binding", qualify_one, policy["candidate"], descriptor, jwt, root / "candidate")
        need(original == candidate, "Original and relocated source observations differ")
        return original
