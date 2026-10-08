/* Gasy Mahay — interactions Quiz IA + Tuteur IA */
(function () {
  "use strict";

  function initialiserGenerationIA() {
    document.querySelectorAll("[data-ai-generation-form]").forEach(function (formulaire) {
      formulaire.addEventListener("submit", function () {
        const bouton = formulaire.querySelector("[data-ai-submit]");
        const chargement = formulaire.closest(".ai-form-card, .ai-exam-card")?.querySelector("[data-ai-loading]");
        if (bouton) {
          bouton.disabled = true;
          bouton.dataset.libelleOriginal = bouton.textContent;
          bouton.textContent = "Génération…";
        }
        if (chargement) chargement.classList.add("is-visible");
      });
    });
  }

  function initialiserQuiz() {
    const formulaire = document.querySelector("[data-quiz-form]");
    if (!formulaire) return;

    const questions = Array.from(document.querySelectorAll("[data-quiz-question]"));
    const total = questions.length;
    const texte = document.querySelector("[data-quiz-progress-text]");
    const remplissage = document.querySelector("[data-quiz-progress-fill]");
    const nav = document.querySelector("[data-quiz-nav]");
    const chronoCarte = document.querySelector("[data-quiz-timer-card]");
    const chrono = document.querySelector("[data-quiz-timer]");
    const secondesInitiales = Number(formulaire.dataset.examenSecondes || 0);
    const adaptatif = formulaire.dataset.quizAdaptatif === "1";
    const tentativeId = Number(formulaire.dataset.quizTentativeId || 0);
    let secondes = secondesInitiales;
    let timer = null;
    let envoiAdaptatif = false;

    function reponsesCount() {
      return questions.reduce(function (totalCourant, question) {
        return totalCourant + (question.querySelector("input[type=radio]:checked") ? 1 : 0);
      }, 0);
    }

    function majProgression() {
      const repondues = reponsesCount();
      const pourcentage = total ? (repondues / total) * 100 : 0;
      if (texte) texte.textContent = repondues + " / " + total + " répondues";
      const focusProgress = document.querySelector("[data-quiz-focus-progress]");
      if (focusProgress) focusProgress.textContent = repondues + " / " + total + " répondues";
      const pourcentageElement = document.querySelector("[data-quiz-progress-percent]");
      if (pourcentageElement) pourcentageElement.textContent = Math.round(pourcentage) + "%";
      if (remplissage) {
        remplissage.value = repondues;
        remplissage.max = total;
      }

      questions.forEach(function (question) {
        const item = nav ? nav.querySelector('[data-nav-index="' + question.dataset.quizIndex + '"]') : null;
        if (item) item.classList.toggle("is-answered", Boolean(question.querySelector("input[type=radio]:checked")));
      });
    }

    function afficherQuestion(index) {
      const cible = questions[index];
      if (!cible) return;
      questions.forEach(function (question) {
        const active = question === cible;
        question.classList.toggle("is-current", active);
        if (adaptatif) question.hidden = !active;
      });
      cible.scrollIntoView({ behavior: "smooth", block: "start" });
      if (nav) {
        nav.querySelectorAll("[data-nav-index]").forEach(function (item) {
          item.classList.toggle("is-current", Number(item.dataset.navIndex) === index);
        });
      }
    }

    if (nav) {
      questions.forEach(function (question, index) {
        const bouton = document.createElement("button");
        bouton.type = "button";
        bouton.className = "quiz-nav-item";
        bouton.dataset.navIndex = String(index);
        bouton.textContent = String(index + 1);
        bouton.setAttribute("aria-label", "Aller à la question " + (index + 1));
        bouton.addEventListener("click", function () {
          if (adaptatif && !question.querySelector("input[type=radio]:checked") &&
              !question.classList.contains("is-current")) {
            return;
          }
          afficherQuestion(index);
        });
        nav.appendChild(bouton);
      });
    }

    formulaire.addEventListener("change", function () {
      majProgression();
      if (!adaptatif || envoiAdaptatif) return;
      const question = questions.find(function (item) {
        return item.classList.contains("is-current");
      });
      if (question) {
        window.setTimeout(function () {
          envoyerReponseAdaptative(question);
        }, 120);
      }
    });

    async function envoyerReponseAdaptative(question) {
      if (!adaptatif || !tentativeId || envoiAdaptatif) return;
      const input = question.querySelector("input[type=radio]:checked");
      if (!input) return;

      envoiAdaptatif = true;
      question.querySelectorAll("input[type=radio]").forEach(function (radio) {
        radio.disabled = true;
      });
      question.querySelectorAll('input[name^="confiance_"]').forEach(function (radio) {
        radio.disabled = true;
      });

      try {
        const body = new URLSearchParams();
        body.set("_csrf", document.querySelector('#form-quiz input[name="_csrf"]')?.value || "");
        body.set("question_index", question.dataset.quizIndex);
        body.set("reponse", input.value);
        const confiance = question.querySelector('input[name^="confiance_"]:checked');
        if (confiance) body.set("confiance", confiance.value);

        const response = await fetch("/quiz/" + tentativeId + "/repondre", {
          method: "POST",
          headers: {"X-Requested-With": "XMLHttpRequest"},
          body: body,
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "La réponse adaptative n'a pas pu être enregistrée.");

        majProgression();
        if (data.termine) {
          const bouton = document.querySelector("[data-quiz-submit]");
          if (bouton) {
            bouton.disabled = true;
            bouton.textContent = "Validation…";
          }
          formulaire.requestSubmit();
          return;
        }

        if (typeof data.prochaine_question === "number") {
          afficherQuestion(data.prochaine_question);
        }
      } catch (erreur) {
        question.querySelectorAll("input[type=radio]").forEach(function (radio) {
          radio.disabled = false;
        });
      question.querySelectorAll('input[name^="confiance_"]').forEach(function (radio) {
          radio.disabled = false;
        });
        const aide = document.querySelector(".quiz-submit-help");
        if (aide) aide.textContent = erreur.message || "Impossible d'enregistrer la réponse. Réessaie.";
      } finally {
        envoiAdaptatif = false;
      }
    }

    formulaire.addEventListener("submit", function (event) {
      if (adaptatif && reponsesCount() < total) {
        event.preventDefault();
        return;
      }
      const bouton = document.querySelector("[data-quiz-submit]");
      if (bouton && !bouton.disabled) {
        bouton.disabled = true;
        bouton.textContent = "Validation…";
      }
    });

    questions.forEach(function (question, index) {
      question.addEventListener("click", function () {
        afficherQuestion(index);
      });
      question.querySelectorAll("input[type=radio]").forEach(function (input) {
        input.addEventListener("change", majProgression);
      });
    });

    function formater(secondesRestantes) {
      const minutes = Math.floor(secondesRestantes / 60);
      const secondesAffichees = secondesRestantes % 60;
      return String(minutes).padStart(2, "0") + ":" + String(secondesAffichees).padStart(2, "0");
    }

    function demarrerChrono() {
      if (!secondesInitiales || !chrono) return;
      chrono.textContent = formater(secondes);
      timer = window.setInterval(function () {
        secondes -= 1;
        if (secondes <= 60 && chronoCarte) chronoCarte.classList.add("is-urgent");
        if (secondes <= 0) {
          window.clearInterval(timer);
          chrono.textContent = "00:00";
          formulaire.querySelectorAll("[required]").forEach(function (champ) {
            champ.removeAttribute("required");
          });
          formulaire.requestSubmit();
          return;
        }
        chrono.textContent = formater(secondes);
      }, 1000);
    }

    document.addEventListener("keydown", function (event) {
      if (event.target && /input|textarea|select/i.test(event.target.tagName)) return;
      if ((event.key === "ArrowRight" || event.key === "j") && questions.length) {
        const courant = questions.findIndex(function (question) {
          return question.classList.contains("is-current");
        });
        afficherQuestion(Math.min(courant < 0 ? 0 : courant + 1, questions.length - 1));
      }
      if ((event.key === "ArrowLeft" || event.key === "k") && questions.length) {
        const courant = questions.findIndex(function (question) {
          return question.classList.contains("is-current");
        });
        afficherQuestion(Math.max(courant <= 0 ? 0 : courant - 1, 0));
      }
    });

    majProgression();
    if (adaptatif) {
      const premierNonRepondu = questions.findIndex(function (question) {
        return !question.querySelector("input[type=radio]:checked");
      });
      afficherQuestion(premierNonRepondu >= 0 ? premierNonRepondu : 0);
    } else {
      afficherQuestion(0);
    }
    demarrerChrono();
  }

  function initialiserVerificationTuteur() {
    const racine = document.querySelector("[data-tuteur-verification-session-id]");
    if (!racine) return;

    const sessionId = Number(racine.dataset.tuteurVerificationSessionId || 0);
    const statusEl = racine.querySelector("[data-tuteur-verification-status]");
    const labelEl = racine.querySelector("[data-tuteur-verification-label]");
    if (!sessionId || !statusEl) return;

    const fields = ["explication", "exemple", "exercice", "correction"];
    let essais = 0;
    const maxEssais = 10;

    // MODIF : applique maintenant le texte brut reçu par l'API via le renderer
    // sécurisé du navigateur ; aucun HTML IA n'est injecté directement.
    function appliquer(data) {
      if (!data || !data.statut) return;
      statusEl.className = "ai-verification-status is-" + data.statut;

      if (labelEl) {
        labelEl.textContent =
          data.statut === "terminee"
            ? "Vérification multi-modèles terminée"
            : data.statut === "echouee"
              ? "Réponse initiale conservée"
              : "Réponse générée · vérification multi-modèles en cours";
      }

      if (data.statut === "terminee" && data.contenu) {
        fields.forEach(function (champ) {
          const cible = racine.querySelector('[data-tuteur-content="' + champ + '"]');
          if (!cible || data.contenu[champ] == null) return;
          if (typeof window.rendreReponseIA !== "function") return;
          window.rendreReponseIA(data.contenu[champ], cible, { enLigne: false });
        });
      }
    }

    async function verifier() {
      try {
        const response = await fetch("/tuteur/" + sessionId + "/statut", {
          headers: {"X-Requested-With": "XMLHttpRequest"}
        });
        if (!response.ok) return;
        const data = await response.json();
        appliquer(data);

        if (
          (data.statut === "en_attente" || data.statut === "en_cours") &&
          essais < maxEssais
        ) {
          essais += 1;
          window.setTimeout(verifier, 1800);
        }
      } catch (_) {
        if (essais < maxEssais) {
          essais += 1;
          window.setTimeout(verifier, 2200);
        }
      }
    }

    if (
      statusEl.classList.contains("is-en_attente") ||
      statusEl.classList.contains("is-en_cours")
    ) {
      window.setTimeout(verifier, 700);
    }
  }

  function initialiserTuteur() {
    const textarea = document.querySelector("[data-tuteur-question]");
    const compteur = document.querySelector("[data-tuteur-count]");
    if (textarea && compteur) {
      const max = Number(textarea.getAttribute("maxlength") || 4000);
      const maj = function () {
        compteur.textContent = textarea.value.length + " / " + max;
      };
      textarea.addEventListener("input", maj);
      maj();
    }

    document.querySelectorAll("[data-tuteur-prompt]").forEach(function (bouton) {
      bouton.addEventListener("click", function () {
        const cible = document.querySelector("[data-tuteur-question]");
        if (!cible) return;
        cible.value = bouton.dataset.tuteurPrompt || "";
        cible.focus();
        cible.dispatchEvent(new Event("input", { bubbles: true }));
      });
    });

    document.querySelectorAll("[data-tuteur-form]").forEach(function (formulaire) {
      formulaire.addEventListener("submit", function () {
        const bouton = formulaire.querySelector("[data-tuteur-submit]");
        const chargement = formulaire.querySelector("[data-tuteur-loading]");
        if (bouton) {
          bouton.disabled = true;
          bouton.textContent = "Préparation…";
        }
        if (chargement) {
          chargement.hidden = false;
        }
      });
    });
  }

  function initialiser() {
    initialiserGenerationIA();
    initialiserQuiz();
    initialiserTuteur();
    initialiserVerificationTuteur();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialiser);
  } else {
    initialiser();
  }
})();
