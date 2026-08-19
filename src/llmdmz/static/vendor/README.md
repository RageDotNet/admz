# Vendored front-end assets

- `0build.min.css` — utility CSS bundle from https://0build.dev
- `datastar.min.js` — Datastar **v1.0.0-beta.11** (the last full HTML-attributes
  engine release; npm `@starfederation/datastar@latest`). This is the build the
  admin console actually runs on: `data-on-*`, `@get`/`@post` SSE actions,
  `datastar-merge-fragments` events, `data-indicator`.
- `datastar-1.0.2.js` — Datastar **v1.0.2**, fetched from
  https://cdn.jsdelivr.net/gh/starfederation/datastar@v1.0.2/bundles/datastar.js
  **NOT loaded by any page.** The 1.0.x line is the rewritten core-only
  signals/effects engine (exports `signal`/`effect`/`computed`/`mergePatch`).
  It contains no `data-on-*` attributes, no SSE fetching, and no
  `datastar-merge-fragments` handling — loading it instead of the beta build
  would disable the entire admin console. Kept for reference / future
  migration planning only.
