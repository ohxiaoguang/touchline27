// Source reference: FPSLocker-Warehouse branch v4, FC 27 1.8c.fd45 config
// SaltySD/plugins/FPSLocker/patches/0100C49025D3E000/9636BCD68E2EF2C8.yaml
// File revision: ec9c0b4fe6043a1ff825627517ad3008e1b03e60 (MasaGratoR).
// Reference addresses / numeric budgets only; no YAML or MASTER_WRITE assembly
// block is included here. Pointer checks and C read/write handling are local code.
// No explicit upstream config license was located; permission/derivation review
// remains open. See docs/fpslocker-provenance.md before public release.
// FC 27 1.8c.fd45 only. Data-only equivalent of FPSLocker-Warehouse v4:
// the original regulator loads s8/s9 from RenderSettings +f8/+144 before
// storing them at regulator +c/+10. Keep that code and all its other fields.
#ifndef DM_FPSLOCK_FC27_H
#define DM_FPSLOCK_FC27_H
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#define FC27_BUILD "9636bcd68e2ef2c863194d76f308c98c"
typedef int (*fc27_io)(uint64_t, void *, size_t);
static int fc27_matches(const char *title, const char *build) {
    return !strcmp(title, "0100C49025D3E000") && !strcmp(build, FC27_BUILD);
}
static float fc27_ms(int fps) { return 1000.0f / fps; }
static int fc27_ptr(fc27_io read, uint64_t a, uint64_t *p) {
    return !(a & 7) && read(a, p, 8) && *p >= 0x1000 && !(*p & 7) && *p <= UINT64_MAX - 0x1500;
}
// Return a bit for each successfully corrected field, negative on a failed
// write. Zero/uninitialised objects are retried at the next game present.
static int fc27_field(fc27_io read, fc27_io write, uint64_t a, int wide, double value) {
    if (a & (wide ? 7 : 3)) return 0;
    double d; float f; size_t n = wide ? 8 : 4;
    void *p = wide ? (void *)&d : (void *)&f;
    if (!read(a, p, n)) return 0;
    double old = wide ? d : f;
    // RenderSettings +144 defaults to zero; FPSLocker overrides it as well.
    // NaN/Inf and implausible FPS/budgets are never treated as live fields.
    if (!(old >= (wide ? 5 : 0) && old <= 120) || old == (wide ? value : (double)(float)value)) return 0;
    d = value; if (!wide) f = (float)value;
    return write(a, p, n) ? 1 : -1;
}
static int fc27_tick(const char *title, const char *build, uint64_t base,
                     int fps, fc27_io read, fc27_io write) {
    if (!fc27_matches(title, build) || (fps != 30 && fps != 60) || base > UINT64_MAX - 0xde82028) return 0;
    uint64_t obj; int changed = 0, r;
    if (fc27_ptr(read, base + 0xda1ee38, &obj)) {
        r = fc27_field(read, write, obj + 8, 1, fps);
        if (r < 0) return -1;
        changed |= r;
    }
    // At 30 keep Frostbite's original budgets, including any scene overrides.
    if (fps == 30) return changed;
    if (fc27_ptr(read, base + 0xde82020, &obj)) {
        const unsigned off[] = {0xf8, 0x144};
        for (int i = 0; i < 2; i++) {
            r = fc27_field(read, write, obj + off[i], 0, fc27_ms(fps));
            if (r < 0) return -1;
            changed |= r << (1 + i);
        }
    }
    if (fc27_ptr(read, base + 0xde81da0, &obj) && fc27_ptr(read, obj + 0x14c8, &obj)) {
        for (int i = 0; i < 2; i++) {
            r = fc27_field(read, write, obj + 0xc + 4 * i, 0, fc27_ms(fps));
            if (r < 0) return -1;
            changed |= r << (3 + i);
        }
    }
    return changed;
}
#endif
