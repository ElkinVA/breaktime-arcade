"""BA Dev Control — local Telegram control plane for autonomous development.

The package is deliberately independent of the Django application: it uses the
Python standard library only and talks to Claude Code through its supported
background-session CLI (``claude --bg`` / ``claude agents`` / ``claude stop``).
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
