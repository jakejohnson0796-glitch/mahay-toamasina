/*
 * Confirmation forte des actions administrateur.
 *
 * Le serveur verifie toujours le secret : ce script ne fait qu'ameliorer
 * l'UX en le demandant avant l'envoi du formulaire et en interpretant les
 * reponses 428/403/429. Desactiver JavaScript ne supprime donc pas la garde.
 */
(function () {
  "use strict";

  function actionProtegee(form) {
    if (document.body.dataset.adminSession !== "1") return false;
    if (!form || (form.method || "get").toLowerCase() !== "post") return false;

    var url;
    try {
      url = new URL(form.action || window.location.href, window.location.origin);
    } catch (_) {
      return false;
    }

    if (url.origin !== window.location.origin) return false;

    var path = url.pathname;
    if (path === "/admin/securite/mot-de-passe-confirmation") return false;

    return (
      path === "/admin" ||
      path.indexOf("/admin/") === 0 ||
      path.indexOf("/moderation") === 0 ||
      /^\/cercles\/\d+\/supprimer$/.test(path)
    );
  }

  document.addEventListener("submit", async function (event) {
    var form = event.target;
    if (!(form instanceof HTMLFormElement) || !actionProtegee(form)) return;
    if (form.dataset.adminConfirmationEnCours === "1") return;

    event.preventDefault();

    var motDePasse = window.prompt(
      "Action administrateur protégée\n\nEntrez votre mot de passe de confirmation :"
    );

    if (motDePasse === null) return;

    if (!motDePasse) {
      window.alert("Le mot de passe de confirmation est requis.");
      return;
    }

    form.dataset.adminConfirmationEnCours = "1";

    var boutons = form.querySelectorAll("button[type='submit'], input[type='submit']");
    boutons.forEach(function (bouton) {
      bouton.disabled = true;
    });

    try {
      var donnees = new FormData(form);
      donnees.set("admin_confirmation_password", motDePasse);

      var reponse = await fetch(form.action, {
        method: "POST",
        body: donnees,
        credentials: "same-origin",
        redirect: "follow",
      });

      if (reponse.status === 428) {
        var configuration = null;
        try {
          configuration = await reponse.json();
        } catch (_) {
          configuration = null;
        }
        window.location.assign(
          (configuration && configuration.configuration_url)
            ? configuration.configuration_url
            : "/admin/securite?configurer=1"
        );
        return;
      }

      if (reponse.status === 403 || reponse.status === 429) {
        var erreur = null;
        try {
          erreur = await reponse.json();
        } catch (_) {
          erreur = null;
        }
        window.alert(
          (erreur && erreur.detail) ||
          "La confirmation administrateur a été refusée."
        );
        return;
      }

      if (!reponse.ok) {
        window.alert("L'action administrateur n'a pas pu être exécutée.");
        return;
      }

      // Les routes admin utilisent normalement une redirection 303 après
      // l'action. fetch suit cette redirection et response.url devient
      // l'écran final à afficher.
      window.location.assign(reponse.url || form.action);
    } catch (_) {
      window.alert("Impossible de joindre le serveur. Réessayez.");
    } finally {
      delete form.dataset.adminConfirmationEnCours;
      boutons.forEach(function (bouton) {
        bouton.disabled = false;
      });
    }
  });
})();
