import os
import unittest
from unittest import mock

from fleetglint.redact import redact


class ShapeTest(unittest.TestCase):
    def assertRedacted(self, text, expected="[redacted]"):
        out, count = redact(text, {})
        self.assertEqual(out, expected)
        self.assertEqual(count, 1)
        return out

    def test_github_tokens(self):
        self.assertRedacted("ghp_" + "A" * 36)
        self.assertRedacted("gho_" + "b" * 20)
        self.assertRedacted("github_pat_" + "A1_" * 7)

    def test_anthropic_key(self):
        self.assertRedacted("sk-ant-api03-" + "x" * 30)

    def test_generic_sk_key(self):
        self.assertRedacted("sk-proj-" + "Z" * 30)

    def test_google_key(self):
        self.assertRedacted("AIza" + "A" * 35)

    def test_npm_token(self):
        self.assertRedacted("npm_" + "a1" * 18)

    def test_aws_key(self):
        self.assertRedacted("AKIA" + "A1" * 8)

    def test_slack_token(self):
        self.assertRedacted("xoxb-" + "1" * 12)

    def test_gitlab_token(self):
        self.assertRedacted("glpat-" + "a" * 22)

    def test_jwt(self):
        self.assertRedacted("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.c2lnbmF0dXJl")

    def test_bearer_token_keeps_the_prefix(self):
        out = self.assertRedacted("Authorization: Bearer abc123", "Authorization: Bearer [redacted]")
        self.assertNotIn("abc123", out)

    def test_ordinary_text_is_untouched(self):
        text = ("/Users/me/Developer/x.log 550e8400-e29b-41d4-a716-446655440000 "
                "0123456789abcdef0123456789abcdef01234567")
        self.assertEqual(redact(text, {}), (text, 0))

    def test_count_sums_replacements(self):
        out, count = redact("AKIA" + "A" * 16 + " and ghp_" + "B" * 36, {})
        self.assertEqual(out, "[redacted] and [redacted]")
        self.assertEqual(count, 2)


class EnvTest(unittest.TestCase):
    def test_credential_named_values_are_redacted(self):
        out, count = redact("key abcdefgh123 end", {"MY_API_KEY": "abcdefgh123"})
        self.assertEqual(out, "key [redacted] end")
        self.assertEqual(count, 1)

    def test_each_occurrence_counts(self):
        out, count = redact("abcdefgh123/abcdefgh123", {"GH_TOKEN": "abcdefgh123"})
        self.assertEqual(out, "[redacted]/[redacted]")
        self.assertEqual(count, 2)

    def test_short_values_and_plain_names_are_ignored(self):
        text = "short and ordinary"
        self.assertEqual(redact(text, {"API_KEY": "short", "HOME": "ordinary"}), (text, 0))

    def test_defaults_to_os_environ(self):
        with mock.patch.dict(os.environ, {"DEPLOY_SECRET": "verysecretvalue"}):
            out, count = redact("value verysecretvalue")
        self.assertEqual(out, "value [redacted]")
        self.assertEqual(count, 1)


class PemTest(unittest.TestCase):
    def test_whole_block_is_redacted(self):
        text = ("before\n-----BEGIN RSA PRIVATE KEY-----\nMIIEsecret\n"
                "-----END RSA PRIVATE KEY-----\nafter")
        out, count = redact(text, {})
        self.assertEqual(out, "before\n[redacted]\nafter")
        self.assertEqual(count, 1)

    def test_unterminated_block_runs_to_the_end(self):
        text = "before\n-----BEGIN OPENSSH PRIVATE KEY-----\nMIIEsecret\nmore"
        out, count = redact(text, {})
        self.assertEqual(out, "before\n[redacted]")
        self.assertEqual(count, 1)

    def test_text_starting_inside_a_block(self):
        text = "MIIEsecret\n-----END RSA PRIVATE KEY-----\nafter"
        out, count = redact(text, {})
        self.assertEqual(out, "[redacted]\nafter")
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
