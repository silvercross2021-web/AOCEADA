/* ============================================================
   AOCEDA — Site vitrine : thème, effets, connexion démo
   ============================================================ */

/* ---------- Thème clair / sombre ---------- */
const root = document.documentElement;
const ttog = document.getElementById('ttog');
let theme = localStorage.getItem('aoceda-theme') || 'light';

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
if (ttog) ttog.addEventListener('click', () => applyTheme(theme === 'light' ? 'dark' : 'light'));

/* ---------- Navbar : état "scrolled" + menu mobile ---------- */
const nav = document.getElementById('nav');
const navLinks = document.getElementById('navLinks');
const burger = document.getElementById('navBurger');

function onScroll() {
  if (nav) nav.classList.toggle('scrolled', window.scrollY > 24);
}
window.addEventListener('scroll', onScroll, { passive: true });
onScroll();

if (burger && navLinks) {
  burger.addEventListener('click', () => {
    const open = navLinks.classList.toggle('open');
    burger.setAttribute('aria-expanded', open ? 'true' : 'false');
  });
  navLinks.querySelectorAll('a').forEach(a =>
    a.addEventListener('click', () => {
      navLinks.classList.remove('open');
      burger.setAttribute('aria-expanded', 'false');
    }));
}

/* ---------- Apparition au défilement (respecte prefers-reduced-motion) ---------- */
const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
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

/* ---------- Connexion démo en un clic ---------- */
const DEMO_ACCOUNTS = {
  client: {
    email: 'adjoua.konate@gmail.com',
    password: 'Password123!',
    redirect: '/dashboard/',
    label: 'Espace Client',
  },
  technicien: {
    email: 'moussa.diarrassouba@aoceda.ci',
    password: 'Password123!',
    redirect: '/technicien/',
    label: 'Espace Technicien',
  },
};

const demoStatus = document.getElementById('demoStatus');

function setDemoStatus(message, kind) {
  if (!demoStatus) return;
  demoStatus.textContent = message;
  demoStatus.className = 'demo-note' + (kind ? ' ' + kind : '');
}

document.querySelectorAll('.demo-btn[data-demo]').forEach(btn => {
  btn.addEventListener('click', async () => {
    const account = DEMO_ACCOUNTS[btn.dataset.demo];
    if (!account) return;

    const originalLabel = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Connexion en cours…';
    setDemoStatus('Connexion au compte de démonstration…');

    try {
      const res = await fetch('/api/auth/login/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: account.email, password: account.password }),
      });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      if (!data.access) throw new Error('Réponse de connexion invalide.');

      localStorage.setItem('aoceda_access_token', data.access);
      if (data.refresh) localStorage.setItem('aoceda_refresh_token', data.refresh);

      setDemoStatus('Connecté ! Ouverture de l’' + account.label + '…', 'ok');
      setTimeout(() => { window.location.href = account.redirect; }, 450);
    } catch (err) {
      btn.disabled = false;
      btn.textContent = originalLabel;
      setDemoStatus('Impossible de joindre le serveur de démonstration. Vérifiez que la plateforme est démarrée, puis réessayez.', 'err');
    }
  });
});
