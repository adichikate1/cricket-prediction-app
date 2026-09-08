"""
github_sync.py
---------------
Uses PyGithub (`from github import Github`) to:
  1. Append a completed match's row DIRECTLY to the training CSV that lives
     in your GitHub repo (fetch -> append -> commit back) - the repo is the
     source of truth, not local disk.
  2. Push the retrained model artifacts back to the same repo.

This replaces local-disk-only storage: Streamlit Community Cloud wipes
local disk on every reboot, but committing straight to GitHub survives
that, since the repo itself is the persistent store.

SETUP (do this once):
1. Create a GitHub Personal Access Token (fine-grained) scoped to ONLY this
   one repo, with "Contents: Read and write" permission:
   https://github.com/settings/personal-access-tokens/new
2. In your Streamlit Community Cloud app -> Settings -> Secrets, add:

       GITHUB_TOKEN = "ghp_..."
       GITHUB_REPO = "your-username/your-repo-name"
       GITHUB_BRANCH = "main"

   (branch defaults to "main" if omitted; add GITHUB_PATH_PREFIX = "sub/dir/"
   too if this project isn't at the repo root)
"""
import io
import json
import pandas as pd
from github import Github, GithubException


def get_config(st_secrets):
    """Pulls GITHUB_TOKEN / GITHUB_REPO / GITHUB_BRANCH / GITHUB_PATH_PREFIX
    out of Streamlit's st.secrets (pass st.secrets in). Raises KeyError if
    GITHUB_TOKEN or GITHUB_REPO aren't set."""
    token = st_secrets["GITHUB_TOKEN"].strip()
    repo_name = st_secrets["GITHUB_REPO"].strip()
    branch = st_secrets.get("GITHUB_BRANCH", "main").strip()
    prefix = st_secrets.get("GITHUB_PATH_PREFIX", "").strip()
    if prefix and not prefix.endswith("/"):
        prefix += "/"
    return repo_name, branch, token, prefix


def _get_repo(repo_name, token):
    return Github(token).get_repo(repo_name)


def append_row_to_github_csv(repo_name, branch, token, csv_path_in_repo, row: dict, commit_message: str) -> pd.DataFrame:
    """Fetches the CSV straight from the GitHub repo, appends `row`, commits
    the update back. Returns the updated DataFrame (so the caller can also
    write it to local disk for training, without a second GitHub round-trip)."""
    repo = _get_repo(repo_name, token)
    contents = repo.get_contents(csv_path_in_repo, ref=branch)
    existing_df = pd.read_csv(io.BytesIO(contents.decoded_content))
    updated_df = pd.concat([existing_df, pd.DataFrame([row])], ignore_index=True)
    repo.update_file(
        path=contents.path,
        message=commit_message,
        content=updated_df.to_csv(index=False),
        sha=contents.sha,
        branch=branch,
    )
    return updated_df


def save_file_to_github(repo_name, branch, token, repo_path: str, local_path: str, commit_message: str) -> str:
    """Pushes a local file's current bytes to `repo_path` in the repo,
    creating it if it doesn't exist yet or updating it if it does. Returns
    the commit's HTML URL."""
    repo = _get_repo(repo_name, token)
    with open(local_path, "rb") as f:
        content = f.read()
    try:
        existing = repo.get_contents(repo_path, ref=branch)
        result = repo.update_file(existing.path, commit_message, content, existing.sha, branch=branch)
    except GithubException as e:
        if e.status == 404:
            result = repo.create_file(repo_path, commit_message, content, branch=branch)
        else:
            raise
    return result["commit"].html_url


def save_files_to_github(repo_name, branch, token, file_map: dict, commit_message: str) -> list:
    """file_map: {"path/in/repo.ext": "local/path/on/disk.ext"}. Commits
    each file separately (PyGithub's simple contents API is per-file) and
    returns the list of commit URLs."""
    urls = []
    for repo_path, local_path in file_map.items():
        urls.append(save_file_to_github(repo_name, branch, token, repo_path, local_path, commit_message))
    return urls


def get_github_json(repo_name, branch, token, repo_path):
    """Returns the parsed JSON content of repo_path, or None if the file
    doesn't exist in the repo yet."""
    repo = _get_repo(repo_name, token)
    try:
        contents = repo.get_contents(repo_path, ref=branch)
        return json.loads(contents.decoded_content)
    except GithubException as e:
        if e.status == 404:
            return None
        raise


def append_to_github_json_list(repo_name, branch, token, repo_path: str, item, commit_message: str) -> list:
    """Appends `item` to a JSON list stored in the repo (creating the file
    if it doesn't exist yet), commits, and returns the updated list. Used
    for data/added_match_urls.json, so duplicate-match checks read from the
    repo (source of truth) rather than local disk."""
    repo = _get_repo(repo_name, token)
    try:
        contents = repo.get_contents(repo_path, ref=branch)
        current = json.loads(contents.decoded_content)
        if item not in current:
            current.append(item)
        repo.update_file(contents.path, commit_message, json.dumps(current, indent=2), contents.sha, branch=branch)
    except GithubException as e:
        if e.status == 404:
            current = [item]
            repo.create_file(repo_path, commit_message, json.dumps(current, indent=2), branch=branch)
        else:
            raise
    return current
