(function () {
  "use strict";

  function setMessage(form, message) {
    var note = form.querySelector("[data-mfa-validation-message]");
    var input = form.querySelector(".mfa-code-input");
    if (note) {
      note.textContent = message;
      note.hidden = !message;
    }
    if (input) {
      if (message) input.setAttribute("aria-invalid", "true");
      else input.removeAttribute("aria-invalid");
    }
  }

  function initialiserValidationCodes() {
    document.querySelectorAll("[data-mfa-code-form]").forEach(function (form) {
      var input = form.querySelector(".mfa-code-input");
      if (!input || form.dataset.mfaReady === "1") return;
      form.dataset.mfaReady = "1";

      input.addEventListener("input", function () {
        input.value = input.value.replace(/[^0-9]/g, "").slice(0, 6);
        if (/^\d{6}$/.test(input.value)) setMessage(form, "");
      });

      form.addEventListener("submit", function (event) {
        if (!/^\d{6}$/.test(input.value.trim())) {
          event.preventDefault();
          setMessage(form, "Saisissez les 6 chiffres affichés par votre application ou reçus par e-mail.");
          input.focus();
        } else {
          setMessage(form, "");
        }
      });
    });
  }

  function copierTexte(text) {
    if (navigator.clipboard && window.isSecureContext && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    return Promise.reject(new Error("clipboard indisponible"));
  }

  function initialiserCopieCle() {
    document.querySelectorAll("[data-copy-secret]").forEach(function (button) {
      if (button.dataset.copyReady === "1") return;
      button.dataset.copyReady = "1";
      button.addEventListener("click", function () {
        var text = button.getAttribute("data-copy-secret") || "";
        var status = document.querySelector("[data-copy-status]");
        var fallback = function () {
          var temp = document.createElement("textarea");
          temp.value = text;
          temp.setAttribute("readonly", "");
          temp.className = "mfa-copy-temporary";
          document.body.appendChild(temp);
          temp.select();
          var ok = false;
          try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
          document.body.removeChild(temp);
          if (status) status.textContent = ok
            ? "Clé copiée. Conservez-la dans un endroit sûr."
            : "Copie impossible : sélectionnez la clé et copiez-la manuellement.";
        };

        copierTexte(text).then(function () {
          if (status) status.textContent = "Clé copiée. Conservez-la dans un endroit sûr.";
        }).catch(fallback);
      });
    });
  }

  function initialiser() {
    initialiserValidationCodes();
    initialiserCopieCle();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialiser);
  } else {
    initialiser();
  }
})();
