from rest_framework import serializers
from .models import Conversation

# Bornes du fil persisté : le frontend légitime n'envoie que des tours user/assistant
# courts, mais l'API est publique pour tout client authentifié — sans bornes, un fil
# arbitraire pourrait grossir sans limite en base (et ce contenu est rejoué comme
# historique au LLM, déjà re-validé côté AIChatView._valider_history : défense en
# profondeur des deux côtés).
MAX_MESSAGES_PAR_FIL = 200
MAX_LONGUEUR_CONTENU = 8000
# Langue RÉELLEMENT utilisée pour un message assistant (voir static/js/ia.js,
# finirTourIA) — permet de reconstruire l'affichage bilingue dioula à la
# réouverture d'un fil depuis l'Historique (voir openConversation) : le contenu
# persisté reste toujours le français (relu tel quel par le LLM), seule cette
# étiquette dit qu'il faut le retraduire à l'affichage.
LANGUES_MESSAGE_VALIDES = ('fr', 'en', 'dioula')


class ConversationSerializer(serializers.ModelSerializer):
    """Détail complet (avec messages) : lecture d'un fil, création, mise à jour."""
    class Meta:
        model = Conversation
        fields = ['id', 'titre', 'messages', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_messages(self, value):
        """N'accepte que des tours {role: user|assistant, content: str} bien formés ;
        contenu tronqué, nombre de messages borné (on garde la FIN du fil, la plus
        récente, comme le contexte LLM). Un `lang` optionnel (fr/en/dioula) est
        préservé UNIQUEMENT sur les messages assistant (voir LANGUES_MESSAGE_VALIDES
        ci-dessus) — ignoré silencieusement si absent/invalide, pour rester
        compatible avec les fils créés avant l'introduction de ce champ."""
        if not isinstance(value, list):
            raise serializers.ValidationError("messages doit être une liste.")
        propres = []
        for m in value[-MAX_MESSAGES_PAR_FIL:]:
            if not isinstance(m, dict) or m.get('role') not in ('user', 'assistant') \
                    or not isinstance(m.get('content'), str):
                raise serializers.ValidationError(
                    "Chaque message doit être un objet {role: user|assistant, content: texte}.")
            propre = {'role': m['role'], 'content': m['content'][:MAX_LONGUEUR_CONTENU]}
            if m['role'] == 'assistant' and m.get('lang') in LANGUES_MESSAGE_VALIDES:
                propre['lang'] = m['lang']
            propres.append(propre)
        return propres


class ConversationListSerializer(serializers.ModelSerializer):
    """Version allégée pour le panneau Historique : pas le fil complet (évite de
    transférer tout le contenu de chaque conversation juste pour afficher une liste),
    seulement un aperçu du dernier message de l'assistant."""
    apercu = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = ['id', 'titre', 'updated_at', 'apercu']
        read_only_fields = fields

    def get_apercu(self, obj):
        for m in reversed(obj.messages or []):
            if m.get('role') == 'assistant':
                contenu = m.get('content') or ''
                return contenu[:80] + '…' if len(contenu) > 80 else contenu
        return ''
