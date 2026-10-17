# Github Cleanup Check Script
# 删除 GitHub 仓库中所有 Actions workflow run
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..", "pipeline")))
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import argparse
import os
import sys
import time
from typing import Generator, Optional

import httpx
from base_config import GITHUB_INTERFACE_CONFIG

HTTP_TIMEOUT_SEC = 30
GITHUB_API_BASE = "https://api.github.com"


def log_status(stage: str, msg: str, status: str = "INFO"):
    print(f"[{stage}] {status}: {msg}")


def _github_request(
    method: str,
    url: str,
    token: str,
    expected_statuses: Optional[set[int]] = None,
    **kwargs,
) -> Optional[httpx.Response]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"Bearer {token}",
    }
    timeout = kwargs.pop("timeout", HTTP_TIMEOUT_SEC)
    follow_redirects = kwargs.pop("follow_redirects", True)
    for attempt in range(3):
        try:
            response = httpx.request(
                method,
                url,
                headers=headers,
                timeout=timeout,
                follow_redirects=follow_redirects,
                **kwargs,
            )
            if expected_statuses:
                if response.status_code in expected_statuses:
                    return response
            elif response.status_code < 500:
                return response
            log_status(
                "GITHUB",
                f"GitHub API returned {response.status_code} on attempt {attempt + 1}: {response.text[:200]}",
                "WARN",
            )
        except httpx.HTTPError as exc:
            log_status("GITHUB", f"GitHub request failed on attempt {attempt + 1}: {exc}", "WARN")
        time.sleep(2)
    return None


def list_workflow_runs(
    token: str,
    repo_owner: str,
    repo_name: str,
    per_page: int = 100,
) -> Generator[dict, None, None]:
    page = 1
    while True:
        url = f"{GITHUB_API_BASE}/repos/{repo_owner}/{repo_name}/actions/runs?per_page={per_page}&page={page}"
        response = _github_request("GET", url, token, expected_statuses={200})
        if response is None:
            log_status("GITHUB", f"Failed to list workflow runs on page {page}.", "ERROR")
            break

        payload = response.json()
        runs = payload.get("workflow_runs", [])
        if not runs:
            break

        for run in runs:
            yield run

        if len(runs) < per_page:
            break
        page += 1


def delete_workflow_run(token: str, repo_owner: str, repo_name: str, run_id: int) -> bool:
    url = f"{GITHUB_API_BASE}/repos/{repo_owner}/{repo_name}/actions/runs/{run_id}"
    response = _github_request("DELETE", url, token, expected_statuses={204})
    return response is not None and response.status_code == 204


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Delete all GitHub workflow runs from a repository.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--token", help="GitHub personal access token.")
    parser.add_argument("--repo-owner", help="GitHub repo owner.")
    parser.add_argument("--repo-name", help="GitHub repo name.")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt.")
    parser.add_argument("--dry-run", action="store_true", help="List workflow runs without deleting them.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    token = (
        args.token
        or GITHUB_INTERFACE_CONFIG.get("TOKEN")
        or os.getenv("GITHUB_TOKEN")
    )
    repo_owner = (
        args.repo_owner
        or GITHUB_INTERFACE_CONFIG.get("REPO_OWNER")
        or os.getenv("GITHUB_REPO_OWNER")
        or os.getenv("REPO_OWNER", "OZinOZ")
    )
    repo_name = (
        args.repo_name
        or GITHUB_INTERFACE_CONFIG.get("REPO_NAME")
        or os.getenv("GITHUB_REPO_NAME")
        or os.getenv("REPO_NAME", "AiGenGitHub")
    )

    if not token or not repo_owner or not repo_name:
        log_status(
            "GITHUB",
            "Missing GitHub configuration. Set --token, --repo-owner, --repo-name or environment variables.",
            "ERROR",
        )
        return 1

    if not args.yes:
        answer = input(
            f"Delete all workflow runs in {repo_owner}/{repo_name}? This cannot be undone. [y/N]: "
        ).strip().lower()
        if answer not in {"y", "yes"}:
            log_status("GITHUB", "Operation cancelled by user.", "INFO")
            return 0

    runs = list(list_workflow_runs(token, repo_owner, repo_name))
    total = len(runs)
    if total == 0:
        log_status("GITHUB", "No workflow runs found.", "OK")
        return 0

    log_status("GITHUB", f"Found {total} workflow run(s).", "INFO")
    if args.dry_run:
        for run in runs:
            log_status(
                "GITHUB",
                f"Dry run: would delete run #{run.get('id')} status={run.get('status')} conclusion={run.get('conclusion')}",
                "INFO",
            )
        return 0

    deleted = 0
    failed = 0
    for run in runs:
        run_id = run.get("id")
        if not run_id:
            continue
        if delete_workflow_run(token, repo_owner, repo_name, run_id):
            deleted += 1
            log_status("GITHUB", f"Deleted workflow run {run_id}.", "OK")
        else:
            failed += 1
            log_status("GITHUB", f"Failed to delete workflow run {run_id}.", "ERROR")
        time.sleep(0.3)

    log_status(
        "GITHUB",
        f"Delete complete. success={deleted}, failed={failed}, total={total}.",
        "OK" if failed == 0 else "WARN",
    )
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
