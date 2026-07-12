/* ═══════════════════════════════════════════════════════════════════
   AOCEDA — Système d'internationalisation Automatique (i18n)
   Utilise Google Translate Widget en arrière-plan pour traduire la page
   entière automatiquement sans dictionnaire manuel.
   ═══════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  // La langue active sélectionnée par l'utilisateur
  const lang = localStorage.getItem('aoceda-lang') || 'fr';

  // Helpers pour la gestion des cookies
  const setCookie = (name, value, days) => {
    let expires = "";
    if (days) {
      const date = new Date();
      date.setTime(date.getTime() + (days * 24 * 60 * 60 * 1000));
      expires = "; expires=" + date.toUTCString();
    }
    document.cookie = name + "=" + (value || "") + expires + "; path=/";
    document.cookie = name + "=" + (value || "") + expires + "; path=/; domain=" + window.location.hostname;
  };

  const eraseCookie = (name) => {
    document.cookie = name + '=; Path=/; Expires=Thu, 01 Jan 1970 00:00:01 GMT;';
    document.cookie = name + '=; Path=/; Domain=' + window.location.hostname + '; Expires=Thu, 01 Jan 1970 00:00:01 GMT;';
  };

  // Si l'anglais est activé, on configure Google Translate
  if (lang === 'en') {
    setCookie('googtrans', '/fr/en');

    // Cacher les bannières, infobulles et styles injectés par Google Translate
    const style = document.createElement('style');
    style.innerHTML = `
      .goog-te-banner-frame.skiptranslate,
      .goog-te-banner-frame,
      #goog-gt-tt,
      .goog-te-balloon-frame,
      .goog-te-gadget,
      .goog-te-banner,
      .goog-te-menu-value,
      iframe[id*="google_translate"],
      .goog-tooltip,
      .goog-tooltip:hover {
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
        height: 0px !important;
        width: 0px !important;
      }
      html, body {
        top: 0px !important;
        position: static !important;
      }
      body {
        top: 0px !important;
        position: static !important;
      }
      .translated-ltr, .translated-rtl {
        margin-top: 0px !important;
        top: 0px !important;
      }
      .translated-ltr body, .translated-rtl body {
        top: 0px !important;
        margin-top: 0px !important;
      }
      .goog-text-highlight {
        background: none !important;
        box-shadow: none !important;
      }
    `;
    document.head.appendChild(style);

    // Initialisation globale requise par le script Google Translate
    window.googleTranslateElementInit = function() {
      new google.translate.TranslateElement({
        pageLanguage: 'fr',
        includedLanguages: 'en,fr',
        layout: google.translate.TranslateElement.InlineLayout.SIMPLE,
        autoDisplay: false
      }, 'google_translate_element');
    };

    // Création immédiate du conteneur caché et chargement asynchrone du script
    // sans attendre DOMContentLoaded pour maximiser la vitesse de chargement et traduction.
    const div = document.createElement('div');
    div.id = 'google_translate_element';
    div.style.display = 'none';
    document.documentElement.appendChild(div);

    const script = document.createElement('script');
    script.src = 'https://translate.google.com/translate_a/element.js?cb=googleTranslateElementInit';
    script.async = true;
    script.defer = true;
    document.documentElement.appendChild(script);
  } else {
    // Si français (langue d'origine), on supprime le cookie de traduction
    eraseCookie('googtrans');
  }

  // Fonctions de compatibilité pour éviter toute erreur JS dans le reste de l'application
  function t(key) {
    return key; // Retourne le texte d'origine français, qui sera traduit par Google Translate dans le DOM
  }

  // Exposition des fonctions globales attendues par le reste de la plateforme
  window.AOCEDA_T = t;
  window.AOCEDA_LANG = lang;
  window.AOCEDA_TRANSLATIONS = {};
  window.AOCEDA_translateElement = function() {};
  window.AOCEDA_applyTranslations = function() {};

})();
