"""Langues proposées dans le chatbot.

« auto » = le chatbot répond dans la langue du dernier message de l'utilisateur.
LANGUES : langues que DeepSeek parle directement (étape 1).
RELAIS : langues ivoiriennes que DeepSeek ne parle pas bien ; on passe par le français à l'aller et au retour
(étape 2 : dioula ; étape 3 : baoulé). Elles ne sont PAS dans LANGUES : la détection automatique du texte
(py3langid), les voix Microsoft et le contrôle de langue ne les connaissent pas et ne doivent pas les voir.
"""

# code : (nom en français, nom dans la langue, code pour la voix du navigateur en secours)
LANGUES = {
    "fr": ("Français", "Français", "fr-FR"),
    "en": ("Anglais", "English", "en-US"),
    "es": ("Espagnol", "Español", "es-ES"),
    "pt": ("Portugais", "Português", "pt-PT"),
    "de": ("Allemand", "Deutsch", "de-DE"),
    "it": ("Italien", "Italiano", "it-IT"),
    "nl": ("Néerlandais", "Nederlands", "nl-NL"),
    "ar": ("Arabe", "العربية", "ar-SA"),
    "sw": ("Swahili", "Kiswahili", "sw-KE"),
    "zh": ("Chinois", "中文", "zh-CN"),
    "ja": ("Japonais", "日本語", "ja-JP"),
    "ko": ("Coréen", "한국어", "ko-KR"),
    "hi": ("Hindi", "हिन्दी", "hi-IN"),
    "bn": ("Bengali", "বাংলা", "bn-IN"),
    "ru": ("Russe", "Русский", "ru-RU"),
    "uk": ("Ukrainien", "Українська", "uk-UA"),
    "pl": ("Polonais", "Polski", "pl-PL"),
    "tr": ("Turc", "Türkçe", "tr-TR"),
    "vi": ("Vietnamien", "Tiếng Việt", "vi-VN"),
    "th": ("Thaï", "ไทย", "th-TH"),
    "id": ("Indonésien", "Bahasa Indonesia", "id-ID"),
    "ro": ("Roumain", "Română", "ro-RO"),
    "el": ("Grec", "Ελληνικά", "el-GR"),
    "he": ("Hébreu", "עברית", "he-IL"),
    "sv": ("Suédois", "Svenska", "sv-SE"),
    "cs": ("Tchèque", "Čeština", "cs-CZ"),
    "hu": ("Hongrois", "Magyar", "hu-HU"),
}


RELAIS = {
    "dyu": ("Dioula", "Jula", None),
    "bci": ("Baoulé", "Wawle", None),
}


def valide(code):
    return code == "auto" or code in LANGUES or code in RELAIS


def est_relais(code):
    return code in RELAIS


def nom(code):
    return LANGUES[code][0] if code in LANGUES else RELAIS[code][0] if code in RELAIS else code


def liste_pour_page():
    return [{"code": "auto", "nom": "Automatique (même langue que vous)"}] + [
        {"code": c, "nom": f"{v[1]} ({v[0]})", "navigateur": None, "relais": True} for c, v in RELAIS.items()] + [
        {"code": c, "nom": f"{v[1]} ({v[0]})" if v[0] != v[1] else v[0], "navigateur": v[2]} for c, v in LANGUES.items()]
