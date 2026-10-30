// Regression test for the AudioOut machinery in dm/host/hle_audio.c.
//
// It includes the real implementation and drives it through the host's internal PCM output (dm_pcmout_*),
// which is the same queue / backend / release code the nn::audio take-overs use. The silent sink is used
// throughout, so the test needs no audio device and makes no sound.
//
// Covered here (the contract the games rely on):
//   1. six-channel output, the format FIFA 23 opens
//   2. two-channel output
//   3. every appended block is released exactly once, in append order, and can then be appended again
//   4. suspend / resume keeps consumption going (buffers keep being released) and comes back to a consumer
//   5. an output that is started but has no consumer at all is covered by the watchdog: it gets the silent
//      sink back instead of leaving the game's audio thread waiting for a buffer that never comes
//
// Build: make -C dm/host/tests GAME=<id> build/t_audio_compat
#include "../hle_audio.c"

#include <time.h>

// ---- the few host services hle_audio.c uses, stubbed for a standalone binary ----
static struct { const void *g; void *h; } g_map[64];
static pthread_mutex_t g_map_m = PTHREAD_MUTEX_INITIALIZER;
void *objmap_get(const void *g) { void *r = NULL; pthread_mutex_lock(&g_map_m); for (int i = 0; i < 64; i++) if (g_map[i].g == g) { r = g_map[i].h; break; } pthread_mutex_unlock(&g_map_m); return r; }
void objmap_put(const void *g, void *h) { pthread_mutex_lock(&g_map_m); for (int i = 0; i < 64; i++) if (!g_map[i].g) { g_map[i].g = g; g_map[i].h = h; break; } pthread_mutex_unlock(&g_map_m); }
void *objmap_del(const void *g) { void *r = NULL; pthread_mutex_lock(&g_map_m); for (int i = 0; i < 64; i++) if (g_map[i].g == g) { r = g_map[i].h; g_map[i].g = NULL; g_map[i].h = NULL; break; } pthread_mutex_unlock(&g_map_m); return r; }
uint64_t now_ns(void) { struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts); return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec; }
module_t *module_of(const void *p) { (void)p; return NULL; }
void hle_signal_system_event(void *g) { (void)g; }
void hle_bind_system_event(void *g, int autoclear) { (void)g; (void)autoclear; }
void dm_host_helper_qos(qos_class_t q) { (void)q; }
module_t g_mod[MAX_MOD];
int g_nmod;
uint64_t g_t0_ns;
struct dm_flags g_flag;

// ---- test plumbing ----
static int g_fail, g_checks;
static void check(int ok, const char *what) {
    g_checks++;
    if (!ok) { g_fail++; printf("  FAIL %s\n", what); }
    else printf("  ok   %s\n", what);
}
static void msleep(int ms) { usleep((useconds_t)ms * 1000); }

// Collect releases until n arrived or the deadline passes; returns how many arrived, in order, into out[]
static int drain(void *k, gbuf **out, int n, int ms) {
    int got = 0; uint64_t end = now_ns() + (uint64_t)ms * 1000000ull;
    while (got < n && now_ns() < end) {
        gbuf *b = dm_pcmout_released(k);
        if (b) out[got++] = b;
        else usleep(500);
    }
    return got;
}

static gbuf g_buf[16];

// Append n blocks of `bytes` bytes, then require that all of them come back in the same order.
static void round_trip(int ch, int n, int bytes, const char *tag) {
    printf("[%s] %d channel(s), %d blocks of %d bytes\n", tag, ch, n, bytes);
    void *k = dm_pcmout_open(ch);
    check(ao(k)->ch == ch, "channel count kept");
    dm_pcmout_start(k);
    check(ao(k)->backend == BK_NULL, "silent sink running");
    for (int i = 0; i < n; i++) {
        memset(&g_buf[i], 0, sizeof g_buf[i]);
        g_buf[i].ptr = calloc(1, (size_t)bytes); g_buf[i].cap = g_buf[i].size = (uint64_t)bytes;
        check(dm_pcmout_append(k, &g_buf[i]) == 1, "append accepted");
    }
    gbuf *out[16];
    int got = drain(k, out, n, 2000);
    check(got == n, "all appended blocks released");
    int in_order = got == n;
    for (int i = 0; i < got; i++) if (out[i] != &g_buf[i]) in_order = 0;
    check(in_order, "released in append order, exactly once");
    // Re-append what came back (the games reuse their buffers this way)
    for (int i = 0; i < got; i++) dm_pcmout_append(k, out[i]);
    got = drain(k, out, got, 2000);
    check(got == n, "re-appended blocks released again");
    // Nothing is left in the queue now: the sink must zero-fill and count it, not hand out a stale block
    uint64_t u0 = atomic_load(&ao(k)->under_n), b0 = atomic_load(&ao(k)->under_b);
    msleep(30);
    check(atomic_load(&ao(k)->under_n) > u0, "underrun counted once the queue runs dry");
    check(atomic_load(&ao(k)->under_b) > b0, "zero-padded bytes accounted for the underrun");
    dm_pcmout_close(k);
    for (int i = 0; i < n; i++) free(g_buf[i].ptr);
}

static void mix_impulses(void) {
    // Each input channel is isolated: centre reaches both speakers, LFE and the surrounds reach the side they belong to. The coefficients
    // are the host's audio renderer matrix (hle_audren.c) rather than ITU-R BS.775: centre and surrounds at -3 dB, LFE at -12 dB. Keeping
    // that matrix is what leaves the other six-channel games (Luigi's Mansion 3 among them) on the behaviour they were validated with.
    const int16_t input[6][6] = {{10000,0,0,0,0,0}, {0,10000,0,0,0,0},
        {0,0,10000,0,0,0}, {0,0,0,10000,0,0}, {0,0,0,0,10000,0}, {0,0,0,0,0,10000}};
    int16_t output[12]; downmix51(&input[0][0], output, 6, 6);
    const int expected[12] = {10000,0,0,10000,7070,7070,2509,2509,7070,0,0,7070};
    for (int i = 0; i < 12; i++) check(abs(output[i] - expected[i]) <= 1, "5.1 impulse routing");
    const int16_t loud[6] = {32767,-32768,0,0,32767,-32768};
    downmix51(loud, output, 1, 6);
    check(output[0] == 32767 && output[1] == -32768, "downmix saturates without wrapping");
}
int main(void) {
    mix_impulses();
    setvbuf(stdout, NULL, _IONBF, 0);
    unsetenv("DM_AUDIO");   // silent sink: no device, no sound
    printf("audio queue regression test (silent sink)\n\n");

    round_trip(6, 8, 6 * 2 * 256, "6ch");   // FIFA 23: 48 kHz, 6 channels, PCM16
    round_trip(2, 8, 2 * 2 * 256, "2ch");

    printf("[suspend] consumption must continue while suspended\n");
    {
        void *k = dm_pcmout_open(6);
        dm_pcmout_start(k);
        for (int i = 0; i < 4; i++) { memset(&g_buf[i], 0, sizeof g_buf[i]); g_buf[i].ptr = calloc(1, 3072); g_buf[i].cap = g_buf[i].size = 3072; dm_pcmout_append(k, &g_buf[i]); }
        gbuf *out[16];
        check(drain(k, out, 4, 2000) == 4, "blocks released before suspend");
        dm_audio_suspend(1);
        for (int i = 0; i < 4; i++) g_buf[i].size = 3072, dm_pcmout_append(k, &g_buf[i]);
        check(drain(k, out, 4, 2000) == 4, "blocks still released while suspended");
        dm_audio_suspend(0);
        for (int i = 0; i < 4; i++) dm_pcmout_append(k, &g_buf[i]);
        check(drain(k, out, 4, 2000) == 4, "blocks released after resume");
        check(ao(k)->backend == BK_NULL, "a consumer is in place after resume (no AudioUnit on this host)");
        dm_pcmout_close(k);
        for (int i = 0; i < 4; i++) free(g_buf[i].ptr);
    }

    printf("[watchdog] a started output with no consumer gets one back\n");
    {
        void *k = dm_pcmout_open(6);
        dm_pcmout_start(k);
        aout *a = ao(k);
        null_stop(a);                                    // as if the AudioUnit start had never taken: STARTED, backend BK_NONE
        check(atomic_load(&a->state) == STATE_STARTED && a->backend == BK_NONE, "simulated: started with no consumer");
        au_watchdog_start();
        msleep(200);
        check(a->backend == BK_NULL, "watchdog put the silent sink back");
        memset(&g_buf[0], 0, sizeof g_buf[0]); g_buf[0].ptr = calloc(1, 3072); g_buf[0].cap = g_buf[0].size = 3072;
        dm_pcmout_append(k, &g_buf[0]);
        gbuf *out[4];
        check(drain(k, out, 1, 2000) == 1, "buffers flow again (no spinning game thread)");
        dm_pcmout_close(k);
        free(g_buf[0].ptr);
    }

    printf("\n%d checks, %d failed\n", g_checks, g_fail);
    return g_fail ? 1 : 0;
}
