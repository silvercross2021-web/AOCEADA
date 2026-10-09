/* Assistant AOCEDA (chatbot) : la page construite et validée au laboratoire, reprise telle quelle. Changements pour AOCEDA
   (repérés « AOCEDA ») : API /api/assistant avec le jeton du client connecté, historique gardé sur son compte (synchronisé
   entre ses appareils), thème partagé avec le reste d'AOCEDA, fichiers statiques de Django. La page s'affiche dans la zone
   de contenu d'AOCEDA (cadre de templates/aoceda-ia.html), le menu et la barre du bas restent autour. */
"use strict";
const $ = s => document.querySelector(s);
/* ── AOCEDA : API de l'assistant et connexion du client (mêmes jetons que le reste d'AOCEDA) ── */
const API = "/api/assistant";
const STATIQUE = document.documentElement.dataset.statique || "/static/";
const JETON = "aoceda_access_token", JETON_RENOUVELLEMENT = "aoceda_refresh_token";
const PARENT = (() => { try { return window.parent !== window && window.parent.AOCEDA ? window.parent : null; } catch { return null; } })();
let renouvellement = null;
function renouvelerJeton() {
  if (PARENT?.AOCEDA.refreshAccessToken) return PARENT.AOCEDA.refreshAccessToken();   // AOCEDA garde aussi l'appli mobile à jour
  if (renouvellement) return renouvellement;
  const r = localStorage.getItem(JETON_RENOUVELLEMENT);
  if (!r) return Promise.reject(new Error("pas de session"));
  renouvellement = api("/auth/refresh/", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh: r }) })
    .then(x => { if (!x.ok) throw new Error("session expirée"); return x.json(); })
    .then(d => { localStorage.setItem(JETON, d.access); if (d.refresh) localStorage.setItem(JETON_RENOUVELLEMENT, d.refresh); return d.access; })
    .finally(() => { renouvellement = null; });
  return renouvellement;
}
function seReconnecter() {               // session finie : page de connexion d'AOCEDA (toute la fenêtre, pas le cadre)
  try { (window.top || window).location.href = "/auth/"; } catch { location.href = "/auth/"; }
}
/** fetch vers l'API de l'assistant avec le jeton du client ; jeton expiré : renouvelé une fois puis la demande est rejouée. */
async function api(chemin, options = {}) {
  const avec = jeton => { const h = Object.assign({}, options.headers || {}); if (jeton) h.Authorization = "Bearer " + jeton; return Object.assign({}, options, { headers: h }); };
  let r = await fetch(API + chemin, avec(localStorage.getItem(JETON)));
  if (r.status !== 401) return r;
  let jeton; try { jeton = await renouvelerJeton(); } catch { seReconnecter(); throw new Error("Session expirée : reconnectez-vous."); }
  r = await fetch(API + chemin, avec(jeton));
  if (r.status === 401) { seReconnecter(); throw new Error("Session expirée : reconnectez-vous."); }
  return r;
}
/** Identifiant du compte connecté (lu dans le jeton) : chaque compte a sa conversation en cours sur cet appareil. */
const COMPTE = (() => { try { return JSON.parse(atob(localStorage.getItem(JETON).split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))).user_id || "x"; } catch { return "x"; } })();
const CLE_SESSION = `aoceda_assistant_session_${COMPTE}`;
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const mediane = xs => { const v = xs.filter(x => x != null).sort((a, b) => a - b); return v.length ? (v.length % 2 ? v[(v.length - 1) / 2] : (v[v.length / 2 - 1] + v[v.length / 2]) / 2) : null; };
const s1 = x => (x == null ? "–" : `${Number(x).toFixed(1).replace(".", ",")} s`);
const stock = { lire(k, d) { try { return localStorage.getItem(k) ?? d; } catch { return d; } }, ecrire(k, v) { try { localStorage.setItem(k, v); } catch {} } };
const nouvelId = () => (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2)).replace(/[^A-Za-z0-9-]/g, "");
const LOCALES = { dyu: "dioula", bci: "baoulé" };        // langues relais (écoute et voix sur le serveur)
const nomLocale = c => LOCALES[c] || c;
let session = stock.lire(CLE_SESSION, null) || nouvelId(); stock.ecrire(CLE_SESSION, session);
let occupe = false, LANGUES = [], langueVocale = null, langueReponse = null, requete = null, arretDemande = false;

/* ── Icônes (traits fins, style iOS) ── */
const I = (d, plein = false) => `<svg class="ic${plein ? " plein" : ""}" viewBox="0 0 24 24" aria-hidden="true">${d}</svg>`;
const ICONES = {
  micro: I(`<path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3Z"/><path d="M19 11a7 7 0 0 1-14 0M12 18v3"/>`),
  envoyer: I(`<path d="M20.2 3.8 3.9 10.6c-.7.3-.6 1.3.1 1.5l6.8 1.6 1.6 6.8c.2.7 1.2.8 1.5.1l6.8-16.3c.2-.4-.2-.8-.5-.5Z" fill="currentColor" stroke="currentColor" stroke-width="1.2"/>`),
  stop: I(`<rect x="7" y="7" width="10" height="10" rx="2.2"/>`, true),
  son: I(`<path d="M11 5 6 9H3v6h3l5 4V5Z"/><path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13"/>`),
  muet: I(`<path d="M11 5 6 9H3v6h3l5 4V5Z"/><path d="m22 9-6 6M16 9l6 6"/>`),
  sablier: `<span class="roue" aria-hidden="true"></span>`,
  traduire: I(`<path d="M4 5h8M8 3v2M6 5c0 4 2 7 5 8M10 5c0 3-2 7-6 9"/><path d="m12 20 4-9 4 9M13.5 17h5"/>`),
  reessayer: I(`<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>`),
  compris: I(`<path d="M12 3l1.8 4.6L18.5 9l-4.7 1.4L12 15l-1.8-4.6L5.5 9l4.7-1.4Z"/><path d="M19 15l.8 2 2 .8-2 .8L19 21l-.8-2.4-2-.8 2-.8Z"/>`),
  oreille: I(`<path d="M6 8.5a6 6 0 1 1 12 0c0 3-2 4.5-3.2 5.7-1 1-1.3 2-1.3 3.3a3 3 0 0 1-5.5 1.6"/><path d="M9.5 9a2.5 2.5 0 1 1 4.3 1.8"/>`),
  valider: I(`<path d="m5 12.5 4.5 4.5L19 7.5"/>`),
  fermer: I(`<path d="M6 6l12 12M18 6 6 18"/>`),
  fleche: I(`<path d="M5 12h14M13 6l6 6-6 6"/>`),
  coche: I(`<path d="m5 12.5 4.5 4.5L19 7.5"/>`),
  chevron: I(`<path d="m9 6 6 6-6 6"/>`),
  bulle: I(`<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12Z"/>`),
};
const POINTS = `<span class="m-points" role="img" aria-label="L'assistant écrit"><i></i><i></i><i></i></span>`;   // il réfléchit
/* « English (Anglais) » -> « anglais » ; « Français » -> « français » (noms de /api/config) */
const nomLangue = code => { const n = (LANGUES.find(l => l.code === code) || {}).nom || code || ""; return (n.match(/\(([^)]+)\)\s*$/)?.[1] || n).toLowerCase(); };
/* Bouton « Écouter » & co : icône + texte ; data-etat sert de repère (préparation, lecture...) */
function etiquette(b, icone, texte) { b.dataset.etat = icone; b.innerHTML = `${ICONES[icone] || ""}<span>${esc(texte)}</span>`; }

/* ── Rendu d'une réponse : texte simple + gras + listes à tirets (tout est échappé d'abord) ── */
const insecables = s => s.replace(/ ([?!:;»])/g, " $1").replace(/« /g, "« ");
function rendu(texte) {
  const lignes = insecables(esc(texte)).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").split(/\n/);
  let html = "", liste = false;
  for (const l of lignes) {
    const puce = l.match(/^\s*[-*•]\s+(.*)/);
    if (puce) { if (!liste) { html += "<ul>"; liste = true; } html += `<li>${puce[1]}</li>`; continue; }
    if (liste) { html += "</ul>"; liste = false; }
    if (l.trim()) html += `<p>${l}</p>`;
  }
  return html + (liste ? "</ul>" : "");
}

/* ── Feuilles (Options, Langue, Historique) ── */
let feuilleOuverte = null;
function ouvrir(id) {
  fermer(); feuilleOuverte = $(id); feuilleOuverte.classList.add("ouvert"); $("#voile").classList.add("ouvert");
  MOUVEMENT.cascade(feuilleOuverte);             // son contenu arrive en cascade
  setTimeout(() => feuilleOuverte?.querySelector("[data-fermer]")?.focus({ preventScroll: true }), 50);
}
function fermer() {
  feuilleOuverte?.classList.remove("ouvert"); $("#voile").classList.remove("ouvert"); feuilleOuverte = null;
  document.querySelectorAll(".agent-bulle").forEach(b => { b.getAnimations().forEach(a => a.cancel()); b.remove(); });   // l'étiquette du choix part avec la fenêtre
}
$("#voile").onclick = fermer;
document.querySelectorAll("[data-fermer]").forEach(b => b.onclick = fermer);
$("#btn_options").onclick = () => ouvrir("#feuille_options");
$("#btn_historique").onclick = () => { remplirHistorique(); ouvrir("#feuille_historique"); };
$("#plus").onclick = () => { remplirLangues(); ouvrir("#feuille_langue"); };
$("#logo").onclick = () => montrerVue("chat");

/* ── Vues (conversation / tests) ── */
function montrerVue(v) {
  const avant = $(".vue.active");
  document.querySelectorAll(".vue").forEach(x => x.classList.toggle("active", x.id === "vue_" + v));
  if (avant && avant.id !== "vue_" + v) MOUVEMENT.vue($("#vue_" + v));
  if (v === "tests") chargerTests();
}
document.querySelectorAll("nav button[data-vue]").forEach(b => b.onclick = () => { fermer(); montrerVue(b.dataset.vue); });

/* ── Thème : Automatique (système) / Clair / Sombre ──
   AOCEDA : c'est le MÊME choix que dans le reste d'AOCEDA (« aoceda-theme-choice » : light / dark / auto) ; changé ici, il
   change partout (menu compris), et changé ailleurs, la page suit. */
const THEME_AOCEDA = { clair: "light", sombre: "dark", auto: "auto" };
const themePage = () => ({ light: "clair", dark: "sombre" })[stock.lire("aoceda-theme-choice", "auto")] || "auto";
function appliquerTheme(t) {
  if (t === "clair" || t === "sombre") document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme;
  document.querySelectorAll("#theme button").forEach(b => b.classList.toggle("choisi", b.dataset.themeChoix === (t || "auto")));
}
function choisirTheme(t) {
  if (PARENT?.AOCEDA.setThemeChoice) PARENT.AOCEDA.setThemeChoice(THEME_AOCEDA[t] || "auto");
  else stock.ecrire("aoceda-theme-choice", THEME_AOCEDA[t] || "auto");
  appliquerTheme(t);
}
document.querySelectorAll("#theme button").forEach(b => b.onclick = e => MOUVEMENT.theme(e,   // le nouveau thème s'ouvre en cercle
  () => choisirTheme(b.dataset.themeChoix), () => PERSO.theme()));
appliquerTheme(themePage());
window.addEventListener("storage", e => { if (e.key === "aoceda-theme-choice" || e.key === "aoceda-theme") appliquerTheme(themePage()); });

/* ── Langue (bouton +) : liste façon iOS avec coche ── */
function remplirLangues() {
  const actuelle = $("#langue").value;
  $("#liste_langues").innerHTML = LANGUES.map(l => `<button class="ligne${l.code === actuelle ? " choisi" : ""}" data-code="${esc(l.code)}">
    <span class="etiquette">${esc(l.nom)}${l.relais ? `<small>voix et écoute AOCEDA</small>` : ""}</span>${ICONES.coche.replace('class="ic"', 'class="ic coche"')}</button>`).join("");
  $("#liste_langues").querySelectorAll("button").forEach(b => b.onclick = () => {
    $("#langue").value = b.dataset.code; $("#langue").dispatchEvent(new Event("change")); setTimeout(fermer, 120);
    $("#liste_langues").querySelectorAll(".ligne").forEach(x => x.classList.toggle("choisi", x === b));
  });
}

/* ── Historique : gardé sur le compte AOCEDA du client (AOCEDA : au laboratoire, sur cet appareil seulement) ── */
const HIST_MSG_MAX = 60;
let HISTORIQUE = [];              // dernière liste lue : [{id, titre, maj, questions}]
let ECHANGES = [];                // messages affichés de la conversation en cours, enregistrés sur le compte
let enregistrement = Promise.resolve();
function noterEchange(question, reponse) {
  ECHANGES.push({ role: "moi", texte: question }, reponse); ECHANGES = ECHANGES.slice(-HIST_MSG_MAX);
  const ident = session, messages = ECHANGES.slice(), titre = (messages.find(m => m.role === "moi")?.texte || question).slice(0, 80);
  enregistrement = enregistrement.then(() => api(`/conversations/${ident}/`, { method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ titre, messages }) })).catch(() => {});
}
const quand = t => { const d = new Date(t), j = new Date(); return d.toDateString() === j.toDateString()
  ? d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }) : d.toLocaleDateString("fr-FR", { day: "numeric", month: "short" }); };
async function remplirHistorique() {
  const liste = $("#liste_historique");
  if (!HISTORIQUE.length) liste.innerHTML = `<div class="vide-liste">Chargement…</div>`;
  try {
    await enregistrement;                                    // le dernier échange est déjà sur le compte
    const d = await (await api("/conversations/")).json();
    HISTORIQUE = (Array.isArray(d) ? d : d.results || []).map(c => ({ id: c.id, titre: c.titre || "Conversation", maj: Date.parse(c.updated_at), questions: c.questions || 0 }));
  } catch { if (!HISTORIQUE.length) { liste.innerHTML = `<div class="vide-liste">Historique indisponible pour le moment.</div>`; return; } }
  const h = HISTORIQUE;
  liste.innerHTML = h.length ? h.map(c => `<button class="ligne${c.id === session ? " choisi" : ""}" data-id="${esc(c.id)}">
      <span class="pastille p-jaune">${ICONES.bulle}</span>
      <span class="etiquette">${esc(c.titre)}<small>${quand(c.maj)} · ${c.questions} question${c.questions > 1 ? "s" : ""}</small></span>
      ${ICONES.chevron.replace('class="ic"', 'class="ic chevron"')}</button>`).join("")
    : `<div class="vide-liste">Aucune conversation pour l'instant.</div>`;
  liste.querySelectorAll("button").forEach(b => b.onclick = () => { reprendre(b.dataset.id); fermer(); });
  $("#effacer_historique").hidden = !h.length;
}
async function reprendre(id) {
  let c; try { c = await (await api(`/conversations/${id}/`)).json(); } catch { return; }
  if (!c || !Array.isArray(c.messages)) return;
  requete?.abort(); if (enreg) arreterEnreg(false); arreterLecture(); occupe = false;
  session = c.id; stock.ecrire(CLE_SESSION, session); langueVocale = null; ECHANGES = c.messages.slice(-HIST_MSG_MAX);
  PERSO.quitterAccueil(() => { colonne.innerHTML = ""; $("#vue_chat").classList.remove("accueil"); });
  // les messages à l'écran (les 10 derniers) arrivent en cascade, de haut en bas ; les autres sont déjà là
  const cascade = (el, i) => el.style.setProperty("--i", Math.max(0, 10 - (c.messages.length - 1 - i)));
  // « const m » : chaque bouton Écouter garde SON message (audit du 09/10/2026 : une seule variable partagée -> tous
  // les boutons d'une conversation reprise lisaient la dernière réponse)
  for (const [i, m] of c.messages.entries()) {
    if (m.role === "moi") { cascade(ajouter("moi", `<div class="bulle">${insecables(esc(m.texte))}</div>`), i); continue; }
    const el = ajouter("ia", `<div class="bulle">${rendu(m.texte)}</div><div class="meta"></div>`); cascade(el, i);
    const bulle = el.querySelector(".bulle"), meta = el.querySelector(".meta");
    const ec = document.createElement("button"); ec.className = "ecouter"; etiquette(ec, "son", "Écouter");
    ec.onclick = e => ecouter(m.texte, e.currentTarget, m.langue || null); meta.appendChild(ec);
    if (m.fr) {
      const fr = document.createElement("div"); fr.className = "francais"; fr.hidden = true; fr.innerHTML = rendu(m.fr); bulle.appendChild(fr);
      const vf = document.createElement("button"); vf.className = "ecouter voir_fr"; etiquette(vf, "traduire", "Voir en français");
      vf.onclick = () => { const ouvre = fr.hidden; MOUVEMENT.deplier(fr); etiquette(vf, "traduire", ouvre ? "Masquer le français" : "Voir en français"); };
      meta.appendChild(vf);
    }
    langueReponse = m.langue || langueReponse;
  }
  majBoutons(); enBas();
}
$("#effacer_historique").onclick = async () => {
  if (!confirm("Effacer toutes vos conversations avec l'assistant (sur tous vos appareils) ?")) return;
  await api("/conversations/", { method: "DELETE" }).catch(() => {});
  HISTORIQUE = []; ECHANGES = []; remplirHistorique();
};

/* ── Fil de discussion ── */
const colonne = $("#colonne"), fil = $("#fil");
function enBas() { fil.scrollTop = fil.scrollHeight; }
fil.addEventListener("scroll", () => MOUVEMENT.versBas(), { passive: true });     // on remonte : un bouton ramène en bas
$("#vers_bas").onclick = () => fil.scrollTo({ top: fil.scrollHeight, behavior: MOUVEMENT.reduit() ? "auto" : "smooth" });
const SUGGESTIONS = ["Comment réduire ma facture d'électricité ?", "N ka kuran juru banna, n bɛ se ka mun kɛ ?", "Wafa sɛ yɛ n kwla fa min mɛtɛri'n n gua nun ɔn ?",
                     "How can I save energy with my fridge?", "Prépayé ou postpayé : quelle différence ?"];
function accueil() {
  const depuis = PERSO.rect();                    // le personnage glisse depuis la barre de saisie jusqu'au-dessus du titre
  // personnage animé au-dessus du titre (sans lui, le logo AOCEDA comme avant)
  const marque = AP ? `<div class="perso perso-accueil" title="L'assistant AOCEDA" aria-hidden="true"></div>`
    : `<img class="marque-accueil clair" src="${STATIQUE}img/assistant/icone.png" alt=""><img class="marque-accueil sombre" src="${STATIQUE}img/assistant/icone-sombre.png" alt="">`;
  const remplir = () => {
    $("#vue_chat").classList.add("accueil");
    colonne.innerHTML = `<div class="vide">${marque}<p class="titre">Comment puis-je vous aider ?</p>
      <p class="sous">L'électricité à la maison, à l'écrit ou à la voix, dans votre langue : dioula et baoulé compris.</p></div>`;
    // les suggestions arrivent une à une (--i : leur rang)
    $("#suggestions").innerHTML = SUGGESTIONS.map((q, i) => `<button class="puce" style="--i:${i}"><span>${insecables(esc(q))}</span>${ICONES.fleche}</button>`).join("");
  };
  // au démarrage, tout est déjà au centre ; après une conversation, la barre de saisie remonte au centre en glissant
  if (colonne.childElementCount) MOUVEMENT.morphZone(remplir); else remplir();
  // une suggestion touchée DEVIENT votre message (elle s'envole jusqu'à sa place dans la conversation)
  $("#suggestions").querySelectorAll(".puce").forEach(b => b.onclick = () => { MOUVEMENT.depuis(b, true); envoyer(b.textContent, "ecrit"); });
  PERSO.accueil(colonne.querySelector(".perso-accueil"), depuis);
}
function ajouter(classe, html) {
  // l'accueil disparaît : le personnage glisse à côté de la barre de saisie
  PERSO.quitterAccueil(() => { colonne.querySelector(".vide")?.remove(); $("#vue_chat").classList.remove("accueil"); });
  const m = document.createElement("div"); m.className = "msg " + classe; m.innerHTML = html; colonne.appendChild(m); enBas(); return m;
}

/* ── Envoi d'un message et lecture du flux de réponse ── */
/* Boutons sous une réponse baoulé (06/10/2026) : Oui / Non pour confirmer (rien ne se fait sans « oui »), ou
   2-3 autres demandes quand le chatbot n'est pas sûr. Un clic envoie le bouton au serveur (action) ; les boutons
   se désactivent pour qu'on ne réponde pas deux fois à la même question. */
function afficherBoutons(m, b) {
  const boite = document.createElement("div"); boite.className = "reponses-rapides";
  const ajouter = (libelle, action, icone) => {
    const x = document.createElement("button"); x.className = "ecouter rapide"; etiquette(x, icone, libelle);
    x.onclick = () => { if (occupe) return; boite.querySelectorAll("button").forEach(y => y.disabled = true); x.classList.add("choisi");
      envoyer(libelle, "ecrit", "", null, null, action); };
    boite.appendChild(x);
  };
  if (b.oui_non) { ajouter("Oui", { type: "oui" }, "valider"); ajouter("Non", { type: "non" }, "fermer"); }
  (b.choix || []).forEach(c => ajouter(c.libelle, { type: "choix", demande: c.demande }, "compris"));
  m.appendChild(boite); MOUVEMENT.arrivee(boite); enBas();
}

/* Langue reconnue, sous le message (vocal : ce que l'oreille a entendu ; écrit : ce que le serveur a détecté) */
const nomComplet = c => { const n = LOCALES[c] || nomLangue(c) || "?"; return n.charAt(0).toUpperCase() + n.slice(1); };
const ICONE_LANGUE = `<svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/></svg>`;
function afficherLangue(moi, html) {
  if (!moi) return;
  moi.querySelector(".langue-vue")?.remove();
  const d = document.createElement("div"); d.className = "langue-vue"; d.innerHTML = `<span>${ICONE_LANGUE}${html}</span>`;
  const compris = moi.querySelector(".compris"); compris ? moi.insertBefore(d, compris) : moi.appendChild(d);
}
const COMMENT_ECRIT = { "détectée": "reconnue automatiquement", "détectée (traces)": "reconnue automatiquement", "conversation": "langue de la conversation",
  "menu": "choisie dans le menu", "demandée": "demandée dans votre message", "demandée plus tôt": "demandée plus tôt",
  "bouton": "réponse par bouton" };

async function envoyer(texte, origine = "ecrit", entete = "", indice = null, langueVue = null, action = null) {
  texte = (texte || "").replace(/ /g, " ").trim();   // espaces insécables de l'affichage -> espaces normales
  if (!texte || occupe) return;
  occupe = true; majBoutons();
  const moiMsg = ajouter("moi", `${entete}<div class="bulle">${insecables(esc(texte))}</div>`);
  MOUVEMENT.lancer(moiMsg);   // part d'où vous l'avez envoyé
  if (langueVue) { afficherLangue(moiMsg, langueVue.html); moiMsg.dataset.langueParlee = langueVue.code; moiMsg.dataset.langueVue = langueVue.html; }
  PERSO.envoi(texte);                               // « compris ! » (ou bonjour, merci...), puis il réfléchit
  const m = ajouter("ia", `<div class="bulle curseur">${POINTS}</div><div class="meta"></div>`);   // il réfléchit : 3 points
  const bulle = m.querySelector(".bulle"), meta = m.querySelector(".meta");
  let brut = "", fin = null, notes = [], francais = "", anticipee = null, boutons = null;
  const fondu = { longueur: 0, morceaux: [] };       // la réponse apparaît en fondu, au fil des morceaux (MOUVEMENT.fondu)
  const moi = m.previousElementSibling;
  const lectureAuto = () => { const a = $("#lecture_auto").value; return a === "toujours" || (a === "vocal" && origine === "vocal"); };
  try {
    requete = new AbortController(); majBoutons();
    const r = await api("/message", { method: "POST", headers: {"Content-Type": "application/json"}, signal: requete.signal,
      // voix_auto : la réponse sera lue toute seule -> la voix baoulé (GPU payant) part tout de suite ; sinon seulement
      // si on appuie sur Écouter
      body: JSON.stringify({ session, texte, langue: $("#langue").value, origine, indice_langue: indice, genre: $("#genre").value, action,
                             voix_auto: lectureAuto() }) });
    if (!r.ok) { const e = new Error((await r.json().catch(() => ({}))).erreur || `Erreur ${r.status}`); e.statut = r.status;
      if (r.status === 403) { session = nouvelId(); stock.ecrire(CLE_SESSION, session); ECHANGES = []; }   // AOCEDA : pas la sienne
      throw e; }
    const lecteur = r.body.getReader(), dec = new TextDecoder(); let tampon = "";
    while (true) {
      const { value, done } = await lecteur.read(); if (done) break;
      tampon += dec.decode(value, { stream: true });
      let i; while ((i = tampon.indexOf("\n\n")) >= 0) {
        const bloc = tampon.slice(0, i); tampon = tampon.slice(i + 2);
        if (!bloc.startsWith("data: ")) continue;
        const ev = JSON.parse(bloc.slice(6));
        if (ev.type === "langue") {
          if (ev.code) langueReponse = ev.code;
          if (ev.code && !moi?.querySelector(".langue-vue"))      // écrit : langue détectée par le serveur
            afficherLangue(moi, ["menu", "demandée", "demandée plus tôt"].includes(ev.source)
              ? `Réponse en <b>${esc(nomComplet(ev.code))}</b> · ${esc(COMMENT_ECRIT[ev.source])}`
              : `Langue : <b>${esc(nomComplet(ev.code))}</b> · ${esc(COMMENT_ECRIT[ev.source] || "reconnue automatiquement")}`);
          else if (ev.code && moi?.dataset.langueParlee && moi.dataset.langueParlee !== ev.code)   // vocal : réponse dans une autre langue
            afficherLangue(moi, `${moi.dataset.langueVue} · réponse en <b>${esc(nomComplet(ev.code))}</b>`);
          if (ev.source === "demandée") { MOUVEMENT.annonce(`Réponses en ${nomLangue(ev.code)} jusqu'à nouvel ordre`); PERSO.langue(); }
        }
        else if (ev.type === "fournisseur") meta.textContent = `${ev.fournisseur} · ${ev.modele}…`;
        else if (ev.type === "outil") meta.textContent = `Lecture de vos données : ${ev.label}…`;   // AOCEDA
        else if (ev.type === "morceau") { brut += ev.texte; MOUVEMENT.fondu(bulle, rendu(brut), fondu); enBas(); PERSO.morceau();
          // dioula : la 1re phrase se lit dès qu'elle est traduite (sa voix est déjà en préparation sur le serveur ;
          // baoulé : non, sa voix prend plusieurs minutes, elle se lira quand elle sera prête)
          if (!anticipee && langueReponse === "dyu" && lectureAuto() && ev.traduit !== false) anticipee = lireDebut(ev.texte.trim()); }
        else if (ev.type === "recommencer") { brut = ""; francais = ""; bulle.innerHTML = POINTS; Object.assign(fondu, { longueur: 0, morceaux: [] }); notes.push(ev.raison); }
        else if (ev.type === "francais") francais += ev.texte;
        else if (ev.type === "intention") {
          moi?.querySelector(".compris")?.remove();
          const c = document.createElement("div"); c.className = "compris";
          const cert = { haute: "sûr", moyenne: "à confirmer", basse: "deviné" }[ev.certitude] || "";
          c.innerHTML = `${ICONES.compris}<span>Compris : <b>${esc(ev.texte)}</b>${cert ? ` · ${cert}` : ""}</span>`; moi?.appendChild(c); enBas();
          PERSO.intention(ev.certitude);
        }
        else if (ev.type === "boutons") boutons = ev;       // baoulé : Oui / Non, ou choix d'une autre demande
        else if (ev.type === "fin" || ev.type === "erreur") fin = ev;
      }
    }
    if (!fin) throw new Error("Réponse interrompue.");
    if (fin.type === "erreur") throw new Error(fin.texte);
    bulle.classList.remove("curseur");             // dioula / baoulé : fin.texte est dans cette langue
    MOUVEMENT.fondu(bulle, rendu(fin.texte), fondu);   // les derniers mots finissent d'apparaître (pas de saut)
    const echecs = (fin.essais || []).filter(e => e.erreur).length;
    if (fin.francais) {                            // dioula / baoulé : la réponse en français, cachée derrière un bouton
      const fr = document.createElement("div"); fr.className = "francais"; fr.hidden = true; fr.innerHTML = rendu(fin.francais); bulle.appendChild(fr);
    }
    const detailTemps = fin.premiere_phrase_s != null ? `1re phrase en ${nomLocale(langueReponse)} ${s1(fin.premiere_phrase_s)}` : `1er mot ${s1(fin.premier_mot_s)}`;
    meta.innerHTML = `<button class="ecouter"></button>${fin.francais ? `<button class="ecouter voir_fr"></button>` : ""}<span title="${esc(fin.fournisseur)} · ${esc(fin.modele)}">${detailTemps} · total ${s1(fin.total_s)}</span>`
      + (fin.non_traduit ? `<span class="note">${fin.non_traduit} phrase(s) non traduite(s) : traducteur indisponible</span>` : "")
      + (fin.douteuses ? `<span class="note" title="La retraduction ne retrouve pas un nombre, un appareil ou le sens : voyez le français.">${fin.douteuses} phrase(s) à vérifier (traduction automatique)</span>` : "")
      + (fin.non_verifiees ? `<span class="note" title="Le traducteur de contrôle a mis trop de temps : la traduction n'a pas pu être revérifiée.">${fin.non_verifiees} phrase(s) non revérifiée(s)</span>` : "")
      + (echecs ? `<span class="note" title="${esc(fin.essais.filter(e => e.erreur).map(e => e.modele + " : " + e.erreur).join("\n"))}">${echecs} modèle(s) saturé(s) évité(s)</span>` : "");
    etiquette(meta.querySelector(".ecouter"), "son", "Écouter");
    MOUVEMENT.arrivee(meta);                       // Écouter, Voir en français, les temps : l'un après l'autre
    const vf = meta.querySelector(".voir_fr");
    if (vf) { etiquette(vf, "traduire", "Voir en français");
      vf.addEventListener("click", () => { const fr = bulle.querySelector(".francais"), ouvre = fr.hidden; MOUVEMENT.deplier(fr);
        etiquette(vf, "traduire", ouvre ? "Masquer le français" : "Voir en français"); }); }
    if (boutons) afficherBoutons(m, boutons);       // sous la réponse : Oui / Non, ou « Vous parlez peut-être de… »
    const lgMsg = fin.langue_voix || langueReponse;   // traducteurs en panne : réponse restée en français, voix française
    noterEchange(texte, { role: "ia", texte: fin.texte, fr: fin.francais || null, langue: lgMsg });
    PERSO.fin(fin.texte, !!anticipee || lectureAuto());   // « voilà » (ou une astuce) ; si la réponse se lit, la voix prend le relais
    let boutonEcouter = meta.querySelector(".ecouter");
    if (anticipee) { boutonEcouter.replaceWith(anticipee.bouton); boutonEcouter = anticipee.bouton; }
    boutonEcouter.onclick = e => ecouter(fin.texte, e.currentTarget, lgMsg);
    if (anticipee) {                               // la 1re phrase est déjà lue : on enchaîne avec la suite
      const a = anticipee;
      a.fini.then(ok => {
        if (lecture !== a) return;                 // arrêtée entre-temps par l'utilisateur
        lecture = null; a.bouton.classList.remove("lecture"); etiquette(a.bouton, "son", "Écouter");
        ecouter(fin.texte, a.bouton, lgMsg, ok ? 1 : 0);
      });
    } else if (lectureAuto()) ecouter(fin.texte, boutonEcouter, lgMsg);   // comme Gemini : la réponse se lit seule
    else precharger(fin.texte, lgMsg);   // sinon la voix se prépare pendant la lecture du texte
  } catch (e) {
    if (e.name === "AbortError") {                // « Stop » ou nouvelle conversation pendant la réponse
      if (arretDemande) { bulle.classList.remove("curseur"); bulle.innerHTML = rendu(brut) + `<p class="note">Réponse arrêtée (elle n'est pas gardée dans la conversation).</p>`; meta.textContent = ""; PERSO.arret(); }
      return;
    }
    PERSO.erreur(e);
    m.classList.add("erreur"); bulle.classList.remove("curseur");
    bulle.innerHTML = `<p>${esc(e.message)}</p>`;
    meta.innerHTML = `<button class="ecouter"></button>`; etiquette(meta.querySelector(".ecouter"), "reessayer", "Réessayer");
    MOUVEMENT.arrivee(meta);
    // le même envoi, À L'IDENTIQUE : langue affichée et bouton baoulé compris (audit du 09/10/2026 : sans l'action, le
    // libellé « Mon crédit » repartait comme un message français)
    meta.querySelector(".ecouter").onclick = () => { m.previousElementSibling?.remove(); m.remove(); occupe = false; envoyer(texte, origine, entete, indice, langueVue, action); };
  } finally { requete = null; arretDemande = false; occupe = false; majBoutons(); enBas(); }
}

/* ── Écouter une réponse : voix Microsoft (ou Kokoro) du serveur, en morceaux (le son démarre vite) ;
      secours = voix du navigateur ── */
/* Voix du serveur en panne : mémorisée PAR LANGUE, 2 minutes (audit du 09/10/2026 : une seule panne de la voix dioula
   (Djelia) coupait la voix du serveur pour TOUTES les langues pendant 10 minutes) */
let lecture = null;
const voixServeurHS = new Map();         // langue -> instant jusqu'auquel la voix du serveur est considérée indisponible
const PANNE_VOIX_MS = 2 * 60 * 1000;
function arreterLecture() {
  if (!lecture) return;
  lecture.stop = true; lecture.audio?.pause(); speechSynthesis.cancel();
  lecture.bouton.classList.remove("lecture"); etiquette(lecture.bouton, "son", "Écouter"); lecture = null;
  PERSO.finParler();
}
function codeNavigateur() {
  const choix = $("#langue").value, code = choix !== "auto" ? choix : (langueReponse || langueVocale || "fr");
  return (LANGUES.find(l => l.code === code) || {}).navigateur || "fr-FR";
}
function voixNavigateur(texte, etat) {
  return new Promise(ok => {
    const u = new SpeechSynthesisUtterance(texte); u.lang = codeNavigateur(); u.onend = u.onerror = ok;
    etat.note = "voix du navigateur (secours)"; PERSO.parler(null); speechSynthesis.speak(u);   // son inaccessible : bouche simulée
  });
}
/* Préparation à l'avance des 2 premiers morceaux (gratuit) : un clic sur « Écouter » joue tout de suite */
const prets = new Map();   // "genre|langue|morceau" -> promesse du son
const cleSon = (t, langue) => `${$("#genre").value}|${langue || ""}|${t}`;
function demanderSon(t, langue) {
  const cle = cleSon(t, langue);
  if (!prets.has(cle)) {
    const lg = langue || ($("#langue").value !== "auto" ? $("#langue").value : null), panne = lg || "auto";
    // une voix qui n'est pas venue (panne, baoulé en échec) est oubliée : la prochaine demande réessaie (audit du
    // 09/10/2026 : la voix baoulé en échec restait « null » jusqu'au rechargement de la page)
    const oublier = b => { if (!b && prets.get(cle) === p) prets.delete(cle); return b; };
    const p = langue === "bci" ? sonBaoule(t).then(oublier)
      : Date.now() < (voixServeurHS.get(panne) || 0) ? Promise.resolve(null).then(oublier)
      : api("/voix", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({ session, texte: t, langue: lg, genre: $("#genre").value }) })
        .then(r => { if (r.status === 503) voixServeurHS.set(panne, Date.now() + PANNE_VOIX_MS); return r.ok ? r.blob() : null; }).catch(() => null)
        .then(oublier);
    prets.set(cle, p);
    if (prets.size > 60) prets.delete(prets.keys().next().value);   // mémoire bornée
  }
  return prets.get(cle);
}
/* Baoulé : la voix est fabriquée par OmniVoice, sur la carte graphique Cerebrium (~2 s ; ~35 s si elle dormait) ou, en
   secours, sur le serveur (plusieurs minutes par phrase). Le serveur répond « en préparation » (202) avec une estimation et
   le moteur ; on redemande toutes les 1,2 s pour le GPU (vu le 06/10 : à 10 s, une voix prête en 2 s attendait 10 s),
   toutes les 10 s pour le PC. */
const attenteBaoule = new Map();   // morceau -> secondes restantes estimées (affichées sur le bouton)
async function sonBaoule(t) {
  const fin = Date.now() + 30 * 60 * 1000;
  let pause = 1200;
  while (Date.now() < fin) {
    let r;
    try { r = await api("/voix", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({ session, texte: t, langue: "bci" }) }); }
    catch { await new Promise(ok => setTimeout(ok, 5000)); continue; }
    if (r.status === 200) { attenteBaoule.delete(t); return r.blob(); }
    if (r.status !== 202) { attenteBaoule.delete(t); return null; }
    const d = await r.json().catch(() => ({}));
    attenteBaoule.set(t, { attente: d.attente_s || 0, pretes: d.phrases_pretes || 0, phrases: d.phrases || 1, moteur: d.moteur });
    pause = d.moteur === "gpu" ? 1200 : 10000;
    await new Promise(ok => setTimeout(ok, pause));
  }
  attenteBaoule.delete(t); return null;
}
const minutes = s => s < 60 ? `${Math.max(1, Math.round(s))} s` : `${Math.max(1, Math.round(s / 60))} min`;
/* Dioula : lecture de la 1re phrase avant la fin de la réponse (le bouton est créé ici, placé ensuite dans la bulle) */
function lireDebut(texte) {
  arreterLecture();
  const bouton = document.createElement("button"); bouton.className = "ecouter lecture"; etiquette(bouton, "sablier", "Préparation…");
  const etat = lecture = { bouton, stop: false, audio: null, texte, langue: "dyu", index: 0 };
  etat.fini = (async () => {
    const m = await decouperTexte(texte); if (!m || etat.stop) return false;
    const blob = await demanderSon(m[0], "dyu"); if (!blob || etat.stop) return false;
    etiquette(bouton, "stop", "Arrêter");
    await new Promise(ok => { const a = etat.audio = new Audio(URL.createObjectURL(blob)); a.onended = a.onerror = ok; PERSO.parler(a); a.play().catch(ok); });
    return !etat.stop;
  })();
  return etat;
}
const morceauxDe = new Map();
/* baoulé : le serveur renvoie UN seul morceau (toute la réponse) -> un audio continu, sans silence entre les phrases */
function decouperTexte(texte, langue = null) {
  const cle = `${langue || ""}|${texte}`;
  if (!morceauxDe.has(cle)) morceauxDe.set(cle, api("/voix/morceaux", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({ session, texte, langue }) })
    .then(r => r.json()).then(d => d.morceaux).catch(() => { morceauxDe.delete(cle); return null; }));
  return morceauxDe.get(cle);
}
async function precharger(texte, langue) {
  if (langue === "bci") return;                      // baoulé : fabriquée seulement si on demande à l'écouter (minutes de calcul)
  const m = await decouperTexte(texte, langue);
  if (m) m.slice(0, 2).forEach(t => demanderSon(t, langue));
}
async function ecouter(texte, bouton, langue = null, depart = 0) {
  if (lecture && lecture.bouton === bouton) return arreterLecture();   // 2e clic = arrêter
  arreterLecture();
  const etat = lecture = { bouton, stop: false, audio: null, texte, langue, index: depart };
  bouton.classList.add("lecture"); etiquette(bouton, "sablier", "Préparation…");
  const t0 = performance.now();
  try {
    const morceaux = await decouperTexte(texte, langue);
    if (!morceaux) throw new Error("découpage impossible");
    const demande = t => demanderSon(t, langue);
    const sons = morceaux.map(() => null);
    for (let k = depart; k < Math.min(morceaux.length, depart + 2); k++) sons[k] = demande(morceaux[k]);   // 2 morceaux d'avance
    if (langue === "bci") morceaux.forEach((m, k) => { if (!sons[k]) sons[k] = demande(m); });   // tous en file dès maintenant
    const affiche = setInterval(() => {            // baoulé : avancement et temps d'attente estimé sur le bouton
      const a = attenteBaoule.get(morceaux[etat.index]);
      if (lecture === etat && a && bouton.dataset.etat === "sablier") {
        etiquette(bouton, "sablier", `Voix baoulé : ${a.phrases > 1 ? `phrase ${a.pretes}/${a.phrases} prête · ` : "en préparation · "}environ ${minutes(a.attente)}`);
        PERSO.attente();                           // en préparation : il patiente (sablier)
      }
    }, 1000);
    try {
      for (let i = depart; i < morceaux.length && !etat.stop; i++) {
        etat.index = i;
        if (morceaux[i + 2] && !sons[i + 2]) sons[i + 2] = demande(morceaux[i + 2]);
        const blob = await sons[i];
        if (etat.stop) break;
        if (i === depart) bouton.title = `1er son après ${((performance.now() - t0) / 1000).toFixed(1)} s`;
        etiquette(bouton, "stop", "Arrêter");
        if (!blob) { if (LOCALES[langue]) { etat.note = "indisponible"; continue; } await voixNavigateur(morceaux[i], etat); continue; }
        await new Promise(ok => { const a = etat.audio = new Audio(URL.createObjectURL(blob)); a.onended = a.onerror = ok; PERSO.parler(a); a.play().catch(ok); });
      }
    } finally { clearInterval(affiche); }
  } catch { if (!etat.stop) { if (LOCALES[langue]) etat.note = "indisponible"; else await voixNavigateur(texte, etat); } }
  if (lecture === etat) { bouton.classList.remove("lecture");
    if (etat.note === "indisponible") etiquette(bouton, "muet", `Voix ${nomLocale(langue)} indisponible`);
    else etiquette(bouton, "son", etat.note ? "Écouter (voix de secours)" : "Écouter");
    lecture = null; PERSO.finParler(); }
}

/* ── Message vocal : micro -> WAV 16 kHz mono -> transcription -> même chemin qu'un message écrit ── */
let enreg = null;
const SILENCE_FIN_MS = 1200;   // envoi automatique après 1,2 s de silence (plus besoin de recliquer)
let AUDIO_MAX_S = 60;          // limite du serveur (relue dans /api/config)
/* Capteur audio moderne (AudioWorklet), écrit ici pour rester en un seul fichier ; secours ScriptProcessor */
const CAPTEUR = `class Capteur extends AudioWorkletProcessor {
  constructor() { super(); this.t = []; this.n = 0; }
  process(entrees) {
    const c = entrees[0] && entrees[0][0];
    if (c) { this.t.push(new Float32Array(c)); this.n += c.length;
      if (this.n >= 2048) { const b = new Float32Array(this.n); let o = 0; for (const x of this.t) { b.set(x, o); o += x.length; }
        this.port.postMessage(b, [b.buffer]); this.t = []; this.n = 0; } }
    return true;
  }
}
registerProcessor("capteur-aoceda", Capteur);`;
let urlCapteur = null;
async function brancherCapteur(ctx, source, surBloc) {
  const muet = ctx.createGain(); muet.gain.value = 0; muet.connect(ctx.destination);   // relié sans rien faire entendre
  if (ctx.audioWorklet) {
    try {
      urlCapteur = urlCapteur || URL.createObjectURL(new Blob([CAPTEUR], { type: "application/javascript" }));
      await ctx.audioWorklet.addModule(urlCapteur);
      const n = new AudioWorkletNode(ctx, "capteur-aoceda");
      n.port.onmessage = ev => surBloc(ev.data);
      source.connect(n); n.connect(muet);
      return n;
    } catch {}
  }
  const proc = ctx.createScriptProcessor(4096, 1, 1);   // navigateur ancien
  proc.onaudioprocess = ev => surBloc(new Float32Array(ev.inputBuffer.getChannelData(0)));
  source.connect(proc); proc.connect(muet);
  return proc;
}
/* Fin de parole : le « bruit de fond » est le niveau bas des 2,5 dernières secondes (ventilateur, rue...),
   la voix doit le dépasser nettement pendant au moins 120 ms ; puis SILENCE_FIN_MS de calme -> envoi. */
const VAD = { FENETRE_MS: 2500, DEBUT_VOIX_MS: 120, SEUIL_MIN: 0.01 };
function analyserBloc(e, d) {
  let max = 0, somme = 0; for (let i = 0; i < d.length; i += 8) { max = Math.max(max, Math.abs(d[i])); somme += d[i] * d[i]; }
  const n = $("#etat_enreg .niveau i"); if (n) n.style.width = Math.min(100, max * 180) + "%";
  MOUVEMENT.niveau(Math.sqrt(somme / (d.length / 8)));   // l'anneau rouge du micro suit votre voix
  const rms = Math.sqrt(somme / (d.length / 8)), duree = d.length / e.taux * 1000;
  e.niveauActuel = rms;                          // le personnage montre qu'il entend (une onde quand vous parlez)
  e.niveaux.push(rms); while (e.niveaux.length > Math.ceil(VAD.FENETRE_MS / duree)) e.niveaux.shift();
  const tries = [...e.niveaux].sort((a, b) => a - b), fond = tries[Math.floor(tries.length * 0.15)];
  const seuil = Math.max(VAD.SEUIL_MIN, fond * 2.5, fond + 0.01);
  if (rms > seuil) { e.voixMs += duree; if (e.voixMs >= VAD.DEBUT_VOIX_MS) e.parle = true; e.silence = 0; }
  else { e.voixMs = 0; if (e.parle && (e.silence += duree) >= SILENCE_FIN_MS) return arreterEnreg(true); }
  // dioula : à chaque pause, le morceau déjà dit part tout de suite au serveur, qui l'écoute pendant qu'on continue
  e.depuisCoupe += d.length;
  if (e.preEcoute && e.parle && e.silence >= PAUSE_MORCEAU_MS && e.depuisCoupe >= MORCEAU_MIN_S * e.taux && e.rang < 11) couperMorceau(e);
}
const afficherEtat = html => { $("#etat_enreg").innerHTML = html; };
async function demarrerEnreg() {
  let flux;
  try { flux = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } }); }
  catch { $("#etat_enreg").textContent = "Micro refusé ou indisponible : autorisez le micro dans le navigateur."; return; }
  arreterLecture();
  const ctx = new AudioContext(), source = ctx.createMediaStreamSource(flux);
  // dioula / baoulé (menu, ou conversation déjà dans cette langue) : les morceaux sont écoutés PENDANT qu'on parle
  const locale = LOCALES[$("#langue").value] ? $("#langue").value : ($("#langue").value === "auto" && LOCALES[langueReponse] ? langueReponse : null);
  const e = enreg = { flux, ctx, noeud: null, morceaux: [], taux: ctx.sampleRate, debut: Date.now(),
                      coupe: 0, rang: 0, depuisCoupe: 0, envois: [], preEcoute: !!locale, locale,
                      niveaux: [], voixMs: 0, parle: false, silence: 0 };
  e.noeud = await brancherCapteur(ctx, source, d => { if (enreg === e) { e.morceaux.push(d); analyserBloc(e, d); } });
  PERSO.ecoute(() => (enreg === e ? e.niveauActuel || 0 : 0));
  $("#micro").classList.add("enreg"); $("#micro").innerHTML = ICONES.stop; $("#micro").title = "Terminer et envoyer";
  afficherEtat(`<span class="point"></span><span>Je vous écoute… <b id="chrono">0 s</b></span><span class="niveau"><i></i></span><span class="aide">envoi automatique quand vous vous taisez · Échap pour annuler</span>`);
  e.minuteur = setInterval(() => {
    const s = Math.round((Date.now() - e.debut) / 1000); const c = $("#chrono"); if (c) c.textContent = s + " s";
    if (s >= AUDIO_MAX_S) arreterEnreg(true);
    else if (!e.parle && s >= 10) { arreterEnreg(false); $("#etat_enreg").textContent = "Je n'ai entendu personne parler : réessayez près du micro."; PERSO.pasCompris(); }
  }, 250);
}
function wav16k(morceaux, taux) {
  const total = morceaux.reduce((n, m) => n + m.length, 0), tout = new Float32Array(total);
  let o = 0; for (const m of morceaux) { tout.set(m, o); o += m.length; }
  const r = taux / 16000, n = Math.floor(total / r), pcm = new Int16Array(n);
  for (let i = 0; i < n; i++) {           // moyenne sur la fenêtre : ré-échantillonnage simple et sans repliement grossier
    const a = Math.floor(i * r), b = Math.min(total, Math.floor((i + 1) * r)); let s = 0; for (let j = a; j < b; j++) s += tout[j];
    const v = Math.max(-1, Math.min(1, s / Math.max(1, b - a))); pcm[i] = v < 0 ? v * 0x8000 : v * 0x7FFF;
  }
  const buf = new ArrayBuffer(44 + pcm.byteLength), d = new DataView(buf), ecr = (p, s) => [...s].forEach((c, i) => d.setUint8(p + i, c.charCodeAt(0)));
  ecr(0, "RIFF"); d.setUint32(4, 36 + pcm.byteLength, true); ecr(8, "WAVE"); ecr(12, "fmt "); d.setUint32(16, 16, true);
  d.setUint16(20, 1, true); d.setUint16(22, 1, true); d.setUint32(24, 16000, true); d.setUint32(28, 32000, true);
  d.setUint16(32, 2, true); d.setUint16(34, 16, true); ecr(36, "data"); d.setUint32(40, pcm.byteLength, true);
  new Int16Array(buf, 44).set(pcm);
  return new Blob([buf], { type: "audio/wav" });
}
async function arreterEnreg(envoi) {
  const e = enreg; if (!e) return; enreg = null;
  clearInterval(e.minuteur); e.noeud?.disconnect(); e.flux.getTracks().forEach(t => t.stop()); e.ctx.close();
  $("#micro").classList.remove("enreg"); $("#micro").innerHTML = ICONES.micro; $("#micro").title = "Message vocal"; MOUVEMENT.niveau(null);
  if (!envoi) { $("#etat_enreg").textContent = "Enregistrement annulé."; PERSO.annule(); return; }
  const duree = (Date.now() - e.debut) / 1000;
  if (duree < 0.6) { $("#etat_enreg").textContent = "Trop court : touchez le micro, parlez, puis touchez à nouveau."; PERSO.pasCompris(); return; }
  const wav = wav16k(e.morceaux, e.taux);
  const envoyes = e.rang ? (await Promise.all(e.envois)).every(Boolean) : false;
  await envoyerVocal(wav, duree, envoyes ? e.rang : 0);   // un morceau a échoué : le serveur réécoute tout
}
/* Dioula / baoulé : morceau du vocal envoyé à une pause, pendant l'enregistrement (le serveur l'écoute tout de suite) */
const PAUSE_MORCEAU_MS = 400, MORCEAU_MIN_S = 5;   // morceaux d'au moins 5 s (plus court : moins précis)
function couperMorceau(e) {
  const blocs = e.morceaux.slice(e.coupe); e.coupe = e.morceaux.length; e.depuisCoupe = 0;
  const fd = new FormData(); fd.append("audio", wav16k(blocs, e.taux), "morceau.wav"); fd.append("session", session); fd.append("rang", e.rang++);
  fd.append("langue", e.locale || "dyu");
  e.envois.push(api("/transcrire/morceau", { method: "POST", body: fd }).then(r => r.ok).catch(() => false));
}
async function envoyerVocal(wav, duree, deja = 0) {
  occupe = true; majBoutons();
  afficherEtat(`<span class="roue"></span><span>Je transcris votre message vocal…</span>`);
  PERSO.transcrit();
  const t0 = performance.now(), fd = new FormData(); fd.append("audio", wav, "vocal.wav"); fd.append("langue", $("#langue").value); fd.append("session", session); fd.append("deja", deja);
  let r;
  try {
    const rep = await api("/transcrire", { method: "POST", body: fd });
    r = await rep.json(); if (!rep.ok) throw new Error(r.erreur || `Erreur ${rep.status}`);
  } catch (err) { occupe = false; majBoutons(); $("#etat_enreg").textContent = err.message; PERSO.erreur(err); return; }
  occupe = false; majBoutons();
  const tr = ((performance.now() - t0) / 1000);
  if (r.prise_en_charge === false) {
    $("#etat_enreg").textContent = `Langue non prise en charge pour l'instant (entendue : « ${r.langue || "?"} »). Parlez dans une des langues proposées.`;
    PERSO.pasCompris(); return;
  }
  if (!r.parole) { $("#etat_enreg").textContent = "Je n'ai pas entendu de parole. Réessayez en parlant près du micro."; PERSO.pasCompris(); return; }
  langueVocale = r.langue || langueVocale;
  $("#etat_enreg").textContent = "";
  const nomLangue = r.langue ? nomLocale(r.langue) : "?";
  let entete = `<div class="vocal">${ICONES.micro}<span>vocal ${s1(duree)} · transcrit en ${s1(tr)} · langue : ${esc(nomLangue)}</span><audio controls src="${URL.createObjectURL(wav)}"></audio></div>`;
  const loc = r.dioula || r.baoule;                // dioula / baoulé : entendu brut et mots douteux, si utile
  if (loc && (loc.brut !== r.texte || (loc.douteux || []).length)) {
    const douteux = new Set(loc.douteux || []);
    const brut = (loc.brut || "").split(/\s+/).map(w => douteux.has(w) ? `<span class="douteux" title="entendu avec peu de certitude">${esc(w)}</span>` : esc(w)).join(" ");
    entete += `<div class="entendu">${ICONES.oreille}<span>Entendu : ${brut}${(loc.reparations || []).length ? ` · réparé : ${loc.reparations.map(x => `${esc(x.entendu)} → ${esc(x.repare)}`).join(", ")}` : ""}</span></div>`;
  }
  MOUVEMENT.depuis($("#micro"));                   // votre message vocal part du micro
  const chemin = r.routage?.chemin;
  const comment = chemin === "menu" ? "langue du menu" : chemin === "menu-whisper" ? "reconnue (autre que le menu)" : "reconnue automatiquement";
  const vue = r.langue ? { code: r.langue, html: `Langue parlée : <b>${esc(nomComplet(r.langue))}</b> · ${comment}` } : null;
  envoyer(r.texte, "vocal", entete, r.langue || null, vue);
}

/* ── Son débloqué au premier geste (Safari/iPhone refusent sinon la lecture automatique) ── */
document.addEventListener("pointerdown", function debloquer() {
  try { const a = new Audio("data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA="); a.play().catch(() => {}); } catch {}
  SON.preparer();                                 // la bouche du personnage suivra le vrai son des réponses
  document.removeEventListener("pointerdown", debloquer);
}, { once: true });
document.addEventListener("keydown", () => SON.preparer(), { once: true });

/* ── Commandes ── */
function majBoutons() {
  const b = $("#envoyer"), stop = occupe && !!requete;   // pendant l'écriture d'une réponse : le bouton devient « Stop »
  if (b.dataset.etat !== (stop ? "stop" : "envoyer")) { b.innerHTML = stop ? ICONES.stop : ICONES.envoyer; b.dataset.etat = stop ? "stop" : "envoyer"; }
  b.title = stop ? "Arrêter la réponse" : "Envoyer"; b.setAttribute("aria-label", b.title);
  b.disabled = stop ? false : (occupe || !$("#texte").value.trim());
  $(".zone").classList.toggle("vide", !stop && !$("#texte").value.trim());
  $("#micro").disabled = occupe && !enreg;
}
const zone = $("#texte");
zone.addEventListener("input", () => { zone.style.height = "auto"; zone.style.height = Math.min(180, zone.scrollHeight) + "px"; majBoutons(); PERSO.frappe(zone.value); });
zone.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); $("#envoyer").click(); } });
$("#envoyer").onclick = () => {
  if (occupe && requete) { arretDemande = true; requete.abort(); return; }   // Stop
  const t = zone.value; if (!t.trim() || occupe) return; zone.value = ""; zone.style.height = "auto"; envoyer(t, "ecrit");
};
$("#micro").innerHTML = ICONES.micro;
$("#micro").onclick = () => enreg ? arreterEnreg(true) : demarrerEnreg();
document.addEventListener("keydown", e => {
  if (e.key !== "Escape") return;
  if (enreg) arreterEnreg(false); else if (feuilleOuverte) fermer();
});
async function nouvelleConversation() {
  requete?.abort(); if (enreg) arreterEnreg(false); arreterLecture(); occupe = false; fermer();
  await api("/nouvelle", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({ session }) }).catch(() => {});
  session = nouvelId(); stock.ecrire(CLE_SESSION, session); ECHANGES = []; langueVocale = langueReponse = null; $("#etat_enreg").textContent = "";
  if (LIVE.actif) envoyerLive({ type: "session", session });   // appel en cours : il continue dans la nouvelle conversation
  montrerVue("chat"); accueil(); majBoutons(); zone.focus({ preventScroll: true });
  PERSO.nouvelle();
}
$("#nouvelle").onclick = nouvelleConversation;
$("#nouvelle_h").onclick = nouvelleConversation;
$("#langue").onchange = () => {
  const v = $("#langue").value; stock.ecrire("aoceda_langue", v); PERSO.langue();
  MOUVEMENT.annonce(v === "auto" ? "Réponses dans la langue de votre message" : `Réponses en ${nomLangue(v)}`);
  if (v === "bci") reveilBaoule();
};
/* Baoulé choisi : le serveur de la voix (carte graphique Cerebrium) démarre tout de suite (~35 s s'il dormait), pour que
   la 1re réponse parlée n'attende pas. Le serveur n'en lance qu'un toutes les 45 s. */
function reveilBaoule() {
  api("/baoule/reveil", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ session }) }).catch(() => {});
}
$("#genre").onchange = () => {
  stock.ecrire("aoceda_genre", $("#genre").value);
  // en pleine lecture : on reprend la phrase en cours avec l'autre voix (déjà préparée par le serveur)
  if (lecture) { const { texte, bouton, langue, index } = lecture; arreterLecture(); ecouter(texte, bouton, langue, index); }
  if (LIVE.actif) envoyerLive({ type: "voix", genre: $("#genre").value });   // la voix de l'appel change aussi (après sa phrase)
};
$("#lecture_auto").onchange = () => stock.ecrire("aoceda_lecture_auto", $("#lecture_auto").value);

/* ── Menu « Tests et rapports » ── */
const VERDICT = { correct: ["b-ok", "✅ Correct"], partiel: ["b-partiel", "⚠️ Partiel"], incorrect: ["b-ko", "❌ Incorrect"] };
const badge = v => { const [c, t] = VERDICT[v] || ["b-neutre", v || "non jugé"]; return `<span class="badge ${c}">${t}</span>`; };
function temps(c) {
  const t = [];
  if (c.transcription_s != null) t.push(`transcription <b>${s1(c.transcription_s)}</b>`);
  if (c.premier_mot_s != null) t.push(`1er mot <b>${s1(c.premier_mot_s)}</b>`);
  if (c.total_s != null) t.push(`réponse complète <b>${s1(c.total_s)}</b>`);
  if (c.voix_reponse?.premier_son_s != null) t.push(`1er son de la réponse <b>${s1(c.voix_reponse.premier_son_s)}</b>`);
  if (c.bout_en_bout_s != null) t.push(`de la fin de la parole à la réponse écrite <b>${s1(c.bout_en_bout_s)}</b>`);
  return `<div class="temps">${t.join("<span>·</span>")}</div>`;
}
function carteCas(c) {
  const etapes = (c.etapes || []).map((e, i) => `
    <dt>${c.etapes.length > 1 ? `Tour ${i + 1} ·` : ""} question</dt><dd>${esc(e.question)}${e.langue_choisie && e.langue_choisie !== "auto" ? ` <span class="badge b-neutre">réponse forcée : ${esc(e.langue_choisie)}</span>` : ""}</dd>
    <dt>réponse</dt><dd>${rendu(e.reponse || e.erreur || "")}<div class="temps">${esc(e.fournisseur || "")} ${esc(e.modele || "")} · 1er mot <b>${s1(e.premier_mot_s)}</b> · total <b>${s1(e.total_s)}</b></div></dd>`).join("");
  const vocal = c.categorie === "vocal" ? `
    <dt>audio envoyé</dt><dd><audio controls preload="none" src="${API}/rapports/audios/${esc(c.question_audio)}"></audio><br><span class="explique">${esc(c.voix_utilisee)}</span></dd>
    <dt>texte prononcé</dt><dd>${esc(c.texte_prononce || "(aucune parole)")}</dd>
    <dt>texte compris</dt><dd>${esc(c.texte_compris || "(rien)")} <span class="badge ${c.erreur_mots_pct === 0 ? "b-ok" : c.erreur_mots_pct <= 15 ? "b-partiel" : "b-ko"}">${c.erreur_mots_pct == null ? "–" : c.erreur_mots_pct + " % de mots faux"}</span> <span class="badge b-neutre">langue trouvée : ${esc(c.langue_detectee || "aucune")}${c.certitude_langue != null ? ` (certitude ${Math.round(c.certitude_langue * 100)} %)` : ""}</span></dd>` : "";
  const voixRep = c.voix_reponse ? `<dt>réponse lue</dt><dd>${c.voix_reponse.fichier ? `<audio controls preload="none" src="${API}/rapports/audios/${esc(c.voix_reponse.fichier)}"></audio>` : ""}
    <div class="temps">${esc(c.voix_reponse.modele || "")} · 1er son <b>${s1(c.voix_reponse.premier_son_s)}</b> · tout l'audio prêt <b>${s1(c.voix_reponse.total_s)}</b>${c.voix_reponse.reecoute ? ` · réécouté : « ${esc(c.voix_reponse.reecoute)} »` : ""}</div></dd>` : "";
  return `<div class="cas"><div class="tete"><b>${esc(c.id)} · ${esc(c.titre)}</b>${badge(c.verdict)}${c.verdict_auto && c.verdict_auto !== c.verdict ? `<span class="badge b-neutre">verdict automatique : ${esc(c.verdict_auto)}</span>` : ""}<span class="badge b-neutre">${esc(c.langue)}</span></div>
    <dl class="echange">${vocal}${etapes}${voixRep}
    ${c.relecture ? `<dt>relecture</dt><dd><b>${esc(c.relecture)}</b></dd>` : ""}
    <dt>vérification</dt><dd>${esc(c.raison || "")}${(c.controles || []).length ? `<ul>${c.controles.map(k => `<li>${k.ok ? "✅" : "❌"} ${esc(k.nom)}</li>`).join("")}</ul>` : ""}</dd></dl>${temps(c)}</div>`;
}
/* ── Comparateur : voix gratuites, Gemini Live, dictée de l'appareil ── */
function comparateur(d) {
  const ligne = (titre, fichier, detail) => `<dt>${esc(titre)}</dt><dd>${fichier ? `<audio controls preload="none" src="${API}/rapports/audios/${esc(fichier)}"></audio>` : ""}<div class="temps">${detail}</div></dd>`;
  const voix = (d.voix_gratuites || []).filter(v => v.fichier).map(v => ligne(`${v.voix.replace("MultilingualNeural", " multi").replace("Neural", "")} (${v.langue})`, v.fichier,
    `${esc(v.service)} · ${esc(v.remarque || "")} · 1er son <b>${s1(v.premier_son_s)}</b>${v.duree_audio_s ? ` · ${s1(v.duree_audio_s)} d'audio` : ""}`)).join("");
  const live = (d.live || []).filter(l => l.fichier).map(l => ligne(`${l.modele} · ${l.question}`, l.fichier,
    `entendu : « ${esc(l.entendu)} » · <b>1er son ${s1(l.premier_son_apres_fin_parole_s)} après la fin de la question</b> · connexion ${s1(l.connexion_s)}`)).join("");
  return `<h2>Comparer les voix et tester la dictée (à faire vous-même)</h2>
    <p class="explique">Même texte lu par chaque voix. edge-tts = voix neurales Microsoft sans clé (non officiel) ; Kokoro = installé sur le PC, hors ligne, illimité.</p>
    <div class="cas"><dl class="echange">${voix}</dl></div>
    ${live ? `<h2>Gemini Live (réponse parlée directe)</h2><p class="explique">Un vrai message vocal envoyé à l'API Gemini Live : elle écoute et répond directement en voix, sans étape de transcription ni de voix séparée.</p><div class="cas"><dl class="echange">${live}</dl></div>` : ""}
    <h2>Dictée de l'appareil (gratuite)</h2>
    <p class="explique">Utilise la reconnaissance vocale intégrée au navigateur (Edge, Chrome, Safari ; pas Firefox). Cliquez, parlez, et regardez le texte apparaître. Le son part vers le service du navigateur (Microsoft pour Edge, Google pour Chrome).</p>
    <div class="cas"><div class="tete"><select id="dictee_langue"><option value="fr-FR">Français</option><option value="en-US">English</option><option value="es-ES">Español</option><option value="ar-SA">العربية</option></select>
      <button class="btn" id="dictee_btn">Parler (dictée de l'appareil)</button></div>
      <p id="dictee_texte" style="font-size:18px;margin:10px 0 4px">…</p><div class="temps" id="dictee_temps"></div></div>`;
}
function brancherDictee() {
  const b = $("#dictee_btn"); if (!b) return;
  const R = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!R) { b.disabled = true; $("#dictee_texte").textContent = "Ce navigateur n'a pas de dictée intégrée (essayez Edge ou Chrome)."; return; }
  b.onclick = () => {
    const r = new R(); r.lang = $("#dictee_langue").value; r.interimResults = true;
    let t0 = performance.now(), finParole = null, premier = null;
    b.disabled = true; b.textContent = "Je vous écoute…"; $("#dictee_texte").textContent = ""; $("#dictee_temps").textContent = "";
    r.onspeechend = () => { finParole = performance.now(); };
    r.onresult = e => { premier = premier ?? performance.now() - t0; let t = ""; for (const x of e.results) t += x[0].transcript;
      $("#dictee_texte").textContent = t; if (e.results[e.results.length - 1].isFinal) {
        $("#dictee_temps").innerHTML = `texte final <b>${finParole ? s1((performance.now() - finParole) / 1000) : "–"}</b> après la fin de votre parole · 1er mot affiché ${s1(premier / 1000)} après le clic`; } };
    r.onerror = e => { $("#dictee_texte").textContent = "Erreur : " + e.error; };
    r.onend = () => { b.disabled = false; b.textContent = "Parler (dictée de l'appareil)"; };
    r.start();
  };
}
/* ── Dioula (étape 2) / baoulé (étape 3) : bilan des mesures + cas réels à écouter ── */
const VERDICT_SENS = { oui: ["b-ok", "✅ compris"], partiel: ["b-partiel", "⚠️ en partie"], non: ["b-ko", "❌ pas compris"] };
function sectionDioula(d, titre = "Dioula (étape 2)", etape = "2") {
  if (!d) return "";
  const r = d.resume, carte = (v, t) => `<div class="carte"><b>${v}</b><span>${esc(t)}</span></div>`;
  const cas = (d.cas || []).map(c => {
    const t = c.temps || {}, v = VERDICT_SENS[c.verdict] || ["b-neutre", c.verdict || "–"];
    return `<div class="cas"><div class="tete"><b>${esc(c.id)} · ${esc(c.titre)}</b><span class="badge ${v[0]}">${v[1]}</span>
      <span class="badge b-neutre">langue trouvée : ${esc(nomLocale(c.langue))}</span></div>
      <dl class="echange">
        <dt>vocal envoyé</dt><dd><audio controls preload="none" src="${API}/rapports/audios/${esc(c.audio)}"></audio>${c.texte_prononce ? `<br><span class="explique">prononcé : ${esc(c.texte_prononce)}</span>` : ""}</dd>
        <dt>entendu</dt><dd>${esc(c.entendu)}${c.dioula && c.dioula.brut !== c.entendu ? `<br><span class="explique">avant réparation : ${esc(c.dioula.brut)}</span>` : ""}</dd>
        ${c.sens ? `<dt>sens réel</dt><dd>${esc(c.sens)}</dd>` : ""}
        ${c.intention ? `<dt>compris</dt><dd><b>${esc(c.intention)}</b> <span class="badge b-neutre">certitude ${esc(c.certitude || "–")}</span></dd>` : ""}
        <dt>réponse</dt><dd>${esc(c.reponse || "")}${c.reponse_fr ? `<br><span class="explique">en français : ${esc(c.reponse_fr)}</span>` : ""}
          ${c.son ? `<br><audio controls preload="none" src="${API}/rapports/audios/${esc(c.son)}"></audio> <span class="explique">${esc(c.voix || "")}</span>` : ""}</dd>
      </dl>
      <div class="temps">transcription <b>${s1(t.transcription_s)}</b>${t.intention_s != null ? ` · « compris » affiché <b>${s1(t.intention_s)}</b>` : ""}
        · 1re phrase <b>${s1(t.premiere_phrase_s)}</b> · 1er son <b>${s1(t.premier_son_s)}</b> · réponse complète <b>${s1(t.reponse_complete_s)}</b>
        <span>(depuis l'envoi du vocal)</span></div></div>`;
  }).join("");
  return `<h2>${esc(titre)}</h2>
    <p class="explique">${esc(d.contexte || "")}</p>
    ${d.bilan ? `<details class="cas"><summary><b>Bilan de l'étape ${esc(etape)}</b> : ce qui marche, comment, les mesures, les limites et ce qu'il vous reste à valider</summary><pre>${esc(d.bilan)}</pre></details>` : ""}
    <div class="cartes">${(r || []).map(x => carte(x.valeur, x.texte)).join("")}</div>
    ${(d.tableaux || []).map(tb => `<h2>${esc(tb.titre)}</h2><p class="explique">${esc(tb.explication || "")}</p>
      <div class="cas" style="overflow-x:auto"><table>
      <tr>${tb.colonnes.map(c => `<th style="text-align:left;padding:6px 8px;border-bottom:1px solid var(--bord)">${esc(c)}</th>`).join("")}</tr>
      ${tb.lignes.map(l => `<tr>${l.map(v => `<td style="padding:6px 8px;border-bottom:1px solid var(--bord)">${esc(v)}</td>`).join("")}</tr>`).join("")}</table></div>`).join("")}
    <h2>Vocaux réels passés dans le vrai serveur</h2>
    <p class="explique">Chaque vocal a été envoyé exactement comme le micro de la page (mode Automatique). Écoutez la question et la réponse.</p>
    ${cas}
    ${d.limites ? `<h2>Limites connues</h2><div class="cas"><ul>${d.limites.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>` : ""}`;
}
/* ── Périodes (« la semaine dernière »…) : calculées par le serveur, même question = même réponse ── */
function sectionPeriodes(p) {
  if (!p || !p.verdict) return "";
  const v = p.verdict, ok = v.memes_periodes && v.memes_kwh && v.parametre_periode_utilise && v.dates_dites_a_voix_haute;
  const lecture = o => `<li><b>${esc(o.args.periode || `${o.args.date_debut || ""} → ${o.args.date_fin || ""}`)}</b> : ${esc(o.periode || o.erreur || "")}${o.kwh != null ? ` · <b>${String(o.kwh).replace(".", ",")} kWh</b>` : ""}</li>`;
  const meme = p.meme_question.map((x, i) => `<dt>appel ${i + 1}</dt><dd><ul>${x.outils.map(lecture).join("")}</ul>${esc(x.reponses[x.reponses.length - 1] || "")}</dd>`).join("");
  const autres = p.plusieurs_periodes ? p.plusieurs_periodes.questions.map((q, i) => {
    const o = p.plusieurs_periodes.outils[i];
    return `<dt>${esc(q)}</dt><dd>${o ? `<ul>${lecture(o)}</ul>` : ""}${esc(p.plusieurs_periodes.reponses[i] || "")}</dd>`;
  }).join("") : "";
  return `<h2>Les périodes (« la semaine dernière »…)</h2>
    <p class="explique">Avant, le modèle calculait lui-même les dates : pour la même question, tantôt la semaine du lundi au dimanche (127,63 kWh), tantôt les 7 jours avant aujourd'hui (112,48 kWh). Maintenant le serveur AOCEDA calcule la période (une semaine va du lundi au dimanche ; « 7 derniers jours » comme la page Historique) et l'agent dit les dates.</p>
    <div class="cas"><div class="tete"><b>Même question, 3 appels séparés : « Combien ai-je consommé la semaine dernière ? »</b>
      <span class="badge ${ok ? "b-ok" : "b-ko"}">${ok ? "✅ même période, même chiffre, dates dites" : "❌ à revoir"}</span></div>
      <dl class="echange">${meme}</dl></div>
    ${autres ? `<div class="cas"><div class="tete"><b>Autres périodes, dans un même appel</b></div><dl class="echange">${autres}</dl></div>` : ""}`;
}
/* ── Appel Live (étape 4) : bilan + essais réels (appel de bout en bout, passage de réserve, Edge) ── */
function sectionLive(d) {
  if (!d || !(d.bout_en_bout || d.reserves || d.navigateur || d.periodes)) return "";
  const carte = (v, t) => `<div class="carte"><b>${v}</b><span>${esc(t)}</span></div>`;
  const be = d.bout_en_bout, rs = d.reserves || [], nav = d.navigateur || [];
  const reussie = e => !!(e.agent && !e.erreur);
  const etapes = (be ? be.etapes : []).map((e, i) => {
    const vocal = e.question === "V1";
    return `<div class="cas"><div class="tete"><b>${i + 1}. ${esc(vocal ? "Message vocal (V1)" : e.question)}</b>
      <span class="badge ${reussie(e) ? "b-ok" : "b-ko"}">${reussie(e) ? "✅ répondu" : "❌ " + esc(e.erreur || "sans réponse")}</span>
      ${e.reserve ? `<span class="badge b-neutre">${esc(e.reserve.replace("vision True", "voit l’écran").replace("vision False", "sans vision"))}</span>` : ""}</div>
      <dl class="echange">
        ${vocal ? `<dt>vocal envoyé</dt><dd><audio controls preload="none" src="${API}/rapports/audios/questions/V1.wav"></audio>${e.vous ? `<br><span class="explique">entendu : ${esc(e.vous)}</span>` : ""}</dd>` : ""}
        ${(e.outils || []).length || (e.page || []).length ? `<dt>a fait</dt><dd>${esc([...(e.outils || []).map(o => "lecture AOCEDA " + o), ...(e.page || [])].join(", "))}</dd>` : ""}
        <dt>réponse</dt><dd>${esc(e.agent || "")}${e.fichier ? `<br><audio controls preload="none" src="${API}/rapports/audios/${esc(e.fichier)}"></audio>` : ""}</dd>
      </dl><div class="temps">1er son <b>${s1(e.premier_son_s)}</b> · voix <b>${s1(e.audio_s)}</b></div></div>`;
  }).join("");
  const scenarios = rs.map(s => `<div class="cas"><div class="tete"><b>${esc(s.scenario)}</b>
      <span class="badge ${s.ok ? "b-ok" : "b-ko"}">${s.ok ? "✅ réussi" : "❌ échec"}</span></div>
      <dl class="echange">
        <dt>réserve utilisée</dt><dd>${esc((s.reserves_utilisees || []).join(", ") || "aucune")}${s.dernier_etat ? ` · vision : ${s.dernier_etat.vision ? "oui" : "non"}` : ""}</dd>
        ${(s.erreurs_vues || []).length ? `<dt>erreur rencontrée</dt><dd>${esc(s.erreurs_vues.join(" ; "))}</dd>` : ""}
        <dt>réponse</dt><dd>${esc(s.agent || "")}</dd>
      </dl><div class="temps">1er son <b>${s1(s.premier_son_s)}</b> · images jointes <b>${s.images_jointes}</b> · captures demandées <b>${s.captures_demandees}</b></div></div>`).join("");
  return `<h2>Appel Live avec l'agent (étape 4)</h2>
    <p class="explique">Vrai serveur, vrai Gemini Live, vraies données AOCEDA du compte de démonstration ; le micro est remplacé par nos vocaux de test.</p>
    ${d.bilan ? `<details class="cas"><summary><b>Bilan de l'étape 4</b> : ce qui marche, comment, les mesures, les réserves modèle × compte, les limites et ce qu'il vous reste à valider</summary><pre>${esc(d.bilan)}</pre></details>` : ""}
    <div class="cartes">
      ${be ? carte(`${be.etapes.filter(reussie).length}/${be.etapes.length}`, "étapes de l'appel réel réussies") : ""}
      ${rs.length ? carte(`${rs.filter(s => s.ok).length}/${rs.length}`, "passages de réserve réussis (en vrai)") : ""}
      ${nav.length ? carte(`${nav.filter(e => e.ok).length}/${nav.length}`, "étapes réussies dans Edge") : ""}
      ${be && be.fin ? carte(s1(be.fin.duree_s), "durée de l'appel réel") : ""}
    </div>
    ${etapes ? `<h2>Un appel réel, de bout en bout</h2><p class="explique">Question sur les données, vrai vocal, action sur la page, « regarde mon écran », au revoir. Écoutez la voix de l'agent.</p>${etapes}` : ""}
    ${be && be.cle_fausse ? `<div class="cas">Clé volontairement fausse : Google répond « ${esc(be.cle_fausse.erreur || "")} », reconnue comme <b>${esc(be.cle_fausse.nature || "–")}</b>.</div>` : ""}
    ${scenarios ? `<h2>Passage d'une réserve à l'autre (en vrai)</h2><p class="explique">Une réserve = un modèle Gemini Live sur un compte. On provoque l'échec de la première et on vérifie que l'appel continue sur la suivante.</p>${scenarios}` : ""}
    ${sectionPeriodes(d.periodes)}
    ${nav.length ? `<h2>Appel Live dans Microsoft Edge</h2><p class="explique">La vraie page pilotée automatiquement ; le micro joue un vocal de test. Dans cet essai, Edge partage une image de test verte à la place de l'écran.</p>
    <div class="cas"><ul>${nav.map(e => `<li>${e.ok ? "✅" : "❌"} <b>${esc(e.etape)}</b>${e.detail ? " : " + esc(e.detail) : ""}</li>`).join("")}</ul></div>` : ""}`;
}
/* ── Personnage animé (étape 5) : essai dans Edge + banc d'essai des animations + captures ── */
function sectionPersonnage(d) {
  if (!d || !(d.etapes || []).length) return "";
  const carte = (v, t) => `<div class="carte"><b>${v}</b><span>${esc(t)}</span></div>`, b = d.banc;
  return `<h2>Personnage animé de l'assistant (étape 5)</h2>
    <p class="explique">Le personnage vit ce que fait le chatbot : il vous regarde écrire, réfléchit, écrit, parle (la bouche suit le vrai son), écoute vos vocaux ;
      pendant l'appel Live il remplace le rond (ça sonne, il écoute, parle avec les mains, réagit à ce que disent vos données). Essai du ${esc(String(d.date).replace("T", " à "))}
      dans Edge : réponses, voix et appel Live simulés (aucun quota), micro remplacé par un vocal de test.</p>
    <div class="cartes">${carte(`${d.etapes.filter(e => e.ok).length}/${d.etapes.length}`, "étapes de l'essai réussies")}
      ${b ? carte(b.actions, "animations passées au banc d'essai (image par image)") + carte(b.sauts + b.sauts_interruption, "saut ou coupure détecté") : ""}</div>
    <div class="cas"><ul>${d.etapes.map(e => `<li>${e.ok ? "✅" : "❌"} <b>${esc(e.etape)}</b>${e.detail ? ` <span class="explique">· ${esc(e.detail)}</span>` : ""}</li>`).join("")}</ul></div>
    ${(d.captures || []).length ? `<div class="vignettes">${d.captures.map(c => `<a href="${API}/rapports/captures/${esc(c)}" target="_blank" rel="noopener"><img src="${API}/rapports/captures/${esc(c)}" alt="" loading="lazy"><span>${esc(c.replace(/^perso_\d+_|\.png$/g, "").replace(/_/g, " "))}</span></a>`).join("")}</div>` : ""}`;
}
/* ── L'agent agit sur la page + cartes de données (05/10/2026) : essai dans Edge, captures ── */
function sectionAgentPage(d) {
  if (!d || !(d.etapes || []).length) return "";
  const carte = (v, t) => `<div class="carte"><b>${v}</b><span>${esc(t)}</span></div>`;
  return `<h2>L'agent agit sur la page, les données s'affichent (05/10)</h2>
    <p class="explique">Pendant l'appel Live, l'agent agit comme une personne (outils « comme Playwright ») : il lit l'écran, puis clique, écrit,
      choisit dans une liste ou montre un élément ; on voit son curseur doré partir du personnage, glisser, entourer l'élément et appuyer.
      Les données lues s'affichent en cartes animées (vraies valeurs AOCEDA). Essai du ${esc(String(d.date).replace("T", " à "))} dans Edge :
      appel et réponses simulés (aucun quota), ordinateur (zoom 125 %), téléphone et mouvements réduits.</p>
    <div class="cartes">${carte(`${d.etapes.filter(e => e.ok).length}/${d.etapes.length}`, "étapes réussies")}${carte((d.erreurs_js || []).length, "erreur JavaScript")}</div>
    <div class="cas"><ul>${d.etapes.map(e => `<li>${e.ok ? "✅" : "❌"} <b>${esc(e.etape)}</b>${e.detail ? ` <span class="explique">· ${esc(e.detail)}</span>` : ""}</li>`).join("")}</ul></div>
    ${(d.captures || []).length ? `<div class="vignettes">${d.captures.map(c => `<a href="${API}/rapports/captures/${esc(c)}" target="_blank" rel="noopener"><img src="${API}/rapports/captures/${esc(c)}" alt="" loading="lazy"><span>${esc(c.replace(/^agent_\d+_|\.png$/g, "").replace(/_/g, " "))}</span></a>`).join("")}</div>` : ""}`;
}
/* ── L'agent qui planifie (05/10/2026) : une demande = un plan, exécuté d'un coup ; essais réels + comparatif des modèles ── */
function sectionAgentPlan(d) {
  if (!d || !(d.plan || d.live || d.comparatif)) return "";
  const carte = (v, t) => `<div class="carte"><b>${v}</b><span>${esc(t)}</span></div>`, s = x => `${String(x ?? "–").replace(".", ",")} s`;
  const p = d.plan, l = d.live, c = d.comparatif;
  const modeles = c ? [...c.modeles].sort((a, b) => b.reussies - a.reussies || a.cout_moyen_par_demande_centimes - b.cout_moyen_par_demande_centimes) : [];
  return `<h2>L'agent qui planifie : toute une demande d'un coup (05/10)</h2>
    <p class="explique">Avant, l'appel faisait un aller-retour avec le modèle à chaque clic (15 à 25 s pour 5 étapes). Maintenant : la page donne la
      carte de toute l'application, DeepSeek Flash renvoie le plan ENTIER en une fois, la page l'exécute vite et vérifie chaque étape
      (corrigé si besoin) ; une demande déjà réussie est rejouée sans modèle (raccourci appris). Ce qui est réservé à la personne reste refusé.</p>
    <div class="cartes">${p ? carte(`${p.reussies}/${p.total}`, "demandes réussies (vrai DeepSeek, vraie page)") + carte(s(p.duree_moyenne_plan_s), "par demande (plan + exécution)")
      + carte(s(p.duree_moyenne_raccourci_s), "par demande déjà apprise") + carte(`${(p.cout_total_dollars * 100).toFixed(2).replace(".", ",")} c`, `centime de $ pour les ${p.total} demandes`) : ""}
      ${l ? carte(`${l.reussies}/${l.total}`, "dans un vrai appel Gemini Live (de bout en bout)") : ""}</div>
    ${p ? `<div class="cas"><div class="tete"><b>Vraie page, vrai DeepSeek</b></div><ul>${p.demandes.map(x => `<li>${x.ok ? "✅" : "❌"} <b>« ${esc(x.objectif)} »</b>
      <span class="badge b-neutre">${s(x.duree_s)} · ${esc(x.source || "refus")}</span><br><span class="explique">${esc(x.fait || "")}${(x.faites || []).length ? ` · ${esc(x.faites.join(" → "))}` : ""}</span></li>`).join("")}</ul></div>` : ""}
    ${l ? `<div class="cas"><div class="tete"><b>Dans l'appel Live (demandes tapées, micro coupé)</b></div><ul>${l.demandes.map(x => `<li>${x.ok ? "✅" : "❌"} <b>« ${esc(x.demande)} »</b>
      <span class="badge b-neutre">page prête en ${s(x.etat_atteint_s)}</span><br><span class="explique">l'agent : ${esc(x.agent)}</span></li>`).join("")}</ul></div>` : ""}
    ${modeles.length ? `<div class="cas" style="overflow-x:auto"><div class="tete"><b>Quel modèle pour planifier ? (4 demandes, mêmes règles)</b></div><table>
      <tr><th style="text-align:left">Modèle</th><th>Réussies</th><th>Centime de $ / demande</th><th>Temps / demande</th></tr>
      ${modeles.map(m => `<tr><td>${esc(m.modele)}</td><td style="text-align:center">${m.reussies}/${m.total}</td><td style="text-align:center">${String(m.cout_moyen_par_demande_centimes).replace(".", ",")}</td><td style="text-align:center">${s(m.duree_moyenne_s)}</td></tr>`).join("")}</table>
      <p class="explique">Ici, chaque modèle agissait clic par clic (l'ancienne façon) : c'est ce qui a départagé les modèles. Retenu : DeepSeek Flash sans réflexion.</p></div>` : ""}`;
}
/* ── Langue des réponses (05/10/2026) : vrai Gemini Live (texte et voix) et vrai DeepSeek ── */
function sectionLangue(d) {
  if (!d || !(d.live || d.chat)) return "";
  const carte = (v, t) => `<div class="carte"><b>${v}</b><span>${esc(t)}</span></div>`;
  const ligne = x => `<li>${x.ok ? "✅" : "❌"} <b>« ${esc(x.question)} »</b> <span class="badge b-neutre">menu ${esc(x.menu)}${x.mode ? ` · ${x.mode === "vocal" ? "voix" : "texte"}` : ""}</span>
    ${x.entendu && x.mode === "vocal" ? `<br><span class="explique">entendu : « ${esc(x.entendu)} »</span>` : ""}<br>attendu : ${esc(x.attendue)} · réponse en <b>${esc(x.langue || "–")}</b>
    ${x.sans_voix || x.invente != null ? ` · ${x.invente ? "❌ mots inventés" : "rien d'inventé"}` : ""} : <span class="explique">${esc(x.reponse || "")}</span></li>`;
  const live = d.live, chat = d.chat;
  return `<h2>Langue des réponses : demande respectée, rien d'inventé (05/10)</h2>
    <p class="explique">« Réponds en anglais » : toutes les réponses restent en anglais, même si vous parlez français, jusqu'à ce que vous changiez
      (autre demande ou autre langue dans le menu) ; sans demande, il suit votre langue. Baoulé, dioula, agni... : l'appel vocal ne les parle pas,
      il le dit honnêtement (le chat écrit comprend le dioula et le baoulé). Essais avec les VRAIS modèles.</p>
    <div class="cartes">${live ? carte(`${live.reussis}/${live.total}`, "appel Live (vrai Gemini, texte et voix)") : ""}${chat ? carte(`${chat.reussis}/${chat.total}`, "chat écrit (vrai DeepSeek)") : ""}</div>
    ${live ? `<div class="cas"><div class="tete"><b>Appel Live</b><span class="badge b-neutre">${esc(String(live.date).replace("T", " à "))}</span></div><ul>${live.cas.map(ligne).join("")}</ul></div>` : ""}
    ${chat ? `<div class="cas"><div class="tete"><b>Chat écrit</b><span class="badge b-neutre">${esc(String(chat.date).replace("T", " à "))}</span></div><ul>${chat.cas.map(ligne).join("")}</ul></div>` : ""}`;
}
/* ── Voix baoulé sur GPU Cerebrium + détection de la langue des vocaux (06/10/2026), vrai serveur ── */
function sectionVoixGpu(d) {
  if (!d || !(d.detection || d.voix_gpu)) return "";
  const carte = (v, t) => `<div class="carte"><b>${v}</b><span>${esc(t)}</span></div>`, s = x => `${String(x ?? "–").replace(".", ",")} s`;
  const NOMS = { bci: "baoulé", dyu: "dioula", fr: "français", en: "anglais" };
  const det = d.detection, v = d.voix_gpu, tours = v?.tours || [];
  return `<h2>Voix baoulé sur carte graphique (Cerebrium) et détection de la langue (06/10)</h2>
    <p class="explique">Vrai serveur, vrai DeepSeek, vrai Google, vraie machine Cerebrium. La voix baoulé (même voix OmniVoice qu'avant) est
      fabriquée sur une carte graphique louée : toutes les phrases d'une réponse en un seul envoi. La machine est réveillée dès que le baoulé
      est choisi ou entendu. Si Cerebrium ne répond pas, la voix est faite sur le serveur (plus lent).</p>
    <div class="cartes">${det ? carte(`${det.reussis}/${det.total}`, "vocaux : langue bien reconnue (menu Automatique)") : ""}
      ${v ? carte(`${v.reussis}/${v.total}`, "réponses baoulé avec voix GPU") + carte(s(v.attente_voix_machine_allumee_mediane_s), "voix prête après le texte (machine allumée, médiane)")
        + (tours[0] ? carte(s(tours[0].attente_voix_s), "voix après le texte, machine endormie (réveil au choix du menu)") : "") : ""}</div>
    ${det ? `<div class="cas"><div class="tete"><b>Détection de la langue des vocaux</b><span class="badge b-neutre">${esc(String(d.date).replace("T", " à "))}</span></div><ul>${det.cas.map(c =>
      `<li>${c.ok ? "✅" : "❌"} <b>${esc(c.fichier)}</b> : attendu ${esc(NOMS[c.attendue] || c.attendue)}, entendu <b>${esc(NOMS[c.entendue] || c.entendue || "–")}</b>
       <span class="badge b-neutre">${s(c.duree_s)} · ${esc(c.chemin || "")}</span><br><span class="explique">« ${esc(c.texte || "")} »</span></li>`).join("")}</ul></div>` : ""}
    ${v ? `<div class="cas"><div class="tete"><b>Réponses baoulé et leur voix</b></div><ul>${tours.map(t =>
      `<li>${t.ok ? "✅" : "❌"} <b>Tour ${t.tour}</b> (${esc(t.entree)}, machine ${esc(t.machine)}) <span class="badge b-neutre">voix ${s(t.attente_voix_s)} après le texte · ${t.audio_s ?? "–"} s de voix</span>
       <br><span class="explique">transcription ${s(t.transcription_s)} · texte ${s(t.reponse_ecrite_s)} · total ${s(t.total_depuis_la_fin_du_vocal_s)} · « ${esc(t.reponse_fr || "")} »</span>
       ${t.fichier_son ? `<br><audio controls preload="none" src="${API}/rapports/audios/voix_gpu/${esc(t.fichier_son)}"></audio>` : ""}</li>`).join("")}</ul>
      <p class="explique">Crédit Cerebrium : ${esc(String(v.credit_avant?.restant_usd ?? "–"))} $ avant, ${esc(String(v.credit_apres?.restant_usd ?? "–"))} $ après (Cerebrium compte avec quelques minutes de retard).</p></div>` : ""}`;
}
/* ── Chaîne robuste du baoulé (06/10/2026) : essai réel, réparation mesurée, carnet, liste d'attente à valider ── */
function sectionChaineBaoule(d) {
  if (!d) return "";
  const carte = (v, t) => `<div class="carte"><b>${v}</b><span>${esc(t)}</span></div>`, s = x => `${String(x ?? "–").replace(".", ",")} s`;
  const e = d.essai, r = d.reparation, c = d.carnet;
  const jeux = e ? Object.entries(e.par_jeu).map(([nom, j]) => `<li><b>${esc(nom)}</b> : ${j.ok}/${j.total} bonne demande du premier coup,
    ${j.ok_top3}/${j.total} parmi les 3 hypothèses${j.sur_et_faux ? ` · <b>${j.sur_et_faux} sûre(s) et fausse(s)</b>` : ""}</li>`).join("") : "";
  const ratees = e ? e.cas.filter(x => !x.ok && x.texte).map(x => `<li>attendu <b>${esc(x.attendu)}</b>, trouvé <b>${esc(x.trouve || x.erreur || "–")}</b>
    (${esc(x.note || "")}, ${esc(x.mode || "")}) · « ${esc(x.texte)} »<br><span class="explique">${esc(x.origine || "")} · interprète : « ${esc(x.google || "")} »</span></li>`).join("") : "";
  return `<h2>Baoulé : la chaîne robuste (06/10)</h2>
    <p class="explique">Un message baoulé suit un seul passage en 4 blocs : savoir ce qui a été dit (réparation contrôlée par le son, deux
      interprètes), savoir ce que la personne veut (l'IA choisit dans une liste fermée de demandes), décider (un règlement : confirmation
      obligatoire pour l'argent et les appareils, note de confiance), répondre (vraies données AOCEDA, traduction contre-vérifiée). Aucun
      modèle entraîné ; carnet de mots de sources libres.</p>
    <div class="cartes">${e ? carte(`${e.ok}/${e.total}`, "bonne demande du premier coup (essai réel)") + carte(String(e.sur_et_faux), "réponses sûres mais fausses")
        + carte(s(e.duree_mediane_s), "pour comprendre (médiane)") : ""}
      ${r ? carte(`${r.ameliores} / ${r.abimes}`, `phrases améliorées / abîmées par la réparation (${r.vocaux} vrais vocaux)`) : ""}
      ${c ? carte(String(c.mots_connus), `mots baoulé connus · ${c.entrees} entrées GATITOS · ${c.fiches} fiches de sens`) : ""}</div>
    ${e ? `<div class="cas"><div class="tete"><b>Essai réel</b><span class="badge b-neutre">${esc(String(e.date).replace("T", " à "))}</span></div>
      <ul>${jeux}</ul><p class="explique">${esc(e.limite)}</p>${ratees ? `<p class="explique">Les ratés :</p><ul>${ratees}</ul>` : ""}</div>` : ""}
    <div class="cas"><div class="tete"><b>Liste d'attente : phrases confirmées par les utilisateurs</b></div>
      <p class="explique">Une phrase n'entre dans la banque d'exemples qu'après votre validation (un exemple faux serait sinon réutilisé pour toujours).</p>
      <div id="attente_baoule"><div class="vide-liste">Chargement…</div></div></div>`;
}
async function remplirAttenteBaoule() {
  const el = $("#attente_baoule"); if (!el) return;
  let d; try { d = await (await api("/baoule/exemples")).json(); } catch { el.innerHTML = `<div class="vide-liste">Liste indisponible.</div>`; return; }
  // réservée au PC du chatbot (phrases d'autres personnes, banque qui sert à tout le monde) : un visiteur voit pourquoi
  if (d.erreur || !Array.isArray(d.demandes)) { el.innerHTML = `<div class="vide-liste">${esc(d.erreur || "Liste indisponible.")}</div>`; return; }
  const noms = Object.fromEntries(d.demandes.map(x => [x.id, x.libelle]));
  el.innerHTML = (d.attente.length ? d.attente.map(x => `<div class="ligne-attente" data-id="${esc(x.id)}"><span>« ${esc(x.bci)} » → <b>${esc(noms[x.demande] || x.demande)}</b>
      <small>${esc(x.origine)} · ${esc(String(x.date).replace("T", " "))}</small></span>
      <button class="ecouter" data-faire="valider">Valider</button><button class="ecouter" data-faire="rejeter">Rejeter</button></div>`).join("")
    : `<div class="vide-liste">Aucune phrase en attente.</div>`)
    + `<p class="explique">Banque : ${d.banque} exemples.${d.mots_manquants.length ? ` Mots cherchés sans résultat (pour un locuteur) : ${d.mots_manquants.map(m => esc(m.mot)).join(", ")}.` : ""}</p>`;
  el.querySelectorAll("[data-faire]").forEach(b => b.onclick = async () => {
    const id = b.closest("[data-id]").dataset.id;
    const r = await api(`/baoule/exemples/${b.dataset.faire}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id }) }).catch(() => null);
    if (r && !r.ok) { const e = await r.json().catch(() => ({})); MOUVEMENT.annonce(e.erreur || `Refusé (erreur ${r.status})`); }
    remplirAttenteBaoule();
  });
}
async function chargerTests() {
  const el = $("#tests");
  let d; try { d = await (await api("/tests")).json(); } catch { el.textContent = "Impossible de charger les résultats."; return; }
  const ev = d.evaluation;
  setTimeout(remplirAttenteBaoule, 0);
  const locales = sectionChaineBaoule(d.chaine_baoule) + sectionVoixGpu(d.voix_gpu) + sectionAgentPlan(d.agent_plan) + sectionAgentPage(d.agent_page) + sectionLangue(d.langue) + sectionPersonnage(d.personnage) + sectionLive(d.etape4)
    + sectionDioula(d.baoule, "Baoulé (étape 3)", "3") + sectionDioula(d.dioula);
  if (!ev) { el.innerHTML = locales || `<p class="explique">Aucune évaluation n'a encore été lancée (tests\\mesures\\evaluation.py).</p>`; return; }
  const r = ev.resume, carte = (v, t) => `<div class="carte"><b>${v}</b><span>${t}</span></div>`;
  el.innerHTML = `
    ${locales}
    ${d.bilan ? `<details class="cas"><summary><b>Bilan de l'étape 1</b> : ce qui a été fait, corrigé, les limites et ce qu'il vous reste à valider</summary><pre>${esc(d.bilan)}</pre></details>` : ""}
    <h2>Résumé de l'évaluation</h2>
    <p class="explique">Lancée le ${esc(ev.date)} contre le vrai serveur, avec les vraies API (aucune réponse simulée). ${esc(ev.contexte || "")}${ev.relue ? " Chaque réponse a ensuite été relue (ligne « relecture »)." : ""}</p>
    <div class="cartes">
      ${carte(`${r.corrects}/${r.total}`, "réponses correctes")}
      ${carte(`${r.ecrits_corrects}/${r.ecrits}`, "questions écrites correctes")}
      ${carte(`${r.vocaux_corrects}/${r.vocaux}`, "messages vocaux corrects")}
      ${carte(r.mots_faux_moyen_pct == null ? "–" : r.mots_faux_moyen_pct + " %", "mots mal compris (vocal, moyenne)")}
      ${carte(s1(r.premier_mot_median_s), "1er mot (médiane)")}
      ${carte(s1(r.total_median_s), "réponse complète (médiane)")}
      ${carte(s1(r.transcription_mediane_s), "transcription vocale (médiane)")}
      ${carte(s1(r.premier_son_median_s), "1er son du bouton Écouter (médiane)")}
      ${carte(r.relances_deepseek ?? "–", "réponses venues de la relance DeepSeek (1re demande trop lente)")}
    </div>
    <h2>Questions écrites (français, anglais${ev.cas.some(c => c.bonus) ? " et bonus autres langues" : ""})</h2>
    <p class="explique">Chaque question est envoyée comme depuis la page. Le verdict combine des contrôles automatiques (langue de la réponse, pas de chiffre inventé, mémoire…) et la relecture.</p>
    ${ev.cas.filter(c => c.categorie === "ecrit").map(carteCas).join("")}
    <h2>Messages vocaux (« comme une vraie personne qui parle »)</h2>
    <p class="explique">Voix de synthèse Windows (Paul, Hortense, David, Mark…), parfois avec bruit de fond. Le fichier est envoyé exactement comme le micro de la page le ferait ; Whisper trouve la langue tout seul.</p>
    ${ev.cas.filter(c => c.categorie === "vocal").map(carteCas).join("")}
    ${ev.voix ? `<h2>Voix des réponses (bouton « Écouter »)</h2>
    <p class="explique">${esc(ev.voix.note)} Mesures du ${esc(ev.voix.date)}. « Réécoute » : l'audio produit est retranscrit et comparé au texte, pour vérifier que la voix lit bien ce qui est écrit.</p>
    <div class="cas"><dl class="echange">${ev.voix.mesures.map(m => `
      <dt>${esc(m.id)}</dt><dd>${m.fichier ? `<audio controls preload="none" src="${API}/rapports/audios/${esc(m.fichier)}"></audio>` : ""}
      <div class="temps">${esc(m.modele)} · ${m.morceaux} morceaux · 1er son <b>${s1(m.premier_son_s)}</b> · tout l'audio prêt <b>${s1(m.total_s)}</b> · durée lue <b>${s1(m.duree_audio_s)}</b>${m.reecoute_mots_faux_pct != null ? ` · réécoute : <b>${m.reecoute_mots_faux_pct} %</b> de mots différents` : ""}</div></dd>`).join("")}</dl></div>` : ""}
    ${comparateur(d)}
    ${d.navigateur ? `<h2>Essai de la vraie page dans Microsoft Edge</h2><p class="explique">Piloté automatiquement ; le micro est simulé par un fichier audio de test (V1) qui « parle » dans la page.</p>
    <div class="cas"><ul>${d.navigateur.map(e => `<li>${e.ok ? "✅" : "❌"} <b>${esc(e.etape)}</b>${e.detail ? " : " + esc(e.detail) : ""}</li>`).join("")}</ul></div>` : ""}
    ${d.tests_unitaires ? `<h2>Tests automatiques du code</h2><p class="explique">Vérifient la logique sans Internet (fournisseurs simulés), étape par étape : bascule de modèle, mémoire, langue, audio, API, dioula, baoulé, appel Live (réserves, coupures, outils, vision).</p><pre>${esc(d.tests_unitaires)}</pre>` : ""}
    `;
  brancherDictee();
}


/* ── Appel Live : modèles x comptes (réserves de quota) ── */
const dureeTexte = s => s >= 3600 ? `${Math.floor(s / 3600)} h ${String(Math.round(s % 3600 / 60)).padStart(2, "0")}` : `${Math.max(1, Math.round(s / 60))} min`;
async function remplirReserves() {
  let e;
  try { e = await (await api("/live/etat")).json(); }
  catch { $("#live_reserves").innerHTML = `<div class="vide-liste">État indisponible.</div>`; return null; }
  const total = e.reserves.reduce((n, r) => n + r.comptes.length, 0), dispo = e.reserves.reduce((n, r) => n + r.comptes.filter(c => c.disponible).length, 0);
  $("#live_resume").textContent = `${dispo} réserve${dispo > 1 ? "s" : ""} disponible${dispo > 1 ? "s" : ""} sur ${total} · ${e.reserves.length} modèles × ${e.comptes} comptes`;
  $("#live_reserves").innerHTML = e.reserves.map((r, i) => {
    const appels = r.comptes.reduce((n, c) => n + c.appels_jour, 0), minutes = r.comptes.reduce((n, c) => n + c.minutes_jour, 0);
    const pastilles = r.comptes.map(c => {
      const cls = ["ok", "repos", "ko"].includes(c.etat) ? c.etat : "repos";
      const titre = c.disponible ? `Compte ${c.compte} : disponible` : `Compte ${c.compte} : ${c.raison}${c.retour_dans_s ? `, retour dans ${dureeTexte(c.retour_dans_s)}` : ""}`;
      return `<i class="pc ${cls}" title="${esc(titre)}" aria-label="${esc(titre)}">${c.compte}</i>`;
    }).join("");
    return `<div class="groupe-titre">${i + 1}. ${esc(r.etiquette)}<span class="badge-vision">${r.vision ? "voit l'écran" : "sans vision"}</span></div>
      <div class="groupe"><div class="ligne"><span class="etiquette">${esc(r.modele)}<small>Aujourd'hui : ${appels} appel${appels > 1 ? "s" : ""} · ${String(Math.round(minutes * 10) / 10).replace(".", ",")} min${r.comptes.every(c => c.etat === "ko") ? " · écarté" : ""}</small></span>
      <span class="pastilles">${pastilles}</span></div></div>`;
  }).join("");
  const remise = new Date(Math.round((Date.now() + e.remise_a_zero_dans_s * 1000) / 60000) * 60000).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }).replace(":", " h ");
  $("#live_reserves_note").textContent = `Google ne donne pas le quota restant : une réserve passe en orange quand sa limite est atteinte. `
    + `Les limites du jour reviennent dans ${dureeTexte(e.remise_a_zero_dans_s)}, à ${remise} (minuit heure du Pacifique, remise à zéro chez Google).`;
  return e;
}
$("#btn_live_etat").onclick = () => { remplirReserves(); ouvrir("#feuille_live_etat"); };
$("#live_actualiser").onclick = remplirReserves;

/* ── Voix baoulé : serveur GPU Cerebrium, crédit restant (lu sur Cerebrium par le serveur, jamais de clé ici) ── */
const dollars = v => (v == null ? "–" : `${Number(v).toFixed(2).replace(".", ",")} $`);
async function remplirGpu(forcer) {
  $("#gpu_corps").innerHTML = `<div class="vide-liste">Lecture du crédit…</div>`;
  let c;
  try { c = await (await api(`/gpu/credit${forcer ? "?forcer=1" : ""}`)).json(); }
  catch { $("#gpu_corps").innerHTML = `<div class="vide-liste">Serveur du chatbot injoignable.</div>`; return null; }
  if (c.erreur) { $("#gpu_corps").innerHTML = `<div class="vide-liste">${esc(c.erreur)}</div>`; return c; }
  const etat = !c.configure ? "GPU non configuré : voix baoulé sur le serveur (lente)"
    : c.plafond_atteint ? "Plafond du jour atteint : voix baoulé sur le serveur jusqu'à demain"
    : c.eveille ? "Allumée (répond en ~2 s)" : "En veille (1re voix ~35 s, puis ~2 s)";
  const ligne = (titre, valeur, petit) => `<div class="ligne"><span class="etiquette">${esc(titre)}${petit ? `<small>${esc(petit)}</small>` : ""}</span><b>${esc(valeur)}</b></div>`;
  $("#gpu_resume").textContent = c.ok ? `Crédit restant : ${dollars(c.restant_usd)} · ${etat.split(" (")[0]}` : etat;
  $("#gpu_corps").innerHTML = `<div class="groupe-titre">Crédit</div><div class="groupe">${c.ok
      ? ligne("Crédit restant (estimé)", dollars(c.restant_usd), `sur ${dollars(c.offert_usd)} offerts`)
        + ligne("Dépensé ce mois-ci", dollars(c.depense_mois_usd), `${String(c.gpu_minutes_mois).replace(".", ",")} min de GPU · ${c.constructions_mois} construction${c.constructions_mois > 1 ? "s" : ""} du serveur`)
        + ligne("Ce qu'il reste permet", `≈ ${c.conversations_restantes} conversations`, `ou ≈ ${String(c.heures_restantes).replace(".", ",")} h de machine allumée (~1 $/h)`)
      : `<div class="ligne"><span class="etiquette">Crédit illisible<small>${esc(c.raison || "")}</small></span></div>`}</div>
    <div class="groupe-titre">Machine</div><div class="groupe">${ligne("État", etat)}
      ${c.minutes_max_jour != null ? ligne("Allumée aujourd'hui", `${c.minutes_jour} min sur ${c.minutes_max_jour} min`, "plafond de dépense par jour (~1 $ de l'heure)") : ""}
      ${c.dernieres_mesures?.length ? ligne("Dernières voix", c.dernieres_mesures.map(x => String(x).replace(".", ",") + " s").join(" · "), "temps total par réponse, réseau compris") : ""}
      ${c.derniere_erreur ? ligne("Dernier incident", c.derniere_erreur, "la voix est alors faite sur le serveur (plus lent)") : ""}</div>`;
  $("#gpu_note").textContent = c.ok ? `Lu sur Cerebrium à ${c.lu_a}. Cerebrium met quelques minutes à compter les dernières secondes utilisées.` : "";
  return c;
}
$("#btn_gpu").onclick = () => { remplirGpu(); ouvrir("#feuille_gpu"); };
$("#gpu_actualiser").onclick = () => remplirGpu(true);

/* ── Appel Live (étape 4) : on parle, l'assistant répond en direct ; il lit les données AOCEDA, regarde l'écran ou
      la caméra, et pilote cette page. Son : micro -> PCM 16 kHz -> serveur (WebSocket) -> Gemini Live -> voix 24 kHz ── */
const LIVE = { ws: null, ctxIn: null, ctxOut: null, flux: null, noeud: null, analyse: null, prochain: 0, sources: new Set(),
               micro: true, actif: false, compact: false, ecran: null, camera: null, t0: 0, niveauIn: 0, fini: false, etat: "",
               numero: 0, minuterie: null, pret: false, tampon: [], tamponOctets: 0, erreur: null, ouverture: {}, fermeture: false,
               cartes: [], lignesVues: 0 };
/* Micro gardé pendant la connexion à Gemini (et pendant une reconnexion), envoyé dès qu'il écoute. Audit du 09/10/2026 :
   seules les 6 DERNIÈRES secondes étaient gardées ; une connexion de 9,5 s perdait le DÉBUT de la phrase. Maintenant :
   avant que la personne parle, seulement 0,6 s (le silence ne sert à rien) ; dès qu'elle parle, tout, jusqu'à 20 s. */
const TAMPON_LIVE_MAX = 16000 * 2 * 20, TAMPON_AVANT_PAROLE = 16000 * 2 * 0.6, NIVEAU_PAROLE_LIVE = 0.015;
const FINS_LIVE = { silence: "Appel terminé : personne n'a parlé depuis 3 minutes.",
                    "durée maximale": "Appel terminé : durée maximale de 30 minutes atteinte." };
class Reechantillonneur {                       // taux du micro (44,1 / 48 kHz) -> 16 kHz, en flux continu
  constructor(taux) { this.r = taux / 16000; this.reste = new Float32Array(0); this.p = 0; }
  convertir(x) {
    const b = new Float32Array(this.reste.length + x.length); b.set(this.reste); b.set(x, this.reste.length);
    const out = []; let p = this.p;
    while (p + this.r <= b.length) {
      const a = Math.floor(p), z = Math.floor(p + this.r); let s = 0; for (let j = a; j < z; j++) s += b[j];
      const v = Math.max(-1, Math.min(1, s / Math.max(1, z - a))); out.push(v < 0 ? v * 0x8000 : v * 0x7FFF); p += this.r;
    }
    this.reste = b.slice(Math.floor(p)); this.p = p - Math.floor(p);
    return Int16Array.from(out);
  }
}
const ETATS_LIVE = { connexion: "Connexion…", ecoute: "Je vous écoute", parle: "AOCEDA vous répond", donnees: "Je consulte vos données…",
                     agit: "Je m'en occupe…",
                     regarde: "Je regarde…", reconnexion: "Reconnexion…" };
function etatLive(etat, texte) {
  LIVE.etat = etat;
  const el = $("#live_etat"), nouveau = texte || ETATS_LIVE[etat] || etat;
  if (el.textContent !== nouveau) { el.textContent = nouveau; MOUVEMENT.texte(el); }   // le nouvel état se pose en douceur
  $("#live").classList.toggle("attente", etat === "ecoute" || etat === "connexion");
  $("#live").classList.toggle("travail", ["connexion", "donnees", "regarde", "reconnexion", "agit"].includes(etat));
  $("#live").classList.toggle("en-ligne", etat !== "connexion" && etat !== "reconnexion");
}
function compactLive(oui) {
  const live = $("#live"), avant = !!LIVE.compact;
  LIVE.compact = oui;
  document.documentElement.classList.toggle("live-reduit", oui && !live.hidden);   // la page fait de la place à la barre
  if (avant !== oui && !live.hidden && LIVE.actif) MOUVEMENT.compacter(live, oui);   // plein écran <-> barre, en se resserrant
  else { MOUVEMENT.animCompact?.cancel(); MOUVEMENT.animPerso?.cancel(); live.classList.toggle("compact", oui); }
  CARTES.place();                                 // (animée : refait quand la barre est en place, voir compacter)
}
const FONDU_LIVE = { vous: { longueur: 0, morceaux: [], texte: "" }, agent: { longueur: 0, morceaux: [], texte: "" } };
function sousTitre(qui, texte) {                 // les mots arrivent en fondu (MOUVEMENT.fondu), seule la fin est montrée
  const plein = String(texte || ""), t = plein.slice(-260), etat = FONDU_LIVE[qui];
  if (!plein.startsWith(etat.texte)) Object.assign(etat, { longueur: 0, morceaux: [] });   // nouveau tour
  etat.texte = plein;
  MOUVEMENT.fondu(qui === "vous" ? $("#live_vous") : $("#live_agent"), null, etat, t, plein.length - t.length);
  if (qui !== "vous") $("#live_court").textContent = t;
}
const attendre = ms => new Promise(r => setTimeout(r, ms));
/* Langue de l'appel : affichée dans le haut quand elle est imposée (demandée, ou choisie dans les réglages) ; elle reste
   jusqu'à ce que la personne en demande une autre. Demandée en pleine conversation : le personnage fait « langue ». */
function langueLive(d) {
  const el = $("#live_langue"), avant = el.textContent;
  el.textContent = d.verrou ? `${d.nom}${d.verrou === "demande" ? " · demandée" : ""}` : "";
  el.title = d.verrou === "demande" ? "Langue demandée : toutes les réponses restent dans cette langue jusqu'à ce que vous en demandiez une autre"
    : d.verrou ? "Langue choisie dans les réglages" : "";
  if (el.textContent && el.textContent !== avant) { MOUVEMENT.texte(el); if (d.verrou === "demande") PERSO_LIVE.langue(); }
}
function jouerLive(ab) {
  if (!LIVE.ctxOut || !ab.byteLength) return;
  const pcm = new Int16Array(ab.byteLength % 2 ? ab.slice(0, ab.byteLength - 1) : ab), f = new Float32Array(pcm.length);
  for (let i = 0; i < pcm.length; i++) f[i] = pcm[i] / 32768;
  const buf = LIVE.ctxOut.createBuffer(1, f.length, 24000); buf.copyToChannel(f, 0);
  const src = LIVE.ctxOut.createBufferSource(); src.buffer = buf; src.connect(LIVE.analyse);
  const t = Math.max(LIVE.ctxOut.currentTime + 0.04, LIVE.prochain); src.start(t); LIVE.prochain = t + buf.duration;
  LIVE.sources.add(src); src.onended = () => LIVE.sources.delete(src);
}
function viderHautParleur() { for (const s of LIVE.sources) { try { s.stop(); } catch {} } LIVE.sources.clear(); LIVE.prochain = 0; }
function animerLive() {                          // niveau du micro (qui retombe doucement) + veille du personnage
  if (!LIVE.actif) return;
  PERSO_LIVE.veille();
  LIVE.niveauIn *= 0.85;
  requestAnimationFrame(animerLive);
}
function envoyerLive(d) { if (LIVE.ws?.readyState === 1) LIVE.ws.send(typeof d === "string" || d instanceof ArrayBuffer ? d : JSON.stringify(d)); }
/* Version de la page : un onglet resté ouvert pendant une mise à jour se recharge seul (hors appel, rien en cours) ; sinon
   le serveur refuse l'appel avec « rechargez la page » (vu le 05/10 : ancienne page + nouveau serveur = rien ne passe). */
let VERSION_PAGE = "";
async function pageAJour() {
  try {
    const v = (await (await api("/config", { cache: "no-store" })).json()).version_page;
    if (!v || !VERSION_PAGE || v === VERSION_PAGE) return true;
    if (!LIVE.actif && !occupe && !enreg) { MOUVEMENT.annonce("Nouvelle version : la page se recharge"); setTimeout(() => location.reload(), 900); }
    return false;
  } catch { return true; }
}
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") pageAJour(); });
async function demarrerLive() {
  if (LIVE.actif) return;
  if (!await pageAJour()) return;                  // nouvelle version : rechargement, l'appel se relance ensuite
  clearTimeout(LIVE.minuterie);
  arreterLecture(); if (enreg) arreterEnreg(false); fermer();
  const appel = ++LIVE.numero, enCours = () => LIVE.actif && LIVE.numero === appel;   // raccroché entre-temps ?
  Object.assign(LIVE, { actif: true, fini: false, micro: true, t0: Date.now(), prochain: 0, pret: false, tampon: [], tamponOctets: 0,
                        parleTampon: false, erreur: null, ouverture: {}, fermeture: false, vision: null, cartes: [], lignesVues: 0 });
  CARTES.vider(); $("#live_langue").textContent = "";
  for (const e of Object.values(FONDU_LIVE)) Object.assign(e, { longueur: 0, morceaux: [], texte: "" });
  for (const id of ["#live_ecran", "#live_camera"]) { $(id).classList.remove("indispo"); $(id).title = ""; }
  const depuis = TRANSITION_LIVE.depart();         // où est le personnage du chat, AVANT qu'il ne passe le relais
  $("#live").hidden = false; compactLive(false); etatLive("connexion"); sousTitre("vous", ""); sousTitre("agent", "");
  $("#live_compte").textContent = ""; $("#live_micro").classList.remove("coupe");
  PERSO.live(true, true); PERSO_LIVE.debut();      // le personnage de l'appel prend le relais (ça sonne)...
  TRANSITION_LIVE.ouvrir(depuis);                  // ... en s'envolant de la place de celui du chat
  $("#btn_live").disabled = true;
  let flux;
  try { flux = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } }); }
  catch {
    if (!enCours()) return;
    LIVE.erreur = "Micro refusé ou indisponible : autorisez le micro."; etatLive("erreur", LIVE.erreur); PERSO_LIVE.etat("erreur");
    LIVE.minuterie = setTimeout(() => { if (LIVE.numero === appel) finLive(null); }, 2500); return;
  }
  if (!enCours()) { flux.getTracks().forEach(t => t.stop()); return; }   // raccroché pendant la demande d'autorisation
  LIVE.flux = flux;
  LIVE.ctxIn = new AudioContext(); LIVE.ctxOut = new AudioContext({ sampleRate: 24000 });
  LIVE.analyse = LIVE.ctxOut.createAnalyser(); LIVE.analyse.fftSize = 512; LIVE.analyse.connect(LIVE.ctxOut.destination);
  const re = new Reechantillonneur(LIVE.ctxIn.sampleRate);
  const noeud = await brancherCapteur(LIVE.ctxIn, LIVE.ctxIn.createMediaStreamSource(flux), bloc => {
    if (LIVE.numero !== appel) return;
    let s = 0; for (let i = 0; i < bloc.length; i += 4) s += bloc[i] * bloc[i];
    const niveau = Math.sqrt(s / (bloc.length / 4)); LIVE.niveauIn = Math.max(LIVE.niveauIn, niveau);
    if (!LIVE.micro) return;
    const pcm = re.convertir(bloc).buffer;
    if (LIVE.pret && LIVE.ws?.readyState === 1) { LIVE.ws.send(pcm); return; }
    LIVE.tampon.push(pcm); LIVE.tamponOctets += pcm.byteLength;      // connexion en cours : on garde la phrase
    if (niveau > NIVEAU_PAROLE_LIVE) LIVE.parleTampon = true;
    const max = LIVE.parleTampon ? TAMPON_LIVE_MAX : TAMPON_AVANT_PAROLE;
    while (LIVE.tamponOctets > max && LIVE.tampon.length > 1) LIVE.tamponOctets -= LIVE.tampon.shift().byteLength;
  });
  if (!enCours()) { noeud.disconnect(); flux.getTracks().forEach(t => t.stop()); return; }
  LIVE.noeud = noeud;
  const ws = LIVE.ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}${API}/live?token=${encodeURIComponent(localStorage.getItem(JETON) || "")}`);
  ws.binaryType = "arraybuffer";
  ws.onopen = () => ws.send(JSON.stringify({ type: "debut", genre: $("#genre").value, langue: $("#langue").value, session, version: VERSION_PAGE }));
  ws.onmessage = ev => typeof ev.data === "string" ? recuLive(JSON.parse(ev.data)) : jouerLive(ev.data);
  ws.onclose = () => { if (!LIVE.fini && LIVE.numero === appel) finLive(null); };
  requestAnimationFrame(animerLive);
}
async function recuLive(d) {
  if (d.type === "etat") {
    etatLive(d.etat, d.etat === "reconnexion" && d.detail === "changement de réserve" ? "Changement de modèle ou de compte…" :
                     d.etat === "connexion" && d.detail === "voix" ? "Changement de voix…" :
                     d.etat === "regarde" ? (d.detail === "camera" ? "Je regarde la caméra…" : "Je regarde votre écran…") : null);
    if (d.etat === "connexion" || d.etat === "reconnexion") LIVE.pret = false;
    else if (!LIVE.pret && LIVE.ws?.readyState === 1) {          // Gemini est prêt : le micro gardé part, puis en direct
      LIVE.pret = true;
      for (const b of LIVE.tampon) LIVE.ws.send(b);
      LIVE.tampon = []; LIVE.tamponOctets = 0; LIVE.parleTampon = false;
    }
    if (d.modele) $("#live_compte").textContent = `${d.modele} · compte ${d.compte}/${d.comptes}`;
    if (typeof d.vision === "boolean") visionLive(d.vision);
    PERSO_LIVE.etat(d.etat, d.detail);
    if (d.etat === "parle" && CARTES.courante) CARTES.courante.parle = true;   // il dit ce que montre la carte
  } else if (d.type === "sous_titre") {
    sousTitre(d.qui, d.texte);
    if (d.fini) LIVE.lignesVues++;
    if (d.qui === "vous" && d.texte) CARTES.conversationSuit();   // on passe à autre chose : la carte s'en va
  }
  else if (d.type === "interrompu") { viderHautParleur(); PERSO_LIVE.interrompu(); }
  else if (d.type === "vider") viderHautParleur();         // réponse partie dans une autre langue : elle est redite
  else if (d.type === "outil") {                           // une donnée est lue : il la MONTRE (carte), puis réagit
    etatLive("donnees", `Je consulte : ${d.label}…`);
    const el = d.carte ? CARTES.montrer(d.carte) : null;
    PERSO_LIVE.outil(d.signal, el);
  }
  else if (d.type === "langue") langueLive(d);
  else if (d.type === "page") {
    let r;
    try {
      const action = PAGE_LIVE[d.nom];
      if (!action) r = { erreur: "action inconnue" };
      else {
        // on montre la page AVANT d'agir (barre réduite) : on voit le curseur de l'agent aller et toucher
        if (!SUR_PLACE.has(d.nom) && !LIVE.compact) { compactLive(true); await attendre(MOUVEMENT.reduit() ? 0 : 480); }
        r = await action(d.args || {});
      }
    } catch (e) { r = { erreur: String(e).slice(0, 120) }; }
    if (!r?.erreur) PERSO_LIVE.page(d.nom, d.args || {});    // le personnage montre ce qu'il vient de faire
    envoyerLive({ type: "resultat_page", id: d.id, resultat: r });
  } else if (d.type === "capture") {                        // l'image voyage DANS le résultat : jointe à la réponse d'outil
    const img = imageLive(d.source);
    envoyerLive({ type: "resultat_page", id: d.id, resultat: img ? { ok: true, source: d.source, image: img }
      : { erreur: d.source === "camera" ? "La caméra n'est pas activée : demandez d'appuyer sur « Caméra »." : "Le partage d'écran n'est pas activé : demandez d'appuyer sur « Écran »." } });
  } else if (d.type === "erreur") {
    LIVE.erreur = d.texte; etatLive("erreur", d.texte); PERSO_LIVE.etat("erreur");
    if (d.recharger) setTimeout(() => location.reload(), 2500);   // nouvelle version de la page : rechargement
  }
  else if (d.type === "fin") { PERSO_LIVE.auRevoir(); finLive(d); }
}
/* Actions que l'agent peut faire dans la page (outils « page » du serveur). Il les fait COMME UNE PERSONNE (AGENT) :
   son curseur va jusqu'au bouton et appuie ; « changer le thème » ouvre les Options puis touche la case... */
const SUR_PLACE = new Set(["lire_ecran", "afficher_appel", "ecran_entier", "carte"]);   // sans réduire l'appel d'abord
const testsAffiches = () => $("#vue_tests").classList.contains("active");
async function dansOptions(faire) {              // la case est dans les Options : il les ouvre (et les referme après)
  const ouvertes = feuilleOuverte?.id === "feuille_options";
  if (!ouvertes) { await AGENT.agir($("#btn_options"), b => b.click()); await attendre(MOUVEMENT.reduit() ? 0 : 520); }
  const r = await faire();
  if (!ouvertes && !r?.erreur) { await attendre(MOUVEMENT.reduit() ? 0 : 900); if (feuilleOuverte?.id === "feuille_options") fermer(); }
  return r;
}
const PAGE_LIVE = {
  lire_ecran: () => etatPage(),
  // agent qui planifie : la carte de toute l'application, puis le plan entier exécuté d'un coup (PLAN)
  carte: () => ({ carte: PLAN.carte(), etat: PLAN.etat() }),
  executer_plan: ({ etapes }) => PLAN.executer(etapes),
  // comme Playwright : un élément (ref donnée par lire_ecran, ou texte visible), et ce qu'on en fait
  cliquer: a => AGENT.agir(a, el => {
    if (el.disabled) return { erreur: `« ${AGENT.nom(el)} » est désactivé pour le moment` };
    el.click(); return { ok: true, clique: AGENT.nom(el) };
  }),
  ecrire: a => AGENT.agir(a.ref || a.nom ? a : zone, async el => {
    if (!/^(TEXTAREA|INPUT)$/.test(el.tagName)) return { erreur: "cet élément n'est pas un champ où écrire" };
    if (a.envoyer && el === zone && occupe) return { erreur: "le chat écrit est déjà en train de répondre : attends la fin" };
    const texte = String(a.texte ?? "").slice(0, 2000);
    el.focus({ preventScroll: true });
    await AGENT.taper(el, texte);
    if (!a.envoyer) return { ok: true, champ: AGENT.nom(el), ecrit: texte };
    if (el !== zone) { el.form?.requestSubmit(); return { ok: true, champ: AGENT.nom(el), ecrit: texte, envoye: true }; }
    await attendre(MOUVEMENT.reduit() ? 0 : 160);
    return AGENT.agir($("#envoyer"), b => { b.click(); return { ok: true, ecrit: texte, envoye: true, note: "le chat écrit répond par écrit dans la conversation" }; });
  }),
  choisir: a => AGENT.agir(a, el => {
    if (el.tagName !== "SELECT") return { erreur: "cet élément n'est pas une liste déroulante" };
    const v = normal(a.valeur), opts = [...el.options];
    const o = opts.find(x => normal(x.value) === v || normal(x.textContent) === v) || opts.find(x => normal(x.textContent).includes(v) || normal(x.value).includes(v));
    if (!o) return { erreur: `option « ${a.valeur} » introuvable`, options: opts.slice(0, 32).map(x => x.textContent) };
    el.value = o.value; el.dispatchEvent(new Event("change", { bubbles: true }));
    MOUVEMENT.texte(el); AGENT.bulle(el, o.textContent);
    return { ok: true, liste: AGENT.nom(el), choisi: o.textContent,
             ...(el.id === "genre" ? { note: "ta voix dans cet appel change juste après ta réponse (reconnexion d'une seconde)" } : {}) };
  }),
  montrer: a => AGENT.montrer(a),
  afficher_appel: ({ mode }) => {
    if (!["plein_ecran", "reduit"].includes(mode)) return { erreur: "mode inconnu" };
    const deja = LIVE.compact === (mode === "reduit");
    compactLive(mode === "reduit");
    return { ok: true, appel: mode === "reduit" ? "réduit en barre (la page est visible)" : "en plein écran", deja };
  },
  ecran_entier: ({ actif }) => AGENT.ecranEntier(actif !== false),
  // raccourcis : mêmes gestes qu'une personne (il touche le bouton, l'icône joue son animation)
  ouvrir_options: () => AGENT.agir($("#btn_options"), b => { b.click(); return { ok: true, fenetre: "Options" }; }),
  ouvrir_historique: () => AGENT.agir($("#btn_historique"), b => { b.click(); return { ok: true, fenetre: "Historique", conversations: HISTORIQUE.length }; }),
  ouvrir_choix_langue: () => AGENT.agir($("#plus"), b => { b.click(); return { ok: true, fenetre: "Langue des réponses" }; }),
  fermer_fenetre: () => {
    const f = feuilleOuverte, nom = f?.querySelector("h2")?.textContent || null;
    if (!f) return { ok: true, fermee: null };
    return AGENT.agir(f.querySelector("[data-fermer]"), b => { b.click(); return { ok: true, fermee: nom }; });
  },
  changer_langue_reponses: async ({ code }) => {
    const l = LANGUES.find(x => x.code === code); if (!l) return { erreur: "langue inconnue" };
    if (feuilleOuverte?.id !== "feuille_langue") { await AGENT.agir($("#plus"), b => b.click()); await attendre(MOUVEMENT.reduit() ? 0 : 520); }
    const ligne = $(`#liste_langues [data-code="${CSS.escape(code)}"]`);
    if (!ligne) { $("#langue").value = code; $("#langue").dispatchEvent(new Event("change")); fermer(); return { ok: true, langue: l.nom }; }
    return AGENT.agir(ligne, b => { b.click(); return { ok: true, langue: l.nom }; });   // la liste se referme d'elle-même
  },
  changer_theme: ({ theme }) => {
    if (!["auto", "clair", "sombre"].includes(theme)) return { erreur: "thème inconnu" };
    return dansOptions(() => AGENT.agir($(`#theme [data-theme-choix="${theme}"]`), b => { b.click(); return { ok: true, theme }; }));
  },
  ouvrir_tests_et_rapports: async () => {
    if (testsAffiches()) return { ok: true, page: "Tests et rapports", deja: true };
    if (feuilleOuverte?.id !== "feuille_options") { await AGENT.agir($("#btn_options"), b => b.click()); await attendre(MOUVEMENT.reduit() ? 0 : 520); }
    return AGENT.agir($("#feuille_options [data-vue='tests']"), b => { b.click(); return { ok: true, page: "Tests et rapports" }; });
  },
  revenir_au_chat: () => {
    if (!testsAffiches()) { if (feuilleOuverte) fermer(); return { ok: true, deja: true }; }
    return AGENT.agir($("#vue_tests .retour"), b => { b.click(); return { ok: true }; });
  },
  defiler: ({ sens }) => {
    // la fenêtre ouverte d'abord (vu le 05/10 : « défile » dans les Options faisait défiler la conversation derrière)
    const el = feuilleOuverte?.querySelector(".corps") || (testsAffiches() ? $(".defile") : fil);
    const avant = el.scrollTop, max = el.scrollHeight - el.clientHeight;
    if (max <= 2) return { ok: true, note: "rien à faire défiler : tout est déjà visible" };
    if ((sens === "haut" && avant <= 1) || (sens !== "haut" && avant >= max - 1)) return { ok: true, note: sens === "haut" ? "déjà tout en haut" : "déjà tout en bas" };
    return AGENT.agir(el, async () => {
      el.scrollBy({ top: (sens === "haut" ? -1 : 1) * el.clientHeight * 0.7, behavior: MOUVEMENT.reduit() ? "auto" : "smooth" });
      await attendre(MOUVEMENT.reduit() ? 0 : 450);
      const pos = el.scrollTop;
      return { ok: true, zone: feuilleOuverte ? feuilleOuverte.querySelector("h2")?.textContent : testsAffiches() ? "Tests et rapports" : "conversation",
               position: pos >= max - 2 ? "tout en bas" : pos <= 1 ? "tout en haut" : "au milieu" };
    }, false);
  },
  nouvelle_conversation: () => AGENT.agir($("#nouvelle"), async b => { b.click(); await attendre(450); return { ok: true }; }),
};
function etatPage() {
  const tests = testsAffiches(), l = LANGUES.find(x => x.code === $("#langue").value);
  return {
    vue: tests ? "Tests et rapports" : "conversation", accueil: $("#vue_chat").classList.contains("accueil"),
    fenetre_ouverte: feuilleOuverte?.querySelector("h2")?.textContent || null,
    appel: LIVE.compact ? "réduit en barre" : "plein écran (la page est derrière)", ecran_entier: !!document.fullscreenElement,
    reglages: { langue_reponses: l ? l.nom : $("#langue").value, voix: $("#genre").value, lecture_auto: $("#lecture_auto").selectedOptions[0]?.textContent,
                theme: themePage() },
    messages: [...colonne.querySelectorAll(".msg")].slice(-6).map(m => ({ de: m.classList.contains("moi") ? "utilisateur" : "assistant",
      texte: (m.querySelector(".bulle, .carte-donnees")?.innerText || "").replace(/\s+/g, " ").slice(0, 220) })),
    titres: tests ? [...document.querySelectorAll("#tests h2")].slice(0, 10).map(h => h.textContent) : [],
    partage_ecran: !!LIVE.ecran, camera: !!LIVE.camera,
    elements: AGENT.instantane(),               // ce qu'on peut toucher, avec une ref (cliquer / ecrire / choisir / montrer)
  };
}
function imageLive(source) {
  const v = (source === "camera" ? LIVE.camera : LIVE.ecran)?.video; if (!v || !v.videoWidth) return null;
  const k = Math.min(1, 1280 / Math.max(v.videoWidth, v.videoHeight)), c = document.createElement("canvas");
  c.width = Math.round(v.videoWidth * k); c.height = Math.round(v.videoHeight * k); c.getContext("2d").drawImage(v, 0, 0, c.width, c.height);
  return c.toDataURL("image/jpeg", 0.75).split(",")[1];
}
function visionLive(oui) {                                  // modèle de secours sans vision : boutons grisés, sources arrêtées
  LIVE.vision = oui;
  for (const [k, id] of [["ecran", "#live_ecran"], ["camera", "#live_camera"]]) {
    $(id).classList.toggle("indispo", !oui);
    $(id).title = oui ? "" : "Indisponible avec le modèle de secours utilisé en ce moment";
    if (!oui && LIVE[k]) { LIVE[k].flux.getTracks().forEach(t => t.stop()); LIVE[k] = null; }
  }
  apercuLive();
}
function apercuLive() {
  const actif = LIVE.camera || LIVE.ecran;
  $("#live_apercu").hidden = !actif;
  if (actif) { $("#live_video").srcObject = actif.flux; $("#live_apercu_nom").textContent = LIVE.camera ? "Caméra" : "Écran partagé"; }
  $("#live_camera").classList.toggle("actif", !!LIVE.camera); $("#live_ecran").classList.toggle("actif", !!LIVE.ecran);
}
async function sourceLive(nom) {                             // nom : "ecran" ou "camera" ; 2e appui = arrêt
  if (!LIVE.actif || LIVE.ouverture[nom]) return;           // ouverture déjà en cours : 2e appui ignoré
  if (LIVE.vision === false) { etatLive(LIVE.etat || "ecoute", "Vision indisponible avec le modèle de secours"); return; }
  if (LIVE[nom]) { LIVE[nom].flux.getTracks().forEach(t => t.stop()); LIVE[nom] = null; apercuLive(); return; }
  const appel = LIVE.numero, abandon = () => !LIVE.actif || LIVE.numero !== appel;
  let flux;
  LIVE.ouverture[nom] = true;
  try {
    flux = nom === "ecran" ? await navigator.mediaDevices.getDisplayMedia({ video: { frameRate: 5 }, audio: false, preferCurrentTab: true, selfBrowserSurface: "include" })
                           : await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment", width: { ideal: 1280 } } });
  } catch { if (!abandon()) etatLive(LIVE.etat || "ecoute", nom === "ecran" ? "Partage d'écran annulé" : "Caméra refusée ou indisponible"); return; }
  finally { LIVE.ouverture[nom] = false; }
  if (abandon()) { flux.getTracks().forEach(t => t.stop()); return; }       // appel fini pendant l'autorisation
  const video = document.createElement("video"); video.muted = true; video.playsInline = true; video.srcObject = flux; await video.play().catch(() => {});
  if (abandon()) { flux.getTracks().forEach(t => t.stop()); return; }
  LIVE[nom] = { flux, video };
  flux.getVideoTracks()[0].onended = () => { if (LIVE[nom]?.flux === flux) { LIVE[nom] = null; apercuLive(); } };
  apercuLive();
  if (nom === "ecran") compactLive(true);                     // l'image part quand l'agent regarde (jointe à son outil)
}
function finLive(d) {
  if (!LIVE.actif || (LIVE.fermeture && !d)) return;
  clearTimeout(LIVE.minuterie);
  const reste = LIVE.ctxOut ? LIVE.prochain - LIVE.ctxOut.currentTime : 0;
  if (d && reste > 0.15 && !LIVE.fermeture) {               // l'agent finit sa phrase (« au revoir ») avant qu'on raccroche
    LIVE.fermeture = true; LIVE.micro = false;
    LIVE.minuterie = setTimeout(() => { LIVE.fermeture = false; finLive(d); }, Math.min(8000, reste * 1000 + 250));
    return;
  }
  LIVE.fini = true; LIVE.actif = false; LIVE.fermeture = false;
  try { LIVE.ws?.readyState === 1 && !d && LIVE.ws.send(JSON.stringify({ type: "fin" })); } catch {}
  try { LIVE.ws?.close(); } catch {}
  LIVE.noeud?.disconnect(); LIVE.flux?.getTracks().forEach(t => t.stop());
  for (const k of ["ecran", "camera"]) { LIVE[k]?.flux.getTracks().forEach(t => t.stop()); LIVE[k] = null; }
  viderHautParleur(); LIVE.ctxIn?.close(); LIVE.ctxOut?.close();
  Object.assign(LIVE, { ws: null, ctxIn: null, ctxOut: null, flux: null, noeud: null, analyse: null });
  const compacte = $("#live").classList.contains("compact");
  apercuLive(); $("#btn_live").disabled = false;
  PERSO_LIVE.fin();                                // l'écran se ferme en dernier (TRANSITION_LIVE.fermer, plus bas)
  const lignes = d?.transcription || [];
  if (lignes.length) {                                       // ce qui s'est dit rejoint la conversation écrite
    montrerVue("chat");
    const s = Math.max(1, Math.round(d.duree_s || 0)), duree = s >= 60 ? `${Math.floor(s / 60)} min ${s % 60} s` : `${s} s`;
    ajouter("ia", `<div class="meta">${ICONES.son}<span>Appel Live · ${duree}</span></div>`);
    let question = null;
    // les cartes de données montrées pendant l'appel restent dans la conversation, à leur place
    const cartes = [...LIVE.cartes], carte = c => { const m = ajouter("ia carte-msg", ""); m.appendChild(CARTES.element(c, false)); };
    lignes.forEach((l, i) => {                      // juste avant la réponse de l'agent qui la commente
      while (l.qui !== "vous" && cartes.length && cartes[0].apres <= i) carte(cartes.shift().c);
      if (l.qui === "vous") { ajouter("moi", `<div class="bulle">${insecables(esc(l.texte))}</div>`); question = l.texte; }
      else { ajouter("ia", `<div class="bulle">${rendu(l.texte)}</div>`); if (question) { noterEchange(question, { role: "ia", texte: l.texte, fr: null, langue: null }); question = null; } }
    });
    cartes.forEach(x => carte(x.c));
  }
  const note = LIVE.erreur || FINS_LIVE[d?.raison];          // pourquoi l'appel s'est arrêté (limite, réseau, silence...)
  if (note) { montrerVue("chat"); ajouter("ia", `<div class="meta note">${ICONES.son}<span>${esc(note)}</span></div>`); }
  // la conversation est en place derrière : le personnage sait où revenir ; le chat le reprend à l'arrivée
  TRANSITION_LIVE.fermer(compacte);
}
$("#btn_live").onclick = demarrerLive;
const invite = () => { zone.placeholder = innerWidth < 420 ? "Votre question…" : "Posez votre question…"; };   // tient sur téléphone
invite(); addEventListener("resize", invite);
$("#live_raccrocher").onclick = () => {
  const appel = LIVE.numero;
  envoyerLive({ type: "fin" }); etatLive("connexion", "Fin de l'appel…"); PERSO_LIVE.auRevoir();
  clearTimeout(LIVE.minuterie);
  LIVE.minuterie = setTimeout(() => { if (LIVE.numero === appel) finLive(null); }, 4000);   // le serveur ne répond pas : on ferme
};
$("#live_micro").onclick = () => {
  LIVE.micro = !LIVE.micro; envoyerLive({ type: "micro", actif: LIVE.micro });
  $("#live_micro").classList.toggle("coupe", !LIVE.micro); $("#live_micro").setAttribute("aria-pressed", String(!LIVE.micro));
  $("#live_micro small").textContent = LIVE.micro ? "Micro" : "Muet";
};
$("#live_camera").onclick = () => sourceLive("camera");
$("#live_ecran").onclick = () => sourceLive("ecran");
$("#live_clavier").onclick = () => { const f = $("#live_ecrire"); f.hidden = !f.hidden; $("#live_clavier").classList.toggle("actif", !f.hidden); if (!f.hidden) $("#live_texte").focus(); };
$("#live_ecrire").onsubmit = e => { e.preventDefault(); const t = $("#live_texte").value.trim(); if (!t) return; envoyerLive({ type: "texte", texte: t }); sousTitre("vous", t); $("#live_texte").value = ""; };
$("#live_reduire").onclick = () => compactLive(true);
$("#live_agrandir").onclick = () => compactLive(false);
$("#live_perso").onclick = () => { if (LIVE.compact) compactLive(false); };
if (!navigator.mediaDevices?.getDisplayMedia) $("#live_ecran").hidden = true;      // téléphone : pas de partage d'écran

/* ── Personnage animé de l'assistant (moteur d'animation Coucou, MIT ; fichier /personnage/personnage.js) ──────────
   Il vit ce que fait le chatbot. Chaque scène (chat, appel Live) a un ÉTAT DE FOND (repos, il vous regarde écrire,
   réfléchit, écrit, parle, écoute...) et des RÉACTIONS courtes (compris, voilà, erreur, nouvelle conversation...)
   jouées par-dessus, qui rendent ensuite la main au fond. Le personnage fond lui-même chaque passage d'une animation à
   l'autre (aucune coupure). Fichier absent ou navigateur trop ancien : la page marche exactement comme avant. */
const AP = window.AocedaPersonnage || null;
const CALME = { nouvelle: "oui", economie: "oui", fete: "oui", alerte: "pas_compris", rire: "voila", colere: "non",
                accueil: "salut" };              // mouvements réduits
/* Temps minimum à l'écran d'un état de fond (s) : une donnée lue en 0,1 s, puis la parole tout de suite, ne doit pas
   faire disparaître l'animation avant qu'on la voie (vu le 03/10 en Live). */
const MIN_FOND = { lit_donnees: 2, prevision: 2.4, regarde_ecran: 2, reconnexion: 1.5, appel: 1.2, transcrit: 1, reflechit: 0.8,
                   ecrit: 0.8, patience: 1.5, hors_ligne: 1.5, erreur: 2 };
class Directeur {
  constructor(scene) {
    this.scene = scene; this.perso = scene.perso; this.fond = "repos"; this.fondO = {}; this.reaction = null; this.courante = null;
    this.minuteur = 0; this.attenteFond = 0; this.debutFond = 0; this.voixActive = false; this.niveauVoix = null;
  }
  duree(nom, o) { const a = AP.ACTIONS_AOCEDA[nom], d = typeof a.duree === "function" ? a.duree(o) : a.duree; return d ?? Infinity; }
  jouer(nom, o) {
    clearTimeout(this.attenteFond);
    this.courante = nom; this.debutFond = performance.now();
    if (nom === "repos") this.perso.repos(); else this.perso.jouer(nom, o);
    if (this.voixActive) this.appliquerVoix();      // la voix continue par-dessus n'importe quelle animation
    this.majCadence();
  }
  /** Au repos (rien ne bouge que la respiration) : la scène dessine moins souvent (audit du 09/10/2026 : ~25 % d'un
   *  cœur du processeur sans rien faire). Dès qu'il bouge, parle ou réagit : pleine fluidité. */
  majCadence() {
    const avant = this.scene.auRepos;
    this.scene.auRepos = !this.voixActive && !this.reaction && (this.courante === "repos" || this.courante === "silence");
    if (avant && !this.scene.auRepos) this.scene.accelerer?.();     // il bouge à nouveau : pleine fluidité tout de suite
  }
  /** État de fond. Une réaction en cours se termine d'abord ; l'état en cours reste visible son temps minimum (MIN_FOND) ;
   *  maintenant = true passe outre (une erreur...). */
  etat(nom, o = {}, maintenant = false) {
    this.fond = nom; this.fondO = o;
    if (this.reaction && !maintenant) return;
    if (this.courante === nom && !this.reaction) { clearTimeout(this.attenteFond); return; }   // déjà en cours
    const reste = (MIN_FOND[this.courante] || 0) * 1000 - (performance.now() - this.debutFond);
    if (!maintenant && !this.reaction && reste > 0) {
      clearTimeout(this.attenteFond);
      this.attenteFond = setTimeout(() => { if (!this.reaction && this.courante !== this.fond) this.jouer(this.fond, this.fondO); }, reste);
      return;
    }
    this.finReaction(); this.jouer(nom, o);
  }
  /** La voix est une couche à part : la bouche suit le son tout de suite, l'animation en cours va jusqu'au bout. */
  voix(niveau) { this.voixActive = true; this.niveauVoix = niveau || null; this.appliquerVoix(); this.majCadence(); }
  appliquerVoix() { if (this.niveauVoix) this.perso.parole = this.niveauVoix; else if (!this.perso.parole) this.perso.dire(Infinity); }
  taire() { this.voixActive = false; this.niveauVoix = null; this.perso.finParole(); this.majCadence(); }
  /** Réaction courte, puis retour au fond ; s = durée imposée (en secondes) pour une animation sans fin. */
  reagir(nom, o = {}, s = null) {
    if (AP.ScenePersonnage.mouvementReduit) nom = CALME[nom] || nom;
    if (!AP.ACTIONS_AOCEDA[nom]) return;
    this.finReaction();
    this.reaction = nom; this.jouer(nom, o);
    this.minuteur = setTimeout(() => { this.reaction = null; this.jouer(this.fond, this.fondO); }, Math.min(s ?? this.duree(nom, o), 6) * 1000);
  }
  finReaction() { clearTimeout(this.minuteur); this.reaction = null; this.majCadence(); }
}
/* Son des réponses lues : il passe par un analyseur, la bouche suit le vrai son (contexte audio ouvert au 1er geste) */
const SON = {
  ctx: null, an: null, buf: null,
  preparer() { try { this.ctx = this.ctx || new AudioContext(); if (this.ctx.state === "suspended") this.ctx.resume(); } catch {} },
  brancher(audio) {
    if (!audio || !this.ctx || this.ctx.state !== "running") return null;    // sinon : bouche simulée, son intact
    try {
      if (!this.an) { this.an = this.ctx.createAnalyser(); this.an.fftSize = 512; this.an.connect(this.ctx.destination); this.buf = new Float32Array(512); }
      this.ctx.createMediaElementSource(audio).connect(this.an);
      return () => niveauVoix(this.an, this.buf);
    } catch { return null; }
  },
};
function niveauVoix(an, buf) {                    // volume de la voix -> ouverture de la bouche (comme la galerie)
  an.getFloatTimeDomainData(buf);
  let s = 0; for (const v of buf) s += v * v;
  const r = Math.sqrt(s / buf.length); return r < 0.012 ? 0 : Math.min(1, r * 5.5);
}
const mots = m => new RegExp(`(^|[^\\p{L}])(${m})(?=$|[^\\p{L}])`, "iu");   // mots entiers, accents compris
const SALUT = mots("bonjour|bonsoir|salut|coucou|hello|hi|hey|au revoir|bye|bonne nuit|bonne soirée|bonne journée|à bientôt|à plus|i ni sɔgɔma|i ni tile|i ni wula");
const MERCI = mots("merci|thanks|thank you|i ni ce|a ni ce"), BRAVO = mots("super|génial|bravo|parfait|excellent|great|awesome");
const ASTUCE = mots("conseils?|astuces?|tips?");

/* Chat écrit et vocal */
const PERSO = {
  chat: null, clics: [], dernierGeste: Date.now(), finFrappe: 0,
  sombre: () => document.documentElement.dataset.theme === "sombre" || (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches),
  rect() { return this.chat?.scene.toile.getBoundingClientRect() || null; },
  /** Accueil : il se met au-dessus du titre (il y glisse s'il était à côté de la saisie). */
  accueil(conteneur, depuis) {
    if (!AP || !conteneur) return;
    conteneur.classList.toggle("cache", LIVE.actif);   // conversation recommencée par l'agent pendant un appel
    if (!this.chat) { this.chat = new Directeur(new AP.ScenePersonnage(conteneur)); this.entree(); this.chat.reagir("accueil"); }
    else this.chat.scene.placer(conteneur, true, depuis);
  },
  /** 1re ouverture : il sort de DERRIÈRE le titre. Tout ce qui passe sous le haut des lettres du titre est masqué
   *  (« horizon », environ 0,4 rayon de corps sous le bas de son cadre : l'animation « accueil » est réglée dessus).
   *  L'horizon s'ouvre à 2,1 s, quand il est posé. */
  entree() {
    const toile = this.chat.scene.toile, cadre = this.chat.scene.conteneur, titre = $(".vide .titre");
    if (AP.ScenePersonnage.mouvementReduit || !titre) return;
    // haut des majuscules du titre, mesuré depuis le cadre du personnage (le titre, lui, arrive en montant : MOUVEMENT)
    const t = toile.getBoundingClientRect(), c = cadre.getBoundingClientRect();
    const horizon = c.bottom + (parseFloat(getComputedStyle(cadre).marginBottom) || 0) + 0.3 * (parseFloat(getComputedStyle(titre).fontSize) || 30);
    if (!t.height || horizon >= t.bottom) return;
    toile.style.clipPath = `inset(-60% -60% ${(t.bottom - horizon).toFixed(1)}px -60%)`;
    this.finEntree = setTimeout(() => this.ouvrirHorizon(), 2100);
  },
  ouvrirHorizon(vite = false) {
    clearTimeout(this.finEntree);
    const toile = this.chat?.scene.toile, masque = toile?.style.clipPath;
    if (!masque) return;
    toile.style.clipPath = "";                    // en fondu (sauf s'il part ailleurs) : le halo sous lui apparaît doucement
    if (!vite) toile.animate([{ clipPath: masque }, { clipPath: "inset(-60% -60% -60% -60%)" }], { duration: 380, easing: "ease-out" });
  },
  /** L'accueil disparaît (1er message, conversation reprise) : il glisse à côté de la barre de saisie. */
  quitterAccueil(changement) {
    const d = this.chat, dansAccueil = d && d.scene.conteneur.classList.contains("perso-accueil"), depuis = dansAccueil ? this.rect() : null;
    this.ouvrirHorizon(true);
    // l'accueil disparaît : la barre de saisie descend en glissant (MOUVEMENT), le personnage glisse avec elle
    if ($("#vue_chat").classList.contains("accueil")) MOUVEMENT.morphZone(changement); else changement();
    if (dansAccueil) d.scene.placer($("#perso_dock"), true, depuis);
  },
  frappe(texte) {                                 // vous écrivez : il regarde la saisie et lit ce que vous tapez
    const d = this.chat; if (!d) return;
    this.geste(); clearTimeout(this.finFrappe);
    if (occupe || enreg || lecture || LIVE.actif) return;
    if (!texte.trim()) { if (d.fond === "frappe") d.etat("repos"); return; }
    d.etat("frappe", { regard: d.scene.viser($("#texte")).regard });
    this.finFrappe = setTimeout(() => { if (d.fond === "frappe") d.etat("repos"); }, 4000);   // il ne fixe pas la saisie indéfiniment
  },
  envoi(texte) {                                  // message envoyé : « compris ! » (bonjour, merci, bravo...), puis il réfléchit
    const d = this.chat; if (!d) return;
    clearTimeout(this.finFrappe); this.geste();
    d.etat("reflechit");
    d.reagir(MERCI.test(texte) ? "timide" : SALUT.test(texte) ? "salut" : BRAVO.test(texte) ? "rire" : "recu");
  },
  intention(certitude) { if (certitude === "basse") this.chat?.reagir("pas_compris", {}, 1.8); },   // dioula / baoulé mal compris
  morceau() { this.chat?.etat("ecrit"); },        // la réponse s'écrit
  fin(texte, luAVoixHaute) {                      // réponse terminée
    const d = this.chat; if (!d) return;
    if (d.fond === "parle" || d.fond === "patience") return;   // la 1re phrase se lit déjà (dioula)
    d.etat("repos");
    if (luAVoixHaute) return;                     // la voix arrive : c'est elle qui le fera parler
    d.reagir(/(\n\s*[-*•][^\n]*){2,}/.test(texte) || ASTUCE.test(texte) ? "conseil" : "voila", { muet: true });
  },
  erreur(e) {
    const d = this.chat; if (!d) return;
    d.etat(navigator.onLine === false ? "hors_ligne" : "repos", {}, true);
    d.reagir(e?.statut === 429 ? "limite" : e?.statut === 503 ? "patience" : "erreur", {}, e?.statut === 429 ? 3.5 : 2.4);
  },
  arret() { this.chat?.etat("repos", {}, true); this.chat?.reagir("interrompu", {}, 1.2); },   // « Stop » pendant la réponse
  parler(audio) {                                 // une réponse se lit : la bouche suit le vrai son (sinon simulée)
    const d = this.chat; if (!d) return;
    this.geste();
    d.voix(SON.brancher(audio));                  // la bouche suit tout de suite ; « voilà » ou autre finit son geste
    d.etat("parle", { duree: Infinity });
  },
  finParler() { const d = this.chat; if (d && (d.fond === "parle" || d.fond === "patience")) { d.taire(); d.etat("repos", {}, true); } },
  attente() { this.chat?.etat("patience"); },     // voix baoulé en préparation (plusieurs minutes)
  ecoute(niveau) { this.geste(); this.chat?.etat("ecoute", { niveau }, true); },   // message vocal en cours
  transcrit() { this.chat?.etat("transcrit", {}, true); },
  pasCompris() { this.chat?.etat("repos"); this.chat?.reagir("pas_compris", {}, 2); },
  annule() { this.chat?.etat("repos", {}, true); },
  nouvelle() { this.chat?.etat("repos", {}, true); this.chat?.reagir("nouvelle"); },
  langue() { this.chat?.reagir("langue"); },
  theme() { this.chat?.reagir("theme", { sombre: this.sombre() }); },
  live(actif, instant = false) {                  // pendant un appel, c'est le personnage de l'appel qui vit
    if (actif) this.ouvrirHorizon(true);
    for (const el of document.querySelectorAll("#perso_dock, .perso-accueil")) {
      if (instant) el.style.transition = "none";  // passage animé vers / depuis l'appel : relais à l'image près
      el.classList.toggle("cache", actif);
      if (instant) { void el.offsetWidth; el.style.transition = ""; }
    }
    this.chat?.scene.pause(actif);
    if (!actif && this.chat) { this.chat.etat("repos", {}, true); this.chat.reagir("voila"); }
  },
  geste() { this.dernierGeste = Date.now(); this.reveil(); },     // quelqu'un est là
  reveil() { const d = this.chat; if (d && d.fond === "silence") { d.etat("repos"); d.reagir("reveil"); } },
  veille() {                                      // personne depuis 2 minutes et rien en cours : il s'endort
    const d = this.chat; if (!d || LIVE.actif || occupe || enreg || lecture) return;
    if (d.fond === "repos" && !d.reaction && Date.now() - this.dernierGeste > 120000) d.etat("silence");
  },
  clic() {                                        // on le touche : il rit, puis rougit, puis s'agace
    const d = this.chat; if (!d) return;
    const n = Date.now(); this.clics = [...this.clics.filter(x => n - x < 1600), n];
    if (d.fond === "silence") return this.reveil();
    d.reagir(["rire", "timide", "colere"][Math.min(2, this.clics.length - 1)]);
  },
};
for (const ev of ["pointerdown", "keydown", "wheel", "touchstart"]) addEventListener(ev, () => PERSO.geste(), { passive: true });
addEventListener("pointermove", () => { if (Date.now() - PERSO.dernierGeste > 1000) PERSO.geste(); }, { passive: true });
document.addEventListener("click", ev => { if (ev.target.closest?.("#perso_dock, .perso-accueil")) PERSO.clic(); });
setInterval(() => PERSO.veille(), 5000);
addEventListener("offline", () => { if (PERSO.chat && !occupe) PERSO.chat.etat("hors_ligne", {}, true); });
addEventListener("online", () => { const d = PERSO.chat; if (d && d.fond === "hors_ligne") { d.etat("repos", {}, true); d.reagir("voila"); } });

/* Appel Live : le personnage remplace l'ancien rond */
const PERSO_LIVE = {
  d: null, connecte: false, humeur: null, buf: null, dernierSon: 0,
  init() { if (AP && !this.d) this.d = new Directeur(new AP.ScenePersonnage($("#live_perso"), { marge: 1.5 })); return this.d; },
  sortie() { return LIVE.analyse ? niveauVoix(LIVE.analyse, this.buf ||= new Float32Array(LIVE.analyse.fftSize)) : 0; },   // voix de l'agent
  ecoute() {                                      // il vous écoute : il réagit à VOTRE voix (micro), oreilles basses si micro coupé
    this.d?.taire();
    this.d?.etat("ecoute_live", { niveau: () => (LIVE.micro ? LIVE.niveauIn : 0), get microCoupe() { return !LIVE.micro; } });
  },
  debut() { const d = this.init(); if (!d) return; this.connecte = false; this.humeur = null; this.dernierSon = Date.now(); d.etat("appel", {}, true); },
  etat(etat, detail) {                            // états envoyés par le serveur (connexion, écoute, parle, données...)
    const d = this.d; if (!d) return;
    if (etat === "ecoute") { this.humeur = null; this.ecoute(); if (!this.connecte) { this.connecte = true; d.reagir("connecte"); } }
    else if (etat === "parle") {                  // la bouche suit la voix tout de suite ; les gestes de parole viennent
      this.dernierSon = Date.now();               // après l'animation en cours (« bravo », loupe...), sans la couper
      d.voix(() => this.sortie());
      d.etat("parle_live", { duree: Infinity, humeur: this.humeur });
    }
    else if (etat === "donnees") { d.etat(detail === "prevision_fin_mois" ? "prevision" : "lit_donnees"); if (detail === "credit_et_recharges") d.reagir("facture"); }
    else if (etat === "regarde") d.etat("regarde_ecran");
    else if (etat === "agit") d.etat("reflechit");     // il prépare le plan (le curseur fera le reste)
    else if (etat === "reconnexion" || (etat === "connexion" && this.connecte)) d.etat("reconnexion");
    else if (etat === "erreur") d.etat("erreur", {}, true);
  },
  /** Une donnée est lue : il MONTRE la carte du doigt (« voilà »), puis dit ce qu'elle annonce : bravo (baisse) ou
   *  attention (hausse, alerte). */
  outil(signal, carte = null) {
    const d = this.d; if (!d) return;
    clearTimeout(this.suiteCarte);
    if (signal) this.humeur = signal === "baisse" ? "contente" : "inquiete";   // il garde cette humeur en le disant
    const emotion = () => { if (signal === "baisse") d.reagir("economie"); else if (signal) d.reagir("alerte", {}, 1.8); };
    if (!carte) return emotion();
    setTimeout(() => { if (carte.isConnected) d.reagir("montre", { ...d.scene.viser(carte), tenue: 2.2, muet: true }); }, 380);
    if (signal) this.suiteCarte = setTimeout(emotion, 2500);
  },
  interrompu() { const d = this.d; if (!d) return; this.ecoute(); d.reagir("interrompu", {}, 1.1); },
  /** Son curseur va toucher un élément : il le regarde et tend la main vers lui. */
  agit(el) { const d = this.d; if (d && LIVE.actif && el) d.reagir("ouvre_fenetre", d.scene.viser(el)); },
  langue() { this.d?.reagir("langue"); },
  page(nom, args = {}) {                          // l'agent a agi sur la page : le personnage le confirme
    const d = this.d; if (!d) return;
    if (nom === "changer_theme") d.reagir("theme", { sombre: PERSO.sombre() });
    else if (nom === "changer_langue_reponses") d.reagir("langue");
    else if (nom === "nouvelle_conversation") d.reagir("nouvelle");
    else if (nom === "lire_ecran") d.reagir("regarde_ecran", {}, 1.4);
    else if (nom === "afficher_appel") d.reagir(args.mode === "plein_ecran" ? "connecte" : "oui");
    else if (nom === "executer_plan") d.reagir("voila");
    else if (nom === "fermer_fenetre" || nom === "revenir_au_chat") d.reagir("oui");
  },
  auRevoir() { this.d?.reagir("salut"); },
  fin() { this.d?.etat("repos", {}, true); this.connecte = false; },
  veille() {                                      // personne ne parle depuis 45 s pendant l'appel : il s'assoupit
    const d = this.d; if (!d || !LIVE.actif) return;
    const voix = (LIVE.micro && LIVE.niveauIn > 0.03) || LIVE.etat === "parle";
    if (voix) this.dernierSon = Date.now();
    if (d.fond === "silence" && voix) { this.ecoute(); d.reagir("reveil"); }
    else if (d.fond === "ecoute_live" && !d.reaction && Date.now() - this.dernierSon > 45000) d.etat("silence");
  },
};

/* ── Passage animé chat <-> appel Live (05/10/2026, demande du client : « comme un motion design, propre, épuré ») ──
   Ouverture : le personnage du chat DEVIENT celui de l'appel. Il quitte sa place (au-dessus du titre ou à côté de la
   saisie) et rejoint le centre en grandissant ; l'écran de l'appel s'ouvre en cercle AUTOUR de lui (le cercle suit son
   vol) ; puis le haut, le texte et les boutons arrivent l'un après l'autre. Fermeture : l'inverse ; le chat le reprend
   à l'arrivée, à l'image près. Mouvements réduits (accessibilité), barre réduite ou personnage absent : simple fondu. */
const TRANSITION_LIVE = {
  OUV: 720, FERM: 560, COURBE_OUV: "cubic-bezier(.22, 1, .36, 1)", COURBE_FERM: "cubic-bezier(.65, 0, .35, 1)",
  reduit: () => matchMedia("(prefers-reduced-motion: reduce)").matches,
  /** Centre du corps du personnage du chat (x, y ; t = taille de son cadre), sinon du bouton Live ; null si rien d'affiché. */
  depart() {
    const s = PERSO.chat?.scene, r = s?.conteneur.isConnected ? s.conteneur.getBoundingClientRect() : null;
    if (r?.width) return { ...s.centre(), perso: true };
    const b = $("#btn_live").getBoundingClientRect();
    return b.width ? { x: b.left + b.width / 2, y: b.top + b.height / 2, t: b.width, perso: false } : null;
  },
  arrivee() {                                     // centre du corps du personnage de l'appel, à sa place
    const s = PERSO_LIVE.d?.scene; if (s) return s.centre();
    const r = $("#live_perso").getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2, t: r.width };
  },
  /** Vol du personnage de l'appel entre `loin` (place dans le chat) et sa place ; retour = de sa place vers `loin`.
   *  Corrige l'écart entre le centre du corps et le centre de la toile (l'agrandissement se fait autour de la toile). */
  voler(loin, ici, retour, duree, courbe) {
    const s = PERSO_LIVE.d?.scene; if (!s) return null;
    const r = s.toile.getBoundingClientRect(), k = loin.t / ici.t;
    const ox = ici.x - (r.left + r.width / 2), oy = ici.y - (r.top + r.height / 2);
    const de = `translate(-50%, -50%) translate(${loin.x - ici.x + (1 - k) * ox}px, ${loin.y - ici.y + (1 - k) * oy}px) scale(${k})`;
    const pose = "translate(-50%, -50%)";
    return s.toile.animate(retour ? [{ transform: pose }, { transform: de }] : [{ transform: de }, { transform: pose }],
                           { duration: duree, easing: courbe, fill: retour ? "forwards" : "none" });
  },
  /** L'écran de l'appel, découpé en cercle : petit autour du personnage dans le chat, grand (tout l'écran) à sa place. */
  cercle(loin, ici, retour, duree, courbe) {
    const r0 = Math.max(30, loin.t * 0.62), R = Math.hypot(Math.max(ici.x, innerWidth - ici.x), Math.max(ici.y, innerHeight - ici.y)) + 2;
    const petit = `circle(${r0}px at ${loin.x}px ${loin.y}px)`, grand = `circle(${R}px at ${ici.x}px ${ici.y}px)`;
    return $("#live").animate(retour ? [{ clipPath: grand }, { clipPath: petit }] : [{ clipPath: petit }, { clipPath: grand }],
                              { duration: duree, easing: courbe, fill: retour ? "forwards" : "none" });
  },
  elements() {
    const l = $("#live");
    return [l.querySelector(".live-haut"), l.querySelector(".live-textes"), l.querySelector(".live-sous-titres"),
            ...l.querySelectorAll(".live-ecrire:not([hidden]), .live-bouton:not([hidden])")].filter(Boolean);
  },
  annuler() { for (const a of $("#live").getAnimations({ subtree: true })) a.cancel(); },
  ouvrir(loin) {
    const live = $("#live");
    this.annuler();
    if (this.reduit() || !loin) { live.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 220, easing: "ease-out" }); return; }
    const s = PERSO_LIVE.d?.scene;
    if (s) { s.visible = true; s.perso.update(0); s.dessiner(); s.relancer(); }   // sa 1re image tout de suite (relais sans trou)
    const ici = this.arrivee();
    this.cercle(loin, ici, false, this.OUV, this.COURBE_OUV);
    if (loin.perso) this.voler(loin, ici, false, this.OUV, this.COURBE_OUV);
    else s?.toile.animate([{ opacity: 0, transform: "translate(-50%, -50%) scale(.55)" }, { opacity: 1, transform: "translate(-50%, -50%)" }],
                          { duration: 560, delay: 140, easing: this.COURBE_OUV, fill: "backwards" });
    this.elements().forEach((el, i) => {          // l'un après l'autre : le haut descend, le reste monte
      const haut = el.classList.contains("live-haut");
      el.animate([{ opacity: 0, transform: `translateY(${haut ? -10 : 16}px)` }, { opacity: 1, transform: "none" }],
                 { duration: 480, delay: (haut ? 300 : 340) + i * 45, easing: this.COURBE_OUV, fill: "backwards" });
    });
  },
  /** Appelée à la toute fin de finLive (la conversation est déjà en place derrière : il sait où revenir). */
  fermer(compacte) {
    const live = $("#live");
    AGENT.cacher(); $("#agent_halo").classList.remove("vise"); $("#propose_plein").hidden = true;   // l'agent ne touche plus rien
    const finir = () => {
      live.hidden = true; compactLive(false); $("#live_ecrire").hidden = true; this.annuler(); CARTES.vider();
      PERSO.chat?.scene.toile.getAnimations().forEach(a => a.finish());   // il glissait vers sa place : il y est
      PERSO.live(false, true);                    // le chat le reprend à l'image près
    };
    if (live.hidden) return finir();
    const loin = this.depart(), ici = this.arrivee();
    if (compacte || this.reduit() || !loin) {
      live.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 200, easing: "ease-in", fill: "forwards" }).onfinish = finir;
      return;
    }
    this.elements().reverse().forEach((el, i) =>
      el.animate([{ opacity: 1 }, { opacity: 0, transform: "translateY(10px)" }], { duration: 170, delay: i * 16, easing: "ease-in", fill: "forwards" }));
    const fin = this.cercle(loin, ici, true, this.FERM, this.COURBE_FERM);
    if (loin.perso) this.voler(loin, ici, true, this.FERM, this.COURBE_FERM);
    else PERSO_LIVE.d?.scene.toile.animate([{ opacity: 1 }, { opacity: 0, transform: "translate(-50%, -50%) scale(.55)" }],
                                           { duration: this.FERM * 0.7, easing: "ease-in", fill: "forwards" });
    fin.onfinish = finir;
  },
};

/* ── L'agent agit sur la page comme une personne (05/10/2026, demande du client : « comme Playwright MCP, toutes les
   actions complètes dans l'application ») ──────────────────────────────────────────────────────────────────────────
   lire_ecran donne les éléments visibles avec une ref (data-agent-ref), comme un « snapshot » ; cliquer / ecrire /
   choisir / montrer agissent dessus. Et on le VOIT faire : son curseur doré part du personnage de l'appel, glisse en
   arc jusqu'à l'élément, un halo l'entoure, il appuie (l'onde part du point touché), il tape lettre à lettre. Ce qui
   est définitif ou appartient à la personne est refusé, avec la raison (l'agent la dit). */
const normal = s => String(s ?? "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, " ").trim();
const AGENT = {
  n: 0, pos: null, minuterie: 0,
  ACTIFS: "button, select, textarea, input:not([type=hidden]), a[href], summary, [role=button]",
  REFUS: [["#live, #live *", "les boutons de l'appel (micro, caméra, écran, raccrocher) appartiennent à la personne ; pour l'affichage de l'appel, utilise afficher_appel"],
          ["#effacer_historique", "effacer l'historique est définitif : la personne doit le faire elle-même (bouton Historique en haut, puis « Effacer l'historique » en bas de la fenêtre)"],
          ["#micro", "le micro du chat écrit ne s'utilise pas pendant l'appel"],
          ["#btn_live", "l'appel est déjà en cours"],
          ["#dictee_btn", "la dictée du navigateur se lance par la personne elle-même"],
          ["a[target=_blank]", "ce lien ouvre un nouvel onglet : la personne doit le toucher elle-même"],
          ["#propose_plein, #agent_curseur *", "élément interne"]],
  refus(el) { for (const [s, r] of this.REFUS) if (el.matches(s)) return r; return null; },
  visible(el) {
    if (!el?.isConnected || el.closest("[hidden]")) return false;
    const r = el.getBoundingClientRect(); if (!r.width || !r.height) return false;
    const s = getComputedStyle(el); return s.visibility !== "hidden" && s.display !== "none" && +s.opacity !== 0;
  },
  /** Ce qu'une personne verrait : la fenêtre ouverte seule (le reste est sous le voile), sinon la page ; jamais les boutons
   *  de l'appel. Ce qui est réservé à la personne est LISTÉ avec sa raison (vu le 05/10 : sans cela, l'agent cherchait
   *  « Effacer l'historique » en boucle au lieu de dire tout de suite que c'est à la personne de le faire). */
  candidats() {
    return [...(feuilleOuverte || document).querySelectorAll(this.ACTIFS)]
      .filter(el => this.visible(el) && !el.closest("#live") && this.refus(el) !== "élément interne");
  },
  nom(el) {
    const t = s => String(s || "").replace(/\s+/g, " ").trim();
    if (el === fil || el.classList?.contains("defile")) return "la conversation";
    if (el.tagName === "SELECT") return t(el.closest(".ligne")?.querySelector(".etiquette")?.textContent || el.getAttribute("aria-label") || el.id);
    return t(el.getAttribute("aria-label") || el.innerText || el.title || el.placeholder || el.id).slice(0, 80);
  },
  role(el) {
    return el.tagName === "SELECT" ? "liste" : /^(TEXTAREA|INPUT)$/.test(el.tagName) ? "champ" : el.tagName === "A" ? "lien"
      : el.classList.contains("puce") ? "suggestion" : "bouton";
  },
  decrire(el) {
    el.dataset.agentRef ||= `e${++this.n}`;
    const d = { ref: el.dataset.agentRef, role: this.role(el), nom: this.nom(el) };
    if (el.tagName === "SELECT") { d.valeur = el.selectedOptions[0]?.textContent || el.value; d.options = [...el.options].slice(0, 32).map(o => o.textContent); }
    else if (d.role === "champ") { d.valeur = el.value.slice(0, 120); if (el.placeholder) d.indice = el.placeholder; }
    if (el.disabled) d.etat = "désactivé";
    else if (el.classList.contains("choisi") || el.getAttribute("aria-pressed") === "true") d.etat = "choisi";
    const r = el.getBoundingClientRect(); if (r.bottom < 0 || r.top > innerHeight) d.hors_ecran = true;
    if (el.matches("#nouvelle, #nouvelle_h")) d.attention = "efface la conversation affichée : demande confirmation avant";
    const refus = this.refus(el); if (refus) d.reserve_a_la_personne = refus;
    return d;
  },
  instantane() { return this.candidats().slice(0, 70).map(el => this.decrire(el)); },
  /** L'élément visé : sa ref, sinon le texte visible le plus proche. montrer = true : même ce qui est réservé à la personne
   *  (on peut lui montrer où est le micro ; pas appuyer dessus). */
  trouver(c, montrer = false) {
    if (c instanceof Element) return this.visible(c) ? { el: c } : { erreur: "cet élément n'est pas affiché en ce moment" };
    const { ref, nom } = c || {}, ok = el => { const r = this.refus(el); return r && !(montrer && r !== "élément interne") ? { refus: r } : { el }; };
    if (ref) {
      const el = document.querySelector(`[data-agent-ref="${CSS.escape(String(ref))}"]`);
      if (el && this.visible(el)) return ok(el);
      if (!nom) return { erreur: `élément ${ref} introuvable (la page a changé) : appelle lire_ecran pour avoir les refs à jour` };
    }
    const n = normal(nom); if (!n) return { erreur: "donne la ref de l'élément (lire_ecran) ou son texte visible" };
    let meilleur = null, score = 0;
    for (const el of document.querySelectorAll(this.ACTIFS)) {
      if (!this.visible(el)) continue;
      const t = normal(`${this.nom(el)} ${el.placeholder || ""} ${el.title || ""}`);
      let s = t === n ? 3 : t.startsWith(n) ? 2 : t.includes(n) ? 1 : 0;
      if (feuilleOuverte && !feuilleOuverte.contains(el)) s *= 0.5;              // la fenêtre ouverte d'abord
      if (s > score) { score = s; meilleur = el; }
    }
    return meilleur ? ok(meilleur) : { erreur: `aucun élément « ${nom} » à l'écran : appelle lire_ecran` };
  },
  /** D'où part le curseur : sa dernière place, sinon la main du personnage de l'appel, sinon le bas de l'écran. */
  depart() {
    if (this.pos) return this.pos;
    const s = PERSO_LIVE.d?.scene;
    if (LIVE.actif && s?.taille) { const c = s.centre(); return { x: c.x + c.t * 0.3, y: c.y - c.t * 0.05 }; }
    return { x: innerWidth / 2, y: innerHeight - 70 };
  },
  /** Le curseur glisse jusqu'à l'élément (trajet en arc, échantillonné) ; le halo l'entoure ; le personnage regarde. */
  async aller(el) {
    clearTimeout(this.minuterie);
    const reduit = MOUVEMENT.reduit(), c = $("#agent_curseur"), h = $("#agent_halo");
    let r = el.getBoundingClientRect();
    if (r.top < 0 || r.bottom > innerHeight) {               // hors de l'écran : il fait défiler jusqu'à lui
      el.scrollIntoView({ block: "center", behavior: reduit ? "auto" : "smooth" }); await attendre(reduit ? 0 : this.rapide ? 260 : 420); r = el.getBoundingClientRect();
    }
    const cible = { x: r.left + (r.width > 160 ? Math.min(r.width * 0.3, 90) : r.width / 2), y: r.top + Math.min(r.height / 2, 60) };
    const de = this.depart(), d = Math.hypot(cible.x - de.x, cible.y - de.y), place = p => `${(p.x - 6).toFixed(1)}px ${(p.y - 4).toFixed(1)}px`;
    c.getAnimations().forEach(a => a.cancel());
    c.style.opacity = 1;
    if (!reduit && d > 2) {
      const k = Math.min(80, d * 0.2), nx = -(cible.y - de.y) / d, ny = (cible.x - de.x) / d;      // arc : point de contrôle décalé
      const ctrl = { x: (de.x + cible.x) / 2 + nx * k, y: (de.y + cible.y) / 2 + ny * k };
      const pts = Array.from({ length: 13 }, (_, i) => { const t = i / 12, u = 1 - t;
        return { translate: place({ x: u * u * de.x + 2 * u * t * ctrl.x + t * t * cible.x, y: u * u * de.y + 2 * u * t * ctrl.y + t * t * cible.y }) }; });
      if (!this.pos) { pts[0].opacity = 0; pts[0].scale = .5; pts[2].opacity = 1; pts[2].scale = 1; }   // il apparaît en partant
      const duree = this.rapide ? Math.min(340, Math.max(170, 140 + d * 0.14)) : Math.min(900, Math.max(460, 360 + d * 0.34));   // plan : mode rapide
      await c.animate(pts, { duration: Math.round(duree), easing: MOUVEMENT.E.deux }).finished.catch(() => {});
    }
    c.style.translate = place(cible);
    this.pos = cible;
    const rayon = (parseFloat(getComputedStyle(el).borderTopLeftRadius) || 8) + 5;
    Object.assign(h.style, { width: `${r.width + 10}px`, height: `${r.height + 10}px`, translate: `${r.left - 5}px ${r.top - 5}px`, borderRadius: `${Math.min(rayon, (r.height + 10) / 2)}px` });
    h.getAnimations().forEach(a => a.cancel());
    h.classList.add("vise");
    h.animate([{ opacity: 0, scale: 1.12 }, { opacity: 1, scale: 1 }], { duration: reduit ? 1 : this.rapide ? 150 : 320, easing: MOUVEMENT.E.sortie, fill: "forwards" });
    PERSO_LIVE.agit(el);
    return cible;
  },
  /** Il appuie : le curseur s'enfonce et se relâche en ressort, l'onde part du point touché. */
  async appuyer(el, p) {
    if (MOUVEMENT.reduit()) return;
    $("#agent_curseur").animate([{ scale: 1 }, { scale: .76, offset: .3 }, { scale: 1 }], { duration: this.rapide ? 240 : 440, easing: MOUVEMENT.E.sortie });
    MOUVEMENT.appui({ button: 0, target: el, clientX: p.x, clientY: p.y });
    await attendre(this.rapide ? 50 : 140);
  },
  finir(tenue = 0) {                               // le halo s'efface ; le curseur reste un instant (une action peut suivre)
    clearTimeout(this.minuterie);
    this.minuterie = setTimeout(() => {
      const h = $("#agent_halo"); h.classList.remove("vise");
      h.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 260, easing: "ease-in", fill: "forwards" });
      this.minuterie = setTimeout(() => this.cacher(), 1100);
    }, tenue);
  },
  cacher() {
    const c = $("#agent_curseur"); c.classList.remove("tape"); this.pos = null;
    if (+getComputedStyle(c).opacity === 0) return;
    c.animate([{ opacity: 1, scale: 1 }, { opacity: 0, scale: .5 }], { duration: 300, easing: MOUVEMENT.E.entree }).finished
      .then(() => { if (!this.pos) c.style.opacity = 0; }).catch(() => {});
  },
  /** Une action complète, comme une personne : trouver, fermer la fenêtre qui gêne, aller, appuyer, faire. */
  async agir(cible, faire, appui = true) {
    const t = this.trouver(cible);
    if (t.refus) return { erreur: `Action réservée à la personne : ${t.refus}.` };
    if (t.erreur) return cible instanceof Element ? await faire(cible) : { erreur: t.erreur };   // raccourci sans élément visible
    const el = t.el;
    if (feuilleOuverte && !feuilleOuverte.contains(el) && el !== fil) { fermer(); await attendre(MOUVEMENT.reduit() ? 0 : 280); }
    const p = await this.aller(el);
    if (appui) await this.appuyer(el, p);
    try { return await faire(el); } finally { this.finir(appui ? 0 : 900); }
  },
  async montrer(cible) {                           // « où est... ? » : il s'y pose et l'entoure, sans toucher
    const t = this.trouver(cible, true);
    if (t.erreur) return { erreur: t.erreur };
    if (feuilleOuverte && !feuilleOuverte.contains(t.el) && !t.el.closest("#live")) { fermer(); await attendre(MOUVEMENT.reduit() ? 0 : 280); }
    if (t.el.closest("#live") && !LIVE.compact) compactLive(true);
    await this.aller(t.el);
    this.finir(2600);
    return { ok: true, montre: this.nom(t.el), role: this.role(t.el) };
  },
  /** Il tape le texte lettre à lettre (1,3 s au plus) ; chaque lettre passe par l'événement « input » comme au clavier. */
  async taper(el, texte) {
    const c = $("#agent_curseur"), ecrire = v => { el.value = v; el.dispatchEvent(new Event("input", { bubbles: true })); };
    if (MOUVEMENT.reduit() || !texte) { ecrire(texte); return; }
    ecrire(""); c.classList.add("tape");
    const total = this.rapide ? 500 : 1300, pas = Math.max(1, Math.ceil(texte.length / 45)), delai = Math.min(34, total / Math.ceil(texte.length / pas));
    for (let i = pas; i < texte.length + pas; i += pas) { ecrire(texte.slice(0, i)); await attendre(delai); }
    c.classList.remove("tape");
  },
  /** Petite étiquette près d'une liste : la valeur choisie (« English (Anglais) ») apparaît puis s'efface. */
  bulle(el, texte) {
    const r = el.getBoundingClientRect(), b = document.createElement("div");
    b.className = "agent-bulle"; b.textContent = `✓ ${texte}`; document.body.appendChild(b);
    const x = Math.min(innerWidth - b.offsetWidth - 12, Math.max(12, r.right - b.offsetWidth)), y = r.top - b.offsetHeight - 10;
    Object.assign(b.style, { left: `${x}px`, top: `${Math.max(8, y)}px` });
    b.animate([{ opacity: 0, transform: "translateY(6px) scale(.9)" }, { opacity: 1, transform: "none", offset: .14 },
               { opacity: 1, transform: "none", offset: .82 }, { opacity: 0, transform: "translateY(-4px)" }],
              { duration: MOUVEMENT.reduit() ? 1600 : 1900, easing: "ease-out" }).onfinish = () => b.remove();
  },
  /** Plein écran de l'appareil : le navigateur l'exige souvent d'un geste de la personne -> un bouton doré le propose. */
  async ecranEntier(oui) {
    if (!oui) { if (document.fullscreenElement) await document.exitFullscreen().catch(() => {}); $("#propose_plein").hidden = true; return { ok: true, ecran_entier: false }; }
    if (document.fullscreenElement) return { ok: true, ecran_entier: true, deja: true };
    if (!document.documentElement.requestFullscreen) return { erreur: "ce navigateur ne permet pas le plein écran (par exemple sur iPhone)" };
    try { await document.documentElement.requestFullscreen({ navigationUI: "hide" }); return { ok: true, ecran_entier: true }; }
    catch {
      const b = $("#propose_plein"); b.hidden = false;
      if (!MOUVEMENT.reduit()) b.animate([{ opacity: 0, transform: "translateY(-12px) scale(.9)" }, { opacity: 1, transform: "none" }], { duration: 520, easing: MOUVEMENT.E.ressort });
      clearTimeout(this.finPropose); this.finPropose = setTimeout(() => { b.hidden = true; }, 15000);
      return { ok: false, a_faire: "le navigateur exige un geste : demande à la personne de toucher le bouton doré « Plein écran » qui vient d'apparaître en haut" };
    }
  },
};
$("#propose_plein").onclick = () => { $("#propose_plein").hidden = true; document.documentElement.requestFullscreen?.({ navigationUI: "hide" }).catch(() => {}); };

/* ── L'agent qui PLANIFIE (05/10/2026 ; demande du client : clic par clic, c'était « extrêmement lent ») ─────────────
   1. CARTE : la page décrit toute l'application, écrans fermés compris (leur contenu est déjà dans la page, on ne
      l'affiche pas) : chaque élément a une clé STABLE (sélecteur), son rôle, son texte, ses options ; data-ouvre dit quel
      écran un bouton ouvre. Rien n'est codé action par action : un bouton ajouté demain apparaît tout seul.
   2. Le serveur (agent_actions.py) demande UN plan complet au modèle : une seule question au lieu d'une par clic.
   3. EXÉCUTION : la page déroule le plan vite (curseur rapide), ouvre d'elle-même l'écran où se trouve l'élément visé (en
      passant par ses vrais boutons, même imbriqués), vérifie chaque étape et s'arrête net au premier écart ; elle referme
      ce qu'elle n'a ouvert que pour atteindre un élément. */
const PLAN = {
  ECRANS: [["Page principale (en-tête, conversation, saisie)", ".entete, #vue_chat"], ["Options", "#feuille_options"],
           ["Langue des réponses", "#feuille_langue"], ["Historique", "#feuille_historique"],
           ["Appel Live : modèles et comptes", "#feuille_live_etat"], ["Voix baoulé : serveur GPU et crédit", "#feuille_gpu"],
           ["Tests et rapports", "#vue_tests"]],
  MAX_ETAPES: 15,
  /** Clé stable d'un élément (la même d'un chargement à l'autre), ou null s'il n'en a pas (boutons d'un message...). */
  cle(el) {
    if (el.id) return `#${el.id}`;
    const base = el.parentElement?.closest("[id]"), b = base ? `#${base.id} ` : "";
    for (const a of ["data-theme-choix", "data-code", "data-id", "data-vue", "data-fermer"]) {
      if (!el.hasAttribute(a)) continue;
      const v = el.getAttribute(a);
      return `${b}[${a}${v ? `=${JSON.stringify(v)}` : ""}]`;
    }
    if (el.classList.contains("puce")) return `#suggestions .puce:nth-child(${[...el.parentElement.children].indexOf(el) + 1})`;
    return null;
  },
  texte(el) {                                      // texte lisible, même d'un écran fermé (innerText y serait vide)
    if (el.tagName === "SELECT") return (el.closest(".ligne")?.querySelector(".etiquette")?.textContent || el.getAttribute("aria-label") || el.id).trim();
    const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT), morceaux = [];
    for (let n; (n = w.nextNode());) if (n.data.trim()) morceaux.push(n.data.trim());
    return (el.getAttribute("aria-label") || morceaux.join(" ") || el.title || el.placeholder || el.id).replace(/\s+/g, " ").slice(0, 90);
  },
  nomEcran(sel) { return (this.ECRANS.find(([, s]) => s.split(",").pop().trim() === sel) || [sel])[0]; },
  carte() {
    remplirLangues(); remplirHistorique();         // listes à jour (sans ouvrir les fenêtres)
    const ouvreurs = {};
    document.querySelectorAll("[data-ouvre]").forEach(b => (ouvreurs[b.dataset.ouvre] ||= []).push(this.cle(b)));
    const ecrans = this.ECRANS.map(([nom, sel]) => {
      const elements = [];
      for (const c of document.querySelectorAll(sel)) for (const el of c.querySelectorAll(AGENT.ACTIFS)) {
        if (el.closest("#live, .msg")) continue;
        const k = this.cle(el);
        if (!k || elements.some(e => e.cle === k)) continue;
        const d = { cle: k, role: AGENT.role(el), nom: this.texte(el) };
        if (el.tagName === "SELECT") { d.valeur = el.selectedOptions[0]?.textContent; d.options = [...el.options].map(o => o.textContent); }
        else if (d.role === "champ") d.valeur = el.value.slice(0, 80);
        if (el.dataset.ouvre) d.ouvre = this.nomEcran(el.dataset.ouvre);
        if (el.disabled) d.etat = "désactivé"; else if (el.classList.contains("choisi")) d.etat = "choisi";
        const r = AGENT.refus(el); if (r) d.reserve_a_la_personne = r;
        if (el.matches("#nouvelle, #nouvelle_h")) d.attention = "efface la conversation affichée";
        elements.push(d);
      }
      const id = sel.split(",").pop().trim();
      return { ecran: nom, cle: id, ouvert_par: ouvreurs[id] || [], elements };
    });
    // version : change si l'application change (pas si l'historique change) -> les raccourcis appris restent valables
    const stable = ecrans.flatMap(e => e.elements.filter(x => !x.cle.includes("data-id")).map(x => x.cle)).join("|");
    let h = 0; for (let i = 0; i < stable.length; i++) h = (h * 31 + stable.charCodeAt(i)) | 0;
    return { version: (h >>> 0).toString(36), ecrans };
  },
  etat() {
    const l = LANGUES.find(x => x.code === $("#langue").value);
    return { ecran_ouvert: feuilleOuverte ? this.nomEcran(`#${feuilleOuverte.id}`) : testsAffiches() ? "Tests et rapports" : null,
             accueil: $("#vue_chat").classList.contains("accueil"), appel: LIVE.compact ? "réduit" : "plein écran",
             saisie: zone.value.slice(0, 120), messages: colonne.querySelectorAll(".msg.moi").length,
             reglages: { langue_reponses: l ? l.nom : $("#langue").value, voix: $("#genre").selectedOptions[0]?.textContent,
                         lecture_auto: $("#lecture_auto").selectedOptions[0]?.textContent, theme: themePage() } };
  },
  conteneur(el) { return el.closest(".feuille, #vue_tests, #vue_chat, .entete"); },
  ouvert(c) { return c.classList.contains("feuille") ? c.classList.contains("ouvert") : c.classList.contains("active"); },
  async attendreQue(test, ms = 1200) {
    const t0 = performance.now();
    while (!test()) { if (performance.now() - t0 > ms) return false; await attendre(30); }
    return true;
  },
  async toucher(el) { const p = await AGENT.aller(el); await AGENT.appuyer(el, p); el.click(); },
  /** Rend l'élément atteignable comme le ferait une personne : ouvre l'écran qui le contient par ses boutons (même
   *  imbriqués : « Tests et rapports » est dans les Options), ou ferme la fenêtre qui le cache. */
  async atteindre(el, auto, profondeur = 0) {
    const c = this.conteneur(el);
    if (!c || profondeur > 3) return;
    const ouvrir = async () => {
      const b = document.querySelector(`[data-ouvre="#${c.id}"]`);
      if (!b) throw new Error(`aucun bouton n'ouvre l'écran « ${this.nomEcran(`#${c.id}`)} »`);
      await this.atteindre(b, auto, profondeur + 1);
      await this.toucher(b);
      if (!await this.attendreQue(() => this.ouvert(c))) throw new Error(`l'écran « ${this.nomEcran(`#${c.id}`)} » ne s'est pas ouvert`);
    };
    if (c.classList.contains("feuille")) {
      if (this.ouvert(c)) return;
      await ouvrir();
      auto.push(c);
      await attendre(MOUVEMENT.reduit() ? 0 : 160);            // la fenêtre se pose
      return;
    }
    if (feuilleOuverte) { fermer(); await attendre(MOUVEMENT.reduit() ? 0 : 200); }   // une fenêtre cache la page
    if (c.classList.contains("vue") && !this.ouvert(c)) await ouvrir();
  },
  /** Déroule un plan [{action, cible, valeur, texte, envoyer, sens}] ; s'arrête au premier écart, avec la raison et
   *  l'état de l'écran (le serveur fait alors corriger le plan). */
  async executer(etapes) {
    const t0 = performance.now(), auto = [], faites = [], liste = Array.isArray(etapes) ? etapes.slice(0, this.MAX_ETAPES) : [];
    const fin = (ok, plus = {}) => ({ ok, faites, ...plus, ecran: this.etat(), duree_ms: Math.round(performance.now() - t0) });
    AGENT.rapide = true;
    try {
      for (const [i, e] of liste.entries()) {
        const echec = raison => fin(false, { etape: i + 1, action: e.action, cible: e.cible, raison });
        if (e.action === "attendre") { await attendre(Math.min(1500, Math.max(0, +e.ms || 300))); faites.push("attendre"); continue; }
        if (e.action === "fermer") {
          if (feuilleOuverte) {
            await this.toucher(feuilleOuverte.querySelector("[data-fermer]"));
            if (!await this.attendreQue(() => !feuilleOuverte)) return echec("la fenêtre ne s'est pas fermée");
          }
          faites.push("fermer"); continue;
        }
        let el = null;
        try { el = e.cible ? document.querySelector(e.cible) : null; } catch { el = null; }
        if (!el) return echec(`élément « ${e.cible} » introuvable`);
        const refus = AGENT.refus(el);
        if (refus) return echec(`réservé à la personne : ${refus}`);
        try { await this.atteindre(el, auto); } catch (x) { return echec(x.message); }
        if (!el.isConnected) el = document.querySelector(e.cible);   // la fenêtre a redessiné sa liste en s'ouvrant
        // les lignes d'une fenêtre qui s'ouvre arrivent en cascade (opacité 0 un instant) : on attend qu'elles soient là
        if (!el || !await this.attendreQue(() => AGENT.visible(el), 900)) return echec("élément encore caché après l'ouverture de son écran");
        if (e.action === "cliquer") {
          if (el.disabled) return echec(`« ${this.texte(el)} » est désactivé`);
          await this.toucher(el);
          if (el.dataset.ouvre) {                  // ouvrir un écran à la demande : il reste ouvert
            const c = $(el.dataset.ouvre);
            if (!await this.attendreQue(() => this.ouvert(c))) return echec("l'écran ne s'est pas ouvert");
            const k = auto.indexOf(c); if (k >= 0) auto.splice(k, 1);
          }
          if (el.matches("[data-fermer]") && !await this.attendreQue(() => !feuilleOuverte)) return echec("la fenêtre ne s'est pas fermée");
          if (el.closest("#theme")) await attendre(MOUVEMENT.reduit() ? 0 : 260);   // le nouveau thème s'ouvre en cercle
          if (el.closest("#liste_langues, #liste_historique")) await attendre(MOUVEMENT.reduit() ? 0 : 200);   // la liste se referme
        } else if (e.action === "choisir") {
          if (el.tagName !== "SELECT") return echec("cet élément n'est pas une liste déroulante");
          const v = normal(e.valeur), opts = [...el.options];
          const o = opts.find(x => normal(x.value) === v || normal(x.textContent) === v)
                 || opts.find(x => v && normal(x.textContent).includes(v));
          if (!o) return echec(`option « ${e.valeur} » introuvable dans « ${this.texte(el)} »`);
          const p = await AGENT.aller(el); await AGENT.appuyer(el, p);
          el.value = o.value; el.dispatchEvent(new Event("change", { bubbles: true }));
          MOUVEMENT.texte(el); AGENT.bulle(el, o.textContent);
          if (el.value !== o.value) return echec("la valeur n'a pas été prise");
        } else if (e.action === "ecrire") {
          if (!/^(TEXTAREA|INPUT)$/.test(el.tagName)) return echec("cet élément n'est pas un champ où écrire");
          const texte = String(e.texte ?? "").slice(0, 2000);
          const p = await AGENT.aller(el); await AGENT.appuyer(el, p);
          el.focus({ preventScroll: true }); await AGENT.taper(el, texte);
          if (el.value !== texte) return echec("le texte n'a pas été écrit");
          if (e.envoyer) {
            if (el !== zone) el.form?.requestSubmit();
            else {
              if (occupe) return echec("le chat écrit est déjà en train de répondre");
              const n = colonne.querySelectorAll(".msg.moi").length;
              await this.toucher($("#envoyer"));
              if (!await this.attendreQue(() => colonne.querySelectorAll(".msg.moi").length > n)) return echec("le message n'est pas parti");
            }
          }
        } else if (e.action === "defiler") {
          const z = el.classList.contains("feuille") ? el.querySelector(".corps") : el.id === "vue_chat" ? fil : el.id === "vue_tests" ? $(".defile") : el;
          await AGENT.aller(z);
          z.scrollBy({ top: (e.sens === "haut" ? -1 : 1) * z.clientHeight * 0.7, behavior: MOUVEMENT.reduit() ? "auto" : "smooth" });
          await attendre(MOUVEMENT.reduit() ? 0 : 300);
        } else return echec(`action inconnue : ${e.action}`);
        faites.push(`${e.action} ${e.cible}${e.valeur ? ` = ${e.valeur}` : ""}${e.texte ? ` « ${String(e.texte).slice(0, 40)} »` : ""}`);
      }
      for (const c of auto.reverse()) {             // ce qui n'a été ouvert que pour atteindre un élément se referme
        if (c.classList.contains("feuille") && this.ouvert(c)) {
          await this.toucher(c.querySelector("[data-fermer]"));
          await this.attendreQue(() => !this.ouvert(c), 600);
        }
      }
      return fin(true);
    } finally { AGENT.rapide = false; AGENT.finir(0); }
  },
};

/* ── Les données lues pendant l'appel s'affichent (05/10/2026 : « s'il dit combien j'ai consommé, il doit le montrer »)
   Valeurs = celles de l'outil AOCEDA (serveur : carte_outil), jamais une de plus. La carte arrive du côté du
   personnage, ses blocs en cascade ; les chiffres comptent jusqu'à leur valeur, les barres poussent une à une, les
   jauges se remplissent ; le personnage la montre du doigt. Elle s'en va quand la conversation passe à autre chose (ou ×) ;
   à la fin de l'appel, elle reste dans la conversation écrite, à sa place. ── */
const nf = (v, d = 0) => v == null || !isFinite(v) ? "–" : Number(v).toLocaleString("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d });
const jourCourt = iso => { const d = new Date(String(iso).length <= 10 ? `${iso}T12:00` : iso); return isNaN(d) ? "" : d.toLocaleDateString("fr-FR", { weekday: "short", day: "numeric" }); };
const dateCourte = iso => { const d = new Date(iso); return isNaN(d) ? "" : d.toLocaleDateString("fr-FR", { day: "numeric", month: "short" }); };
const CARTES = {
  courante: null,
  PASTILLES: { conso: ["p-jaune", `<path d="M13 2 4.5 13.5H11L10 22l8.5-11.5H12Z"/>`], repartition: ["p-violet", `<path d="M12 3a9 9 0 1 0 9 9h-9Z"/><path d="M15 3.5A9 9 0 0 1 20.5 9H15Z"/>`],
               mensuel: ["p-bleu", `<rect x="3.5" y="5" width="17" height="15" rx="2.5"/><path d="M3.5 10h17M8 3v4M16 3v4"/>`], heures: ["p-jaune", `<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>`],
               prevision: ["p-vert", `<path d="M3.5 17 9 11l4 4 7.5-8"/><path d="M15 7h5.5v5.5"/>`], credit: ["p-vert", `<rect x="3" y="6" width="18" height="13" rx="2.5"/><path d="M3 10h18M15.5 14.5h2"/>`],
               alertes: ["p-rouge", `<path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15Z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>`], interventions: ["p-gris", `<path d="M14.5 6.5a4 4 0 0 0-5.3 5.3L4 17l3 3 5.2-5.2a4 4 0 0 0 5.3-5.3l-2.5 2.5-2.5-.5-.5-2.5Z"/>`],
               capteurs: ["p-bleu", `<path d="M9 3v5M15 3v5M6.5 8h11v3a5.5 5.5 0 0 1-11 0Z"/><path d="M12 16.5V21"/>`] },
  barres(vals, { fort = [], partiel = -1, titres = [] } = {}) {
    const max = Math.max(0, ...vals.map(v => v || 0));
    return `<div class="cd-barres">${vals.map((v, i) => `<i style="--h:${max > 0 ? Math.max(0.025, (v || 0) / max).toFixed(3) : 0.025};--i:${i}" class="${fort.includes(i) ? "fort" : ""}${i === partiel ? " partiel" : ""}" title="${esc(titres[i] || "")}"></i>`).join("")}</div>`;
  },
  axe: libelles => `<div class="cd-axe">${libelles.map(l => `<span>${esc(l)}</span>`).join("")}</div>`,
  grand: (v, dec, unite, prefixe = "") => `<div class="cd-grand">${prefixe}<span data-compte="${v ?? ""}" data-dec="${dec}">${nf(v, dec)}</span><small>${unite}</small></div>`,
  corps(c) {
    const vide = t => `<div class="cd-note">${t}</div>`;
    switch (c.type) {
      case "conso": {
        // 0 kWh sans aucun jour mesuré = aucune mesure reçue : jamais de faux « -100 % » (même règle qu'AOCEDA)
        const j = c.jours || [], mesure = !!c.kwh || j.length > 0, r = mesure && c.prec?.kwh > 0 && c.kwh != null ? c.kwh / c.prec.kwh - 1 : null;
        const sens = r == null ? "" : r <= -0.1 ? "baisse" : r >= 0.1 ? "hausse" : "";
        const max = j.reduce((m, x, i) => (x.kwh ?? 0) > (j[m]?.kwh ?? 0) ? i : m, 0);
        return this.grand(c.kwh, 2, "kWh")
          + (c.fcfa != null && c.kwh ? `<div class="cd-second">≈ <b data-compte="${c.fcfa}">${nf(c.fcfa)}</b> F CFA <span>(estimation, hors prime fixe)</span></div>` : "")
          + (!c.kwh && !j.length ? vide("Aucune mesure reçue sur cette période.") : "")
          + (c.prec ? `<div class="cd-puce ${sens}">${r == null ? "" : `<b style="white-space:nowrap">${r < 0 ? "▼" : r > 0 ? "▲" : "="} ${nf(Math.abs(r * 100))} %</b>`}<span>${esc(c.prec.libelle)} : ${nf(c.prec.kwh, 2)} kWh</span></div>` : "")
          + (j.length >= 2 ? this.barres(j.map(x => x.kwh), { fort: [max], partiel: c.en_cours ? j.length - 1 : -1, titres: j.map(x => `${jourCourt(x.date)} : ${nf(x.kwh, 2)} kWh`) })
                             + this.axe([jourCourt(j[0].date), jourCourt(j[j.length - 1].date)]) : "");
      }
      case "repartition":
        if (!(c.appareils || []).length) return vide("Aucune mesure par appareil sur cette période.");
        return this.grand(c.kwh, 2, "kWh au total") + `<div class="cd-lignes" style="margin-top:12px">${c.appareils.map((a, i) =>
          `<div class="cd-ligne"><span>${esc(a.nom)}</span><b>${nf(a.pct)} % <small>${nf(a.kwh, 2)} kWh</small></b><div class="cd-jauge"><i style="--p:${a.pct || 0};--i:${i}"></i></div></div>`).join("")}</div>`;
      case "mensuel": {
        const m = c.mois || [], fini = [...m].reverse().find(x => !x.en_cours) || m[m.length - 1];
        if (!m.length) return vide("Aucun mois mesuré pour l'instant.");
        return this.grand(fini?.fcfa, 0, "F CFA") + `<div class="cd-second">${esc(fini?.libelle || "")}${fini ? ` · ${nf(fini.kwh, 1)} kWh` : ""}</div>`
          + this.barres(m.map(x => x.fcfa), { fort: [m.indexOf(fini)], partiel: m.findIndex(x => x.en_cours), titres: m.map(x => `${x.libelle} : ${nf(x.fcfa)} F CFA${x.en_cours ? " (en cours)" : ""}`) })
          + this.axe(m.map(x => x.libelle.split(" ")[0].slice(0, 4) + (x.en_cours ? "…" : "")));
      }
      case "heures": {
        const h = c.heures || [];
        if (!h.length) return vide("Aucune mesure sur ces jours.");
        return `<div class="cd-second" style="margin-top:0">Pointe : <b>${(c.pointe || []).map(x => `${x} h`).join(", ") || "–"}</b></div>`
          + this.barres(h.map(x => x.kwh), { fort: h.map((x, i) => (c.pointe || []).includes(x.h) ? i : -1), titres: h.map(x => `${x.h} h : ${nf(x.kwh, 3)} kWh`) })
          + this.axe(["0 h", "6 h", "12 h", "18 h", "23 h"]);
      }
      case "prevision": {
        if (!["band", "band_large"].includes(c.mode))
          return this.grand(c.a_ce_jour, 0, "F CFA à ce jour") + vide(`Trop tôt pour une prévision fiable : il faut au moins ${c.n_min ?? 3} jours complets de mesures ce mois-ci (jour ${c.jours_ecoules ?? "–"} sur ${c.jours_du_mois ?? "–"}).`);
        const fin = (c.haut || 1) * 1.1, pc = v => `${Math.max(0, Math.min(100, (v || 0) / fin * 100)).toFixed(1)}%`;
        return this.grand(c.central, 0, "F CFA", "≈ ") + `<div class="cd-second">entre <b>${nf(c.bas)}</b> et <b>${nf(c.haut)}</b> F CFA · déjà <b>${nf(c.a_ce_jour)}</b> F</div>`
          + `<div class="cd-plage"><div class="deja" style="width:${pc(c.a_ce_jour)}"></div><div class="fourchette" style="left:${pc(c.bas)};width:calc(${pc(c.haut)} - ${pc(c.bas)})"></div><div class="repere" style="left:${pc(c.central)}"></div></div>`
          + (c.confiance ? vide(`Prévision ${String(c.confiance).replace("_", " ")}.`) : "");
      }
      case "credit": {
        if (c.postpaye) return vide("Compteur postpayé : pas de crédit à recharger, une facture CIE tous les deux mois.");
        const p = c.recharge > 0 ? Math.max(0, Math.min(1, (c.restant || 0) / c.recharge)) : 0;
        return `<div class="cd-anneau"><svg viewBox="0 0 84 84"><circle class="fond" cx="42" cy="42" r="34"/><circle class="plein" cx="42" cy="42" r="34" data-part="${p.toFixed(4)}" style="stroke-dasharray:213.63;stroke-dashoffset:${(213.63 * (1 - p)).toFixed(2)}"/></svg>
          <div>${this.grand(c.restant, 0, "F CFA")}<div class="cd-second">restants sur <b>${nf(c.recharge)}</b> F rechargés${c.jours_restants != null ? ` · ≈ <b>${nf(c.jours_restants)}</b> jours` : ""}</div></div></div>`
          + ((c.recharges || []).length ? `<div class="cd-lignes" style="margin-top:12px">${c.recharges.map(x => `<div class="cd-rang"><span class="cd-pt on" style="animation:none"></span><div><b>+${nf(x.montant)} F</b></div><span class="cd-statut">${dateCourte(x.date)}</span></div>`).join("")}</div>` : "");
      }
      case "alertes":
        return `<div class="cd-second" style="margin:0 0 10px"><b>${nf(c.non_lues)}</b> non lue${c.non_lues > 1 ? "s" : ""}</div>`
          + ((c.alertes || []).length ? `<div class="cd-lignes">${c.alertes.map(a => `<div class="cd-rang"><span class="cd-pt ${normal(a.severite)}"></span><div><b>${esc(a.type)}</b><small>${esc(a.message)}</small></div><span class="cd-statut">${dateCourte(a.date)}</span></div>`).join("")}</div>` : vide("Aucune alerte."));
      case "interventions":
        return (c.liste || []).length ? `<div class="cd-lignes">${c.liste.map(x => `<div class="cd-rang"><div><b>${esc(x.type)}</b><small>${esc(x.description)}</small></div><span class="cd-statut">${esc(x.statut)}${x.date_programmee ? ` · ${dateCourte(x.date_programmee)}` : x.date ? ` · ${dateCourte(x.date)}` : ""}</span></div>`).join("")}</div>` : vide("Aucune intervention.");
      case "capteurs":
        return `<div class="cd-lignes">${(c.capteurs || []).map(x => { const etat = !x.en_ligne ? ["hl", "hors ligne"] : x.etat === "ON" ? ["on", "allumé"] : ["", "éteint"];
          return `<div class="cd-rang"><span class="cd-pt ${etat[0]}"></span><div><b>${esc(x.nom)}</b></div><span class="cd-statut">${etat[1]}</span></div>`; }).join("")}</div>`;
    }
    return "";
  },
  element(c, anime = true) {
    const [p, ic] = this.PASTILLES[c.type] || ["p-gris", ""], el = document.createElement("div");
    el.className = `carte-donnees c-${c.type}${anime && !MOUVEMENT.reduit() ? " anime" : ""}`;
    el.innerHTML = `<div class="cd-tete"><span class="pastille ${p}">${I(ic)}</span><div><div class="cd-titre">${esc(c.titre || "")}</div>${c.periode ? `<div class="cd-periode">${esc(c.periode)}</div>` : ""}</div>
      <button class="cd-fermer" aria-label="Fermer la carte">${I(`<path d="M6 6l12 12M18 6 6 18"/>`)}</button></div>${this.corps(c)}`;
    [...el.children].forEach((x, k) => x.style.setProperty("--k", k));
    el.querySelector(".cd-fermer").onclick = () => this.retirer();
    return el;
  },
  /** Les chiffres comptent jusqu'à leur valeur (1 s, ralentit à la fin) ; l'anneau du crédit se remplit. */
  animer(el) {
    if (MOUVEMENT.reduit()) return;
    el.querySelectorAll("[data-compte]").forEach(x => {
      const fin = Number(x.dataset.compte), dec = Number(x.dataset.dec || 0);
      if (x.dataset.compte === "" || !isFinite(fin)) return;
      const t0 = performance.now() + 260;
      const pas = t => { const k = Math.min(1, Math.max(0, (t - t0) / 1000)), e = 1 - Math.pow(1 - k, 4);
        x.textContent = nf(fin * e, dec); if (k < 1 && x.isConnected) requestAnimationFrame(pas); else x.textContent = nf(fin, dec); };
      x.textContent = nf(0, dec); requestAnimationFrame(pas);
    });
    el.querySelectorAll("circle[data-part]").forEach(x => x.animate([{ strokeDashoffset: 213.63 }, { strokeDashoffset: 213.63 * (1 - Number(x.dataset.part)) }],
                                                                    { duration: 1100, delay: 300, easing: MOUVEMENT.E.sortie, fill: "backwards" }));
  },
  /** Montre la carte dans l'appel (remplace la précédente) ; renvoie son élément (le personnage la montre du doigt). */
  montrer(c) {
    const z = $("#live_carte"), live = $("#live"), ancienne = z.firstElementChild, el = this.element(c);
    if (ancienne) {
      ancienne.getAnimations().forEach(a => a.cancel());
      if (MOUVEMENT.reduit()) ancienne.remove();
      else { Object.assign(ancienne.style, { position: "absolute", top: "0", left: "0", width: `${ancienne.offsetWidth}px` });
        ancienne.animate([{ opacity: 1 }, { opacity: 0, transform: "translateY(-8px) scale(.97)" }], { duration: 220, easing: MOUVEMENT.E.entree }).onfinish = () => ancienne.remove(); }
    }
    const pile = [$(".live-pile"), $("#live_perso"), $(".live-textes"), $(".live-sous-titres")];
    if (!live.classList.contains("avec-carte") && !LIVE.compact) MOUVEMENT.flip(pile, () => { live.classList.add("avec-carte"); z.prepend(el); });
    else { live.classList.add("avec-carte"); z.prepend(el); }
    if (!MOUVEMENT.reduit()) {                     // elle arrive du côté du personnage
      const ligne = !LIVE.compact && getComputedStyle($(".live-centre")).flexDirection === "row";
      const de = LIVE.compact ? (innerWidth <= 640 ? "translateY(-12px)" : "translateY(12px)") : ligne ? "translateX(-28px)" : "translateY(-14px)";
      el.animate([{ opacity: 0, transform: `${de} scale(.96)`, filter: "blur(4px)" }, { opacity: 1, transform: "none", filter: "blur(0)" }],
                 { duration: 620, easing: MOUVEMENT.E.sortie });
    }
    this.animer(el);
    this.courante = { c, el, t: Date.now(), parle: false };
    LIVE.cartes.push({ c, apres: LIVE.lignesVues });
    this.place();
    return el;
  },
  retirer() {
    const z = $("#live_carte"), el = z.firstElementChild, live = $("#live");
    this.courante = null;
    if (!el) return;
    document.documentElement.style.setProperty("--haut-carte", "0px");   // la page reprend sa place pendant qu'elle part
    const fin = () => {
      const pile = [$(".live-pile"), $("#live_perso"), $(".live-textes"), $(".live-sous-titres")];
      if (LIVE.compact || MOUVEMENT.reduit()) { el.remove(); live.classList.remove("avec-carte"); }
      else MOUVEMENT.flip(pile, () => { el.remove(); live.classList.remove("avec-carte"); });
    };
    if (MOUVEMENT.reduit()) return fin();
    el.animate([{ opacity: 1 }, { opacity: 0, transform: "scale(.96)", filter: "blur(3px)" }], { duration: 240, easing: MOUVEMENT.E.entree, fill: "forwards" }).onfinish = fin;
  },
  /** La personne reprend la parole après que l'agent a dit ce que montrait la carte : la carte s'en va. */
  conversationSuit() { const c = this.courante; if (c && c.parle && Date.now() - c.t > 3000) this.retirer(); },
  vider() { this.courante = null; $("#live_carte").innerHTML = ""; $("#live").classList.remove("avec-carte"); this.place(); },
  /** Barre réduite : la page fait aussi de la place à la carte (rien de ce que l'agent touche n'est caché dessous). */
  place() {
    const z = $("#live_carte"), live = $("#live");
    const h = LIVE.compact && z.firstElementChild && !live.hidden && live.classList.contains("compact") ? Math.round(z.getBoundingClientRect().height) + 12 : 0;
    document.documentElement.style.setProperty("--haut-carte", `${h}px`);
  },
};

/* ── Mouvement (motion design, 05/10/2026) : la partie script du système décrit dans les styles (« Mouvement »).
   Rien ici ne change ce que fait un bouton : on ne fait que montrer, avec précision, ce qui se passe. ── */
const MOUVEMENT = {
  E: { sortie: "cubic-bezier(.22, 1, .36, 1)", entree: "cubic-bezier(.55, 0, 1, .45)", deux: "cubic-bezier(.65, 0, .35, 1)",
       ressort: "cubic-bezier(.34, 1.36, .64, 1)" },
  reduit: () => matchMedia("(prefers-reduced-motion: reduce)").matches,
  source: null,                                   // d'où part votre prochain message (bouton Envoyer, suggestion, micro)
  /** Vrai ressort amorti : x'' = -k (x - 1) - c x', raideur k = 260, amortissement c = 22 (masse 1) -> facteur
   *  d'amortissement 0,68 : UN seul dépassement d'environ 5 %, posé en 0,56 s. Échantillonné en 48 points pour la
   *  fonction CSS linear() (navigateurs récents) ; sinon la courbe de secours des styles. */
  ressort(raideur = 260, amort = 22, n = 48) {
    const w0 = Math.sqrt(raideur), z = amort / (2 * w0), wd = w0 * Math.sqrt(1 - z * z), T = Math.log(500) / (z * w0);
    const x = t => 1 - Math.exp(-z * w0 * t) * (Math.cos(wd * t) + (z * w0 / wd) * Math.sin(wd * t));
    return `linear(${Array.from({ length: n }, (_, i) => (i === n - 1 ? 1 : x(T * i / (n - 1))).toFixed(4)).join(", ")})`;
  },
  init() {
    try {
      const r = this.ressort();
      if (CSS.supports("transition-timing-function", r)) { this.E.ressort = r; document.documentElement.style.setProperty("--e-ressort", r); }
    } catch {}
    document.addEventListener("pointerdown", e => this.appui(e), { passive: true });
    document.addEventListener("click", e => this.clic(e), true);   // AVANT les actions : certaines remplacent l'icône
  },

  /* ── Onde : un halo part exactement du point touché et s'étend jusqu'au coin le plus loin du bouton ── */
  ONDE: ".rond, .outil, .puce, .ecouter, .bouton-large, button.ligne, .btn, .retour, .live-icone, .live-bouton, .live-ecrire button, .vers-bas, .cd-fermer, .segments button",
  appui(e) {
    if (e.button !== 0 || this.reduit()) return;
    let hote = e.target.closest?.(this.ONDE);
    if (!hote || hote.disabled) return;
    if (hote.classList.contains("live-bouton")) hote = hote.querySelector("i") || hote;   // le rond, pas la légende
    let couche = hote.querySelector(":scope > .m-onde");
    if (!couche) { couche = document.createElement("span"); couche.className = "m-onde"; hote.classList.add("m-hote"); hote.appendChild(couche); }
    const r = hote.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
    const d = 2 * Math.hypot(Math.max(x, r.width - x), Math.max(y, r.height - y)), i = document.createElement("i");
    Object.assign(i.style, { left: `${x - d / 2}px`, top: `${y - d / 2}px`, width: `${d}px`, height: `${d}px` });
    couche.appendChild(i);
    i.animate([{ transform: "scale(0)", opacity: .2 }, { transform: "scale(1)", opacity: 0 }],
              { duration: 680, easing: this.E.sortie }).onfinish = () => i.remove();
  },

  /* ── Icônes qui miment leur action : la classe m-joue (styles) le temps de l'animation ── */
  JOUE: "#plus, #nouvelle, #btn_historique, #btn_options, #btn_live, .retour, .ecouter[data-etat='reessayer']",
  clic(e) {
    const el = e.target.closest?.(`${this.JOUE}, #envoyer`);
    if (!el || el.disabled || this.reduit()) return;
    if (el.id === "envoyer") { if (el.dataset.etat === "envoyer") { this.envol(el); this.depuis(el); } return; }
    el.classList.remove("m-joue"); void el.offsetWidth; el.classList.add("m-joue");
    clearTimeout(el._mJoue); el._mJoue = setTimeout(() => el.classList.remove("m-joue"), 1100);
  },
  /** Envoyer : l'avion en papier s'envole en haut à droite (une copie : le bouton devient déjà « Stop »). */
  envol(b) {
    const svg = b.querySelector("svg"); if (!svg) return;
    const r = svg.getBoundingClientRect(), c = svg.cloneNode(true);
    Object.assign(c.style, { position: "fixed", left: `${r.left}px`, top: `${r.top}px`, width: `${r.width}px`, height: `${r.height}px`,
                             margin: 0, pointerEvents: "none", zIndex: 30, color: getComputedStyle(b).color, animation: "none" });
    document.body.appendChild(c);
    c.animate([{ transform: "none", opacity: 1 }, { transform: "translate(30px, -30px) rotate(-10deg) scale(.6)", opacity: 0 }],
              { duration: 440, easing: this.E.entree }).onfinish = () => c.remove();
  },

  /* ── Votre message part d'où vous l'avez envoyé (FLIP : on le pose à sa place, puis on l'anime DEPUIS la source) ── */
  depuis(el, garderTaille = false) {
    const r = el.getBoundingClientRect();
    this.source = { x: r.left + r.width / 2, y: r.top + r.height / 2, w: garderTaille ? r.width : 0, t: performance.now() };
  },
  lancer(msg) {
    const s = this.source; this.source = null;
    const b = msg?.querySelector(".bulle");
    if (!b || !s || performance.now() - s.t > 1500 || this.reduit()) return;
    msg.classList.add("m-vole");
    const r = b.getBoundingClientRect(), k = s.w ? Math.min(1.15, Math.max(.6, s.w / r.width)) : .35;
    const dx = s.x - (r.left + r.width / 2), dy = s.y - (r.top + r.height / 2);
    // une suggestion DEVIENT votre message (même taille, opaque) ; depuis un bouton, il grandit en apparaissant
    b.animate([{ transform: `translate(${dx}px, ${dy}px) scale(${k})`, opacity: s.w ? 1 : 0 }, { opacity: 1, offset: .3 },
               { transform: "none", opacity: 1 }], { duration: 640, easing: this.E.sortie });
    for (const c of msg.children) if (c !== b) c.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 360, delay: 240, easing: this.E.sortie, fill: "backwards" });
  },

  /* ── Fenêtres : leur contenu arrive en cascade (36 ms entre deux blocs, 24 ms entre deux lignes d'une liste) ── */
  cascade(f) {
    if (!f) return;
    this.curseur(f.querySelector(".segments"));
    if (this.reduit()) return;
    [...f.querySelectorAll(".corps > *")].filter(e => e.offsetParent && !e.hidden).slice(0, 12).forEach((el, i) =>
      el.animate([{ opacity: 0, translate: "0 10px" }, { opacity: 1, translate: "0 0" }],
                 { duration: 480, delay: 90 + i * 36, easing: this.E.sortie, fill: "backwards" }));
    [...f.querySelectorAll("#liste_historique > .ligne, #liste_langues > .ligne")].slice(0, 14).forEach((el, i) =>
      el.animate([{ opacity: 0, translate: "0 6px" }, { opacity: 1, translate: "0 0" }],
                 { duration: 420, delay: 160 + i * 24, easing: this.E.sortie, fill: "backwards" }));
  },
  /** Choix du thème : un curseur glisse sous la case choisie (comme un sélecteur iOS), en ressort. */
  curseur(seg) {
    const b = seg?.querySelector("button.choisi");
    if (!b || !b.offsetWidth) return;
    let c = seg.querySelector(".m-curseur");
    if (!c) { c = document.createElement("span"); c.className = "m-curseur"; seg.prepend(c); seg.classList.add("m-glisse"); c.style.transition = "none"; }
    c.style.width = `${b.offsetWidth}px`; c.style.translate = `${b.offsetLeft}px 0`;
    if (c.style.transition) { void c.offsetWidth; c.style.transition = ""; }
  },
  /** Nouveau thème : il s'ouvre en cercle depuis le doigt (View Transitions) ; navigateur ancien : tout de suite. */
  theme(e, faire, apres) {
    const appliquer = () => { faire(); this.curseur($("#theme")); };
    const vt = !this.reduit() && document.startViewTransition ? document.startViewTransition(appliquer) : null;
    if (!vt) { appliquer(); apres(); return; }
    const r = e.currentTarget?.getBoundingClientRect?.();
    const x = e.clientX || (r ? r.left + r.width / 2 : innerWidth / 2), y = e.clientY || (r ? r.top + r.height / 2 : 0);
    const R = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
    vt.ready.then(() => document.documentElement.animate({ clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${R}px at ${x}px ${y}px)`] },
      { duration: 720, easing: this.E.deux, pseudoElement: "::view-transition-new(root)" })).catch(() => {});
    vt.finished.then(apres, apres);
  },

  /** « Voir en français » : le bloc se déplie (hauteur réelle mesurée) ou se replie, plus vite. */
  deplier(el) {
    const ouvrir = el.hidden;
    if (this.reduit()) { el.hidden = !ouvrir; return; }
    el.getAnimations().forEach(a => a.cancel());
    if (ouvrir) {
      el.hidden = false;
      const h = el.offsetHeight;
      el.animate([{ height: "0px", opacity: 0, marginTop: "0px", paddingTop: "0px", borderTopColor: "transparent" },
                  { height: `${h}px`, opacity: 1 }], { duration: 460, easing: this.E.sortie });
    } else {
      el.animate([{ height: `${el.offsetHeight}px`, opacity: 1 }, { height: "0px", opacity: 0, marginTop: "0px", paddingTop: "0px" }],
                 { duration: 260, easing: this.E.entree }).onfinish = () => { el.hidden = true; };
    }
  },
  /** Un texte qui change (état de l'appel Live) : l'ancien s'efface, le nouveau monte et se précise. */
  texte(el) {
    if (!this.reduit()) el.animate([{ opacity: 0, translate: "0 6px", filter: "blur(3px)" }, { opacity: 1, translate: "0 0", filter: "blur(0)" }],
                                   { duration: 380, easing: this.E.sortie });
  },
  /** Barre de saisie : du centre de l'accueil au bas de la conversation (et retour) en glissant et en changeant de
   *  taille (vraies largeur et hauteur, pas une déformation) ; les boutons et le texte suivent (transitions des styles). */
  morphZone(changement) {
    const z = $(".zone"), avant = z.getBoundingClientRect();
    changement();
    if (this.reduit() || !avant.width) return;
    const apres = z.getBoundingClientRect(), dy = avant.top + avant.height / 2 - (apres.top + apres.height / 2);
    if (Math.abs(dy) < 2 && Math.abs(avant.width - apres.width) < 2 && Math.abs(avant.height - apres.height) < 2) return;
    z.getAnimations().forEach(a => a.cancel());
    z.animate([{ translate: `0 ${dy}px`, maxWidth: `${avant.width}px`, height: `${avant.height}px` },
               { translate: "0 0", maxWidth: `${apres.width}px`, height: `${apres.height}px` }], { duration: 640, easing: this.E.deux });
  },
  /** Changement de vue (conversation, Tests et rapports) : la nouvelle arrive de la droite. */
  vue(el) {
    if (!this.reduit()) el.animate([{ opacity: 0, translate: "14px 0" }, { opacity: 1, translate: "0 0" }], { duration: 480, easing: this.E.sortie });
  },
  /** Appel Live : plein écran <-> barre réduite. L'écran se resserre en rectangle arrondi jusqu'à la place de la barre
   *  (puis la barre apparaît) ; à l'inverse, la barre s'ouvre en plein écran et le contenu revient en cascade. */
  compacter(live, oui) {
    this.animCompact?.cancel(); this.animCompact = null; this.animPerso?.cancel(); this.animPerso = null;
    if (this.reduit()) { live.classList.toggle("compact", oui); return; }
    const W = innerWidth, H = innerHeight, cadre = b => `inset(${b.top}px ${W - b.right}px ${H - b.bottom}px ${b.left}px round 26px)`;
    const perso = $("#live_perso"), centre = r => [r.left + r.width / 2, r.top + r.height / 2];
    // le personnage suit l'écran qui se resserre (ou s'ouvre) : il passe de sa grande place à sa place dans la barre
    const deplace = (a, b) => { const [ax, ay] = centre(a), [bx, by] = centre(b); return `translate(${(bx - ax).toFixed(1)}px, ${(by - ay).toFixed(1)}px) scale(${(b.width / a.width).toFixed(3)})`; };
    if (oui) {
      const p0 = perso.getBoundingClientRect();
      live.classList.add("compact"); const b = live.getBoundingClientRect(), p1 = perso.getBoundingClientRect(); live.classList.remove("compact");
      const a = this.animCompact = live.animate([{ clipPath: "inset(0px 0px 0px 0px round 0px)" }, { clipPath: cadre(b) }],
                                                { duration: 440, easing: this.E.deux, fill: "forwards" });
      const ap = this.animPerso = p0.width ? perso.animate([{ transform: "none" }, { transform: deplace(p0, p1) }], { duration: 440, easing: this.E.deux, fill: "forwards" }) : null;
      a.onfinish = () => { live.classList.add("compact"); a.cancel(); ap?.cancel(); this.animCompact = this.animPerso = null; CARTES.place(); };
    } else {
      const b = live.getBoundingClientRect(), p0 = perso.getBoundingClientRect();
      live.classList.remove("compact");
      const p1 = perso.getBoundingClientRect();
      live.animate([{ clipPath: cadre(b) }, { clipPath: "inset(0px 0px 0px 0px round 0px)" }], { duration: 560, easing: this.E.sortie });
      if (p0.width && p1.width) this.animPerso = perso.animate([{ transform: deplace(p1, p0) }, { transform: "none" }], { duration: 560, easing: this.E.sortie });
      TRANSITION_LIVE.elements().forEach((el, i) => el.animate([{ opacity: 0, translate: "0 12px" }, { opacity: 1, translate: "0 0" }],
        { duration: 440, delay: 160 + i * 40, easing: this.E.sortie, fill: "backwards" }));
      const carte = $("#live_carte").firstElementChild;   // la carte reprend sa place à côté de lui
      carte?.animate([{ opacity: 0, transform: "scale(.96)" }, { opacity: 1, transform: "none" }], { duration: 480, delay: 200, easing: this.E.sortie, fill: "backwards" });
    }
  },
  /** FLIP : on mesure, on change la mise en page, puis chaque élément glisse (et change de taille) de l'ancienne place à
   *  la nouvelle, au lieu de sauter. */
  flip(els, changement, duree = 560) {
    els = els.filter(Boolean);
    if (this.reduit()) { changement(); return; }
    const avant = els.map(e => e.getBoundingClientRect());
    changement();
    els.forEach((e, i) => {
      const a = avant[i], b = e.getBoundingClientRect();
      if (!a.width || !b.width) return;
      const dx = a.left - b.left, dy = a.top - b.top, sx = a.width / b.width, sy = a.height / b.height;
      if (Math.abs(dx) < 1 && Math.abs(dy) < 1 && Math.abs(sx - 1) < .01 && Math.abs(sy - 1) < .01) return;
      e.animate([{ transformOrigin: "0 0", transform: `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})` }, { transformOrigin: "0 0", transform: "none" }],
                { duration: duree, easing: this.E.sortie });
    });
  },
  /** Texte qui arrive par morceaux (réponse en cours, sous-titres de l'appel) : chaque nouveau morceau apparaît en fondu
   *  (520 ms) sans que ceux qui apparaissent encore ne « sautent » quand l'élément est réécrit : chaque morceau garde son
   *  heure d'arrivée (délai négatif). etat = { longueur, morceaux } propre à l'élément ; decalage = caractères du début
   *  qui ne sont plus affichés (sous-titres : seule la fin est montrée). */
  fondu(el, html, etat, texte = null, decalage = 0) {
    if (html != null) el.innerHTML = html; else el.textContent = texte;
    const t = performance.now(), total = decalage + el.textContent.length;
    if (total > etat.longueur) etat.morceaux.push([etat.longueur, t]);
    etat.longueur = total;
    etat.morceaux = etat.morceaux.filter(([p, t0]) => t - t0 < 520 && p < total);
    if (this.reduit() || !etat.morceaux.length) return;
    const depart = etat.morceaux[0][0], noeuds = [], w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    for (let n, p = decalage; (n = w.nextNode()); p += n.length) noeuds.push([n, p]);
    for (const [n, p0] of noeuds) {
      const p1 = p0 + n.length;
      if (p1 <= depart || !n.length) continue;
      const frag = document.createDocumentFragment(), bornes = etat.morceaux.map(m => m[0]).filter(b => b > p0 && b < p1);
      let a = p0;
      for (const b of [...bornes, p1]) {
        const s = n.data.slice(a - p0, b - p0), k = etat.morceaux.findLastIndex(m => m[0] <= a);
        if (s && (a < depart || k < 0)) frag.append(s);
        else if (s) { const sp = document.createElement("span"); sp.className = "m-neuf"; sp.textContent = s;
          sp.style.animationDelay = `${-Math.round(t - etat.morceaux[k][1])}ms`; frag.append(sp); }
        a = b;
      }
      n.replaceWith(frag);
    }
  },
  /** Petite annonce au-dessus de la saisie (langue choisie, langue demandée...) : elle monte, reste, s'efface. */
  annonce(texte) {
    const a = $("#annonce"); if (!a) return;
    a.innerHTML = `${ICONES.traduire}<span>${esc(texte)}</span>`;
    a.getAnimations().forEach(x => x.cancel()); clearTimeout(this.finAnnonce);
    if (this.reduit()) { a.style.opacity = 1; this.finAnnonce = setTimeout(() => { a.style.opacity = ""; }, 2800); return; }
    a.animate([{ opacity: 0, transform: "translateY(8px) scale(.94)", easing: this.E.sortie }, { opacity: 1, transform: "none", offset: .14 },
               { opacity: 1, transform: "none", offset: .86, easing: this.E.entree }, { opacity: 0, transform: "translateY(-4px) scale(.98)" }],
              { duration: 3000 });
  },
  /** Les boutons sous une réponse arrivent l'un après l'autre. */
  arrivee(el) {
    if (this.reduit() || !el) return;
    [...el.children].forEach((c, i) => c.style.setProperty("--j", i));
    el.classList.remove("m-arrive"); void el.offsetWidth; el.classList.add("m-arrive");
  },
  /** Bouton « en bas » : il apparaît quand on remonte la conversation (ressort), disparaît quand on y est. */
  versBas() {
    const b = $("#vers_bas"), loin = fil.scrollHeight - fil.scrollTop - fil.clientHeight > 260 && !$("#vue_chat").classList.contains("accueil");
    if (loin) {
      if (!b.hidden && !b._part) return;
      b._part = false; b.getAnimations().forEach(x => x.cancel()); b.hidden = false;
      if (!this.reduit()) b.animate([{ opacity: 0, transform: "translateY(10px) scale(.7)" }, { opacity: 1, transform: "none" }], { duration: 460, easing: this.E.ressort });
    } else if (!b.hidden && !b._part) {
      if (this.reduit()) { b.hidden = true; return; }
      b._part = true;
      b.animate([{ opacity: 1 }, { opacity: 0, transform: "translateY(8px) scale(.8)" }], { duration: 200, easing: this.E.entree, fill: "forwards" })
        .onfinish = () => { if (b._part) { b.hidden = true; b._part = false; b.getAnimations().forEach(x => x.cancel()); } };
    }
  },
  /** Micro : niveau de votre voix (0..1) pour l'anneau rouge (styles). */
  niveau(v) { $("#micro").style.setProperty("--niveau", v == null ? "0" : Math.min(1, v * 14).toFixed(3)); },
};
MOUVEMENT.init();

/* ── Démarrage ── */
(async () => {
  try {
    const c = await (await api("/config")).json(); LANGUES = c.langues; AUDIO_MAX_S = c.audio_max_s || 60; VERSION_PAGE = c.version_page || "";
    $("#langue").innerHTML = LANGUES.map(l => `<option value="${esc(l.code)}">${esc(l.nom)}</option>`).join("");
    const choix = stock.lire("aoceda_langue", "auto"); if (LANGUES.some(l => l.code === choix)) $("#langue").value = choix;
    $("#genre").value = stock.lire("aoceda_genre", "femme") === "homme" ? "homme" : "femme";
    const la = stock.lire("aoceda_lecture_auto", "vocal"); if (["vocal", "toujours", "jamais"].includes(la)) $("#lecture_auto").value = la;
  } catch { LANGUES = [{ code: "auto", nom: "Automatique" }]; $("#langue").innerHTML = `<option value="auto">Automatique</option>`; }
  accueil(); majBoutons();
})();
