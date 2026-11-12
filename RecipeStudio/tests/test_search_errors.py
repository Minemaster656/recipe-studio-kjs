import tempfile
import unittest
from pathlib import Path
from emb_api import EmbeddingError, ImageNotSupported
from RecipeStudio.services.search import SearchGateway, SearchUnavailable


class _FakeIndex:
    def __init__(self, exc):
        self.exc = exc
        self.closed = False

    def search_text(self, query, limit):
        raise self.exc

    def search_image(self, path, limit):
        raise self.exc

    def close(self):
        self.closed = True


class SearchErrorTests(unittest.TestCase):
    def _gateway(self, exc):
        gateway = SearchGateway({"search_limit": 500}, None)
        gateway._load_api = lambda: (
            object,
            object,
            EmbeddingError,
            ImageNotSupported,
        )
        gateway._open_index = lambda embeddings=False: _FakeIndex(exc)
        return gateway

    def test_embedding_model_unavailable_is_reported(self):
        gateway = self._gateway(EmbeddingError("connection refused"))
        with self.assertRaises(SearchUnavailable) as context:
            gateway.search("minecraft:iron_ingot", "E")
        self.assertIn("unavailable", str(context.exception))

    def test_image_not_supported_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "item.png"
            image.write_bytes(b"not really a png")
            gateway = self._gateway(ImageNotSupported("server rejected image input"))
            with self.assertRaises(SearchUnavailable) as context:
                gateway.search(str(image), "E")
        self.assertIn("does not support images", str(context.exception))

    def test_missing_image_file_is_reported(self):
        gateway = self._gateway(EmbeddingError("should not be called"))
        with self.assertRaises(SearchUnavailable) as context:
            gateway.search("/tmp/definitely-missing-item.png", "E")
        self.assertIn("Image file not found", str(context.exception))


if __name__ == "__main__":
    unittest.main()
