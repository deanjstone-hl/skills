---
name: new-repo
description: >
  Create a new repo end to end: scaffold (or split out of a monorepo), tooling, Claude project
  files, colour scheme, initial commit, then the GitHub side (CI, PR template, labels, trunk
  readiness) and the production ops (secrets, Supabase, promotion-based deploy and release).
  Use for "new project", "new repo", "create project", "bootstrap project", "scaffold
  project", "start a new <X> project", "set up github for <project>", "add CI to <project>",
  "wire github", "set up project fully", "production setup", "wire Supabase".
---

# New Repo

Phases, run in order; stop after the phase the user asked for.

| Phase | Does | Where |
|---|---|---|
| 1. Scaffold | Directory under `~/repos/<name>`, stack, tooling, Claude project files, initial commit | Steps below |
| 2. GitHub | Repo, CI that runs the local check, PR template, labels, trunk readiness | `references/github.md` |
| 3. Ops | Secrets, Supabase, deploy script, `deploy`-branch workflows, release workflow | `references/ops.md` |

"Add CI to <project>" or "wire github" on an existing repo starts at phase 2; "set up
project fully" on a scaffolded repo starts at phase 3. Secrets are their own skill
(`secrets-setup`), called from phase 3 or on request.

## Phase 1: Scaffold

Creates a project under `~/repos/<name>` with the stack, Claude project files, per-project
colour scheme, git init and initial commit. A product-family repo split out of the argus
monorepo follows the same steps, with the code moved in (history kept with
`git filter-repo` if the owner wants it) instead of generated.

---

## Step 1 — Check CORTEX for prior art

Before scaffolding, run the **vault-search** skill on `cortex` for the project name or type.
It surfaces:

- Previous attempts or abandoned versions of the same project
- Architecture decisions or constraints already recorded
- Related tools or patterns the user has evaluated

If relevant results are found, summarise them briefly and confirm with the user before
proceeding. If nothing relevant is found, continue without comment.

---

## Step 2 — Gather requirements

If the user hasn't specified, ask with `AskUserQuestion`:

**Required:**
- Project name (becomes the directory name, e.g. `my-app`)
- Project type (see types below)

**Optional (ask only if not obvious from context):**
- Supabase integration needed?
- Deploy target: Vercel / Cloudflare Workers / none
- GitHub repo: create now? (phase 2)
- Bitwarden secrets needed? (If yes, invoke the **secrets-setup** skill after Step 12)

### Project types

| Type | Template | What gets scaffolded |
|---|---|---|
| `web-react` | `react-ts` | Vite + React + TypeScript + Tailwind v4 |
| `web-vanilla` | `vanilla-ts` | Vite + Vanilla TypeScript + Tailwind v4 |
| `node-cli` | *(manual)* | TypeScript + tsx + bin entry |
| `node-lib` | *(manual)* | TypeScript library with tsup build |

Default to `web-react` if the user says "app" or "web app" without more detail.

---

## Step 3 — Scaffold the project

### Web projects (react or vanilla)

```bash
cd ~/repos
pnpm create vite <name> --template <template>
cd <name>
pnpm install
```

### Node CLI project

```bash
mkdir -p ~/repos/<name>/src
cd ~/repos/<name>
pnpm init
pnpm add -D typescript tsx @types/node
```

Create `tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "outDir": "dist",
    "rootDir": "src",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true
  },
  "include": ["src"]
}
```

Add to `package.json`:

```json
{
  "type": "module",
  "main": "dist/index.js",
  "bin": { "<name>": "dist/index.js" },
  "scripts": {
    "dev": "tsx watch src/index.ts",
    "build": "tsc",
    "start": "node dist/index.js"
  }
}
```

### Node library

```bash
mkdir -p ~/repos/<name>/src
cd ~/repos/<name>
pnpm init
pnpm add -D typescript tsup @types/node
```

`tsconfig.json` same as CLI above. `package.json` scripts:

```json
{
  "type": "module",
  "main": "dist/index.js",
  "types": "dist/index.d.ts",
  "exports": { ".": { "import": "./dist/index.js", "types": "./dist/index.d.ts" } },
  "scripts": {
    "dev": "tsup src/index.ts --watch",
    "build": "tsup src/index.ts --dts",
    "prepublishOnly": "pnpm build"
  }
}
```

### Lint (all project types)

Lint with oxlint, type-aware, the same setup as myargus. Never scaffold ESLint or Biome.

```bash
pnpm add -D oxlint oxlint-tsgolint
```

Add to `package.json` `scripts` (`check` is the one command workers run before every push and
CI runs on every push to `main`; drop `pnpm test` until a suite exists):

```json
{
  "scripts": {
    "lint": "oxlint --type-aware .",
    "check": "pnpm lint && pnpm build && pnpm test"
  }
}
```

Create `oxlint.config.ts`:

```ts
import { defineConfig } from "oxlint";

export default defineConfig({
  ignorePatterns: ["**/node_modules/**", "**/dist/**"],
  rules: {
    "typescript/no-floating-promises": "error",
  },
});
```

Run `pnpm check` once and fix anything it reports before the initial commit. The CI
workflow in `references/github.md` runs it.

---

## Step 4 — Add Tailwind CSS (web projects only)

Tailwind v4 uses the Vite plugin — no config file needed.

```bash
pnpm add tailwindcss @tailwindcss/vite
```

Edit `vite.config.ts` to add the plugin:

```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'       // omit for vanilla
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [
    react(),            // omit for vanilla
    tailwindcss(),
  ],
})
```

Replace the contents of `src/index.css` (or `src/style.css`) with:

```css
@import "tailwindcss";
```

Remove the Vite default CSS from `src/App.tsx` / `src/main.ts` if present.

---

## Step 5 — Supabase client (if requested)

```bash
pnpm add @supabase/supabase-js
```

Create `src/lib/supabase.ts`:

```ts
import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error('Missing Supabase env vars')
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey)
```

Add to `.env.example` (and `.env.local` with real values if available):

```
VITE_SUPABASE_URL=https://<project>.supabase.co
VITE_SUPABASE_ANON_KEY=<anon-key>
```

For Node projects, use `process.env` instead of `import.meta.env` and name vars without `VITE_`.

---

## Step 6 — Deploy config

### Vercel

Create `vercel.json` only if non-SPA routing is needed. For standard SPAs, Vercel
auto-detects Vite — no config file required. Just confirm with the user.

### Cloudflare Workers

```bash
pnpm add -D wrangler
```

Create `wrangler.toml`:

```toml
name = "<name>"
main = "src/worker.ts"
compatibility_date = "2025-01-01"
```

---

## Step 7 — .gitignore

Create `.gitignore`:

```gitignore
# Dependencies
node_modules/

# Build output
dist/
.output/

# Environment — never commit secrets
.env
.env.local
.env.*.local

# Editor and OS
.DS_Store
*.log
.vscode/settings.json

# TypeScript build info
*.tsbuildinfo

# Wrangler (Cloudflare)
.wrangler/
```

---

## Step 8 — .env.example

Create `.env.example` with all expected vars, values as placeholders. This is always
committed. `.env.local` / `.env` are gitignored.

---

## Step 9 — Project docs

Do not create `docs/TODO.md` or `docs/TODO-archive.md` — GitHub issues are the canonical
backlog for every project (global CLAUDE.md `## TODO Convention`). Deferred work gets filed
as a GitHub issue via the `/todo` skill once the repo exists, not tracked in a project-local
file.

---

## Step 10 — Claude project files

Colour is a **project-level** concern. Set it once at the project root.
Sub-packages, apps, tools, and any nested workspace members must **not** get their
own `.claude/project.json` or `.claude/settings.json` — they inherit from the root.

### Pick a tab colour

Check `~/CONTEXT/MEMORY/fact_per_project_colours.md` for the existing colour map
and pick an unused colour from this palette:

| Name | Hex |
|---|---|
| amber | `#F59E0B` |
| sky | `#38BDF8` |
| green | `#22C55E` |
| red | `#EF4444` |
| violet | `#8B5CF6` |
| cyan | `#06B6D4` |
| slate | `#64748B` |
| lime | `#84CC16` |
| pink | `#EC4899` |
| teal | `#14B8A6` |
| indigo | `#6366F1` |
| rose | `#F43F5E` |
| orange | `#F97316` |
| purple | `#A855F7` |
| yellow | `#EAB308` |
| emerald | `#10B981` |

If all are taken, pick the closest unused shade or ask the user.

### Create `<project-root>/.claude/project.json`

```json
{ "wtTabColor": "<hex>" }
```

### Create `<project-root>/.claude/settings.json`

```json
{
  "theme": "custom:<name>"
}
```

### Create the theme file

Write `~/.claude/themes/<name>.json`:

```json
{
  "name": "<name>",
  "base": "dark-ansi",
  "overrides": {
    "promptBorder": "<hex>",
    "autoAccept": "<hex>",
    "planMode": "<hex>",
    "warning": "<hex>"
  }
}
```

Use the same hex as `wtTabColor`.

> **Monorepo / workspace rule:** if the project has sub-packages (e.g. `packages/`,
> `apps/`, `tools/`), do **not** create `.claude/` files inside them. Claude Code
> walks up to the nearest `.claude/` directory, so sub-packages automatically inherit
> the root colour and theme.

### Update the colour memory

Record the new project + colour by calling `memory_remember` with the key
`fact_per_project_colours` — **do not edit the mirror file by hand.** A direct
edit bypasses frontmatter validation, `source:` provenance tagging and the
theme-index write, which is why `memory_remember` is the sole sanctioned write path
([context#159](https://github.com/deanjstone/context/issues/159)). It also leaves the
store's copy of the colour map stale, so the next spawn may read it and reuse a colour.

### Create `CLAUDE.md` (if the project warrants it)

Only create a project-level `CLAUDE.md` if there is non-obvious project-specific
context to capture (custom scripts, non-standard conventions, external dependencies).
For simple projects, skip it — the global CLAUDE.md is sufficient.

---

## Step 11 — Architectural rules

Write `.claude/SYSTEM.md` with the permanent architectural constraints specific to this
project. Always include:

- Package manager rules (pnpm only for JS/TS; never npm/yarn)
- Stack summary (what lives where, why)
- Any core invariants the code must keep
- TypeScript rules (strict, no `any`, no `.js` source files)

Do not create `.claude/tasks/` or a task template: task files are retired, and work is
tracked as GitHub issues (the `todo` and `wayfinder` skills).

---

## Step 12 — Git init and initial commit

```bash
cd ~/repos/<name>
git init
git add .
git commit -m "chore: initial scaffold"
```

---

## Step 13 — Project registration is automatic

Nothing to do. The `context/projects.md` registry is gone: the SessionStart hook
(`~/.argus/hooks/projects-registry.sh`) scans `~/repos/` fresh every session, so a new
directory with a `CLAUDE.md` is picked up on the next session start.

---

## Step 14 — Continue or open a session

If the user asked for GitHub, secrets or deploy, continue with phase 2 or 3 now.
Otherwise ask: "Want me to open a Claude session in the new project?" If yes, invoke the
**t3-thread** skill with the new project name.

---

## Checklist

Scaffold:

- [ ] CORTEX searched for prior art
- [ ] Directory created and deps installed
- [ ] oxlint wired (`lint` and `check` scripts, `oxlint.config.ts`, `pnpm check` clean)
- [ ] Tailwind CSS wired (web only)
- [ ] Supabase client added (if requested)
- [ ] Deploy config added (if requested)
- [ ] `.gitignore` and `.env.example` created
- [ ] `.claude/project.json` with `wtTabColor`, `.claude/settings.json` with `theme: custom:<name>`
- [ ] `~/.claude/themes/<name>.json` created (with `promptBorder`/`autoAccept`/`planMode`/`warning`)
- [ ] Colour map memory updated through `memory_remember`
- [ ] `.claude/SYSTEM.md` with architectural constraints (no `.claude/tasks/`; work is GitHub issues)
- [ ] Git init and initial commit

New-repo (see the references):

- [ ] README covers setup, commands, config and env, deploy and public behaviour (updated in the same push as any change to them)
- [ ] CI runs the local check on every push to `main`; `scripts/trunk-readiness.sh` passes, output kept for the Resolution
- [ ] Repo added to the deploy-repo list in the instruction files, and to the ops-hub, if it deploys
- [ ] `release.yml` on push to `deploy` with `Test before release (<what it ran>)` then `Release`
- [ ] Secrets set up through `secrets-setup` (separate skill, if needed)
