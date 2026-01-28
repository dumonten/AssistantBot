# src/app.py
from __future__ import annotations

# IMPORTANT: import workflows to register them
import workflows  # noqa: F401

# chainlit handlers registration
import ui.chainlit_handlers  # noqa: F401
