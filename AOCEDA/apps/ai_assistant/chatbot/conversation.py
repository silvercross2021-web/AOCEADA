"""Mémoire des conversations, dans une petite base SQLite (fichier sur le disque).

Pourquoi SQLite et plus la mémoire vive : les conversations survivent au redémarrage du serveur,
plusieurs personnes peuvent écrire en même temps (chaque accès est court et protégé), et la même
logique se transposera telle quelle vers la base de données d'AOCEDA (Django).

- Une conversation = une suite de messages {"role": "user"|"model", "texte"} + sa langue courante.
- On n'envoie au modèle que les MAX_MESSAGES derniers messages (coût et vitesse bornés).
- Un échange qui échoue ou qui est interrompu est retiré : l'historique reste propre.
- Les conversations inactives depuis DUREE_VIE_S sont effacées.
- Pour chaque conversation, on retient les morceaux de voix AUTORISÉS (ceux des réponses du chatbot) :
  le serveur refuse de fabriquer la voix d'un texte qu'il n'a pas écrit lui-même (sécurité).
"""
import sqlite3
import threading
import time

from .config import CACHE

MAX_MESSAGES = 20          # 10 échanges gardés en mémoire pour le modèle
MAX_CARACTERES = 2000      # longueur maximum d'un message utilisateur
DUREE_VIE_S = 7 * 24 * 3600   # conversation oubliée après 7 jours sans activité
MAX_MORCEAUX_AUTORISES = 200  # morceaux de voix gardés par conversation

FICHIER = CACHE / "conversations.sqlite3"
_verrou = threading.Lock()
_local = threading.local()
_derniere_purge = {"t": 0.0}


class MessageInvalide(ValueError):
    pass


def _base():
    """Une connexion par fil d'exécution (SQLite n'aime pas partager une connexion entre fils)."""
    c = getattr(_local, "connexion", None)
    if c is None or getattr(_local, "fichier", None) != FICHIER:
        FICHIER.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(FICHIER, timeout=10)
        c.execute("PRAGMA journal_mode=WAL")          # lectures et écritures simultanées sans blocage
        c.executescript("""
            CREATE TABLE IF NOT EXISTS conversation (session TEXT PRIMARY KEY, langue TEXT, langue_imposee TEXT, maj REAL);
            CREATE TABLE IF NOT EXISTS message (id INTEGER PRIMARY KEY AUTOINCREMENT, session TEXT, role TEXT, texte TEXT);
            CREATE INDEX IF NOT EXISTS message_session ON message(session, id);
            CREATE TABLE IF NOT EXISTS voix_autorisee (session TEXT, texte TEXT, PRIMARY KEY (session, texte));
        """)
        # 05/10/2026 : langue du menu vue au dernier message (un changement de menu efface une ancienne demande)
        if "menu" not in {r[1] for r in c.execute("PRAGMA table_info(conversation)")}:
            c.execute("ALTER TABLE conversation ADD COLUMN menu TEXT")
        _local.connexion, _local.fichier = c, FICHIER
    return c


def nettoyer_message(texte):
    t = (texte or "").strip()
    if not t:
        raise MessageInvalide("Message vide.")
    if len(t) > MAX_CARACTERES:
        raise MessageInvalide(f"Message trop long ({len(t)} caractères, maximum {MAX_CARACTERES}).")
    return t


def _purger(c):
    if time.time() - _derniere_purge["t"] < 600:      # au plus toutes les 10 min
        return
    _derniere_purge["t"] = time.time()
    anciennes = [r[0] for r in c.execute("SELECT session FROM conversation WHERE maj < ?", (time.time() - DUREE_VIE_S,))]
    for s in anciennes:
        _effacer(c, s)


def _effacer(c, session):
    c.execute("DELETE FROM message WHERE session = ?", (session,))
    c.execute("DELETE FROM voix_autorisee WHERE session = ?", (session,))
    c.execute("DELETE FROM conversation WHERE session = ?", (session,))


def _toucher(c, session):
    c.execute("INSERT INTO conversation(session, maj) VALUES (?, ?) ON CONFLICT(session) DO UPDATE SET maj = excluded.maj",
              (session, time.time()))


def historique(session):
    with _verrou:
        rows = _base().execute("SELECT role, texte FROM message WHERE session = ? ORDER BY id", (session,)).fetchall()
    return [{"role": r, "texte": t} for r, t in rows]


def poser_question(session, texte):
    """Ajoute la question ; renvoie (historique à envoyer au modèle (borné), identifiant de la question).
    L'identifiant permet de retirer CETTE question si sa réponse échoue ou est arrêtée (audit du 09/10/2026 : retirer « la
    dernière question » pouvait effacer une NOUVELLE question posée entre-temps)."""
    with _verrou:
        c = _base()
        with c:
            _purger(c)
            _toucher(c, session)
            ident = c.execute("INSERT INTO message(session, role, texte) VALUES (?, 'user', ?)", (session, texte)).lastrowid
        rows = c.execute("SELECT role, texte FROM (SELECT id, role, texte FROM message WHERE session = ? ORDER BY id DESC LIMIT ?) "
                         "ORDER BY id", (session, MAX_MESSAGES)).fetchall()
    return [{"role": r, "texte": t} for r, t in rows], ident


def ajouter_question(session, texte):
    """Ajoute la question et renvoie l'historique à envoyer au modèle (borné)."""
    return poser_question(session, texte)[0]


def ajouter_reponse(session, texte):
    with _verrou:
        c = _base()
        with c:
            _toucher(c, session)
            c.execute("INSERT INTO message(session, role, texte) VALUES (?, 'model', ?)", (session, texte))
            # on garde un peu plus que ce qu'on envoie au modèle
            c.execute("DELETE FROM message WHERE session = ? AND id NOT IN "
                      "(SELECT id FROM message WHERE session = ? ORDER BY id DESC LIMIT ?)", (session, session, MAX_MESSAGES * 2))


def remplacer_derniere_question(session, texte, ident=None):
    """Remplace le texte d'une question de l'utilisateur : celle d'identifiant `ident` (poser_question), sinon la dernière
    (dioula : on garde pour la suite de la conversation une version courte « ce qu'il a dit + ce qu'on a compris », pas
    tout le dossier envoyé à DeepSeek)."""
    with _verrou:
        with _base() as c:
            if ident is not None:
                c.execute("UPDATE message SET texte = ? WHERE id = ? AND session = ? AND role = 'user'", (texte, ident, session))
                return
            der = c.execute("SELECT id FROM message WHERE session = ? AND role = 'user' ORDER BY id DESC LIMIT 1",
                            (session,)).fetchone()
            if der:
                c.execute("UPDATE message SET texte = ? WHERE id = ?", (texte, der[0]))


def annuler_question(session, ident=None):
    """Retire une question restée sans réponse (échec, ou réponse arrêtée par l'utilisateur) : celle d'identifiant `ident`
    (poser_question), où qu'elle soit ; sans identifiant, la dernière si elle est sans réponse."""
    with _verrou:
        c = _base()
        with c:
            if ident is not None:
                c.execute("DELETE FROM message WHERE id = ? AND session = ? AND role = 'user'", (ident, session))
                return
            der = c.execute("SELECT id, role FROM message WHERE session = ? ORDER BY id DESC LIMIT 1", (session,)).fetchone()
            if der and der[1] == "user":
                c.execute("DELETE FROM message WHERE id = ?", (der[0],))


def langue(session):
    with _verrou:
        r = _base().execute("SELECT langue FROM conversation WHERE session = ?", (session,)).fetchone()
    return r[0] if r else None


def noter_langue(session, code, imposee=False):
    """Langue courante de la conversation ; `imposee` = demandée explicitement (« réponds en anglais »)."""
    if not code:
        return
    with _verrou:
        c = _base()
        with c:
            _toucher(c, session)
            c.execute("UPDATE conversation SET langue = ? WHERE session = ?", (code, session))
            if imposee:
                c.execute("UPDATE conversation SET langue_imposee = ? WHERE session = ?", (code, session))


def langue_imposee(session):
    with _verrou:
        r = _base().execute("SELECT langue_imposee FROM conversation WHERE session = ?", (session,)).fetchone()
    return r[0] if r else None


def oublier_langue_imposee(session):
    with _verrou:
        with _base() as c:
            c.execute("UPDATE conversation SET langue_imposee = NULL WHERE session = ?", (session,))


def noter_menu(session, menu):
    """Retient la langue du menu de la page. Si elle a CHANGÉ depuis le dernier message, la langue demandée plus tôt
    (« réponds en anglais ») est oubliée : c'est le dernier choix de la personne qui compte. Renvoie True si le menu a
    changé."""
    with _verrou:
        c = _base()
        with c:
            r = c.execute("SELECT menu FROM conversation WHERE session = ?", (session,)).fetchone()
            _toucher(c, session)
            change = bool(r and r[0] is not None and r[0] != menu)
            c.execute("UPDATE conversation SET menu = ?" + (", langue_imposee = NULL" if change else "") + " WHERE session = ?",
                      (menu, session))
    return change


def autoriser_voix(session, morceaux):
    """Retient les morceaux qu'on a le droit de lire à voix haute pour cette conversation."""
    with _verrou:
        c = _base()
        with c:
            c.executemany("INSERT OR IGNORE INTO voix_autorisee(session, texte) VALUES (?, ?)", [(session, m) for m in morceaux])
            c.execute("DELETE FROM voix_autorisee WHERE session = ? AND rowid NOT IN "
                      "(SELECT rowid FROM voix_autorisee WHERE session = ? ORDER BY rowid DESC LIMIT ?)",
                      (session, session, MAX_MORCEAUX_AUTORISES))


def voix_autorisee(session, morceau):
    with _verrou:
        return _base().execute("SELECT 1 FROM voix_autorisee WHERE session = ? AND texte = ?", (session, morceau)).fetchone() is not None


def effacer(session):
    with _verrou:
        c = _base()
        with c:
            _effacer(c, session)
