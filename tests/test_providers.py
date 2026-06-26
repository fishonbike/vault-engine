import unittest

from vaultengine.config import Config
from vaultengine.providers import available, get_provider
from vaultengine.providers.base import Provider, parse_json_array


class CannedProvider(Provider):
    """Returns a fixed model reply, to exercise base detect/critique parsing."""
    def __init__(self, config, reply):
        super().__init__(config)
        self._reply = reply

    def complete(self, prompt: str) -> str:
        return self._reply


class ParseTests(unittest.TestCase):
    def test_plain_array(self):
        self.assertEqual(parse_json_array('[{"surface":"a"}]'), [{"surface": "a"}])

    def test_strips_code_fence(self):
        raw = '```json\n[{"surface":"x","category":"person"}]\n```'
        self.assertEqual(parse_json_array(raw)[0]["surface"], "x")

    def test_ignores_surrounding_prose(self):
        raw = '好的，结果如下：[{"surface":"y"}] 以上。'
        self.assertEqual(parse_json_array(raw), [{"surface": "y"}])

    def test_bracket_inside_string(self):
        raw = '[{"surface":"a]b"}]'
        self.assertEqual(parse_json_array(raw), [{"surface": "a]b"}])

    def test_garbage_returns_empty(self):
        self.assertEqual(parse_json_array("not json at all"), [])
        self.assertEqual(parse_json_array(""), [])


class BaseDetectTests(unittest.TestCase):
    def test_detect_builds_spans(self):
        reply = ('[{"surface":"张三","category":"person","aliases":["小张"],'
                 '"confidence":0.9},{"surface":"x","category":"weird"}]')
        p = CannedProvider(Config(), reply)
        spans = p.detect("张三 小张 x")
        self.assertEqual(spans[0].surface, "张三")
        self.assertEqual(spans[0].category, "person")
        self.assertEqual(spans[0].aliases, ("小张",))
        self.assertEqual(spans[1].category, "other")   # unknown -> normalized

    def test_critique_parses(self):
        p = CannedProvider(Config(), '[{"quote":"张三","why":"name","category":"person"}]')
        out = p.critique("张三 still here")
        self.assertEqual(out[0]["quote"], "张三")

    def test_empty_text_no_calls(self):
        self.assertEqual(CannedProvider(Config(), "boom").detect(""), [])


class RegistryTests(unittest.TestCase):
    def test_builtins_registered(self):
        for name in ("ollama", "openai-compat", "null"):
            self.assertIn(name, available())

    def test_get_unknown_raises(self):
        with self.assertRaises(ValueError):
            get_provider(Config(provider="nope"))

    def test_null_provider(self):
        self.assertEqual(get_provider(Config(provider="null")).detect("张三"), [])


if __name__ == "__main__":
    unittest.main()
