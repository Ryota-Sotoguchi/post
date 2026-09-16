from __future__ import annotations

import subprocess
from pathlib import Path

from tiktok_poster import pages
from tiktok_poster.config import Config


def _run(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def test_push_succeeds_when_the_remote_moved_on_meanwhile(tmp_path: Path, config: Config) -> None:
    # Actions commits state/posted.json every hour, so the remote is usually
    # ahead by the time sync runs on the PC. A bare push was rejected there.
    remote = tmp_path / "remote.git"
    _run(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))

    local = config.project_root
    _run(local, "init", "-q", "-b", "main")
    _run(local, "config", "user.email", "t@example.com")
    _run(local, "config", "user.name", "t")
    (local / "state").mkdir(exist_ok=True)
    (local / "state" / "posted.json").write_text('{"records": []}', encoding="utf-8")
    _run(local, "add", "-A")
    _run(local, "commit", "-q", "-m", "base")
    _run(local, "remote", "add", "origin", str(remote))
    _run(local, "push", "-q", "origin", "main")

    # Someone else - the Actions run - pushes a state commit.
    other = tmp_path / "actions"
    _run(tmp_path, "clone", "-q", str(remote), str(other))
    _run(other, "config", "user.email", "a@example.com")
    _run(other, "config", "user.name", "a")
    (other / "state" / "posted.json").write_text('{"records": [1]}', encoding="utf-8")
    _run(other, "commit", "-q", "-am", "state: sent via Actions")
    _run(other, "push", "-q", "origin", "main")

    # Meanwhile the PC produces new media.
    config.publish_dir.mkdir(parents=True, exist_ok=True)
    (config.publish_dir / "manifest.json").write_text("{}", encoding="utf-8")

    assert pages.push(config, "media: sync 1 carousel(s)")
    log = _run(remote, "log", "--format=%s", "main")
    assert "media: sync 1 carousel(s)" in log
    assert "state: sent via Actions" in log
