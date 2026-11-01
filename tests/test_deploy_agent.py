"""Tests for the scripts behind the `Deploy agent` workflow.

The Azure- and GitHub-facing scripts run against a fake `az`, `gh` and `curl`
on PATH that record every call, so the tests can check what would happen to
Azure and GitHub without touching them. The fakes answer from environment
variables:

- FAKE_MISSING: comma list of `repo:tag`; `az acr repository show` exits 1 for them.
- FAKE_FAIL_UPDATE: when set, `az containerapp update` exits 1.
- FAKE_IMAGE: image printed for `az containerapp show ... image`.
- FAKE_PUBLIC_URL: value of the app's TFL_STATUS_AGENT_PUBLIC_URL env var.
- FAKE_HTTP_CODES: comma list of status codes, one per `curl` call (the last repeats).
- FAKE_PROVISIONING: comma list of revision states, one per `az containerapp
  revision show` call (the last repeats).
- FAKE_NO_CRED / FAKE_NO_TASK: federated credentials / the purge task that do not exist yet.
- FAKE_POLICY_NAMES: branch policies of the `production` environment, one per line.
"""

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"

FAKE_AZ = r"""#!/usr/bin/env bash
echo "$*" >> "$FAKE_LOG"
case "$*" in
  "acr repository show"*)
    image=$(echo "$*" | sed -E 's/.*--image ([^ ]+).*/\1/')
    case ",${FAKE_MISSING:-}," in *",$image,"*) exit 1 ;; esac
    exit 0 ;;
  "acr show"*) echo "/acr-id"; exit 0 ;;
  "identity federated-credential show"*)
    cred=$(echo "$*" | sed -E 's/.*--name ([^ ]+).*/\1/')
    case ",${FAKE_NO_CRED:-}," in *",$cred,"*) exit 1 ;; esac
    exit 0 ;;
  "identity show"*)
    name=$(echo "$*" | sed -E 's/.* -n ([^ ]+).*/\1/')
    case "$*" in
      *principalId*) echo "principal-$name" ;;
      *clientId*) echo "client-$name" ;;
      *) echo "/identity/$name" ;;
    esac
    exit 0 ;;
  "acr build"*)
    echo "$PWD $(test -f tfl_status_agent/Dockerfile && echo has-dockerfile)" >> "$FAKE_LOG.build-dir"
    exit 0 ;;
  "containerapp update"*)
    [ -n "${FAKE_FAIL_UPDATE:-}" ] && exit 1
    exit 0 ;;
  "containerapp show"*latestRevisionName*) echo "ca-tfl-status-agent--rev1"; exit 0 ;;
  "containerapp show"*PUBLIC_URL*) echo "${FAKE_PUBLIC_URL-https://agent.example.test}"; exit 0 ;;
  "containerapp show"*ingress.fqdn*) echo "agent.example.test"; exit 0 ;;
  "containerapp show"*image*) echo "${FAKE_IMAGE:-}"; exit 0 ;;
  "containerapp show"*) echo "/app-id"; exit 0 ;;
  "acr task show"*)
    [ -n "${FAKE_NO_TASK:-}" ] && exit 1
    exit 0 ;;
  "containerapp revision show"*)
    counter="$FAKE_LOG.provisioning"
    n=$(cat "$counter" 2>/dev/null || echo 0)
    IFS=',' read -r -a states <<< "${FAKE_PROVISIONING:-Provisioned}"
    last=$(( ${#states[@]} - 1 ))
    idx=$(( n > last ? last : n ))
    echo "${states[$idx]}"
    echo $(( n + 1 )) > "$counter"
    exit 0 ;;
  "account show"*) echo "account-value"; exit 0 ;;
esac
exit 0
"""

FAKE_CURL = r"""#!/usr/bin/env bash
echo "$*" >> "$FAKE_LOG.curl"
counter="$FAKE_LOG.curl-count"
n=$(cat "$counter" 2>/dev/null || echo 0)
IFS=',' read -r -a codes <<< "${FAKE_HTTP_CODES:-401}"
last=$(( ${#codes[@]} - 1 ))
idx=$(( n > last ? last : n ))
printf '%s' "${codes[$idx]}"
echo $(( n + 1 )) > "$counter"
"""

# A user lookup prints the id 77542239. A request body given on stdin
# (`--input -`) is kept in `$FAKE_LOG.gh-body`.
FAKE_GH = r"""#!/usr/bin/env bash
echo "$*" >> "$FAKE_LOG.gh"
case "$*" in
  *"deployment-branch-policies"*)
    case "$*" in *"-X POST"*) exit 0 ;; esac
    printf '%s' "${FAKE_POLICY_NAMES:-}"
    exit 0 ;;
  *" users/"*) echo 77542239; exit 0 ;;
  *"--input -"*) cat >> "$FAKE_LOG.gh-body"; exit 0 ;;
esac
exit 0
"""


@dataclass
class Fakes:
    log: Path
    bin_dir: Path

    def run(
        self, script: str, *args: str, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(SCRIPTS / script), *args],
            cwd=REPO_ROOT,
            env={
                **os.environ,
                "PATH": f"{self.bin_dir}{os.pathsep}{os.environ['PATH']}",
                "FAKE_LOG": str(self.log),
                **(env or {}),
            },
            capture_output=True,
            text=True,
            timeout=60,
        )

    def lines(self, suffix: str = "") -> list[str]:
        path = Path(f"{self.log}{suffix}")
        return path.read_text().splitlines() if path.exists() else []

    @property
    def calls(self) -> list[str]:
        return self.lines()

    @property
    def gh_calls(self) -> list[str]:
        return self.lines(".gh")


@pytest.fixture
def fakes(tmp_path: Path) -> Fakes:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("az", FAKE_AZ), ("curl", FAKE_CURL), ("gh", FAKE_GH)):
        tool = bin_dir / name
        tool.write_text(body)
        tool.chmod(0o755)
    return Fakes(log=tmp_path / "az.log", bin_dir=bin_dir)


def source_and_run(snippet: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", f"source scripts/lib/images.sh; {snippet}", "bash", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )


NEW = "b" * 40
OLD = "a" * 40
REPO = "tfl-status-agent"
APP = "ca-tfl-status-agent"


def image(tag: str) -> str:
    return f"acrchatbotfredheda.azurecr.io/{REPO}:{tag}"


def updates(fakes: Fakes) -> list[str]:
    return [c for c in fakes.calls if c.startswith("containerapp update")]


def lock_calls(fakes: Fakes) -> list[str]:
    return [c for c in fakes.calls if c.startswith("acr repository update")]


def test_is_sha_accepts_only_40_lowercase_hex() -> None:
    assert source_and_run('is_sha "$1"', "a" * 40).returncode == 0
    for bad in ("a" * 39, "a" * 41, "A" * 40, "main", "", "g" * 40):
        assert source_and_run('is_sha "$1"', bad).returncode != 0, bad


def test_redeploy_rejects_non_sha_before_any_az_call(fakes: Fakes) -> None:
    for bad in ("main", "b" * 39, "B" * 40):
        result = fakes.run("redeploy.sh", bad)
        assert result.returncode == 2, bad
    assert fakes.calls == []


def test_redeploy_refuses_when_the_image_is_missing(fakes: Fakes) -> None:
    result = fakes.run(
        "redeploy.sh",
        NEW,
        env={"FAKE_MISSING": f"{REPO}:{NEW}", "FAKE_IMAGE": image(OLD)},
    )
    assert result.returncode == 1
    assert updates(fakes) == []
    assert lock_calls(fakes) == []
    assert REPO in result.stderr


def test_redeploy_rolls_the_app_to_the_sha_tag(fakes: Fakes) -> None:
    result = fakes.run("redeploy.sh", NEW, env={"FAKE_IMAGE": image(OLD)})
    assert result.returncode == 0, result.stderr
    (update,) = updates(fakes)
    assert f"-n {APP}" in update
    assert f"--image {image(NEW)}" in update


def test_redeploy_locks_the_new_tag_and_unlocks_the_replaced_one(fakes: Fakes) -> None:
    result = fakes.run("redeploy.sh", NEW, env={"FAKE_IMAGE": image(OLD)})
    assert result.returncode == 0, result.stderr
    locks = lock_calls(fakes)
    assert any(
        f"--image {REPO}:{NEW}" in c and "--delete-enabled false" in c for c in locks
    )
    assert any(
        f"--image {REPO}:{OLD}" in c and "--delete-enabled true" in c for c in locks
    )


@pytest.mark.parametrize("current", [image("latest"), "not-an-image", image(NEW)])
def test_redeploy_never_unlocks_latest_a_non_sha_or_the_same_sha(
    fakes: Fakes, current: str
) -> None:
    result = fakes.run("redeploy.sh", NEW, env={"FAKE_IMAGE": current})
    assert result.returncode == 0, result.stderr
    assert not any("--delete-enabled true" in c for c in lock_calls(fakes))
    assert sum("--delete-enabled false" in c for c in lock_calls(fakes)) == 1


def test_redeploy_failed_update_changes_no_locks(fakes: Fakes) -> None:
    result = fakes.run(
        "redeploy.sh", NEW, env={"FAKE_IMAGE": image(OLD), "FAKE_FAIL_UPDATE": "1"}
    )
    assert result.returncode != 0
    assert lock_calls(fakes) == []


def head_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def builds(fakes: Fakes) -> list[str]:
    return [c for c in fakes.calls if c.startswith("acr build")]


def test_build_push_builds_the_agent_image_when_it_is_missing(fakes: Fakes) -> None:
    sha = head_sha()
    result = fakes.run("build-push.sh", env={"FAKE_MISSING": f"{REPO}:{sha}"})
    assert result.returncode == 0, result.stderr
    (build,) = builds(fakes)
    assert "--file tfl_status_agent/Dockerfile" in build
    assert f"--image {REPO}:latest" in build
    assert f"--image {REPO}:{sha}" in build
    assert build.endswith(" .")


def test_build_push_skips_an_image_that_already_exists(fakes: Fakes) -> None:
    result = fakes.run("build-push.sh")
    assert result.returncode == 0, result.stderr
    assert builds(fakes) == []


def test_build_push_builds_the_given_commit_from_an_archive(fakes: Fakes) -> None:
    # The Deploy workflow builds a SHA that is not necessarily the checkout, so
    # the build runs from `git archive <sha>`, never from the working tree.
    sha = head_sha()
    result = fakes.run("build-push.sh", sha, env={"FAKE_MISSING": f"{REPO}:{sha}"})
    assert result.returncode == 0, result.stderr
    (entry,) = fakes.lines(".build-dir")
    directory, _, marker = entry.partition(" ")
    assert Path(directory).resolve() != REPO_ROOT.resolve()
    assert marker == "has-dockerfile"
    assert not Path(directory).exists()  # temp dir removed afterwards


@pytest.mark.parametrize("bad", ["main", "b" * 39, "B" * 40, "b" * 40])
def test_build_push_rejects_a_bad_or_unknown_sha_before_any_az_call(
    fakes: Fakes, bad: str
) -> None:
    # "b" * 40 is a well-formed SHA that is not a commit in this repository.
    result = fakes.run("build-push.sh", bad)
    assert result.returncode != 0
    assert fakes.calls == []


def revision_polls(fakes: Fakes) -> int:
    return sum(c.startswith("containerapp revision show") for c in fakes.calls)


def test_wait_healthy_passes_when_provisioned(fakes: Fakes) -> None:
    result = fakes.run(
        "wait-healthy.sh",
        "10",
        "0",
        env={"FAKE_PROVISIONING": "Provisioning,Provisioned"},
    )
    assert result.returncode == 0, result.stderr
    assert revision_polls(fakes) == 2


def test_wait_healthy_fails_fast_on_a_failed_revision(fakes: Fakes) -> None:
    result = fakes.run(
        "wait-healthy.sh", "10", "0", env={"FAKE_PROVISIONING": "Failed"}
    )
    assert result.returncode == 1
    assert APP in result.stderr
    assert revision_polls(fakes) == 1


def test_wait_healthy_times_out(fakes: Fakes) -> None:
    result = fakes.run(
        "wait-healthy.sh", "2", "1", env={"FAKE_PROVISIONING": "Provisioning"}
    )
    assert result.returncode == 1
    assert "timed out" in result.stderr


def test_check_agent_passes_with_the_public_address_and_the_auth_gate_on(
    fakes: Fakes,
) -> None:
    result = fakes.run("check-agent.sh", "10", "0")
    assert result.returncode == 0, result.stderr
    (request,) = fakes.lines(".curl")
    assert "https://agent.example.test/.well-known/agent-card.json" in request


def test_check_agent_retries_while_the_app_is_starting(fakes: Fakes) -> None:
    result = fakes.run(
        "check-agent.sh", "10", "0", env={"FAKE_HTTP_CODES": "000,503,401"}
    )
    assert result.returncode == 0, result.stderr
    assert len(fakes.lines(".curl")) == 3


@pytest.mark.parametrize(
    "public_url", ["http://localhost:8002", "https://other.example.test", ""]
)
def test_check_agent_fails_when_the_card_address_is_not_the_public_one(
    fakes: Fakes, public_url: str
) -> None:
    result = fakes.run("check-agent.sh", "10", "0", env={"FAKE_PUBLIC_URL": public_url})
    assert result.returncode == 1
    assert "TFL_STATUS_AGENT_PUBLIC_URL" in result.stderr
    assert fakes.lines(".curl") == []


def test_check_agent_fails_at_once_when_the_card_is_served_without_a_token(
    fakes: Fakes,
) -> None:
    result = fakes.run("check-agent.sh", "10", "0", env={"FAKE_HTTP_CODES": "200"})
    assert result.returncode == 1
    assert "auth" in result.stderr.lower()
    assert len(fakes.lines(".curl")) == 1


def test_check_agent_times_out_when_the_app_never_answers(fakes: Fakes) -> None:
    result = fakes.run("check-agent.sh", "2", "1", env={"FAKE_HTTP_CODES": "503"})
    assert result.returncode == 1
    assert "timed out" in result.stderr


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
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
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> dict[str, str | Path]:
    """A throwaway repository: two commits on main (mirrored as origin/main) and
    one commit that is only on a side branch."""
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "a.txt").write_text("a")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "first")
    first = git(root, "rev-parse", "HEAD")
    (root / "b.txt").write_text("b")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "second")
    second = git(root, "rev-parse", "HEAD")
    git(root, "update-ref", "refs/remotes/origin/main", second)
    git(root, "switch", "-q", "-c", "side")
    (root / "c.txt").write_text("c")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "side")
    side = git(root, "rev-parse", "HEAD")
    return {"root": root, "first": first, "second": second, "side": side}


def resolve(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPTS / "resolve-agent-sha.sh"), *args],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_resolve_agent_sha_defaults_to_the_head_of_origin_main(repo) -> None:
    result = resolve(repo["root"])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == repo["second"]


def test_resolve_agent_sha_accepts_an_older_commit_on_main(repo) -> None:
    result = resolve(repo["root"], str(repo["first"]))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == repo["first"]


@pytest.mark.parametrize("bad", ["main", "abc1234", "A" * 40, "g" * 40])
def test_resolve_agent_sha_rejects_a_malformed_sha(repo, bad: str) -> None:
    result = resolve(repo["root"], bad)
    assert result.returncode == 1
    assert "ERROR" in result.stderr


def test_resolve_agent_sha_rejects_an_unknown_commit(repo) -> None:
    result = resolve(repo["root"], "d" * 40)
    assert result.returncode == 1
    assert "not a commit" in result.stderr


def test_resolve_agent_sha_rejects_a_commit_that_is_not_on_main(repo) -> None:
    result = resolve(repo["root"], str(repo["side"]))
    assert result.returncode == 1
    assert "not on main" in result.stderr


PROD_SUBJECT = "repo:Fredheda/tfl-mcp:environment:production"


def role_calls(fakes: Fakes) -> list[str]:
    return [c for c in fakes.calls if c.startswith("role assignment create")]


def roles_of(fakes: Fakes, principal: str) -> set[tuple[str, str]]:
    result = set()
    for call in role_calls(fakes):
        if f"--assignee-object-id {principal} " not in call:
            continue
        role = call.split("--role ")[1].split(" --scope ")[0]
        scope = call.split("--scope ")[1].split(" ")[0]
        result.add((role, scope))
    return result


def test_setup_github_agent_grants_each_identity_only_its_roles(fakes: Fakes) -> None:
    result = fakes.run("setup-github-agent.sh")
    assert result.returncode == 0, result.stderr
    assert roles_of(fakes, "principal-id-tfl-agent-gh-build") == {
        ("AcrPush", "/acr-id"),
        ("Container Registry Tasks Contributor", "/acr-id"),
    }
    assert roles_of(fakes, "principal-id-tfl-agent-gh-deploy") == {
        ("AcrPush", "/acr-id"),
        ("Managed Identity Operator", "/identity/id-tfl-status-acrpull"),
        ("Container Apps Contributor", "/app-id"),
    }
    assert len(role_calls(fakes)) == 5  # nothing for any other principal


def test_setup_github_agent_trusts_only_the_production_environment(
    fakes: Fakes,
) -> None:
    result = fakes.run(
        "setup-github-agent.sh", env={"FAKE_NO_CRED": "github-production"}
    )
    assert result.returncode == 0, result.stderr
    creates = [
        c for c in fakes.calls if c.startswith("identity federated-credential create")
    ]
    assert len(creates) == 2
    for identity in ("id-tfl-agent-gh-build", "id-tfl-agent-gh-deploy"):
        (create,) = [c for c in creates if f"--identity-name {identity}" in c]
        assert f"--subject {PROD_SUBJECT}" in create
    assert not any("refs/heads/main" in c for c in fakes.calls)


def environment_body(fakes: Fakes) -> dict[str, object]:
    """The JSON the script sends to `PUT .../environments/production`."""
    return json.loads(Path(f"{fakes.log}.gh-body").read_text())


def test_setup_github_agent_restricts_the_environment_to_main(fakes: Fakes) -> None:
    result = fakes.run("setup-github-agent.sh")
    assert result.returncode == 0, result.stderr
    (put,) = [
        c for c in fakes.gh_calls if "-X PUT" in c and "environments/production" in c
    ]
    assert environment_body(fakes)["deployment_branch_policy"] == {
        "protected_branches": False,
        "custom_branch_policies": True,
    }
    posts = [
        c
        for c in fakes.gh_calls
        if "-X POST" in c and "deployment-branch-policies" in c
    ]
    assert len(posts) == 1
    assert "name=main" in posts[0]


def test_setup_github_agent_makes_the_repo_owner_the_required_reviewer(
    fakes: Fakes,
) -> None:
    # Every deploy then waits for the owner's approval in GitHub, and no admin
    # can bypass the gate.
    result = fakes.run("setup-github-agent.sh")
    assert result.returncode == 0, result.stderr
    assert "api users/Fredheda --jq .id" in fakes.gh_calls
    body = environment_body(fakes)
    assert body["reviewers"] == [{"type": "User", "id": 77542239}]
    assert body["prevent_self_review"] is False
    assert body["can_admins_bypass"] is False


def test_setup_github_agent_adds_no_second_main_policy(fakes: Fakes) -> None:
    result = fakes.run("setup-github-agent.sh", env={"FAKE_POLICY_NAMES": "main\n"})
    assert result.returncode == 0, result.stderr
    assert not any("-X POST" in c for c in fakes.gh_calls)


def test_setup_github_agent_stores_ids_as_secrets_and_leaves_the_function_secret(
    fakes: Fakes,
) -> None:
    result = fakes.run("setup-github-agent.sh")
    assert result.returncode == 0, result.stderr
    names = {c.split()[2] for c in fakes.gh_calls if c.startswith("secret set")}
    assert names == {
        "AZURE_TENANT_ID",
        "AZURE_SUBSCRIPTION_ID",
        "AZURE_BUILD_CLIENT_ID",
        "AZURE_AGENT_DEPLOY_CLIENT_ID",
    }
    assert any(
        c.startswith(
            "secret set AZURE_BUILD_CLIENT_ID --body client-id-tfl-agent-gh-build"
        )
        for c in fakes.gh_calls
    )
    assert not any("variable set" in c for c in fakes.gh_calls)


PURGE_SHA = "c" * 40


def purge_call(fakes: Fakes, prefix: str) -> str:
    (call,) = [c for c in fakes.calls if c.startswith(prefix)]
    return call


def test_purge_dry_run_locks_the_running_image_and_creates_no_task(
    fakes: Fakes,
) -> None:
    result = fakes.run("setup-acr-purge.sh", env={"FAKE_IMAGE": image(PURGE_SHA)})
    assert result.returncode == 0, result.stderr
    (lock,) = lock_calls(fakes)
    assert f"{REPO}:{PURGE_SHA}" in lock
    assert "--delete-enabled false" in lock
    assert "--dry-run" in purge_call(fakes, "acr run")
    assert not any(c.startswith("acr task") for c in fakes.calls)


def test_purge_filters_name_only_this_projects_sha_tags(fakes: Fakes) -> None:
    result = fakes.run("setup-acr-purge.sh")
    assert result.returncode == 0, result.stderr
    run_call = purge_call(fakes, "acr run")
    assert run_call.count("--filter") == 1
    assert f"--filter '{REPO}:^[0-9a-f]{{40}}$'" in run_call
    assert "--ago 30d" in run_call
    assert "--keep 10" in run_call
    assert "--untagged" in run_call
    assert "--include-locked" not in run_call


def test_purge_does_not_lock_a_latest_tag(fakes: Fakes) -> None:
    result = fakes.run("setup-acr-purge.sh", env={"FAKE_IMAGE": image("latest")})
    assert result.returncode == 0, result.stderr
    assert lock_calls(fakes) == []


def test_purge_create_makes_the_weekly_task_without_dry_run(fakes: Fakes) -> None:
    result = fakes.run("setup-acr-purge.sh", "--create", env={"FAKE_NO_TASK": "1"})
    assert result.returncode == 0, result.stderr
    create = purge_call(fakes, "acr task create")
    assert "-n purge-tfl-status-agent-images" in create
    assert "--schedule 0 3 * * Sun" in create
    assert "--dry-run" not in create
    assert "--include-locked" not in create
    assert create.count("--filter") == 1


def test_purge_create_replaces_an_existing_task(fakes: Fakes) -> None:
    result = fakes.run("setup-acr-purge.sh", "--create")
    assert result.returncode == 0, result.stderr
    verbs = [c.split()[2] for c in fakes.calls if c.startswith("acr task ")]
    assert verbs == ["show", "delete", "create"]


WORKFLOWS = REPO_ROOT / ".github" / "workflows"


def test_workflows_read_the_azure_ids_from_secrets_not_variables() -> None:
    for workflow in sorted(WORKFLOWS.glob("*.yml")):
        assert "vars.AZURE_" not in workflow.read_text(), workflow.name
    text = (WORKFLOWS / "deploy-agent.yml").read_text()
    for secret in (
        "AZURE_TENANT_ID",
        "AZURE_SUBSCRIPTION_ID",
        "AZURE_BUILD_CLIENT_ID",
        "AZURE_AGENT_DEPLOY_CLIENT_ID",
    ):
        assert f"secrets.{secret}" in text, secret


def test_deploy_agent_validates_then_builds_as_build_identity_then_rolls() -> None:
    text = (WORKFLOWS / "deploy-agent.yml").read_text()
    resolve_sha = text.index("resolve-agent-sha.sh")
    build_login = text.index("secrets.AZURE_BUILD_CLIENT_ID")
    build = text.index('./scripts/build-push.sh "$SHA"')
    deploy_login = text.index("secrets.AZURE_AGENT_DEPLOY_CLIENT_ID")
    roll = text.index('./scripts/redeploy.sh "$SHA"')
    wait = text.index("./scripts/wait-healthy.sh")
    check = text.index("./scripts/check-agent.sh")
    assert resolve_sha < build_login < build < deploy_login < roll < wait < check


def test_ci_builds_and_deploys_nothing() -> None:
    text = (WORKFLOWS / "ci.yml").read_text()
    assert "build-push.sh" not in text
    assert "AZURE_" not in text
