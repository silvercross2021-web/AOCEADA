/* Page « Assistant IA » d'AOCEDA (aoceda-ia.html) : le gabarit commun (menu, en-tête, barre du bas) autour du cadre de
   l'assistant (/ia/assistant/, js/assistant.js).
   Gère la table d'alias canoniques (ACTION_MAP), la file d'attente pré-chargement d'iframe,
   le mode plein écran et la synchronisation synchrone du thème parent ↔ cadre. */
(function () {
  'use strict';

  const ICON_MOON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
  const ICON_SUN = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>';

  // Table de correspondance canonique entre les commandes de l'en-tête parent et les IDs du cadre
  const ACTION_MAP = {
    'nouvelle': 'nouvelle',
    'historique': 'btn_historique',
    'btn_historique': 'btn_historique',
    'options': 'btn_options',
    'btn_options': 'btn_options',
    'credits': 'btn_credits',
    'btn_credits': 'btn_credits',
    'plein_ecran': 'toggle_plein_ecran',
    'toggle_plein_ecran': 'toggle_plein_ecran'
  };

  let actionQueue = [];
  let iframePrete = false;

  function majIcone() {
    const b = document.getElementById('theme-toggle');
    if (b) b.innerHTML = document.documentElement.getAttribute('data-theme') === 'dark' ? ICON_SUN : ICON_MOON;
  }

  function synchroniserThemeCadre(themeParent) {
    try {
      const theme = themeParent || document.documentElement.getAttribute('data-theme') || 'light';
      const cadre = document.getElementById('assistant-cadre');
      const doc = cadre?.contentDocument || cadre?.contentWindow?.document;
      if (doc && doc.documentElement) {
        const themeAssistant = (theme === 'dark') ? 'sombre' : 'clair';
        doc.documentElement.setAttribute('data-theme', themeAssistant);
        doc.documentElement.dataset.theme = themeAssistant;
      }
    } catch (e) {
      /* cadre non accessible ou en cours de chargement */
    }
  }

  function basculerPleinEcran(forcer) {
    const conteneurApp = document.querySelector('.app') || document.body;
    const cadreZone = document.getElementById('assistant-page-cadre') || document.querySelector('.content.assistant-page');
    const btnPleinEcran = document.getElementById('btn_plein_ecran') || document.querySelector('[data-assistant="plein_ecran"]');
    const icAgrandir = btnPleinEcran ? btnPleinEcran.querySelector('.ic-agrandir') : null;
    const icReduire = btnPleinEcran ? btnPleinEcran.querySelector('.ic-reduire') : null;

    const estPleinActuel = conteneurApp.classList.contains('assistant-plein-ecran');
    const nouveauPlein = (typeof forcer === 'boolean') ? forcer : !estPleinActuel;

    conteneurApp.classList.toggle('assistant-plein-ecran', nouveauPlein);
    document.body.classList.toggle('assistant-plein-ecran', nouveauPlein);
    if (cadreZone) {
      cadreZone.classList.toggle('assistant-plein-ecran', nouveauPlein);
    }

    if (btnPleinEcran) {
      btnPleinEcran.setAttribute('aria-pressed', String(nouveauPlein));
      btnPleinEcran.title = nouveauPlein ? "Quitter le plein écran" : "Plein écran";
      if (icAgrandir && icReduire) {
        icAgrandir.style.display = nouveauPlein ? 'none' : '';
        icReduire.style.display = nouveauPlein ? '' : 'none';
      }
    }

    // Informer le cadre de la bascule plein écran
    try {
      const cadre = document.getElementById('assistant-cadre');
      const doc = cadre?.contentDocument || cadre?.contentWindow?.document;
      if (doc && doc.documentElement) {
        doc.documentElement.classList.toggle('mode-plein-ecran', nouveauPlein);
      }
    } catch (e) {}
  }

  function actionner(id) {
    const action = ACTION_MAP[id] || id;
    if (action === 'toggle_plein_ecran') {
      basculerPleinEcran();
      return;
    }

    const cadre = document.getElementById('assistant-cadre');
    if (!cadre) return;

    try {
      const doc = cadre.contentDocument || cadre.contentWindow?.document;
      if (doc && (doc.readyState === 'complete' || doc.readyState === 'interactive')) {
        const b = doc.getElementById(action);
        if (b) {
          b.click();
          return;
        }
      }
      // Iframe pas encore prête ou élément manquant à l'instant T : ajout en file d'attente
      actionQueue.push(action);
    } catch (e) {
      actionQueue.push(action);
    }
  }

  function viderFileAttente() {
    iframePrete = true;
    if (!actionQueue.length) return;
    const actions = actionQueue.slice();
    actionQueue = [];
    actions.forEach(action => actionner(action));
  }

  function attacherEcouteurIframe(cadre) {
    try {
      const doc = cadre.contentDocument || cadre.contentWindow?.document;
      if (doc) {
        doc.addEventListener('keydown', (e) => {
          if (e.key === 'Escape' || e.key === 'Esc') {
            basculerPleinEcran(false);
          }
        });
      }
    } catch (e) {}
  }

  document.addEventListener('DOMContentLoaded', () => {
    // Écouteurs sur les boutons d'en-tête dotés de data-assistant
    document.querySelectorAll('[data-assistant]').forEach(b => {
      b.addEventListener('click', () => actionner(b.dataset.assistant));
    });

    // Bouton flottant pour quitter le plein écran
    const btnQuitter = document.getElementById('btn_quitter_plein_ecran');
    if (btnQuitter) {
      btnQuitter.addEventListener('click', () => basculerPleinEcran(false));
    }

    // Raccourci clavier Échap pour restaurer l'affichage standard
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' || e.key === 'Esc') {
        const conteneurApp = document.querySelector('.app') || document.body;
        if (conteneurApp.classList.contains('assistant-plein-ecran')) {
          basculerPleinEcran(false);
        }
      }
    });

    majIcone();

    const btnTheme = document.getElementById('theme-toggle');
    if (btnTheme) {
      btnTheme.addEventListener('click', () => {
        if (window.AOCEDA && window.AOCEDA.toggleTheme) {
          window.AOCEDA.toggleTheme();
        }
        // Propagation synchrone immédiate vers le cadre
        setTimeout(() => synchroniserThemeCadre(), 10);
      });
    }

    // Observer les changements d'attribut data-theme sur document.documentElement
    new MutationObserver(() => {
      majIcone();
      synchroniserThemeCadre();
    }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

    // Gestion du chargement de l'iframe
    const cadre = document.getElementById('assistant-cadre');
    if (cadre) {
      cadre.addEventListener('load', () => {
        synchroniserThemeCadre();
        attacherEcouteurIframe(cadre);
        viderFileAttente();
      });
      // Si déjà prêt au moment du DOMContentLoaded
      try {
        const doc = cadre.contentDocument || cadre.contentWindow?.document;
        if (doc && (doc.readyState === 'complete' || doc.readyState === 'interactive')) {
          synchroniserThemeCadre();
          attacherEcouteurIframe(cadre);
          viderFileAttente();
        }
      } catch (e) {}
    }
  });

  // Export pour les tests automatisés
  window.AOCEDA_ASSISTANT_PAGE = {
    ACTION_MAP,
    actionner,
    basculerPleinEcran,
    synchroniserThemeCadre,
    getActionQueue: () => actionQueue,
    isIframePrete: () => iframePrete
  };
})();
