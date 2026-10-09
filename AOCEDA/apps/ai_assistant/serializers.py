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
    return propre


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
