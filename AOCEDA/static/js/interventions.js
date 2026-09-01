(function () {
  'use strict';

  // 1. Protection Auth
  const token = localStorage.getItem('aoceda_access_token');
  if (!token && window.location.pathname.indexOf('/auth/') === -1) {
    window.location.href = '/auth/';
    return;
  }

  const $ = id => document.getElementById(id);

  /* ── Thème clair / sombre (bouton présent dans le header, non câblé
     jusqu'ici : cliquer ne faisait rien sur cette page). ── */
  const ICON_MOON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
  const ICON_SUN = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/></svg>';
  const themeToggleBtn = $('theme-toggle');
  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    if (themeToggleBtn) themeToggleBtn.innerHTML = theme === 'light' ? ICON_MOON : ICON_SUN;
  }
  applyTheme(document.documentElement.getAttribute('data-theme') || 'light');
  if (themeToggleBtn) themeToggleBtn.addEventListener('click', () => applyTheme(window.AOCEDA.toggleTheme()));

  // Éléments DOM
  const interventionsContainer = $('interventions-container');
  const modalOverlay = $('modal-overlay');
  const btnOpenModal = $('btn-open-modal');
  const btnCloseModal = $('btn-close-modal');
  const btnCancelModal = $('btn-cancel-modal');
  const formIntervention = $('form-intervention');
  const modalTitleText = $('modal-title-text');
  const typeSelect = $('type-intervention');
  const descField = $('description-intervention');

  // Si non-null, la prochaine soumission du formulaire crée une intervention DE
  // SUIVI liée à cet id (« Signaler un problème persistant ») plutôt qu'une
  // déclaration de panne standard.
  let pendingOrigineId = null;

  // Traductions des types et statuts d'intervention
  const typeLabels = {
    'INSTALLATION': 'Installation de capteur',
    'CALIBRATION': 'Calibration de capteur',
    'PANNE': 'Déclaration de panne / Dysfonctionnement',
    'MAINTENANCE': 'Maintenance de l\'installation'
  };

  const statusLabels = {
    'EN_ATTENTE': 'En attente de prise en charge',
    'EN_COURS': 'En cours d\'intervention',
    'TERMINEE': 'Intervention terminée',
    'ANNULEE': 'Annulée'
  };

  const statusClasses = {
    'EN_ATTENTE': 'status-pending',
    'EN_COURS': 'status-active',
    'TERMINEE': 'status-done',
    'ANNULEE': 'status-cancelled'
  };

  // Charger les interventions
  function loadInterventions() {
    interventionsContainer.innerHTML = `
      <div style="text-align:center;padding:48px 0;color:var(--tx-s,#666)">
        Chargement de vos interventions...
      </div>
    `;

    window.AOCEDA.authFetch('/api/sensors/interventions/')
      .then(res => {
        if (!res.ok) throw new Error('Erreur lors du chargement');
        return res.json();
      })
      .then(data => {
        const list = window.AOCEDA.asList(data);
        if (list.length === 0) {
          interventionsContainer.innerHTML = `
            <div style="text-align:center;padding:48px 0;color:var(--tx-s,#666);border:1px dashed var(--bd-s,#E5E7EB);border-radius:12px">
              Aucune intervention enregistrée pour le moment.
            </div>
          `;
          return;
        }

        interventionsContainer.innerHTML = '';
        list.forEach(item => {
          const card = document.createElement('div');
          card.className = 'inter-card';
          
          const dateStr = item.dateIntervention
            ? new Date(item.dateIntervention).toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
            : 'Non planifiée';

          const typeText = typeLabels[item.typeIntervention] || item.typeIntervention;
          const statusText = statusLabels[item.statut] || item.statut;
          const statusClass = statusClasses[item.statut] || 'status-cancelled';

          // Rapport disponible
          let pdfBtnHtml = '';
          if (item.statut === 'TERMINEE' && item.rapport) {
            pdfBtnHtml = `
              <button class="btn-pdf" data-id="${item.id}" type="button">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                Télécharger le Rapport (PDF)
              </button>
            `;
          }

          const techName = item.technicien_nom || 'Technicien assigné d\'office';
          const techPhoneHtml = item.technicien_telephone
            ? ` · <a href="tel:${item.technicien_telephone.replace(/\s+/g, '')}" style="color:inherit">${item.technicien_telephone}</a>`
            : '';

          // Planification : bandeau visible tant que l'intervention n'est pas finale.
          let plannedHtml = '';
          if (item.dateProgrammee && (item.statut === 'EN_ATTENTE' || item.statut === 'EN_COURS')) {
            const dp = new Date(item.dateProgrammee).toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
            plannedHtml = `
              <div class="ic-planned">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
                Intervention prévue le ${dp}
              </div>
            `;
          }

          // Retour client : uniquement pertinent une fois l'intervention TERMINEE.
          const feedbackHtml = item.statut === 'TERMINEE' ? renderFeedback(item) : '';

          card.innerHTML = `
            <div class="ic-header">
              <span class="ic-type">${typeText}</span>
              <span class="status-badge ${statusClass}">${statusText}</span>
            </div>
            ${plannedHtml}
            <div class="ic-date">Date : ${dateStr}</div>
            <div class="ic-desc">${item.description || 'Aucune description fournie.'}</div>
            <div class="ic-footer">
              <span class="ic-tech">Assigné à : <strong>${techName}</strong>${techPhoneHtml}</span>
              ${pdfBtnHtml}
            </div>
            ${feedbackHtml}
          `;
          interventionsContainer.appendChild(card);
        });

        // Binder le téléchargement du PDF
        interventionsContainer.querySelectorAll('.btn-pdf').forEach(btn => {
          btn.addEventListener('click', function() {
            const id = this.getAttribute('data-id');
            downloadPDF(id);
          });
        });

        // Binder la sélection d'étoiles (retour client)
        interventionsContainer.querySelectorAll('.ic-feedback[data-feedback-id]').forEach(block => {
          const starsWrap = block.querySelector('.fb-stars');
          const submitBtn = block.querySelector('.fb-submit');
          if (!starsWrap || !submitBtn) return;
          const stars = Array.from(starsWrap.querySelectorAll('.fb-star'));
          stars.forEach(star => {
            star.addEventListener('click', function() {
              const n = Number(this.getAttribute('data-star'));
              starsWrap.setAttribute('data-selected', String(n));
              stars.forEach(s => s.classList.toggle('on', Number(s.getAttribute('data-star')) <= n));
              submitBtn.disabled = false;
            });
          });
          submitBtn.addEventListener('click', function() {
            const id = block.getAttribute('data-feedback-id');
            const note = Number(starsWrap.getAttribute('data-selected')) || 0;
            const commentaire = block.querySelector('.fb-comment').value;
            if (note < 1) return;
            submitFeedback(id, note, commentaire, submitBtn);
          });
        });

        // Binder « Signaler un problème persistant »
        interventionsContainer.querySelectorAll('.btn-signal').forEach(btn => {
          btn.addEventListener('click', function() {
            signalerPersistance(this.getAttribute('data-origine'));
          });
        });
      })
      .catch(err => {
        console.error(err);
        interventionsContainer.innerHTML = `
          <div style="text-align:center;padding:48px 0;color:var(--err,#C32D22)">
            Impossible de charger les interventions. Veuillez réessayer.
          </div>
        `;
      });
  }

  // Échappement minimal (le commentaire client est de la saisie libre).
  function escHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[c]);
  }

  // Bloc « Retour client » : formulaire de notation (1re visite) ou avis déjà
  // enregistré (lecture seule), + « Signaler un problème persistant ».
  function renderFeedback(item) {
    if (item.dateRetourClient) {
      const note = item.satisfactionClient;
      const stars = note ? '★'.repeat(note) + '☆'.repeat(5 - note) : '-';
      const comment = item.commentaireClient
        ? `<div style="margin-top:4px">${escHtml(item.commentaireClient)}</div>` : '';
      return `
        <div class="ic-feedback">
          <div class="fb-done">Votre avis : <span class="fb-stars-ro">${stars}</span>${comment}</div>
        </div>
      `;
    }
    return `
      <div class="ic-feedback" data-feedback-id="${item.id}">
        <span class="fb-label">Que pensez-vous de cette intervention ?</span>
        <div class="fb-stars" data-selected="0">
          ${[1, 2, 3, 4, 5].map(n => `<button type="button" class="fb-star" data-star="${n}" aria-label="${n} étoile(s)">★</button>`).join('')}
        </div>
        <input type="text" class="fb-comment" placeholder="Commentaire (facultatif)" maxlength="500">
        <div class="fb-row">
          <button type="button" class="fb-submit" disabled>Envoyer mon avis</button>
          <button type="button" class="btn-signal" data-origine="${item.id}">Signaler un problème persistant</button>
        </div>
      </div>
    `;
  }

  // Enregistre la note/commentaire du client sur une intervention TERMINEE.
  function submitFeedback(id, note, commentaire, btn) {
    btn.disabled = true;
    btn.textContent = 'Envoi…';
    window.AOCEDA.authFetch(`/api/sensors/interventions/${id}/retour/`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ satisfactionClient: note, commentaireClient: commentaire || '' })
    })
      .then(res => {
        if (!res.ok) throw new Error('Échec de l\'envoi du retour');
        return res.json();
      })
      .then(() => loadInterventions())
      .catch(err => {
        console.error(err);
        btn.disabled = false;
        btn.textContent = 'Envoyer mon avis';
        alert('Impossible d\'enregistrer votre avis. Réessayez.');
      });
  }

  // Ouvre la modale en mode « suivi » : crée une NOUVELLE intervention liée à
  // l'originale (interventionOrigine), sans jamais réécrire l'historique du
  // technicien (statut/résultat de l'intervention d'origine restent intacts).
  function signalerPersistance(originId) {
    pendingOrigineId = originId;
    if (modalTitleText) modalTitleText.textContent = 'Signaler un problème persistant';
    if (descField) descField.placeholder = 'Décrivez pourquoi le problème persiste malgré l\'intervention précédente.';
    if (typeSelect) {
      typeSelect.value = 'PANNE';
      typeSelect.disabled = true;
    }
    openModal();
  }

  // Télécharger le rapport PDF d'une intervention
  function downloadPDF(id) {
    const url = `/api/sensors/interventions/${id}/rapport/pdf/`;
    window.AOCEDA.authFetch(url)
      .then(res => {
        if (!res.ok) throw new Error('Téléchargement du rapport impossible');
        return res.blob();
      })
      .then(blob => window.AOCEDA.downloadBlob(blob, `rapport_intervention_${id}.pdf`))
      .catch(err => {
        console.error(err);
        alert("Impossible de télécharger le rapport d'intervention.");
      });
  }

  // Gestion de la modale
  function openModal() {
    modalOverlay.classList.add('active');
  }

  function closeModal() {
    modalOverlay.classList.remove('active');
    formIntervention.reset();
    pendingOrigineId = null;
    if (modalTitleText) modalTitleText.textContent = 'Déclarer une panne';
    if (descField) descField.placeholder = "Décrivez le problème rencontré (ex: le capteur n'affiche plus de consommation, voyant éteint...)";
    if (typeSelect) typeSelect.disabled = false;
  }

  btnOpenModal.addEventListener('click', openModal);
  btnCloseModal.addEventListener('click', closeModal);
  btnCancelModal.addEventListener('click', closeModal);
  modalOverlay.addEventListener('click', function(e) {
    if (e.target === modalOverlay) closeModal();
  });

  // Soumission du formulaire (anti double-soumission : bouton désactivé pendant
  // la requête, réactivé seulement en cas d'échec — un succès ferme la modale).
  formIntervention.addEventListener('submit', function(e) {
    e.preventDefault();
    const submitBtn = formIntervention.querySelector('.btn-submit');
    if (submitBtn.disabled) return;

    const typeIntervention = $('type-intervention').value;
    const description = $('description-intervention').value;
    const payload = { typeIntervention: typeIntervention, description: description };
    if (pendingOrigineId) payload.interventionOrigine = pendingOrigineId;

    submitBtn.disabled = true;
    submitBtn.textContent = 'Envoi…';

    window.AOCEDA.authFetch('/api/sensors/interventions/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    })
    .then(res => {
      if (!res.ok) throw new Error('Échec de la déclaration');
      return res.json();
    })
    .then(() => {
      closeModal();
      loadInterventions();
    })
    .catch(err => {
      console.error(err);
      alert('Impossible d\'enregistrer votre demande d\'intervention.');
    })
    .finally(() => {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Envoyer la demande';
    });
  });

  // Init
  loadInterventions();

})();
