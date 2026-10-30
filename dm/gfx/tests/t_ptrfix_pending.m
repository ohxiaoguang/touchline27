// Exercise actual replay dependency checks with synthetic interior bindings.
#include "../nvn/nvn_mtl.m"
uint64_t g_t0_ns;
int dm_guest_as_contains(uintptr_t a) { (void)a; return 0; }
void *front_metal_layer(void) { return NULL; }
module_t *module_of(const void *p) { (void)p; return NULL; }
module_t g_mod[MAX_MOD]; int g_nmod;
void svc_thread_dump(void) {}
uint64_t now_ns(void) { return bp_now(); }
static int checks, failures;
#define CHECK(label, expected, actual) do { checks++; if ((expected) != (actual)) { fprintf(stderr, "[RED] %s\n", label); failures++; } } while (0)
static void pending(uint64_t lo, uint64_t n) {
    g_nubd = 0; memset(g_ubd_pf, 0, sizeof g_ubd_pf); g_ubd_wide = 0;
    if (n) { g_ubd[0].lo = lo; g_ubd[0].hi = lo + n; g_nubd = 1; ubd_pf_add(lo, lo + n); }
}
int main(void) { @autoreleasepool {
    mtl_init();
    size_t size = (size_t)getpagesize(); void *mem;
    if (posix_memalign(&mem, size, size)) return 2;
    memset(mem, 0, size); mtl_pool_add(mem, size); state_reset();
    uint64_t base = (uint64_t)(uintptr_t)mem;
    S.ssbo[0][0] = (p_bind_buf){.addr=base + size / 2, .size=128};
    NvShader *sh = [NvShader new]; sh->pf_pool_slot=12; sh->pf_reg=0;
    sh->rf.nb=1; sh->rf.b[0]=(nvn_rbind){.kind=NVN_RB_SBUFP, .reg=0};
    pending(base + 64, 16);
    CHECK("indirect read sees pending bytes before instance origin", 1, ubd_conflict_sh(sh, 0));
    sh->pf_pool_slot=0;
    CHECK("ordinary binding does not broaden its range", 0, ubd_conflict_sh(sh, 0));
    sh->pf_pool_slot=12;
    pending(base + size / 2 + 8, 16);
    CHECK("pending bytes in instance binding still conflict", 1, ubd_conflict_sh(sh, 0));
    pending(base, 4);
    CHECK("pool lower endpoint is covered", 1, ubd_conflict_sh(sh, 0));
    pending(base + size, 4);
    CHECK("unrelated pending bytes do not conflict", 0, ubd_conflict_sh(sh, 0));
    pending(0, 0);
    CHECK("no updates need no landing", 0, ubd_conflict_sh(sh, 0));
    uint64_t a=ptrfix_slot(base, size), b=ptrfix_slot(base, size / 2);
    CHECK("same base with changed extent has immutable parameters", 1, a != b);
    CHECK("identical window reuses immutable parameters", a, ptrfix_slot(base, size));
    mtl_pool_del(mem); mtl_drain(); free(mem);
    printf("Pointer dependency regression: %d checks, %d failures\n", checks, failures);
    return failures != 0;
} }
