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

The generator's own logic - slugs, source-origin stripping, escaping - is
covered by `python3 -m unittest discover -s tools`.

Nothing about a collection date is written into the HTML. The council, its
provenance and its population are baked in; the day itself is looked up in the
browser against `api.bin-space.app`, so a page cannot fossilise a schedule.

That API allows CORS from `https://www.bin-space.app` only, so **the lookup
cannot be exercised against real data from localhost** - a locally served page
will show the form and fail the fetch. Test the widget by stubbing `window.fetch`,
or on the deployed site.

## Checking a stylesheet change

`main.css` is one sheet for the whole site, so a change to it touches every
page and a line diff is a poor guide to what actually moved:

```shell
python3 tools/css-rule-diff.py                 # origin/main vs the working tree
python3 tools/css-rule-diff.py <ref-a> <ref-b> # any two revisions
python3 tools/css-rule-diff.py --orphans       # classes with no rule, rules with no class
```

It resolves both versions down to `(selector, property)` pairs - including
inside `@media`, which a bare selector comparison would flatten - and reports
what one side has and the other does not, plus any value that changed under a
selector that survived. Each loss is ranked by whether the markup still emits
the class: `LIVE` is the shape a regression takes, `RETIRED` is a deliberate
removal, `DYNAMIC` is a class built by concatenation that it cannot decide.
It exits non-zero when anything `LIVE` was dropped.

Run it on any commit that rewrites rather than edits the stylesheet. Two have
now deleted live rules in passing - `ff8ff6a` rebased the sheet on a stale copy
and lost the whole `.council-*` block along with `.legal-page h3`, and the
repair for it, `0f9c6d8`, took the same stale base and restored everything
except those two. Both are visible in one run.

A `LIVE` loss is a lead, not a verdict: a broader rule may have taken over, the
way `.site-nav a { display: none }` superseded `.site-nav .nav-secondary`. Read
the pair before believing it either way.

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
