// Etape 1 (sidebar globale) du brief de refonte visuelle : remplace la
// logique de l'ancien mega-menu (accordeon desktop/mobile, disparu avec
// components/mega_menu.html) par l'ouverture/fermeture du drawer mobile
// de la nouvelle sidebar globale (.tb-sidebar, incluse par base.html).
(function () {
  function initMenuCompte() {
    const bouton = document.getElementById("bouton-menu-compte");
    const menu = document.getElementById("menu-compte-utilisateur");
    if (!bouton || !menu) return;

    function fermer() {
      if (menu.hidden) return;
      menu.hidden = true;
      bouton.setAttribute("aria-expanded", "false");
    }

    function ouvrir() {
      menu.hidden = false;
      bouton.setAttribute("aria-expanded", "true");
    }

    bouton.addEventListener("click", function (evenement) {
      evenement.stopPropagation();
      if (menu.hidden) ouvrir(); else fermer();
    });

    menu.addEventListener("click", function (evenement) {
      evenement.stopPropagation();
    });

    menu.querySelectorAll("a, button[type='submit']").forEach(function (element) {
      element.addEventListener("click", function () {
        window.setTimeout(fermer, 0);
      });
    });

    document.addEventListener("click", fermer);
    document.addEventListener("keydown", function (evenement) {
      if (evenement.key === "Escape") fermer();
    });

    window.addEventListener("resize", fermer);
  }

  initMenuCompte();
  const bouton = document.getElementById("bouton-menu-mobile");
  const sidebar = document.getElementById("nav-principale");
  const overlay = document.getElementById("sidebar-overlay");
  if (!bouton || !sidebar || !overlay) return;

  function ouvrir() {
    sidebar.classList.add("tb-sidebar-ouverte");
    overlay.classList.add("sidebar-overlay-visible");
    document.body.classList.add("sidebar-menu-ouvert");
    document.documentElement.setAttribute("data-sidebar-ouvert", "true");
    bouton.setAttribute("aria-expanded", "true");
    // Le premier lien recoit le focus : au clavier/lecteur d'ecran, on
    // atterrit directement dans le menu qui vient de s'ouvrir plutot que
    // de laisser le focus sur un bouton desormais hors du flux visuel
    // (piege deja evite ailleurs dans ce fichier pour le fil de discussion).
    const premierLien = sidebar.querySelector("a");
    if (premierLien) premierLien.focus();
  }

  function fermer(rendreFocusAuBouton) {
    sidebar.classList.remove("tb-sidebar-ouverte");
    overlay.classList.remove("sidebar-overlay-visible");
    document.body.classList.remove("sidebar-menu-ouvert");
    document.documentElement.removeAttribute("data-sidebar-ouvert");
    bouton.setAttribute("aria-expanded", "false");
    if (rendreFocusAuBouton) bouton.focus();
  }

  function estOuvert() {
    return sidebar.classList.contains("tb-sidebar-ouverte");
  }

  bouton.addEventListener("click", function () {
    if (estOuvert()) {
      fermer(false);
    } else {
      ouvrir();
    }
  });

  overlay.addEventListener("click", function () {
    fermer(false);
  });

  // Echap referme le drawer et rend le focus au bouton hamburger, pour ne
  // pas perdre le focus clavier quelque part dans une sidebar masquee.
  document.addEventListener("keydown", function (evenement) {
    if (evenement.key === "Escape" && estOuvert()) {
      fermer(true);
    }
  });

  // Un clic sur un vrai lien (pas un simple survol) referme le drawer,
  // pour ne pas le laisser ouvert par-dessus la page suivante.
  sidebar.querySelectorAll("a").forEach(function (lien) {
    lien.addEventListener("click", function () {
      if (estOuvert()) fermer(false);
    });
  });

  // Si la fenetre repasse au-dessus du seuil mobile (rotation tablette,
  // redimensionnement), on referme proprement plutot que de laisser un
  // etat "ouvert" incoherent une fois le drawer redevenu une sidebar fixe.
  window.addEventListener("resize", function () {
    if (window.matchMedia("(min-width: 769px)").matches && estOuvert()) {
      fermer(false);
    }
  });
})();
