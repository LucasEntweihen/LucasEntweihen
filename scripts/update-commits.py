#!/usr/bin/env python3
"""Count all commits authored by a GitHub user across all repos and branches,
and update the Total Commits badge in README.md.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

USERNAME = os.environ.get("GITHUB_USERNAME", "LucasEntweihen")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
README_PATH = os.environ.get("README_PATH", "README.md")
TIMEOUT_SECONDS = 15


def api_get(url: str) -> tuple[object, dict[str, str]]:
    """Perform an authenticated GitHub API GET request with explicit timeout."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "LucasEntweihen-commit-counter",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        resp_headers = {k.lower(): v for k, v in resp.headers.items()}
        return data, resp_headers


def paginate(url: str) -> list[dict]:
    """Fetch all pages from a GitHub REST list endpoint."""
    results: list[dict] = []
    next_url: str | None = url
    while next_url:
        data, headers = api_get(next_url)
        if isinstance(data, list):
            results.extend(data)
        link = headers.get("link", "")
        next_url = None
        for part in link.split(","):
            if 'rel="next"' in part:
                match = re.search(r"<([^>]+)>", part)
                if match:
                    next_url = match.group(1)
                break
    return results


def count_user_repo_branch_commits(username: str) -> int:
    """Count unique commit SHAs authored by `username` across all branches of their repos."""
    repos = paginate(f"https://api.github.com/users/{username}/repos?per_page=100&type=owner")
    unique_shas: set[str] = set()

    for repo in repos:
        full_name = repo.get("full_name")
        if not full_name:
            continue
        try:
            branches = paginate(f"https://api.github.com/repos/{full_name}/branches?per_page=100")
        except urllib.error.HTTPError:
            continue

        for branch in branches:
            branch_name = branch.get("name")
            if not branch_name:
                continue
            encoded_branch = urllib.parse.quote(branch_name, safe="")
            commits_url = (
                f"https://api.github.com/repos/{full_name}/commits"
                f"?sha={encoded_branch}&author={urllib.parse.quote(username)}&per_page=100"
            )
            try:
                commits = paginate(commits_url)
                for commit in commits:
                    sha = commit.get("sha")
                    if sha:
                        unique_shas.add(sha)
            except urllib.error.HTTPError:
                continue

    return len(unique_shas)


def count_search_commits(username: str) -> int:
    """Query GitHub Commit Search API for total commits authored by `username`."""
    query = urllib.parse.quote(f"author:{username}")
    url = f"https://api.github.com/search/commits?q={query}&per_page=1"
    try:
        data, _ = api_get(url)
        if isinstance(data, dict):
            return int(data.get("total_count", 0))
    except urllib.error.HTTPError:
        return 0
    return 0


def update_readme(count: int) -> bool:
    """Update the Total Commits badge in README.md. Returns True if file changed."""
    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    badge_html = (
        "<!-- COMMITS_COUNT_START -->\n"
        f'  <img src="https://img.shields.io/badge/Total%20Commits-{count}-39A7FF?style=for-the-badge&logo=github" alt="Total Commits: {count}" />\n'
        "  <!-- COMMITS_COUNT_END -->"
    )

    pattern = re.compile(
        r"<!-- COMMITS_COUNT_START -->.*?<!-- COMMITS_COUNT_END -->",
        re.DOTALL,
    )
    if not pattern.search(content):
        print("Markers COMMITS_COUNT_START / COMMITS_COUNT_END not found in README.md", file=sys.stderr)
        return False

    updated = pattern.sub(badge_html, content, count=1)
    if updated == content:
        return False

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(updated)
    return True


def main() -> int:
    repo_branch_count = count_user_repo_branch_commits(USERNAME)
    search_count = count_search_commits(USERNAME)
    total = max(repo_branch_count, search_count)
    print(f"Counted commits for {USERNAME}: repos/branches={repo_branch_count}, search={search_count}, total={total}")
    changed = update_readme(total)
    print("README.md updated." if changed else "README.md already up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
