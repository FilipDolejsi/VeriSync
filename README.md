# VeriSync

## GitHub webhook setup

GitHub repository webhooks must point to a **publicly reachable** URL.

Set one of these environment variables before watching repositories:

- `WEBHOOK_URL=https://<public-domain>/webhook/github`
- `PUBLIC_BASE_URL=https://<public-domain>` (the app will derive `/webhook/github`)

`localhost`, `127.0.0.1`, and private IPs are rejected by GitHub and will fail with 422.