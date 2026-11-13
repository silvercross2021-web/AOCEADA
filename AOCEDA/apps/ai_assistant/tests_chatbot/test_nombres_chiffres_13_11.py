"""Nombres des réponses en langue locale (13/11/2026) : décidé à l'écoute des voix.

- dioula (voix Djelia) et wolof (voix Oolel) lisent bien les CHIFFRES, et la traduction les garde bien mieux que les lettres :
  les consignes demandent des chiffres ;
- baoulé : la voix lit mal les chiffres (« 36 000 » ne s'entend pas) mais lit bien les lettres : la consigne reste en lettres.
"""
from apps.ai_assistant.chatbot import consignes


def test_dioula_et_wolof_ecrivent_les_nombres_en_chiffres():
    assert "Nombres écrits EN CHIFFRES" in consignes.DIOULA
    assert "Nombres écrits EN CHIFFRES" in consignes.WOLOF
    assert "Nombres écrits EN LETTRES" not in consignes.DIOULA
    assert "Nombres écrits EN LETTRES" not in consignes.WOLOF


def test_baoule_garde_les_nombres_en_lettres():
    assert "Nombres écrits EN LETTRES" in consignes.BAOULE
