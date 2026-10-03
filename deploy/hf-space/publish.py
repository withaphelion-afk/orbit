"""Publish the static web terminal and its data to a Hugging Face Space (free, static).

    publish.py --web web/dist      the terminal's built files (deploy-space.yml, after CI)
    publish.py --api site/api      the data snapshot (python -m orbit.snapshot; every Actions job)
    publish.py --squash            collapse the Space's git history (daily, so it stays small)

Creates the Space on first use: private (only its owner can open it), static
SDK. Hugging Face only runs server Spaces on a paid plan, so the terminal is
static files reading the snapshot (web/src/api/static.ts).

Only changed files are sent. The Space keeps a list of what it holds
(.orbit-manifest.json: path -> sha256), and each publish adds the files whose
hash differs and deletes the ones that disappeared from its own part of the
Space (web files or api/), never the other's.

Reads HF_TOKEN and HF_SPACE (default <hf-user>/orbit) from the environment and
never prints the token.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from huggingface_hub import CommitOperationAdd, CommitOperationDelete, HfApi, hf_hub_download
from huggingface_hub.errors import EntryNotFoundError, HfHubHTTPError

MANIFEST = ".orbit-manifest.json"
SPACE_README = """---
title: Orbit
colorFrom: gray
colorTo: gray
sdk: static
app_file: index.html
pinned: false
---

# Orbit

The web terminal of [Orbit](https://github.com/{repo}), published by its GitHub
Actions jobs. Don't edit this Space by hand: every job overwrites it.
"""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _space(api: HfApi) -> str:
    return os.environ.get("HF_SPACE") or f"{api.whoami()['name']}/orbit"


def _ensure_space(api: HfApi, space: str) -> None:
    try:
        api.create_repo(space, repo_type="space", space_sdk="static", private=True, exist_ok=True)
    except HfHubHTTPError as exc:
        body = exc.response.text[:500] if exc.response is not None else ""
        raise SystemExit(f"::error::Hugging Face refused to create {space}: {exc.server_message or ''} {body}")


def _manifest(api: HfApi, space: str) -> dict[str, str]:
    try:
        path = hf_hub_download(space, MANIFEST, repo_type="space", token=api.token)
    except (EntryNotFoundError, HfHubHTTPError):
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def publish(api: HfApi, space: str, local: Path, area: str, extra: dict[str, bytes] | None = None) -> int:
    """Make the Space's files in `area` match `local`; the other area is left as it is.
    area "web": everything outside api/ (the built terminal). area "api": api/ (the data).
    Returns the number of files sent."""
    in_area = (lambda rel: rel.startswith("api/")) if area == "api" else (lambda rel: not rel.startswith("api/"))
    prefix = "api/" if area == "api" else ""
    old = _manifest(api, space)
    new = {rel: digest for rel, digest in old.items() if not in_area(rel)}
    ops: list = []

    def add(rel: str, digest: str, source) -> None:
        new[rel] = digest
        if old.get(rel) != digest:
            ops.append(CommitOperationAdd(path_in_repo=rel, path_or_fileobj=source))

    for path in sorted(p for p in local.rglob("*") if p.is_file()):
        rel = prefix + path.relative_to(local).as_posix()
        if in_area(rel):  # a stray api/ folder in the web build never overwrites the data
            add(rel, _sha(path), str(path))
    for rel, data in (extra or {}).items():
        add(rel, hashlib.sha256(data).hexdigest(), data)
    removed = [rel for rel in old if in_area(rel) and rel not in new]
    sent = len(ops)
    if not ops and not removed:
        return 0
    ops += [CommitOperationDelete(path_in_repo=rel) for rel in removed]
    ops.append(CommitOperationAdd(path_in_repo=MANIFEST, path_or_fileobj=json.dumps(new, indent=0, sort_keys=True).encode()))
    api.create_commit(space, repo_type="space", operations=ops, commit_message=f"Publish {area}: {sent} changed, {len(removed)} removed")
    return sent


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish Orbit's static terminal to a Hugging Face Space")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--web", type=Path, help="the built web terminal (web/dist)")
    group.add_argument("--api", type=Path, help="the data snapshot folder")
    group.add_argument("--squash", action="store_true", help="collapse the Space's history to one commit")
    args = parser.parse_args()

    token = os.environ.get("HF_TOKEN", "")
    if not token:
        print("::notice::HF_TOKEN is not set, so nothing is published (README: Free cloud hosting).")
        return 0
    api = HfApi(token=token)
    space = _space(api)
    _ensure_space(api, space)

    if args.squash:
        api.super_squash_history(space, repo_type="space")
        print(f"Squashed the history of {space}.")
    elif args.web:
        readme = SPACE_README.replace("{repo}", os.environ.get("GITHUB_REPOSITORY", "withaphelion-afk/orbit")).encode()
        n = publish(api, space, args.web, "web", extra={"README.md": readme})
        print(f"Web terminal: {n} files sent to https://huggingface.co/spaces/{space}")
    else:
        n = publish(api, space, args.api, "api")
        print(f"Data: {n} changed files sent to https://huggingface.co/spaces/{space}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
