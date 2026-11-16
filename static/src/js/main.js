// CSP-совместимость (§2.3): allowEval выключается до инициализации HTMX.
if (window.htmx) {
  window.htmx.config.allowEval = false;
}

const THEME_KEY = "ba_theme";

function applyTheme(value) {
  document.documentElement.dataset.theme = value;
  document.cookie = `ba_theme=${value}; path=/; max-age=31536000; SameSite=Lax`;
}

function readCookie(name) {
  const row = document.cookie.split("; ").find((item) => item.startsWith(`${name}=`));
  return row ? row.split("=")[1] : null;
}

export function csrfToken() {
  return readCookie("csrftoken") ?? "";
}

document.addEventListener("DOMContentLoaded", () => {
  const saved = readCookie("ba_theme");
  if (saved === "light" || saved === "dark") {
    document.documentElement.dataset.theme = saved;
  }
  document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      applyTheme(next);
    });
  });
});

export { THEME_KEY, applyTheme };
