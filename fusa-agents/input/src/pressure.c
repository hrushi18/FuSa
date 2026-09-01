#include <stdint.h>
#include <string.h>

#define ADC_FULL_SCALE   4095u
#define PRESSURE_MAX_BAR  250u

static uint8_t buf[8];

uint16_t decode_pressure(const uint8_t *frame, uint32_t len) {
    if (frame == NULL || len < 2u || len > sizeof(buf)) {
        return 0u;                    /* invalid frame: report zero, status flag raised by caller */
    }
    memcpy(buf, frame, len);
    uint16_t raw = (uint16_t)(((uint16_t)frame[0] << 8) | (uint16_t)frame[1]);
    return (uint16_t)(((uint32_t)raw * PRESSURE_MAX_BAR) / ADC_FULL_SCALE);
}
