#!/usr/bin/env python3
"""Find CSS declarations a change silently dropped, and say which ones still matter.

    python3 tools/css-rule-diff.py                    # origin/main vs working tree
    python3 tools/css-rule-diff.py <ref>              # <ref> vs the working tree
    python3 tools/css-rule-diff.py <ref-a> <ref-b>    # two revisions
    python3 tools/css-rule-diff.py --orphans          # classes in markup with no rule

Why this exists. Twice now a rewrite of main.css has deleted live rules in
passing. ff8ff6a ("send a QR scan to the right store") rebased the stylesheet on
a stale copy and dropped the whole .council-* block plus .legal-page h3 - 68
insertions against 307 deletions. The house-elf review caught the dark-mode half
of it; the repair, 0f9c6d8, then took *the same stale base* and restored
everything except those two. The for-councils mock rendered unstyled in
production for a week, and h3 outranked h2 on /support/ the whole time.

A line diff cannot see this. 300 deleted lines against 68 added looks alarming
but says nothing about what was lost, and a restore commit shows large numbers
on both sides while quietly reintroducing the same gap. So compare what the
browser actually resolves: every (selector, property) pair, including inside
@media, and report the pairs that exist on one side and not the other.

Then rank them, because most deletions are deliberate. A lost rule only matters
if something still asks for it, so each loss is checked against the markup:

  LIVE     every class in the selector is still emitted by a template, content
           file or script - this is the shape a regression takes
  DYNAMIC  the class is built by string concatenation ('cov-pill-' + b), so
           whether it is still emitted cannot be decided here - look yourself
  RETIRED  no class in the selector appears anywhere - almost certainly on
           purpose, the way .store-pill went with the "coming soon" pills

LIVE losses set the exit status, so this can gate a build later. It does not
today: this repo has no PR workflow, only deploy.yml on a push to main.

A LIVE loss is a lead, not a verdict. A rule can be legitimately dropped
because a broader one took over - .site-nav .nav-secondary was replaced by
.site-nav a { display: none } at a wider breakpoint - and no parser can tell
that from a regression. Read the pair before believing either.
"""

import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STYLESHEET = "src/main/resources/public/css/main.css"
# origin/main, not main: this is a shared clone whose local main goes stale, and
# a stale base invents losses that were really later additions. Comparing
# against the branch nothing rebases is the version that cannot lie.
DEFAULT_BASE = "origin/main"
# Everything that can put a class on an element: Qute layouts, page content, and
# the scripts that build the coverage table and the bin-day answer at runtime.
MARKUP_GLOBS = ("src/main/resources/**/*.html", "src/main/resources/**/*.js")

COMMENT = re.compile(r"/\*.*?\*/", re.S)
# A class token in a selector. Deliberately not anchored to the start: it has to
# find .b in "a.b" and both halves of ".cov-pill.cov-pill-ok".
SELECTOR_CLASS = re.compile(r"\.(-?[A-Za-z_][\w-]*)")
STRING_LITERAL = re.compile(r"""['"]([^'"\n]*)['"]""")
# A literal used as the left half of a concatenation: el('span', 'cov-pill-' + b)
CONCAT_PREFIX = re.compile(r"""['"]([^'"\n]*)['"]\s*\+""")


def strip_comments(css):
    return COMMENT.sub("", css)


def parse(css, context=""):
    """Flatten a stylesheet into [(selector, {property: value})].

    Selectors inside an at-rule are prefixed with it, so a rule that applies only
    under @media (max-width: 640px) never compares equal to the same selector at
    the top level - which is the whole point, since dropping the media-query copy
    is exactly the kind of loss that reads as "still there" in a line diff.

    Grouped selectors are split, so "h1, h2, h3" yields three entries and losing
    one of them from the group is visible.
    """
    css = strip_comments(css)
    rules = []
    buf = ""
    i = 0
    while i < len(css):
        ch = css[i]
        if ch == "{":
            selector = " ".join(buf.split())
            buf = ""
            body, i = _take_block(css, i)
            if selector.startswith("@") and "{" in body:
                rules.extend(parse(body, context + selector + " | "))
            else:
                declarations = _declarations(body)
                for one in filter(None, (s.strip() for s in selector.split(","))):
                    rules.append((context + " ".join(one.split()), declarations))
        elif ch == ";" and buf.lstrip().startswith("@"):
            # A statement at-rule with no block (@import, @charset). Nothing to
            # compare, so drop it rather than letting it glue onto the next
            # selector.
            buf = ""
            i += 1
        else:
            buf += ch
            i += 1
    return rules


def _take_block(css, open_index):
    """Return (body, index-after-close) for the block whose { is at open_index."""
    depth = 1
    j = open_index + 1
    while j < len(css) and depth:
        if css[j] == "{":
            depth += 1
        elif css[j] == "}":
            depth -= 1
        j += 1
    return css[open_index + 1:j - 1], j


def _declarations(body):
    out = {}
    for part in body.split(";"):
        prop, sep, value = part.partition(":")
        if sep and "{" not in part:
            out[" ".join(prop.split())] = " ".join(value.split())
    return out


def declaration_map(css):
    """{(selector, property): value}, later rules winning, as the cascade does."""
    resolved = {}
    for selector, declarations in parse(css):
        for prop, value in declarations.items():
            resolved[(selector, prop)] = value
    return resolved


def markup_text(root=HERE, globs=MARKUP_GLOBS):
    """Everything that could name a class, concatenated. One corpus, one search.

    Searching the raw text rather than parsing class attributes is deliberate: a
    class reaches an element from a Qute expression, a JS helper and a plain
    attribute, and a parser that only understands one of those reports the other
    two as dead.
    """
    import glob as globmod

    chunks = []
    for pattern in globs:
        for path in sorted(globmod.glob(os.path.join(root, pattern), recursive=True)):
            with open(path, encoding="utf-8", errors="replace") as handle:
                chunks.append(handle.read())
    return "\n".join(chunks)


def concat_prefixes(corpus):
    """The stems of runtime-built class names: 'cov-pill cov-pill-' + bucket.

    Only the last whitespace-separated token of the literal is the stem. The rest
    are complete classes sitting alongside it, and taking the whole literal would
    make the stem "cov-pill cov-pill-", which nothing starts with - so every
    bucket variant would be reported dead.
    """
    stems = set()
    for match in CONCAT_PREFIX.finditer(corpus):
        tail = match.group(1).split()[-1:] if match.group(1).strip() else []
        stems.update(t for t in tail if t and not t.endswith(("'", '"')))
    return stems


def classify(selector, corpus, prefixes):
    """LIVE / DYNAMIC / RETIRED for one selector, judged on its class tokens.

    An element-only selector (h3, body, a:hover) is always LIVE - the element
    exists whatever the markup says. A selector is only as live as its rarest
    part, so .council-mock .mock-card needs both.
    """
    classes = SELECTOR_CLASS.findall(selector)
    if not classes:
        return "LIVE"
    verdict = "LIVE"
    for name in classes:
        if re.search(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", corpus):
            continue
        if any(name.startswith(p) and p for p in prefixes):
            verdict = "DYNAMIC" if verdict == "LIVE" else verdict
        else:
            return "RETIRED"
    return verdict


def read_revision(ref, path=STYLESHEET):
    if ref is None:
        with open(os.path.join(HERE, path), encoding="utf-8") as handle:
            return handle.read()
    return subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        cwd=HERE, check=True, capture_output=True, text=True,
    ).stdout


def compare(before, after, corpus):
    """(losses, changes) - losses carry a verdict, changes carry both values."""
    prefixes = concat_prefixes(corpus)
    a, b = declaration_map(before), declaration_map(after)
    losses = [
        (selector, prop, value, classify(selector, corpus, prefixes))
        for (selector, prop), value in a.items()
        if (selector, prop) not in b
    ]
    changes = [
        (selector, prop, value, b[(selector, prop)])
        for (selector, prop), value in a.items()
        if (selector, prop) in b and b[(selector, prop)] != value
    ]
    return sorted(losses), sorted(changes)


def orphans(css, corpus):
    """Classes the markup emits that no rule styles, and rules nothing emits.

    The second half is noisy by nature - a class built at runtime looks unused -
    so anything that could be built by concatenation is left out rather than
    reported as dead.
    """
    prefixes = concat_prefixes(corpus)
    styled = set()
    for selector, _ in parse(strip_comments(css)):
        styled.update(SELECTOR_CLASS.findall(selector))

    emitted = set()
    for attr in re.finditer(r'class\s*=\s*"([^"]*)"', corpus):
        emitted.update(t for t in attr.group(1).split() if re.fullmatch(r"[\w-]+", t))
    for literal in STRING_LITERAL.finditer(corpus):
        for token in literal.group(1).split():
            if re.fullmatch(r"[a-z][\w-]*-[\w-]+", token):
                emitted.add(token)

    unstyled = sorted(c for c in emitted - styled if c in _attribute_classes(corpus))
    unused = sorted(
        c for c in styled - emitted
        if not any(c.startswith(p) and p for p in prefixes)
    )
    return unstyled, unused


def _attribute_classes(corpus):
    """Only the classes that really sit in a plain class attribute.

    String literals are scanned too when looking for what is emitted, because
    that is how the runtime-built ones appear - but a literal is far too loose a
    source to accuse a class of being unstyled, so that direction stays strict.

    An attribute value carrying anything but names and spaces is skipped whole,
    not filtered token by token. coverage.html builds markup in JS as
    'class="cov-area cov-area-' + b + '"', and picking the readable tokens out of
    that yields a class called "b".
    """
    found = set()
    for attr in re.finditer(r'class\s*=\s*"([^"]*)"', corpus):
        value = attr.group(1)
        if re.fullmatch(r"[\w\s-]*", value):
            found.update(value.split())
    return found


def _list(heading, names):
    print(heading)
    print("\n".join(f"  .{n}" for n in names) if names else "  none")
    print()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Find CSS declarations a change dropped, ranked by whether "
                    "the markup still asks for them.")
    parser.add_argument("refs", nargs="*", metavar="REF",
                        help="0 refs: origin/main vs working tree. 1: REF vs "
                             "working tree. 2: REF-A vs REF-B.")
    parser.add_argument("--orphans", action="store_true",
                        help="instead, audit classes against the current sheet")
    parser.add_argument("--path", default=STYLESHEET, help="stylesheet to read")
    args = parser.parse_args(argv)

    corpus = markup_text()

    if args.orphans:
        unstyled, unused = orphans(read_revision(None, args.path), corpus)
        _list("Classes in markup with no rule (each renders unstyled):", unstyled)
        _list("Rules no markup asks for (dead, or built somewhere I cannot see):",
              unused)
        return 0

    if len(args.refs) > 2:
        parser.error("at most two revisions")
    before_ref = args.refs[0] if args.refs else DEFAULT_BASE
    after_ref = args.refs[1] if len(args.refs) == 2 else None

    losses, changes = compare(read_revision(before_ref, args.path),
                              read_revision(after_ref, args.path), corpus)

    label_a = before_ref
    label_b = after_ref or "working tree"
    print(f"{label_a} -> {label_b}: {len(losses)} declaration(s) dropped, "
          f"{len(changes)} changed value\n")

    live = [l for l in losses if l[3] == "LIVE"]
    for verdict in ("LIVE", "DYNAMIC", "RETIRED"):
        group = [l for l in losses if l[3] == verdict]
        if not group:
            continue
        print(f"  {verdict} ({len(group)})")
        for selector, prop, value, _ in group:
            print(f"    {selector} :: {prop}: {value}")
        print()

    if changes:
        print(f"  CHANGED VALUE ({len(changes)})")
        for selector, prop, was, now in changes:
            print(f"    {selector} :: {prop}\n        was: {was}\n        now: {now}")
        print()

    if live:
        print(f"{len(live)} live declaration(s) dropped. Each is a lead, not a "
              f"verdict - a broader rule may have taken over.")
    return 1 if live else 0


if __name__ == "__main__":
    sys.exit(main())
