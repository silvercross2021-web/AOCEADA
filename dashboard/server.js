const express  = require('express');
const { WebSocketServer } = require('ws');
const { SerialPort }      = require('serialport');
const { ReadlineParser }  = require('@serialport/parser-readline');
const fs   = require('fs');
const path = require('path');
const http = require('http');

// ---- CONFIGURATION -------------------------------------------------
// Usage : node server.js COM4
const HTTP_PORT   = 3000;
const SERIAL_PORT = process.argv[2] || 'COM3';
const BAUD_RATE   = 9600;
const DATA_FILE   = path.join(__dirname, 'data.json');

// ---- STOCKAGE JSON -------------------------------------------------
// Lectures : dernières 200 par capteur (graphiques)
// Evenements : derniers 200 (historique)
const MAX_LECTURES  = 200;
const MAX_EVENEMENTS = 200;

let store = { lectures: {}, evenements: [] };

if (fs.existsSync(DATA_FILE)) {
  try { store = JSON.parse(fs.readFileSync(DATA_FILE, 'utf8')); }
  catch (e) { console.warn('data.json illisible, reset.'); }
}

function sauvegarder() {
  fs.writeFileSync(DATA_FILE, JSON.stringify(store), 'utf8');
}

function ajouterLecture(capteur, lecture) {
  if (!store.lectures[capteur]) store.lectures[capteur] = [];
  store.lectures[capteur].push(lecture);
  if (store.lectures[capteur].length > MAX_LECTURES)
    store.lectures[capteur].shift();
}

function ajouterEvenement(ev) {
  store.evenements.push(ev);
  if (store.evenements.length > MAX_EVENEMENTS)
    store.evenements.shift();
  sauvegarder();
}

// Sauvegarde périodique toutes les 10s (pas à chaque lecture pour éviter I/O excessif)
setInterval(sauvegarder, 10000);

// ---- HTTP + WEBSOCKET ---------------------------------------------
const app    = express();
const server = http.createServer(app);
const wss    = new WebSocketServer({ server });

app.use(express.static(path.join(__dirname, 'public')));
app.use(express.text());   // pour recevoir les lignes de l'ESP32

app.get('/api/evenements', (_req, res) => {
  res.json([...store.evenements].reverse());
});

app.get('/api/lectures/:capteur', (req, res) => {
  res.json(store.lectures[req.params.capteur] || []);
});

app.get('/api/etat',  (_req, res) => res.json(etatActuel));
app.get('/api/a2raw', (_req, res) => res.json(dernierA2));

// Endpoint WiFi : l'ESP32 envoie chaque ligne serie via HTTP POST
app.post('/api/wifi', (req, res) => {
  if (typeof req.body === 'string' && req.body.length > 0) {
    parseLigne(req.body);
  }
  res.json({ ok: true });
});

// ---- ETAT EN MEMOIRE -----------------------------------------------
const etatActuel = {};
let evenementEnCours = null;
let dernierA2 = null;

function broadcast(msg) {
  const str = JSON.stringify(msg);
  wss.clients.forEach(c => { if (c.readyState === 1) c.send(str); });
}

wss.on('connection', ws => {
  ws.send(JSON.stringify({ type: 'etat', data: etatActuel }));
});

// ---- PARSEUR SERIE -------------------------------------------------
function parseLigne(ligne) {
  const ts = Date.now();
  ligne = ligne.trim();

  // Statut: [Capteur_1]  Centre=458  Ampl=12  [OFF]
  //      ou [Capteur_1]  Centre=467  Ampl=43  [ON ]  Courant=0.176A  Tension=220V  Puissance=38.8W
  const mStat = ligne.match(/\[(\w+)\]\s+Centre=(\d+)\s+Ampl=(\d+)\s+\[(ON |OFF)\](.*)/);
  if (mStat) {
    const capteur   = mStat[1];
    const centre    = parseInt(mStat[2]);
    const ampl      = parseInt(mStat[3]);
    const etat      = mStat[4].trim();
    const reste     = mStat[5];
    const mC = reste.match(/Courant=([\d.]+)A/);
    const mP = reste.match(/Puissance=([\d.]+)W/);
    const courant   = mC ? parseFloat(mC[1]) : null;
    const puissance = mP ? parseFloat(mP[1]) : null;
    const ecret     = reste.includes('!ECRET');

    etatActuel[capteur] = { capteur, etat, centre, ampl, courant, puissance, ecret, ts };
    ajouterLecture(capteur, { ts, etat, courant, puissance });
    broadcast({ type: 'etat', data: etatActuel });
    return;
  }

  // Evenement ON : +++ PRISE BRANCHEE  #1  [Capteur_2]
  const mON = ligne.match(/\+\+\+\s+(.+?)\s+#(\d+)\s+\[(\w+)\]/);
  if (mON) {
    const ev = { capteur: mON[3], ts, type: 'ON', label: mON[1], numero: parseInt(mON[2]), duree_s: null, courant_moy: null, puissance_moy: null };
    ajouterEvenement(ev);
    broadcast({ type: 'evenement', data: ev });
    return;
  }

  // Evenement OFF ligne 1 : --- LAMPE ETEINTE  #1  [Capteur_1]  Duree=315.8s
  const mOFF = ligne.match(/---\s+(.+?)\s+#(\d+)\s+\[(\w+)\]\s+Duree=([\d.]+)s/);
  if (mOFF) {
    evenementEnCours = { capteur: mOFF[3], ts, type: 'OFF', label: mOFF[1], numero: parseInt(mOFF[2]), duree_s: parseFloat(mOFF[4]) };
    return;
  }

  // Diagnostic A2 ESP32
  const mA2 = ligne.match(/\[A2-ESP32\]\s+Centre=(\d+)\s+Min=(\d+)\s+Max=(\d+)\s+Ampl=(\d+)\s+RMS=([\d.]+)/);
  if (mA2) {
    dernierA2 = { centre: parseInt(mA2[1]), min: parseInt(mA2[2]), max: parseInt(mA2[3]), ampl: parseInt(mA2[4]), rms: parseFloat(mA2[5]), ts };
    broadcast({ type: 'a2raw', data: dernierA2 });
    return;
  }

  // Evenement OFF ligne 2 : Courant=0.181A  Tension=220V  Puissance=39.9W  K=0.04883
  if (evenementEnCours) {
    const mC = ligne.match(/Courant=([\d.]+)A/);
    const mP = ligne.match(/Puissance=([\d.]+)W/);
    if (mC && mP) {
      evenementEnCours.courant_moy   = parseFloat(mC[1]);
      evenementEnCours.puissance_moy = parseFloat(mP[1]);
      ajouterEvenement(evenementEnCours);
      broadcast({ type: 'evenement', data: evenementEnCours });
      evenementEnCours = null;
    }
  }
}

// ---- CONNEXION SERIE -----------------------------------------------
function connecterSerie() {
  let port;
  try {
    port = new SerialPort({ path: SERIAL_PORT, baudRate: BAUD_RATE });
  } catch (err) {
    console.error(`[Serie] Impossible d'ouvrir ${SERIAL_PORT}: ${err.message}`);
    console.error(`  -> Verifiez que l'Arduino est branche`);
    console.error(`  -> Usage: node server.js COM4`);
    return;
  }
  const parser = port.pipe(new ReadlineParser({ delimiter: '\n' }));
  parser.on('data', l => parseLigne(l));
  port.on('error', err => console.error('[Serie] Erreur:', err.message));
  port.on('close', () => {
    console.warn('[Serie] Port ferme, reconnexion dans 5s...');
    setTimeout(connecterSerie, 5000);
  });
  port.on('open', () => console.log(`[Serie] Connecte sur ${SERIAL_PORT} @ ${BAUD_RATE} baud`));
}

// ---- DEMARRAGE -----------------------------------------------------
server.listen(HTTP_PORT, () => {
  console.log('\n=== ZMCT103C Dashboard ===');
  console.log(`Ouvrir : http://localhost:${HTTP_PORT}`);
  console.log(`Serie  : ${SERIAL_PORT}  (changer: node server.js COM4)`);
  console.log('');
  connecterSerie();
});
