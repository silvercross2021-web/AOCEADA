"""Adaptateurs multi-fournisseurs pour l'assistant IA (clé API personnelle du client).

Le reste de l'app (AIChatView._boucle_llm) ne manipule QUE le format canonique :
messages = [{"role": "user"|"assistant"|"tool", "content": str, ...}], où un tour
assistant qui demande des outils porte "tool_calls": [{"id", "name", "arguments":
dict}] et un tour "tool" porte "tool_call_id"/"name"/"content". Chaque adaptateur
traduit CE format canonique vers le format réseau propre à son fournisseur (et la
réponse en sens inverse) — ajouter un fournisseur = ajouter une classe ici, rien à
toucher dans la boucle d'appel d'outils.

La clé perso du client ne précise QUE la clé, jamais le fournisseur explicitement :
`detecter_fournisseur` le déduit du FORMAT de la clé (préfixe caractéristique de
chaque plateforme), sauf si le client a aussi renseigné une URL personnalisée
(endpoint générique compatible OpenAI, ex. self-hosted / proxy / fournisseur non
listé) auquel cas l'URL prime sur toute détection.
"""
import json
import logging
import re

import requests  # pyrefly: ignore [untyped-import]

logger = logging.getLogger(__name__)


class ErreurAppelLLM(Exception):
    """Échec réseau ou statut non-200 d'un appel LLM — message court destiné aux
    logs (JAMAIS la clé), l'appelant catch large et replie sur l'assistant local.
    `status_code` (None si l'erreur n'est pas un statut HTTP) permet à l'appelant
    de distinguer clé invalide (401/403) / modèle introuvable (404) / quota (429)
    sans reparser le message — voir verifier_cle_fonctionnelle."""

    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


# ── Détection du fournisseur depuis le FORMAT de la clé ─────────────────────────
# Chaque plateforme a un préfixe caractéristique et stable dans le temps ; testé
# dans l'ordre du plus spécifique au plus générique pour ne jamais mal classer une
# clé Anthropic/OpenAI "projet" comme une simple clé "sk-" générique.
_RE_DEEPSEEK = re.compile(r'^sk-[0-9a-f]{32}$')

NOMS_AFFICHABLES = {
    'openai': 'OpenAI', 'gemini': 'Google Gemini', 'anthropic': 'Anthropic Claude',
    'deepseek': 'DeepSeek', 'grok': 'xAI Grok', 'generique': 'Endpoint personnalisé',
}


def detecter_fournisseur(cle, url_perso=None):
    """Renvoie l'identifiant du fournisseur déduit de la clé (et de l'URL perso
    éventuelle), ou None si le format n'est pas reconnu — dans ce cas l'appelant
    doit refuser la clé avec un message clair plutôt que de tenter un appel voué
    à l'échec silencieux."""
    if (url_perso or '').strip():
        return 'generique'
    cle = (cle or '').strip()
    if not cle:
        return None
    if cle.startswith('sk-ant-'):
        return 'anthropic'
    if cle.startswith('AIzaSy') or cle.startswith('AQ.'):
        # AIzaSy... : format historique. AQ.... : format émis depuis Google AI
        # Studio (aistudio.google.com/api-keys) — confirmé en test réel.
        return 'gemini'
    if cle.startswith('xai-'):
        return 'grok'
    if cle.startswith('sk-proj-') or cle.startswith('sk-svcacct-'):
        return 'openai'
    if _RE_DEEPSEEK.match(cle):
        return 'deepseek'
    if cle.startswith('sk-'):
        # Préfixe générique historique d'OpenAI — le seul cas réellement ambigu
        # (DeepSeek suit un format plus strict, déjà filtré ci-dessus).
        return 'openai'
    return None


# ── Adaptateurs ──────────────────────────────────────────────────────────────
class _AdaptateurBase:
    id = None

    def __init__(self, cle, url, modele, timeout, max_tokens, temperature):
        self.cle = cle
        self.url = url
        self.modele = modele
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.temperature = temperature

    def appeler(self, system_instruction, messages, outils_spec, dernier_tour):
        """messages = historique canonique (voir docstring du module), SANS le
        message system. Renvoie (texte, tool_calls_canonique, tokens_in, tokens_out).
        Lève ErreurAppelLLM sur statut HTTP non-200 ; laisse remonter les exceptions
        réseau (timeout, DNS...) telles quelles — l'appelant les catch largement."""
        raise NotImplementedError


class AdaptateurOpenAICompatible(_AdaptateurBase):
    """DeepSeek, xAI/Grok, OpenAI, ou tout endpoint générique respectant le format
    chat/completions (Bearer + tools façon OpenAI) — le format déjà en place."""
    id = 'openai_compatible'

    def __init__(self, *args, desactiver_thinking=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.desactiver_thinking = desactiver_thinking

    def _messages_wire(self, system_instruction, messages):
        wire = [{"role": "system", "content": system_instruction}]
        for m in messages:
            role = m.get('role')
            if role == 'assistant' and m.get('tool_calls'):
                wire.append({
                    "role": "assistant",
                    "content": m.get('content') or "",
                    "tool_calls": [
                        {"id": tc['id'], "type": "function",
                         "function": {"name": tc['name'],
                                      "arguments": json.dumps(tc.get('arguments') or {}, ensure_ascii=False)}}
                        for tc in m['tool_calls']
                    ],
                })
            elif role == 'tool':
                wire.append({"role": "tool", "tool_call_id": m.get('tool_call_id') or '',
                             "content": m.get('content') or ''})
            else:
                wire.append({"role": role, "content": m.get('content') or ''})
        return wire

    def appeler(self, system_instruction, messages, outils_spec, dernier_tour):
        payload = {
            "model": self.modele,
            "messages": self._messages_wire(system_instruction, messages),
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        if outils_spec:
            # Certains fournisseurs (dont OpenAI) refusent "tools": [] (tableau
            # vide) — omis entièrement plutôt qu'envoyé vide (voir l'appel de
            # vérification de clé, sans outils, dans verifier_cle_fonctionnelle).
            payload["tools"] = outils_spec
            payload["tool_choice"] = "none" if dernier_tour else "auto"
        if self.desactiver_thinking:
            # Voir AdaptateurOpenAICompatible (DeepSeek) : le mode "thinking" par
            # défaut peut consommer tout le budget max_tokens en raisonnement
            # interne et laisser 'content' vide — désactivé pour des réponses
            # courtes et fiables (constaté en test réel).
            payload["thinking"] = {"type": "disabled"}

        resp = requests.post(
            self.url,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.cle}"},
            json=payload, timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise ErreurAppelLLM(f"{self.modele} statut {resp.status_code} : {resp.text[:300]}", status_code=resp.status_code)

        data = resp.json()
        usage = data.get('usage') or {}
        msg = (data.get('choices') or [{}])[0].get('message', {}) or {}
        tool_calls = []
        for tc in (msg.get('tool_calls') or []):
            fonction = tc.get('function') or {}
            try:
                arguments = json.loads(fonction.get('arguments') or '{}')
            except ValueError:
                arguments = {}
            tool_calls.append({"id": tc.get('id') or '', "name": fonction.get('name') or '', "arguments": arguments})
        texte = (msg.get('content') or '').strip()
        return texte, tool_calls, int(usage.get('prompt_tokens') or 0), int(usage.get('completion_tokens') or 0)


class AdaptateurGemini(_AdaptateurBase):
    """Google Gemini (generateContent) — auth par header `X-goog-api-key` (format
    du guide de démarrage officiel, aistudio.google.com/api-keys), pas de rôle
    'system' dans `contents` (champ séparé `system_instruction`), rôles
    'user'/'model'/'function', function calling via functionCall/functionResponse."""
    id = 'gemini'

    def _contents(self, messages):
        contents = []
        for m in messages:
            role = m.get('role')
            if role == 'user':
                contents.append({"role": "user", "parts": [{"text": m.get('content') or ''}]})
            elif role == 'assistant':
                parts = []
                if m.get('content'):
                    parts.append({"text": m['content']})
                for tc in (m.get('tool_calls') or []):
                    parts.append({"functionCall": {"name": tc['name'], "args": tc.get('arguments') or {}}})
                contents.append({"role": "model", "parts": parts})
            elif role == 'tool':
                try:
                    reponse = json.loads(m.get('content') or '{}')
                except ValueError:
                    reponse = {"resultat": m.get('content') or ''}
                contents.append({
                    "role": "function",
                    "parts": [{"functionResponse": {"name": m.get('name') or '', "response": reponse}}],
                })
        return contents

    def appeler(self, system_instruction, messages, outils_spec, dernier_tour):
        payload = {
            "system_instruction": {"parts": [{"text": system_instruction}]},
            "contents": self._contents(messages),
            "generationConfig": {"temperature": self.temperature, "maxOutputTokens": self.max_tokens},
        }
        if not dernier_tour:
            function_declarations = [
                {"name": o['function']['name'], "description": o['function']['description'],
                 "parameters": o['function']['parameters']}
                for o in outils_spec
            ]
            payload["tools"] = [{"functionDeclarations": function_declarations}]

        url = f"{self.url.rstrip('/')}/{self.modele}:generateContent"
        resp = requests.post(
            url, headers={"Content-Type": "application/json", "X-goog-api-key": self.cle},
            json=payload, timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise ErreurAppelLLM(f"{self.modele} statut {resp.status_code} : {resp.text[:300]}", status_code=resp.status_code)

        data = resp.json()
        usage = data.get('usageMetadata') or {}
        candidats = data.get('candidates') or [{}]
        parts = ((candidats[0].get('content') or {}).get('parts')) or []
        texte = ''.join(p.get('text', '') for p in parts if 'text' in p).strip()
        tool_calls = []
        for i, p in enumerate(parts):
            fc = p.get('functionCall')
            if fc:
                tool_calls.append({"id": f"gemini-{i}", "name": fc.get('name') or '', "arguments": fc.get('args') or {}})
        return texte, tool_calls, int(usage.get('promptTokenCount') or 0), int(usage.get('candidatesTokenCount') or 0)


class AdaptateurAnthropic(_AdaptateurBase):
    """Anthropic Claude (Messages API) — auth par header x-api-key, system séparé
    des messages, tool_use/tool_result en blocs de contenu structurés."""
    id = 'anthropic'
    VERSION = '2023-06-01'

    def _messages_wire(self, messages):
        wire = []
        for m in messages:
            role = m.get('role')
            if role == 'user':
                wire.append({"role": "user", "content": m.get('content') or ''})
            elif role == 'assistant':
                blocs = []
                if m.get('content'):
                    blocs.append({"type": "text", "text": m['content']})
                for tc in (m.get('tool_calls') or []):
                    blocs.append({"type": "tool_use", "id": tc['id'], "name": tc['name'], "input": tc.get('arguments') or {}})
                wire.append({"role": "assistant", "content": blocs})
            elif role == 'tool':
                wire.append({"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": m.get('tool_call_id') or '', "content": m.get('content') or ''},
                ]})
        return wire

    def appeler(self, system_instruction, messages, outils_spec, dernier_tour):
        payload = {
            "model": self.modele,
            "system": system_instruction,
            "messages": self._messages_wire(messages),
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if not dernier_tour:
            payload["tools"] = [
                {"name": o['function']['name'], "description": o['function']['description'],
                 "input_schema": o['function']['parameters']}
                for o in outils_spec
            ]

        resp = requests.post(
            self.url,
            headers={"Content-Type": "application/json", "x-api-key": self.cle, "anthropic-version": self.VERSION},
            json=payload, timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise ErreurAppelLLM(f"{self.modele} statut {resp.status_code} : {resp.text[:300]}", status_code=resp.status_code)

        data = resp.json()
        usage = data.get('usage') or {}
        texte_parts, tool_calls = [], []
        for bloc in (data.get('content') or []):
            if bloc.get('type') == 'text':
                texte_parts.append(bloc.get('text') or '')
            elif bloc.get('type') == 'tool_use':
                tool_calls.append({"id": bloc.get('id') or '', "name": bloc.get('name') or '', "arguments": bloc.get('input') or {}})
        return ''.join(texte_parts).strip(), tool_calls, int(usage.get('input_tokens') or 0), int(usage.get('output_tokens') or 0)


# ── Fabrique ─────────────────────────────────────────────────────────────────
def construire_adaptateur(fournisseur, cle, url_perso, modele_perso, settings):
    """Construit l'adaptateur pour le fournisseur DÉTECTÉ à partir de la clé perso
    d'un client (voir detecter_fournisseur). `settings` = django.conf.settings.
    None si le fournisseur est inconnu ou (cas générique) si l'URL/le modèle
    personnalisés manquent."""
    if fournisseur == 'gemini':
        return AdaptateurGemini(cle, settings.GEMINI_API_URL, modele_perso or settings.GEMINI_MODEL,
                                 settings.GEMINI_TIMEOUT, settings.GEMINI_MAX_TOKENS, settings.GEMINI_TEMPERATURE)
    if fournisseur == 'anthropic':
        return AdaptateurAnthropic(cle, settings.ANTHROPIC_API_URL, modele_perso or settings.ANTHROPIC_MODEL,
                                    settings.ANTHROPIC_TIMEOUT, settings.ANTHROPIC_MAX_TOKENS, settings.ANTHROPIC_TEMPERATURE)
    if fournisseur == 'openai':
        return AdaptateurOpenAICompatible(cle, settings.OPENAI_API_URL, modele_perso or settings.OPENAI_MODEL,
                                           settings.OPENAI_TIMEOUT, settings.OPENAI_MAX_TOKENS, settings.OPENAI_TEMPERATURE)
    if fournisseur == 'grok':
        return AdaptateurOpenAICompatible(cle, settings.GROK_API_URL, modele_perso or settings.GROK_MODEL,
                                           settings.GROK_TIMEOUT, settings.GROK_MAX_TOKENS, settings.GROK_TEMPERATURE)
    if fournisseur == 'deepseek':
        return AdaptateurOpenAICompatible(cle, settings.DEEPSEEK_API_URL, modele_perso or settings.DEEPSEEK_MODEL,
                                           settings.DEEPSEEK_TIMEOUT, settings.DEEPSEEK_MAX_TOKENS,
                                           settings.DEEPSEEK_TEMPERATURE, desactiver_thinking=True)
    if fournisseur == 'generique':
        if not url_perso or not modele_perso:
            return None
        return AdaptateurOpenAICompatible(cle, url_perso, modele_perso,
                                           settings.DEEPSEEK_TIMEOUT, settings.DEEPSEEK_MAX_TOKENS, settings.DEEPSEEK_TEMPERATURE)
    return None


_MESSAGE_VERIF = "Réponds uniquement par le mot OK, sans rien ajouter."


def verifier_cle_fonctionnelle(fournisseur, cle, url_perso, modele_perso, settings):
    """Fait un VRAI appel minimal (un seul aller-retour, sans outils) au fournisseur
    DÉTECTÉ pour confirmer que la clé authentifie réellement — un format de clé
    valide n'est PAS une garantie qu'elle fonctionne (révoquée, expirée, mauvais
    projet/quota...). Appelée à l'ENREGISTREMENT (voir accounts.serializers) pour
    ne jamais accepter en silence une clé qui échouerait ensuite au premier
    message de l'utilisateur. Renvoie (ok: bool, message_erreur: str|None) — le
    message est déjà présentable au client, jamais un détail technique brut."""
    adaptateur = construire_adaptateur(fournisseur, cle, url_perso, modele_perso, settings)
    if adaptateur is None:
        return False, "Configuration incomplète : l'URL et le modèle personnalisés sont requis ensemble."
    try:
        texte, _tool_calls, _tin, _tout = adaptateur.appeler(
            _MESSAGE_VERIF, [{"role": "user", "content": "Test de connexion."}], [], True)
    except ErreurAppelLLM as e:
        if e.status_code in (401, 403):
            return False, "Clé refusée par le fournisseur (invalide, expirée ou révoquée)."
        if e.status_code == 404:
            return False, "Modèle introuvable chez ce fournisseur — vérifiez le nom du modèle personnalisé."
        if e.status_code == 429:
            return False, "Quota ou limite de facturation atteinte chez ce fournisseur pour cette clé."
        logger.warning("Échec de vérification d'une clé IA perso : %s", e)
        return False, "Le fournisseur a refusé la requête de test."
    except requests.RequestException:
        return False, "Impossible de joindre ce fournisseur (réseau ou délai dépassé)."
    if not texte:
        return False, "Le fournisseur a répondu sans contenu exploitable."
    return True, None
