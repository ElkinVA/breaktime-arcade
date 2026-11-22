// Rating vote widget on the public game detail page (§2.9).
// Progressive enhancement: the form posts JSON to the existing ratings API.
function setStatus(node, message, state) {
  if (!node) {
    return;
  }
  node.textContent = message;
  node.dataset.state = state;
}

function errorMessage(form, code) {
  if (code === "E_PLAYTIME_REQUIRED") {
    return form.dataset.playtimeMessage || form.dataset.errorMessage;
  }
  if (code === "E_RATE_LIMIT") {
    return form.dataset.limitMessage || form.dataset.errorMessage;
  }
  return form.dataset.errorMessage;
}

async function parseJson(response) {
  try {
    return await response.json();
  } catch {
    return {};
  }
}

function initRatingForm(form) {
  const status = form.querySelector("[data-testid='rating-vote-status']");
  const token = form.querySelector("input[name='csrfmiddlewaretoken']");
  const submit = form.querySelector("button[type='submit']");

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!form.reportValidity()) {
      return;
    }
    const selected = form.querySelector("input[name='value']:checked");
    if (!selected) {
      setStatus(status, form.dataset.errorMessage, "error");
      return;
    }

    if (submit) {
      submit.disabled = true;
    }
    form.setAttribute("aria-busy", "true");
    try {
      const response = await fetch(form.action, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": token ? token.value : "",
        },
        body: JSON.stringify({ value: Number(selected.value) }),
      });
      const payload = await parseJson(response);
      if (!response.ok) {
        setStatus(status, errorMessage(form, payload.code), "error");
        return;
      }
      setStatus(status, form.dataset.successMessage, "success");
      // Reload so the aggregate, vote count and selected star stay in sync
      // without duplicating plural/localisation logic in JavaScript.
      globalThis.setTimeout(() => globalThis.location.reload(), 500);
    } catch {
      setStatus(status, form.dataset.errorMessage, "error");
    } finally {
      form.removeAttribute("aria-busy");
      if (submit) {
        submit.disabled = false;
      }
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-rating-form]").forEach(initRatingForm);
});
