# Vendored front-end assets

- `0build.min.css` — utility CSS bundle from https://0build.dev
- `datastar-1.0.2.js` — Datastar **v1.0.2**, fetched from
  https://cdn.jsdelivr.net/gh/starfederation/datastar@v1.0.2/bundles/datastar.js
  **This is the build the admin console loads** (dashboard.html, ES module).
  The 1.0.x line renamed the SSE protocol: event `datastar-patch-elements`
  with `selector`/`mode`/`elements` keys (was `datastar-merge-fragments` with
  `mergeMode`/`fragments`), and form submits use
  `@get(url, {contentType: 'form'})` instead of `?' + $formData`.
- `datastar.min.js` — Datastar **v1.0.0-beta.11** (pre-1.0 npm release).
  Kept for reference/rollback only; no longer loaded by any page.
