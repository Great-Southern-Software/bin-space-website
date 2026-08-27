# Bin Space - marketing website

Static marketing site for [Bin Space](https://www.bin-space.app), built with
[Quarkus Roq](https://iamroq.dev/) and deployed to GitHub Pages at
`www.bin-space.app`.

## Layout

- `src/main/resources/content/` - pages (`index.html`, `apps.html`)
- `src/main/resources/templates/layouts/` - Qute layouts (`default.html`)
- `src/main/resources/public/` - static assets served as-is (CSS, images, `CNAME`)

## Bin day pages

`/bin-day/<state>/<council>/` is one static page per council, generated from the
coverage API:

```shell
python3 tools/generate-bin-day-pages.py
```

That rewrites `src/main/resources/content/bin-day/` and `public/sitemap.xml`, and
the output is committed - the build has no network dependency, and a coverage
change shows up in review rather than appearing silently at deploy. Re-run it
when coverage changes, or to widen the tranche (`TRANCHE` in the script).

Nothing about a collection date is written into the HTML. The council, its
provenance and its population are baked in; the day itself is looked up in the
browser against `api.bin-space.app`, so a page cannot fossilise a schedule.

That API allows CORS from `https://www.bin-space.app` only, so **the lookup
cannot be exercised against real data from localhost** - a locally served page
will show the form and fail the fetch. Test the widget by stubbing `window.fetch`,
or on the deployed site.

## Local dev

```shell
mvn quarkus:dev
```

Then open <http://localhost:8080>. Live reload applies content and CSS changes.

## Static build

```shell
QUARKUS_ROQ_GENERATOR_BATCH=true mvn package quarkus:run -DskipTests
```

The generated site lands in `target/roq/`.

## Deploy

Pushes to `main` trigger `.github/workflows/deploy.yml`, which uses the official
`quarkiverse/quarkus-roq` GitHub Action to build the site and publish it to
GitHub Pages.
