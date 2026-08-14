// Navigation principale : mega-menu (desktop) + accordeon (mobile) +
// menu mobile complet. Deplace hors de base.html pour garder les
// templates legers (voir §19 du brief refonte UI/UX).
(function () {
  const bouton = document.getElementById("bouton-menu-mobile");
  const nav = document.getElementById("nav-principale");
  if (!bouton || !nav) return;

  const declencheurs = Array.from(nav.querySelectorAll(".mega-trigger"));

  function estMobile() {
    return window.matchMedia("(max-width: 768px)").matches;
  }

  function fermerPanneau(declencheur) {
    declencheur.setAttribute("aria-expanded", "false");
    const panneau = document.getElementById(declencheur.getAttribute("aria-controls"));
    if (panneau) panneau.hidden = true;
  }

  function fermerTousLesPanneaux(sauf) {
    declencheurs.forEach(function (d) {
      if (d !== sauf) fermerPanneau(d);
    });
  }

  function ouvrirPanneau(declencheur) {
    declencheur.setAttribute("aria-expanded", "true");
    const panneau = document.getElementById(declencheur.getAttribute("aria-controls"));
    if (panneau) panneau.hidden = false;
  }

  declencheurs.forEach(function (declencheur) {
    // Desktop : clic ouvre/ferme ce panneau et ferme les autres (un seul
    // ouvert a la fois). Mobile : fonctionne comme un accordeon simple,
    // plusieurs sections peuvent rester ouvertes en meme temps — plus
    // naturel au doigt qu'un menu qui se referme sans cesse.
    declencheur.addEventListener("click", function () {
      const dejaOuvert = declencheur.getAttribute("aria-expanded") === "true";
      if (!estMobile()) fermerTousLesPanneaux(declencheur);
      if (dejaOuvert) {
        fermerPanneau(declencheur);
      } else {
        ouvrirPanneau(declencheur);
      }
    });
  });

  // Echap referme tout et rend le focus au bouton concerne, plutot que
  // de le perdre quelque part dans la page.
  document.addEventListener("keydown", function (evenement) {
    if (evenement.key === "Escape") {
      const ouvert = declencheurs.find(function (d) { return d.getAttribute("aria-expanded") === "true"; });
      fermerTousLesPanneaux(null);
      if (ouvert) ouvert.focus();
    }
  });

  // Clic en dehors de la nav referme les panneaux ouverts (comportement
  // desktop habituel d'un mega menu).
  document.addEventListener("click", function (evenement) {
    if (!nav.contains(evenement.target)) fermerTousLesPanneaux(null);
  });

  bouton.addEventListener("click", function () {
    const ouvert = nav.classList.toggle("nav-ouverte");
    bouton.setAttribute("aria-expanded", ouvert ? "true" : "false");
    if (!ouvert) fermerTousLesPanneaux(null);
  });

  // Les vrais liens (pas les boutons declencheurs) referment le menu
  // mobile complet apres selection, pour ne pas le laisser ouvert
  // par-dessus la page suivante.
  nav.querySelectorAll("a").forEach(function (lien) {
    lien.addEventListener("click", function () {
      nav.classList.remove("nav-ouverte");
      bouton.setAttribute("aria-expanded", "false");
      fermerTousLesPanneaux(null);
    });
  });

  // Header compact au scroll : impression plus "produit SaaS", sans
  // rien casser du comportement existant (§8 du brief).
  const entete = document.querySelector(".entete");
  if (entete) {
    let dernierEtat = false;
    function surScroll() {
      const compact = window.scrollY > 24;
      if (compact !== dernierEtat) {
        entete.classList.toggle("entete-compacte", compact);
        dernierEtat = compact;
      }
    }
    window.addEventListener("scroll", surScroll, { passive: true });
    surScroll();
  }
})();
