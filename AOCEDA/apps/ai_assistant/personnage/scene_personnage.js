// ════════════════════════════════════════════════════════════════════════════════════════════════════════
// Scène du personnage AOCEDA : la toile qui l'affiche dans une page, à la taille de son CONTENEUR (un carré).
//  - La toile est plus grande que le conteneur (marge) : oreilles, pastille et particules débordent sans être coupées ;
//    elle ne reçoit aucun clic (seul le conteneur, à la taille du personnage, en reçoit).
//  - Elle ne dessine que si le personnage est visible (onglet affiché, conteneur à l'écran et pas masqué) : aucun
//    calcul inutile sur un téléphone ou sur le PC qui sert aussi de serveur.
//  - placer(autreConteneur) : le personnage change de place en glissant (technique FLIP), sans réapparaître.
//  - Mêmes proportions que la galerie et le banc d'essai (CADRE 80 %, débord 0,108).
// ════════════════════════════════════════════════════════════════════════════════════════════════════════

// Images par seconde (audit du 09/10/2026 : la page prenait ~25 % d'un cœur du processeur SANS RIEN FAIRE, le
// personnage étant redessiné 60 fois par seconde même au repos ; sur téléphone, la batterie fondait) :
// en mouvement (geste, réaction, parole, écoute) : 60 ; au repos (il respire, cligne des yeux) : 24 ; mouvements
// réduits demandés par le système : 12.
const IPS_MOUVEMENT = 60, IPS_REPOS = 24, IPS_REDUIT = 12;

class ScenePersonnage {
  constructor(conteneur, o = {}) {
    this.perso = o.perso || new PersonnageAoceda();
    this.cadre = { e: 0.8, bas: 0.07 };
    this.marge = o.marge ?? 1.6;
    this.actif = true; this.visible = false; this.raf = 0; this.avant = 0; this.taille = 0; this.dpr = 1;
    this.auRepos = false; this.minuterie = 0;         // auRepos : posé par la page (Directeur) quand rien ne bouge
    this.reduit = ScenePersonnage.mouvementReduit;
    matchMedia("(prefers-reduced-motion: reduce)").addEventListener?.("change", (e) => { this.reduit = e.matches; });
    this.toile = document.createElement("canvas");
    this.toile.className = "perso-toile";
    this.toile.setAttribute("aria-hidden", "true");
    Object.assign(this.toile.style, { position: "absolute", left: "50%", top: "50%", transform: "translate(-50%, -50%)",
                                      pointerEvents: "none", display: "block" });
    this.ctx = this.toile.getContext("2d");
    this.io = new IntersectionObserver((e) => { this.visible = e[e.length - 1].isIntersecting; this.relancer(); });
    this.ro = new ResizeObserver(() => this.ajuster());
    document.addEventListener("visibilitychange", () => this.relancer());
    addEventListener("pointermove", (ev) => this.suivre(ev), { passive: true });
    this.placer(conteneur, false);
  }

  /** Mouvements réduits demandés par le système (accessibilité). */
  static get mouvementReduit() { return matchMedia("(prefers-reduced-motion: reduce)").matches; }

  /** Met le personnage dans un autre conteneur ; anime = il y glisse depuis sa place actuelle (ou depuis `depuis`, sa
   *  position mesurée AVANT un changement de mise en page). */
  placer(conteneur, anime = true, depuis = null) {
    if (!conteneur || conteneur === this.conteneur) return;
    const avant = !anime ? null : depuis || (this.toile.isConnected && this.taille ? this.toile.getBoundingClientRect() : null);
    if (this.conteneur) this.ro.unobserve(this.conteneur);
    this.conteneur = conteneur;
    if (getComputedStyle(conteneur).position === "static") conteneur.style.position = "relative";
    conteneur.appendChild(this.toile);
    this.ro.observe(conteneur);
    this.io.disconnect(); this.io.observe(conteneur);
    this.ajuster();
    if (!avant || !avant.width || ScenePersonnage.mouvementReduit) return;
    const apres = this.toile.getBoundingClientRect();
    if (!apres.width) return;
    const dx = avant.left + avant.width / 2 - (apres.left + apres.width / 2);
    const dy = avant.top + avant.height / 2 - (apres.top + apres.height / 2), k = avant.width / apres.width;
    this.toile.animate([{ transform: `translate(-50%, -50%) translate(${dx}px, ${dy}px) scale(${k})` },
                        { transform: "translate(-50%, -50%)" }], { duration: 560, easing: "cubic-bezier(.2, .8, .2, 1)" });
  }

  /** La toile suit la taille du conteneur (densité de pixels bornée à 2). */
  ajuster() {
    const t = this.conteneur.clientWidth;
    this.taille = t;
    if (!t) return;
    this.dpr = Math.min(2, devicePixelRatio || 1);
    const cote = Math.round(t * this.marge), px = Math.round(cote * this.dpr);
    this.toile.style.width = this.toile.style.height = cote + "px";
    // largeur ET hauteur : une toile neuve fait 300 x 150 ; à 125 % de zoom, 240 px x 1,25 = 300 tombait pile sur sa
    // largeur, la hauteur restait à 150 et la moitié basse du personnage était coupée (vu le 05/10/2026)
    if (this.toile.width !== px || this.toile.height !== px) { this.toile.width = px; this.toile.height = px; }
    this.relancer();
  }

  /** Centre du corps, en coordonnées de la page (t : taille du conteneur). */
  centre() {
    const r = this.conteneur.getBoundingClientRect(), t = r.width, e = this.cadre.e;
    return { x: r.left + t / 2, y: r.top + e * 0.518 * t + (1 - e) * t / 2 + this.cadre.bas * t, t };
  }

  /** Direction d'un élément de la page vu par le personnage : {angle (bord du corps -> cible), cote, regard}. */
  viser(el) {
    const c = this.centre(), e = el.getBoundingClientRect();
    const ex = e.left + e.width / 2, ey = e.top + e.height / 2, cote = ex >= c.x ? 1 : -1;
    const R = 0.3 * c.t * this.cadre.e;                   // mêmes mesures que le moteur (rx = 1,14 R)
    const borne = (v) => Math.max(-1, Math.min(1, v)), d = Math.max(c.t * 1.2, 160);
    return { angle: Math.atan2(ey - c.y, ex - (c.x + cote * 1.14 * R)), cote,
             regard: { x: borne((ex - c.x) / d), y: borne((ey - c.y) / d) } };
  }

  /** Les yeux suivent la souris (seulement si le personnage est à l'écran). */
  suivre(ev) {
    if (!this.visible || !this.taille) return;
    const c = this.centre(), d = Math.max(180, c.t * 2), b = (v) => Math.max(-1, Math.min(1, v));
    this.perso.regarderSouris(b((ev.clientX - c.x) / d), b((ev.clientY - c.y) / d));
  }

  pause(oui) { this.actif = !oui; this.relancer(); }
  doitTourner() { return this.actif && this.visible && !document.hidden && this.taille > 0; }
  relancer() {
    if (this.raf || this.minuterie || !this.doitTourner()) return;
    this.avant = performance.now();
    this.raf = requestAnimationFrame(() => this.image());
  }
  /** Cadence voulue maintenant (images par seconde). */
  cadence() { return this.reduit ? IPS_REDUIT : this.auRepos ? IPS_REPOS : IPS_MOUVEMENT; }
  /** Il se remet à bouger : l'image suivante part tout de suite (sans attendre la fin de la pause du repos). */
  accelerer() {
    if (!this.minuterie) return;
    clearTimeout(this.minuterie); this.minuterie = 0;
    this.relancer();
  }
  /** Image suivante : à la prochaine trame de l'écran en mouvement ; au repos, le navigateur DORT entre deux images
   *  (minuterie, pas 60 réveils par seconde pour rien). */
  suivante() {
    const ips = this.cadence();
    if (ips >= IPS_MOUVEMENT) { this.raf = requestAnimationFrame(() => this.image()); return; }
    this.minuterie = setTimeout(() => {
      this.minuterie = 0;
      if (!this.raf && this.doitTourner()) this.raf = requestAnimationFrame(() => this.image());
    }, Math.max(0, 1000 / ips - 16));
  }
  image() {
    this.raf = 0;
    if (!this.doitTourner()) return;
    const t = performance.now(), dt = Math.min(0.1, (t - this.avant) / 1000);   // 0,1 s au plus : à 12 images/s
    this.avant = t;                                                              // le mouvement garde sa vitesse
    this.perso.update(dt);
    this.dessiner();
    if (typeof this.apresImage === "function") this.apresImage();
    this.suivante();
  }
  dessiner() {
    const { ctx, dpr, taille: t } = this, e = this.cadre.e, decal = (t * this.marge - t) / 2, debord = t * 0.108;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, this.toile.width, this.toile.height);
    this.perso.particleOverhang = debord;
    ctx.setTransform(dpr * e, 0, 0, dpr * e, dpr * (decal + t * (1 - e) / 2), dpr * (decal + t * (1 - e) / 2 + this.cadre.bas * t));
    this.perso.draw(ctx, t, t - debord);
  }
}
