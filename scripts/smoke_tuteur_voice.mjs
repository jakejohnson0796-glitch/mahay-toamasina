import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";

const root = process.cwd();
const read = (p) => fs.readFileSync(path.join(root, p), "utf8");
const script = read("app/static/js/lecture-tuteur.js");
const template = read("app/templates/tuteur_reponse.html");

assert.match(template, /data-lecture-tout/);
assert.match(template, /data-lecture-pause/);
assert.match(template, /data-lecture-reprendre/);
assert.match(template, /data-lecture-arreter/);
assert.match(template, /data-lecture-cible="correction"/);

const html = [
  '<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body>',
  '<main class="ai-learning-page">',
  '<section data-tuteur-lecture aria-label="Lecture vocale">',
  '<button type="button" data-lecture-tout>Écouter toute la réponse</button>',
  '<button type="button" data-lecture-pause disabled>Pause</button>',
  '<button type="button" data-lecture-reprendre disabled>Reprendre</button>',
  '<button type="button" data-lecture-arreter disabled>Arrêter</button>',
  '<select data-lecture-voix aria-label="Choisir une voix"><option value="">Voix automatique</option></select>',
  '<select data-lecture-vitesse><option value="1" selected>Normale</option></select>',
  '<p data-lecture-statut role="status" aria-live="polite">Prêt à lire.</p>',
  '</section>',
  '<article><h2>Explication</h2>',
  '<button type="button" data-lecture-cible="explication">Écouter</button>',
  '<div data-tuteur-content="explication"><p>La fraction ',
  '<span class="katex"><span class="katex-mathml"><math><semantics><mfrac><mn>12</mn><mn>18</mn></mfrac><annotation encoding="application/x-tex">\\frac{12}{18}</annotation></semantics></math></span><span class="katex-html" aria-hidden="true">12 sur 18</span></span>',
  ' se simplifie. Le résultat est deux tiers.</p><pre>console.log("ne pas lire ce code")</pre></div></article>',
  '<article><h2>Exemple</h2><div data-tuteur-content="exemple"><p>Exemple : trois quarts égale zéro virgule soixante-quinze.</p></div></article>',
  '<details><summary>Afficher la correction</summary>',
  '<button type="button" data-lecture-cible="correction">Écouter la correction</button>',
  '<div data-tuteur-content="correction"><p>Correction cachée : on divise le numérateur et le dénominateur par six.</p></div>',
  '</details></main></body></html>'
].join("");

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  await page.addInitScript(() => {
    const utterances = [];
    const voices = [
      { name: "French Test Voice", lang: "fr-FR", default: true, localService: true }
    ];
    class MockUtterance {
      constructor(text) { this.text = text; this.lang = ""; this.rate = 1; this.pitch = 1; }
    }
    const mock = {
      utterances,
      cancelCount: 0,
      pauseCount: 0,
      resumeCount: 0,
      paused: false,
      speaking: false,
      getVoices() { return voices; },
      speak(utterance) { utterances.push(utterance); this.speaking = true; },
      cancel() { this.cancelCount += 1; this.speaking = false; this.paused = false; },
      pause() { this.pauseCount += 1; this.paused = true; },
      resume() { this.resumeCount += 1; this.paused = false; },
      addEventListener() {}
    };
    Object.defineProperty(window, "speechSynthesis", { configurable: true, value: mock });
    window.SpeechSynthesisUtterance = MockUtterance;
    window.__speechMock = mock;
  });
  await page.setContent(html);
  await page.addScriptTag({ content: script });
  await page.waitForFunction(() =>
    Array.from(document.querySelector("[data-lecture-voix]").options).some((o) => o.value === "0")
  );

  await page.locator("[data-lecture-tout]").click();
  const premiereLecture = await page.evaluate(() => ({
    text: window.__speechMock.utterances.map((u) => u.text).join(" "),
    voice: window.__speechMock.utterances[0]?.voice?.name || null,
    rate: window.__speechMock.utterances[0]?.rate,
    pauseEnabled: !document.querySelector("[data-lecture-pause]").disabled,
    stopEnabled: !document.querySelector("[data-lecture-arreter]").disabled
  }));
  assert.match(premiereLecture.text, /fraction 12 sur 18/i);
  assert.match(premiereLecture.text, /deux tiers/i);
  assert.match(premiereLecture.text, /Exemple/i);
  assert.doesNotMatch(premiereLecture.text, /\\frac|\\\[|\\\(/);
  assert.doesNotMatch(premiereLecture.text, /console\.log|ne pas lire ce code/i);
  assert.doesNotMatch(premiereLecture.text, /Correction cachée/i, "Une correction repliée ne doit pas être lue.");
  assert.equal(premiereLecture.pauseEnabled, true);
  assert.equal(premiereLecture.stopEnabled, true);

  await page.locator("[data-lecture-pause]").click();
  assert.equal(await page.evaluate(() => window.__speechMock.pauseCount), 1);
  assert.equal(await page.locator("[data-lecture-reprendre]").isEnabled(), true);
  await page.locator("[data-lecture-reprendre]").click();
  assert.equal(await page.evaluate(() => window.__speechMock.resumeCount), 1);
  await page.locator("[data-lecture-arreter]").click();
  assert.equal(await page.evaluate(() => window.__speechMock.cancelCount > 0), true);
  assert.equal(await page.locator("[data-lecture-arreter]").isDisabled(), true);

  await page.evaluate(() => { window.__speechMock.utterances.length = 0; });
  await page.locator('[data-lecture-cible="explication"]').click();
  const sectionSeule = await page.evaluate(() => window.__speechMock.utterances.map((u) => u.text).join(" "));
  assert.match(sectionSeule, /deux tiers/i);
  assert.doesNotMatch(sectionSeule, /Exemple|Correction cachée/i);

  await page.evaluate(() => {
    window.__speechMock.cancel();
    window.__speechMock.utterances.length = 0;
    document.querySelector("details").open = true;
  });
  await page.locator("[data-lecture-tout]").click();
  const correctionOuverte = await page.evaluate(() => window.__speechMock.utterances.map((u) => u.text).join(" "));
  assert.match(correctionOuverte, /Correction cachée/i);

  console.log(JSON.stringify({
    checks: [
      "formule fractionnée en paroles lisibles",
      "code source exclu de la lecture",
      "correction repliée non lue",
      "lecture globale et par section",
      "pause, reprise et arrêt",
      "correction incluse uniquement lorsqu'elle est ouverte"
    ]
  }, null, 2));
} finally {
  await browser.close();
}
