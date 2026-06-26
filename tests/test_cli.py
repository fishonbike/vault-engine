import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from vaultengine import cli

PII_TEXT = "联系 zhang.san@example.com 或 13900001111，证件 11010119900307391X。"


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def read_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.infile = os.path.join(self.tmp.name, "in.txt")
        with open(self.infile, "w", encoding="utf-8") as fh:
            fh.write(PII_TEXT)

    def test_scrub_offline_writes_outputs(self):
        out = os.path.join(self.tmp.name, "out.txt")
        code, _, err = run(["scrub", self.infile, "-o", out, "--no-llm"])
        self.assertEqual(code, 0)
        scrubbed = read(out)
        self.assertNotIn("zhang.san@example.com", scrubbed)
        self.assertNotIn("13900001111", scrubbed)
        self.assertTrue(os.path.exists(out + ".map.json"))
        self.assertIn("已假名化", err)

    def test_one_way_writes_no_map(self):
        out = os.path.join(self.tmp.name, "ow.txt")
        code, _, _ = run(["scrub", self.infile, "-o", out, "--no-llm", "--one-way"])
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(out + ".map.json"))

    def test_report_written(self):
        out = os.path.join(self.tmp.name, "r.txt")
        rep = os.path.join(self.tmp.name, "report.md")
        run(["scrub", self.infile, "-o", out, "--no-llm", "--report", rep])
        self.assertIn("# vault-engine 脱敏报告", read(rep))

    def test_scrub_then_rehydrate_round_trip(self):
        out = os.path.join(self.tmp.name, "out.txt")
        run(["scrub", self.infile, "-o", out, "--no-llm"])
        mapping = read_json(out + ".map.json")
        email_tok = next(t for t, e in mapping["tokens"].items()
                         if e["surface"] == "zhang.san@example.com")

        reply = os.path.join(self.tmp.name, "reply.json")
        with open(reply, "w", encoding="utf-8") as fh:
            json.dump({"hit": email_tok}, fh)
        restored = os.path.join(self.tmp.name, "restored.json")
        code, _, _ = run(["rehydrate", reply, "--map", out + ".map.json",
                          "-o", restored])
        self.assertEqual(code, 0)
        self.assertEqual(read_json(restored)["hit"], "zhang.san@example.com")

    def test_providers_lists_builtins(self):
        code, out, _ = run(["providers"])
        self.assertEqual(code, 0)
        self.assertIn("ollama", out)
        self.assertIn("openai-compat", out)

    def test_version(self):
        code, out, _ = run(["version"])
        self.assertEqual(code, 0)
        self.assertIn("vault-engine", out)

    def test_stdin_stdout(self):
        import sys
        old = sys.stdin
        sys.stdin = io.StringIO(PII_TEXT)
        try:
            code, out, _ = run(["scrub", "-", "-o", "-", "--no-llm", "--one-way"])
        finally:
            sys.stdin = old
        self.assertEqual(code, 0)
        self.assertNotIn("13900001111", out)


if __name__ == "__main__":
    unittest.main()
