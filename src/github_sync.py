"""
github_sync.py
---------------
Commits updated files (the training CSV, retrained model artifacts) back to
a GitHub repo via the Git Data API, so changes made by the deployed
Streamlit app survive container reboots/redeploys - local disk on Streamlit
Community Cloud is wiped on every restart, but the repo isn't.

Uses the low-level Git Data API (blob/tree/commit/ref), not the simpler
"Create or update file contents" endpoint, because that simpler endpoint is
capped around 1MB per file and best_model.pkl is a few MB.

SETUP (do this once):
1. Create a GitHub Personal Access Token (fine-grained) scoped to ONLY this
   one repo, with "Contents: Read and write" permission.
   https://github.com/settings/personal-access-tokens/new
2. In your Streamlit Community Cloud app -> Settings -> Secrets, add:

       GITHUB_TOKEN = "ghp_..."
       GITHUB_REPO = "your-username/your-repo-name"
       GITHUB_BRANCH = "main"

   (branch defaults to "main" if you omit it)

Without these secrets configured, sync_to_github() raises a clear error
that app.py catches and turns into an on-screen warning - the app still
works, it just won't persist across reboots until you set this up.
"""
import base64
import requests

API_ROOT = "https://api.github.com"


def _headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _raise_with_body(r):
    """raise_for_status() alone only shows '404 Not Found for url: ...' -
    GitHub's actual reason (bad credentials, permission denied, wrong repo,
    etc.) is in the response body, so surface that too."""
    if not r.ok:
        try:
            detail = r.json().get("message", r.text)
        except ValueError:
            detail = r.text
        raise requests.HTTPError(
            f"{r.status_code} {r.reason} for {r.request.method} {r.url} - GitHub says: {detail}"
        )


def _get(url, token):
    r = requests.get(url, headers=_headers(token), timeout=20)
    _raise_with_body(r)
    return r.json()


def _post(url, token, payload):
    r = requests.post(url, headers=_headers(token), json=payload, timeout=30)
    _raise_with_body(r)
    return r.json()


def _patch(url, token, payload):
    r = requests.patch(url, headers=_headers(token), json=payload, timeout=20)
    _raise_with_body(r)
    return r.json()


def sync_to_github(repo, branch, token, file_map, commit_message):
    """
    repo: "owner/name"
    branch: e.g. "main"
    token: GitHub personal access token with Contents:write on `repo`
    file_map: dict of {"path/in/repo.ext": "local/path/on/disk.ext"}
    commit_message: commit message string

    Returns the new commit's HTML URL on success. Raises on any failure -
    callers should catch and show the error rather than silently continuing,
    since a failed sync means the change will NOT survive a reboot.
    """
    if not (repo and branch and token and file_map):
        raise ValueError("repo, branch, token, and file_map are all required")

    ref_url = f"{API_ROOT}/repos/{repo}/git/ref/heads/{branch}"
    ref = _get(ref_url, token)
    latest_commit_sha = ref["object"]["sha"]

    commit_url = f"{API_ROOT}/repos/{repo}/git/commits/{latest_commit_sha}"
    commit = _get(commit_url, token)
    base_tree_sha = commit["tree"]["sha"]

    tree_entries = []
    for repo_path, local_path in file_map.items():
        with open(local_path, "rb") as f:
            content_b64 = base64.b64encode(f.read()).decode("utf-8")
        blob_url = f"{API_ROOT}/repos/{repo}/git/blobs"
        blob = _post(blob_url, token, {"content": content_b64, "encoding": "base64"})
        tree_entries.append({
            "path": repo_path, "mode": "100644", "type": "blob", "sha": blob["sha"],
        })

    tree_url = f"{API_ROOT}/repos/{repo}/git/trees"
    new_tree = _post(tree_url, token, {"base_tree": base_tree_sha, "tree": tree_entries})

    new_commit_url = f"{API_ROOT}/repos/{repo}/git/commits"
    new_commit = _post(new_commit_url, token, {
        "message": commit_message,
        "tree": new_tree["sha"],
        "parents": [latest_commit_sha],
    })

    _patch(ref_url, token, {"sha": new_commit["sha"]})

    return new_commit.get("html_url", f"https://github.com/{repo}/commit/{new_commit['sha']}")


def get_config(st_secrets):
    """Pulls GITHUB_TOKEN / GITHUB_REPO / GITHUB_BRANCH / GITHUB_PATH_PREFIX
    out of Streamlit's st.secrets (pass st.secrets in). Returns
    (repo, branch, token, path_prefix). path_prefix defaults to "" (repo
    root == project root, i.e. app.py/data//models/ sit directly at the
    repo's top level). Set GITHUB_PATH_PREFIX (e.g. "cricket_prediction/")
    if your repo nests the project inside a subfolder instead."""
    token = st_secrets["GITHUB_TOKEN"].strip()
    repo = st_secrets["GITHUB_REPO"].strip()
    branch = st_secrets.get("GITHUB_BRANCH", "main").strip()
    prefix = st_secrets.get("GITHUB_PATH_PREFIX", "").strip()
    if prefix and not prefix.endswith("/"):
        prefix += "/"
    return repo, branch, token, prefix
