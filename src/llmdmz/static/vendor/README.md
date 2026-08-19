# Vendored front-end assets

- `0build-kit.min.css` ? 0build **v0.6.0** kit CSS (642 KB), the real upstream
  stylesheet from https://cdn.jsdelivr.net/gh/0builddotdev/0build@0.6.0/dist/css/kit.min.css.
  All console styling uses its `z-*` component classes; project-specific bits
  (mono, diff coloring, pager gap) live in `static/admin.css`. Pages also carry
  0build's theme-init script (`dark` mode / `z-layout-small`) per its docs.
  The old hand-authored `0build.min.css` was deleted.

- `datastar-1.0.2.js` — Datastar **v1.0.2**, fetched from
  https://cdn.jsdelivr.net/gh/starfederation/datastar@v1.0.2/bundles/datastar.js
  **This is the build the admin console loads** (dashboard.html, ES module).
  The 1.0.x line renamed the SSE protocol: event `datastar-patch-elements`
  with `selector`/`mode`/`elements` keys (was `datastar-merge-fragments` with
  `mergeMode`/`fragments`), and form submits use
  `@get(url, {contentType: 'form'})` instead of `?' + $formData`.
- `datastar.min.js` — Datastar **v1.0.0-beta.11** (pre-1.0 npm release).
  Kept for reference/rollback only; no longer loaded by any page.
