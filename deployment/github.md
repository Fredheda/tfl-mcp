# Deploying with GitHub Actions

## Checks on every pull request

Pull requests are opened as drafts. A draft runs only the light jobs; marking it ready (`gh pr ready`) starts the heavy ones and the AI review. A merge to `main` starts no workflow. Run `scripts/ci-local.sh` (every check `ci.yml` runs, same order) before `gh pr ready`.

`.github/workflows/ci.yml` runs on pull requests only. A `changes` job skips the other jobs for documentation-only changes (Markdown and `docs/`); a skipped job counts as a pass for a required check. `backend` (tests, ruff, pyright) runs on drafts too; `function-app-test` runs once the PR is ready.

`.github/workflows/security.yml` runs on PRs and weekly: `gitleaks` (secret scan, blocks the PR) on every push to a PR, and on ready PRs `pip-audit` (advisory on PRs, fails on the weekly run), `bandit` (HIGH severity only) and `codeql` (results in the Security tab). The weekly run scans the full history. The pip-audit step ignores two advisories that only a bump of the pinned `langchain` / `langgraph` fixes; remove the `--ignore-vuln` flags when those pins move.

`.github/workflows/claude-review.yml` posts an AI security-first review when a PR is ready (not a draft) and on every push to it. The repo owner can also request one by commenting `@claude`. It is comment-only. Besides the security-first review, every review runs a documentation check: it reports documentation that now contradicts the change, changes with no matching documentation update, and stale names, paths, counts or versions, or says "Docs: current". Its token expiry is in [expirations.md](expirations.md).

## Function App: the Deploy functions workflow

The **Deploy functions** workflow publishes the Function App's code from a commit on `main`. It runs only when you start it (Actions tab, or `gh workflow run deploy-functions.yml --ref main`), never on a merge. The optional `sha` input takes a full 40-character commit SHA; empty means the head of `main`.

```bash
gh workflow run deploy-functions.yml --ref main                    # head of main
gh workflow run deploy-functions.yml --ref main -f sha=<full sha>  # rollback
```

Before it logs in to Azure it checks that the SHA is a full lowercase SHA, is on `main`, and has `function_app/` and `tfl_status.py`. It then copies `tfl_status.py` into the package like `deploy-mcp-tools.sh` does, zips `function_app/`, and pushes the zip with `az functionapp deployment source config-zip --build-remote true`. The run ends by waiting until the Function App lists its functions and prints them in the run summary.

### One-time setup

Needs rights to create identities and assign roles, and admin on the GitHub repo:

```bash
./scripts/setup-github-deploy.sh
```

It creates the managed identity `id-tfl-mcp-gh-deploy` with Website Contributor on `func-tfl-mcp` only, a federated credential that trusts only the `production` environment of this repo, restricts that environment to `main`, and stores the Azure IDs the workflow reads as repo secrets (identifiers, not credentials, but the logs of this public repo are public and a secret's value is masked there). No credential is stored in GitHub. Re-running it changes nothing.

### Limits

- Rollback rebuilds the dependencies from the old commit's `function_app/requirements.txt`. That file uses `>=` ranges, so an old SHA can pick up newer library versions than it ran with originally.
- Flex Consumption has no deployment slots; a bad deploy is fixed by deploying the previous SHA.
- The workflow covers Function App code only. Infra (`infra/deploy.sh`), the MCP key and the agent's container app (`scripts/ship.sh`) stay manual; see [local.md](local.md).
- `scripts/deploy-mcp-tools.sh` still works as the laptop fallback.

## Agent (`tfl_status_agent/`)

No GitHub workflow deploys the agent. Use `scripts/ship.sh` as described in [local.md](local.md).
