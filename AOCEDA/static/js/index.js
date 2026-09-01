/* ============================================================
   AOCEDA, Site vitrine : thème, hero vidéo, scrollytelling logo,
   effets, connexion démo
   ============================================================ */

const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/* ---------- Thème clair / sombre ---------- */
const root = document.documentElement;
const ttog = document.getElementById('ttog');
let theme = root.getAttribute('data-theme') || 'light';

function applyTheme(t) {
  root.setAttribute('data-theme', t);
  localStorage.setItem('aoceda-theme', t);
  theme = t;
  if (ttog) {
    ttog.setAttribute('aria-pressed', t === 'dark' ? 'true' : 'false');
    ttog.setAttribute('aria-label', t === 'dark' ? 'Activer le thème clair' : 'Activer le thème sombre');
  }
}
applyTheme(theme);
if (ttog) ttog.addEventListener('click', () => {
  // Fige un choix explicite (sort du mode « auto ») pour rester cohérent
  // avec les autres pages de la plateforme après connexion.
  localStorage.setItem('aoceda-theme-choice', theme === 'light' ? 'dark' : 'light');
  applyTheme(theme === 'light' ? 'dark' : 'light');
});

/* ---------- Navbar : état "scrolled" + menu mobile ---------- */
const nav = document.getElementById('nav');
const navLinks = document.getElementById('navLinks');
const burger = document.getElementById('navBurger');

if (burger && navLinks) {
  burger.addEventListener('click', () => {
    const open = navLinks.classList.toggle('open');
    burger.classList.toggle('open', open);
    burger.setAttribute('aria-expanded', open ? 'true' : 'false');
  });
  navLinks.querySelectorAll('a').forEach(a =>
    a.addEventListener('click', () => {
      navLinks.classList.remove('open');
      burger.classList.remove('open');
      burger.setAttribute('aria-expanded', 'false');
    }));
}

const clamp01 = v => Math.max(0, Math.min(1, v));

/* ============================================================
   SCÈNE IMMERSIVE — le film du logo AOCEDA scrubbé au défilement.
   La vidéo est épinglée pendant qu'on parcourt la longue scène ;
   sa timeline suit la progression du scroll, et chaque chapitre de
   texte apparaît/disparaît en douceur autour de son point (data-at).
   Le film étant ré-encodé tout-image-clé, le seek est instantané.
   ============================================================ */
const filmStage = document.querySelector('[data-film-stage]');
const film = document.getElementById('filmEl');
const filmBar = document.getElementById('filmBar');
const filmCue = document.getElementById('filmCue');
const fchapters = Array.from(document.querySelectorAll('.fchapter'));

const marks = fchapters.map(el => ({
  el,
  at: parseFloat(el.dataset.at || '0'),
  isHero: el.hasAttribute('data-hero'),
  isFinal: el.hasAttribute('data-final'),
}));

/* Affiche les chapitres en fonction de la progression p (0→1).
   Fenêtre d'apparition large (les chapitres se croisent en fondu) : aucun
   « trou » où plus aucun texte n'est visible entre deux points. */
function updateChapters(p) {
  for (const m of marks) {
    const half = m.isHero || m.isFinal ? 0.17 : 0.15;
    const dist = Math.abs(p - m.at);
    let o = clamp01(1 - dist / half);
    o = o * o * (3 - 2 * o); // smoothstep
    m.el.style.opacity = o.toFixed(3);
    m.el.style.transform = `translate3d(0,${((m.at - p) * 60).toFixed(1)}px,0)`;
    m.el.style.pointerEvents = o > 0.5 ? 'auto' : 'none';
  }
}

if (filmStage && film) {
  let duration = 0;
  let stageScroll = 0;
  let targetTime = 0;
  let shownTime = 0;
  let lastSeek = -1;
  let started = false;

  function recompute() {
    stageScroll = filmStage.offsetHeight - window.innerHeight;
  }

  /* Bascule en mode statique (pile verticale, film figé sur le logo final).
     N'est utilisé QUE si le navigateur ne peut réellement pas seeker dans
     la vidéo — c'est un repli technique, pas un choix esthétique. */
  function fallbackStatic(reason) {
    root.classList.add('film-static');
    marks.forEach(m => { m.el.style.opacity = 1; m.el.style.transform = 'none'; m.el.style.pointerEvents = 'auto'; });
    const poster = film.getAttribute('poster');
    if (poster) film.setAttribute('poster', poster.replace('logo-reveal-first', 'logo-reveal-poster'));
    try { film.currentTime = (film.duration || 10) - 0.05; } catch (e) {}
    if (filmCue) filmCue.classList.add('is-hidden');
    // eslint-disable-next-line no-console
    if (window.console) console.info('[AOCEDA] film scrub désactivé —', reason);
  }

  function onMeta() {
    duration = film.duration || 0;
    film.pause();
    try { film.currentTime = 0.001; } catch (e) {}
  }
  if (film.readyState >= 1) onMeta();
  film.addEventListener('loadedmetadata', onMeta);

  /* Certains navigateurs (mobiles surtout) n'exposent le rendu des frames
     qu'après un premier play() « débloquant ». On le tente en muet. */
  function unlock() {
    const pr = film.play();
    if (pr && pr.then) pr.then(() => film.pause()).catch(() => {});
  }

  /* Boucle de rendu : la timeline du film suit le défilement (scrub).
     Qualité + fluidité :
       - on vise `currentTime` EXACT (image nette) — la vidéo est tout-image-clé
         donc le seek exact est aussi rapide que fastSeek, mais sans flou ;
       - lissage adaptatif (rattrape vite les grands écarts, glisse fin près de
         la cible) → ni saut ni traînage ;
       - on ne relance un seek que si le précédent est terminé (`!film.seeking`)
         → on ne sature jamais le décodeur (cause n°1 des à-coups) ;
       - les chapitres suivent le temps LISSÉ (pas le scroll brut) → texte et
         image parfaitement synchronisés. */
  function loop() {
    const progress = clamp01(window.scrollY / (stageScroll || 1));
    if (duration) targetTime = progress * (duration - 0.05);

    const delta = targetTime - shownTime;
    const ad = Math.min(1, Math.abs(delta) * 1.6);       // 0→1 selon l'écart
    const k = 0.18 + 0.42 * ad;                          // 0.18 (fin) → 0.6 (rapide)
    shownTime += delta * k;
    if (Math.abs(delta) < 0.004) shownTime = targetTime; // snap anti-tremblement

    if (duration && film.readyState >= 2 && !film.seeking &&
        Math.abs(shownTime - lastSeek) > 0.018) {
      try { film.currentTime = shownTime; lastSeek = shownTime; } catch (e) {}
    }

    updateChapters(duration ? shownTime / (duration - 0.05) : progress);
    if (filmBar) filmBar.style.width = (progress * 100).toFixed(2) + '%';
    if (filmCue) filmCue.classList.toggle('is-hidden', progress > 0.02);

    requestAnimationFrame(loop);
  }

  function start() {
    if (started) return;
    started = true;
    recompute();
    window.addEventListener('resize', recompute, { passive: true });
    unlock();
    requestAnimationFrame(loop);
  }

  /* Vérifie que le seek est réellement possible (le serveur doit répondre
     aux requêtes Range). Sinon → repli statique propre. */
  function verifyThenStart() {
    start();
    // Laisse le temps au 1er buffer, puis contrôle que la vidéo est seekable.
    setTimeout(() => {
      const seekable = film.seekable && film.seekable.length && film.seekable.end(film.seekable.length - 1) > 0;
      if (!duration || !seekable) {
        // 2e chance : on force un petit préchargement puis on recontrôle.
        try { film.load(); } catch (e) {}
        setTimeout(() => {
          const ok = film.seekable && film.seekable.length && film.seekable.end(film.seekable.length - 1) > 0;
          if (!ok) fallbackStatic('vidéo non seekable (Range HTTP indisponible ?)');
        }, 1600);
      }
    }, 1400);
  }

  if (film.readyState >= 1) verifyThenStart();
  else film.addEventListener('loadedmetadata', verifyThenStart, { once: true });
  // Filet de sécurité : si les métadonnées ne chargent jamais, on démarre quand même.
  setTimeout(() => { if (!started) verifyThenStart(); }, 2500);

  /* ---------- Aimantation douce sur les chapitres ----------
     Quand on arrête de défiler DANS la scène du film, on glisse jusqu'au
     point du chapitre le plus proche → le texte s'affiche toujours pile en
     place, l'image nette. Gentle : ne s'active que si on est assez près
     (jamais de « yank » brutal), et jamais pendant un défilement continu. */
  if (!reduceMotion) {
    let snapTimer = null, snapping = false, rafSnap = 0;

    function easeTo(to, dur, done) {
      cancelAnimationFrame(rafSnap);
      const from = window.scrollY, dist = to - from, t0 = performance.now();
      const ease = t => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
      (function frame(now) {
        const t = Math.min(1, (now - t0) / dur);
        window.scrollTo(0, from + dist * ease(t));
        if (t < 1) rafSnap = requestAnimationFrame(frame); else if (done) done();
      })(performance.now());
    }

    function trySnap() {
      if (snapping || !stageScroll) return;
      const y = window.scrollY;
      if (y < 4 || y > stageScroll - 4) return;           // hors de la scène
      // cible = chapitre le plus proche (en px de défilement)
      let best = null, bd = Infinity;
      for (const m of marks) {
        const target = m.at * stageScroll;
        const d = Math.abs(target - y);
        if (d < bd) { bd = d; best = target; }
      }
      if (best == null || bd < 6) return;                 // déjà en place
      if (bd > window.innerHeight * 0.55) return;          // trop loin → laisse libre
      snapping = true;
      easeTo(best, 460, () => { snapping = false; });
    }

    window.addEventListener('scroll', () => {
      if (snapping) return;
      clearTimeout(snapTimer);
      snapTimer = setTimeout(trySnap, 150);               // après l'arrêt du scroll
    }, { passive: true });
    // Un geste utilisateur annule une aimantation en cours (on ne le bloque jamais)
    ['wheel', 'touchstart', 'keydown'].forEach(ev =>
      window.addEventListener(ev, () => { if (snapping) { snapping = false; cancelAnimationFrame(rafSnap); } }, { passive: true }));
  }
}

/* ============================================================
   BLOC IMMERSIF « Ce qu'AOCEDA fait pour vous » — la 2e vidéo studio
   joue EN BOUCLE en fond (elle anime le décor pendant qu'on lit le
   contenu qui se révèle). Lecture mise en pause hors écran (économie).
   ============================================================ */
const civVideo = document.getElementById('pillarsVideo');
if (civVideo && !reduceMotion) {
  civVideo.loop = true;
  const play = () => { const p = civVideo.play(); if (p && p.then) p.catch(() => {}); };
  // Ne joue que lorsque le bloc est à l'écran.
  const io = new IntersectionObserver((entries) => {
    entries.forEach(e => { if (e.isIntersecting) play(); else civVideo.pause(); });
  }, { threshold: 0.01 });
  const host = civVideo.closest('.content-immersive');
  if (host) io.observe(host); else play();
  document.addEventListener('visibilitychange', () => { if (!document.hidden) play(); });
} else if (civVideo && reduceMotion) {
  // Mouvement réduit : image fixe (poster), pas de lecture.
  civVideo.removeAttribute('autoplay');
}

/* ---------- Fil d'or : progression de lecture globale + nav scrolled ---------- */
const thread = document.getElementById('scrollThread');
let ticking = false;
function onScrollFrame() {
  ticking = false;
  const y = window.scrollY;
  const ribbon = document.getElementById('histoire');
  const triggerPoint = ribbon ? ribbon.offsetTop + ribbon.offsetHeight : 24;
  if (nav) nav.classList.toggle('scrolled', y > triggerPoint);
  if (thread) {
    const max = document.documentElement.scrollHeight - window.innerHeight;
    thread.style.transform = `scaleX(${max > 0 ? clamp01(y / max) : 0})`;
  }
}
window.addEventListener('scroll', () => {
  if (!ticking) { ticking = true; requestAnimationFrame(onScrollFrame); }
}, { passive: true });
window.addEventListener('resize', onScrollFrame, { passive: true });
onScrollFrame();

/* ---------- Apparition au défilement (respecte prefers-reduced-motion) ---------- */
if (reduceMotion) {
  document.querySelectorAll('.reveal').forEach(el => el.classList.add('in'));
} else {
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        e.target.classList.add('in');
        observer.unobserve(e.target);
      }
    });
  }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });
  document.querySelectorAll('.reveal').forEach(el => observer.observe(el));
}

