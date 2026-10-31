# Expirations

| What | Expires | Renew |
|---|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` repo secret (used by `.github/workflows/claude-review.yml`) | about 2027-10-24 | `claude setup-token`, then `gh secret set CLAUDE_CODE_OAUTH_TOKEN`. If subscription auth is refused, switch the action input to `anthropic_api_key`. |
