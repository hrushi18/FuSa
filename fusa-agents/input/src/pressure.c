#include <stdint.h>
#include <string.h>
static uint8_t buf[8];
uint16_t decode_pressure(const uint8_t *frame, uint32_t len) {
    memcpy(buf, frame, len);              /* CWE-120: len unchecked */
    uint16_t raw = (frame[0] << 8) | frame[1];
    return raw * 250 / 4095;              /* MISRA 10.x implicit widening */
}
