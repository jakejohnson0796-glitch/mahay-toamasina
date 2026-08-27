/*
Bascule clair/sombre. Le theme AU CHARGEMENT est deja pose par le
script inline bloquant dans <head> de base.html (evite le flash du
mauvais theme) -- ce fichier ne gere que le CLIC sur le bouton.
*/
(function () {
  var CLE_STOCKAGE = "mahay-theme";
  var bouton = document.getElementById("bouton-theme");
  if (!bouton) return; // page sans sidebar connectee (visiteur non connecte) : rien a cabler

  bouton.addEventListener("click", function () {
    var actuel = document.documentElement.getAttribute("data-theme") === "sombre" ? "sombre" : "clair";
    var suivant = actuel === "sombre" ? "clair" : "sombre";
    document.documentElement.setAttribute("data-theme", suivant);
    try {
      localStorage.setItem(CLE_STOCKAGE, suivant);
    } catch (erreur) {
      /* stockage indisponible : le theme choisi vaut pour cette page seulement, pas de risque, pas d'erreur bloquante */
    }
  });
})();
