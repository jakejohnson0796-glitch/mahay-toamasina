/* Boutons visuels du sélecteur de langue.
 * La sélection native reste la source de vérité pour langue.js ; un clic
 * émet son événement change habituel afin de mémoriser la langue et traduire.
 */
(function () {
  "use strict";

  const select = document.getElementById("select-langue");
  const boutons = Array.from(document.querySelectorAll("[data-langue-choix]"));
  if (!select || !boutons.length) return;

  function synchroniser() {
    const langue = select.value === "mg" ? "mg" : "fr";
    boutons.forEach(function (bouton) {
      const actif = bouton.dataset.langueChoix === langue;
      bouton.setAttribute("aria-pressed", actif ? "true" : "false");
    });
  }

  boutons.forEach(function (bouton) {
    bouton.addEventListener("click", function () {
      const langue = bouton.dataset.langueChoix;
      if (langue !== "fr" && langue !== "mg") return;
      if (select.value !== langue) {
        select.value = langue;
        select.dispatchEvent(new Event("change", { bubbles: true }));
      }
      synchroniser();
    });
  });

  select.addEventListener("change", synchroniser);
  synchroniser();
})();
