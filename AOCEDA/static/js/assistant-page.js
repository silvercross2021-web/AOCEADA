/* Page « Assistant IA » d'AOCEDA (aoceda-ia.html) : le gabarit commun (menu, en-tête, barre du bas) autour du cadre de
   l'assistant (/ia/assistant/, js/assistant.js). Ici seulement ce que chaque page câble elle-même : les outils de
   l'assistant dans l'en-tête (Nouvelle / Historique / Options) et le bouton thème. Le thème est le MÊME pour tout AOCEDA
   (client-shell.js) ; l'assistant le suit, et quand on le change dans ses Options, l'icône de l'en-tête suit aussi. */
(function () {
  'use strict';
  const ICON_MOON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
  const ICON_SUN = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>';

  function majIcone() {
    const b = document.getElementById('theme-toggle');
    if (b) b.innerHTML = document.documentElement.getAttribute('data-theme') === 'dark' ? ICON_SUN : ICON_MOON;
  }

  /* Nouvelle / Historique / Options (à la place de la recherche) : le bouton du même nom dans la page de l'assistant
     (cadre), qui fait tout le reste (fenêtres, animations, conversation). data-assistant = son id. */
  function actionner(id) {
    try {
      const doc = document.getElementById('assistant-cadre').contentDocument;
      const b = doc && doc.getElementById(id);
      if (b) b.click();
    } catch (e) { /* cadre pas encore chargé */ }
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-assistant]').forEach(b => b.addEventListener('click', () => actionner(b.dataset.assistant)));
    majIcone();
    const b = document.getElementById('theme-toggle');
    if (b) b.addEventListener('click', () => { if (window.AOCEDA && window.AOCEDA.toggleTheme) window.AOCEDA.toggleTheme(); });
    // thème changé ici, par le système (mode auto) ou dans les Options de l'assistant : l'icône suit
    new MutationObserver(majIcone).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
  });
})();
