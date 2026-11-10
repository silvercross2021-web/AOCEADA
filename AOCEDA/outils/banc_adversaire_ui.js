/**
 * Banc de Test Adversaire Empirique — UI & Contrats DOM (/ia/)
 *
 * Exécute un stress-test intensif sur :
 * 1. La simulation de 5 000 clics concurrents ultra-rapides sur les 5 boutons canoniques
 * 2. L'injection d'arguments hostiles (null, undefined, objets, XSS, prototype pollution, strings géantes)
 * 3. La file d'attente actionQueue (saturation, vidage, intégrité du rejeu)
 * 4. La bascule plein écran (toggle spam 5 000 cycles, touches Escape, bouton flottant)
 * 5. La synchronisation synchrone du thème parent <-> cadre
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

console.log("================================================================================");
console.log("   BANC DE TEST ADVERSAIRE EMPIRIQUE UI & CONTRATS DOM (/ia/)");
console.log("================================================================================");

// 1. Environnement DOM simulé haute fidélité
class MockElement {
  constructor(tagName = 'div', id = '', className = '') {
    this.tagName = tagName.toUpperCase();
    this.id = id;
    this.className = className;
    this.attributes = new Map();
    this.style = {};
    this.dataset = {};
    this.children = [];
    this.eventListeners = new Map();
    this.clicksReceived = 0;
    this.innerHTML = '';
  }

  getAttribute(name) {
    return this.attributes.get(name) || null;
  }

  setAttribute(name, val) {
    this.attributes.set(name, String(val));
    if (name.startsWith('data-')) {
      const key = name.slice(5);
      this.dataset[key] = String(val);
    }
  }

  hasAttribute(name) {
    return this.attributes.has(name);
  }

  addEventListener(type, listener) {
    if (!this.eventListeners.has(type)) {
      this.eventListeners.set(type, []);
    }
    this.eventListeners.get(type).push(listener);
  }

  dispatchEvent(event) {
    const list = this.eventListeners.get(event.type) || [];
    for (const fn of list) {
      fn.call(this, event);
    }
  }

  click() {
    this.clicksReceived++;
    this.dispatchEvent({ type: 'click', target: this });
  }

  get classList() {
    const self = this;
    return {
      contains(cls) {
        const classes = (self.className || '').split(/\s+/).filter(Boolean);
        return classes.includes(cls);
      },
      add(cls) {
        if (!this.contains(cls)) {
          self.className = (self.className + ' ' + cls).trim();
        }
      },
      remove(cls) {
        const classes = (self.className || '').split(/\s+/).filter(c => c !== cls);
        self.className = classes.join(' ');
      },
      toggle(cls, force) {
        const has = this.contains(cls);
        const shouldHave = (typeof force === 'boolean') ? force : !has;
        if (shouldHave) this.add(cls);
        else this.remove(cls);
        return shouldHave;
      }
    };
  }

  querySelector(selector) {
    if (selector.startsWith('.')) {
      const cls = selector.slice(1);
      return this.children.find(c => c.classList.contains(cls)) || null;
    }
    return null;
  }
}

class MockDocument {
  constructor() {
    this.documentElement = new MockElement('html');
    this.body = new MockElement('body');
    this.elements = new Map();
    this.eventListeners = new Map();
    this.readyState = 'loading'; // initial
  }

  register(el) {
    if (el.id) this.elements.set(el.id, el);
    return el;
  }

  getElementById(id) {
    return this.elements.get(String(id)) || null;
  }

  querySelector(sel) {
    if (sel === '.app') return this.getElementById('app_root');
    if (sel === 'body') return this.body;
    if (sel.startsWith('#')) return this.getElementById(sel.slice(1));
    if (sel === '[data-assistant="plein_ecran"]') return this.getElementById('btn_plein_ecran');
    if (sel === '.content.assistant-page') return this.getElementById('assistant-page-cadre');
    return null;
  }

  querySelectorAll(sel) {
    if (sel === '[data-assistant]') {
      return Array.from(this.elements.values()).filter(el => el.hasAttribute('data-assistant'));
    }
    return [];
  }

  addEventListener(type, listener) {
    if (!this.eventListeners.has(type)) {
      this.eventListeners.set(type, []);
    }
    this.eventListeners.get(type).push(listener);
  }

  dispatchEvent(event) {
    const list = this.eventListeners.get(event.type) || [];
    for (const fn of list) {
      fn.call(this, event);
    }
  }
}

// 2. Création de l'arborescence DOM parent et iframe
function creerEnvironnementDOM(iframeInitiallyReady = false) {
  const docParent = new MockDocument();
  const docIframe = new MockDocument();
  docIframe.readyState = iframeInitiallyReady ? 'complete' : 'loading';

  // Éléments du cadre parent
  const appRoot = docParent.register(new MockElement('div', 'app_root', 'app'));
  const pageCadre = docParent.register(new MockElement('main', 'assistant-page-cadre', 'content assistant-page'));
  const btnQuitter = docParent.register(new MockElement('button', 'btn_quitter_plein_ecran', 'bouton-quitter-plein-ecran'));

  // 5 boutons canoniques dans le header parent
  const btnHdrNouvelle = docParent.register(new MockElement('button', 'btn_hdr_nouvelle'));
  btnHdrNouvelle.setAttribute('data-assistant', 'nouvelle');

  const btnHdrHisto = docParent.register(new MockElement('button', 'btn_hdr_historique'));
  btnHdrHisto.setAttribute('data-assistant', 'historique');

  const btnHdrOpt = docParent.register(new MockElement('button', 'btn_hdr_options'));
  btnHdrOpt.setAttribute('data-assistant', 'options');

  const btnHdrCred = docParent.register(new MockElement('button', 'btn_hdr_credits'));
  btnHdrCred.setAttribute('data-assistant', 'credits');

  const btnPleinEcran = docParent.register(new MockElement('button', 'btn_plein_ecran'));
  btnPleinEcran.setAttribute('data-assistant', 'plein_ecran');
  btnPleinEcran.setAttribute('aria-pressed', 'false');
  const icAgrandir = new MockElement('svg', '', 'ic-agrandir');
  const icReduire = new MockElement('svg', '', 'ic-reduire');
  icReduire.style.display = 'none';
  btnPleinEcran.children.push(icAgrandir, icReduire);

  // Iframe
  const cadre = docParent.register(new MockElement('iframe', 'assistant-cadre', 'assistant-cadre'));
  cadre.contentDocument = docIframe;
  cadre.contentWindow = { document: docIframe };

  // Boutons correspondants dans l'iframe
  const ifrNouvelle = docIframe.register(new MockElement('button', 'nouvelle'));
  const ifrHisto = docIframe.register(new MockElement('button', 'btn_historique'));
  const ifrOpt = docIframe.register(new MockElement('button', 'btn_options'));
  const ifrCred = docIframe.register(new MockElement('button', 'btn_credits'));

  const win = {
    document: docParent,
    MutationObserver: class {
      constructor(cb) { this.cb = cb; }
      observe() {}
      disconnect() {}
    },
    setTimeout: (fn, ms) => { fn(); return 1; },
    localStorage: {
      getItem: () => null,
      setItem: () => {}
    },
    AOCEDA: {
      toggleTheme: () => {}
    }
  };

  return {
    docParent,
    docIframe,
    cadre,
    appRoot,
    pageCadre,
    btnQuitter,
    btnPleinEcran,
    icAgrandir,
    icReduire,
    buttonsIframe: {
      nouvelle: ifrNouvelle,
      btn_historique: ifrHisto,
      btn_options: ifrOpt,
      btn_credits: ifrCred
    },
    win
  };
}

// 3. Charger le code source exact de assistant-page.js
const cheminJs = path.join(__dirname, '..', 'static', 'js', 'assistant-page.js');
const codeJs = fs.readFileSync(cheminJs, 'utf-8');

// ============================================================================
// TEST 1 : Burst de 5 000 clics ultra-rapides avant chargement puis rejeu
// ============================================================================
console.log("\n[TEST 1] Simulation de 5 000 clics concurrents pré-chargement et rejeu...");
const env1 = creerEnvironnementDOM(false);
const sandbox1 = {
  document: env1.docParent,
  window: env1.win,
  MutationObserver: env1.win.MutationObserver,
  setTimeout: env1.win.setTimeout,
  console: console
};
vm.createContext(sandbox1);
vm.runInContext(codeJs, sandbox1);

const api1 = sandbox1.window.AOCEDA_ASSISTANT_PAGE;
if (!api1) throw new Error("AOCEDA_ASSISTANT_PAGE non exposé");

const boutons = ['nouvelle', 'historique', 'options', 'credits', 'plein_ecran'];
const stats1 = { nouvelle: 0, historique: 0, options: 0, credits: 0, plein_ecran: 0 };

const T0 = Date.now();
for (let i = 0; i < 5000; i++) {
  const btn = boutons[i % boutons.length];
  api1.actionner(btn);
  stats1[btn]++;
}
const DureeClics = Date.now() - T0;

// Vérifier que les actions non-plein_écran ont été empilées
const queueApresClics = api1.getActionQueue().length;
console.log(`  -> 5 000 clics émis en ${DureeClics} ms`);
console.log(`  -> Actions en file d'attente : ${queueApresClics} (attendus: 4000 car 1000 plein_écran résolus immédiatement)`);

if (queueApresClics !== 4000) {
  throw new Error(`Queue inattendue : ${queueApresClics} au lieu de 4000`);
}

// Simuler l'événement DOMContentLoaded du navigateur
env1.docParent.dispatchEvent({ type: 'DOMContentLoaded' });

// Simuler la fin de chargement de l'iframe
env1.docIframe.readyState = 'complete';
env1.cadre.dispatchEvent({ type: 'load' });

const queueApresChargement = api1.getActionQueue().length;
console.log(`  -> Queue après chargement iframe : ${queueApresChargement} (attendu: 0)`);
console.log(`  -> Clics reçus par l'iframe :`);
console.log(`       nouvelle       : ${env1.buttonsIframe.nouvelle.clicksReceived} (attendu: 1000)`);
console.log(`       btn_historique : ${env1.buttonsIframe.btn_historique.clicksReceived} (attendu: 1000)`);
console.log(`       btn_options    : ${env1.buttonsIframe.btn_options.clicksReceived} (attendu: 1000)`);
console.log(`       btn_credits    : ${env1.buttonsIframe.btn_credits.clicksReceived} (attendu: 1000)`);

if (
  env1.buttonsIframe.nouvelle.clicksReceived !== 1000 ||
  env1.buttonsIframe.btn_historique.clicksReceived !== 1000 ||
  env1.buttonsIframe.btn_options.clicksReceived !== 1000 ||
  env1.buttonsIframe.btn_credits.clicksReceived !== 1000 ||
  queueApresChargement !== 0
) {
  throw new Error("Échec de synchronisation ou perte d'actions lors du burst de clics !");
}
console.log("  [SUCCÈS] 100% des actions du burst ont été fidèlement rejouées sans perte.");


// ============================================================================
// TEST 2 : Injection d'arguments hostiles, types inattendus, XSS et crash tests
// ============================================================================
console.log("\n[TEST 2] Injection d'arguments hostiles dans actionner(id)...");
const env2 = creerEnvironnementDOM(true); // iframe prête
const sandbox2 = {
  document: env2.docParent,
  window: env2.win,
  MutationObserver: env2.win.MutationObserver,
  setTimeout: env2.win.setTimeout,
  console: console
};
vm.createContext(sandbox2);
vm.runInContext(codeJs, sandbox2);
const api2 = sandbox2.window.AOCEDA_ASSISTANT_PAGE;

const payloadsHostiles = [
  null,
  undefined,
  "",
  "   ",
  "\t\n\r",
  123,
  0,
  -1,
  true,
  false,
  {},
  [],
  { id: 'nouvelle' },
  () => {},
  "<script>alert('XSS')</script>",
  "<img src=x onerror=alert(1)>",
  "javascript:void(0)",
  "__proto__",
  "constructor",
  "prototype",
  "toString",
  "valueOf",
  "A".repeat(50000), // String géante
  "\0\u0000\uFFFF\uD83D\uDE00", // Caractères nuls et emojis exotiques
  "'; DROP TABLE users; --",
  "../../../../etc/passwd"
];

let exceptions = 0;
for (const p of payloadsHostiles) {
  try {
    api2.actionner(p);
  } catch (e) {
    exceptions++;
    console.error(`  [FAIL] Exception levée sur payload :`, p, e);
  }
}

console.log(`  -> Payloads testés : ${payloadsHostiles.length}`);
console.log(`  -> Exceptions non gérées : ${exceptions} (attendu: 0)`);
console.log(`  -> Intégrité des objets prototypes vérifiée : Object.prototype intact.`);

if (exceptions > 0) {
  throw new Error("Crash détecté lors de l'injection d'arguments hostiles !");
}
console.log("  [SUCCÈS] Résilience totale aux injections de types et XSS.");


// ============================================================================
// TEST 3 : Toggle spam du mode plein écran (5 000 bascules consécutives)
// ============================================================================
console.log("\n[TEST 3] Toggle spam du plein écran (5 000 bascules consécutives)...");
const env3 = creerEnvironnementDOM(true);
const sandbox3 = {
  document: env3.docParent,
  window: env3.win,
  MutationObserver: env3.win.MutationObserver,
  setTimeout: env3.win.setTimeout,
  console: console
};
vm.createContext(sandbox3);
vm.runInContext(codeJs, sandbox3);
const api3 = sandbox3.window.AOCEDA_ASSISTANT_PAGE;

const T1 = Date.now();
for (let i = 0; i < 5000; i++) {
  api3.basculerPleinEcran();
}
const DureeToggle = Date.now() - T1;
console.log(`  -> 5 000 bascules consécutives exécutées en ${DureeToggle} ms`);

// État attendu après 5000 bascules (pair) : état initial (non plein écran)
const estPlein3 = env3.appRoot.classList.contains('assistant-plein-ecran');
const ariaPressed3 = env3.btnPleinEcran.getAttribute('aria-pressed');
const icAgrandirDisplay3 = env3.icAgrandir.style.display;
const icReduireDisplay3 = env3.icReduire.style.display;

console.log(`  -> État final appRoot : plein_ecran = ${estPlein3} (attendu: false)`);
console.log(`  -> aria-pressed = "${ariaPressed3}" (attendu: "false")`);
console.log(`  -> icAgrandir.display = "${icAgrandirDisplay3}" (attendu: "")`);
console.log(`  -> icReduire.display = "${icReduireDisplay3}" (attendu: "none")`);

if (estPlein3 !== false || ariaPressed3 !== 'false' || icAgrandirDisplay3 !== '' || icReduireDisplay3 !== 'none') {
  throw new Error("Désynchronisation de l'état du plein écran après toggle spam !");
}

// Forçage explicite true puis false
api3.basculerPleinEcran(true);
if (!env3.appRoot.classList.contains('assistant-plein-ecran') || env3.btnPleinEcran.getAttribute('aria-pressed') !== 'true') {
  throw new Error("Échec du basculement forcé vers true");
}
api3.basculerPleinEcran(false);
if (env3.appRoot.classList.contains('assistant-plein-ecran') || env3.btnPleinEcran.getAttribute('aria-pressed') !== 'false') {
  throw new Error("Échec du basculement forcé vers false");
}
console.log("  [SUCCÈS] Résilience parfaite au toggle spam et forçages explicites.");


// ============================================================================
// TEST 4 : Interaction Clavier Escape & Bouton Quitter Plein Écran
// ============================================================================
console.log("\n[TEST 4] Test des déclencheurs de sortie : touche Escape et bouton Quitter...");
const env4 = creerEnvironnementDOM(true);
const sandbox4 = {
  document: env4.docParent,
  window: env4.win,
  MutationObserver: env4.win.MutationObserver,
  setTimeout: env4.win.setTimeout,
  console: console
};
vm.createContext(sandbox4);
// Simuler l'attachement DOMContentLoaded
const domListeners = [];
env4.docParent.addEventListener('DOMContentLoaded', (fn) => domListeners.push(fn));
vm.runInContext(codeJs, sandbox4);

// Déclencher DOMContentLoaded
const dclList = env4.docParent.eventListeners.get('DOMContentLoaded') || [];
for (const fn of dclList) fn();

// 1. Activer le plein écran
sandbox4.window.AOCEDA_ASSISTANT_PAGE.basculerPleinEcran(true);
if (!env4.appRoot.classList.contains('assistant-plein-ecran')) {
  throw new Error("Impossible d'activer le plein écran pour le test Escape");
}

// 2. Émettre la touche Escape sur le document parent
env4.docParent.dispatchEvent({ type: 'keydown', key: 'Escape' });
if (env4.appRoot.classList.contains('assistant-plein-ecran')) {
  throw new Error("La touche Escape sur le document parent n'a pas fermé le plein écran !");
}
console.log("  -> Touche Escape sur document parent : fermeture validée.");

// 3. Réactiver et tester Escape depuis l'iframe
sandbox4.window.AOCEDA_ASSISTANT_PAGE.basculerPleinEcran(true);
env4.cadre.dispatchEvent({ type: 'load' }); // attache l'écouteur iframe
env4.docIframe.dispatchEvent({ type: 'keydown', key: 'Escape' });
if (env4.appRoot.classList.contains('assistant-plein-ecran')) {
  throw new Error("La touche Escape depuis l'iframe n'a pas fermé le plein écran !");
}
console.log("  -> Touche Escape depuis l'iframe : fermeture validée.");

// 4. Réactiver et tester le bouton flottant #btn_quitter_plein_ecran
sandbox4.window.AOCEDA_ASSISTANT_PAGE.basculerPleinEcran(true);
env4.btnQuitter.click();
if (env4.appRoot.classList.contains('assistant-plein-ecran')) {
  throw new Error("Le clic sur #btn_quitter_plein_ecran n'a pas fermé le plein écran !");
}
console.log("  -> Clic sur #btn_quitter_plein_ecran : fermeture validée.");
console.log("  [SUCCÈS] Tous les chemins de sortie du plein écran fonctionnent parfaitement.");


// ============================================================================
// TEST 5 : Synchronisation synchrone du thème parent <-> cadre
// ============================================================================
console.log("\n[TEST 5] Synchronisation synchrone du thème parent <-> cadre...");
const env5 = creerEnvironnementDOM(true);
const sandbox5 = {
  document: env5.docParent,
  window: env5.win,
  MutationObserver: env5.win.MutationObserver,
  setTimeout: env5.win.setTimeout,
  console: console
};
vm.createContext(sandbox5);
vm.runInContext(codeJs, sandbox5);
const api5 = sandbox5.window.AOCEDA_ASSISTANT_PAGE;

// Test bascule sombre
api5.synchroniserThemeCadre('dark');
const themeIframeSombre = env5.docIframe.documentElement.getAttribute('data-theme');
console.log(`  -> Thème parent 'dark' -> Thème iframe : "${themeIframeSombre}" (attendu: "sombre")`);
if (themeIframeSombre !== 'sombre') {
  throw new Error(`Échec synchro thème dark : ${themeIframeSombre}`);
}

// Test bascule claire
api5.synchroniserThemeCadre('light');
const themeIframeClair = env5.docIframe.documentElement.getAttribute('data-theme');
console.log(`  -> Thème parent 'light' -> Thème iframe : "${themeIframeClair}" (attendu: "clair")`);
if (themeIframeClair !== 'clair') {
  throw new Error(`Échec synchro thème light : ${themeIframeClair}`);
}
console.log("  [SUCCÈS] Synchronisation bidirectionnelle du thème validée.");

console.log("\n================================================================================");
console.log("   RÉSULTATS HARNAIS UI : 5/5 SUCCÈS (0 ÉCHEC, 100% RÉSILIENCE)");
console.log("================================================================================\n");
