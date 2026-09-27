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
    let secondes = secondesInitiales;
    let timer = null;

    function reponsesCount() {
      return questions.reduce(function (totalCourant, question) {
        return totalCourant + (question.querySelector("input[type=radio]:checked") ? 1 : 0);
      }, 0);
    }

    function majProgression() {
      const repondues = reponsesCount();
      const pourcentage = total ? (repondues / total) * 100 : 0;
      if (texte) texte.textContent = repondues + " / " + total + " répondues";
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
      cible.scrollIntoView({ behavior: "smooth", block: "start" });
      questions.forEach(function (question) {
        question.classList.toggle("is-current", question === cible);
      });
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
          afficherQuestion(index);
        });
        nav.appendChild(bouton);
      });
    }

    formulaire.addEventListener("change", function () {
      majProgression();
    });

    formulaire.addEventListener("submit", function () {
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
    afficherQuestion(0);
    demarrerChrono();
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
        if (bouton) {
          bouton.disabled = true;
          bouton.textContent = "Le tuteur réfléchit…";
        }
      });
    });
  }

  function initialiser() {
    initialiserGenerationIA();
    initialiserQuiz();
    initialiserTuteur();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialiser);
  } else {
    initialiser();
  }
})();
