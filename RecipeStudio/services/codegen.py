"""Helpers that turn slot values into KubeJS source code."""

from __future__ import annotations

from RecipeStudio.model.ingredient import Ingredient, normalize_fluid_id


def quote(value: str) -> str:
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def format_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:g}"


def item_literal(ing: Ingredient, *, output: bool = False) -> str | None:
    """Return a KubeJS expression for an ingredient.

    ``output=True`` uses ``Item.of`` for stacks and ``CreateItem.of`` for
    chance outputs.  Inputs use the shorter ``'3x id'`` form.
    """
    if ing is None or ing.is_empty:
        return None

    rid = ing.id.strip()
    if ing.kind == "tag":
        rid = "#" + rid.lstrip("#")
        if ing.count > 1:
            return quote(f"{ing.count}x {rid}")
        return quote(rid)

    if ing.kind == "fluid":
        rid = normalize_fluid_id(rid)
        amount = int(ing.amount or 1000)
        return f"Fluid.of({quote(rid)}, {amount})"

    nbt_part = f", {quote(ing.nbt)}" if ing.nbt else ""

    if output:
        if ing.chance is not None:
            return f"CreateItem.of({quote(rid)}, {format_number(ing.chance)}{nbt_part})"
        if ing.count > 1 or ing.nbt:
            count_part = f", {ing.count}" if ing.count != 1 else ""
            return f"Item.of({quote(rid)}{count_part}{nbt_part})"
        return quote(rid)

    if ing.count > 1:
        return quote(f"{ing.count}x {rid}")
    if ing.nbt:
        return f"Item.of({quote(rid)}{nbt_part})"
    return quote(rid)


def build_export(
    body: str,
    remove_filter: Ingredient | None = None,
    *,
    wrap: bool = True,
    event_var: str = "event",
) -> str:
    """Wrap a recipe body in ``ServerEvents.recipes`` and optionally remove.

    ``remove_filter`` is only used when it is non-empty.
    """
    body = (body or "").rstrip()
    if not body:
        return ""

    remove_line = None
    if remove_filter is not None and not remove_filter.is_empty:
        if remove_filter.kind == "tag":
            target = quote("#" + remove_filter.id.lstrip("#"))
        elif remove_filter.kind == "fluid":
            target = quote(normalize_fluid_id(remove_filter.id))
        else:
            target = quote(remove_filter.id)
        remove_line = f"{event_var}.remove({{ output: {target} }});"

    if not wrap:
        return body + "\n"

    lines = ["ServerEvents.recipes((event) => {"]
    if remove_line:
        lines.append("  " + remove_line)
        lines.append("")
    lines.extend("  " + line if line else "" for line in body.splitlines())
    lines.append("});")
    return "\n".join(lines) + "\n"
