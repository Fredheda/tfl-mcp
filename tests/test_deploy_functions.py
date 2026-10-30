"""Tests for the scripts behind the `Deploy functions` workflow.

The git-facing scripts run against a throwaway repository. The Azure-facing
scripts run against a fake `az` on PATH that records every call, so the tests
can check what would happen to Azure without touching it.
"""

import os
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"


def run_script(
    script: str,
    *args: str,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPTS / script), *args],
        cwd=cwd,
        env={**os.environ, **(env or {})},
        capture_output=True,
        text=True,
        timeout=60,
    )


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.test",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


@dataclass
class GitRepo:
    path: Path
    a: str  # on main, before function_app/ existed
    b: str  # head of origin/main, has function_app/
    c: str  # on a side branch, not on main


FUNCTION_FILES = [
    "function_app/function_app.py",
    "function_app/host.json",
    "function_app/requirements.txt",
    "tfl_status.py",
]


@pytest.fixture
def git_repo(tmp_path: Path) -> GitRepo:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "README.md").write_text("readme\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "a")
    a = git(repo, "rev-parse", "HEAD")
    for name in FUNCTION_FILES:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {name}\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "b")
    b = git(repo, "rev-parse", "HEAD")
    git(repo, "update-ref", "refs/remotes/origin/main", b)
    git(repo, "switch", "-q", "-c", "side")
    (repo / "side.txt").write_text("side\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "c")
    c = git(repo, "rev-parse", "HEAD")
    return GitRepo(path=repo, a=a, b=b, c=c)


# --- resolve-deploy-sha.sh ---------------------------------------------------


def test_resolve_defaults_to_head_of_main(git_repo: GitRepo) -> None:
    result = run_script("resolve-deploy-sha.sh", cwd=git_repo.path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == git_repo.b


def test_resolve_trims_whitespace_and_newline(git_repo: GitRepo) -> None:
    result = run_script("resolve-deploy-sha.sh", f" {git_repo.b}\n", cwd=git_repo.path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == git_repo.b


@pytest.mark.parametrize("bad", ["abc1234", "UPPER", "main", "HEAD~1", "g" * 40])
def test_resolve_rejects_short_uppercase_and_garbage(
    git_repo: GitRepo, bad: str
) -> None:
    value = git_repo.b.upper() if bad == "UPPER" else bad
    result = run_script("resolve-deploy-sha.sh", value, cwd=git_repo.path)
    assert result.returncode == 1
    assert "is not a full 40-character" in result.stderr


def test_resolve_rejects_a_sha_the_repo_does_not_know(git_repo: GitRepo) -> None:
    result = run_script("resolve-deploy-sha.sh", "0" * 40, cwd=git_repo.path)
    assert result.returncode == 1
    assert "is not a commit" in result.stderr


def test_resolve_rejects_sha_not_on_main(git_repo: GitRepo) -> None:
    result = run_script("resolve-deploy-sha.sh", git_repo.c, cwd=git_repo.path)
    assert result.returncode == 1
    assert "is not on main" in result.stderr


def test_resolve_rejects_commit_without_function_folder(git_repo: GitRepo) -> None:
    result = run_script("resolve-deploy-sha.sh", git_repo.a, cwd=git_repo.path)
    assert result.returncode == 1
    assert "function_app/function_app.py" in result.stderr


# --- package-functions.sh ----------------------------------------------------


def make_source_root(root: Path) -> Path:
    files = {
        "function_app/function_app.py": "app\n",
        "function_app/host.json": "{}\n",
        "function_app/requirements.txt": "azure-functions\n",
        "function_app/local.settings.json": "{}\n",
        "function_app/local.settings.json.example": "{}\n",
        "function_app/tests/test_x.py": "def test_x(): pass\n",
        "function_app/__pycache__/x.pyc": "pyc\n",
        "function_app/.gitignore": "*.pyc\n",
        "tfl_status.py": "shared logic\n",
    }
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


def zip_names(path: Path) -> set[str]:
    with zipfile.ZipFile(path) as archive:
        return set(archive.namelist())


def test_package_has_the_copied_in_file_and_no_local_files(tmp_path: Path) -> None:
    src = make_source_root(tmp_path / "src")
    out = tmp_path / "out" / "functions.zip"
    out.parent.mkdir()
    result = run_script("package-functions.sh", str(src), str(out), cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    names = zip_names(out)
    assert {
        "function_app.py",
        "host.json",
        "requirements.txt",
        "tfl_status.py",
    } <= names
    assert not any(
        part in name
        for name in names
        for part in ("local.settings", "tests", "__pycache__", ".pyc", ".gitignore")
    )


def test_package_works_on_a_root_that_is_not_the_checkout(tmp_path: Path) -> None:
    # The rollback case: the target commit's sources sit in a temp directory,
    # and the script must read nothing from the directory it runs in.
    src = make_source_root(tmp_path / "elsewhere" / "src")
    other = tmp_path / "cwd"
    other.mkdir()
    out = tmp_path / "functions.zip"
    result = run_script("package-functions.sh", str(src), str(out), cwd=other)
    assert result.returncode == 0, result.stderr
    assert "tfl_status.py" in zip_names(out)


def test_package_takes_the_shared_file_from_the_given_root(tmp_path: Path) -> None:
    src = make_source_root(tmp_path / "src")
    out = tmp_path / "functions.zip"
    run_script("package-functions.sh", str(src), str(out), cwd=tmp_path)
    with zipfile.ZipFile(out) as archive:
        assert archive.read("tfl_status.py") == b"shared logic\n"


def test_package_fails_clearly_when_inputs_are_missing(tmp_path: Path) -> None:
    out = tmp_path / "functions.zip"
    no_folder = tmp_path / "no_folder"
    no_folder.mkdir()
    (no_folder / "tfl_status.py").write_text("x\n")
    result = run_script("package-functions.sh", str(no_folder), str(out), cwd=tmp_path)
    assert result.returncode == 1
    assert "function_app" in result.stderr

    no_shared = tmp_path / "no_shared"
    (no_shared / "function_app").mkdir(parents=True)
    result = run_script("package-functions.sh", str(no_shared), str(out), cwd=tmp_path)
    assert result.returncode == 1
    assert "tfl_status.py" in result.stderr
    assert not out.exists()
