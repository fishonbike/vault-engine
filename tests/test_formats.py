import os
import unittest

from vaultengine import formats

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "sample_markdown.md")


class FormatTests(unittest.TestCase):
    def setUp(self):
        with open(FIX, encoding="utf-8") as fh:
            self.doc = fh.read()

    def test_plain_is_one_scrub_segment(self):
        segs = formats.segment("hello world", formats.PLAIN)
        self.assertEqual(segs, [("scrub", "hello world")])

    def test_auto_detects_fenced_markdown(self):
        self.assertEqual(formats.detect_format(self.doc), formats.MARKDOWN)
        self.assertEqual(formats.detect_format("just text"), formats.PLAIN)

    def test_concatenation_reproduces_input(self):
        segs = formats.segment(self.doc, formats.MARKDOWN)
        self.assertEqual("".join(c for _, c in segs), self.doc)

    def test_fenced_block_is_kept_prose_is_scrubbed(self):
        segs = formats.segment(self.doc, formats.MARKDOWN)
        kept = "".join(c for k, c in segs if k == "keep")
        scrubbed = "".join(c for k, c in segs if k == "scrub")
        # the fenced schema block is preserved verbatim
        self.assertIn("```json", kept)
        self.assertIn('"summary"', kept)
        # the prose material is scrubbable; the schema is not in the scrub region
        self.assertIn("张三", scrubbed)
        self.assertNotIn("```json", scrubbed)

    def test_unterminated_fence_kept(self):
        segs = formats.segment("intro 张三\n```\nopen fence", formats.MARKDOWN)
        self.assertEqual("".join(c for _, c in segs), "intro 张三\n```\nopen fence")
        self.assertTrue(any(k == "keep" and "```" in c for k, c in segs))


    def test_fenced_block_contents_scrubbed_when_scrub_fenced_true(self):
        text = "Hello 张三\n```json\nLi Si\n```\nGoodbye"
        segs = formats.segment(text, formats.MARKDOWN, scrub_fenced=True)
        expected = [
            ("scrub", "Hello 张三\n"),
            ("keep", "```json\n"),
            ("scrub", "Li Si\n"),
            ("keep", "```"),
            ("scrub", "\nGoodbye"),
        ]
        self.assertEqual(segs, expected)


if __name__ == "__main__":
    unittest.main()
