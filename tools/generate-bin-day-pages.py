#!/usr/bin/env python3
"""Generate the per-council bin day pages under content/bin-day/.

Each page is a static shell: the council, its provenance and its population are
baked in at generation time, and the collection day itself is looked up in the
browser against api.bin-space.app. Nothing about a date is written into the
HTML, so a generated page cannot go stale the way a printed calendar does - and
it works for the zone-keyed councils too, where a suburb has no single answer.

Run it again whenever coverage changes:

    python3 tools/generate-bin-day-pages.py

It rewrites content/bin-day/ and public/sitemap.xml, and commits are expected -
the output is checked in so the build has no network dependency and so a
coverage change is visible in review rather than appearing silently at deploy.
"""

import html
import json
import os
import re
import shutil
import sys
import urllib.parse
import urllib.request

API = "https://api.bin-space.app"
SITE = "https://www.bin-space.app"

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT = os.path.join(HERE, "src/main/resources/content")
BIN_DAY = os.path.join(CONTENT, "bin-day")
SITEMAP = os.path.join(HERE, "src/main/resources/public/sitemap.xml")

# How many councils to publish, largest first. A first tranche rather than all
# 400: several hundred pages of the same shape, pushed onto a young domain in
# one go, is the version of this that gets read as a doorway farm. Raise it once
# Search Console says the first ones rank.
TRANCHE = 50

# Councils to publish regardless of size. Frankston is where the marketplace
# density is being built, so it needs a page whatever its population rank.
ALWAYS = [("Frankston", "VIC")]

# A transcribed calendar closer than this to running out is left unpublished.
# Pointing a search engine at a schedule we already know needs re-reading is the
# one way these pages actively mislead someone.
MIN_TRANSCRIPTION_DAYS = 120

# The pages that existed before this generator, in the order they were listed.
STATIC_PAGES = [
    ("/", "weekly", "1.0"),
    ("/apps/", "monthly", None),
    ("/privacy/", "yearly", None),
    ("/support/", "monthly", None),
    ("/coverage/", "weekly", None),
    ("/for-councils/", "monthly", None),
]


def get(path):
    with urllib.request.urlopen(API + path, timeout=120) as r:
        return json.load(r)


def escape(text):
    """HTML-escape a registry value before it is spliced into prose.

    Every value here comes from our own coverage API today, so nothing is
    hostile. It is still the one place registry data reaches raw HTML with no
    other guard: a council named "A & B" would produce malformed markup that
    renders wrong rather than failing, and nothing downstream would notice.
    """
    return html.escape(str(text), quote=True)


def display_name(council_name):
    """The council name as prose wants it.

    Several registry names carry a parenthetical state - "Central Coast (NSW)",
    "Central Highlands (Qld)" - to tell same-named councils apart. On a page
    that already says the state in its heading and its URL, the parenthetical
    just reads as a stutter. The full name is still what goes on the wire.
    """
    return re.sub(r"\s*\([^)]*\)", "", council_name).strip()


def slug(text):
    # The parenthetical on names like "Central Coast (NSW)" only ever repeats
    # the state, which the URL already carries in its own segment.
    text = re.sub(r"\s*\([^)]*\)", "", text)
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def source_origin(source_url):
    """The bare scheme://host a schedule was read from, or None.

    Deliberately not the stored URL: several are vendor endpoints carrying query
    strings, and at least one carries the council's own API key. The host is the
    checkable part of the provenance claim; the query string is plumbing.
    """
    if not source_url:
        return None
    first = source_url.split("|")[0]
    match = re.search(r"https?://[^\s&|]+", first)
    if not match:
        return None
    parts = urllib.parse.urlsplit(match.group(0))
    if not parts.hostname:
        return None
    return parts.scheme + "://" + parts.hostname


def yaml_quote(text):
    return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"') + '"'


def provenance(council, transcription, origin):
    """The paragraph that makes each page its own page rather than a template.

    Everything in it is already published on /coverage/ - this states it in
    words on the page a resident actually lands on.
    """
    name = escape(display_name(council["council"]))
    lines = []

    if transcription:
        through = transcription["transcribedThrough"]
        lines.append(
            "<p>%s publishes its collection calendar as a document rather than a "
            "lookup anyone can query, so our schedule is a transcription of that "
            "document. It covers collections through to %s. After that we re-read "
            "whatever the council publishes next - and until we have, the lookup "
            "above says so rather than quietly projecting dates at you.</p>"
            % (name, human_date(through))
        )
    else:
        lines.append(
            "<p>%s's schedule is read from the council's own service at the moment "
            "you ask for it, not from a copy we took earlier. That is why this page "
            "has no calendar printed on it: there is nothing here to go out of date.</p>"
            % name
        )

    if origin:
        lines.append(
            '<p>The source is <a href="%s" rel="nofollow noopener">%s</a>. '
            "Every council we cover is listed the same way, with the document or "
            "service each schedule came from, on our "
            '<a href="/coverage/">coverage and data sources</a> page.</p>'
            % (escape(origin), escape(origin.split("://", 1)[1]))
        )
    else:
        lines.append(
            "<p>Every council we cover is listed with the document or service its "
            'schedule came from on our <a href="/coverage/">coverage and data '
            "sources</a> page.</p>"
        )

    population = council.get("population")
    if population:
        # Rounded on purpose. The ABS figure is an estimate to begin with, and
        # quoting it to the person invites a precision the number does not have.
        rounded = round(population, -3) if population >= 10000 else round(population, -2)
        lines.append(
            "<p>About %s people live in %s. All of them are covered here - the "
            "lookup answers for any address the council collects from, not just "
            "the main town.</p>" % (f"{rounded:,}", name)
        )

    return "\n".join(lines)


MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


def human_date(iso):
    year, month, day = iso.split("-")
    return "%d %s %s" % (int(day), MONTHS[int(month) - 1], year)


def page_html(council, transcription, origin):
    name = display_name(council["council"])
    state = council["state"]
    return """---
title: {title}
description: {description}
layout: bin-day
council: {council}
name: {name}
state: {state}
---
<h2>Where this schedule comes from</h2>
{provenance}
""".format(
        title=yaml_quote("%s bin day" % name),
        description=yaml_quote(
            "When your bins go out in %s, %s. Look up your street for this week's "
            "collection - and see exactly which council document the schedule came "
            "from." % (name, state)
        ),
        council=yaml_quote(council["council"]),
        name=yaml_quote(name),
        state=yaml_quote(state),
        provenance=provenance(council, transcription, origin),
    )


def index_html(published, covered, share):
    items = []
    for council, url in published:
        items.append(
            '    <li><a href="%s"><strong>%s</strong><span>%s</span></a></li>'
            % (url, escape(display_name(council["council"])), escape(council["state"]))
        )
    return """---
title: "Bin collection days by council"
description: "Look up your bin day by council - read from each council's own published schedule, with the source named on every page."
layout: default
---
<section class="legal-page binday-index">
    <h1>Bin collection days by council</h1>
    <p class="legal-meta">Pick your council, then look up your street. Every schedule is
       read from something the council actually published.</p>

    <p>Bin Space answers bin night for {covered} Australian councils - {share} of the
       population. These are the ones with a page of their own so far; the rest are
       answered in the <a href="/apps/">app</a>, and every council we know about,
       covered or not, is listed on our
       <a href="/coverage/">coverage and data sources</a> page.</p>

    <ul class="binday-index-list">
{items}
    </ul>

    <p class="fine-print">Bin Space is not affiliated with any council. Council data
       belongs to the councils that publish it; we read their published schedules to
       tell residents when their bins go out.</p>
</section>
""".format(items="\n".join(items), covered=covered, share=share)


def write_sitemap(published):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path, freq, priority in STATIC_PAGES:
        entry = "  <url><loc>%s%s</loc><changefreq>%s</changefreq>" % (SITE, path, freq)
        if priority:
            entry += "<priority>%s</priority>" % priority
        lines.append(entry + "</url>")
    lines.append("  <url><loc>%s/bin-day/</loc><changefreq>weekly</changefreq></url>" % SITE)
    for _, url in published:
        lines.append("  <url><loc>%s%s</loc><changefreq>monthly</changefreq></url>"
                     % (SITE, url))
    lines.append("</urlset>")
    with open(SITEMAP, "w") as f:
        f.write("\n".join(lines) + "\n")


def main():
    coverage = get("/coverage")
    transcriptions = {t["council"] + "|" + t["state"]: t
                      for t in get("/coverage/transcriptions")}
    stats = get("/coverage/stats")

    def key(c):
        return c["council"] + "|" + c["state"]

    # PARTIAL councils are excluded on purpose. We cannot say which part of one
    # we answer for, so a page promising an answer for the whole council would
    # be a promise we already know we break for some of its residents.
    covered = [c for c in coverage if c["status"] in ("OK", "STALE", "ON_DEMAND")]

    def publishable(c):
        t = transcriptions.get(key(c))
        return t is None or t["daysRemaining"] >= MIN_TRANSCRIPTION_DAYS

    candidates = [c for c in covered if publishable(c)]
    candidates.sort(key=lambda c: -(c.get("population") or 0))

    chosen = candidates[:TRANCHE]
    chosen_keys = {key(c) for c in chosen}
    for name, state in ALWAYS:
        for c in candidates:
            if c["council"] == name and c["state"] == state and key(c) not in chosen_keys:
                chosen.append(c)
                chosen_keys.add(key(c))

    if os.path.isdir(BIN_DAY):
        shutil.rmtree(BIN_DAY)

    published = []
    seen = set()
    for council in sorted(chosen, key=lambda c: (c["state"], c["council"])):
        state_slug = council["state"].lower()
        council_slug = slug(council["council"])
        path = (state_slug, council_slug)
        if path in seen:
            sys.exit("slug collision: %s %s - two councils in one state share a slug"
                     % (council["council"], council["state"]))
        seen.add(path)

        directory = os.path.join(BIN_DAY, state_slug)
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, council_slug + ".html"), "w") as f:
            f.write(page_html(council,
                              transcriptions.get(key(council)),
                              source_origin(council.get("sourceUrl"))))
        published.append((council, "/bin-day/%s/%s/" % (state_slug, council_slug)))

    share = "%.1f%%" % (stats["coveredPopulationShare"] * 100)
    with open(os.path.join(BIN_DAY, "index.html"), "w") as f:
        f.write(index_html(published, f"{stats['coveredCouncils']:,}", share))

    write_sitemap(published)
    print("%d council pages written, %d councils covered nationally"
          % (len(published), stats["coveredCouncils"]))


if __name__ == "__main__":
    main()
