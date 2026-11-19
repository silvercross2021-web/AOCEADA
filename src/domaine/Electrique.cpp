#include "domaine/Electrique.h"
#include "config/Reglages.h"
#include <math.h>

namespace Electrique {

namespace {
constexpr float DEUX_PI = 6.28318530718f;
}

float tensionSecteurV(float tSecondes, float microVariationV) {
  float ondeLente = 3.2f * sinf(DEUX_PI * tSecondes / 30.0f) +
                    1.1f * cosf(DEUX_PI * tSecondes / 11.0f);
  float u = Reglages::TENSION_NOMINALE_V + ondeLente + microVariationV;
  if (u < Reglages::TENSION_MIN_V)
    u = Reglages::TENSION_MIN_V;
  if (u > Reglages::TENSION_MAX_V)
    u = Reglages::TENSION_MAX_V;
  return u;
}

float courantA(float secteur, float bruit) {
  float pNette = secteur - bruit;
  if (pNette < 0.0f)
    pNette = 0.0f;
  return Reglages::K * sqrtf(pNette);
}

float puissanceW(float tensionV, float courant) { return tensionV * courant; }

} // namespace Electrique
