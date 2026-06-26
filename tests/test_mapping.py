import unittest

from vaultengine import config as cfg
from vaultengine.mapping import Vault, is_token_like
from vaultengine.spans import (CAT_DATE, CAT_ORG, CAT_PERSON, Span)


class MappingTests(unittest.TestCase):
    def test_stable_token_per_surface(self):
        v = Vault()
        t1 = v.token_for("Acme Capital", CAT_ORG)
        t2 = v.token_for("Acme Capital", CAT_ORG)
        self.assertEqual(t1, t2)
        self.assertTrue(t1.startswith("ORG_"))

    def test_alias_groups_to_one_token(self):
        v = Vault()
        spans = [Span("张三", CAT_PERSON, source="llm", aliases=("小张",))]
        pairs = v.assign(spans)
        self.assertEqual(pairs["张三"], pairs["小张"])
        self.assertTrue(pairs["张三"].startswith("P-n"))

    def test_new_person_namespace_never_collides_with_plain_pid(self):
        v = Vault()
        tok = v.token_for("李四", CAT_PERSON)
        self.assertTrue(tok.startswith("P-n"))
        self.assertNotEqual(tok, "P-7")           # pre-existing P-<int> stays distinct

    def test_token_like_filter(self):
        for s in ("P-7", "P-n3", "ORG_1", "ID_12", "EMAIL_2"):
            self.assertTrue(is_token_like(s))
        for s in ("张三", "P-", "Acme"):
            self.assertFalse(is_token_like(s))

    def test_reserved_left_untouched(self):
        v = Vault(reserved={"P-7"})
        self.assertIsNone(v.token_for("P-7", CAT_PERSON))

    def test_policy_light_keeps_org(self):
        v = Vault(policy=cfg.POLICY_LIGHT)
        pairs = v.assign([Span("蚂蚁集团", CAT_ORG, source="llm")])
        self.assertEqual(pairs, {})               # light: orgs untouched

    def test_policy_balanced_keeps_dates_max_redacts(self):
        bal = Vault(policy=cfg.POLICY_BALANCED)
        self.assertEqual(bal.assign([Span("2026-06-01", CAT_DATE, source="llm")]), {})
        mx = Vault(policy=cfg.POLICY_MAX)
        self.assertTrue(mx.assign([Span("2026-06-01", CAT_DATE, source="llm")]))

    def test_policy_max_is_opaque(self):
        v = Vault(policy=cfg.POLICY_MAX)
        tok = v.token_for("蚂蚁集团", CAT_ORG)
        self.assertTrue(tok.startswith("R_"))     # type hidden under max

    def test_apply_longest_surface_first(self):
        v = Vault()
        spans = [Span("Acme", CAT_ORG, source="llm"),
                 Span("Acme Capital", CAT_ORG, source="llm")]
        pairs = v.assign(spans)
        out = v.apply("Acme Capital 与 Acme 是同一家", pairs)
        self.assertNotIn("Acme Capital", out)
        # both surfaces collapse to their own tokens, no partial corruption
        self.assertNotIn("Capital", out)

    def test_rehydrate_round_trip(self):
        v = Vault()
        pairs = v.assign([Span("张三", CAT_PERSON, source="llm")])
        token = pairs["张三"]
        sanitized = v.apply("张三去了北京", pairs)
        self.assertEqual(v.rehydrate_text(sanitized), "张三去了北京")
        self.assertIn(token, sanitized)

    def test_rehydrate_prefix_safe(self):
        # ID_1 must not corrupt ID_12 on reverse
        v = Vault.from_map({"policy": "balanced", "tokens": {
            "ID_1": {"surface": "AAA", "category": "id", "kind": "", "aliases": []},
            "ID_12": {"surface": "BBB", "category": "id", "kind": "", "aliases": []},
        }})
        self.assertEqual(v.rehydrate_text("ID_12 与 ID_1"), "BBB 与 AAA")

    def test_rehydrate_nested_structure(self):
        v = Vault()
        pairs = v.assign([Span("李四", CAT_PERSON, source="llm")])
        tok = pairs["李四"]
        reply = {"insights": [{"text": f"{tok} 很关键", "entities": [tok]}]}
        out = v.rehydrate(reply)
        self.assertEqual(out["insights"][0]["entities"], ["李四"])

    def test_save_load(self):
        v = Vault()
        v.assign([Span("王五", CAT_PERSON, source="llm")])
        data = v.to_map()
        v2 = Vault.from_map(data)
        self.assertEqual(v2.rehydrate_text(v.apply("王五在此")), "王五在此")


    def test_ascii_word_boundary_guards(self):
        v = Vault()
        pairs = v.assign([
            Span("Jack", CAT_PERSON, source="llm"),
            Span("张三", CAT_PERSON, source="llm"),
        ])
        text = "Jack went to jackpot with 张三, hijack, and 张三李四."
        out = v.apply(text, pairs)
        # Jack -> P-n1 (assuming it's P-n1)
        # jackpot -> unchanged (partial hit prevented)
        # hijack -> unchanged (partial hit prevented)
        # 张三 -> P-n2
        # 张三李四 -> P-n2李四 (CJK has no word boundary check)
        self.assertNotIn("Jack went", out)
        self.assertIn("jackpot", out)
        self.assertIn("hijack", out)
        self.assertIn("P-n2李四", out)


if __name__ == "__main__":
    unittest.main()
