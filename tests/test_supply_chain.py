"""Guards the supply-chain rules of this repo.

1. A 14-day install cooldown (`poetry.toml`) beside every `pyproject.toml`,
   with no exclusion committed.
2. No `pip` or `pipx` install of a package without an exact `==` pin.
3. Every GitHub Action pinned by commit, with its release as a comment.
4. No `npx -y`.
5. One Poetry version across CI and the agent image.
6. `function_app/requirements.txt` holds exact `==` pins only (no hashes, on
   purpose), its compile script applies the 14-day window with the image's pip,
   and CI and `ci-local.sh` install pytest under the same window.

To bump Poetry, change the `poetry==` pin in `.github/workflows/ci.yml`,
`.github/workflows/security.yml` and `tfl_status_agent/Dockerfile` together.
"""

import re
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# Installed with `-r` because it pins every package with `==`, checked line by
# line below. It has no hashes on purpose: Azure's remote build installs it, and
# exact pins under the 14-day window were chosen over hashes for this file.
PINNED_REQUIREMENTS = {"function_app/requirements.txt"}
COMPILE_SCRIPT = "scripts/compile-function-requirements.sh"
DOCKERFILE = "tfl_status_agent/Dockerfile"
PIP_SOURCES = (
    COMPILE_SCRIPT,
    DOCKERFILE,
    ".github/workflows/ci.yml",
    "scripts/ci-local.sh",
)
PIP_WINDOW = "PIP_UPLOADED_PRIOR_TO=P14D"

USES_LINE = re.compile(r"^\s*(?:-\s+)?uses:\s*(?P<ref>\S+)(?P<rest>.*)$")
PINNED_REF = re.compile(r"^[\w./-]+@[0-9a-f]{40}$")
PINNED_COMMENT = re.compile(r"^\s+#\s+v\d")
INSTALL_LINE = re.compile(r"\b(?:pip|pipx) install\b(?P<args>.*)")
EXACT_PIN = re.compile(r"^[A-Za-z0-9_.\[\]-]+==[0-9][A-Za-z0-9.]*$")
NPX_YES = re.compile(r"\bnpx\s+(?:-y|--yes)\b")
POETRY_PIN = re.compile(r"\bpoetry==([0-9][0-9.]*)")
PIP_PIN = re.compile(r"\bpip==([0-9][0-9.]*)")
PINNED_LINE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*==[0-9][A-Za-z0-9.+!]*$")


def project_files(*pathspecs: str) -> list[Path]:
    """Tracked and new (not ignored) files that match the git pathspecs."""
    out = subprocess.run(
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            *pathspecs,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [REPO_ROOT / line for line in out.splitlines()]


def install_sources() -> list[Path]:
    return project_files(".github/workflows/*", "*Dockerfile", "*.sh")


def offending_lines(paths: list[Path], is_offender: Callable[[str], bool]) -> list[str]:
    found: list[str] = []
    for path in paths:
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            if is_offender(line):
                found.append(f"{path.relative_to(REPO_ROOT)}:{number}: {line.strip()}")
    return found


def is_unpinned_use(line: str) -> bool:
    match = USES_LINE.match(line)
    if match is None or match["ref"].startswith("./"):
        return False
    pinned = PINNED_REF.match(match["ref"]) and PINNED_COMMENT.match(match["rest"])
    return not pinned


def has_loose_install(line: str) -> bool:
    match = INSTALL_LINE.search(line)
    if match is None:
        return False
    tokens = re.split(r"&&|\|\||[|;\\]", match["args"])[0].split()
    if "--dry-run" in tokens:
        return False
    loose = False
    index = 0
    while index < len(tokens):
        token = tokens[index].strip("\"'")
        if token == "-r":
            index += 1
            requirements = tokens[index].strip("\"'") if index < len(tokens) else ""
            loose = loose or requirements not in PINNED_REQUIREMENTS
        elif not token.startswith("-") and not EXACT_PIN.match(token):
            loose = True
        index += 1
    return loose


def test_every_pyproject_has_the_14_day_cooldown():
    missing = []
    for pyproject in project_files("*pyproject.toml"):
        poetry_toml = pyproject.with_name("poetry.toml")
        text = poetry_toml.read_text() if poetry_toml.exists() else ""
        has_section = re.search(r"^\[solver\]$", text, re.MULTILINE)
        has_window = re.search(r"^min-release-age = 14$", text, re.MULTILINE)
        if not (has_section and has_window):
            missing.append(str(poetry_toml.relative_to(REPO_ROOT)))
    assert missing == []


def test_no_cooldown_exclusion_is_committed():
    found = offending_lines(
        project_files("*poetry.toml", "*.npmrc"),
        lambda line: "min-release-age-exclude" in line,
    )
    assert found == []


def test_pip_and_pipx_install_only_exact_versions():
    assert offending_lines(install_sources(), has_loose_install) == []


def is_loose_requirement(line: str) -> bool:
    text = line.strip()
    return bool(text) and not text.startswith("#") and not PINNED_LINE.match(text)


def test_pinned_requirements_hold_only_exact_pins():
    found: list[str] = []
    for name in sorted(PINNED_REQUIREMENTS):
        lines = (REPO_ROOT / name).read_text().splitlines()
        assert any(PINNED_LINE.match(line) for line in lines), f"{name} pins nothing"
        found += [f"{name}: {line}" for line in lines if is_loose_requirement(line)]
    assert found == []


def test_compile_script_applies_the_14_day_window():
    script = REPO_ROOT / COMPILE_SCRIPT
    assert script.exists(), f"{COMPILE_SCRIPT} is missing"
    assert PIP_WINDOW in script.read_text()


def test_compile_script_ci_and_the_image_pin_the_same_pip():
    def pins(name: str) -> set[str]:
        path = REPO_ROOT / name
        return set(PIP_PIN.findall(path.read_text())) if path.exists() else set()

    per_file = {name: pins(name) for name in PIP_SOURCES}
    assert all(len(found) == 1 for found in per_file.values()), per_file
    assert len(set().union(*per_file.values())) == 1, per_file


def is_unwindowed_pytest_install(line: str) -> bool:
    return "pytest==" in line and " install " in line and PIP_WINDOW not in line


def test_pytest_installs_apply_the_14_day_window():
    assert offending_lines(install_sources(), is_unwindowed_pytest_install) == []


def test_ci_and_the_image_install_one_poetry_version():
    versions: set[str] = set()
    for path in install_sources():
        versions.update(POETRY_PIN.findall(path.read_text()))
    assert len(versions) == 1, f"poetry pins found: {sorted(versions)}"


def test_no_npx_yes():
    found = offending_lines(
        project_files(".github/workflows/*", "*.sh"),
        lambda line: NPX_YES.search(line) is not None,
    )
    assert found == []


def test_every_action_is_pinned_by_commit_with_its_release():
    found = offending_lines(project_files(".github/workflows/*"), is_unpinned_use)
    assert found == []


@pytest.mark.parametrize(
    "line",
    [
        "      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1",
        "        uses: github/codeql-action/init@9b3254085494b55a0f7c4c2b3d2d52cc712ce370 # v4.39.1",
        "      - uses: ./.github/actions/local",
    ],
)
def test_pinned_use_is_accepted(line: str):
    assert not is_unpinned_use(line)


@pytest.mark.parametrize(
    "line",
    [
        "      - uses: actions/checkout@v7",
        "      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
        "      - uses: actions/checkout@3d3c42e # v7",
        "      - uses: actions/checkout@main # v7",
    ],
)
def test_tag_branch_short_or_uncommented_use_is_rejected(line: str):
    assert is_unpinned_use(line)


@pytest.mark.parametrize(
    "line",
    [
        "        run: pipx install poetry==2.5.1",
        "RUN pip install --no-cache-dir pip==26.2.2 \\",
        "      - run: poetry run pip install pip-audit==2.10.1 bandit==1.9.4",
        "  function_app/.venv/bin/pip install -r function_app/requirements.txt pytest==9.1.1",
        '"$py" -m pip install --ignore-installed --dry-run --report r.json "requests>=2.34.2"',
    ],
)
def test_exact_install_is_accepted(line: str):
    assert not has_loose_install(line)


@pytest.mark.parametrize(
    "line",
    [
        '        run: pipx install "poetry>=2.0,<3.0"',
        "RUN pip install --no-cache-dir poetry \\",
        "pip install -r requirements.txt",
        "  function_app/.venv/bin/pip install -r function_app/requirements.txt pytest",
    ],
)
def test_range_unpinned_or_unknown_requirements_install_is_rejected(line: str):
    assert has_loose_install(line)


@pytest.mark.parametrize(
    "line",
    ["requests==2.34.2", "azure-functions==2.3.0", "# Generated by a script", ""],
)
def test_exact_pin_comment_and_blank_lines_are_accepted(line: str):
    assert not is_loose_requirement(line)


@pytest.mark.parametrize(
    "line",
    [
        "requests>=2.34.2",
        "requests",
        "requests==2.*",
        "requests==2.34.2 --hash=sha256:abc",
        "-r other.txt",
    ],
)
def test_range_bare_wildcard_hashed_or_option_line_is_rejected(line: str):
    assert is_loose_requirement(line)


def test_windowed_pytest_install_is_accepted():
    line = "      - run: PIP_UPLOADED_PRIOR_TO=P14D function_app/.venv/bin/pip install pytest==9.1.1"
    assert not is_unwindowed_pytest_install(line)


def test_pytest_install_without_the_window_is_rejected():
    assert is_unwindowed_pytest_install(
        "function_app/.venv/bin/pip install pytest==9.1.1"
    )
