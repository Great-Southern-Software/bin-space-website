# Working on this site

This is the Bin Space marketing site (www.bin-space.app): a Quarkus Roq static site in the
older Roq layout, everything under `src/main/resources/`. Keep it that way. The Bin Space
APP and its services live elsewhere and are not touched from here.

- Pages are HTML with front matter in `src/main/resources/content/` (`index.html`,
  `apps.html`, `for-councils.html`, `coverage.html`, `support.html`, `privacy.html`,
  `delete-account.html`). The per-council pages under `content/bin-day/<state>/<council>.html`
  use the `bin-day` layout; everything else uses `default`.
- Layouts: `templates/layouts/default.html` and `templates/layouts/bin-day.html`. Styles:
  `public/css/main.css` (light/dark tokens on `:root`, two identical dark blocks, the
  `theme-toggle` button and script in `default.html`). Images: `public/images/`.
- `public/CNAME` holds `www.bin-space.app` and MUST stay; `site.url` in
  `application.properties` matches it. Google Analytics is switched by
  `binspace.analytics.enabled` and off in dev/test; leave that as it is.
- Links use `{site.url('/path/')}`; never hard-code the domain. Qute expressions here use
  the default `{expr}` syntax. Wrap inline `<script>` and `<style>` bodies in `{| ... |}`.
- Every page must render well at 360px wide. Tap targets at least 44px. Respect
  `prefers-reduced-motion`. Keep the light/dark parity: a colour changed in one dark block
  is changed in the other.
- Writing style: plain Australian English, no em or en dashes, no marketing filler, no
  exclamation marks, no emoji, nothing Bin Space did not say. The elf hands you the full
  list as STYLE.md when it asks for work.
- Verify before you finish: `QUARKUS_HTTP_PORT=8765 QUARKUS_ROQ_GENERATOR_BATCH=true mvn -q -B package quarkus:run`
  must succeed and `target/roq/index.html` must exist.
- There is no blog or news collection. A request for a "post" means a new section or page
  unless the owner asks for a news section to be created.
