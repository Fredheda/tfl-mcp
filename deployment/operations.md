# Operations

## Function App: verify

```bash
poetry run python scripts/verify_deployed_mcp.py victoria
```

This confirms a live TfL line-status call round-trips through the deployed Function App, not just that it shows "Running". It calls `get_tfl_status` and the three journey tools once each (`find_station`, `get_arrivals`, `plan_journey`), so a tool missing from the deployed Function App shows up as a `StopIteration` here. It needs `FUNCTION_APP_URL` and `FUNCTION_MCP_KEY` in `.env`.

After adding or changing tools, run `scripts/deploy-mcp-tools.sh` (or the Deploy functions workflow) first, then `scripts/ship.sh` for the agent: the agent fetches tool schemas live at startup, and its system prompt is baked into the image.

## Agent: approve a caller

No caller can obtain a token for the agent until explicitly approved. Entra's `appRoleAssignmentRequired` is set on the app, so an unapproved principal cannot even get a token issued, let alone pass the Container Apps auth gate.

```bash
./scripts/approve-caller.sh <principal-object-id> [display-name]
```

For a service (the common case: one deployed agent or app calling this one), that is the caller's own service-principal object ID, approved for client-credentials (app-only) tokens. This is the authentication model any new consumer of the agent should use.

## Agent: verify a live deployment

```bash
curl -i https://<tfl-status-agent-fqdn>/.well-known/agent-card.json
```

Expect `401` unauthenticated. With a valid, approved caller's token in the `Authorization: Bearer` header, expect `200` with the agent card.

Also try these questions through an approved caller:

- "fastest way from Waterloo to King's Cross right now"
- "next Victoria line trains at Oxford Circus"
- "Waterloo to King's Cross, arriving by 9am tomorrow" (this one exercises `get_current_time` and the image's `tzdata`)

## Rollback

Function App: run the Deploy functions workflow with an older SHA ([github.md](github.md)). Agent: run the Deploy agent workflow with an older SHA ([github.md](github.md)), or `./scripts/redeploy.sh <older-git-sha>` from a laptop ([local.md](local.md)).
