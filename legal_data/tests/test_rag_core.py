from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from build_index_v2 import vi_legal_tokenize
from generate_safe import verify_citations


class TokenizerTests(unittest.TestCase):
    def test_vietnamese_bigrams(self):
        tokens = vi_legal_tokenize("trợ cấp thất nghiệp")
        self.assertIn("trợ_cấp", tokens)
        self.assertIn("thất_nghiệp", tokens)


class CitationTests(unittest.TestCase):
    def setUp(self):
        self.evidence = {"c1": {"text": "Người lao động được hưởng trợ cấp thất nghiệp."}}

    def test_valid_quote(self):
        payload = {
            "answerable": True,
            "citations": [{"chunk_id": "c1", "quote": "hưởng trợ cấp thất nghiệp"}],
        }
        self.assertEqual(verify_citations(payload, self.evidence), (True, []))

    def test_unknown_chunk_is_rejected(self):
        valid, errors = verify_citations(
            {"answerable": True, "citations": [{"chunk_id": "missing", "quote": "x"}]},
            self.evidence,
        )
        self.assertFalse(valid)
        self.assertTrue(errors)

    def test_unverifiable_quote_is_rejected(self):
        valid, errors = verify_citations(
            {"answerable": True, "citations": [{"chunk_id": "c1", "quote": "không tồn tại"}]},
            self.evidence,
        )
        self.assertFalse(valid)
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()

