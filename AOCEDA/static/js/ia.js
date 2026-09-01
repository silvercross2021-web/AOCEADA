'use strict';
const t = window.AOCEDA_T || (x => x);
/* ════════════════════════════════════════════════════════════
   AOCEDA, Assistant IA (vanilla JS, sans React)
   Le CONTENU des conversations est persisté côté serveur (modèle
   Conversation, apps.ai_assistant) et synchronisé entre tous les
   appareils du compte client — voir ConversationListCreateView /
   ConversationDetailView. L'IA lit aussi les données de conso côté
   serveur pour personnaliser ses réponses.
   ════════════════════════════════════════════════════════════ */

(function () {
  const token = localStorage.getItem('aoceda_access_token');
  if (!token && window.location.pathname.indexOf('/auth/') === -1) {
    window.location.href = '/auth/';
  }
})();

/* Délègue au helper partagé (client-shell.js) : refresh JWT transparent sur 401.
   Renvoie la Response brute (les appelants lisent res.json() / res.ok). */
function fetchWithAuth(url, options = {}) {
  return window.AOCEDA.authFetch(url, options);
}

function esc(s) {
  return String(s === null || s === undefined ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function logoSVG(s) {
  return `<svg width="${s}" height="${s}" viewBox="0 0 36 36" fill="none"><rect width="36" height="36" rx="8" fill="#C9760E"/><path d="M5 18H10L13.5 9L17.5 27L21 14L24 22L27 18H31" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}

const MOON_SVG = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
const SUN_SVG = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/></svg>';
const CHECK_SVG = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>';
const SPEAKER_SVG = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/></svg>';

const SUGGESTIONS = [
  "Pourquoi ma facture a augmenté ?",
  "Comment réduire ma consommation la nuit ?",
  "Quel est mon appareil le plus consommateur ?",
  "Comment est calculée ma facture CIE ?"
];

// Combien de messages du fil actif on envoie au serveur comme contexte pour CET appel
// (le serveur re-plafonne de toute façon, mais autant ne pas envoyer plus que nécessaire).
const HISTORIQUE_ENVOI_MAX = 20;
const PROVIDER_STORAGE_KEY = 'aoceda_ia_provider';
// Garde-fou côté client pour l'import d'un fichier audio (voir audio-import-btn) —
// aucune limite serveur dédiée aujourd'hui (AIChatAudioView), donc purement pour
// éviter d'envoyer par erreur un fichier énorme (podcast, etc.) qui prendrait un
// temps déraisonnable à transcrire pour rien.
const AUDIO_IMPORT_MAX_MB = 20;
const AUDIO_IMPORT_MAX_BYTES = AUDIO_IMPORT_MAX_MB * 1024 * 1024;

// Quota inconnu tant que l'API n'a pas répondu → on n'affiche jamais un chiffre inventé.
// activeConvId : null tant qu'aucun message n'a été envoyé dans CETTE session (nouvelle
// conversation) ; fixé à l'ouverture d'un fil depuis l'historique ou à la 1ère sauvegarde serveur.
// activeConvMessages : copie en mémoire des messages du fil actif (évite de re-fetch le
// serveur avant chaque échange ; réécrite en bloc côté serveur après chaque réponse).
const state = {
  quota: null, limite: null, quotaKnown: false, user: null, typing: false, depleted: false,
  activeConvId: null, activeConvMessages: [], modeles: [], provider: localStorage.getItem(PROVIDER_STORAGE_KEY) || 'standard',
};
const $ = id => document.getElementById(id);

/* ── Conversations : persistées côté serveur (Conversation), synchronisées entre appareils ── */
function fetchConversationList() {
  return fetchWithAuth('/api/assistant/conversations/')
    .then(res => (res.ok ? res.json() : []))
    .then(data => window.AOCEDA.asList(data))
    .catch(() => []);
}
function fetchConversation(id) {
  return fetchWithAuth('/api/assistant/conversations/' + encodeURIComponent(id) + '/')
    .then(res => (res.ok ? res.json() : null))
    .catch(() => null);
}
// Enregistre l'échange dans le fil actif : crée le fil au serveur au 1er message,
// remplace ensuite la liste complète des messages à chaque nouvel échange. `lang` :
// langue RÉELLE de la réponse assistant ('fr'/'en'/'dioula', voir finirTourIA) —
// persistée avec le message pour pouvoir reconstruire l'affichage dioula à la
// réouverture du fil (voir openConversation). Le contenu texte reste TOUJOURS le
// français, même pour une réponse dioula (relu tel quel par le LLM aux tours
// suivants) : seule cette étiquette dit qu'il faut le retraduire à l'affichage.
function saveExchangeToServer(userMsg, aiMsg, lang) {
  state.activeConvMessages.push({ role: 'user', content: userMsg });
  state.activeConvMessages.push({ role: 'assistant', content: aiMsg, lang: lang || 'fr' });

  if (!state.activeConvId) {
    return fetchWithAuth('/api/assistant/conversations/', {
      method: 'POST',
      body: JSON.stringify({ titre: userMsg.slice(0, 60), messages: state.activeConvMessages })
    })
      .then(res => (res.ok ? res.json() : null))
      .then(conv => { if (conv && conv.id) state.activeConvId = conv.id; })
      .catch(() => { /* échange déjà affiché à l'écran : un échec de sauvegarde n'est pas bloquant */ });
  }
  return fetchWithAuth('/api/assistant/conversations/' + encodeURIComponent(state.activeConvId) + '/', {
    method: 'PATCH',
    body: JSON.stringify({ messages: state.activeConvMessages })
  }).catch(() => {});
}

function nowTime() {
  const locale = (localStorage.getItem('aoceda-lang') === 'en') ? 'en-GB' : 'fr-FR';
  return new Date().toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' });
}

/* ════════════════════════════════════════════════════════════
   Voix (dictée + lecture des réponses)
   Deux moteurs possibles :
   - Pont natif Android (window.NativeSpeech, injecté par MainActivity.java
     dans l'APK) : la WebView Android n'a PAS l'API Web Speech du navigateur,
     il faut donc passer par SpeechRecognizer/TextToSpeech côté natif.
   - Web Speech API du navigateur (SpeechRecognition / speechSynthesis) sur
     le web classique (Chrome desktop/Android notamment).
   Langue de saisie (micro) et langue de réponse (texte + voix) sont DEUX
   réglages indépendants, choisis via deux boutons dédiés du composer (voir
   sttLangEntry()/ttsLangEntry() ci-dessous) — la reconnaissance vocale ne
   « détecte » pas la langue parlée, il faut la lui indiquer AVANT d'écouter.
   ════════════════════════════════════════════════════════════ */
const AUTOREAD_KEY = 'aoceda_ia_autoread';
// Langue de SAISIE et langue de RÉPONSE : deux réglages INDÉPENDANTS (deux
// boutons distincts dans le composer, voir aoceda-ia.html), chacun avec sa
// propre clé localStorage. La langue de SAISIE ne pilote QUE la grammaire
// d'écoute du micro (STT) ; la langue de RÉPONSE pilote la langue du texte ET
// de la voix de la réponse (TTS système + traduction dioula côté serveur, voir
// `lang_sortie` envoyé au serveur dans send()/sendAudioDioula()). Avant cette
// séparation, un seul sélecteur mélangeait les deux : parler français avec le
// sélecteur sur anglais faisait écouter le micro avec la mauvaise grammaire, et
// une réponse française pouvait être relue avec une voix anglaise. Ni l'un ni
// l'autre ne dépend du toggle FR/EN de l'interface (aoceda-lang, qui pilote
// Google Translate ailleurs sur le site). Français par défaut pour les deux.
// Agni/Dioula sont listés (vision produit : langues locales de Côte d'Ivoire)
// mais AUCUN moteur système (navigateur ou pont natif Android) ne supporte
// Agni aujourd'hui — bcp47:null le marque comme non fonctionnel, jamais simulé.
const STT_LANG_KEY = 'aoceda_ia_stt_lang';
const TTS_LANG_KEY = 'aoceda_ia_tts_lang';
const VOICE_LANGS = [
  { code: 'fr', label: 'Français', short: 'FR', bcp47: 'fr-FR' },
  { code: 'en', label: 'Anglais', short: 'EN', bcp47: 'en-US' },
  { code: 'agni', label: 'Agni', short: 'AG', bcp47: null },
  { code: 'dioula', label: 'Dioula', short: 'DY', bcp47: null },
];
const NATIVE_SPEECH = !!window.NativeSpeech;
const WebSpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
// Dioula : aucun moteur système (navigateur/Android) ne comprend cette langue —
// on enregistre l'AUDIO BRUT et on l'envoie au serveur (/api/assistant/chat-audio/),
// qui fait tout (compréhension + réponse + traduction + voix). Ça marche dès que
// le navigateur sait enregistrer le micro (MediaRecorder), même sans Web Speech API.
const mediaRecorderSupported = !!(navigator.mediaDevices && window.MediaRecorder);
const sttSupported = NATIVE_SPEECH || !!WebSpeechRecognition || mediaRecorderSupported;
// Lecture via la voix SYSTÈME (native Android / navigateur) : répond immédiatement,
// sans aller-retour réseau — la voix serveur (Piper, /api/assistant/tts/) sonnait
// plus humaine mais avec un temps d'attente perçu comme trop long ; la priorité a
// été remise sur la réactivité (voir meilleureVoixWeb() pour limiter le côté robotique).
const ttsSupported = NATIVE_SPEECH || !!window.speechSynthesis;

function sttLangEntry() {
  const code = localStorage.getItem(STT_LANG_KEY) || 'fr';
  return VOICE_LANGS.find(l => l.code === code) || VOICE_LANGS[0];
}
function ttsLangEntry() {
  const code = localStorage.getItem(TTS_LANG_KEY) || 'fr';
  return VOICE_LANGS.find(l => l.code === code) || VOICE_LANGS[0];
}
function isAutoRead() { return localStorage.getItem(AUTOREAD_KEY) === '1'; }

let webRecognizer = null;
let listening = false;

// Bascule l'indicateur « à l'écoute » façon Gemini : barres + texte affichés en
// surimpression du champ de saisie, ET pulsation rouge du bouton micro lui-même —
// deux signaux redondants pour que le début/la fin de l'écoute soit sans ambiguïté.
function setMicState(on) {
  listening = on;
  const btn = $('mic-btn');
  if (btn) { btn.classList.toggle('is-listening', on); btn.setAttribute('aria-pressed', String(on)); }
  const indicator = $('listening-indicator');
  if (indicator) indicator.classList.toggle('is-active', on);
  if (!on) {
    const bars = $('li-bars-wrap');
    if (bars) bars.style.transform = '';
  }
}

// Amplitude de la voix en direct (pont natif Android uniquement, via
// SpeechRecognizer.onRmsChanged côté Java) : fait « respirer » les barres avec
// le volume réel de la voix, comme l'animation d'écoute de Gemini. Le Web Speech
// API du navigateur n'expose pas ce niveau, donc sur le web les barres utilisent
// seulement leur animation CSS en boucle (déjà un signal clair de démarrage/arrêt).
window.__nativeSpeechRms = function (level) {
  const bars = $('li-bars-wrap');
  if (!bars) return;
  const v = Math.max(0, Math.min(1, (parseFloat(level) + 2) / 12));
  bars.style.transform = `scaleY(${(0.6 + v * 0.7).toFixed(2)})`;
};

// Remplit le champ de saisie avec le texte dicté — n'envoie JAMAIS automatiquement :
// une mauvaise transcription ne doit pas consommer une question du quota IA sans
// relecture par l'utilisateur.
function applyDictation(texte) {
  const ta = $('msg-input');
  if (!ta || !texte) return;
  ta.value = texte;
  autoResize();
  updateSendBtn();
  ta.focus();
}

function startListening() {
  if (!sttSupported || listening || state.typing || state.depleted) return;
  clearError();
  const entry = sttLangEntry();

  if (entry.code === 'dioula') { startRecordingDioula(); return; }
  if (entry.code === 'agni') {
    // Agni : pas encore de moteur, ni système ni serveur — honnête plutôt qu'un
    // échec silencieux ou une fausse transcription.
    showError(t('La dictée n\'est pas encore disponible en ' + entry.label + '. Choisissez Français, Anglais ou Dioula.'), false);
    return;
  }
  if (NATIVE_SPEECH) {
    setMicState(true);
    window.NativeSpeech.startListening(entry.bcp47);
    return;
  }
  webRecognizer = new WebSpeechRecognition();
  webRecognizer.lang = entry.bcp47;
  webRecognizer.interimResults = false;
  webRecognizer.maxAlternatives = 1;
  webRecognizer.onstart = () => setMicState(true);
  webRecognizer.onresult = e => applyDictation(e.results[0][0].transcript);
  webRecognizer.onerror = () => setMicState(false);
  webRecognizer.onend = () => setMicState(false);
  webRecognizer.start();
}
function stopListening() {
  if (sttLangEntry().code === 'dioula') { stopRecordingDioula(); return; }
  if (NATIVE_SPEECH) { window.NativeSpeech.stopListening(); setMicState(false); return; }
  if (webRecognizer) webRecognizer.stop();
}

/* ── Dictée DIOULA : enregistrement audio brut (web = MediaRecorder ; APK = pont
   natif NativeSpeech.startRecordingRaw/stopRecordingRaw), envoyé tel quel au
   serveur qui fait toute la compréhension + réponse + traduction + voix. ── */
let mediaRecorder = null;
let audioChunksDioula = [];

function startRecordingDioula() {
  if (NATIVE_SPEECH) {
    if (typeof window.NativeSpeech.startRecordingRaw !== 'function') {
      showError(t("La dictée dioula n'est pas disponible dans cette version de l'application."), false);
      return;
    }
    setMicState(true);
    window.NativeSpeech.startRecordingRaw();
    return;
  }
  if (!mediaRecorderSupported) {
    showError(t("L'enregistrement vocal n'est pas supporté par ce navigateur."), false);
    return;
  }
  navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
    audioChunksDioula = [];
    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = e => { if (e.data.size > 0) audioChunksDioula.push(e.data); };
    mediaRecorder.onstop = () => {
      stream.getTracks().forEach(tr => tr.stop());
      const blob = new Blob(audioChunksDioula, { type: mediaRecorder.mimeType || 'audio/webm' });
      setMicState(false);
      if (blob.size > 0) sendAudioDioula(blob);
    };
    mediaRecorder.start();
    setMicState(true);
  }).catch(() => {
    showError(t("Impossible d'accéder au micro. Vérifiez les autorisations du navigateur."), false);
  });
}
function stopRecordingDioula() {
  if (NATIVE_SPEECH) { window.NativeSpeech.stopRecordingRaw(); return; }
  if (mediaRecorder && mediaRecorder.state !== 'inactive') mediaRecorder.stop();
}

// Callback du pont natif Android : reçoit l'audio enregistré en base64 (voir
// MainActivity.java → NativeSpeechBridge.stopRecordingRaw), le convertit en
// Blob exactement comme le ferait MediaRecorder côté web, même chemin ensuite.
window.__nativeAudioRecorded = function (base64Audio, mimeType) {
  setMicState(false);
  if (!base64Audio) return;
  try {
    const binaire = atob(base64Audio);
    const octets = new Uint8Array(binaire.length);
    for (let i = 0; i < binaire.length; i++) octets[i] = binaire.charCodeAt(i);
    sendAudioDioula(new Blob([octets], { type: mimeType || 'audio/m4a' }));
  } catch (e) {
    showError(t("Échec de la lecture de l'enregistrement audio."), false);
  }
};
window.__nativeAudioError = function () {
  setMicState(false);
  showError(t("Échec de l'enregistrement audio."), false);
};

// Lecteur bilingue dioula/français : joue les segments (voir dioula.py,
// traduire_par_phrases) PHRASE PAR PHRASE, en surlignant la phrase en cours
// dans les DEUX colonnes en même temps (dioula à gauche, français à droite) —
// demandé après retour de vrais locuteurs dioula : la synthèse est un dioula
// authentique mais pas toujours facile à suivre, d'où l'intérêt de voir la
// phrase française correspondante en même temps que ce qui est en train
// d'être lu, comme des sous-titres qui avancent avec l'audio.
let audioDioulaPlayer = null;
function getAudioDioulaPlayer() { if (!audioDioulaPlayer) audioDioulaPlayer = new Audio(); return audioDioulaPlayer; }
// Incrémenté à chaque arrêt/nouvelle lecture : une suite programmée (onended)
// d'une lecture PRÉCÉDENTE se voit ainsi invalidée au lieu de continuer à
// jouer par-dessus une lecture plus récente.
let dioulaPlaybackToken = 0;

function jouerSegmentsDioula(segments, readerEl, btn) {
  const monToken = ++dioulaPlaybackToken;
  const player = getAudioDioulaPlayer();
  const rows = readerEl ? Array.from(readerEl.querySelectorAll('.dioula-reader-row')) : [];
  if (btn) btn.classList.add('is-speaking');

  const surligner = index => rows.forEach((r, idx) => r.classList.toggle('is-active', idx === index));
  const terminer = () => { if (btn) btn.classList.remove('is-speaking'); surligner(-1); };

  let i = 0;
  const jouerSuivant = () => {
    if (monToken !== dioulaPlaybackToken) return; // une lecture plus récente (ou un stop) a pris le relais
    if (i >= segments.length) { terminer(); return; }
    const seg = segments[i];
    surligner(i);
    if (!seg.audio_base64) { i++; jouerSuivant(); return; } // pas d'audio pour cette phrase : avance sans bloquer
    const binaire = atob(seg.audio_base64);
    const octets = new Uint8Array(binaire.length);
    for (let k = 0; k < binaire.length; k++) octets[k] = binaire.charCodeAt(k);
    const url = URL.createObjectURL(new Blob([octets], { type: 'audio/wav' }));
    player.src = url;
    player.onended = () => { URL.revokeObjectURL(url); i++; jouerSuivant(); };
    player.onerror = () => { URL.revokeObjectURL(url); i++; jouerSuivant(); };
    player.play().catch(() => { i++; jouerSuivant(); });
  };
  jouerSuivant();
}

// Bascule lecture/arrêt (clic sur le haut-parleur) — même convention que
// speakText()/speakTextDioula : un clic pendant la lecture l'arrête.
function toggleLectureDioulaSegments(segments, readerEl, btn) {
  const wasSpeaking = btn && btn.classList.contains('is-speaking');
  stopSpeaking();
  if (wasSpeaking) return;
  jouerSegmentsDioula(segments, readerEl, btn);
}

// Callbacks appelés par le pont natif Android (MainActivity.java → evaluateJavascript) —
// la reconnaissance/synthèse tourne côté Java, le résultat revient par ce canal.
window.__nativeSpeechResult = function (texte) { applyDictation(texte); };
window.__nativeSpeechEnd = function () { setMicState(false); };
window.__nativeSpeechError = function () { setMicState(false); };
window.__nativeSpeechTtsEnd = function () {
  document.querySelectorAll('.msg-speak-btn.is-speaking').forEach(b => b.classList.remove('is-speaking'));
};

// Texte brut à lire à voix haute : dépouille TOUT ce qu'un moteur vocal ne sait
// pas lire correctement (Markdown, liens, tableaux, émojis, sigles) et restructure
// le texte en phrases courtes pour une intonation naturelle — sans ce découpage,
// une liste à puces sonnait comme un seul bloc plat, sans pause ni respiration.
function stripForSpeech(raw) {
  let text = String(raw);

  // Blocs de code : aucun intérêt à l'oral.
  text = text.replace(/```[\s\S]*?```/g, ' ');

  // Liens Markdown [texte](url) → on garde le texte, jamais l'URL (illisible à l'oral).
  text = text.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1');
  // URLs brutes restantes → supprimées.
  text = text.replace(/https?:\/\/\S+/g, '');

  // Émojis/pictogrammes : le moteur vocal ne sait pas les lire (silence gênant
  // ou bruit parasite selon le moteur) — retirés par sécurité.
  text = text.replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/gu, '');

  // Lignes de tableau Markdown : les séparateurs purs (|---|:--:|) n'ont rien à
  // dire à l'oral et sont retirés ; les pipes des lignes de données deviennent
  // des virgules pour garder un semblant de rythme énuméré.
  text = text.split('\n')
    .filter(line => !/^[\s|:-]+$/.test(line))
    .map(line => line.replace(/\|/g, ', '))
    .join('\n');

  // Puces/numéros de liste (-, *, •, 1., 2)…) : seul le contenu compte à l'oral,
  // pas le marqueur.
  text = text.replace(/^[ \t]*(?:[-*•]|\d+[.)])[ \t]+/gm, '');

  // Titres Markdown restants, emphases, séparateurs horizontaux.
  text = text
    .replace(/^#{1,6}[ \t]+/gm, '')
    .replace(/[*_`#]/g, '')
    .replace(/^-{3,}$/gm, '');

  // Chaque ligne devient sa propre phrase (pause + intonation descendante en fin
  // de ligne), au lieu d'un enchaînement plat sans respiration entre les puces.
  text = text.split('\n').map(l => l.trim()).filter(Boolean).join('. ');

  // Sigles/abréviations qui sonnent mal lus tels quels par un moteur système :
  // « AOCEDA » en MAJUSCULES pousse beaucoup de moteurs à l'épeler lettre par
  // lettre (A-O-C-E-D-A) au lieu de le lire comme un mot — casse mixte + accent
  // force la bonne lecture. kWh/FCFA/°C sont développés pour une lecture fluide.
  // Ne change jamais le texte AFFICHÉ à l'écran, seulement ce qui est prononcé.
  text = text
    .replace(/\bAOCEDA\b/gi, 'Aocéda')
    .replace(/\bkWh\b/g, 'kilowattheures')
    .replace(/\bFCFA\b/g, 'francs CFA')
    .replace(/°C/g, ' degrés');

  // Nettoyage final : ponctuation dupliquée/mal enchaînée (« ,. », « :. », etc.)
  // et espaces multiples laissés par les remplacements ci-dessus.
  return text
    .replace(/,\s*\./g, '.')
    .replace(/:\s*\./g, ':')
    .replace(/,\s*,+/g, ',')
    .replace(/\.{2,}/g, '.')
    .replace(/\s+([.,])/g, '$1')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

function stopSpeaking() {
  document.querySelectorAll('.msg-speak-btn.is-speaking, .msg-speak-btn.is-loading').forEach(b => {
    b.classList.remove('is-speaking', 'is-loading');
  });
  // Invalide toute lecture séquentielle dioula en cours (voir jouerSegmentsDioula) —
  // sans ça, sa suite programmée (onended) continuait à jouer par-dessus.
  dioulaPlaybackToken++;
  if (audioDioulaPlayer) audioDioulaPlayer.pause();
  document.querySelectorAll('.dioula-reader-row.is-active').forEach(r => r.classList.remove('is-active'));
  if (NATIVE_SPEECH) window.NativeSpeech.stopSpeaking();
  else if (window.speechSynthesis) window.speechSynthesis.cancel();
}

// Meilleure voix système disponible pour une langue (web) : la voix par défaut
// du navigateur est souvent la plus ancienne/robotique de la liste. Priorité à
// une correspondance EXACTE de locale (fr-FR, pas fr-CA/fr-BE — un mauvais
// dialecte sonnerait tout aussi « pas français ») ; à défaut, une voix dont la
// langue correspond au moins au préfixe. Si le système n'a AUCUNE voix dans
// cette langue installée, on le signale en console plutôt que de laisser une
// voix anglaise lire du texte français en silence — ça, c'est une vraie limite
// de l'appareil/navigateur (pas un bug corrigeable côté code).
let cachedWebVoices = [];
if (window.speechSynthesis) {
  const refreshVoices = () => { cachedWebVoices = window.speechSynthesis.getVoices() || []; };
  refreshVoices();
  window.speechSynthesis.onvoiceschanged = refreshVoices;
}
function meilleureVoixWeb(bcp47) {
  const cible = bcp47.toLowerCase();
  const prefixe = cible.split('-')[0];
  const norm = l => (l || '').toLowerCase().replace('_', '-');
  const exact = cachedWebVoices.filter(v => norm(v.lang) === cible);
  const proches = cachedWebVoices.filter(v => norm(v.lang).startsWith(prefixe));
  const candidates = exact.length ? exact : proches;
  if (!candidates.length) {
    console.warn(`[Assistant IA] Aucune voix système pour '${bcp47}' sur cet appareil/navigateur — la lecture vocale utilisera la voix par défaut (accent possiblement incorrect).`);
    return null;
  }
  const scoreVoix = v => /natural|neural|online|wavenet|studio/i.test(v.name) ? 2
    : /google/i.test(v.name) ? 1 : 0;
  candidates.sort((a, b) => scoreVoix(b) - scoreVoix(a));
  return candidates[0];
}

// Clic sur le haut-parleur d'un message : lit ce message, ou l'arrête s'il est
// déjà en cours de lecture (un seul message lu à la fois). Voix SYSTÈME
// (native Android / navigateur) — répond immédiatement, sans aller-retour
// réseau. On choisit la meilleure voix disponible et un débit un peu plus
// lent/posé pour limiter le côté robotique, sans sacrifier la réactivité.
// `langCode` : langue RÉELLEMENT utilisée pour CE message, figée au moment de
// l'envoi (voir appendMessage/finirTourIA) — jamais le sélecteur de langue de
// réponse COURANT, qui a pu changer depuis. Bug corrigé : avant, relire un
// vieux message français après avoir basculé le sélecteur sur anglais le
// relisait avec une voix anglaise (mauvaise prononciation).
function speakText(text, btn, langCode) {
  const wasActive = btn && (btn.classList.contains('is-speaking') || btn.classList.contains('is-loading'));
  stopSpeaking();
  if (wasActive) return;
  const entry = VOICE_LANGS.find(l => l.code === langCode) || ttsLangEntry();
  // Dioula : pas de voix système, traduction + audio à la demande côté serveur
  // (message stampé 'dioula' sans audio pré-généré — cas rare, voir appendMessage).
  if (entry.code === 'dioula') { speakTextDioula(text, btn); return; }
  if (!entry.bcp47) {
    showError(t('La lecture vocale n\'est pas encore disponible en ' + entry.label + '. Choisissez Français ou Anglais.'), false);
    return;
  }
  const clean = stripForSpeech(text);
  if (!clean) return;
  if (btn) btn.classList.add('is-speaking');

  if (NATIVE_SPEECH) {
    window.NativeSpeech.speak(clean, entry.bcp47);
  } else if (window.speechSynthesis) {
    const utt = new SpeechSynthesisUtterance(clean);
    utt.lang = entry.bcp47;
    // 0.94 sonnait traînant ; 1.05 (un peu plus rapide que la vitesse "neutre" 1.0)
    // donne un débit plus vif, plus proche d'une vraie conversation.
    utt.rate = 1.05;
    const voix = meilleureVoixWeb(entry.bcp47);
    if (voix) utt.voice = voix;
    utt.onend = () => { if (btn) btn.classList.remove('is-speaking'); };
    utt.onerror = () => { if (btn) btn.classList.remove('is-speaking'); };
    window.speechSynthesis.speak(utt);
  } else if (btn) {
    btn.classList.remove('is-speaking');
  }
}

// Traduction + voix dioula À LA DEMANDE (clic sur le haut-parleur) : contrairement
// aux nouvelles réponses (traduites proactivement, voir finirTourIA), un ancien
// message n'a pas d'audio prêt d'avance — on l'appelle ici, une seule fois.
function speakTextDioula(text, btn) {
  const clean = stripForSpeech(text);
  if (!clean) return;
  if (btn) btn.classList.add('is-loading');
  fetchWithAuth('/api/assistant/translate-dioula/', {
    method: 'POST',
    body: JSON.stringify({ text: clean }),
  })
    .then(res => res.json().catch(() => ({})))
    .then(data => {
      if (btn) btn.classList.remove('is-loading');
      const segments = Array.isArray(data.dioula_segments) ? data.dioula_segments : [];
      if (segments.some(s => s.audio_base64)) {
        // Pas de lecteur bilingue ici (message déjà affiché sans, voir appendMessage) :
        // lecture simple, readerEl=null → pas de surlignage à faire avancer.
        jouerSegmentsDioula(segments, null, btn);
      } else {
        showError(t('La lecture en dioula a échoué.'), false);
      }
    })
    .catch(() => {
      if (btn) btn.classList.remove('is-loading');
      showError(t('La lecture en dioula a échoué.'), false);
    });
}

/* Rendu Markdown → HTML des réponses de l'assistant. Couvre le sous-ensemble que
   les LLM produisent réellement : gras, code inline, blocs de code, listes à puces
   ET numérotées (vrais <ol>), titres ###, séparateurs ---, et TABLEAUX |…|…| —
   sans quoi les tableaux s'affichaient en pipes bruts (rendu « cassé » constaté). */
function renderMsgText(raw) {
  const text = String(raw);

  // 1) Blocs de code (``` ... ```), traités AVANT toute ligne
  const CODE_BLOCKS = [];
  const withoutCodeBlocks = text.replace(/```[\w]*\n?([\s\S]*?)```/g, (_, code) => {
    const idx = CODE_BLOCKS.length;
    CODE_BLOCKS.push(`<pre class="msg-code"><code>${esc(code.trim())}</code></pre>`);
    return `\x00CODE${idx}\x00`;
  });

  // 2) Traitement ligne par ligne
  const lines = withoutCodeBlocks.split('\n');
  const parts = [];
  let listItems = [];   // liste à puces en cours
  let olItems = [];     // liste numérotée en cours
  let tableRows = [];   // lignes |…| du tableau en cours

  const flushList = () => {
    if (listItems.length) {
      parts.push(`<ul class="msg-list">${listItems.map(i => `<li>${i}</li>`).join('')}</ul>`);
      listItems = [];
    }
  };
  const flushOl = () => {
    if (olItems.length) {
      parts.push(`<ol class="msg-list">${olItems.map(i => `<li>${i}</li>`).join('')}</ol>`);
      olItems = [];
    }
  };
  const flushTable = () => {
    if (!tableRows.length) return;
    // Écarte les lignes séparatrices (|---|:--:|…) — pur balisage Markdown
    const rows = tableRows.filter(cells => !cells.every(c => /^:?-{2,}:?$/.test(c) || c === ''));
    tableRows = [];
    if (!rows.length) return;
    const head = `<tr>${rows[0].map(c => `<th>${c}</th>`).join('')}</tr>`;
    const body = rows.slice(1).map(r => `<tr>${r.map(c => `<td>${c}</td>`).join('')}</tr>`).join('');
    parts.push(`<div class="msg-table-wrap"><table class="msg-table"><thead>${head}</thead>` +
               (body ? `<tbody>${body}</tbody>` : '') + `</table></div>`);
  };
  const flushAll = () => { flushList(); flushOl(); flushTable(); };

  const inlineFormat = line => esc(line)
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')        // **gras**
    .replace(/`([^`]+)`/g, '<code class="msg-inline-code">$1</code>'); // `code`

  lines.forEach(line => {
    const trimmed = line.trim();
    // Marqueur de bloc de code → réinjecter
    if (/^\x00CODE\d+\x00$/.test(trimmed)) {
      flushAll();
      const idx = parseInt(trimmed.replace(/\x00CODE(\d+)\x00/, '$1'), 10);
      parts.push(CODE_BLOCKS[idx] || '');
      return;
    }
    if (!trimmed) {
      flushAll();
      return; // ligne vide : ferme liste/tableau éventuels, pas de <br> superflu
    }
    // Ligne de tableau |…|…| : accumulée puis rendue d'un bloc
    if (/^\|.*\|$/.test(trimmed)) {
      flushList(); flushOl();
      tableRows.push(trimmed.slice(1, -1).split('|').map(c => inlineFormat(c.trim())));
      return;
    }
    flushTable(); // toute ligne non-| clôt le tableau en cours
    // Séparateur horizontal (---, ***, ___)
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
      flushAll();
      parts.push('<hr class="msg-hr">');
      return;
    }
    // Titre Markdown (# à ####) → intertitre visuel
    const h = trimmed.match(/^#{1,4}\s+(.+)/);
    if (h) {
      flushAll();
      parts.push(`<p class="msg-heading">${inlineFormat(h[1])}</p>`);
      return;
    }
    // Liste à tirets (- item) ou liste à puces (* item)
    const listMatch = line.match(/^\s*[-*]\s+(.+)/);
    if (listMatch) {
      flushOl();
      listItems.push(inlineFormat(listMatch[1]));
      return;
    }
    // Liste numérotée (1. item / 2) item) → vrai <ol> (la numérotation était perdue avant)
    const numMatch = line.match(/^\s*\d+[.)]\s+(.+)/);
    if (numMatch) {
      flushList();
      olItems.push(inlineFormat(numMatch[1]));
      return;
    }
    // Paragraphe normal
    flushAll();
    parts.push(`<p>${inlineFormat(line)}</p>`);
  });

  flushAll();
  return parts.join('');
}

/* ── Thème ── */
function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  $('theme-toggle').innerHTML = theme === 'light' ? MOON_SVG : SUN_SVG;
}

/* ── Quota (pied de saisie) ── */
function renderQuota() {
  const inline = $('quota-inline');
  if (!inline) return;
  if (!state.quotaKnown) {
    inline.textContent = t('Quota du jour…');
    inline.classList.remove('is-low');
    return;
  }
  const lang = localStorage.getItem('aoceda-lang');
  // limite === null → aucune limite quotidienne active côté serveur (illimité).
  if (state.limite == null) {
    inline.textContent = lang === 'en' ? t('Unlimited questions today') : t("Questions illimitées aujourd'hui");
    inline.classList.remove('is-low');
    return;
  }
  const q = state.quota;
  const s = q > 1 ? 's' : '';
  if (lang === 'en') {
    inline.textContent = `${q} question${s} remaining today`;
  } else {
    inline.textContent = `${q} question${s} restante${s} aujourd'hui`;
  }
  inline.classList.toggle('is-low', q <= 2);
}

function renderDepleted() {
  const sug = $('suggestions');
  if (sug) sug.style.display = state.depleted ? 'none' : '';
  $('input-bar').style.display = state.depleted ? 'none' : '';
  $('quota-empty').style.display = state.depleted ? '' : 'none';
  // Numéros du bandeau « limite atteinte » = vraie limite serveur (jamais « 10 » en dur)
  if (state.depleted && state.limite != null) {
    ['qe-lim1', 'qe-lim2', 'qe-lim3'].forEach(id => { const el = $(id); if (el) el.textContent = state.limite; });
  }
}

/* ── Messages ── */
function userInitials() {
  return state.user && state.user.nom ? state.user.nom.substring(0, 2).toUpperCase() : '··';
}
function scrollToEnd() {
  const end = $('messages-end');
  if (end && end.scrollIntoView) end.scrollIntoView({ behavior: 'smooth' });
}
// Lecteur bilingue 2 colonnes (dioula à gauche, français à droite, une ligne
// par phrase) — demandé après retour de vrais locuteurs dioula : la synthèse
// est un dioula authentique mais pas toujours facile à suivre, donc afficher
// la phrase française en vis-à-vis aide à vérifier ce qui est réellement dit.
// Empilé verticalement sur petit écran (voir ia.css), côte à côte sur grand écran.
function buildDioulaReaderHTML(segments) {
  const lignes = segments.map((s, i) => `
    <div class="dioula-reader-row" data-index="${i}">
      <div class="dioula-col dioula-col-dy">${esc(s.dioula || t('(indisponible)'))}</div>
      <div class="dioula-col dioula-col-fr">${esc(s.fr)}</div>
    </div>`).join('');
  return `<div class="dioula-reader">${lignes}</div>`;
}

// dioulaInfo : { segments: [{fr, dioula, audio_base64}, ...], frenchText } SI ce
// message est une réponse dioula, sinon null/undefined. lang : langue RÉELLE de
// CE message ('fr'/'en'/'dioula'), figée au moment de l'envoi (voir
// finirTourIA). Une fois posés ici, dioulaInfo ET lang sont FIGÉS pour ce
// message — un changement ultérieur du sélecteur de langue de réponse ne doit
// JAMAIS changer comment CE message précis se relit au clic sur son
// haut-parleur. Bug corrigé (dioula) : avant, un message dioula sans audio
// pré-généré retombait sur speakText(), qui relisait la langue COURANTE du
// sélecteur au moment du clic — si l'utilisateur avait entre-temps changé de
// langue, cliquer sur l'ancien message essayait de le lire avec la mauvaise
// voix. Même correction généralisée aux messages français/anglais (avant,
// SEUL le cas dioula était figé par message).
// audioUrl : message vocal de l'UTILISATEUR (dictée dioula) — lecteur audio
// écoutable affiché à la place du texte, IMMÉDIATEMENT après l'enregistrement
// (voir sendAudioDioula), sans attendre la transcription (qui arrive après tout
// le traitement serveur, ~20-30s, et reste imparfaite). Voir
// ajouterLegendeTranscription() pour l'ajout de la légende une fois connue.
function appendMessage(role, text, time, dioulaInfo, lang, audioUrl) {
  const row = document.createElement('div');
  row.className = `msg-row ${role}`;
  if (role === 'ai') row.dataset.lang = lang || 'fr';
  const avatar = role === 'ai' ? logoSVG(15) : esc(userInitials());
  const who = role === 'ai' ? t('Assistant AOCEDA') : t('Vous');
  const speakBtn = (role === 'ai' && (ttsSupported || dioulaInfo))
    ? `<button type="button" class="msg-speak-btn" aria-label="${esc(t('Écouter cette réponse'))}" title="${esc(t('Écouter cette réponse'))}">${SPEAKER_SVG}</button>`
    : '';
  const hasSegments = !!(dioulaInfo && dioulaInfo.segments && dioulaInfo.segments.length);
  const contenuBulle = audioUrl
    ? `<audio controls src="${esc(audioUrl)}" class="msg-audio-player"></audio><div class="msg-audio-caption" hidden></div>`
    : (hasSegments ? buildDioulaReaderHTML(dioulaInfo.segments) : renderMsgText(text));
  row.innerHTML = `<div class="msg-avatar ${role === 'ai' ? 'av-ai' : 'av-user'}">${avatar}</div>
    <div class="msg-col">
      <div class="msg-bubble ${role}${hasSegments ? ' msg-bubble-dioula' : ''}${audioUrl ? ' msg-bubble-audio' : ''}">${contenuBulle}</div>
      <div class="msg-time ${role === 'ai' ? 'ai-t' : ''}">${who}${time ? ' · ' + esc(time) : ''}${speakBtn}</div>
    </div>`;
  $('messages').insertBefore(row, $('messages-end'));
  if (role === 'ai') {
    const btn = row.querySelector('.msg-speak-btn');
    if (btn) {
      if (dioulaInfo) {
        btn.addEventListener('click', () => {
          if (hasSegments) toggleLectureDioulaSegments(dioulaInfo.segments, row.querySelector('.dioula-reader'), btn);
          else speakTextDioula(dioulaInfo.frenchText || text, btn); // pas de segment du tout : re-synthèse complète à la demande
        });
      } else {
        btn.addEventListener('click', () => speakText(text, btn, row.dataset.lang));
      }
    }
  }
  scrollToEnd();
  return row;
}

// Ajoute la transcription automatique (dictée dioula) en LÉGENDE sous le lecteur
// audio de l'utilisateur, une fois connue (elle arrive après tout le traitement
// serveur) — ne remplace JAMAIS le lecteur : la transcription reste imparfaite,
// le vrai message que l'utilisateur a envoyé est l'audio lui-même.
function ajouterLegendeTranscription(row, transcription) {
  const caption = row && row.querySelector('.msg-audio-caption');
  if (!caption || !transcription) return;
  caption.textContent = transcription;
  caption.hidden = false;
}

// 4 étapes affichées À TOUR DE RÔLE sous les points « en train d'écrire » — façon
// Gemini/Claude, pour savoir où en est le traitement plutôt qu'une simple
// animation sans information. PUREMENT indicatif (calé sur la durée typique de
// chaque pipeline, voir le rythme dans setTyping) : la vraie réponse peut
// arriver à n'importe quelle étape, jamais une fausse barre de progression.
const ETAPES_TEXTE = [
  'Réflexion…',
  'Analyse de votre question…',
  'Consultation de vos données…',
  'Rédaction de la réponse…',
];
const ETAPES_DIOULA = [
  'Transcription de votre message…',
  'Réflexion…',
  'Consultation de vos données…',
  'Traduction en dioula…',
];
let typingEtapesTimer = null;

// etapes : tableau de 4 étapes RAW (non traduites, voir ETAPES_TEXTE/ETAPES_DIOULA
// — traduites ici via t() au moment de l'affichage, jamais par l'appelant), ou
// rien (→ ETAPES_TEXTE par défaut, seul cas courant).
function setTyping(on, etapes) {
  state.typing = on;
  const existing = $('typing-row');
  if (typingEtapesTimer) { clearInterval(typingEtapesTimer); typingEtapesTimer = null; }

  if (on && !existing) {
    const row = document.createElement('div');
    row.className = 'typing-row';
    row.id = 'typing-row';
    const liste = Array.isArray(etapes) ? etapes : ETAPES_TEXTE;
    row.innerHTML = `<div class="msg-avatar av-ai">${logoSVG(16)}</div>
      <div class="msg-col">
        <div class="typing-bubble"><div class="tydot"></div><div class="tydot"></div><div class="tydot"></div></div>
        <div class="typing-hint" id="typing-hint">${esc(t(liste[0]))}</div>
      </div>`;
    $('messages').insertBefore(row, $('messages-end'));
    scrollToEnd();

    if (liste.length > 1) {
      // Rythme calé sur la durée réelle mesurée de chaque pipeline : ~20-30s pour
      // le dioula vocal (STT + LLM + traduction, voir sendAudioDioula) contre
      // quelques secondes pour une question texte classique.
      const rythmeMs = liste === ETAPES_DIOULA ? 6000 : 1800;
      let i = 0;
      typingEtapesTimer = setInterval(() => {
        i = Math.min(i + 1, liste.length - 1); // reste sur la dernière étape si ça prend plus longtemps que prévu
        const hintEl = $('typing-hint');
        if (hintEl) hintEl.textContent = t(liste[i]);
      }, rythmeMs);
    }
  } else if (!on && existing) {
    existing.remove();
  }
  updateSendBtn();
}

function updateSendBtn() {
  const btn = $('send-btn');
  btn.disabled = !$('msg-input').value.trim() || state.typing;
  btn.classList.toggle('is-sending', state.typing);
  btn.setAttribute('aria-label', state.typing ? t('Envoi en cours…') : t('Envoyer le message'));
}

/* ── Bannière d'erreur (gérée hors du fil de messages) ── */
/* isNetwork=true → « Connexion interrompue » (échec réseau) ; sinon on affiche le
   message applicatif tel quel (ex. un 403 « réservé aux clients » n'est pas une coupure). */
function showError(msg, isNetwork) {
  const box = $('chat-error');
  const txt = $('chat-error-text');
  if (txt) txt.innerHTML = isNetwork ? `<strong>${t('Connexion interrompue.')}</strong> ${esc(msg)}` : esc(msg);
  if (box) box.style.display = 'flex';
}

/* Note discrète « Données consultées : … » sous la DERNIÈRE réponse de l'assistant :
   trace honnête des lectures réellement faites par l'IA via les outils serveur
   (function calling) — labels FR renvoyés par l'API dans `outils_utilises`. */
function appendSourcesNote(labels) {
  const rows = document.querySelectorAll('#messages .msg-row.ai');
  const last = rows[rows.length - 1];
  const col = last ? last.querySelector('.msg-col') : null;
  if (!col) return;
  const el = document.createElement('div');
  el.className = 'msg-sources';
  el.textContent = t('Données consultées :') + ' ' + labels.join(', ');
  col.appendChild(el);
}

/* Indicateur « mode dégradé » : signale honnêtement quand la réponse vient des
   conseils locaux (pas d'un vrai LLM). Affiché une seule fois, discret. */
function showFallbackNotice() {
  if (document.getElementById('ia-mode-notice')) return;
  const anchor = $('messages-end');
  if (!anchor || !anchor.parentNode) return;
  const el = document.createElement('div');
  el.id = 'ia-mode-notice';
  el.style.cssText = 'margin:8px auto;max-width:640px;font-size:12px;color:var(--tx-m);text-align:center;font-style:italic';
  el.textContent = t('Conseils basés sur vos données réelles et la grille CIE (assistant IA avancé non configuré).');
  anchor.parentNode.insertBefore(el, anchor);
}
function clearError() {
  const box = $('chat-error');
  if (box) box.style.display = 'none';
}
function autoResize() {
  const t = $('msg-input');
  t.style.height = 'auto';
  t.style.height = Math.min(t.scrollHeight, 120) + 'px';
}

// Termine un tour de conversation IA (affichage + audio + notes + sauvegarde +
// fin du « en train d'écrire ») — partagé entre le chat texte et le chat vocal
// dioula pour ne pas dupliquer cette logique en deux endroits divergents.
// dioulaInfo : { segments: [{fr, dioula, audio_base64}, ...], frenchText } si CE
// tour est une réponse dioula (figé définitivement sur ce message, voir
// appendMessage), sinon null. lang : langue RÉELLE de la réponse ('fr'/'en'
// pour un message normal, 'dioula' pour un message dioula), figée par
// l'appelant AU MOMENT DE L'ENVOI (voir send()/sendAudioDioula()).
function finirTourIA(historyLabel, data, texteAffiche, dioulaInfo, lang) {
  const row = appendMessage('ai', texteAffiche, nowTime(), dioulaInfo || null, lang);
  const hasAudio = dioulaInfo && dioulaInfo.segments && dioulaInfo.segments.some(s => s.audio_base64);
  if (hasAudio) {
    const btn = row && row.querySelector('.msg-speak-btn');
    const readerEl = row && row.querySelector('.dioula-reader');
    if (btn) jouerSegmentsDioula(dioulaInfo.segments, readerEl, btn); // lecture automatique, comme une vraie conversation vocale
  } else if (!dioulaInfo && isAutoRead()) {
    const btns = document.querySelectorAll('#messages .msg-row.ai .msg-speak-btn');
    const lastBtn = btns[btns.length - 1];
    if (lastBtn) speakText(texteAffiche, lastBtn, lang);
  }
  if (Array.isArray(data.outils_utilises) && data.outils_utilises.length) {
    appendSourcesNote(data.outils_utilises);
  }
  if (data.mode === 'fallback') showFallbackNotice();
  saveExchangeToServer(historyLabel, data.response, dioulaInfo ? 'dioula' : lang);
  setTyping(false);
}

function send(txt) {
  if (!txt || !txt.trim() || state.typing || state.depleted) return;
  clearError();
  const emptyState = $('chat-empty');
  if (emptyState) emptyState.remove();
  const messageText = txt.trim();
  // Figée MAINTENANT, pas relue dans le .then() ci-dessous : une réponse dioula peut
  // prendre plusieurs secondes, et si l'utilisateur change la langue de RÉPONSE
  // pendant l'attente, la réponse À CETTE question doit rester dans la langue
  // choisie au moment de l'envoi (bug corrigé : elle suivait la langue au moment
  // de la RÉPONSE, pas de la question). Indépendante de la langue de SAISIE
  // (sttLangEntry) — voir la séparation des deux sélecteurs plus haut.
  const langueSortieChoisie = ttsLangEntry().code;
  appendMessage('user', messageText, nowTime());
  const ta = $('msg-input');
  ta.value = '';
  ta.style.height = 'auto';
  updateSendBtn();
  setTyping(true);

  // Historique du fil actif (AVANT d'y ajouter ce message) : envoyé au serveur
  // seulement pour construire le contexte de CET appel au LLM.
  const historyPourServeur = state.activeConvMessages
    .slice(-HISTORIQUE_ENVOI_MAX)
    .map(m => ({ role: m.role, content: m.content }));

  fetchWithAuth('/api/assistant/chat/', {
    method: 'POST',
    body: JSON.stringify({
      message: messageText,
      lang: localStorage.getItem('aoceda-lang') || 'fr',
      lang_sortie: langueSortieChoisie,
      history: historyPourServeur,
      provider: state.provider,
    })
  })
    .then(async res => {
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        if (res.status === 429) { state.depleted = true; renderDepleted(); }
        const e = new Error(data.detail || t('Une erreur est survenue.'));
        e.apiError = true; // erreur applicative (corps JSON), pas une coupure réseau
        throw e;
      }
      return data;
    })
    .then(data => {
      // limite_quotidienne peut être `null` (illimité) : on la reflète telle quelle,
      // sans jamais retomber sur 0 (qui afficherait à tort "quota épuisé").
      state.limite = (data.limite_quotidienne === undefined) ? state.limite : data.limite_quotidienne;
      if (state.limite == null) {
        state.quota = Infinity;
        state.depleted = false;
      } else {
        state.quota = Math.max(0, state.limite - (data.nb_requetes_aujourd_hui || 0));
        state.depleted = state.quota <= 0;
      }
      state.quotaKnown = true;
      renderQuota();
      renderDepleted();

      // Langue de réponse = dioula (choisie AU MOMENT DE L'ENVOI, voir
      // langueSortieChoisie) : TOUTE réponse doit sortir en dioula, pas
      // seulement la dictée vocale — même en tapant du texte, on traduit avant
      // d'afficher (le LLM a déjà répondu en français, voir lang_sortie côté
      // serveur : LAMIA ne traduit fiablement QUE depuis le français).
      if (langueSortieChoisie === 'dioula') {
        fetchWithAuth('/api/assistant/translate-dioula/', {
          method: 'POST',
          body: JSON.stringify({ text: data.response }),
        })
          .then(res => res.json().catch(() => ({})))
          .then(td => {
            const segments = Array.isArray(td.dioula_segments) ? td.dioula_segments : [];
            if (!segments.length) {
              showError(t('La traduction en dioula a échoué — réponse affichée en français.'), false);
              finirTourIA(messageText, data, data.response, null, 'fr');
              return;
            }
            finirTourIA(messageText, data, td.response_dioula || data.response, { segments, frenchText: data.response }, 'dioula');
          })
          .catch(() => finirTourIA(messageText, data, data.response, null, 'fr'));
        return;
      }

      finirTourIA(messageText, data, data.response, null, langueSortieChoisie);
    })
    .catch(err => {
      setTyping(false);
      // Quota épuisé : la bannière de quota suffit, pas d'erreur en doublon.
      if (state.depleted) return;
      // Erreur applicative (4xx) → message tel quel ; erreur réseau → « Connexion interrompue ».
      showError(err.apiError ? err.message : `${err.message} ${t('Réessayez dans un instant.')}`, !err.apiError);
    });
}

// Envoi d'une dictée DIOULA (audio brut, pas de texte) : /api/assistant/chat-audio/
// fait TOUT côté serveur (compréhension + réponse + traduction + voix, voir
// AIChatAudioView). Le message vocal de l'utilisateur s'affiche IMMÉDIATEMENT
// (lecteur audio écoutable, voir appendMessage) — il n'attend plus la
// transcription (qui arrive après tout le traitement, ~20-30s, et reste
// imparfaite) ; elle est ajoutée en légende sous le lecteur une fois connue
// (voir ajouterLegendeTranscription).
function sendAudioDioula(blob) {
  if (state.typing || state.depleted) return;
  clearError();
  const emptyState = $('chat-empty');
  if (emptyState) emptyState.remove();

  const audioUrl = URL.createObjectURL(blob);
  const userRow = appendMessage('user', '', nowTime(), null, null, audioUrl);

  // 4 étapes défilantes (transcription -> réflexion -> données -> traduction) —
  // voir ETAPES_DIOULA/setTyping : donne une vraie idée de la progression sur un
  // pipeline long (~20-30s mesurés en test réel) au lieu d'une attente opaque.
  setTyping(true, ETAPES_DIOULA);

  // Figée MAINTENANT (avant l'attente, potentiellement longue) — même principe
  // que dans send() : la langue de RÉPONSE de CET échange ne doit jamais suivre
  // un changement de sélecteur pendant le traitement. La langue de SAISIE est
  // forcément dioula ici (seule langue sans moteur système passant par cette
  // fonction, voir startListening()) ; la langue de RÉPONSE reste un choix
  // indépendant : 'dioula' (comportement d'origine) traduit la réponse via
  // LAMIA, 'fr'/'en' l'affiche telle quelle (voir lang_sortie côté serveur).
  const langueSortieChoisie = ttsLangEntry().code;

  const historyPourServeur = state.activeConvMessages
    .slice(-HISTORIQUE_ENVOI_MAX)
    .map(m => ({ role: m.role, content: m.content }));

  const formData = new FormData();
  formData.append('audio', blob, 'dictee.webm');
  formData.append('history', JSON.stringify(historyPourServeur));
  formData.append('provider', state.provider);
  formData.append('lang_sortie', langueSortieChoisie);

  fetchWithAuth('/api/assistant/chat-audio/', { method: 'POST', body: formData })
    .then(async res => {
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        if (res.status === 429) { state.depleted = true; renderDepleted(); }
        const e = new Error(data.detail || t('Une erreur est survenue.'));
        e.apiError = true;
        throw e;
      }
      return data;
    })
    .then(data => {
      state.limite = (data.limite_quotidienne === undefined) ? state.limite : data.limite_quotidienne;
      if (state.limite == null) {
        state.quota = Infinity;
        state.depleted = false;
      } else {
        state.quota = Math.max(0, state.limite - (data.nb_requetes_aujourd_hui || 0));
        state.depleted = state.quota <= 0;
      }
      state.quotaKnown = true;
      renderQuota();
      renderDepleted();

      // Légende de transcription ajoutée sous le lecteur audio DÉJÀ affiché
      // (voir userRow, posé avant l'envoi) — jamais un nouveau message.
      ajouterLegendeTranscription(userRow, data.transcription_dioula);
      // Historique : le texte réellement affiché en interne, cohérent avec le
      // reste du fil (relu tel quel par le LLM aux tours suivants).
      const historyLabel = t('[Message vocal en dioula] ') + (data.transcription_dioula || '');
      const segments = Array.isArray(data.dioula_segments) ? data.dioula_segments : [];
      if (segments.length) {
        // Langue de réponse = dioula, traduction réussie : lecteur bilingue habituel.
        finirTourIA(historyLabel, data, data.response_dioula || data.response, { segments, frenchText: data.response }, 'dioula');
      } else if (langueSortieChoisie === 'dioula') {
        // Langue de réponse = dioula MAIS la traduction a échoué (LAMIA
        // indisponible) : repli honnête sur le français déjà généré, jamais un
        // vide (voir apps.ai_assistant.dioula.traduire_par_phrases).
        showError(t('La traduction en dioula a échoué — réponse affichée en français.'), false);
        finirTourIA(historyLabel, data, data.response, null, 'fr');
      } else {
        // Langue de réponse fr/en choisie explicitement : le serveur répond déjà
        // dans la bonne langue (voir lang_sortie), pas de traduction à faire ici.
        finirTourIA(historyLabel, data, data.response, null, langueSortieChoisie);
      }
    })
    .catch(err => {
      setTyping(false);
      if (state.depleted) return;
      showError(err.apiError ? err.message : `${err.message} ${t('Réessayez dans un instant.')}`, !err.apiError);
    });
}

/* ── Panneau « Historique des conversations » (synchronisé via le compte, serveur) ── */
function startNewConversation() {
  state.activeConvId = null;
  state.activeConvMessages = [];
  clearError();
  const box = $('messages');
  if (box) {
    box.querySelectorAll('.msg-row, .typing-row, #ia-mode-notice').forEach(el => el.remove());
    let emptyState = $('chat-empty');
    if (!emptyState) {
      // Reconstruit le bloc d'accueil minimal si un envoi l'avait retiré du DOM.
      emptyState = document.createElement('div');
      emptyState.id = 'chat-empty';
      emptyState.className = 'chat-empty';
      emptyState.innerHTML = `<h2 class="ce-title">${esc(t("Bonjour, l'Assistant AOCEDA vous écoute"))}</h2>
        <p class="ce-sub">${esc(t('Posez vos questions sur votre consommation, votre facture CIE ou vos appareils.'))}</p>
        <div id="suggestions" class="ce-chips"></div>`;
      box.insertBefore(emptyState, $('messages-end'));
      renderSuggestions();
    }
  }
  closeHistory();
}

function openHistory() {
  const panel = $('conv-history');
  if (panel) panel.hidden = false;
  const list = $('conv-history-list');
  if (list) list.innerHTML = `<div class="conv-history-empty">${esc(t('Chargement…'))}</div>`;
  renderConvHistoryList();
}
function closeHistory() {
  const panel = $('conv-history');
  if (panel) panel.hidden = true;
}

function renderConvHistoryList() {
  const list = $('conv-history-list');
  if (!list) return;
  fetchConversationList().then(items => {
    if (!items.length) {
      list.innerHTML = `<div class="conv-history-empty">${esc(t('Aucune conversation précédente.'))}</div>`;
      return;
    }
    const lang = localStorage.getItem('aoceda-lang');
    list.innerHTML = items.map(c => {
      const date = new Date(c.updated_at).toLocaleDateString(lang === 'en' ? 'en-GB' : 'fr-FR', { day: '2-digit', month: 'short' });
      return `<button type="button" class="conv-item${c.id === state.activeConvId ? ' active' : ''}" data-id="${esc(c.id)}">
        <div class="conv-item-titre">${esc(c.titre || t('Nouvelle conversation'))}</div>
        ${c.apercu ? `<div class="conv-item-apercu">${esc(c.apercu)}</div>` : ''}
        <div class="conv-item-date">${esc(date)}</div>
      </button>`;
    }).join('');
  });
}

// Un message assistant persisté avec lang='dioula' (voir saveExchangeToServer)
// n'a PAS son texte/audio dioula stockés tels quels — le serveur ne garde que le
// français (relu tel quel par le LLM aux tours suivants). On le retraduit donc à
// la demande via le MÊME endpoint que speakTextDioula (aucun nouveau stockage
// nécessaire, la traduction est déterministe et ne coûte pas de quota IA). Bug
// corrigé : avant, rouvrir un fil (ex. après déconnexion/reconnexion) perdait le
// champ lang à la sauvegarde (voir ConversationSerializer.validate_messages) et
// réaffichait TOUJOURS le français, même pour un échange qui était sorti en
// dioula au moment de l'envoi.
function retraduireMessageDioula(texteFrancais) {
  return fetchWithAuth('/api/assistant/translate-dioula/', {
    method: 'POST',
    body: JSON.stringify({ text: texteFrancais }),
  })
    .then(res => res.json().catch(() => ({})))
    .then(td => {
      const segments = Array.isArray(td.dioula_segments) ? td.dioula_segments : [];
      return segments.length ? { segments, frenchText: texteFrancais } : null;
    })
    .catch(() => null); // échec réseau : repli sur l'affichage français, jamais bloquant
}

// Met À NIVEAU un message DÉJÀ affiché (texte français, voir openConversation) vers
// le lecteur bilingue dioula, dès que SA retraduction arrive — jamais groupé avec
// les autres messages du fil. Bug corrigé : un Promise.all() sur TOUTES les
// retraductions du fil bloquait l'affichage de TOUT l'historique (y compris les
// messages français/anglais qui n'ont besoin d'aucun appel réseau) tant que la
// PLUS LENTE des traductions LAMIA n'était pas terminée — un fil avec plusieurs
// échanges dioula, ou un seul appel LAMIA lent/bloqué, faisait croire que
// « l'historique ne s'affiche plus ». `row.isConnected` évite de mettre à jour une
// ligne d'un fil qu'on a entre-temps quitté (l'utilisateur a ouvert un autre fil
// pendant que cette retraduction était en cours).
function upgradeMessageDioula(row, texteFrancais) {
  retraduireMessageDioula(texteFrancais).then(dioulaInfo => {
    if (!dioulaInfo || !row || !row.isConnected) return;
    row.dataset.lang = 'dioula';
    const bubble = row.querySelector('.msg-bubble');
    if (bubble) {
      bubble.classList.add('msg-bubble-dioula');
      bubble.innerHTML = buildDioulaReaderHTML(dioulaInfo.segments);
    }
    // Le bouton haut-parleur peut ne PAS exister encore (pas de TTS système sur cet
    // appareil et pas encore de dioulaInfo au moment du 1er rendu, voir
    // appendMessage) — créé ici si besoin, sinon juste réattaché au lecteur dioula.
    let speakBtn = row.querySelector('.msg-speak-btn');
    if (!speakBtn) {
      const timeEl = row.querySelector('.msg-time');
      if (timeEl) {
        timeEl.insertAdjacentHTML('beforeend',
          `<button type="button" class="msg-speak-btn" aria-label="${esc(t('Écouter cette réponse'))}" title="${esc(t('Écouter cette réponse'))}">${SPEAKER_SVG}</button>`);
        speakBtn = row.querySelector('.msg-speak-btn');
      }
    }
    if (speakBtn) {
      const propre = speakBtn.cloneNode(true); // retire l'éventuel handler texte simple posé au 1er rendu
      speakBtn.replaceWith(propre);
      propre.addEventListener('click', () => toggleLectureDioulaSegments(dioulaInfo.segments, row.querySelector('.dioula-reader'), propre));
    }
  });
}

function openConversation(id) {
  fetchConversation(id).then(conv => {
    if (!conv) return;
    state.activeConvId = conv.id;
    state.activeConvMessages = Array.isArray(conv.messages) ? conv.messages : [];
    clearError();
    const box = $('messages');
    if (!box) { closeHistory(); return; }
    box.querySelectorAll('.msg-row, .typing-row, #ia-mode-notice, #chat-empty').forEach(el => el.remove());

    // Affiche TOUT le fil IMMÉDIATEMENT (texte français pour un message dioula,
    // comme avant l'introduction du lecteur bilingue) — ne dépend JAMAIS du
    // réseau. Les messages dioula sont ensuite mis à niveau en place,
    // indépendamment les uns des autres (voir upgradeMessageDioula).
    state.activeConvMessages.forEach(m => {
      const row = appendMessage(m.role === 'assistant' ? 'ai' : 'user', m.content, '', null, m.lang);
      if (m.role === 'assistant' && m.lang === 'dioula') {
        upgradeMessageDioula(row, m.content);
      }
    });
    closeHistory();
  });
}

/* ── Sélecteur de modèle + ajout de clé API personnelle (menu de la page IA) ── */
function renderModelSwitcher() {
  const label = $('model-switcher-label');
  const current = state.modeles.find(m => m.id === state.provider);
  if (label) label.textContent = (current && current.nom) || t('Modèle');

  const list = $('model-switcher-list');
  if (!list) return;
  list.innerHTML = state.modeles.map(m => `
    <button type="button" class="model-item${m.id === state.provider ? ' active' : ''}"
            data-id="${esc(m.id)}" ${m.disponible ? '' : 'disabled'}>
      <span>${esc(m.nom)}</span>
      ${m.id === state.provider ? CHECK_SVG : ''}
      ${!m.disponible ? `<span class="model-item-note">${esc(t('clé requise'))}</span>` : ''}
    </button>`).join('');
}

function loadModeles() {
  fetchWithAuth('/api/assistant/chat/')
    .then(async res => ({ ok: res.ok, status: res.status, data: await res.json().catch(() => ({})) }))
    .then(({ ok, status, data }) => {
      if (!ok) {
        const inline = $('quota-inline');
        if (status === 403) {
          if (inline) inline.textContent = (data && data.detail) || t('Assistant réservé aux clients');
          const bar = $('input-bar'); if (bar) bar.style.display = 'none';
          const sug = $('suggestions'); if (sug) sug.style.display = 'none';
        } else if (inline && !state.quotaKnown) {
          inline.textContent = t('Quota indisponible');
        }
        return;
      }
      if (data.nb_requetes_aujourd_hui !== undefined) {
        state.limite = (data.limite_quotidienne === undefined) ? state.limite : data.limite_quotidienne;
        if (state.limite == null) {
          state.quota = Infinity;
          state.depleted = false;
        } else {
          state.quota = Math.max(0, state.limite - data.nb_requetes_aujourd_hui);
          state.depleted = state.quota <= 0;
        }
        state.quotaKnown = true;
        renderQuota();
        renderDepleted();
      }
      state.modeles = Array.isArray(data.modeles) ? data.modeles : [];
      // Si le modèle choisi n'est plus disponible (ex. clé perso retirée depuis Paramètres),
      // retombe silencieusement sur le standard.
      const choixValide = state.modeles.find(m => m.id === state.provider && m.disponible);
      if (!choixValide) {
        state.provider = 'standard';
        localStorage.setItem(PROVIDER_STORAGE_KEY, 'standard');
      }
      renderModelSwitcher();
    })
    .catch(err => {
      console.error(err);
      const inline = $('quota-inline');
      if (inline && !state.quotaKnown) inline.textContent = t('Quota indisponible');
    });
}

function renderSuggestions() {
  const wrap = $('suggestions');
  if (!wrap) return;
  wrap.innerHTML = '';
  SUGGESTIONS.forEach(s => {
    const translated = t(s);
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'sug-chip';
    btn.innerHTML = `<span>${esc(translated)}</span><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>`;
    btn.addEventListener('click', () => { $('msg-input').value = translated; updateSendBtn(); send(translated); });
    wrap.appendChild(btn);
  });
}

/* ── Sélecteurs de langue (saisie ET réponse) : même widget, deux instances
   indépendantes câblées dans DOMContentLoaded ci-dessous. `getEntry` est la
   fonction globale (sttLangEntry/ttsLangEntry) qui lit le localStorage dédié —
   partagée pour que le reste du fichier (startListening, send…) et ce widget
   restent toujours d'accord sur la valeur courante. */
function wireLangSwitcher({ switcherId, btnId, menuId, labelId, storageKey, getEntry, titre, arreterEcouteAuChangement }) {
  const switcher = $(switcherId);
  const btn = $(btnId);
  const menu = $(menuId);
  if (!switcher || !btn || !menu) return null;
  const refresh = () => {
    const cur = getEntry();
    const labelEl = $(labelId);
    if (labelEl) labelEl.textContent = cur.short;
    btn.title = titre + cur.label;
    btn.setAttribute('aria-label', btn.title);
    menu.querySelectorAll('.lang-switcher-item').forEach(item => {
      item.classList.toggle('active', item.dataset.code === cur.code);
    });
  };
  refresh();
  btn.addEventListener('click', e => {
    e.stopPropagation();
    const ouvert = !menu.hidden;
    menu.hidden = ouvert;
    btn.setAttribute('aria-expanded', String(!ouvert));
  });
  menu.addEventListener('click', e => {
    const item = e.target.closest('.lang-switcher-item');
    if (!item) return;
    if (arreterEcouteAuChangement && listening) stopListening();
    localStorage.setItem(storageKey, item.dataset.code);
    refresh();
    menu.hidden = true;
    btn.setAttribute('aria-expanded', 'false');
  });
  document.addEventListener('click', e => {
    if (!menu.hidden && !e.target.closest('#' + switcherId)) {
      menu.hidden = true;
      btn.setAttribute('aria-expanded', 'false');
    }
  });
  return switcher;
}

/* ── Initialisation ── */
document.addEventListener('DOMContentLoaded', () => {
  let theme = document.documentElement.getAttribute('data-theme') || 'light';
  applyTheme(theme);
  $('theme-toggle').addEventListener('click', () => {
    theme = window.AOCEDA.toggleTheme();
    applyTheme(theme);
  });

  renderQuota();
  renderDepleted();
  renderSuggestions();

  const ta = $('msg-input');
  ta.addEventListener('input', () => { autoResize(); updateSendBtn(); });
  ta.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(ta.value); }
  });
  const form = $('input-bar');
  if (form) form.addEventListener('submit', e => { e.preventDefault(); send(ta.value); });

  // Langue de SAISIE (micro) : le moteur vocal a besoin qu'on lui dise À
  // L'AVANCE dans quelle langue écouter, il ne « devine » pas la langue parlée.
  // Révélée seulement si la dictée est disponible (même condition que le micro).
  if (sttSupported) {
    const sw = wireLangSwitcher({
      switcherId: 'stt-lang-switcher', btnId: 'stt-lang-btn', menuId: 'stt-lang-menu',
      labelId: 'stt-lang-label', storageKey: STT_LANG_KEY, getEntry: sttLangEntry,
      titre: t('Langue de saisie : '), arreterEcouteAuChangement: true,
    });
    if (sw) sw.hidden = false;
  }
  // Langue de RÉPONSE : indépendante de la langue de saisie ci-dessus — change
  // aussi la langue du TEXTE de la réponse (pas seulement de la voix), donc
  // toujours visible, même sur un appareil sans synthèse vocale disponible.
  wireLangSwitcher({
    switcherId: 'tts-lang-switcher', btnId: 'tts-lang-btn', menuId: 'tts-lang-menu',
    labelId: 'tts-lang-label', storageKey: TTS_LANG_KEY, getEntry: ttsLangEntry,
    titre: t('Langue de réponse : '), arreterEcouteAuChangement: false,
  });

  // Micro (dictée) : révélé seulement si le navigateur/pont natif le supporte —
  // pas de bouton mort sur les navigateurs sans reconnaissance vocale (ex. Firefox desktop).
  const micBtn = $('mic-btn');
  if (micBtn && sttSupported) {
    micBtn.hidden = false;
    micBtn.addEventListener('click', () => { listening ? stopListening() : startListening(); });
  }

  // Importer un audio déjà enregistré (au lieu de dicter en direct) : envoyé
  // comme si l'utilisateur avait parlé, MÊME pipeline que la dictée dioula (voir
  // sendAudioDioula) — c'est le seul chemin serveur qui comprend un fichier audio
  // aujourd'hui, quelle que soit la langue de saisie choisie dans le sélecteur.
  // Toujours révélé : un <input type=file> ne dépend d'aucune API vocale du
  // navigateur (contrairement au micro), donc pas de garde-fou de disponibilité
  // à faire ici, seulement côté serveur si le modèle dioula est indisponible
  // (déjà géré honnêtement, voir AIChatAudioView).
  const audioImportBtn = $('audio-import-btn');
  const audioFileInput = $('audio-file-input');
  if (audioImportBtn && audioFileInput) {
    audioImportBtn.hidden = false;
    audioImportBtn.addEventListener('click', () => {
      if (state.typing || state.depleted) return;
      audioFileInput.click();
    });
    audioFileInput.addEventListener('change', () => {
      const fichier = audioFileInput.files && audioFileInput.files[0];
      audioFileInput.value = ''; // permet de réimporter le même fichier une 2e fois
      if (!fichier) return;
      if (fichier.size > AUDIO_IMPORT_MAX_BYTES) {
        showError(t(`Fichier audio trop volumineux (maximum ${AUDIO_IMPORT_MAX_MB} Mo).`), false);
        return;
      }
      sendAudioDioula(fichier); // un File est un Blob : même fonction que l'enregistrement live
    });
  }

  // Lecture vocale automatique des réponses (header) : même règle de disponibilité que le TTS.
  const ttsAutoBtn = $('tts-toggle-btn');
  if (ttsAutoBtn && ttsSupported) {
    ttsAutoBtn.hidden = false;
    const refreshAutoBtn = () => {
      const on = isAutoRead();
      ttsAutoBtn.classList.toggle('is-active', on);
      ttsAutoBtn.setAttribute('aria-pressed', String(on));
    };
    refreshAutoBtn();
    ttsAutoBtn.addEventListener('click', () => {
      localStorage.setItem(AUTOREAD_KEY, isAutoRead() ? '0' : '1');
      if (!isAutoRead()) stopSpeaking();
      refreshAutoBtn();
    });
  }

  // Historique / nouvelle conversation / clic sur un fil du panneau (100% local)
  const historyBtn = $('history-toggle-btn');
  if (historyBtn) historyBtn.addEventListener('click', openHistory);
  const historyCloseBtn = $('conv-history-close');
  if (historyCloseBtn) historyCloseBtn.addEventListener('click', closeHistory);
  const newChatBtn = $('new-chat-btn');
  if (newChatBtn) newChatBtn.addEventListener('click', startNewConversation);
  document.addEventListener('click', e => {
    const item = e.target.closest('.conv-item');
    if (item && item.dataset.id) openConversation(item.dataset.id);
  });

  // Sélecteur de modèle : ouverture/fermeture du menu
  const switcherBtn = $('model-switcher-btn');
  const switcherMenu = $('model-switcher-menu');
  if (switcherBtn && switcherMenu) {
    switcherBtn.addEventListener('click', e => {
      e.stopPropagation();
      const ouvert = !switcherMenu.hidden;
      switcherMenu.hidden = ouvert;
      switcherBtn.setAttribute('aria-expanded', String(!ouvert));
    });
    document.addEventListener('click', e => {
      if (!switcherMenu.hidden && !e.target.closest('#model-switcher')) {
        switcherMenu.hidden = true;
        switcherBtn.setAttribute('aria-expanded', 'false');
      }
    });
  }
  // Choix d'un modèle dans la liste (switch possible en cours de discussion)
  document.addEventListener('click', e => {
    const item = e.target.closest('.model-item');
    if (!item || item.disabled) return;
    state.provider = item.dataset.id;
    localStorage.setItem(PROVIDER_STORAGE_KEY, state.provider);
    renderModelSwitcher();
    if (switcherMenu) switcherMenu.hidden = true;
  });
  // Ajout d'une clé API personnelle DIRECTEMENT depuis ce menu (pas besoin de Paramètres)
  const keySaveBtn = $('model-switcher-key-save');
  if (keySaveBtn) {
    keySaveBtn.addEventListener('click', () => {
      const input = $('model-switcher-key');
      const feedback = $('model-switcher-key-feedback');
      const valeur = input ? input.value.trim() : '';
      if (feedback) feedback.textContent = '';
      if (!valeur) return;
      fetchWithAuth('/api/users/me/', {
        method: 'PUT',
        body: JSON.stringify({ cle_api_ia_personnelle: valeur }),
      })
        .then(res => res.json().catch(() => ({})))
        .then(data => {
          if (data && data.email) {
            if (input) input.value = '';
            if (feedback) feedback.textContent = t('Clé ajoutée ✓');
            state.provider = 'personnel';
            localStorage.setItem(PROVIDER_STORAGE_KEY, 'personnel');
            loadModeles();
          } else if (feedback) {
            feedback.textContent = t("Échec de l'enregistrement.");
          }
        })
        .catch(() => { if (feedback) feedback.textContent = t("Échec de l'enregistrement."); });
    });
  }

  // Données utilisateur (initiales d'avatar)
  fetchWithAuth('/api/users/me/')
    .then(res => res.json())
    .then(data => {
      state.user = data;
      document.querySelectorAll('.msg-row.user .msg-avatar').forEach(el => { el.textContent = userInitials(); });
    })
    .catch(err => console.error(err));

  // Quota du jour + modèles disponibles (GET : ne consomme PAS de question). La page
  // s'ouvre TOUJOURS sur l'état d'accueil vide — le contenu vit dans le localStorage,
  // consultable via le panneau Historique, jamais rejoué automatiquement.
  loadModeles();
});
