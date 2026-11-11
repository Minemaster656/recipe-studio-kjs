# Recipe Studio

Визуальный редактор рецептов KubeJS для Minecraft 1.21.1 (KubeJS 2101).
Собирает рецепты мышкой и отдаёт готовый JS-код для `kubejs/server_scripts`.

Поддерживаются ванильные рецепты и Create: crafting, smelting, blasting,
smoking, campfire, stonecutting, smithing, compacting, milling, crushing,
cutting, deploying, emptying, filling, haunting, splashing, mixing, pressing,
sandpaper polishing, mechanical crafting и sequenced assembly.

## Как это работает

1. **Иконки.** Мод **IconExporter** выгружает иконки предметов в 32 пикселя в
   папку `icon-exports-x32`. Имена файлов имеют вид `modid__item_id.png`
   (жидкости — `fluid__modid__fluid_id.png`).
2. **Каталог.** Из этой папки строится палитра предметов: id, мод, иконка и
   отображаемое имя.
3. **Поиск.** В строке поиска доступны три режима:
   - `S` — substring по id;
   - `F` — fuzzy (опечатки);
   - `E` — семантический поиск по эмбеддингам, текстом или картинкой.
4. **Эмбеддинги.** `embeddings.db` — база sqlite-vec с векторами предметов.
   Для режима `E` нужен локальный OpenAI-совместимый сервер эмбеддингов.
   База хранит только векторы: запрос тоже превращается в вектор на сервере.
5. **Экспорт.** Кнопка копирует сгенерированный `event.custom({...})` (или
   `event.shaped` и т.п.) в буфер обмена.

## Что понадобится

- **Python 3.14** и [uv](https://docs.astral.sh/uv/).
- **Папка `icon-exports-x32`** — иконки, собранные модом IconExporter в 32 px.
  Без неё программа запустится, но палитра предметов будет пустой.
- **`embeddings.db`** — база векторов. Без неё работают режимы `S` и `F`,
  а `E` будет недоступен.
- **llama.cpp на порту 9931 с моделью `embeddinggemma2`** — желательно.
  Нужен только для режима `E`; без него `S`/`F` продолжают работать.

## Установка и запуск

### Linux / macOS

```bash
uv sync
uv run python -m RecipeStudio
```

Или готовый скрипт:

```bash
./start_recipe_studio.sh
```

### Windows

```bat
start_recipe_studio.bat
```

Скрипт сам поставит `uv`, Python и зависимости при первом запуске (нужен
интернет). Подробнее о переносимой сборке — в [WINDOWS.md](WINDOWS.md).

## Подготовка иконок

1. Установи мод **IconExporter** в модпак.
2. Выгрузи иконки предметов в размере **32×32**.
3. Положи полученную папку в корень проекта под именем `icon-exports-x32`.

Путь можно изменить в `RecipeStudio/config.json` → `icons_dir`. Папку нужно
класть целиком, не переименовывая файлы: из их имён строится каталог.

## Сервер эмбеддингов (режим `E`)

Достаточно любого OpenAI-совместимого embedding-сервера на
`http://127.0.0.1:9931/v1`. Рекомендуемый вариант — llama.cpp:

```bash
llama-server \
  --model embeddinggemma2.gguf \
  --embeddings \
  --mmproj mmproj.gguf \
  --host 127.0.0.1 \
  --port 9931
```

`--mmproj` нужен только для поиска по картинке. Адрес и имя модели задаются в
`RecipeStudio/config.json` (`base_url`, `embedding_model`).

## Сборка `embeddings.db`

Если базы ещё нет, её можно собрать из папки с иконками:

```bash
uv run python embedder.py
```

С параметрами по умолчанию: `icon-exports-x32` → `embeddings.db`,
сервер `http://localhost:9931/v1`, модель `embeddinggemma2`.

```bash
uv run python embedder.py icon-exports-x32 \
  -d embeddings.db \
  -u http://localhost:9931/v1 \
  -m embeddinggemma2
```

Повторный запуск не создаёт дублей — уже проиндексированные предметы
пропускаются.

## Техническая документация

- [TECHNICAL.md](TECHNICAL.md) — CLI, Python API, схемы для LLM, индексация,
  добавление новых типов рецептов и устройство проекта.
- [RecipeStudio/README.md](RecipeStudio/README.md) — горячие клавиши и приёмы
  работы в редакторе.
- [WINDOWS.md](WINDOWS.md) — сборка и запуск на Windows.
