from __future__ import annotations

import subprocess
import time
from pathlib import Path

import requests

from tiktok_poster.config import Config

# Pages needs a moment to build after a push, and TikTok rejects a URL it
# cannot fetch, so the publish step waits for the files to actually serve.
POLL_ATTEMPTS = 40
POLL_DELAY = 15
HEAD_TIMEOUT = 20


class PagesError(RuntimeError):
    pass


def _git(config: Config, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=config.project_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise PagesError(f"git {' '.join(args)} failed: {result.stderr.strip() or result.stdout.strip()}")
    return result.stdout.strip()


def has_changes(config: Config) -> bool:
    return bool(_git(config, "status", "--porcelain", "--", str(config.publish_dir)))


def push(config: Config, message: str) -> bool:
    """Commit and push the media tree. Returns False when nothing changed."""
    if not has_changes(config):
        return False
    _git(config, "add", "--", str(config.publish_dir))
    _git(config, "commit", "-m", message)
    branch = _git(config, "rev-parse", "--abbrev-ref", "HEAD")
    _git(config, "push", "origin", f"HEAD:{branch}")
    return True


def wait_until_live(urls: list[str], attempts: int = POLL_ATTEMPTS, delay: int = POLL_DELAY) -> None:
    """Block until every URL serves, so TikTok never pulls a 404."""
    if not urls:
        return
    # The last file to deploy gates the rest, so probe both ends.
    probes = [urls[0], urls[-1]]
    for attempt in range(1, attempts + 1):
        try:
            responses = [requests.head(url, timeout=HEAD_TIMEOUT, allow_redirects=False) for url in probes]
        except requests.RequestException:
            responses = []
        if responses and all(response.status_code == 200 for response in responses):
            return
        if attempt < attempts:
            time.sleep(delay)
    raise PagesError(f"Pages did not serve {probes[0]} within {attempts * delay}s")
