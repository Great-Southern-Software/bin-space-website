"""Unit tests for the CSS rule differ.

    python3 -m unittest discover -s tools

Everything here is hermetic - inline stylesheets and inline markup, no git and
no repository state - so the tests still mean something after the history they
were written about has scrolled away.

Four things carry the logic and fail quietly when they are wrong. The at-rule
prefix decides whether losing a media-query override is visible at all. The
liveness verdict decides whether a real regression is buried under deliberate
deletions. The concatenation stems decide whether every runtime-built class is
falsely reported dead. And the class-attribute scan decides whether markup built
inside a JS string invents classes that never existed.
"""

import unittest

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

spec = spec_from_file_location("cssdiff", Path(__file__).parent / "css-rule-diff.py")
cssdiff = module_from_spec(spec)
spec.loader.exec_module(cssdiff)


class ParseTest(unittest.TestCase):

    def test_a_media_query_copy_is_not_the_same_rule_as_the_bare_one(self):
        # The whole point. .council-mock exists at both levels with different
        # declarations, and dropping the media block has to show as a loss.
        rules = dict(cssdiff.parse(
            ".council-mock { gap: 14px }"
            "@media (min-width: 560px) { .council-mock { gap: 20px } }"))
        self.assertEqual(rules[".council-mock"], {"gap": "14px"})
        self.assertEqual(
            rules["@media (min-width: 560px) | .council-mock"], {"gap": "20px"})

    def test_grouped_selectors_are_split_so_losing_one_is_visible(self):
        rules = dict(cssdiff.parse("h1, h2, h3 { margin: 0 }"))
        self.assertEqual(sorted(rules), ["h1", "h2", "h3"])

    def test_comments_do_not_become_selectors(self):
        rules = dict(cssdiff.parse("/* .ghost { colour: red } */ .real { top: 0 }"))
        self.assertEqual(sorted(rules), [".real"])

    def test_whitespace_in_a_selector_is_normalised(self):
        # Otherwise a reflow turns every descendant selector into a false loss.
        rules = dict(cssdiff.parse(".a\n   .b { top: 0 }"))
        self.assertEqual(sorted(rules), [".a .b"])

    def test_nested_at_rules_keep_their_inner_selector(self):
        rules = dict(cssdiff.parse("@keyframes fill { 0% { width: 0 } }"))
        self.assertEqual(sorted(rules), ["@keyframes fill | 0%"])

    def test_a_blockless_at_rule_does_not_glue_onto_the_next_selector(self):
        rules = dict(cssdiff.parse('@import url(x.css); .real { top: 0 }'))
        self.assertEqual(sorted(rules), [".real"])


class DeclarationMapTest(unittest.TestCase):

    def test_a_later_rule_wins_the_way_the_cascade_does(self):
        resolved = cssdiff.declaration_map(".a { top: 1px } .a { top: 2px }")
        self.assertEqual(resolved[(".a", "top")], "2px")


class ClassifyTest(unittest.TestCase):

    CORPUS = '<span class="council-logo-slot">Your logo</span>'

    def classify(self, selector, corpus=None, prefixes=()):
        return cssdiff.classify(selector, corpus or self.CORPUS, set(prefixes))

    def test_a_class_the_markup_still_emits_is_live(self):
        self.assertEqual(self.classify(".council-logo-slot"), "LIVE")

    def test_a_class_nothing_emits_is_retired(self):
        self.assertEqual(self.classify(".store-pill"), "RETIRED")

    def test_a_selector_is_only_as_live_as_its_rarest_part(self):
        # .council-logo-slot is emitted; .gone is not, so the pair is dead.
        self.assertEqual(self.classify(".council-logo-slot .gone"), "RETIRED")

    def test_an_element_only_selector_is_always_live(self):
        # This is how .legal-page h3 has to be reachable at all - and how the
        # heading-hierarchy bug was allowed to survive a class-only audit.
        self.assertEqual(self.classify("h3", corpus=""), "LIVE")

    def test_a_longer_class_does_not_borrow_liveness_from_a_shorter_one(self):
        # "council-logo-slot" contains "council-logo", and a substring search
        # would call the retired one live.
        self.assertEqual(self.classify(".council-logo"), "RETIRED")

    def test_a_shorter_class_does_not_borrow_liveness_from_a_longer_one(self):
        self.assertEqual(
            self.classify(".council", corpus='<b class="council-strip">'), "RETIRED")

    def test_a_runtime_built_class_is_dynamic_rather_than_retired(self):
        self.assertEqual(
            self.classify(".cov-pill-ok", corpus="", prefixes=["cov-pill-"]),
            "DYNAMIC")


class ConcatPrefixTest(unittest.TestCase):

    def test_only_the_last_token_of_the_literal_is_the_stem(self):
        # el('span', 'cov-pill cov-pill-' + bucket). Keeping the whole literal
        # gives a stem nothing starts with, and every bucket reads as dead.
        self.assertEqual(
            cssdiff.concat_prefixes("el('span', 'cov-pill cov-pill-' + b)"),
            {"cov-pill-"})

    def test_a_literal_that_is_not_concatenated_is_not_a_stem(self):
        self.assertEqual(cssdiff.concat_prefixes("el('span', 'cov-pill')"), set())


class AttributeClassTest(unittest.TestCase):

    def test_markup_built_inside_a_js_string_invents_no_classes(self):
        # '<path class="cov-area cov-area-' + b + '">' must not yield a class
        # called "b" - which is exactly what token-by-token filtering did.
        corpus = """parts.push('<path class="cov-area cov-area-' + b + '">')"""
        self.assertEqual(cssdiff._attribute_classes(corpus), set())

    def test_a_plain_attribute_is_read_normally(self):
        self.assertEqual(
            cssdiff._attribute_classes('<div class="mock-card council-mock-page">'),
            {"mock-card", "council-mock-page"})


class CompareTest(unittest.TestCase):
    """The shape of the bug this tool exists for, in miniature."""

    BEFORE = (".legal-page h2 { font-size: 1.15rem }"
              ".legal-page h3 { font-size: 1rem; margin: 26px 0 8px }"
              ".store-pill { padding: 8px 16px }")
    AFTER = (".legal-page h2 { font-size: 1.15rem }")
    CORPUS = '<section class="legal-page"><h3>Common questions</h3></section>'

    def losses(self):
        return cssdiff.compare(self.BEFORE, self.AFTER, self.CORPUS)[0]

    def test_the_dropped_rule_is_reported_as_live(self):
        live = [(s, p) for s, p, _, verdict in self.losses() if verdict == "LIVE"]
        self.assertEqual(live, [(".legal-page h3", "font-size"),
                                (".legal-page h3", "margin")])

    def test_a_deliberate_retirement_is_not_mixed_in_with_it(self):
        retired = [s for s, _, _, verdict in self.losses() if verdict == "RETIRED"]
        self.assertEqual(retired, [".store-pill"])

    def test_a_surviving_declaration_is_not_a_loss(self):
        self.assertNotIn(".legal-page h2", [s for s, _, _, _ in self.losses()])

    def test_a_changed_value_is_reported_apart_from_a_loss(self):
        # Silent drift: the selector survives, the value does not. This is how
        # a role token gets quietly replaced by a hardcoded literal.
        _, changes = cssdiff.compare(
            ".a { color: var(--text) }", ".a { color: #fff }", "")
        self.assertEqual(changes, [(".a", "color", "var(--text)", "#fff")])


class OrphanTest(unittest.TestCase):

    def test_a_class_in_markup_with_no_rule_is_reported(self):
        unstyled, _ = cssdiff.orphans(".styled { top: 0 }",
                                      '<a class="styled nav-secondary">')
        self.assertEqual(unstyled, ["nav-secondary"])

    def test_a_rule_no_markup_asks_for_is_reported(self):
        _, unused = cssdiff.orphans(".cta-centre { top: 0 }", "<div></div>")
        self.assertEqual(unused, ["cta-centre"])

    def test_a_runtime_built_class_is_not_called_dead(self):
        _, unused = cssdiff.orphans(".cov-pill-ok { top: 0 }",
                                    "el('span', 'cov-pill cov-pill-' + b)")
        self.assertEqual(unused, [])


if __name__ == "__main__":
    unittest.main()
