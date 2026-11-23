# Diagrams

Three self-contained HTML/SVG diagrams for `skills`: its architecture, its main flow, and its build and deploy path. Drawn in the house style of [argus-config/docs/diagrams](https://github.com/deanjstone/argus-config/tree/main/docs/diagrams) with the [diagram-design](https://github.com/cathrynlavery/diagram-design) Claude Code plugin checks (map [argus-config#1433](https://github.com/deanjstone/argus-config/issues/1433), task [context#453](https://github.com/deanjstone/context/issues/453)). Open the `.html` file in a browser.

Each step node is a `<g id="step-<flow>-<step>">`, the deep-link contract of [ops-hub#13](https://github.com/deanjstone-hl/ops-hub/issues/13): the hub links `#/diagrams/<repo>/<path>#<step-id>`, and the page highlights the targeted step (`:target`). Anything inferred is marked `[speculation]` in the diagram or its source line.

| Diagram | Type | Flow | Step ids | Sources |
|---|---|---|---|---|
| [`architecture.html`](architecture.html) | Architecture | `skills` | `authored` `imported` `dir` `lock` `licenses` `scripts` `tests` `scrub` `consumers` | README.md, scripts/skills_lib.py, scripts/scrub-scan.sh, skills-lock.json layout, skills-config.json. |
| [`import-update-flow.html`](import-update-flow.html) | Flow | `import` | `import` `commit` `edit` `refresh` `check` `status` `merge` `clean` `conflict` `again` | README.md (How imports stay updatable), scripts/import_skill.py, refresh_lock.py, update_skill.py, check_skills.py. |
| [`build-deploy.html`](build-deploy.html) | Pipeline | `skillsrel` | `push` `check` `approve` `test` `release` `install` | .github/workflows/check.yml, release.yml, .releaserc.json, README.md (Settings and CI, Releases and the deploy branch) |

## Not drawn

How machines consume a release (argus-config#1225), and the individual skills.

## Network

The diagrams use the system font stack and make no network request. They name services and roles, never addresses or ids.

## Redrawing

The diagrams are hand-checked against their sources, not generated from them. After the sources change, redraw and rerun the plugin's checks: `self_check.py` in the skill directory and `verify-geometry.py` in the plugin's `scripts/`.
