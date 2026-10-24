import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { JSDOM } from "jsdom";

const script = readFileSync("app/static/js/notifications-center.js", "utf8");
const html = [
  '<main data-notifications-center>',
  '<input data-notification-search>',
  '<button data-notification-filter="all" aria-pressed="true">Toutes</button>',
  '<button data-notification-filter="unread" aria-pressed="false">Non lues</button>',
  '<button data-notification-filter="read" aria-pressed="false">Lues</button>',
  '<p data-notification-result-count aria-live="polite"></p>',
  '<article data-notification-card data-unread="true">Quiz de mathématiques</article>',
  '<article data-notification-card data-unread="false">Fiche de révision prête</article>',
  '<article data-notification-card data-unread="true">Nouveau message dans un cercle</article>',
  '<p data-notification-filter-empty hidden>Aucun résultat</p>',
  '</main>'
].join("");
const dom = new JSDOM(html, { runScripts: "outside-only" });
dom.window.eval(script);
const document = dom.window.document;
const cards = [...document.querySelectorAll("[data-notification-card]")];
const filters = [...document.querySelectorAll("[data-notification-filter]")];
const search = document.querySelector("[data-notification-search]");
assert.equal(cards.filter((card) => !card.hidden).length, 3);
assert.equal(document.querySelector("[data-notification-result-count]").textContent, "3 notifications affichées");
filters.find((button) => button.dataset.notificationFilter === "unread").click();
assert.equal(cards.filter((card) => !card.hidden).length, 2);
assert.equal(filters[1].getAttribute("aria-pressed"), "true");
search.value = "fiche";
search.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
assert.equal(cards.filter((card) => !card.hidden).length, 0);
assert.equal(document.querySelector("[data-notification-filter-empty]").hidden, false);
filters.find((button) => button.dataset.notificationFilter === "all").click();
assert.equal(cards.filter((card) => !card.hidden).length, 1);
assert.equal(cards.filter((card) => !card.hidden)[0].textContent, "Fiche de révision prête");
console.log("Notifications center smoke passed.");
