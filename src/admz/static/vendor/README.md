# Vendored front-end assets

- `bootstrap-5.3.3.min.css` — Bootstrap **v5.3.3** CSS (227 KB) from
  https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css.
  All console styling uses its component/utility classes (cards, tables,
  badges, nav-tabs, flex/spacing utilities); no custom stylesheet remains
  and Bootstrap's JS bundle is not needed (all interactivity is Datastar).
  Color mode is set via `data-bs-theme` on `<html>` (auto dark mode).
  The earlier `0build-kit.min.css` and `admin.css` were deleted.

- `datastar-1.0.2.js` — Datastar **v1.0.2**, fetched from
  https://cdn.jsdelivr.net/gh/starfederation/datastar@v1.0.2/bundles/datastar.js
  **This is the build the admin console loads** (dashboard.html, ES module).
  Server-side SSE event formatting is handled by the official `datastar-py`
  SDK (pinned `>=1.0.2,<1.1`, version-matched to this bundle) via its
  framework-agnostic `ServerSentEventGenerator` — Flask has no dedicated
  helpers, so `sse_merge()` in `admin.py` wraps the generator's string
  output in a Flask `text/event-stream` response.
  The 1.0.x line renamed the SSE protocol: event `datastar-patch-elements`
  with `selector`/`mode`/`elements` keys (was `datastar-merge-fragments` with
  `mergeMode`/`fragments`), and form submits use
  `@get(url, {contentType: 'form'})` instead of `?' + $formData`.
