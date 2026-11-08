---
name: playwright
description: >
  Browser automation with Playwright: fetching JS-rendered pages, scraping, testing a
  running app in a real browser, verifying Vite workers in isolation. Use when WebFetch
  returns a login wall or SPA shell. Install differs per environment: run the "check it's
  there" step first.
---

# Playwright — Browser Automation

Every script below imports from `${process.env.PLAYWRIGHT_DIR}/index.mjs`. How you get
`PLAYWRIGHT_DIR` depends on the machine — a bare `import 'playwright'` from a scratch script
fails with `ERR_MODULE_NOT_FOUND` everywhere (ESM ignores global installs and `NODE_PATH`).

## Setup per environment

Pin **1.61.1**: it uses browser revision **1228** (`chromium-1228`,
`chromium_headless_shell-1228`), which every environment has cached. An unpinned install
pulls a newer Playwright that wants a browser build that isn't cached.

| Environment | Playwright package | Browser cache |
|---|---|---|
| WSL2 | pnpm global 1.61.1 — `playwright` on PATH (`~/.local/share/pnpm/bin/playwright`) | `~/.cache/ms-playwright/` (1228, 1232, 1234, 1243) |
| homelab | **none** — not on PATH, not in `npm root -g`; use the scratch-dir fallback | `~/.cache/ms-playwright/chromium_headless_shell-1228` |
| Windows | npm global 1.61.1 in `%APPDATA%\npm\node_modules\playwright` | `%LOCALAPPDATA%\ms-playwright\` (1228) — see that env's own copy of this skill |

### Check it's there

```bash
command -v playwright && playwright --version; ls ~/.cache/ms-playwright
```

`Version 1.61.1` plus a `*-1228` directory → use the WSL2 path. No binary → scratch dir.

### WSL2: read the path from the pnpm bin shim

`npm root -g` / `pnpm root -g` don't point at it. Never `find /` for it:

```bash
export PLAYWRIGHT_DIR="$(dirname "$(sed -n 's/^# cmd-shim-target=//p' "$(command -v playwright)")")"
```

### homelab (or any machine without it): scratch-dir fallback

Install locally into a throwaway directory — never globally. Matching the cached `1228`
revision means nothing downloads:

```bash
mkdir -p /tmp/pw && npm i --prefix /tmp/pw playwright@1.61.1
export PLAYWRIGHT_DIR=/tmp/pw/node_modules/playwright
```

If `ls ~/.cache/ms-playwright` shows a different revision, install the Playwright version
that matches it rather than downloading browsers.

Inside a project, add `pnpm add -D playwright@1.61.1` instead.

## Quickstart: scrape a JS-rendered page

Write a script to the scratchpad and run it with `node`:

```js
const { chromium } = await import(`${process.env.PLAYWRIGHT_DIR}/index.mjs`);

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
await page.waitForTimeout(3000);           // let lazy-loaded content settle
const text = await page.evaluate(() => document.body.innerText);
await browser.close();
console.log(text);
```

**When to use:** try `WebFetch` first. If the result is only nav/footer boilerplate with no
content (JS-rendered SPA or login wall), switch to Playwright.

## Quickstart: verify a Vite Web Worker

Do NOT try to drive the React app to a verification route — auth guards and loading states
silently prevent renders. Instead, create a static HTML file in `public/` that imports the
worker directly:

```html
<!-- public/verify-probe.html -->
<script type="module">
  const worker = new Worker('/src/workers/db.worker.js?worker_file&type=module', { type: 'module' })
  worker.onmessage = (e) => {
    if (e.data.type === 'ready') {
      document.body.setAttribute('data-verdict', 'PASS')
    }
  }
  worker.postMessage({ type: 'init' })
</script>
<div id="out"></div>
```

Then drive it with Playwright:

```js
const { chromium } = await import(`${process.env.PLAYWRIGHT_DIR}/index.mjs`);
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
await page.goto('http://localhost:5174/verify-probe.html', { waitUntil: 'networkidle' });
await page.waitForSelector('[data-verdict]', { timeout: 20000 });
const verdict = await page.$eval('[data-verdict]', el => el.getAttribute('data-verdict'));
await browser.close();
console.log(verdict);  // PASS
```

Cleanup: delete `public/verify-*.html` after verification.

**Notes:**
- OPFS (`opfs-ahp://`) works in headless Chromium at `localhost` — it's a secure context.
- No COOP/COEP headers needed for OPFS in dedicated workers.

## Quickstart: manage a dev server's lifecycle

When the target app isn't already running, spawn it, wait for the port to open, run the
Playwright script, then kill the server — don't leave orphaned `npm run dev` processes behind.

```js
const { chromium } = await import(`${process.env.PLAYWRIGHT_DIR}/index.mjs`);
import { spawn } from 'node:child_process';
import net from 'node:net';

async function waitForPort(port, timeout = 20000) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    const ok = await new Promise((resolve) => {
      const socket = net.connect(port, 'localhost');
      socket.once('connect', () => { socket.destroy(); resolve(true); });
      socket.once('error', () => resolve(false));
    });
    if (ok) return;
    await new Promise((r) => setTimeout(r, 300));
  }
  throw new Error(`port ${port} never opened`);
}

const server = spawn('npm', ['run', 'dev'], { cwd: '/path/to/project', stdio: 'ignore' });
try {
  await waitForPort(5173);
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto('http://localhost:5173', { waitUntil: 'networkidle' });
  // ... automation logic
  await browser.close();
} finally {
  server.kill();
}
```

For multiple servers (e.g. backend + frontend), spawn each and `waitForPort` each before
navigating. Always kill in a `finally` block — a script that throws mid-run must not leave
the dev server running.

## Running scripts

Write the script to the scratchpad dir, then:

```bash
# PLAYWRIGHT_DIR exported per "Setup per environment" above
node /tmp/claude-<session>/scratchpad/playwright-script.mjs
```

Scripts must use ES module syntax (`import`) — Playwright exports are ESM.

## Browser management

On homelab, prefix these with `npx --prefix /tmp/pw`, since `playwright` isn't on PATH.

```bash
playwright install chromium          # install/update Chromium
playwright install --dry-run         # check what would be installed vs cached
playwright show-trace <trace.zip>    # open trace viewer
```

## Viewport / auth / screenshots

```js
const page = await browser.newPage({
  viewport: { width: 1280, height: 800 }
});
await page.screenshot({ path: '/tmp/screenshot.png', fullPage: true });

// Cookie auth
await page.context().addCookies([{ name: 'session', value: '...', domain: '...' }]);
```
