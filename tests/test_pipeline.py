import unittest

from vaultengine import config as cfg
from vaultengine.pipeline import deidentify
from vaultengine.providers.base import Provider

from .fakes import FakeProvider, RaisingProvider, fake_config

TEXT = ("张三在杭州的蚂蚁集团做风控总监，邮箱 zhang.san@example.com，"
        "手机 13900001111。他和 P-7 见了 Acme Capital。")


class PipelineTests(unittest.TestCase):
    def test_persons_and_pii_removed(self):
        r = deidentify(TEXT, fake_config(), provider=FakeProvider(fake_config()))
        for leaked in ("张三", "蚂蚁集团", "Acme Capital", "风控总监", "杭州",
                       "zhang.san@example.com", "13900001111"):
            self.assertNotIn(leaked, r.text, f"{leaked} leaked into output")

    def test_preexisting_token_preserved(self):
        r = deidentify(TEXT, fake_config(), provider=FakeProvider(fake_config()))
        self.assertIn("P-7", r.text)            # pre-existing placeholder untouched

    def test_every_person_tokenized(self):
        r = deidentify(TEXT, fake_config(), provider=FakeProvider(fake_config()))
        persons = [e for e in r.vault.tokens.values() if e["category"] == "person"]
        self.assertTrue(persons)
        self.assertTrue(all(False for p in persons if p["surface"] == ""))

    def test_critic_clean_after_scrub(self):
        r = deidentify(TEXT, fake_config(), provider=FakeProvider(fake_config()))
        self.assertEqual(r.residual, [])        # names gone -> nothing to flag
        self.assertTrue(r.critic_ok)

    def test_report_counts(self):
        r = deidentify(TEXT, fake_config(), provider=FakeProvider(fake_config()))
        self.assertGreaterEqual(r.report.person_total, 1)
        self.assertIn("person", r.report.category_counts)

    def test_degraded_when_model_fails(self):
        r = deidentify(TEXT, fake_config(), provider=RaisingProvider(fake_config()))
        self.assertFalse(r.llm_ok)
        self.assertFalse(r.safe)
        self.assertTrue(any("脱敏不足" in w for w in r.report.warnings))
        # regex floor still applied even though the model failed
        self.assertNotIn("zhang.san@example.com", r.text)

    def test_offline_regex_only(self):
        r = deidentify(TEXT, cfg.Config(use_llm=False))
        self.assertFalse(r.llm_requested)
        self.assertTrue(r.safe)                 # nothing was requested-but-failed
        self.assertNotIn("13900001111", r.text)
        self.assertIn("张三", r.text)            # needs a model; regex won't catch

    def test_max_policy_opaque(self):
        c = fake_config(policy=cfg.POLICY_MAX)
        r = deidentify(TEXT, c, provider=FakeProvider(c))
        self.assertNotIn("张三", r.text)
        self.assertTrue(any(t.startswith("R_") for t in r.vault.tokens))
        self.assertFalse(any(t.startswith("ORG_") for t in r.vault.tokens))


if __name__ == "__main__":
    unittest.main()
