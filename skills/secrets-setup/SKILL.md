---
name: secrets-setup
description: >
  Scaffold Bitwarden vault items and .env templates for a project. Use for "set up
  secrets", "bootstrap Bitwarden", "create env", "add secrets", "/secrets-setup", or from
  new-repo when secrets are requested.
---

# Secrets Setup

Scaffolds the secret management layer for a project: infers what secrets are needed,
generates Bitwarden item names following the argus convention, writes a `.env.local`
template, and optionally creates a `deploy.sh` fragment for pulling secrets at deploy time.

---

## Step 1 — Identify the project

Default to the current working directory. If the user named a different project, use that.

```bash
basename $(pwd)
```

Derive `$PROJECT_NAME` = the directory name (e.g. `budget`, `atto1`, `mcp-memory`).

---

## Step 2 — Infer required secrets

Read `package.json`, existing `.env.example`, and `src/` for environment variable
references to infer what secrets the project needs:

```bash
grep -r "process\.env\.\|import\.meta\.env\.\|VITE_" \
  src/ .env.example 2>/dev/null | \
  grep -oE '(process\.env\.|import\.meta\.env\.|VITE_)[A-Z_]+' | \
  sort -u
```

Also check for common integration patterns:
- `@supabase/supabase-js` → needs `SUPABASE_URL`, `SUPABASE_ANON_KEY`, optionally `SUPABASE_SERVICE_ROLE_KEY`
- `telegraf` or `telegram` → needs `TELEGRAM_BOT_TOKEN`
- `wrangler` / Cloudflare → needs `CF_API_TOKEN`, `CF_ACCOUNT_ID`
- `resend` → needs `RESEND_API_KEY`

---

## Step 3 — Ask to confirm secrets list

If any secrets were inferred, confirm with the user:

```
AskUserQuestion: "Which secrets does this project need?"
Options: [list inferred ones] + "Other / custom"
```

Allow multi-select. If no secrets were inferred, ask the user to name them.

---

## Step 4 — Generate Bitwarden item names

Bitwarden item naming convention: `<project-name>-<service>-<key-type>`

Examples:
- `SUPABASE_URL` for project `budget` → `budget-supabase-url`
- `TELEGRAM_BOT_TOKEN` for project `atto1` → `atto1-telegram-bot-token`
- `CF_API_TOKEN` for project `mcp-memory` → `mcp-memory-cloudflare-api-token`
- `RESEND_API_KEY` for project `myargus` → `myargus-resend-api-key`

Generate the full list and display it so the user can create the items in Bitwarden.

---

## Step 5 — Check Bitwarden session

```bash
ls ~/.bw_session 2>/dev/null && source ~/.bw_session && \
  bw get item "test" --session "$BW_SESSION" --nointeraction &>/dev/null 2>&1 && \
  echo "valid" || echo "unavailable"
```

If Bitwarden session is **valid**, check which of the generated item names already exist:

```bash
bw list items --session "$BW_SESSION" --nointeraction 2>/dev/null | \
  jq -r '.[].name' | grep "^$PROJECT_NAME-"
```

Report which items are already present vs. which need to be created.

If session is **unavailable**, skip existence check and tell the user to create the items
manually using the generated names from Step 4.

---

## Step 6 — Write .env.local template

Create `.env.local` (or update if it exists) with placeholder values for all secrets:

```bash
# .env.local — gitignored, never commit
# Populate with real values from Bitwarden before running locally
```

For each secret, one line:
```
SUPABASE_URL=             # bw item: budget-supabase-url
SUPABASE_ANON_KEY=        # bw item: budget-supabase-anon-key
```

Also ensure `.env.example` has the same vars with empty values (no comments, no secrets):

```
SUPABASE_URL=
SUPABASE_ANON_KEY=
```

Ensure `.gitignore` contains `.env.local` and `.env`.

---

## Step 7 — deploy.sh fragment (optional)

Ask: "Generate a deploy.sh fragment for pulling secrets from Bitwarden?"

If yes, write a `scripts/pull-secrets.sh` (or append to existing `deploy.sh`):

```bash
#!/usr/bin/env bash
set -euo pipefail

# Pull secrets from Bitwarden and write .env.local
source ~/.bw_session 2>/dev/null || {
  echo "No BW session. Run bw-unlock first."
  exit 1
}

bw get password "<project-name>-supabase-url" \
  --session "$BW_SESSION" --nointeraction > /tmp/supabase_url

# Write .env.local
cat > .env.local <<EOF
SUPABASE_URL=$(cat /tmp/supabase_url)
EOF

rm -f /tmp/supabase_url
echo ".env.local written"
```

Adapt the template to match the actual secrets for this project.

---

## Step 8 — Report

Summary:
- Project: `$PROJECT_NAME`
- Secrets identified: `N`
- Bitwarden item names to create: list
- `.env.local` template: written / updated
- `.env.example`: updated
- `scripts/pull-secrets.sh`: written / skipped

Remind the user: "Create the Bitwarden items, then populate `.env.local` with real values
before running the project."
