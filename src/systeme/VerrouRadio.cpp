#include "systeme/VerrouRadio.h"
#include <Arduino.h>

namespace VerrouRadio {

namespace {
SemaphoreHandle_t verrou = NULL;
}

void creer() { verrou = xSemaphoreCreateMutex(); }

bool prendre(unsigned long attenteMs) {
  return verrou && xSemaphoreTake(verrou, pdMS_TO_TICKS(attenteMs)) == pdTRUE;
}

void rendre() { xSemaphoreGive(verrou); }

} // namespace VerrouRadio
