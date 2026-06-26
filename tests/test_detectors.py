import unittest

from vaultengine.detectors import _luhn_ok, detect
from vaultengine.spans import CAT_CONTACT, CAT_ID


def kinds(text):
    return {s.note for s in detect(text)}


def surfaces(text):
    return {s.surface for s in detect(text)}


class DetectorTests(unittest.TestCase):
    def test_email(self):
        self.assertIn("a.b+x@mail.example.com", surfaces("写信 a.b+x@mail.example.com 给我"))

    def test_cn_mobile(self):
        spans = detect("电话 13912345678 联系")
        self.assertEqual(spans[0].surface, "13912345678")
        self.assertEqual(spans[0].category, CAT_CONTACT)

    def test_international_phone(self):
        self.assertIn("phone-e164", kinds("call +1 415 555 0199 now"))

    def test_cn_id(self):
        self.assertIn("11010119900307391X", surfaces("证件 11010119900307391X 号"))

    def test_url_and_handle(self):
        s = surfaces("see https://x.example.org/p and ping @alice_99")
        self.assertIn("https://x.example.org/p", s)
        self.assertIn("@alice_99", s)

    def test_ipv4(self):
        self.assertIn("ipv4", kinds("server at 192.168.31.7 down"))

    def test_card_luhn(self):
        self.assertTrue(_luhn_ok("4111111111111111"))
        self.assertFalse(_luhn_ok("4111111111111112"))
        self.assertIn("card", kinds("卡号 4111 1111 1111 1111 已绑定"))
        self.assertNotIn("card", kinds("流水号 4111 1111 1111 1112 无效"))

    def test_empty(self):
        self.assertEqual(detect(""), [])

    def test_offsets_are_anchored(self):
        for s in detect("mail me a@b.com please"):
            self.assertGreaterEqual(s.start, 0)
            self.assertGreater(s.end, s.start)


if __name__ == "__main__":
    unittest.main()
