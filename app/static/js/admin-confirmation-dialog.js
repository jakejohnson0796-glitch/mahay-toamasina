(function () {
  "use strict";

  var dialog = null;
  var input = null;
  var error = null;
  var resolver = null;

  function t(fr, mg) {
    try {
      if (document.documentElement.getAttribute("lang") === "mg" ||
          window.localStorage.getItem("mahay-langue") === "mg") return mg;
    } catch (_) {
      if (document.documentElement.getAttribute("lang") === "mg") return mg;
    }
    return fr;
  }

  function close(value) {
    if (!resolver) return;
    var resolve = resolver;
    resolver = null;
    if (dialog && dialog.open) dialog.close();
    if (input) {
      input.value = "";
      input.type = "password";
    }
    if (error) {
      error.textContent = "";
      error.hidden = true;
    }
    resolve(value);
  }

  function setup() {
    if (dialog) return;
    dialog = document.createElement("dialog");
    dialog.className = "admin-confirmation-dialog";
    dialog.setAttribute("aria-labelledby", "admin-confirmation-title");
    dialog.setAttribute("aria-describedby", "admin-confirmation-description");
    dialog.innerHTML =
      '<div class="admin-confirmation-dialog__panel">' +
        '<header class="admin-confirmation-dialog__header">' +
          '<span class="admin-confirmation-dialog__icon" aria-hidden="true">' +
            '<svg viewBox="0 0 24 24" focusable="false">' +
              '<path d="M12 3.2 19 6v5.2c0 4.4-2.9 7.9-7 9.6-4.1-1.7-7-5.2-7-9.6V6l7-2.8Z"></path>' +
              '<path d="m9 12 2 2 4-4"></path>' +
            '</svg>' +
          '</span>' +
          '<span class="admin-confirmation-dialog__eyebrow">' + t("SÉCURITÉ ADMINISTRATEUR", "FIAROVANA NY MPITANTANA") + '</span>' +
          '<span class="admin-confirmation-dialog__secure"><i aria-hidden="true"></i>' + t("Connexion protégée", "Fifandraisana voaaro") + '</span>' +
        '</header>' +
        '<div class="admin-confirmation-dialog__content">' +
          '<h2 id="admin-confirmation-title">' + t("Confirmer cette action", "Hamarino ity hetsika ity") + '</h2>' +
          '<p id="admin-confirmation-description">' + t("Une vérification supplémentaire est nécessaire avant de poursuivre cette opération dans l’espace administrateur.", "Ilaina ny fanamarinana fanampiny alohan’ny hanohizana ity hetsika ity ao amin’ny faritra fitantanana.") + '</p>' +
          '<div class="admin-confirmation-dialog__notice"><span aria-hidden="true">i</span><p>' + t("Cette action est contrôlée et journalisée côté serveur. Votre mot de passe n’est pas enregistré dans cette fenêtre.", "Hamarinin’ny mpizara sy raketiny ity hetsika ity. Tsy tehirizina eto amin’ity varavarankely ity ny tenimiafinao.") + '</p></div>' +
          '<form class="admin-confirmation-dialog__form" novalidate>' +
            '<label for="admin-confirmation-password">' + t("Mot de passe de confirmation", "Tenimiafina fanamafisana") + '</label>' +
            '<div class="admin-confirmation-dialog__input">' +
              '<input id="admin-confirmation-password" type="password" autocomplete="current-password" autocapitalize="off" spellcheck="false" required>' +
              '<button type="button" data-visibility aria-pressed="false">' + t("Afficher", "Asehoy") + '</button>' +
            '</div>' +
            '<p class="admin-confirmation-dialog__hint">' + t("Utilisez votre mot de passe de confirmation administrateur, distinct de votre mot de passe de connexion.", "Ampiasao ny tenimiafina fanamafisana ny mpitantana, izay tsy mitovy amin’ny tenimiafina fidirana.") + '</p>' +
            '<p class="admin-confirmation-dialog__error" role="alert" aria-live="assertive" hidden></p>' +
            '<div class="admin-confirmation-dialog__actions">' +
              '<button type="button" class="admin-confirmation-dialog__button admin-confirmation-dialog__button--secondary" data-cancel>' + t("Annuler", "Aoka ihany") + '</button>' +
              '<button type="submit" class="admin-confirmation-dialog__button admin-confirmation-dialog__button--primary">' + t("Confirmer l’action", "Hamarino ny hetsika") + '<span aria-hidden="true">→</span></button>' +
            '</div>' +
          '</form>' +
        '</div>' +
        '<footer class="admin-confirmation-dialog__footer"><span aria-hidden="true"></span>' + t("Validation supplémentaire requise pour cette opération.", "Ilaina ny fanamarinana fanampiny amin’ity hetsika ity.") + '</footer>' +
      '</div>';

    document.body.appendChild(dialog);
    input = dialog.querySelector("#admin-confirmation-password");
    error = dialog.querySelector(".admin-confirmation-dialog__error");

    dialog.querySelector("form").addEventListener("submit", function (event) {
      event.preventDefault();
      if (!input.value) {
        error.textContent = t("Saisissez votre mot de passe de confirmation pour continuer.", "Ampidiro ny tenimiafina fanamafisana mba hanohizana.");
        error.hidden = false;
        input.focus();
        return;
      }
      close(input.value);
    });

    dialog.querySelector("[data-cancel]").addEventListener("click", function () {
      close(null);
    });

    dialog.querySelector("[data-visibility]").addEventListener("click", function (event) {
      var button = event.currentTarget;
      var visible = input.type === "password";
      input.type = visible ? "text" : "password";
      button.textContent = visible ? t("Masquer", "Afeno") : t("Afficher", "Asehoy");
      button.setAttribute("aria-pressed", visible ? "true" : "false");
      button.setAttribute("aria-label", visible ? t("Masquer le mot de passe", "Afeno ny tenimiafina") : t("Afficher le mot de passe", "Asehoy ny tenimiafina"));
    });

    dialog.addEventListener("cancel", function (event) {
      event.preventDefault();
      close(null);
    });

    dialog.addEventListener("click", function (event) {
      if (event.target === dialog) close(null);
    });
  }

  window.demanderConfirmationAdmin = function () {
    setup();
    // Une saisie ne peut autoriser qu'une seule requête à la fois.
    if (resolver) return Promise.resolve(null);
    return new Promise(function (resolve) {
      resolver = resolve;
      input.value = "";
      input.type = "password";
      error.textContent = "";
      error.hidden = true;
      var visibility = dialog.querySelector("[data-visibility]");
      visibility.textContent = t("Afficher", "Asehoy");
      visibility.setAttribute("aria-pressed", "false");
      dialog.showModal();
      if (window.requestAnimationFrame) {
        window.requestAnimationFrame(function () { input.focus(); });
      } else {
        input.focus();
      }
    });
  };

  window.notifierConfirmationAdmin = function (message) {
    var toast = document.createElement("div");
    toast.className = "admin-confirmation-toast";
    toast.setAttribute("role", "alert");
    toast.setAttribute("aria-live", "assertive");
    toast.textContent = String(message || "");
    document.body.appendChild(toast);
    window.setTimeout(function () {
      toast.classList.add("admin-confirmation-toast--sortie");
      window.setTimeout(function () {
        if (toast.parentNode) toast.parentNode.removeChild(toast);
      }, 220);
    }, 5600);
  };
})();
