"""Entry point for ``python -m RecipeStudio``."""

from __future__ import annotations

import customtkinter as ctk

from RecipeStudio.app import RecipeStudioApp
from RecipeStudio.config import load_config


def main() -> None:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    config = load_config()
    app = RecipeStudioApp(config)
    app.mainloop()


if __name__ == "__main__":
    main()
