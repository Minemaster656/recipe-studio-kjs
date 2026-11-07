# embeddings

Семантический поиск по `embeddings.db` через локальный OpenAI-совместимый
embedding-сервер (llama.cpp с `--embeddings --mmproj`, vLLM, infinity, tei и т.п.).

## CLI

```bash
python embed_search.py
```

Меню: векторный поиск по тексту, substring, fuzzy и векторный поиск по картинке.

## Как модуль

```python
from emb_api import EmbeddingClient, SearchIndex

client = EmbeddingClient("http://localhost:9931/v1", "embeddinggemma2")
idx = SearchIndex("embeddings.db", client=client)

hits = idx.search_text("black fan", limit=5)
hits = idx.search_image("/path/to/fan.jpg", limit=5)
hits = idx.search_substring("fan", field="id", limit=5)
hits = idx.search_fuzzy("fna", field="id", limit=5)

for h in hits:
    print(f"{h.score * 100:5.1f}%  {h.full}")

idx.close()
```

Или через контекстный менеджер:

```python
with SearchIndex("embeddings.db", client=client) as idx:
    hits = idx.search_image("fan.jpg")
```

`Hit` — dataclass с полями `full`, `mod`, `id`, `score` (0..1) и методом
`as_dict()`.

Низкоуровневые функции тоже доступны: `open_db`, `knn_by_vec`,
`text_search`, `fuzzy_search`, `image_to_data_url`.

Индексация новых строк:

```python
from emb_api import index_texts

index_texts(
    ["mod:id", "other_mod:some_item"],
    db_path="embeddings.db",
    client=client,
)
```

Повторный запуск не создаёт дублей.
