"""Recipe module discovery.

Dropping a new file into ``RecipeStudio/recipes/`` with a module-level
``MODULE`` object registers a new tab automatically.
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass

from RecipeStudio.config import Config


@dataclass
class ModuleLoadError:
    module: str
    error: str


def discover_modules(config: Config) -> tuple[list, list[ModuleLoadError]]:
    import RecipeStudio.recipes as recipes_pkg

    modules = []
    errors: list[ModuleLoadError] = []
    disabled = set(str(x) for x in (config.get("disabled_modules", []) or []))

    for info in pkgutil.walk_packages(recipes_pkg.__path__, recipes_pkg.__name__ + "."):
        leaf = info.name.rsplit(".", 1)[-1]
        if leaf in ("base", "registry"):
            continue
        try:
            mod = importlib.import_module(info.name)
        except Exception as exc:  # pragma: no cover - defensive
            errors.append(ModuleLoadError(info.name, f"{type(exc).__name__}: {exc}"))
            continue
        module = getattr(mod, "MODULE", None)
        if module is None:
            continue
        module_id = getattr(module, "id", "")
        if not module_id or module_id in disabled:
            continue
        modules.append(module)

    modules.sort(
        key=lambda m: (
            getattr(m, "order", 100),
            getattr(m, "category", ""),
            getattr(m, "title", ""),
        )
    )
    return modules, errors
