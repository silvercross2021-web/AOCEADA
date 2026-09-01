# pyrefly: ignore [untyped-import]
from django.urls import path
from .views import (
    AIChatView, AIChatAudioView, TranslateDioulaView,
    ConversationListCreateView, ConversationDetailView,
)

urlpatterns = [
    path('chat/', AIChatView.as_view(), name='ai_chat'),
    path('chat-audio/', AIChatAudioView.as_view(), name='ai_chat_audio'),
    path('translate-dioula/', TranslateDioulaView.as_view(), name='ai_translate_dioula'),
    path('conversations/', ConversationListCreateView.as_view(), name='ai_conversations'),
    path('conversations/<uuid:id>/', ConversationDetailView.as_view(), name='ai_conversation_detail'),
]
