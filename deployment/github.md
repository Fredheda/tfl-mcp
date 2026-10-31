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
- The workflow covers Function App code only. Infra (`infra/deploy.sh`) and the MCP key stay manual; see [local.md](local.md).
- `scripts/deploy-mcp-tools.sh` still works as the laptop fallback.

## Agent: the Deploy agent workflow

The **Deploy agent** workflow builds the image for a commit on `main` and rolls `ca-tfl-status-agent` to it. It runs only when you start it (`gh workflow run deploy-agent.yml --ref main`), never on a merge, and CI never builds. The optional `sha` input takes a full 40-character commit SHA; empty means the head of `main`.

```bash
gh workflow run deploy-agent.yml --ref main                    # head of main
gh workflow run deploy-agent.yml --ref main -f sha=<full sha>  # rollback
```

Steps, in order:

1. `scripts/resolve-agent-sha.sh` checks the SHA (full lowercase, a commit, on `main`) before any Azure login.
2. Logs in as the build identity and runs `scripts/build-push.sh "$SHA"`. It builds the commit from `git archive` with `az acr build` and tags `:<sha>` and `:latest`. If `:<sha>` already exists nothing is built, so a repeat deploy or a rollback to a deployed commit needs no build.
3. Logs in as the deploy identity and runs `scripts/redeploy.sh "$SHA"`. It refuses unless the image exists, rolls the app, locks the new tag against the registry purge and unlocks the SHA tag it replaced. `latest` is never touched.
4. `scripts/wait-healthy.sh` waits until the new revision is `Provisioned`.
5. `scripts/check-agent.sh` checks that `TFL_STATUS_AGENT_PUBLIC_URL` is `https://<the app's fqdn>` (the agent card's `url` is built from it, and callers dial that address) and that a card request without a token returns `401`. The card itself needs a token; see [operations.md](operations.md).

### One-time setup

Needs rights to create identities and assign roles, and admin on the GitHub repo. Run it before the first Deploy agent run:

```bash
./scripts/setup-github-agent.sh
```

It creates two managed identities. `id-tfl-agent-gh-build` can push images (AcrPush, Container Registry Tasks Contributor on the registry). `id-tfl-agent-gh-deploy` can roll this one app (Container Apps Contributor on `ca-tfl-status-agent`, Managed Identity Operator on `id-tfl-status-acrpull`) and lock tags (AcrPush on the registry). Both trust only the `production` environment of this repo, which is restricted to `main`. The Azure IDs are stored as the repo secrets `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_BUILD_CLIENT_ID` and `AZURE_AGENT_DEPLOY_CLIENT_ID`. The Function App identity and its secret are untouched. Re-running changes nothing.

### Registry clean-up

`./scripts/setup-acr-purge.sh` locks the tag the app runs, then prints a dry run of what a purge would delete. After you have read it, `./scripts/setup-acr-purge.sh --create` makes the weekly task `purge-tfl-status-agent-images` (Sundays 03:00 UTC): SHA tags of `tfl-status-agent` older than 30 days, always keeping the newest 10. `latest`, other projects' images and locked tags are never touched.

### Limits

- Push rights cannot be scoped per repository (the registry is in legacy permission mode): both agent identities can push to any repository in `acrchatbotfredheda`.
- There is one app, so there is no mixed-version risk, and a failed update changes nothing.
- A rollback target must still be in the registry (purged after 30 days, newest 10 kept). Otherwise the button builds it again from its commit.
- `infra/deploy.sh` defaults its image tag to the local `HEAD`; after a GitHub deploy, pass the deployed SHA.
- Each first-time deploy of a commit runs one ACR build, which is billed (the price is not on Microsoft Learn). Check Cost Management after the first few deploys.
- `scripts/ship.sh` still works as the laptop fallback; see [local.md](local.md).
