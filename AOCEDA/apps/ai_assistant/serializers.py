import json

from rest_framework import serializers

from .models import Conversation

# Historique AFFICHÉ d'une conversation (feuille Historique de la page, synchronisé entre les appareils du client) :
# ce que la page a montré, {role: "moi" | "ia", texte, langue?, fr?}. Ce n'est PAS la mémoire envoyée au modèle (gardée
# par le serveur seul : chatbot/conversation.py) : un client qui écrit ici ne peut rien glisser dans les consignes.
MAX_MESSAGES_PAR_FIL = 200
MAX_LONGUEUR_CONTENU = 8000
MAX_LONGUEUR_TITRE = 200


def _message_propre(m):
    """Un message affiché, borné. Accepte aussi l'ancien format de l'assistant d'AOCEDA ({role: user|assistant,
    content, lang}), converti : les conversations d'avant restent lisibles."""
    if not isinstance(m, dict):
        return None
    role = {"user": "moi", "assistant": "ia"}.get(m.get("role"), m.get("role"))
    texte = m.get("texte", m.get("content"))
    if role not in ("moi", "ia") or not isinstance(texte, str):
        return None
    propre = {"role": role, "texte": texte[:MAX_LONGUEUR_CONTENU]}
    if role == "ia":
        langue = m.get("langue") or {"dioula": "dyu"}.get(m.get("lang"), m.get("lang"))
        if isinstance(langue, str) and len(langue) <= 8:
            propre["langue"] = langue
        if isinstance(m.get("fr"), str) and m["fr"]:
            propre["fr"] = m["fr"][:MAX_LONGUEUR_CONTENU]
        cartes = cartes_propres(m.get("cartes"))
        if cartes:
            propre["cartes"] = cartes
    return propre


# Cartes de données montrées sous une réponse (19/10/2026 : « à chaque réponse un visuel », qui doit rester quand on
# rouvre la conversation). Seulement des cartes de LECTURE (jamais la carte Oui / Non d'une coupure, qui ne doit pas
# revenir active), bornées, et sans caractère capable de sortir d'un attribut HTML de la page.
TYPES_CARTES = {"conso", "repartition", "mensuel", "heures", "prevision", "credit", "alertes", "interventions", "capteurs",
                "facture"}
MAX_CARTES = 4
MAX_OCTETS_CARTE = 12000


def _valeur_propre(v, profondeur=0):
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)):
        return v if v == v and abs(v) < 1e15 else None          # ni NaN ni valeur absurde
    if isinstance(v, str):
        return "".join(c for c in v[:300] if c not in '"<>`\\')
    if profondeur >= 4:
        return None
    if isinstance(v, list):
        return [_valeur_propre(x, profondeur + 1) for x in v[:40]]
    if isinstance(v, dict):
        return {k[:40]: _valeur_propre(x, profondeur + 1) for k, x in list(v.items())[:40]
                if isinstance(k, str) and k.replace("_", "").isalnum()}
    return None


def cartes_propres(cartes):
    if not isinstance(cartes, list):
        return []
    out = []
    for c in cartes[:MAX_CARTES]:
        if not isinstance(c, dict) or c.get("type") not in TYPES_CARTES:
            continue
        propre = _valeur_propre(c)
        if len(json.dumps(propre, ensure_ascii=False)) <= MAX_OCTETS_CARTE:
            out.append(propre)
    return out


class ConversationSerializer(serializers.ModelSerializer):
    """Détail complet (avec messages) : lecture d'une conversation, création, mise à jour après chaque échange."""
    class Meta:
        model = Conversation
        fields = ['id', 'titre', 'messages', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_titre(self, value):
        return (value or "")[:MAX_LONGUEUR_TITRE]

    def validate_messages(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("messages doit être une liste.")
        propres = [_message_propre(m) for m in value[-MAX_MESSAGES_PAR_FIL:]]
        if any(m is None for m in propres):
            raise serializers.ValidationError("Chaque message doit être un objet {role: moi|ia, texte: texte}.")
        return propres

    def to_representation(self, instance):
        d = super().to_representation(instance)
        d["messages"] = [m for m in (_message_propre(x) for x in d.get("messages") or []) if m]
        return d


class ConversationListSerializer(serializers.ModelSerializer):
    """Version allégée pour la feuille Historique : titre, date, nombre de questions (pas le fil complet)."""
    questions = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = ['id', 'titre', 'updated_at', 'questions']
        read_only_fields = fields

    def get_questions(self, obj):
        return sum(1 for m in (obj.messages or []) if isinstance(m, dict) and m.get("role") in ("moi", "user"))
