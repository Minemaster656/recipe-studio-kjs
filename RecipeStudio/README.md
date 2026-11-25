# Recipe Studio

Небольшой десктопный редактор для сборки рецептов KubeJS
(Minecraft 1.21.1, KubeJS 2101).

## Запуск

```bash
cd /home/minemaster/.local/share/PrismLauncher/instances/Kindur-II-DEV-III/minecraft/scripts
uv run python -m RecipeStudio
```

`uv run` сам поставит зависимости (включая Pillow). Если окружение уже
подготовлено, достаточно `uv sync`, затем `uv run …`.

Общая инструкция по установке, иконкам и серверу эмбеддингов — в
[../README.md](../README.md). Технические детали и добавление новых типов
рецептов — в [../TECHNICAL.md](../TECHNICAL.md).

## Проекты (сборки)

Сборки переключаются списком **PROJECT** в верхней панели. Каждая сборка —
JSON-профиль в каталоге данных пользователя
(`~/.local/share/recipe-studio/projects/<slug>.json`): каталог предметов,
иконки, база эмбеддингов, `mods`/`kubejs`, избранное и кэш имён. `New…`
создаёт профиль, `Edit…` меняет пути, `Open…` открывает готовый JSON. При
переключении палитра, переводы, избранное и индекс рецептов пересоздаются;
`mods`, `kubejs` и `recipe_sources` индексируются в фоне (`auto_index`).

## Горячие клавиши

| Клавиша | Действие |
| --- | --- |
| `Ctrl+F` | Фокус в поиск; повторное нажатие возвращает к сетке |
| `Ctrl+Shift+F` | Переключить режим поиска `S` → `F` → `E` |
| `Ctrl+Backspace` | Удалить предыдущее слово в поиске |
| `Ctrl+Delete` | Удалить следующее слово в поиске |
| `Ctrl+E` | Скопировать рецепт |
| `Ctrl+Shift+E` | Скопировать рецепт со строкой удаления исходного рецепта |
| `Ctrl+A` | Показать только избранное (когда ввод не в фокусе) |
| `A` | Добавить/убрать предмет из избранного под курсором |
| `+` / `-` | Изменить количество в слоте под курсором |
| `Esc` | Выйти из поиска / снять выделение / выйти из избранного |

Кнопка `★` рядом со счётчиком палитры тоже включает режим «только
избранное», так что его можно выключить без клавиатуры.

Средний клик по заполненному слоту берёт ингредиент (пипетка), левый клик по
другому слоту вставляет его. Количества, объёмы жидкостей, шансы, NBT и теги
сохраняются; `Esc` отменяет выбор.

## Поиск

Режимы: `S` — substring, `F` — fuzzy, `E` — эмбеддинги (текст или путь к
картинке). `S` и `F` работают по локальному каталогу, даже если векторная база
недоступна.

Слоты жидкостей принимают bucket-предметы NeoForge из палитры (например,
`minecraft:water_bucket`) и хранят/экспортируют id жидкости без суффикса
(`minecraft:water`). Векторная база индексирует bucket-предметы, а не id
жидкостей.

## Create: addon или custom

В панели **EXPORT** есть переключатель `Create: addon / custom`:

- `addon` — нативные вызовы KubeJS Create (`event.recipes.create.crushing(...)`);
- `custom` — сырой JSON (`event.custom({ "type": "create:crushing", ... })`),
  как в рецептах самого мода.

Режим сохраняется в профиле проекта (`create_export_mode`) и применяется ко
всем create-редакторам: compacting, crushing, cutting, deploying, emptying,
filling, haunting, mechanical crafting, mixing, milling, pressing, sandpaper,
sequenced assembly, splashing.

## Включённые модули

Ванильные: Crafting (shaped/shapeless), Smelting, Blasting, Smoking, Campfire
Cooking, Stonecutting, Smithing.

Create: Compacting, Milling, Crushing, Cutting, Deploying, Emptying, Filling,
Haunting, Splashing, Mixing, Pressing, Sandpaper Polishing, Mechanical
Crafting (до 9×9), Sequenced Assembly.
