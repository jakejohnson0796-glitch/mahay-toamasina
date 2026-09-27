/*
 * Gasy Mahay — interactions UX 2026
 * Routine quotidienne locale + installation PWA.
 * Aucune donnée personnelle ni tracking externe.
 */
(function () {
  "use strict";

  function cleRoutineDuJour() {
    const maintenant = new Date();
    const annee = maintenant.getFullYear();
    const mois = String(maintenant.getMonth() + 1).padStart(2, "0");
    const jour = String(maintenant.getDate()).padStart(2, "0");
    return "mahay-routine-v1-" + annee + "-" + mois + "-" + jour;
  }

  function initRoutine() {
    const routine = document.getElementById("routine-du-jour");
    if (!routine) return;

    const boutons = Array.from(routine.querySelectorAll(".tb-routine-fait"));
    const compteur = routine.querySelector(".tb-routine-compteur");
    const remplissage = routine.querySelector(".tb-routine-remplissage");

    let etat = {};
    try {
      etat = JSON.parse(localStorage.getItem(cleRoutineDuJour()) || "{}");
    } catch (_erreur) {
      etat = {};
    }

    function sauvegarder() {
      try {
        localStorage.setItem(cleRoutineDuJour(), JSON.stringify(etat));
      } catch (_erreur) {
        /* Le stockage local est optionnel : l'UI reste utilisable. */
      }
    }

    function appliquer() {
      const total = boutons.length;
      const terminees = boutons.filter(function (bouton) {
        return etat[bouton.dataset.routineId] === true;
      }).length;

      boutons.forEach(function (bouton) {
        const faite = etat[bouton.dataset.routineId] === true;
        bouton.setAttribute("aria-pressed", faite ? "true" : "false");
        bouton.setAttribute(
          "aria-label",
          faite ? "Étape terminée" : "Marquer cette étape comme terminée"
        );

        const etape = bouton.closest(".tb-routine-etape");
        if (etape) etape.dataset.terminee = faite ? "true" : "false";
        bouton.textContent = faite ? "✓" : "○";
      });

      if (compteur) compteur.textContent = terminees + "/" + total + " aujourd'hui";
      if (remplissage) {
        remplissage.style.width = total
          ? ((terminees / total) * 100) + "%"
          : "0%";
      }

      routine.dataset.complete = total > 0 && terminees === total ? "true" : "false";
    }

    appliquer();

    boutons.forEach(function (bouton) {
      bouton.addEventListener("click", function () {
        const id = bouton.dataset.routineId;
        etat[id] = etat[id] !== true;
        sauvegarder();
        appliquer();
      });
    });
  }

  function initPwa() {
    const installation = document.getElementById("pwa-installation");
    if (!installation) return;

    const cleMasquee = "mahay-pwa-installation-masquee-v1";
    try {
      if (localStorage.getItem(cleMasquee) === "1") return;
    } catch (_erreur) {}

    let evenementInstallation = null;

    window.addEventListener("beforeinstallprompt", function (evenement) {
      evenement.preventDefault();
      evenementInstallation = evenement;
      installation.hidden = false;
    });

    const installer = installation.querySelector(".pwa-installer");
    const fermer = installation.querySelector(".pwa-fermer");

    if (installer) {
      installer.addEventListener("click", async function () {
        if (!evenementInstallation) return;
        evenementInstallation.prompt();
        try {
          await evenementInstallation.userChoice;
        } catch (_erreur) {}
        evenementInstallation = null;
        installation.hidden = true;
      });
    }

    if (fermer) {
      fermer.addEventListener("click", function () {
        installation.hidden = true;
        try {
          localStorage.setItem(cleMasquee, "1");
        } catch (_erreur) {}
      });
    }
  }

  function initAnimations() {
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const candidats = Array.from(document.querySelectorAll(
      "main h1, main h2, main .hero-phare, main .tb-carte-stat, main .tb-carte-cercle-moderne, main .carte-claire, main .doc-carte, main .quiz-card, main .carte-formulaire, main .section-phare"
    ));

    const elements = candidats.filter(function (element, index) {
      return candidats.indexOf(element) === index;
    }).slice(0, 50);

    if (!elements.length) return;

    elements.forEach(function (element, index) {
      element.classList.add("gm-reveal", "gm-hover-lift");
      element.classList.add("gm-delay-" + Math.min((index % 4) + 1, 4));
    });

    if (!("IntersectionObserver" in window)) {
      elements.forEach(function (element) { element.classList.add("gm-visible"); });
      return;
    }

    const observer = new IntersectionObserver(function (entries, instance) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("gm-visible");
        instance.unobserve(entry.target);
      });
    }, { threshold: 0.08, rootMargin: "0px 0px -40px 0px" });

    elements.forEach(function (element) { observer.observe(element); });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initAnimations();
    initRoutine();
    initPwa();
  });
})();
