// Protection generique contre les doubles soumissions : desactive le(s)
// bouton(s) submit d'un formulaire des qu'il est valide et en cours
// d'envoi, pour eviter qu'un clic rapide (double-clic, ou re-clic par
// impatience sur connexion lente) ne cree une entree en double
// (cercle, message, inscription...). Aucun formulaire du site n'avait
// cette protection avant ce fichier.
//
// evenement.defaultPrevented exclut automatiquement, sans liste a
// maintenir, tout formulaire qui gere deja sa propre soumission en JS
// (ex. #form-chat en WebSocket dans cercle_chat.html, qui appelle
// preventDefault() en premiere ligne de son propre handler) : ce
// handler-ci est attache sur document (delegation, phase de bulles),
// donc il s'execute apres le onsubmit direct du formulaire -- si ce
// dernier a deja appele preventDefault() (validation refusee,
// interception WebSocket, mahayConfirmSubmit qui attend une
// confirmation...), defaultPrevented est deja vrai ici et on ne touche
// a rien.
//
// Echappatoire explicite : data-pas-de-blocage-auto sur le <form> pour
// les cas futurs qui ne rentreraient pas dans ce schema.
(function () {
  document.addEventListener("submit", function (evenement) {
    if (evenement.defaultPrevented) return;
    const formulaire = evenement.target;
    if (formulaire.dataset.pasDeBlocageAuto !== undefined) return;
    formulaire.querySelectorAll('button[type="submit"], input[type="submit"]').forEach(function (bouton) {
      bouton.disabled = true;
    });
  });
})();
