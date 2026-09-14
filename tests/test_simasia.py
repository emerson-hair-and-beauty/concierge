import tempfile
import unittest

import numpy as np

from simasia import SimasiaGuard


class KeywordEmbedder:
    """A deterministic, offline embedding backend for Simasia tests."""

    def encode(self, sentences, **_kwargs):
        vectors = []
        for sentence in sentences:
            text = sentence.lower()
            friendly = sum(word in text for word in ("hey", "happy", "quick", "thanks"))
            formal = sum(word in text for word in ("kindly", "enterprise", "processing", "request"))
            vectors.append([friendly, formal, len(text.split()) / 100])
        return np.asarray(vectors, dtype=np.float32)


class TestSimasiaIntegration(unittest.TestCase):
    def test_train_score_and_explain_with_offline_embedder(self):
        on_brand = (
            "Hey, we are happy to help. Thanks for choosing us. "
            "Quick updates keep things simple. We are happy to help today. "
            "Hey there, thanks for reaching out. We will keep this quick and clear."
        )
        off_brand = (
            "Kindly note your request is processing. Enterprise workflows require review. "
            "The enterprise system is processing records. Kindly await the next review. "
            "Your request remains under review. Kindly follow enterprise procedures."
        )

        with tempfile.TemporaryDirectory() as artifact_dir:
            guard = SimasiaGuard(
                brand_id="concierge",
                artifact_dir=artifact_dir,
                embedding_model=KeywordEmbedder(),
            )
            self.assertGreaterEqual(guard.train(on_brand, off_brand), 0.9)

            reloaded_guard = SimasiaGuard(
                brand_id="concierge",
                artifact_dir=artifact_dir,
                embedding_model=KeywordEmbedder(),
            )
            explanation = reloaded_guard.explain("Hey, thanks! We are happy to help quickly.")

        self.assertGreater(explanation["score"], 0.5)
        self.assertEqual(explanation["verdict"], "on-brand")
        self.assertIn("text", explanation["closest_on_brand"])
        self.assertIn("text", explanation["closest_off_brand"])


if __name__ == "__main__":
    unittest.main()
