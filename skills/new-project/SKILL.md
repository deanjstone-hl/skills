---
name: new-project
description: >
  Bootstrap a new project from scratch: scaffold, tooling, Claude project files, colour
  scheme, initial commit. Use for "new project", "create project", "bootstrap project",
  "scaffold project", "init project", "start a new <X> project". Stops at the initial
  commit; production ops are project-init-extended.
---

# New Project Bootstrap

Creates a fully configured project under `~/repos/<name>` with the correct stack,
Claude project files, per-project colour scheme, git init, and initial commit. At the
end, optionally opens a Claude session in the new project via the launch-claude skill.

---

## Step 1 — Check CORTEX for prior art

Before scaffolding, invoke the **cortex-search** skill to search for any existing notes,
decisions, or reference material related to the project name or type. This surfaces:

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
- GitHub repo: create now?
- Bitwarden secrets needed? (If yes, invoke the **secrets-setup** skill after Step 8)

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

Add to `package.json` `scripts`:

```json
{
  "scripts": {
    "lint": "oxlint --type-aware ."
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

Run `pnpm lint` once and fix anything it reports before the initial commit. The
github-setup skill's CI template runs `pnpm lint` on every PR.

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

## Step 11 — Director-Agent governance

Create the governance files that enable the Director-Agent workflow in this project.

### `.claude/SYSTEM.md`

Write `.claude/SYSTEM.md` with permanent architectural constraints specific to this project. Always include:

- Package manager rules (pnpm only for JS/TS; never npm/yarn)
- Stack summary (what lives where, why)
- Any core invariants (e.g. RelayEvent stream rule for code-relay)
- TypeScript rules (strict, no `any`, no `.js` source files)
- The Director-Agent workflow block (copy verbatim):

```markdown
## Director-Agent Workflow

- All non-trivial work begins with a task file in `.claude/tasks/task-NNN-<name>.md`.
- Claude must append its implementation plan to the task file before writing any code.
- Code execution is blocked until the Director provides explicit approval in chat.
- Chat is the UI; the task file is the source of truth.
```

### `.claude/tasks/_task-template.md`

Create the task template at `.claude/tasks/_task-template.md`:

```markdown
# Task-XXX: [Title]

## 1. Specification (Human Authored)

- **Objective:** Concise summary of what needs to be accomplished.
- **Requirements:**
  1. [Requirement A]
  2. [Requirement B]
- **Architectural Boundary:** Constraints (e.g., "Do not introduce new dependencies").

## 2. AI Implementation Plan (AI Authored)

*To be filled by Claude before writing any code.*

### Scope of changes

**Files to create:**
- `path/to/file` — purpose

**Files to modify:**
- `path/to/file` — what changes and why

**Files to delete:**
- `path/to/file` — reason

**Files NOT touched:**
- [list anything explicitly out of scope]

### Step-by-step execution plan

**Step 1 — [Name]**
Description of what happens and why.

### Risks / tradeoffs

- [Any non-obvious side effects or decisions made]

## 3. Human Approval Sign-off

- **Status:** Pending
- **Director Review Notes:** —

## 4. Verification Checklist (AI Completed)

- [ ] [Specific verifiable outcome]
- [ ] TypeScript compiles with no errors
```

---

## Step 13 — GitHub repo (if requested)

```bash
cd ~/repos/<name>
gh repo create <name> --private --source . --remote origin
```

Adjust `--private`/`--public` per user preference. Then invoke the **github-setup** skill to add CI workflow and PR/issue templates.

---

## Step 14 — Git init and initial commit

```bash
cd ~/repos/<name>
git init
git add .
git commit -m "chore: initial scaffold"
```

If a GitHub remote was created in Step 13, push immediately:

```bash
git push -u origin main
```

---

## Step 15 — Project registration is automatic

Nothing to do here. The `context/projects.md` registry is gone — project discovery now
happens via the SessionStart hook (`~/.argus/hooks/projects-registry.sh`), which scans
`~/repos/` fresh every session. A new project directory with a `CLAUDE.md` is picked up
automatically on the next session start.

---

## Step 16 — Open a session (optional)

Ask the user: "Want me to open a Claude session in the new project?"

If yes, invoke the **launch-claude** skill with the new project name.

---

## Checklist summary

- [ ] CORTEX searched for prior art
- [ ] Directory created and deps installed
- [ ] oxlint wired (`lint` script, `oxlint.config.ts`, `pnpm lint` clean)
- [ ] Tailwind CSS wired (web only)
- [ ] Supabase client added (if requested)
- [ ] Deploy config added (if requested)
- [ ] `.gitignore` created
- [ ] `.env.example` created
- [ ] `.claude/project.json` with `wtTabColor`
- [ ] `.claude/settings.json` with `theme: custom:<name>`
- [ ] `~/.claude/themes/<name>.json` created (with `promptBorder`/`autoAccept`/`planMode`/`warning`)
- [ ] Colour map memory updated
- [ ] `.claude/SYSTEM.md` created with architectural constraints + Director-Agent block
- [ ] `.claude/tasks/_task-template.md` created
- [ ] Git init + initial commit
- [ ] GitHub repo created + github-setup invoked (if requested)
- [ ] Session opened (if requested)
