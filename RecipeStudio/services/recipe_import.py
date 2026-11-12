"""Import recipes from KubeJS or vanilla datapack JSON.

The importer is deliberately independent from the GUI: it turns a text blob
into an :class:`ImportedRecipe` with a module id and a state dict that the
matching editor can apply through ``set_state``.

Supported inputs
----------------
* vanilla datapack JSON (``minecraft:*`` recipe types);
* KubeJS ``event.custom({...})`` with a recipe object;
* native KubeJS calls such as ``event.shaped(...)``, ``event.smelting(...)``,
  ``event.stonecutting(...)``, ``event.smithing(...)`` and the Create helpers
  ``event.recipes.create.<type>(...)``.

Anything unsupported raises :class:`RecipeImportError` with a readable
message.  The GUI catches that exception and shows it in the status bar instead
of letting it crash the editor.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from RecipeStudio.model.ingredient import Ingredient, normalize_fluid_id


class RecipeImportError(ValueError):
    """Raised when the text cannot be recognised as a supported recipe."""


@dataclass
class ImportedRecipe:
    module_id: str
    state: dict
    format: str
    warnings: list[str] = field(default_factory=list)


# ============================================================== JS parser ==


@dataclass(frozen=True)
class _Token:
    kind: str  # "ident" | "string" | "number" | "punct"
    value: Any
    pos: int


@dataclass(frozen=True)
class _Ref:
    parts: tuple[str, ...]


@dataclass(frozen=True)
class _Member:
    obj: Any
    name: str


@dataclass(frozen=True)
class _Call:
    func: Any
    args: list[Any]


def _decode_escape(text: str, index: int) -> tuple[str, int]:
    """Decode one JS escape starting after a backslash."""
    if index >= len(text):
        return "", index
    ch = text[index]
    simple = {
        "n": "\n",
        "r": "\r",
        "t": "\t",
        "b": "\b",
        "f": "\f",
        "v": "\v",
        "0": "\0",
        "'": "'",
        '"': '"',
        "\\": "\\",
        "/": "/",
    }
    if ch in simple:
        return simple[ch], index + 1
    if ch == "u":
        raw = text[index + 1 : index + 5]
        try:
            return chr(int(raw, 16)), index + 5
        except ValueError:
            return "u", index + 1
    if ch == "x":
        raw = text[index + 1 : index + 3]
        try:
            return chr(int(raw, 16)), index + 3
        except ValueError:
            return "x", index + 1
    return ch, index + 1


def _tokenize(text: str) -> list[_Token]:
    tokens: list[_Token] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        # Comments. These are common in KubeJS scripts.
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            i += 2
            while i < n and text[i] not in "\r\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            start = i
            i += 1
            out: list[str] = []
            while i < n:
                c = text[i]
                if c == "\\":
                    value, i = _decode_escape(text, i + 1)
                    out.append(value)
                    continue
                if c == quote:
                    i += 1
                    break
                out.append(c)
                i += 1
            tokens.append(_Token("string", "".join(out), start))
            continue
        if ch.isdigit() or (ch == "." and i + 1 < n and text[i + 1].isdigit()):
            start = i
            if ch == "0" and i + 1 < n and text[i + 1] in "xX":
                i += 2
                while i < n and text[i].lower() in "0123456789abcdef":
                    i += 1
                raw = text[start:i]
                try:
                    tokens.append(_Token("number", int(raw, 16), start))
                except ValueError:
                    tokens.append(_Token("number", 0, start))
                continue
            while i < n and (text[i].isdigit() or text[i] in ".eE+-"):
                # A sign is only part of a number after an exponent marker.
                if text[i] in "+-" and text[i - 1] not in "eE":
                    break
                i += 1
            raw = text[start:i]
            try:
                value = float(raw) if any(c in raw for c in ".eE") else int(raw)
            except ValueError:
                value = 0
            tokens.append(_Token("number", value, start))
            continue
        if ch.isalpha() or ch in "_$":
            start = i
            i += 1
            while i < n and (text[i].isalnum() or text[i] in "_$"):
                i += 1
            tokens.append(_Token("ident", text[start:i], start))
            continue
        # Multi-character punctuation we care about.
        for punct in ("=>", "...", "==", "!=", "&&", "||"):
            if text.startswith(punct, i):
                tokens.append(_Token("punct", punct, i))
                i += len(punct)
                break
        else:
            tokens.append(_Token("punct", ch, i))
            i += 1
    return tokens


class _JSParser:
    def __init__(self, tokens: list[_Token]):
        self.tokens = tokens
        self.i = 0

    def eof(self) -> bool:
        return self.i >= len(self.tokens)

    def peek(self, offset: int = 0) -> _Token | None:
        pos = self.i + offset
        return self.tokens[pos] if 0 <= pos < len(self.tokens) else None

    def take(self) -> _Token:
        token = self.peek()
        if token is None:
            raise RecipeImportError("Неожиданный конец KubeJS-кода")
        self.i += 1
        return token

    def at(self, value: str) -> bool:
        token = self.peek()
        return token is not None and token.value == value

    def expect(self, value: str) -> _Token:
        token = self.take()
        if token.value != value:
            raise RecipeImportError(
                f"Ожидался {value!r}, а найден {token.value!r} (позиция {token.pos})"
            )
        return token

    def parse_expression(self) -> Any:
        return self.parse_postfix()

    def parse_postfix(self) -> Any:
        expr = self.parse_primary()
        while True:
            if self.at("."):
                self.take()
                name = self.take()
                if name.kind != "ident":
                    raise RecipeImportError(f"Ожидалось имя поля, а не {name.value!r}")
                expr = _Member(expr, name.value)
            elif self.at("("):
                expr = _Call(expr, self.parse_arguments())
            else:
                return expr

    def parse_primary(self) -> Any:
        token = self.take()
        if token.kind == "string":
            return token.value
        if token.kind == "number":
            return token.value
        if token.kind == "ident":
            if token.value == "true":
                return True
            if token.value == "false":
                return False
            if token.value in ("null", "undefined"):
                return None
            if token.value == "new":
                # ``new ItemStack(...)`` is not used in normal KubeJS recipes,
                # but handling the keyword makes the parser less brittle.
                return self.parse_postfix()
            return _Ref((token.value,))
        if token.value == "-":
            value = self.parse_primary()
            if isinstance(value, (int, float)):
                return -value
            raise RecipeImportError("Унарный минус перед нечисловым значением")
        if token.value == "{":
            return self.parse_object()
        if token.value == "[":
            return self.parse_array()
        if token.value == "(":
            expr = self.parse_expression()
            self.expect(")")
            return expr
        raise RecipeImportError(
            f"Неожиданный токен {token.value!r} (позиция {token.pos})"
        )

    def parse_object(self) -> dict:
        result: dict = {}
        while True:
            if self.at("}"):
                self.take()
                return result
            if self.at("..."):
                self.take()
                value = self.parse_expression()
                if isinstance(value, dict):
                    result.update(value)
                if self.at(","):
                    self.take()
                continue
            token = self.take()
            if token.kind not in ("ident", "string", "number"):
                raise RecipeImportError(
                    f"Неожиданный ключ объекта {token.value!r} (позиция {token.pos})"
                )
            key = str(token.value)
            self.expect(":")
            result[key] = self.parse_expression()
            if self.at(","):
                self.take()
            elif not self.at("}"):
                raise RecipeImportError(
                    f"Ожидалась запятая или }}, а найден {self.peek().value!r}"
                )

    def parse_array(self) -> list:
        result: list = []
        while True:
            if self.at("]"):
                self.take()
                return result
            if self.at("..."):
                self.take()
                value = self.parse_expression()
                if isinstance(value, list):
                    result.extend(value)
                else:
                    result.append(value)
            else:
                result.append(self.parse_expression())
            if self.at(","):
                self.take()
            elif not self.at("]"):
                raise RecipeImportError(
                    f"Ожидалась запятая или ], а найден {self.peek().value!r}"
                )

    def parse_arguments(self) -> list:
        self.expect("(")
        result: list = []
        while True:
            if self.at(")"):
                self.take()
                return result
            result.append(self.parse_expression())
            if self.at(","):
                self.take()
            elif not self.at(")"):
                raise RecipeImportError(
                    f"Ожидалась запятая или ), а найден {self.peek().value!r}"
                )


def _path(expr: Any) -> str | None:
    if isinstance(expr, _Ref):
        return ".".join(expr.parts)
    if isinstance(expr, _Member):
        base = _path(expr.obj)
        return f"{base}.{expr.name}" if base else None
    return None


def _decompose_chain(
    call: _Call,
) -> tuple[str | None, list[Any], list[tuple[str, list[Any]]]]:
    """Return ``(base path, base args, chained methods)`` for a call."""
    methods: list[tuple[str, list[Any]]] = []
    current = call
    while (
        isinstance(current, _Call)
        and isinstance(current.func, _Member)
        and isinstance(current.func.obj, _Call)
    ):
        methods.append((current.func.name, current.args))
        current = current.func.obj
    return _path(current.func), current.args, list(reversed(methods))


def _find_event_calls(text: str) -> list[_Call]:
    parser = _JSParser(_tokenize(text))
    calls: list[_Call] = []
    while not parser.eof():
        token = parser.peek()
        if token is not None and token.kind == "ident" and token.value == "event":
            saved = parser.i
            try:
                expr = parser.parse_expression()
            except RecipeImportError:
                parser.i = saved + 1
                continue
            if isinstance(expr, _Call):
                calls.append(expr)
            continue
        parser.take()
    return calls


# ========================================================= ingredient glue ==


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _number(value: Any, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except TypeError, ValueError:
        return default


def _int(value: Any, default: int | None = None) -> int | None:
    number = _number(value)
    return int(number) if number is not None else default


def _string(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, _Ref):
        return ".".join(value.parts)
    return "" if value is None else str(value).strip()


def _parse_stack_string(text: str) -> tuple[str, int]:
    match = re.match(r"^\s*(\d+)\s*[xX]\s+(.+?)\s*$", text)
    if match:
        return match.group(2), int(match.group(1))
    return text.strip(), 1


def _ingredient_from_string(value: str, *, output: bool = False) -> Ingredient:
    text, count = _parse_stack_string(value)
    if not text:
        return Ingredient()
    if text.startswith("#"):
        return Ingredient(kind="tag", id=text.lstrip("#"), count=count if output else 1)
    return Ingredient(kind="item", id=text, count=count if output else 1)


def _ingredient_from_dict(
    data: dict, *, output: bool = False, warnings: list[str] | None = None
) -> Ingredient:
    if not data:
        return Ingredient()
    if "kind" in data and "id" in data:
        return Ingredient.from_dict(data)

    # Recipe types that wrap the actual ingredient in a nested object.
    for key in ("ingredient", "input", "result", "value"):
        if key in data and (len(data) == 1 or (len(data) == 2 and "type" in data)):
            return _to_ingredient(
                data[key], output=output or key == "result", warnings=warnings
            )

    count = _int(data.get("count", data.get("Count", 1)), 1) or 1
    amount = _int(data.get("amount", data.get("Amount")), None)
    chance = _number(data.get("chance", data.get("Chance")), None)

    rtype = str(data.get("type", "")).lower()
    if "tag" in data:
        value = data["tag"]
        if isinstance(value, dict):
            value = value.get("id", value.get("tag", ""))
        return Ingredient(
            kind="tag", id=_string(value).lstrip("#"), count=count, chance=chance
        )
    if "fluid" in data:
        value = data["fluid"]
        if isinstance(value, dict):
            value = value.get("id", value.get("fluid", ""))
        return Ingredient(
            kind="fluid",
            id=normalize_fluid_id(_string(value)),
            amount=amount or 1000,
            chance=chance,
        )
    if "item" in data:
        value = data["item"]
        if isinstance(value, dict):
            value = value.get("id", value.get("item", ""))
        return Ingredient(kind="item", id=_string(value), count=count, chance=chance)
    if "id" in data:
        kind = "fluid" if amount is not None or "fluid" in rtype else "item"
        return Ingredient(
            kind=kind,
            id=normalize_fluid_id(_string(data["id"]))
            if kind == "fluid"
            else _string(data["id"]),
            count=count,
            amount=amount,
            chance=chance,
        )
    raise RecipeImportError(f"Не удалось разобрать ингредиент: {data!r}")


def _ingredient_from_call(
    call: _Call, *, output: bool = False, warnings: list[str] | None = None
) -> Ingredient:
    methods: list[tuple[str, list[Any]]] = []
    current = call
    while (
        isinstance(current, _Call)
        and isinstance(current.func, _Member)
        and isinstance(current.func.obj, _Call)
    ):
        methods.append((current.func.name, current.args))
        current = current.func.obj

    path = _path(current.func) or ""
    args = current.args
    if not args:
        raise RecipeImportError(f"Пустой вызов ингредиента: {path}")

    head = _string(args[0])
    tail = args[1:]
    if path.endswith(("Fluid.of", "FluidStack", "FluidStack.of")):
        amount = _int(tail[0], 1000) if tail else 1000
        ingredient = Ingredient(
            kind="fluid", id=normalize_fluid_id(head), amount=amount or 1000
        )
    else:
        ingredient = _ingredient_from_string(head, output=output)
        if output and tail:
            second = tail[0]
            if isinstance(second, (int, float)):
                if "CreateItem" in path:
                    ingredient.chance = float(second)
                    if len(tail) > 1 and isinstance(tail[1], str):
                        ingredient.nbt = tail[1]
                else:
                    ingredient.count = max(1, int(second))
                    if len(tail) > 1 and isinstance(tail[1], str):
                        ingredient.nbt = tail[1]
            elif isinstance(second, str):
                # ``Item.of('id', '{nbt}')``
                if second.startswith("{"):
                    ingredient.nbt = second
                else:
                    extra_count = _int(second, None)
                    if extra_count is not None:
                        ingredient.count = max(1, extra_count)
        elif not output and tail:
            # ``Ingredient.of('id', 2)`` / ``Item.of('id', 2)`` as an input.
            if isinstance(tail[0], (int, float)):
                ingredient.count = max(1, int(tail[0]))

    for name, margs in reversed(methods):
        low = name.lower()
        if low == "withchance" and margs:
            ingredient.chance = _number(margs[0])
        elif low == "withcount" and margs:
            ingredient.count = max(1, _int(margs[0], 1) or 1)
        elif low == "withnbt" and margs:
            ingredient.nbt = _string(margs[0])
    return ingredient


def _to_ingredient(
    value: Any, *, output: bool = False, warnings: list[str] | None = None
) -> Ingredient:
    if isinstance(value, Ingredient):
        return value.copy()
    if isinstance(value, dict):
        return _ingredient_from_dict(value, output=output, warnings=warnings)
    if isinstance(value, _Call):
        return _ingredient_from_call(value, output=output, warnings=warnings)
    if isinstance(value, (list, tuple)):
        values = list(value)
        if not values:
            return Ingredient()
        if len(values) > 1 and warnings is not None:
            warnings.append("В списке альтернатив выбрана первая")
        return _to_ingredient(values[0], output=output, warnings=warnings)
    if isinstance(value, str):
        return _ingredient_from_string(value, output=output)
    if value is None:
        return Ingredient()
    raise RecipeImportError(f"Не удалось разобрать ингредиент: {value!r}")


def _ingredient_dict(
    value: Any, *, output: bool = False, warnings: list[str] | None = None
) -> dict:
    return _to_ingredient(value, output=output, warnings=warnings).to_dict()


def _ingredient_dicts(
    value: Any, *, output: bool = False, warnings: list[str] | None = None
) -> list[dict]:
    return [
        _ingredient_dict(item, output=output, warnings=warnings)
        for item in _as_list(value)
        if not _to_ingredient(item, output=output, warnings=warnings).is_empty
    ]


def _split_fluids(
    values: Any, *, output: bool = False, warnings: list[str] | None = None
) -> tuple[list[dict], list[dict]]:
    items: list[dict] = []
    fluids: list[dict] = []
    for item in _as_list(values):
        ing = _to_ingredient(item, output=output, warnings=warnings)
        if ing.is_empty:
            continue
        (fluids if ing.kind == "fluid" else items).append(ing.to_dict())
    return items, fluids


# ============================================================== conversion ==


_VANILLA_TYPES = {
    "crafting_shaped": "vanilla.crafting",
    "crafting_shapeless": "vanilla.crafting",
    "smelting": "vanilla.smelting",
    "blasting": "vanilla.blasting",
    "smoking": "vanilla.smoking",
    "campfire_cooking": "vanilla.campfire",
    "stonecutting": "vanilla.stonecutting",
    "smithing_transform": "vanilla.smithing",
    "smithing": "vanilla.smithing",
}

_CREATE_TYPES = {
    "crushing": "create.crushing",
    "cutting": "create.cutting",
    "milling": "create.milling",
    "pressing": "create.pressing",
    "sandpaper_polishing": "create.sandpaper",
    "splashing": "create.splashing",
    "haunting": "create.haunting",
    "compacting": "create.compacting",
    "mixing": "create.mixing",
    "filling": "create.filling",
    "emptying": "create.emptying",
    "deploying": "create.deploying",
    "mechanical_crafting": "create.mechanical_crafting",
    "sequenced_assembly": "create.sequenced_assembly",
}

_CREATE_SIMPLE = {
    "create.crushing",
    "create.cutting",
    "create.milling",
    "create.pressing",
    "create.sandpaper",
    "create.splashing",
    "create.haunting",
}


def _normalise_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


_CREATE_NATIVE_TYPES = {
    _normalise_name(key): value for key, value in _CREATE_TYPES.items()
}


def _module_for_type(recipe_type: str) -> str | None:
    if ":" not in recipe_type:
        return None
    namespace, name = recipe_type.split(":", 1)
    if namespace == "minecraft":
        return _VANILLA_TYPES.get(name)
    if namespace == "create":
        return _CREATE_TYPES.get(name)
    return None


def _empty_grid(rows: int = 3, cols: int = 3) -> list[list[dict]]:
    return [[Ingredient().to_dict() for _ in range(cols)] for _ in range(rows)]


def _crafting_from_json(data: dict, warnings: list[str]) -> ImportedRecipe:
    result = _ingredient_dict(
        data.get("result", data.get("output")), output=True, warnings=warnings
    )
    if not result.get("id"):
        raise RecipeImportError("В рецепте крафта нет результата")

    if "pattern" in data:
        pattern = data.get("pattern") or []
        if isinstance(pattern, str):
            pattern = pattern.splitlines()
        keys = data.get("key") or {}
        if not isinstance(keys, dict):
            raise RecipeImportError("Поле 'key' должно быть объектом")
        if len(pattern) > 3 or any(len(str(row)) > 3 for row in pattern):
            raise RecipeImportError(
                "Сетка крафта больше 3×3 — этот редактор её не поддерживает"
            )
        grid = _empty_grid()
        for r, row in enumerate(pattern):
            for c, char in enumerate(str(row)):
                if char == " ":
                    continue
                if char not in keys:
                    raise RecipeImportError(f"В 'key' нет символа {char!r}")
                grid[r][c] = _ingredient_dict(keys[char], warnings=warnings)
        return ImportedRecipe(
            "vanilla.crafting",
            {"shapeless": False, "inputs": grid, "output": result},
            "vanilla JSON",
            warnings,
        )

    ingredients = data.get("ingredients")
    if ingredients is None:
        raise RecipeImportError("В рецепте крафта нет pattern/ingredients")
    flat = [_ingredient_dict(v, warnings=warnings) for v in _as_list(ingredients)]
    flat = [v for v in flat if v.get("id")]
    if len(flat) > 9:
        raise RecipeImportError("Бесформенный крафт содержит больше 9 ингредиентов")
    grid = _empty_grid()
    for index, ing in enumerate(flat):
        grid[index // 3][index % 3] = ing
    return ImportedRecipe(
        "vanilla.crafting",
        {"shapeless": True, "inputs": grid, "output": result},
        "vanilla JSON",
        warnings,
    )


def _cooking_from_json(
    data: dict, module_id: str, warnings: list[str]
) -> ImportedRecipe:
    ingredient = data.get("ingredient", data.get("input"))
    result = data.get("result", data.get("output"))
    if ingredient is None or result is None:
        raise RecipeImportError("В рецепте приготовления нет ingredient/result")
    return ImportedRecipe(
        module_id,
        {
            "input": _ingredient_dict(ingredient, warnings=warnings),
            "output": _ingredient_dict(result, output=True, warnings=warnings),
            "ticks": _int(
                data.get("cookingtime", data.get("cooking_time", data.get("time")))
            ),
            "xp": _number(data.get("experience", data.get("xp"))),
        },
        "vanilla JSON",
        warnings,
    )


def _stonecutting_from_json(data: dict, warnings: list[str]) -> ImportedRecipe:
    ingredient = data.get("ingredient", data.get("input"))
    result = data.get("result", data.get("output"))
    if ingredient is None or result is None:
        raise RecipeImportError("В stonecutting-рецепте нет ingredient/result")
    return ImportedRecipe(
        "vanilla.stonecutting",
        {
            "input": _ingredient_dict(ingredient, warnings=warnings),
            "output": _ingredient_dict(result, output=True, warnings=warnings),
        },
        "vanilla JSON",
        warnings,
    )


def _smithing_from_json(data: dict, warnings: list[str]) -> ImportedRecipe:
    template = data.get("template")
    if template is None:
        warnings.append("В рецепте нет template — поле останется пустым")
        template = Ingredient().to_dict()
    else:
        template = _ingredient_dict(template, warnings=warnings)
    return ImportedRecipe(
        "vanilla.smithing",
        {
            "template": template,
            "base": _ingredient_dict(data.get("base"), warnings=warnings),
            "addition": _ingredient_dict(data.get("addition"), warnings=warnings),
            "output": _ingredient_dict(
                data.get("result", data.get("output")), output=True, warnings=warnings
            ),
        },
        "vanilla JSON",
        warnings,
    )


def _heat_from_json(data: dict) -> str | None:
    value = data.get("heat_requirement", data.get("heatRequirement"))
    return str(value) if value else None


def _simple_create_from_json(
    data: dict, module_id: str, warnings: list[str]
) -> ImportedRecipe:
    return ImportedRecipe(
        module_id,
        {
            "inputs": _ingredient_dicts(data.get("ingredients"), warnings=warnings),
            "outputs": _ingredient_dicts(
                data.get("results", data.get("result")), output=True, warnings=warnings
            ),
            "processing_time": _int(
                data.get("processing_time", data.get("processingTime"))
            ),
        },
        "KubeJS JSON",
        warnings,
    )


def _compacting_from_json(data: dict, warnings: list[str]) -> ImportedRecipe:
    items, fluids = _split_fluids(data.get("ingredients"), warnings=warnings)
    return ImportedRecipe(
        "create.compacting",
        {
            "item_inputs": items,
            "fluid_inputs": fluids,
            "outputs": _ingredient_dicts(
                data.get("results", data.get("result")), output=True, warnings=warnings
            ),
            "heat_requirement": _heat_from_json(data),
        },
        "KubeJS JSON",
        warnings,
    )


def _mixing_from_json(data: dict, warnings: list[str]) -> ImportedRecipe:
    item_inputs, fluid_inputs = _split_fluids(
        data.get("ingredients"), warnings=warnings
    )
    item_outputs, fluid_outputs = _split_fluids(
        data.get("results", data.get("result")), output=True, warnings=warnings
    )
    return ImportedRecipe(
        "create.mixing",
        {
            "item_inputs": item_inputs,
            "fluid_inputs": fluid_inputs,
            "item_outputs": item_outputs,
            "fluid_outputs": fluid_outputs,
            "heat_requirement": _heat_from_json(data),
        },
        "KubeJS JSON",
        warnings,
    )


def _filling_from_json(data: dict, warnings: list[str]) -> ImportedRecipe:
    ingredients = _as_list(data.get("ingredients"))
    item_input = Ingredient().to_dict()
    fluid_input = Ingredient().to_dict()
    for raw in ingredients:
        ing = _to_ingredient(raw, warnings=warnings)
        if ing.kind == "fluid" and not fluid_input.get("id"):
            fluid_input = ing.to_dict()
        elif ing.kind != "fluid" and not item_input.get("id"):
            item_input = ing.to_dict()
    outputs = _ingredient_dicts(
        data.get("results", data.get("result")), output=True, warnings=warnings
    )
    return ImportedRecipe(
        "create.filling",
        {
            "item_input": item_input,
            "fluid_input": fluid_input,
            "amount": _int(fluid_input.get("amount"), 1000) or 1000,
            "output": outputs[0] if outputs else Ingredient().to_dict(),
        },
        "KubeJS JSON",
        warnings,
    )


def _emptying_from_json(data: dict, warnings: list[str]) -> ImportedRecipe:
    inputs = _as_list(data.get("ingredients"))
    item_outputs, fluid_outputs = _split_fluids(
        data.get("results", data.get("result")), output=True, warnings=warnings
    )
    fluid_output = fluid_outputs[0] if fluid_outputs else Ingredient().to_dict()
    return ImportedRecipe(
        "create.emptying",
        {
            "input": _ingredient_dict(inputs[0], warnings=warnings)
            if inputs
            else Ingredient().to_dict(),
            "item_output": item_outputs[0] if item_outputs else Ingredient().to_dict(),
            "fluid_output": fluid_output,
            "amount": _int(fluid_output.get("amount"), 1000) or 1000,
        },
        "KubeJS JSON",
        warnings,
    )


def _deploying_from_json(data: dict, warnings: list[str]) -> ImportedRecipe:
    inputs = _as_list(data.get("ingredients"))
    depot = (
        _ingredient_dict(inputs[0], warnings=warnings)
        if inputs
        else Ingredient().to_dict()
    )
    held = (
        _ingredient_dict(inputs[1], warnings=warnings)
        if len(inputs) > 1
        else Ingredient().to_dict()
    )
    keep = bool(data.get("keep_held_item", data.get("keepHeldItem", False)))
    return ImportedRecipe(
        "create.deploying",
        {
            "depot": depot,
            "held": held,
            "outputs": _ingredient_dicts(
                data.get("results", data.get("result")), output=True, warnings=warnings
            ),
            "keep_held": keep,
        },
        "KubeJS JSON",
        warnings,
    )


def _grid_from_pattern(
    pattern: list, keys: dict, warnings: list[str]
) -> tuple[int, int, list[list[dict]]]:
    rows = len(pattern)
    if rows == 0:
        raise RecipeImportError("Пустой pattern")
    cols = max(len(str(row)) for row in pattern)
    if rows > 9 or cols > 9:
        raise RecipeImportError("Сетка больше 9×9 — этот редактор её не поддерживает")
    grid = _empty_grid(rows, cols)
    for r, row in enumerate(pattern):
        for c, char in enumerate(str(row)):
            if char == " ":
                continue
            if char not in keys:
                raise RecipeImportError(f"В 'key' нет символа {char!r}")
            grid[r][c] = _ingredient_dict(keys[char], warnings=warnings)
    return rows, cols, grid


def _mechanical_from_json(data: dict, warnings: list[str]) -> ImportedRecipe:
    pattern = data.get("pattern") or []
    if isinstance(pattern, str):
        pattern = pattern.splitlines()
    keys = data.get("key") or {}
    rows, cols, grid = _grid_from_pattern(pattern, keys, warnings)
    output = data.get("result")
    if output is None:
        results = _as_list(data.get("results"))
        output = results[0] if results else None
    return ImportedRecipe(
        "create.mechanical_crafting",
        {
            "rows": rows,
            "cols": cols,
            "grid": grid,
            "output": _ingredient_dict(output, output=True, warnings=warnings),
        },
        "KubeJS JSON",
        warnings,
    )


def _step_kind(recipe_type: str) -> str | None:
    name = _normalise_name(recipe_type.split(":", 1)[-1])
    return {
        "pressing": "Pressing",
        "cutting": "Cutting",
        "deploying": "Deploying",
        "filling": "Filling",
    }.get(name)


def _sequenced_from_json(data: dict, warnings: list[str]) -> ImportedRecipe:
    sequence = _as_list(data.get("sequence"))
    steps = []
    for index, step in enumerate(sequence, start=1):
        if not isinstance(step, dict):
            raise RecipeImportError(f"Шаг {index} не является объектом рецепта")
        rtype = str(step.get("type", ""))
        kind = _step_kind(rtype)
        if kind is None:
            raise RecipeImportError(f"Шаг {index}: неподдерживаемый тип {rtype!r}")
        ingredients = _as_list(step.get("ingredients"))
        item = None
        fluid = None
        if kind == "Deploying" and len(ingredients) > 1:
            item = _ingredient_dict(ingredients[1], warnings=warnings)
        elif kind == "Filling" and len(ingredients) > 1:
            fluid = _ingredient_dict(ingredients[1], warnings=warnings)
        steps.append({"type": kind, "item": item, "fluid": fluid})

    return ImportedRecipe(
        "create.sequenced_assembly",
        {
            "start": _ingredient_dict(
                data.get("ingredient", data.get("input")), warnings=warnings
            ),
            "transitional": _ingredient_dict(
                data.get("transitional_item", data.get("transitionalItem")),
                warnings=warnings,
            ),
            "steps": steps,
            "results": _ingredient_dicts(
                data.get("results", data.get("result")), output=True, warnings=warnings
            ),
            "scrap": [],
            "loops": _int(data.get("loops"), 1) or 1,
        },
        "KubeJS JSON",
        warnings,
    )


def _create_from_json(
    data: dict, name: str, module_id: str, warnings: list[str]
) -> ImportedRecipe:
    if module_id in _CREATE_SIMPLE:
        return _simple_create_from_json(data, module_id, warnings)
    if name == "compacting":
        return _compacting_from_json(data, warnings)
    if name == "mixing":
        return _mixing_from_json(data, warnings)
    if name == "filling":
        return _filling_from_json(data, warnings)
    if name == "emptying":
        return _emptying_from_json(data, warnings)
    if name == "deploying":
        return _deploying_from_json(data, warnings)
    if name == "mechanical_crafting":
        return _mechanical_from_json(data, warnings)
    if name == "sequenced_assembly":
        return _sequenced_from_json(data, warnings)
    raise RecipeImportError(f"Неподдерживаемый тип Create: {name!r}")


def _from_json(data: Any, fmt: str = "JSON") -> ImportedRecipe:
    warnings: list[str] = []
    if isinstance(data, list):
        candidates = [item for item in data if isinstance(item, dict)]
        if not candidates:
            raise RecipeImportError("JSON-массив не содержит объектов рецептов")
        if len(candidates) > 1:
            warnings.append("Найдено несколько рецептов; импортирован первый")
        data = candidates[0]
    if not isinstance(data, dict):
        raise RecipeImportError("JSON-рецепт должен быть объектом")

    recipe_type = str(data.get("type", "")).strip()
    if not recipe_type:
        raise RecipeImportError("В JSON-рецепте нет поля 'type'")
    module_id = _module_for_type(recipe_type)
    if module_id is None:
        raise RecipeImportError(f"Неподдерживаемый тип рецепта: {recipe_type!r}")

    if recipe_type.startswith("minecraft:"):
        name = recipe_type.split(":", 1)[1]
        if name in ("crafting_shaped", "crafting_shapeless"):
            recipe = _crafting_from_json(data, warnings)
        elif name in ("smelting", "blasting", "smoking", "campfire_cooking"):
            recipe = _cooking_from_json(data, module_id, warnings)
        elif name == "stonecutting":
            recipe = _stonecutting_from_json(data, warnings)
        elif name in ("smithing", "smithing_transform"):
            recipe = _smithing_from_json(data, warnings)
        else:
            raise RecipeImportError(f"Неподдерживаемый ванильный тип: {recipe_type!r}")
    else:
        name = recipe_type.split(":", 1)[1]
        recipe = _create_from_json(data, name, module_id, warnings)
    recipe.format = fmt
    return recipe


# ============================================================ native calls ==


def _method_value(methods: list[tuple[str, list[Any]]], *names: str) -> Any:
    wanted = {_normalise_name(name) for name in names}
    for name, args in methods:
        if _normalise_name(name) in wanted and args:
            return args[0]
    return None


def _heat_from_methods(
    methods: list[tuple[str, list[Any]]], extra: Any = None
) -> str | None:
    for name, _args in methods:
        low = _normalise_name(name)
        if low == "heated":
            return "heated"
        if low == "superheated":
            return "superheated"
    value = _method_value(methods, "heatRequirement", "heat_requirement")
    if value is not None:
        return _string(value)
    if isinstance(extra, str) and extra:
        return extra
    if isinstance(extra, dict):
        return _heat_from_json(extra)
    return None


def _crafting_from_call(
    path: str, args: list[Any], warnings: list[str]
) -> ImportedRecipe:
    if not args:
        raise RecipeImportError("Вызов крафта без аргументов")
    output = _ingredient_dict(args[0], output=True, warnings=warnings)
    if path.endswith("shapeless"):
        if len(args) > 2:
            values = args[1:]
        else:
            values = _as_list(args[1]) if len(args) > 1 else []
        flat = [_ingredient_dict(v, warnings=warnings) for v in values]
        flat = [v for v in flat if v.get("id")]
        if len(flat) > 9:
            raise RecipeImportError("Бесформенный крафт содержит больше 9 ингредиентов")
        grid = _empty_grid()
        for index, ing in enumerate(flat):
            grid[index // 3][index % 3] = ing
        return ImportedRecipe(
            "vanilla.crafting",
            {"shapeless": True, "inputs": grid, "output": output},
            "KubeJS",
            warnings,
        )

    if len(args) < 3:
        raise RecipeImportError("event.shaped ожидает result, pattern и key")
    pattern = args[1]
    if isinstance(pattern, str):
        pattern = pattern.splitlines()
    if not isinstance(pattern, list):
        raise RecipeImportError("pattern в event.shaped должен быть массивом строк")
    keys = args[2]
    if not isinstance(keys, dict):
        raise RecipeImportError("key в event.shaped должен быть объектом")
    if len(pattern) > 3 or any(len(str(row)) > 3 for row in pattern):
        raise RecipeImportError(
            "Сетка крафта больше 3×3 — этот редактор её не поддерживает"
        )
    grid = _empty_grid()
    for r, row in enumerate(pattern):
        for c, char in enumerate(str(row)):
            if char == " ":
                continue
            if char not in keys:
                raise RecipeImportError(f"В key нет символа {char!r}")
            grid[r][c] = _ingredient_dict(keys[char], warnings=warnings)
    return ImportedRecipe(
        "vanilla.crafting",
        {"shapeless": False, "inputs": grid, "output": output},
        "KubeJS",
        warnings,
    )


def _cooking_from_call(
    module_id: str,
    args: list[Any],
    methods: list[tuple[str, list[Any]]],
    warnings: list[str],
) -> ImportedRecipe:
    if len(args) < 2:
        raise RecipeImportError("Рецепт приготовления ожидает output и input")
    xp = _method_value(methods, "xp", "experience")
    ticks = _method_value(methods, "cookingTime", "cooking_time", "time")
    return ImportedRecipe(
        module_id,
        {
            "input": _ingredient_dict(args[1], warnings=warnings),
            "output": _ingredient_dict(args[0], output=True, warnings=warnings),
            "ticks": _int(ticks),
            "xp": _number(xp),
        },
        "KubeJS",
        warnings,
    )


def _simple_create_from_call(
    module_id: str,
    args: list[Any],
    methods: list[tuple[str, list[Any]]],
    warnings: list[str],
) -> ImportedRecipe:
    if len(args) < 2:
        raise RecipeImportError("Create-рецепт ожидает results и ingredients")
    return ImportedRecipe(
        module_id,
        {
            "inputs": _ingredient_dicts(args[1], warnings=warnings),
            "outputs": _ingredient_dicts(args[0], output=True, warnings=warnings),
            "processing_time": _int(
                _method_value(methods, "processingTime", "processing_time")
            ),
        },
        "KubeJS native",
        warnings,
    )


def _compacting_from_call(
    module_id: str,
    args: list[Any],
    methods: list[tuple[str, list[Any]]],
    warnings: list[str],
) -> ImportedRecipe:
    if len(args) < 2:
        raise RecipeImportError("Create-рецепт ожидает results и ingredients")
    item_inputs, fluid_inputs = _split_fluids(args[1], warnings=warnings)
    extra = args[2] if len(args) > 2 else None
    return ImportedRecipe(
        module_id,
        {
            "item_inputs": item_inputs,
            "fluid_inputs": fluid_inputs,
            "outputs": _ingredient_dicts(args[0], output=True, warnings=warnings),
            "heat_requirement": _heat_from_methods(methods, extra),
        },
        "KubeJS native",
        warnings,
    )


def _mixing_from_call(
    args: list[Any],
    methods: list[tuple[str, list[Any]]],
    warnings: list[str],
) -> ImportedRecipe:
    if len(args) < 2:
        raise RecipeImportError("Create-рецепт ожидает results и ingredients")
    item_inputs, fluid_inputs = _split_fluids(args[1], warnings=warnings)
    item_outputs, fluid_outputs = _split_fluids(args[0], output=True, warnings=warnings)
    extra = args[2] if len(args) > 2 else None
    return ImportedRecipe(
        "create.mixing",
        {
            "item_inputs": item_inputs,
            "fluid_inputs": fluid_inputs,
            "item_outputs": item_outputs,
            "fluid_outputs": fluid_outputs,
            "heat_requirement": _heat_from_methods(methods, extra),
        },
        "KubeJS native",
        warnings,
    )


def _filling_from_call(args: list[Any], warnings: list[str]) -> ImportedRecipe:
    if len(args) < 2:
        raise RecipeImportError("Create filling ожидает output и ingredients")
    output = _ingredient_dict(args[0], output=True, warnings=warnings)
    values = args[1] if len(args) == 2 and isinstance(args[1], list) else args[1:]
    item_input = Ingredient().to_dict()
    fluid_input = Ingredient().to_dict()
    for raw in values:
        ing = _to_ingredient(raw, warnings=warnings)
        if ing.kind == "fluid" and not fluid_input.get("id"):
            fluid_input = ing.to_dict()
        elif ing.kind != "fluid" and not item_input.get("id"):
            item_input = ing.to_dict()
    return ImportedRecipe(
        "create.filling",
        {
            "item_input": item_input,
            "fluid_input": fluid_input,
            "amount": _int(fluid_input.get("amount"), 1000) or 1000,
            "output": output,
        },
        "KubeJS native",
        warnings,
    )


def _emptying_from_call(args: list[Any], warnings: list[str]) -> ImportedRecipe:
    if len(args) < 2:
        raise RecipeImportError("Create emptying ожидает output и input")
    item_outputs, fluid_outputs = _split_fluids(args[0], output=True, warnings=warnings)
    fluid_output = fluid_outputs[0] if fluid_outputs else Ingredient().to_dict()
    return ImportedRecipe(
        "create.emptying",
        {
            "input": _ingredient_dict(args[1], warnings=warnings),
            "item_output": item_outputs[0] if item_outputs else Ingredient().to_dict(),
            "fluid_output": fluid_output,
            "amount": _int(fluid_output.get("amount"), 1000) or 1000,
        },
        "KubeJS native",
        warnings,
    )


def _deploying_from_call(
    args: list[Any],
    methods: list[tuple[str, list[Any]]],
    warnings: list[str],
) -> ImportedRecipe:
    if len(args) < 2:
        raise RecipeImportError("Create deploying ожидает output и ingredients")
    values = args[1] if len(args) == 2 and isinstance(args[1], list) else args[1:]
    depot = (
        _ingredient_dict(values[0], warnings=warnings)
        if values
        else Ingredient().to_dict()
    )
    held = (
        _ingredient_dict(values[1], warnings=warnings)
        if len(values) > 1
        else Ingredient().to_dict()
    )
    keep = _method_value(methods, "keepHeldItem", "keep_held_item") is not None
    if not keep:
        keep = any(_normalise_name(name) == "keephelditem" for name, _ in methods)
    return ImportedRecipe(
        "create.deploying",
        {
            "depot": depot,
            "held": held,
            "outputs": _ingredient_dicts(args[0], output=True, warnings=warnings),
            "keep_held": keep,
        },
        "KubeJS native",
        warnings,
    )


def _mechanical_from_call(args: list[Any], warnings: list[str]) -> ImportedRecipe:
    if len(args) < 3:
        raise RecipeImportError("mechanical_crafting ожидает output, pattern и key")
    pattern = args[1]
    if isinstance(pattern, str):
        pattern = pattern.splitlines()
    keys = args[2]
    if not isinstance(keys, dict):
        raise RecipeImportError("key в mechanical_crafting должен быть объектом")
    rows, cols, grid = _grid_from_pattern(pattern, keys, warnings)
    return ImportedRecipe(
        "create.mechanical_crafting",
        {
            "rows": rows,
            "cols": cols,
            "grid": grid,
            "output": _ingredient_dict(args[0], output=True, warnings=warnings),
        },
        "KubeJS native",
        warnings,
    )


def _step_from_native(value: Any, index: int, warnings: list[str]) -> dict:
    if isinstance(value, dict):
        step = _sequenced_step_from_dict(value, index, warnings)
        return step
    if not isinstance(value, _Call):
        raise RecipeImportError(f"Шаг {index}: ожидался вызов рецепта")
    path, args, _methods = _decompose_chain(value)
    if path == "event.custom":
        if not args or not isinstance(args[0], dict):
            raise RecipeImportError(f"Шаг {index}: event.custom ожидает объект")
        return _sequenced_step_from_dict(args[0], index, warnings)
    name = _create_native_name(path)
    if name is None:
        raise RecipeImportError(f"Шаг {index}: неизвестный рецепт {path!r}")
    kind = _step_kind("create:" + _normalise_name(name))
    if kind is None:
        raise RecipeImportError(f"Шаг {index}: неподдерживаемый тип {path!r}")
    item = None
    fluid = None
    if kind in ("Deploying", "Filling"):
        values = args[1] if len(args) > 1 and isinstance(args[1], list) else args[1:]
        # The first ingredient is the transitional item; the extra one is the
        # deployer's held item or the spout's fluid.
        if len(values) > 1:
            extra = _to_ingredient(values[1], warnings=warnings)
            if kind == "Filling" and extra.kind == "fluid":
                fluid = extra.to_dict()
            elif kind == "Deploying" and extra.kind != "fluid":
                item = extra.to_dict()
    return {"type": kind, "item": item, "fluid": fluid}


def _sequenced_step_from_dict(data: dict, index: int, warnings: list[str]) -> dict:
    recipe_type = str(data.get("type", ""))
    kind = _step_kind(recipe_type)
    if kind is None:
        raise RecipeImportError(f"Шаг {index}: неподдерживаемый тип {recipe_type!r}")
    ingredients = _as_list(data.get("ingredients"))
    item = None
    fluid = None
    if kind == "Deploying" and len(ingredients) > 1:
        item = _ingredient_dict(ingredients[1], warnings=warnings)
    elif kind == "Filling" and len(ingredients) > 1:
        fluid = _ingredient_dict(ingredients[1], warnings=warnings)
    return {"type": kind, "item": item, "fluid": fluid}


def _sequenced_from_call(
    args: list[Any],
    methods: list[tuple[str, list[Any]]],
    warnings: list[str],
) -> ImportedRecipe:
    if len(args) < 3:
        raise RecipeImportError("sequenced_assembly ожидает results, input и sequence")
    transitional_raw = _method_value(methods, "transitionalItem", "transitional_item")
    transitional = _ingredient_dict(transitional_raw, warnings=warnings)
    if not transitional.get("id"):
        raise RecipeImportError(
            "В sequenced_assembly не указан transitionalItem "
            "(добавь .transitionalItem('mod:item'))"
        )
    sequence = _as_list(args[2])
    steps = [
        _step_from_native(value, index, warnings)
        for index, value in enumerate(sequence, start=1)
    ]
    loops = _int(_method_value(methods, "loops"), 1) or 1
    return ImportedRecipe(
        "create.sequenced_assembly",
        {
            "start": _ingredient_dict(args[1], warnings=warnings),
            "transitional": transitional,
            "steps": steps,
            "results": _ingredient_dicts(args[0], output=True, warnings=warnings),
            "scrap": [],
            "loops": loops,
        },
        "KubeJS native",
        warnings,
    )


def _create_native_name(path: str | None) -> str | None:
    if not path:
        return None
    parts = path.split(".")
    if len(parts) >= 4 and parts[:3] == ["event", "recipes", "create"]:
        return "_".join(parts[3:])
    if len(parts) == 3 and parts[:2] == ["event", "recipes"]:
        name = parts[2]
        if name.lower().startswith("create"):
            return name[len("create") :]
    return None


def _from_call(call: _Call, warnings: list[str]) -> ImportedRecipe | None:
    path, args, methods = _decompose_chain(call)
    if not path:
        return None

    if path == "event.custom":
        if not args:
            raise RecipeImportError("event.custom без аргументов")
        if not isinstance(args[0], dict):
            raise RecipeImportError("event.custom ожидает объект рецепта")
        recipe = _from_json(args[0], "KubeJS (event.custom)")
        recipe.warnings = warnings + recipe.warnings
        return recipe

    if path in ("event.shaped", "event.shapeless"):
        return _crafting_from_call(path, args, warnings)

    cooking = {
        "event.smelting": "vanilla.smelting",
        "event.blasting": "vanilla.blasting",
        "event.smoking": "vanilla.smoking",
        "event.campfirecooking": "vanilla.campfire",
    }
    low_path = path.lower()
    if low_path in cooking:
        return _cooking_from_call(cooking[low_path], args, methods, warnings)
    if low_path == "event.stonecutting":
        if len(args) < 2:
            raise RecipeImportError("event.stonecutting ожидает output и input")
        return ImportedRecipe(
            "vanilla.stonecutting",
            {
                "input": _ingredient_dict(args[1], warnings=warnings),
                "output": _ingredient_dict(args[0], output=True, warnings=warnings),
            },
            "KubeJS",
            warnings,
        )
    if low_path == "event.smithing":
        if len(args) < 4:
            raise RecipeImportError(
                "event.smithing ожидает output, template, base и addition"
            )
        return ImportedRecipe(
            "vanilla.smithing",
            {
                "template": _ingredient_dict(args[1], warnings=warnings),
                "base": _ingredient_dict(args[2], warnings=warnings),
                "addition": _ingredient_dict(args[3], warnings=warnings),
                "output": _ingredient_dict(args[0], output=True, warnings=warnings),
            },
            "KubeJS",
            warnings,
        )

    create_name = _create_native_name(path)
    if create_name is None:
        warnings.append(f"Пропущен неизвестный вызов {path}")
        return None
    normalised = _normalise_name(create_name)
    module_id = _CREATE_NATIVE_TYPES.get(normalised)
    if module_id is None:
        raise RecipeImportError(f"Неподдерживаемый рецепт Create: {create_name!r}")
    if module_id in _CREATE_SIMPLE:
        return _simple_create_from_call(module_id, args, methods, warnings)
    if module_id == "create.compacting":
        return _compacting_from_call(module_id, args, methods, warnings)
    if module_id == "create.mixing":
        return _mixing_from_call(args, methods, warnings)
    if module_id == "create.filling":
        return _filling_from_call(args, warnings)
    if module_id == "create.emptying":
        return _emptying_from_call(args, warnings)
    if module_id == "create.deploying":
        return _deploying_from_call(args, methods, warnings)
    if module_id == "create.mechanical_crafting":
        return _mechanical_from_call(args, warnings)
    if module_id == "create.sequenced_assembly":
        return _sequenced_from_call(args, methods, warnings)
    raise RecipeImportError(f"Неподдерживаемый рецепт Create: {create_name!r}")


# ================================================================ public ====


def _strip_code_fence(text: str) -> str:
    value = text.strip()
    if not value.startswith("```"):
        return value
    lines = value.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _try_json(text: str) -> Any | None:
    try:
        return json.loads(text)
    except ValueError, TypeError:
        return None


def parse_recipe(text: str) -> ImportedRecipe:
    """Parse a KubeJS snippet or a datapack JSON recipe.

    Raises:
        RecipeImportError: the text is empty, unknown, or uses an unsupported
            recipe type.  The message is safe to show in the GUI.
    """
    source = _strip_code_fence(text or "")
    if not source:
        raise RecipeImportError("Вставь KubeJS-код или JSON-рецепт")

    data = _try_json(source)
    if data is not None:
        return _from_json(data, "vanilla JSON" if _looks_vanilla(data) else "JSON")

    calls = _find_event_calls(source)
    if not calls:
        # Give a more useful hint than a generic parser failure.
        if "{" in source and "type" in source:
            raise RecipeImportError(
                "Похоже на рецепт, но не удалось разобрать синтаксис. "
                "Проверь запятые и кавычки."
            )
        raise RecipeImportError(
            "Не найден рецепт. Поддерживаются event.custom({...}), "
            "native KubeJS-вызовы и JSON датапака."
        )

    warnings: list[str] = []
    last_error: RecipeImportError | None = None
    for call in calls:
        try:
            recipe = _from_call(call, warnings)
        except RecipeImportError as exc:
            # Keep looking: KubeJS files often contain several calls and the
            # first one may be event.remove() or an unrelated helper.
            last_error = exc
            continue
        if recipe is not None:
            if len(calls) > 1:
                recipe.warnings.append(
                    "Найдено несколько рецептов; импортирован первый"
                )
            return recipe

    if last_error is not None:
        raise last_error
    details = ", ".join(filter(None, (_path(call.func) for call in calls)))
    raise RecipeImportError(
        "В KubeJS-коде не найден поддерживаемый рецепт"
        + (f" (вызовы: {details})" if details else "")
    )


def _looks_vanilla(data: Any) -> bool:
    if isinstance(data, list):
        data = next((item for item in data if isinstance(item, dict)), {})
    if not isinstance(data, dict):
        return False
    return str(data.get("type", "")).startswith("minecraft:")
