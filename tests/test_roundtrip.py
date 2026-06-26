import json
import os
import unittest

from vaultengine import formats
from vaultengine.pipeline import deidentify, rehydrate

from .fakes import FakeProvider, fake_config

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "sample_markdown.md")


class RoundTripTests(unittest.TestCase):
    def setUp(self):
        with open(FIX, encoding="utf-8") as fh:
            self.doc = fh.read()
        cfg = fake_config()
        segs = formats.segment(self.doc, formats.AUTO)
        self.result = deidentify(self.doc, cfg, provider=FakeProvider(cfg),
                                 segments=segs)

    def _token_for(self, surface):
        for tok, e in self.result.vault.tokens.items():
            if e["surface"] == surface:
                return tok
        return None

    def test_fenced_schema_preserved_verbatim(self):
        out = self.result.text
        self.assertIn("```json", out)            # reply schema intact for the model
        self.assertIn('"summary"', out)

    def test_material_scrubbed(self):
        out = self.result.text
        for leaked in ("张三", "小张", "蚂蚁集团", "Acme Capital", "杭州",
                       "zhang.san@example.com", "13900001111"):
            self.assertNotIn(leaked, out)

    def test_preexisting_token_passes_through(self):
        # a pre-existing P-<n> placeholder in the input is preserved untouched
        self.assertIn("P-7", self.result.text)

    def test_new_person_gets_pn_token(self):
        tok = self._token_for("张三")
        self.assertIsNotNone(tok)
        self.assertTrue(tok.startswith("P-n"))

    def test_cloud_reply_rehydrates_to_real_identity(self):
        ptok = self._token_for("张三")
        cloud_reply = {
            "summary": f"{ptok} 与 P-7 是核心二人组",
            "people": [ptok, "P-7"],
            "links": [{"a": ptok, "b": "P-7", "rel": "同事"}],
        }
        restored = rehydrate(cloud_reply, self.result.vault)
        self.assertIn("张三", restored["summary"])
        self.assertIn("P-7", restored["summary"])      # pre-existing token untouched
        self.assertEqual(restored["links"][0]["a"], "张三")
        self.assertEqual(restored["links"][0]["b"], "P-7")

    def test_rehydrate_from_saved_map(self):
        ptok = self._token_for("张三")
        saved = json.loads(json.dumps(self.result.map))   # simulate disk round-trip
        restored = rehydrate({"x": ptok}, saved)
        self.assertEqual(restored["x"], "张三")


if __name__ == "__main__":
    unittest.main()
