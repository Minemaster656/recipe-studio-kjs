"""Entry point for ``python -m RecipeStudio``."""

from __future__ import annotations

import customtkinter as ctk

from RecipeStudio.app import RecipeStudioApp
from RecipeStudio.config import load_config
from RecipeStudio.services.projects import ensure_active_project


def main() -> None:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    app_config = load_config()
    project, info = ensure_active_project(app_config)
    app = RecipeStudioApp(project, app_config, info)
    app.mainloop()


if __name__ == "__main__":
    main()
