"""Tests for the scripts behind the `Deploy functions` workflow.

The git-facing scripts run against a throwaway repository. The Azure-facing
scripts run against a fake `az` on PATH that records every call, so the tests
can check what would happen to Azure without touching it.
"""

import json
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


# --- fake az / curl ----------------------------------------------------------

# Records every call. Answers from environment variables:
# - FAKE_FAIL_ZIP: when set, `config-zip` exits 1.
# - FAKE_FUNCTIONS: `;`-separated answers to successive `function list` calls,
#   each a comma list of names (empty = none yet, ERR = the call fails). The
#   last answer repeats.
FAKE_AZ = r"""#!/usr/bin/env bash
echo "$*" >> "$FAKE_LOG"
case "$*" in
  "functionapp deployment source config-zip"*)
    [ -n "${FAKE_FAIL_ZIP:-}" ] && exit 1
    exit 0 ;;
  "functionapp function list"*)
    counter="$FAKE_LOG.list"
    n=$(cat "$counter" 2>/dev/null || echo 0)
    IFS=';' read -r -a steps <<< "${FAKE_FUNCTIONS:-}"
    step=""
    if [ "${#steps[@]}" -gt 0 ]; then
      last=$(( ${#steps[@]} - 1 ))
      idx=$(( n > last ? last : n ))
      step="${steps[$idx]}"
    fi
    echo $(( n + 1 )) > "$counter"
    [ "$step" = "ERR" ] && exit 1
    echo "$step" | tr ',' '\n' | sed '/^$/d'
    exit 0 ;;
  "account show"*tenantId*) echo "tenant-1"; exit 0 ;;
  "account show"*) echo "sub-1"; exit 0 ;;
  "identity show"*principalId*) echo "principal-1"; exit 0 ;;
  "identity show"*clientId*) echo "client-1"; exit 0 ;;
  "identity show"*)
    [ -n "${FAKE_IDENTITY_EXISTS:-}" ] && exit 0
    exit 1 ;;
  "functionapp show"*)
    echo "/subscriptions/sub-1/resourceGroups/rg-chatbot/providers/Microsoft.Web/sites/func-tfl-mcp"
    exit 0 ;;
  "identity federated-credential show"*)
    [ -n "${FAKE_CREDENTIAL_EXISTS:-}" ] && exit 0
    exit 1 ;;
esac
exit 0
"""

# Stands in for the GitHub CLI. Listing the environment's branch policies
# prints FAKE_POLICY_NAMES (`\n` separates names), as the script's --jq filter
# would. A user lookup prints the id 77542239. A request body given on stdin
# (`--input -`) is kept in `$FAKE_LOG.gh-body`.
FAKE_GH = r"""#!/usr/bin/env bash
echo "$*" >> "$FAKE_LOG.gh"
case "$*" in
  *"deployment-branch-policies"*)
    case "$*" in *"-X POST"*) exit 0 ;; esac
    printf '%b' "${FAKE_POLICY_NAMES:-}"
    exit 0 ;;
  *" users/"*) echo 77542239; exit 0 ;;
  *"--input -"*) cat >> "$FAKE_LOG.gh-body"; exit 0 ;;
esac
exit 0
"""

# Stands in for the GitHub Actions OIDC token endpoint.
FAKE_CURL = r"""#!/usr/bin/env bash
echo "$*" >> "$FAKE_LOG.curl"
echo '{"value":"fake-token"}'
"""

APP = "func-tfl-mcp"
RG = "rg-chatbot"


@dataclass
class FakeAz:
    log: Path
    bin_dir: Path

    def run(
        self, script: str, *args: str, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        return run_script(
            script,
            *args,
            cwd=REPO_ROOT,
            env={
                "PATH": f"{self.bin_dir}{os.pathsep}{os.environ['PATH']}",
                "FAKE_LOG": str(self.log),
                **(env or {}),
            },
        )

    def calls(self, suffix: str = "") -> list[str]:
        path = Path(f"{self.log}{suffix}")
        return path.read_text().splitlines() if path.exists() else []


@pytest.fixture
def fake_az(tmp_path: Path) -> FakeAz:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("az", FAKE_AZ), ("curl", FAKE_CURL), ("gh", FAKE_GH)):
        tool = bin_dir / name
        tool.write_text(body)
        tool.chmod(0o755)
    return FakeAz(log=tmp_path / "az.log", bin_dir=bin_dir)


# --- ci-azure-login.sh -------------------------------------------------------

LOGIN_ENV = {
    "AZURE_TENANT_ID": "tenant-1",
    "AZURE_SUBSCRIPTION_ID": "sub-1",
    "ACTIONS_ID_TOKEN_REQUEST_URL": "https://token.example.test/?api-version=2",
    "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "request-token",
}


def test_login_exchanges_the_token_for_the_identity(fake_az: FakeAz) -> None:
    result = fake_az.run("ci-azure-login.sh", "client-1", env=LOGIN_ENV)
    assert result.returncode == 0, result.stderr
    assert (
        "login --service-principal -u client-1 -t tenant-1 "
        "--federated-token fake-token --allow-no-subscriptions --output none"
    ) in fake_az.calls()
    assert "account set --subscription sub-1" in fake_az.calls()
    assert any(
        "audience=api://AzureADTokenExchange" in c for c in fake_az.calls(".curl")
    )


def test_login_fails_without_an_oidc_endpoint(fake_az: FakeAz) -> None:
    env = {**LOGIN_ENV, "ACTIONS_ID_TOKEN_REQUEST_URL": ""}
    result = fake_az.run("ci-azure-login.sh", "client-1", env=env)
    assert result.returncode == 1
    assert "id-token: write" in result.stderr
    assert fake_az.calls() == []


# --- deploy-functions.sh -----------------------------------------------------


@pytest.fixture
def zip_file(tmp_path: Path) -> Path:
    path = tmp_path / "functions.zip"
    path.write_bytes(b"zip")
    return path


def test_deploy_calls_config_zip_with_a_remote_build(
    fake_az: FakeAz, zip_file: Path
) -> None:
    result = fake_az.run(
        "deploy-functions.sh", str(zip_file), "5", "0", env={"FAKE_FUNCTIONS": "a"}
    )
    assert result.returncode == 0, result.stderr
    assert (
        f"functionapp deployment source config-zip -g {RG} -n {APP} "
        f"--src {zip_file} --build-remote true"
    ) in fake_az.calls()


def test_deploy_prints_the_functions_it_finds(fake_az: FakeAz, zip_file: Path) -> None:
    result = fake_az.run(
        "deploy-functions.sh",
        str(zip_file),
        "5",
        "0",
        env={"FAKE_FUNCTIONS": "get_tfl_status,find_station"},
    )
    assert result.returncode == 0, result.stderr
    assert "function: get_tfl_status" in result.stdout
    assert "function: find_station" in result.stdout


def test_deploy_waits_while_the_function_list_is_empty(
    fake_az: FakeAz, zip_file: Path
) -> None:
    result = fake_az.run(
        "deploy-functions.sh", str(zip_file), "30", "0", env={"FAKE_FUNCTIONS": ";;a"}
    )
    assert result.returncode == 0, result.stderr
    lists = [c for c in fake_az.calls() if c.startswith("functionapp function list")]
    assert len(lists) == 3


def test_deploy_fails_when_no_function_ever_appears(
    fake_az: FakeAz, zip_file: Path
) -> None:
    result = fake_az.run(
        "deploy-functions.sh", str(zip_file), "1", "0.1", env={"FAKE_FUNCTIONS": ""}
    )
    assert result.returncode == 1
    assert APP in result.stderr


def test_deploy_treats_a_list_error_as_empty(fake_az: FakeAz, zip_file: Path) -> None:
    result = fake_az.run(
        "deploy-functions.sh", str(zip_file), "30", "0", env={"FAKE_FUNCTIONS": "ERR;a"}
    )
    assert result.returncode == 0, result.stderr
    assert "function: a" in result.stdout


def test_deploy_stops_when_config_zip_fails_and_never_lists(
    fake_az: FakeAz, zip_file: Path
) -> None:
    result = fake_az.run(
        "deploy-functions.sh",
        str(zip_file),
        "5",
        "0",
        env={"FAKE_FAIL_ZIP": "1", "FAKE_FUNCTIONS": "a"},
    )
    assert result.returncode == 1
    assert not any(c.startswith("functionapp function list") for c in fake_az.calls())


def test_deploy_rejects_a_missing_zip(fake_az: FakeAz, tmp_path: Path) -> None:
    result = fake_az.run("deploy-functions.sh", str(tmp_path / "nope.zip"))
    assert result.returncode == 1
    assert "nope.zip" in result.stderr
    assert fake_az.calls() == []


# --- setup-github-deploy.sh --------------------------------------------------

REPO = "Fredheda/tfl-mcp"
FUNCTION_APP_ID = (
    "/subscriptions/sub-1/resourceGroups/rg-chatbot/providers/Microsoft.Web/sites/"
    "func-tfl-mcp"
)


def test_setup_grants_website_contributor_on_the_function_app_only(
    fake_az: FakeAz,
) -> None:
    result = fake_az.run("setup-github-deploy.sh")
    assert result.returncode == 0, result.stderr
    roles = [c for c in fake_az.calls() if c.startswith("role assignment create")]
    assert len(roles) == 1
    assert "--role Website Contributor" in roles[0]
    assert f"--scope {FUNCTION_APP_ID}" in roles[0]
    assert "--assignee-object-id principal-1" in roles[0]


def test_setup_trusts_only_the_production_environment(fake_az: FakeAz) -> None:
    result = fake_az.run("setup-github-deploy.sh")
    assert result.returncode == 0, result.stderr
    creds = [
        c
        for c in fake_az.calls()
        if c.startswith("identity federated-credential create")
    ]
    assert len(creds) == 1
    assert f"--subject repo:{REPO}:environment:production" in creds[0]
    assert "--audiences api://AzureADTokenExchange" in creds[0]


def environment_body(fake_az: FakeAz) -> dict[str, object]:
    """The JSON the script sends to `PUT .../environments/production`."""
    return json.loads(Path(f"{fake_az.log}.gh-body").read_text())


def test_setup_restricts_the_environment_to_main(fake_az: FakeAz) -> None:
    result = fake_az.run("setup-github-deploy.sh")
    assert result.returncode == 0, result.stderr
    gh = fake_az.calls(".gh")
    put = [c for c in gh if f"api -X PUT repos/{REPO}/environments/production" in c]
    assert len(put) == 1
    assert environment_body(fake_az)["deployment_branch_policy"] == {
        "protected_branches": False,
        "custom_branch_policies": True,
    }
    assert any(
        "-X POST" in c and "deployment-branch-policies" in c and "name=main" in c
        for c in gh
    )


def test_setup_makes_the_repo_owner_the_required_reviewer(fake_az: FakeAz) -> None:
    # Every deploy then waits for the owner's approval in GitHub, and no admin
    # can bypass the gate.
    result = fake_az.run("setup-github-deploy.sh")
    assert result.returncode == 0, result.stderr
    assert "api users/Fredheda --jq .id" in fake_az.calls(".gh")
    body = environment_body(fake_az)
    assert body["reviewers"] == [{"type": "User", "id": 77542239}]
    assert body["prevent_self_review"] is False
    assert body["can_admins_bypass"] is False


def test_setup_does_not_add_the_main_policy_twice(fake_az: FakeAz) -> None:
    result = fake_az.run("setup-github-deploy.sh", env={"FAKE_POLICY_NAMES": "main"})
    assert result.returncode == 0, result.stderr
    assert not any("-X POST" in c for c in fake_az.calls(".gh"))


def test_setup_warns_about_other_branch_policies(fake_az: FakeAz) -> None:
    result = fake_az.run(
        "setup-github-deploy.sh", env={"FAKE_POLICY_NAMES": "main\\nfeature"}
    )
    assert result.returncode == 0, result.stderr
    assert "feature" in result.stderr


def test_setup_twice_creates_nothing_new(fake_az: FakeAz) -> None:
    result = fake_az.run(
        "setup-github-deploy.sh",
        env={"FAKE_IDENTITY_EXISTS": "1", "FAKE_CREDENTIAL_EXISTS": "1"},
    )
    assert result.returncode == 0, result.stderr
    calls = fake_az.calls()
    assert not any(c.startswith("identity create") for c in calls)
    assert not any(c.startswith("identity federated-credential create") for c in calls)


def test_setup_stores_the_three_ids_as_secrets_so_logs_mask_them(
    fake_az: FakeAz,
) -> None:
    result = fake_az.run("setup-github-deploy.sh")
    assert result.returncode == 0, result.stderr
    gh = fake_az.calls(".gh")
    for name, value in (
        ("AZURE_TENANT_ID", "tenant-1"),
        ("AZURE_SUBSCRIPTION_ID", "sub-1"),
        ("AZURE_DEPLOY_CLIENT_ID", "client-1"),
    ):
        assert f"secret set {name} --body {value} -R {REPO}" in gh
    assert not any("variable set" in c for c in gh)


def test_workflow_reads_the_azure_ids_from_secrets_not_variables() -> None:
    # Variables are printed in clear text in the (public) run logs; secrets
    # are masked.
    text = (REPO_ROOT / ".github" / "workflows" / "deploy-functions.yml").read_text()
    assert "vars.AZURE_" not in text
    for name in ("AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID", "AZURE_DEPLOY_CLIENT_ID"):
        assert f"secrets.{name}" in text
