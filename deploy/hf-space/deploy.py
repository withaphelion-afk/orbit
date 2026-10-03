"""Create/update the Hugging Face Space from GitHub Actions (deploy-space.yml).

Reads everything from the environment the workflow sets; never prints a secret.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

from huggingface_hub import HfApi

HERE = Path(__file__).resolve().parent
SPACE_FILES = ("Dockerfile", "README.md")


def main() -> int:
    token = os.environ.get("HF_TOKEN", "")
    if not token:
        print("::notice::HF_TOKEN is not set, so there is no Space to deploy yet (README: Free cloud hosting).")
        return 0
    api = HfApi(token=token)
    space = os.environ.get("HF_SPACE") or f"{api.whoami()['name']}/orbit"

    created = api.create_repo(space, repo_type="space", space_sdk="docker", private=True, exist_ok=True)
    print(f"Space: {created}")

    missing = []
    for name in ("ORBIT_DATA_TOKEN", "ORBIT_DISPATCH_TOKEN"):
        value = os.environ.get(name, "")
        if value:
            api.add_space_secret(space, name, value)
        else:
            missing.append(name)
    data_repo = os.environ.get("ORBIT_DATA_REPO", "")
    if data_repo:
        api.add_space_variable(space, "ORBIT_DATA_REPO", data_repo)
    else:
        missing.append("ORBIT_DATA_REPO (variable)")
    if missing:
        print(f"::warning::Not set in GitHub yet, so the Space won't work fully: {', '.join(missing)}")

    with tempfile.TemporaryDirectory() as tmp:
        for name in SPACE_FILES:
            shutil.copy(HERE / name, Path(tmp) / name)
        (Path(tmp) / "ORBIT_REPO").write_text(os.environ["GITHUB_REPOSITORY"] + "\n", encoding="utf-8")
        (Path(tmp) / "ORBIT_COMMIT").write_text(os.environ["SHA"] + "\n", encoding="utf-8")
        api.upload_folder(folder_path=tmp, repo_id=space, repo_type="space", commit_message=f"Build {os.environ['SHA'][:7]}")
    print(f"Uploaded; Hugging Face is rebuilding https://huggingface.co/spaces/{space}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
