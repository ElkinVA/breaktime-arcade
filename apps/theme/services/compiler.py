"""Генерация CSS-файла темы из токенов (§2.7)."""

from __future__ import annotations

import hashlib

from apps.theme.models import ThemeTokenSet


def compile_theme_css(tokens: dict[str, str]) -> str:
    """Возвращает CSS с :root { ... } из словаря токенов."""
    lines = [":root {"]
    for key, value in sorted(tokens.items()):
        if not key.startswith("--"):
            key = f"--{key}"
        lines.append(f"  {key}: {value};")
    lines.append("}")
    return "\n".join(lines)


def compute_theme_hash(css: str) -> str:
    """SHA-256 первых 16 символов."""
    return hashlib.sha256(css.encode("utf-8")).hexdigest()[:16]


def get_active_theme_css() -> tuple[str, str]:
    """Возвращает (hash, css) активной темы."""
    theme = ThemeTokenSet.objects.filter(is_active=True).first()
    if theme is None:
        # Значения по умолчанию из static/src/css/tokens.css
        default_tokens = {
            "--ba-bg": "#0f1115",
            "--ba-surface": "#171a21",
            "--ba-text": "#e8eaf0",
            "--ba-muted": "#9aa3b2",
            "--ba-accent": "#39ff88",
            "--ba-danger": "#ff5c72",
            "--ba-radius-card": "14px",
            "--ba-space-unit": "4px",
            "--ba-font-body": 'system-ui, "Segoe UI", Roboto, sans-serif',
            "--ba-font-display": '"Segoe UI", system-ui, sans-serif',
        }
        css = compile_theme_css(default_tokens)
        return compute_theme_hash(css), css

    return theme.hash, compile_theme_css(theme.tokens)
