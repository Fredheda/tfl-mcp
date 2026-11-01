#!/usr/bin/env bash
# One-time (idempotent) setup so the `Deploy functions` workflow can publish to
# the Function App with no stored secrets, using OpenID Connect (workload
# identity federation).
#
# What it does:
#   1. Creates the user-assigned managed identity id-tfl-mcp-gh-deploy in
#      rg-chatbot.
#   2. Grants it Website Contributor on the Function App func-tfl-mcp, and
#      nothing else.
#   3. Adds one federated credential: only the job that runs in the
#      `production` environment of this repo can use the identity.
#   4. Creates the `production` GitHub environment, restricted to jobs running
#      on the main branch (a branch author cannot edit their way around it)
#      and gated by the repo owner as required reviewer (every deploy waits
#      for his approval in GitHub), and stores the Azure IDs the workflow
#      reads as repo SECRETS:
#      AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID, AZURE_DEPLOY_CLIENT_ID. They
#      are identifiers, not credentials, but the run logs of a public repo are
#      public and GitHub masks a secret's value there.
#
# Needs the signed-in user to be able to create identities, assign roles, and
# administer the GitHub repo. Auth is the live `az login` and `gh auth`
# sessions; nothing secret is written anywhere. Federated credentials do not
# expire.
#
# Usage: ./scripts/setup-github-deploy.sh
set -euo pipefail

GH_REPO=Fredheda/tfl-mcp
RG=rg-chatbot
LOCATION=westeurope
IDENTITY=id-tfl-mcp-gh-deploy
FUNCTION_APP=func-tfl-mcp
ISSUER=https://token.actions.githubusercontent.com

TENANT_ID=$(az account show --query tenantId -o tsv)
SUBSCRIPTION_ID=$(az account show --query id -o tsv)
echo "Subscription $SUBSCRIPTION_ID, repo $GH_REPO"

if az identity show -g "$RG" -n "$IDENTITY" -o none 2>/dev/null; then
  echo "identity $IDENTITY: exists"
else
  az identity create -g "$RG" -n "$IDENTITY" -l "$LOCATION" -o none
  echo "identity $IDENTITY: created"
fi
PRINCIPAL=$(az identity show -g "$RG" -n "$IDENTITY" --query principalId -o tsv)
CLIENT=$(az identity show -g "$RG" -n "$IDENTITY" --query clientId -o tsv)

# Role assignment by object id + principal type, so a just-created identity
# does not have to wait for Entra replication before the lookup succeeds.
APP_ID=$(az functionapp show -g "$RG" -n "$FUNCTION_APP" --query id -o tsv)
az role assignment create --assignee-object-id "$PRINCIPAL" \
  --assignee-principal-type ServicePrincipal \
  --role "Website Contributor" --scope "$APP_ID" -o none
echo "role 'Website Contributor' on $FUNCTION_APP: ensured"

CRED=github-production
SUBJECT="repo:$GH_REPO:environment:production"
if az identity federated-credential show -g "$RG" --identity-name "$IDENTITY" \
  --name "$CRED" -o none 2>/dev/null; then
  echo "federated credential $IDENTITY/$CRED: exists"
else
  az identity federated-credential create -g "$RG" --identity-name "$IDENTITY" \
    --name "$CRED" --issuer "$ISSUER" --subject "$SUBJECT" \
    --audiences api://AzureADTokenExchange -o none
  echo "federated credential $IDENTITY/$CRED: created ($SUBJECT)"
fi

# The identity trusts any job that runs in the `production` environment,
# whatever branch it runs on, and the `main`-only check inside the workflow is
# in a file any branch author can edit. So the environment itself only admits
# jobs from main: GitHub enforces this outside the workflow file. The repo
# owner is its required reviewer, so every deploy waits for his approval in
# GitHub (the run shows `waiting`) and no admin can bypass that. Required
# reviewers need a public repo on the Free plan.
OWNER_ID=$(gh api "users/${GH_REPO%%/*}" --jq .id)
gh api -X PUT "repos/$GH_REPO/environments/production" --input - \
  --jq '"environment " + .name + ": ensured"' <<EOF
{
  "deployment_branch_policy": {"protected_branches": false, "custom_branch_policies": true},
  "reviewers": [{"type": "User", "id": $OWNER_ID}],
  "prevent_self_review": false,
  "can_admins_bypass": false
}
EOF
policies=$(gh api "repos/$GH_REPO/environments/production/deployment-branch-policies" \
  --jq '.branch_policies[].name')
if grep -qx main <<<"$policies"; then
  echo "environment production: branch policy main exists"
else
  gh api -X POST "repos/$GH_REPO/environments/production/deployment-branch-policies" \
    -f name=main -f type=branch --silent
  echo "environment production: branch policy main created"
fi
while IFS= read -r other; do
  { [ -z "$other" ] || [ "$other" = main ]; } && continue
  echo "WARNING: environment production also admits branch '$other'; remove it in Settings > Environments unless intended." >&2
done <<<"$policies"

gh secret set AZURE_TENANT_ID --body "$TENANT_ID" -R "$GH_REPO"
gh secret set AZURE_SUBSCRIPTION_ID --body "$SUBSCRIPTION_ID" -R "$GH_REPO"
gh secret set AZURE_DEPLOY_CLIENT_ID --body "$CLIENT" -R "$GH_REPO"
echo "repo secrets: set"
echo "Done. Re-running changes nothing."
