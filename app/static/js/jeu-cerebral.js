(function () {
  "use strict";
  var root = document.querySelector(".jeu-cerebral-page, .jeu-session-page, .jeu-result-page");
  if (!root) return;

  var motionKey = "mitaridala-jeu-reduire-animations";
  var motionToggle = root.querySelector("#jeu-reduire-animations, #jeu-reduire-animations-session, #jeu-reduire-animations-resultat");
  var prefersQuiet = false;
  try { prefersQuiet = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches); } catch (_) {}
  function readMotionPreference() {
    try {
      var stored = window.localStorage.getItem(motionKey);
      return stored === null ? prefersQuiet : stored === "1";
    } catch (_) { return prefersQuiet; }
  }
  function applyMotionPreference(value) {
    root.classList.toggle("jeu-reduit-mouvement", !!value);
    if (motionToggle) motionToggle.checked = !!value;
  }
  applyMotionPreference(readMotionPreference());
  if (motionToggle) {
    motionToggle.addEventListener("change", function () {
      try { window.localStorage.setItem(motionKey, motionToggle.checked ? "1" : "0"); } catch (_) {}
      applyMotionPreference(motionToggle.checked);
    });
  }

  var partieId = root.getAttribute("data-partie-id");
  if (root.getAttribute("data-session-terminee") === "true" && partieId) {
    try {
      ["deadline", "paused", "pause-at"].forEach(function (suffix) {
        window.sessionStorage.removeItem("mitaridala:jeu:" + partieId + ":" + suffix);
      });
    } catch (_) {}
  }

  var pauseButton = root.querySelector("#jeu-pause-toggle");
  var pauseNotice = root.querySelector("#jeu-pause-notice");
  var pauseStatus = root.querySelector("#jeu-pause-status");
  var answerForm = root.querySelector("#form-reponse-jeu");
  var answerFieldset = answerForm && answerForm.querySelector("fieldset");
  var submitButton = root.querySelector("#envoyer-reponse");
  var timerPanel = root.querySelector("#jeu-chrono-panel");
  var timerValue = root.querySelector("#jeu-chrono-valeur");
  var timerMessage = root.querySelector("#jeu-chrono-message");
  var timerActive = root.getAttribute("data-chrono-actif") === "true";
  var language = root.getAttribute("data-langue") || "fr";
  var paused = false;
  var deadlineKey = partieId ? "mitaridala:jeu:" + partieId + ":deadline" : "";
  var pausedKey = partieId ? "mitaridala:jeu:" + partieId + ":paused" : "";
  var pauseAtKey = partieId ? "mitaridala:jeu:" + partieId + ":pause-at" : "";
  var deadline = 0;
  var interval = null;
  var limitSeconds = 150;

  function storageRead(key) {
    try { return key ? window.sessionStorage.getItem(key) : null; } catch (_) { return null; }
  }
  function storageWrite(key, value) {
    try { if (key) window.sessionStorage.setItem(key, String(value)); } catch (_) {}
  }
  function storageRemove(key) {
    try { if (key) window.sessionStorage.removeItem(key); } catch (_) {}
  }
  function announcePause(text) {
    if (pauseStatus) pauseStatus.textContent = text;
  }
  function formatSeconds(seconds) {
    var safe = Math.max(0, Math.ceil(seconds));
    return String(Math.floor(safe / 60)).padStart(2, "0") + ":" + String(safe % 60).padStart(2, "0");
  }
  function pauseCopy(isPaused) {
    if (!pauseButton) return;
    pauseButton.textContent = isPaused
      ? (language === "mg" ? "Tohizo ny lalao" : "Reprendre le défi")
      : (language === "mg" ? "Miato kely" : "Mettre en pause");
    pauseButton.setAttribute("aria-pressed", isPaused ? "true" : "false");
    if (pauseNotice) pauseNotice.hidden = !isPaused;
    if (answerFieldset) answerFieldset.disabled = isPaused;
    if (submitButton) submitButton.disabled = isPaused;
    root.classList.toggle("jeu-session-en-pause", isPaused);
    announcePause(isPaused
      ? (language === "mg" ? "Miato ny lalao." : "Défi en pause.")
      : (language === "mg" ? "Mitohy ny lalao." : "Défi repris."));
  }
  function readDeadline() {
    var stored = Number(storageRead(deadlineKey));
    return Number.isFinite(stored) && stored > 0 ? stored : 0;
  }
  function updateTimer() {
    if (!timerActive || !timerValue) return;
    var end = deadline || readDeadline();
    var pauseAt = Number(storageRead(pauseAtKey));
    var now = paused && pauseAt > 0 ? pauseAt : Date.now();
    var remaining = Math.max(0, (end - now) / 1000);
    timerValue.textContent = formatSeconds(remaining);
    if (remaining <= 0) {
      if (timerPanel) timerPanel.classList.add("jeu-chrono-ecoule");
      if (timerMessage) timerMessage.textContent = language === "mg"
        ? "Tapitra ny fotoana kendrena — tohizo am-pitoniana."
        : "Temps cible écoulé — tu peux continuer tranquillement.";
      if (interval) { window.clearInterval(interval); interval = null; }
    }
  }
  function startTimer() {
    if (!timerActive || !timerPanel || !timerValue || !partieId) return;
    if (!deadline) deadline = readDeadline();
    if (!deadline) {
      deadline = Date.now() + limitSeconds * 1000;
      storageWrite(deadlineKey, deadline);
    }
    timerPanel.hidden = false;
    updateTimer();
    if (!paused && !interval && readDeadline() > Date.now()) {
      interval = window.setInterval(updateTimer, 1000);
    }
  }
  function togglePause() {
    paused = !paused;
    if (paused) {
      storageWrite(pausedKey, "1");
      storageWrite(pauseAtKey, Date.now());
      if (interval) { window.clearInterval(interval); interval = null; }
    } else {
      var pauseAt = Number(storageRead(pauseAtKey));
      if (timerActive && pauseAt > 0) {
        deadline = Math.max(deadline, readDeadline()) + Math.max(0, Date.now() - pauseAt);
        storageWrite(deadlineKey, deadline);
      }
      storageRemove(pausedKey);
      storageRemove(pauseAtKey);
    }
    pauseCopy(paused);
    updateTimer();
    if (!paused) startTimer();
  }

  if (pauseButton) {
    paused = storageRead(pausedKey) === "1";
    if (paused && !storageRead(pauseAtKey)) storageWrite(pauseAtKey, Date.now());
    pauseCopy(paused);
    pauseButton.addEventListener("click", togglePause);
  }
  if (timerActive) startTimer();
})();