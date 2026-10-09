// Construit static/js/personnage.js, le personnage animé chargé par la page de l'assistant d'AOCEDA :
//   moteur d'animation de Coucou (code MIT © 2026 Louis Raillé, sources dans moteur/, converties en JavaScript simple)
//   + personnage AOCEDA (personnage_aoceda.js) + scène (scene_personnage.js),
// le tout dans une fonction fermée : rien ne fuit dans la page, sauf window.AocedaPersonnage.
// La page le charge avec ?v=<empreinte du fichier>, calculée par Django (dashboard.views.assistant_view) : le navigateur
// ne garde jamais une vieille copie, rien d'autre à mettre à jour.
//
//     node appsi_assistant\personnage\construire_personnage.js        (depuis le dossier AOCEDA ; Node.js 22 ou plus)
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { stripTypeScriptTypes } = require("node:module");

const ICI = __dirname, RACINE = path.resolve(ICI, "../../..");                 // dossier AOCEDA
const SORTIE = path.join(RACINE, "static", "js", "personnage.js");
const enJs = (fichier) => stripTypeScriptTypes(fs.readFileSync(path.join(ICI, "moteur", fichier), "utf8"), { mode: "transform" })
  .replace(/^\s*import[^;]*;\s*$/gm, "")                // un seul fichier : pas d'import
  .replace(/^export\s+/gm, "");                          // ni d'export

const anim = enJs("anim.ts");
const moteur = enJs("engine.ts")
  .replace(/^const BASE_TOP\b/m, "let BASE_TOP").replace(/^const BASE_BOTTOM\b/m, "let BASE_BOTTOM").replace(/^const INK\b/m, "let INK");
for (const v of ["let BASE_TOP", "let BASE_BOTTOM", "let INK"]) {
  if (!moteur.includes(v)) throw new Error("conversion inattendue : " + v + " introuvable");
}
const licence = fs.readFileSync(path.join(ICI, "moteur", "LICENSE"), "utf8").trim();
const personnage = fs.readFileSync(path.join(ICI, "personnage_aoceda.js"), "utf8");
const scene = fs.readFileSync(path.join(ICI, "scene_personnage.js"), "utf8");

const entete = `/*! Personnage animé de l'assistant AOCEDA.
 *  FICHIER GÉNÉRÉ par etudes/coucou/construire_personnage.js : ne pas le modifier à la main (modifier les sources).
 *  Moteur d'animation : Coucou, github.com/Louis-CFM/coucou (windows/src/mochi/engine.ts, core/anim.ts), sous licence
 *  MIT reproduite ci-dessous. Le personnage « Mochi », son nom, son apparence et ses sons (tous droits réservés) ne sont
 *  pas repris : personnage, chorégraphies, pastilles et scène AOCEDA.
 *
${licence.split("\n").map((l) => (" *  " + l).trimEnd()).join("\n")}
 */`;
const code = `${entete}
(() => {
"use strict";
${anim}
const Sound = { play() {} };                       // sons de Mochi : tous droits réservés -> jamais joués
${moteur}
function changerCouleurs(haut, bas, encre) { BASE_TOP = haut; BASE_BOTTOM = bas; INK = encre; }
${personnage}
${scene}
changerCouleurs(hexToRGB("#ffe07a"), hexToRGB("#f2b300"), "rgb(22,33,46)");   // couleurs AOCEDA
window.AocedaPersonnage = Object.freeze({ PersonnageAoceda, ScenePersonnage, ACTIONS_AOCEDA, changerCouleurs, hexToRGB });
})();
`;
fs.mkdirSync(path.dirname(SORTIE), { recursive: true });
fs.writeFileSync(SORTIE, code, "utf8");
const version = crypto.createHash("sha256").update(code).digest("hex").slice(0, 10);
console.log(`static/js/personnage.js écrit : ${code.length} caractères, empreinte ${version}`);
