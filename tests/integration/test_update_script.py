"""Integration tests for vox-refiner-update.sh."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = "Test Bot"
    env["GIT_AUTHOR_EMAIL"] = "test@example.com"
    env["GIT_COMMITTER_NAME"] = "Test Bot"
    env["GIT_COMMITTER_EMAIL"] = "test@example.com"
    return env


def _run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, env=_env(), check=check, capture_output=True, text=True)


def _setup_repo_pair(tmp_path: Path) -> tuple[Path, Path]:
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"

    _run(["git", "init", "--bare", str(remote)], cwd=tmp_path)
    _run(["git", "clone", str(remote), str(work)], cwd=tmp_path)

    _run(["git", "checkout", "-b", "main"], cwd=work)
    (work / "README.md").write_text("init\n", encoding="utf-8")
    _run(["git", "add", "README.md"], cwd=work)
    _run(["git", "commit", "-m", "init"], cwd=work)
    _run(["git", "push", "-u", "origin", "main"], cwd=work)

    return remote, work


def _install_updater(work: Path, repo_root: Path) -> None:
    src = repo_root / "vox-refiner-update.sh"
    dst = work / "vox-refiner-update.sh"
    shutil.copy2(src, dst)
    dst.chmod(dst.stat().st_mode | stat.S_IXUSR)


def test_check_reports_up_to_date(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[2]
    _, work = _setup_repo_pair(tmp_path)
    _install_updater(work, repo_root)

    result = _run(["bash", "./vox-refiner-update.sh", "--check"], cwd=work)

    assert result.returncode == 0
    assert "Up to date" in result.stdout


def test_check_reports_update_available(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[2]
    remote, work = _setup_repo_pair(tmp_path)
    _install_updater(work, repo_root)

    # Create one commit ahead on a separate clone.
    other = tmp_path / "other"
    _run(["git", "clone", str(remote), str(other)], cwd=tmp_path)
    _run(["git", "checkout", "main"], cwd=other)
    (other / "README.md").write_text("init\nnew\n", encoding="utf-8")
    _run(["git", "add", "README.md"], cwd=other)
    _run(["git", "commit", "-m", "remote update"], cwd=other)
    _run(["git", "push"], cwd=other)

    result = _run(["bash", "./vox-refiner-update.sh", "--check"], cwd=work)

    assert result.returncode == 0
    assert "Update available" in result.stdout


def test_apply_refuses_dirty_tracked_tree(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[2]
    _, work = _setup_repo_pair(tmp_path)
    _install_updater(work, repo_root)

    (work / "README.md").write_text("dirty\n", encoding="utf-8")
    result = _run(["bash", "./vox-refiner-update.sh", "--apply"], cwd=work, check=False)

    assert result.returncode != 0
    assert "Local tracked changes detected" in (result.stdout + result.stderr)


def test_apply_auto_resolves_obsolete_local_deletion(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[2]
    remote, work = _setup_repo_pair(tmp_path)
    _install_updater(work, repo_root)

    legacy = work / "launch_vox-refiner.sh"
    legacy.write_text("#!/bin/bash\necho legacy\n", encoding="utf-8")
    _run(["git", "add", "launch_vox-refiner.sh"], cwd=work)
    _run(["git", "commit", "-m", "add legacy launcher"], cwd=work)
    _run(["git", "push"], cwd=work)

    # Remove the legacy file on remote via a second clone (upstream cleanup).
    other = tmp_path / "other"
    _run(["git", "clone", str(remote), str(other)], cwd=tmp_path)
    _run(["git", "checkout", "main"], cwd=other)
    _run(["git", "rm", "launch_vox-refiner.sh"], cwd=other)
    _run(["git", "commit", "-m", "remove legacy launcher"], cwd=other)
    _run(["git", "push"], cwd=other)

    # Local user also deleted this tracked file before update.
    legacy.unlink()

    result = _run(["bash", "./vox-refiner-update.sh", "--apply"], cwd=work)

    assert result.returncode == 0
    assert "Update applied successfully" in result.stdout
    assert not legacy.exists()
