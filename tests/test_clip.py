import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from vaultengine import cli

# Real clipboard I/O (pbcopy/pbpaste etc.) is replaced with fakes so the test is
# deterministic and runs in CI — it exercises the `clip` command's logic, not the
# OS clipboard.


def run_clip(argv, clipboard_text):
    """Run `vault-engine <argv>` with a fake clipboard; return what it wrote."""
    written = {}

    def fake_read():
        return clipboard_text

    def fake_write(text):
        written["text"] = text

    out, err = io.StringIO(), io.StringIO()
    with mock.patch("vaultengine.clipboard.read_clipboard", fake_read), \
         mock.patch("vaultengine.clipboard.write_clipboard", fake_write), \
         redirect_stdout(out), redirect_stderr(err):
        code = cli.main(argv)
    return code, written.get("text"), err.getvalue()


class ClipTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.map = os.path.join(self.tmp.name, "clip.map.json")

    def test_clip_scrubs_clipboard_and_saves_map(self):
        code, written, _ = run_clip(
            ["clip", "--no-llm", "--map", self.map],
            "联系 a@b.com 或 13900001111，地址杭州。")
        self.assertEqual(code, 0)
        self.assertNotIn("a@b.com", written)
        self.assertNotIn("13900001111", written)
        self.assertTrue(os.path.exists(self.map))

    def test_one_way_writes_no_map(self):
        code, _, _ = run_clip(
            ["clip", "--no-llm", "--one-way", "--map", self.map], "x@y.com")
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(self.map))

    def test_empty_clipboard_errors(self):
        code, _, err = run_clip(["clip", "--no-llm", "--map", self.map], "   ")
        self.assertEqual(code, cli.EXIT_ERROR)
        self.assertIn("空", err)

    def test_round_trip_via_clipboard(self):
        # scrub
        _, scrubbed, _ = run_clip(
            ["clip", "--no-llm", "--map", self.map], "我的邮箱是 z@s.com。")
        self.assertNotIn("z@s.com", scrubbed)
        # rehydrate the scrubbed text back
        _, restored, _ = run_clip(
            ["clip", "--rehydrate", "--map", self.map], scrubbed)
        self.assertIn("z@s.com", restored)

    def test_rehydrate_handles_json_reply(self):
        _, _, _ = run_clip(["clip", "--no-llm", "--map", self.map], "邮箱 a@b.com")
        with open(self.map, encoding="utf-8") as fh:
            token = next(iter(json.load(fh)["tokens"]))
        _, restored, _ = run_clip(
            ["clip", "--rehydrate", "--map", self.map],
            json.dumps({"note": token}))
        self.assertIn("a@b.com", restored)


if __name__ == "__main__":
    unittest.main()
