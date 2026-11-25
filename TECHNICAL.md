# Техническая документация

Здесь собрана техническая информация: CLI, Python API, схемы для LLM,
индексация и внутреннее устройство проекта. Для установки и запуска см.
[README.md](README.md).

## Устройство проекта

```
emb_api.py              библиотека поиска и клиент эмбеддингов
embedder.py             индексация иконок в embeddings.db
embed_search.py         интерактивный CLI-поиск
all_items.json          локальный каталог предметов
icon-exports-x32/       иконки 32×32 из IconExporter
embeddings.db           sqlite-vec база (создаётся локально)
package_windows.py      сборка переносимого Windows-архива
RecipeStudio/           GUI-редактор рецептов
  app.py                окно, горячие клавиши, связывание
  components/           слоты, сетка предметов, поиск, экспорт
  services/             каталог, иконки, имена, избранное, кодогенерация
  recipes/              модули рецептов (vanilla/ и create/)
  data/                 кэш имён и избранное (создаются по требованию)
  config.json           глобальные настройки (папка проектов, активный проект)
projects/               профили сборок (по JSON-файлу на сборку)
```

`RecipeStudio/services/search.py` — единственное место, которое импортирует
`emb_api` и открывает `embeddings.db`. Поэтому редактор можно перенести в
другой проект, изменив только профиль сборки.

## Конфигурация

### Глобальный `RecipeStudio/config.json`

| Ключ | Назначение |
| --- | --- |
| `projects_dir` | папка с профилями сборок (по умолчанию — каталог данных `platformdirs`) |
| `active_project` | путь к JSON-файлу активного проекта |
| `start_maximized` | запускать окно развёрнутым |

По умолчанию проекты и кэши лежат в каталоге данных пользователя
(`platformdirs.user_data_dir("recipe-studio")`):

- Linux: `~/.local/share/recipe-studio/projects`;
- Windows: `%LOCALAPPDATA%\recipe-studio\projects`;
- macOS: `~/Library/Application Support/recipe-studio/projects`.

`projects_dir` в `config.json` переопределяет это место: можно держать
профили рядом с модпаком или на переносимом диске.

Старый плоский `config.json` (с `icons_dir`, `database`, `mods_dir` и т.д.)
мигрирует автоматически: при первом запуске создаётся профиль `default` в
`projects_dir`, а из глобального файла убираются ключи проекта.

### Профиль проекта

`projects/<slug>.json` — один профиль сборки. Все пути **абсолютные**;
относительные значения из файлов, написанных вручную, считаются от папки
проекта.

| Ключ | Назначение |
| --- | --- |
| `schema` | версия формата (сейчас `1`) |
| `name` | отображаемое имя сборки |
| `items_json` | локальный каталог предметов |
| `icons_dir` | папка с иконками `modid__item_id.png` |
| `icon_manifest` | необязательный JSON с иконками |
| `database` | путь к `embeddings.db` |
| `base_url` | OpenAI-совместимый сервер эмбеддингов |
| `embedding_model` | имя модели |
| `mods_dir`, `kubejs_dir` | источники названий предметов |
| `extra_lang_jars` | дополнительные jar/zip с переводами |
| `recipe_sources` | папки и файлы для индексации рецептов |
| `auto_index` | индексировать `mods_dir`, `kubejs_dir` и `recipe_sources` при переключении |
| `favorites` | файл избранного (свой на проект) |
| `names_cache` | кэш отображаемых имён (свой на проект) |
| `search_limit` | максимум результатов поиска |
| `disabled_modules` | id отключённых модулей рецептов |
| `create_export_mode` | `addon` (нативные `event.recipes.create.*`) или `custom` (сырой JSON) |

`icon_manifest` — необязательный JSON-объект `id -> значение`, где значение:

- строка — путь к PNG (относительный путь считается от файла манифеста);
- объект `{"path": "icon.png"}` — путь к PNG;
- объект `{"data": "<base64>"}` — PNG в base64 (можно с префиксом `data:`);
- объект `{"path": ..., "kind": "fluid"}` — жидкость.

`items_json` принимает список id, список объектов `{"id", "path"|"data",
"kind"}` или объект `{"items": ...}`. Каталог объединяет манифест,
`items_json` и `icons_dir`; дубликаты схлопываются, иконка ищется в любом
источнике.

Кэши по умолчанию лежат в `.../recipe-studio/data/<slug>/`
(`favorites.json`, `names_cache.json`), поэтому разные сборки не смешивают
избранное и переводы.

Переключение сборки — выпадающий список **PROJECT** в верхней панели
(`New…`, `Edit…`, `Open…`). При смене проекта приложение отменяет текущую
индексацию, пересоздаёт каталог, иконки, имена, избранное и поиск, обновляет
`EditorContext` открытых редакторов на месте, очищает индекс рецептов и
запускает индексацию `recipe_sources` (если включён `auto_index`).

## CLI

```bash
python embed_search.py
```

Меню: векторный поиск по тексту, substring, fuzzy и векторный поиск по
картинке.

## Python API

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

## Схемы для LLM (schemafunc)

Методы поиска обёрнуты в `@add_schemafunc` и имеют Google-style docstrings,
поэтому из них автоматически генерируются OpenAI-совместимые tool-схемы.

Все четыре сразу:

```python
from emb_api import search_tool_schemas

tools = search_tool_schemas()
# response = llm.chat.completions.create(..., tools=tools)
```

Или по отдельности:

```python
SearchIndex.search_text.schemafunc.openai.schema       # JSON Schema
SearchIndex.search_text.schemafunc.openai_tool_kwargs  # tools + tool_choice
```

Схемы содержат описания параметров, значения по умолчанию и enum для `field`
(`mod` / `id` / `full`).

## Индексация новых строк

```python
from emb_api import index_texts

index_texts(
    ["mod:id", "other_mod:some_item"],
    db_path="embeddings.db",
    client=client,
)
```

Повторный запуск не создаёт дублей.

## Формат имён иконок

`embedder.py` и каталог понимают файлы `modid__item_id.png`:

- `addictives__big_vape__{'addictives__fluid_type'__'nicotine'}.png` —
  NBT/component-суффикс после `__{` отбрасывается;
- `fluid__modid__fluid_id.png` — жидкости индексируются отдельно;
- `fluid__baton.png` — предмет мода, который буквально называется `fluid`.

После обрезки NBT-суффикса коллизии схлопываются по полному `mod:id`, первая
запись выигрывает. Вектор строится по id предмета без префикса мода.

Колонки `embeddings.db`: `full` (PRIMARY KEY, `mod:id`), `mod`, `id`,
`embedding` (`FLOAT[N]`).

## Добавление нового типа рецепта

Создай файл в `RecipeStudio/recipes/` (например,
`recipes/create/pressing.py`):

```python
from RecipeStudio.recipes.base import RecipeEditor, RecipeModule


class PressingEditor(RecipeEditor):
    def serialize(self, event_var="event"):
        return f"{event_var}.custom({{ type: 'create:pressing', ingredients: [...], results: [...] }})"


class PressingModule(RecipeModule):
    id = "create.pressing"
    title = "Pressing"
    order = 200
    description = "Create mechanical press"

    def create_editor(self, parent, ctx):
        return PressingEditor(parent, ctx, self)


MODULE = PressingModule()
```

Модуль обнаруживается автоматически. Отключить можно, добавив его `id` в
`disabled_modules` профиля проекта (`projects/<slug>.json`).

Иконки вкладок принадлежат обработчику, а не общему каталогу предметов.
Положи маленький PNG рядом с модулем и укажи на него из класса:

```python
from pathlib import Path

icon = Path(__file__).with_name("icons") / "pressing.png"
```

Ванильные обработчики используют файлы в `recipes/vanilla/icons/`.

## Сборка Windows-архива

```bash
python package_windows.py                # только приложение
python package_windows.py --with-data    # приложение + embeddings.db + иконки
python package_windows.py --out C:\path\RecipeStudio-Windows.zip
```

Архив распаковывается в папку `RecipeStudio-Windows`; запуск —
`start_recipe_studio.bat`. Подробности в [WINDOWS.md](WINDOWS.md).
