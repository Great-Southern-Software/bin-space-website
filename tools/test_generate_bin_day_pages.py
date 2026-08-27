"""Unit tests for the bits of the bin day generator that are not obvious.

    python3 -m unittest discover -s tools

Three functions carry real logic and fail quietly when they are wrong: a bad
slug silently changes a published URL, a bad source_origin can republish a
vendor query string carrying an API key, and the population rounding has a
boundary. The rest of the generator is string templating.
"""

import unittest

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

spec = spec_from_file_location("generator",
                               Path(__file__).parent / "generate-bin-day-pages.py")
generator = module_from_spec(spec)
spec.loader.exec_module(generator)


class SlugTest(unittest.TestCase):

    def test_drops_the_state_disambiguator(self):
        # The URL already carries the state in its own segment.
        self.assertEqual(generator.slug("Central Coast (NSW)"), "central-coast")
        self.assertEqual(generator.slug("Central Highlands (Qld)"), "central-highlands")

    def test_collapses_punctuation_and_spelling_out_ampersands(self):
        self.assertEqual(generator.slug("Bridgetown-Greenbushes"), "bridgetown-greenbushes")
        self.assertEqual(generator.slug("Glamorgan-Spring Bay"), "glamorgan-spring-bay")
        self.assertEqual(generator.slug("A & B"), "a-and-b")

    def test_never_leaves_a_leading_or_trailing_separator(self):
        self.assertEqual(generator.slug("  Perth  "), "perth")
        self.assertEqual(generator.slug("(Tas.) Dorset"), "dorset")


class SourceOriginTest(unittest.TestCase):

    def test_keeps_only_the_scheme_and_host(self):
        self.assertEqual(
            generator.source_origin("https://www.moretonbay.qld.gov.au/some/path?x=1"),
            "https://www.moretonbay.qld.gov.au")

    def test_strips_a_query_string_carrying_a_key(self):
        # Ipswich's stored source URL embeds the council's own API key. It must
        # not reach a published page.
        origin = generator.source_origin(
            "host=console.whatbinday.com&apiKey=b8dbca0c-ad9c-4&base=https://x.gov.au/y")
        self.assertNotIn("apiKey", origin)
        self.assertEqual(origin, "https://x.gov.au")

    def test_takes_the_first_of_several_pipe_separated_urls(self):
        self.assertEqual(
            generator.source_origin(
                "https://leichhardt.waste-info.com.au|https://marrickville.waste-info.com.au"),
            "https://leichhardt.waste-info.com.au")

    def test_returns_none_when_there_is_no_url(self):
        for value in [None, "", "bundled", "kalamunda", "swan"]:
            self.assertIsNone(generator.source_origin(value), value)


class EscapeTest(unittest.TestCase):

    def test_escapes_markup_significant_characters(self):
        self.assertEqual(generator.escape("A & B"), "A &amp; B")
        self.assertEqual(generator.escape('a "b" <c>'), "a &quot;b&quot; &lt;c&gt;")


class DisplayNameTest(unittest.TestCase):

    def test_drops_the_parenthetical_but_keeps_the_rest(self):
        self.assertEqual(generator.display_name("Central Coast (NSW)"), "Central Coast")
        self.assertEqual(generator.display_name("Unincorporated ACT"), "Unincorporated ACT")


if __name__ == "__main__":
    unittest.main()
