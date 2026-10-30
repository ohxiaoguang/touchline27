// ROMFS mod overlay over an external container (NSP / gamecard) unit test: includes hle_fs.c
// directly and calls its static implementation, the same way t_fs.c does.
// The container backend is nxrom_directory() (the reader's own directory backend), so the test needs
// no real container and no keys: what is under test is the HLE layer's overlay dispatch, not nxrom.
// Expectations are written by hand from the semantics, not by calling the implementation:
//   (1) a mod file replaces the same container path; a path no mod has still comes from the container;
//   (2) a file only the mod has is readable and appears in the directory listing of a path that only
//       the container has (the merge), and a same-named child is listed once, with the mod's size;
//   (3) a directory only the mod has can be opened and enumerated;
//   (4) lexical normalization (".", "//", "x/../x") works in front of the overlay;
//   (5) ".." above the mount root is refused, and a link inside the mod that points outside it is
//       never served (the container's answer is used instead);
//   (6) empty and missing mod roots leave every read on the game's own resources;
//   (7) binary and large files are served byte-exactly at arbitrary offsets;
//   (8) non-ASCII names and nested directories work;
//   (9) the mount stays read-only; reads without an overlay are unchanged.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include "../hle_fs.c"

struct dm_flags g_flag; uint64_t g_t0_ns; uint64_t now_ns(void) { return 0; }
void dm_guest_write_prepare(void *a, size_t n) { (void)a; (void)n; }

static int fails, checks;
#define CHECK(c, ...) do { checks++; if (!(c)) { fails++; printf("  ✗ "); } else printf("  ✓ "); printf(__VA_ARGS__); printf("\n"); } while (0)
static void wfile(const char *p, const void *buf, size_t n) {
    FILE *f = fopen(p, "wb"); if (!f) { printf("cannot write %s\n", p); exit(1); }
    if (n && fwrite(buf, 1, n, f) != n) { printf("short write %s\n", p); exit(1); }
    fclose(f);
}
static void wtext(const char *p, const char *s) { wfile(p, s, strlen(s)); }
static void make_dir(const char *p) {                       // mkdir -p
    char b[1400]; strlcpy(b, p, sizeof b);
    for (char *q = b + 1; *q; q++) if (*q == '/') { *q = 0; if (mkdir(b, 0755) && errno != EEXIST) { printf("cannot create %s\n", b); exit(1); } *q = '/'; }
    if (mkdir(b, 0755) && errno != EEXIST) { printf("cannot create %s\n", b); exit(1); }
}
static char *path(const char *base, const char *rest) {      // one reusable buffer per call site is enough here
    static char b[8][1600]; static int next;
    char *out = b[next++ & 7];
    snprintf(out, sizeof b[0], "%s/%s", base, rest);
    return out;
}

static nxrom *g_fs;
// Simulates what h_fs_MountRom does for DM_RESOURCE_BACKEND=nsp: mount the name, attach the container,
// then resolve the overlay roots (mod_attach). NULL means DM_ROMFS_OVERLAY is unset.
static void mount_container(const char *overlay) {
    g_nmnt = 0;
    if (overlay) setenv("DM_ROMFS_OVERLAY", overlay, 1); else unsetenv("DM_ROMFS_OVERLAY");
    if (mount("rom", "<external NSP>", 1) != RES_OK) { printf("mount failed\n"); exit(1); }
    g_mnt[0].container = g_fs;
    mod_attach("rom");
}
static int read_all(const char *p, char *out, size_t n) {
    uint64_t h; size_t got = 0; out[0] = 0;
    if (h_fs_OpenFile(&h, p, MODE_READ)) return 0;
    Result r = h_fs_ReadFile(&got, h, 0, out, n - 1);
    h_fs_CloseFile(h); out[got] = 0; return !r;
}
static int read_at(const char *p, char *out, size_t n, int64_t off, size_t *got) {
    uint64_t h; *got = 0; if (h_fs_OpenFile(&h, p, MODE_READ)) return 0;
    Result r = h_fs_ReadFile(got, h, off, out, n); h_fs_CloseFile(h); return !r;
}
static int64_t fsize(const char *p) {
    uint64_t h; int64_t n = -1;
    if (h_fs_OpenFile(&h, p, MODE_READ)) return -1;
    if (h_fs_GetFileSize(&n, h)) n = -2;
    h_fs_CloseFile(h); return n;
}
static int listing(const char *p, int mode, DirectoryEntry *out, int64_t max, int64_t *count) {
    uint64_t h; int64_t n = 0;
    if (h_fs_OpenDirectory(&h, p, mode)) return 0;
    Result r = h_fs_ReadDirectory(&n, out, h, max);
    h_fs_CloseDirectory(h); *count = n; return !r;
}
static const DirectoryEntry *find_ent(const DirectoryEntry *e, int64_t n, const char *name) {
    for (int64_t i = 0; i < n; i++) if (!strcmp(e[i].name, name)) return &e[i];
    return NULL;
}
static int entry_type(const char *p, int32_t want) { int32_t t = -1; return !h_fs_GetEntryType(&t, p) && t == want; }

int main(void) {
    char root[1024], base[1100], modroot[1300], outside[1100];
    const char *sp = getenv("TMPDIR");
    snprintf(root, sizeof root, "%s/t_fs_mod.XXXXXX", sp ? sp : "/private/tmp");
    if (!mkdtemp(root)) { perror("mkdtemp"); return 1; }
    snprintf(base, sizeof base, "%s/container", root);
    snprintf(modroot, sizeof modroot, "%s/mods/romfs", root);
    snprintf(outside, sizeof outside, "%s/outside", root);

    // ---- the container's view (what the external NSP/XCI holds) ----
    make_dir(root); make_dir(outside);
    const char *cdirs[] = {"dir", "newparent", "sub/deep"};
    for (int i = 0; i < 3; i++) make_dir(path(base, cdirs[i]));
    wtext(path(base, "same.txt"), "base-same");
    wtext(path(base, "a.txt"), "base-a");
    wtext(path(base, "dir/x.txt"), "base-x");
    wtext(path(base, "dir/only.txt"), "base-only");
    { unsigned char b[256]; for (int i = 0; i < 256; i++) b[i] = (unsigned char)i; wfile(path(base, "bytes.bin"), b, sizeof b); }
    { size_t N = 4u << 20; unsigned char *b = malloc(N);
      if (!b) return 1;
      for (size_t i = 0; i < N; i++) b[i] = (unsigned char)(i * 31 + (i >> 9));
      wfile(path(base, "sub/deep/large.bin"), b, N); free(b); }

    // ---- the mod's view (a player's mods/romfs folder) ----
    const char *mdirs[] = {"dir", "new/deep", "sub/deep", "中文 目录"};
    for (int i = 0; i < 4; i++) make_dir(path(modroot, mdirs[i]));
    wtext(path(modroot, "same.txt"), "mod-same");
    wtext(path(modroot, "dir/x.txt"), "mod-x");
    wtext(path(modroot, "dir/added.txt"), "mod-added");
    wtext(path(modroot, "new/deep/only.txt"), "mod-new");
    wtext(path(modroot, "中文 目录/文件 名.txt"), "中文内容");
    { unsigned char b[256]; for (int i = 0; i < 256; i++) b[i] = (unsigned char)(255 - i); wfile(path(modroot, "bytes.bin"), b, sizeof b); }
    { size_t N = (4u << 20) + 3; unsigned char *b = malloc(N);
      if (!b) return 1;
      for (size_t i = 0; i < N; i++) b[i] = (unsigned char)(i * 7 + 1);
      wfile(path(modroot, "sub/deep/large.bin"), b, N); free(b); }
    wtext(path(outside, "secret.txt"), "outside-secret");
    if (symlink("../outside/secret.txt", path(modroot, "escape.txt"))) { printf("cannot create the link\n"); return 1; }

    if (nxrom_directory(base, &g_fs)) { printf("cannot open the container stand-in: %s\n", strerror(errno)); return 1; }

    char buf[256];

    printf("① no overlay (DM_ROMFS_OVERLAY unset)\n");
    mount_container(NULL);
    CHECK(read_all("rom:/same.txt", buf, sizeof buf) && !strcmp(buf, "base-same"), "the container's file is read (same.txt=base-same)");
    { int64_t n = 0; DirectoryEntry e[64]; CHECK(listing("rom:/dir", DIRMODE_DIR | DIRMODE_FILE, e, 64, &n) && n == 2, "rom:/dir lists the container's 2 files (actually %lld)", (long long)n); }
    CHECK(fsize("rom:/bytes.bin") == 256, "the container's file size is reported");

    printf("② overlay active: hit, miss, added file, merged listing\n");
    char ovl[1300]; strlcpy(ovl, modroot, sizeof ovl);
    mount_container(ovl);
    CHECK(g_mnt[0].ovl_roots == 1, "the root is accepted (%d)", g_mnt[0].ovl_roots);
    CHECK(read_all("rom:/same.txt", buf, sizeof buf) && !strcmp(buf, "mod-same"), "the mod's file replaces the container's (same.txt=mod-same)");
    CHECK(read_all("rom:/a.txt", buf, sizeof buf) && !strcmp(buf, "base-a"), "a path no mod has still comes from the container (a.txt=base-a)");
    CHECK(read_all("rom:/dir/x.txt", buf, sizeof buf) && !strcmp(buf, "mod-x"), "a nested mod file replaces the container's (dir/x.txt=mod-x)");
    CHECK(read_all("rom:/dir/added.txt", buf, sizeof buf) && !strcmp(buf, "mod-added"), "a file only the mod has is readable (dir/added.txt)");
    CHECK(read_all("rom:/dir/only.txt", buf, sizeof buf) && !strcmp(buf, "base-only"), "the container's sibling file is unaffected (dir/only.txt)");
    CHECK(fsize("rom:/same.txt") == 8, "the size reported is the mod file's (8)");
    CHECK(entry_type("rom:/same.txt", ENT_FILE), "GetEntryType reports the mod file as a file");
    CHECK(entry_type("rom:/new", ENT_DIR), "GetEntryType reports a mod-only directory as a directory");
    CHECK(entry_type("rom:/dir", ENT_DIR), "GetEntryType reports a merged directory as a directory");
    { int64_t n = 0; DirectoryEntry e[64];
      CHECK(listing("rom:/dir", DIRMODE_DIR | DIRMODE_FILE, e, 64, &n) && n == 3, "rom:/dir lists 3 entries: the merged view (actually %lld)", (long long)n);
      const DirectoryEntry *x = find_ent(e, n, "x.txt"), *a = find_ent(e, n, "added.txt"), *o = find_ent(e, n, "only.txt");
      CHECK(x && x->size == 5, "x.txt is listed once with the mod's size (5)");
      CHECK(a && a->size == 9, "added.txt (mod only) is listed with its size (9)");
      CHECK(o && o->size == 9, "only.txt (container only) is still listed"); }
    { uint64_t h = 0; int64_t c = -1;
      CHECK(!h_fs_OpenDirectory(&h, "rom:/dir", DIRMODE_DIR | DIRMODE_FILE) && !h_fs_DirCount(&c, h) && c == 3,
            "GetDirectoryEntryCount agrees with the listing (3, actually %lld)", (long long)c);
      if (h) h_fs_CloseDirectory(h); }
    { int64_t n = 0; DirectoryEntry e[64];
      CHECK(listing("rom:/new/deep", DIRMODE_DIR | DIRMODE_FILE, e, 64, &n) && n == 1 && !strcmp(e[0].name, "only.txt"), "a mod-only directory enumerates on its own (new/deep: 1 entry)");
      CHECK(read_all("rom:/new/deep/only.txt", buf, sizeof buf) && !strcmp(buf, "mod-new"), "its file is readable (new/deep/only.txt=mod-new)"); }
    { int64_t n = 0; DirectoryEntry e[64];
      CHECK(listing("rom:/", DIRMODE_DIR | DIRMODE_FILE, e, 64, &n) && n == 8, "the RomFS root merges both views (6 container entries + new + 中文 目录, actually %lld)", (long long)n);
      CHECK(find_ent(e, n, "new") && find_ent(e, n, "same.txt"), "the root lists the mod-only directory and the replaced file once"); }

    printf("③ path normalization in front of the overlay\n");
    CHECK(read_all("rom:/dir/./x.txt", buf, sizeof buf) && !strcmp(buf, "mod-x"), "rom:/dir/./x.txt resolves to the mod file");
    CHECK(read_all("rom:/dir//x.txt", buf, sizeof buf) && !strcmp(buf, "mod-x"), "a doubled separator is harmless (rom:/dir//x.txt)");
    CHECK(read_all("rom:/dir/../same.txt", buf, sizeof buf) && !strcmp(buf, "mod-same"), "rom:/dir/../same.txt resolves to the mod file");
    CHECK(read_all("rom:/./dir/x.txt", buf, sizeof buf) && !strcmp(buf, "mod-x"), "rom:/./dir/x.txt resolves to the mod file");

    printf("④ non-ASCII names and nested directories\n");
    CHECK(read_all("rom:/中文 目录/文件 名.txt", buf, sizeof buf) && !strcmp(buf, "中文内容"), "a non-ASCII directory and file name are served from the mod");
    { int64_t n = 0; DirectoryEntry e[64];
      CHECK(listing("rom:/中文 目录", DIRMODE_FILE, e, 64, &n) && n == 1 && !strcmp(e[0].name, "文件 名.txt"), "the non-ASCII directory enumerates (1 file)"); }

    printf("⑤ path traversal and links out of the mod root\n");
    { char secret[64];
      CHECK(!read_all("rom:/../outside/secret.txt", secret, sizeof secret), "\"..\" above the mount root is refused");
      CHECK(!read_all("rom:/dir/../../outside/secret.txt", secret, sizeof secret), "a deeper \"..\" above the root is refused");
      CHECK(!read_all("rom:/escape.txt", secret, sizeof secret), "a link inside the mod that points outside it is not served");
      CHECK(!strstr(secret, "outside-secret"), "no bytes from outside the mod root were returned"); }
    CHECK(entry_type("rom:/escape.txt", ENT_FILE) == 0, "the escaping link is not even reported as an entry");

    printf("⑥ binary and large files are served byte-exactly\n");
    { unsigned char a[256]; size_t got = 0;
      CHECK(read_at("rom:/bytes.bin", (char *)a, sizeof a, 0, &got) && got == 256, "the whole 256-byte mod file is read (%zu)", got);
      int ok = 1; for (int i = 0; i < 256; i++) if (a[i] != (unsigned char)(255 - i)) { ok = 0; break; }
      CHECK(ok, "every byte matches the mod file (0x00/0xFF included)"); }
    { const size_t N = (4u << 20) + 3; unsigned char *a = malloc(65536);
      size_t total = 0; int ok = a != NULL;
      for (size_t off = 0; ok && off < N; off += 65536) {
          size_t want = N - off < 65536 ? N - off : 65536, got = 0;
          if (!read_at("rom:/sub/deep/large.bin", (char *)a, want, (int64_t)off, &got) || got != want) { ok = 0; break; }
          for (size_t i = 0; i < got; i++) if (a[i] != (unsigned char)((off + i) * 7 + 1)) { ok = 0; break; }
          total += got;
      }
      CHECK(ok, "a %zu-byte mod file read in 64 KiB chunks matches at every offset (%zu bytes read)", N, total);
      { size_t got = 0; CHECK(read_at("rom:/sub/deep/large.bin", (char *)a, 16, (int64_t)N - 8, &got) && got == 8, "a read that starts near the end returns exactly the remaining 8 bytes (%zu)", got); }
      { size_t got = 99; CHECK(read_at("rom:/sub/deep/large.bin", (char *)a, 16, (int64_t)N, &got) && got == 0, "a read at EOF returns 0 bytes, not an error"); }
      CHECK(fsize("rom:/sub/deep/large.bin") == (int64_t)N, "the size is the mod file's own, not the container's: %lld", (long long)fsize("rom:/sub/deep/large.bin"));
      free(a); }

    printf("⑦ the mount stays read-only\n");
    { uint64_t h;
      CHECK(h_fs_OpenFile(&h, "rom:/same.txt", MODE_WRITE) == RES_FAIL, "opening a mod file for writing fails");
      CHECK(h_fs_OpenFile(&h, "rom:/a.txt", MODE_WRITE) == RES_FAIL, "opening a container file for writing fails");
      CHECK(h_fs_CreateFile("rom:/newfile.txt", 0) == RES_FAIL, "CreateFile fails");
      CHECK(h_fs_DeleteFile("rom:/same.txt") == RES_FAIL, "DeleteFile fails");
      CHECK(h_fs_CreateDirectory("rom:/newdir") == RES_FAIL, "CreateDirectory fails"); }

    printf("⑧ empty and missing mod roots\n");
    { make_dir(path(root, "empty"));
      mount_container(path(root, "empty"));
      CHECK(read_all("rom:/same.txt", buf, sizeof buf) && !strcmp(buf, "base-same"), "an empty mod root: the container answers (same.txt=base-same)");
      CHECK(read_all("rom:/a.txt", buf, sizeof buf) && !strcmp(buf, "base-a"), "an empty mod root: other reads are unaffected");
      { int64_t n = 0; DirectoryEntry e[64]; CHECK(listing("rom:/dir", DIRMODE_DIR | DIRMODE_FILE, e, 64, &n) && n == 2, "an empty mod root: the listing is the container's (2)"); } }
    { char missing[1300]; strlcpy(missing, path(root, "no-such-mod-root"), sizeof missing);
      mount_container(missing);
      CHECK(g_mnt[0].ovl_roots == 0, "a missing mod root leaves the overlay off instead of failing the mount");
      CHECK(read_all("rom:/same.txt", buf, sizeof buf) && !strcmp(buf, "base-same"), "a missing mod root: the game's own resource is still read");
      CHECK(read_all("rom:/dir/added.txt", buf, sizeof buf) == 0, "a missing mod root: a mod-only file is not invented"); }

    printf("⑨ root resolution and root lists\n");
    { char sub[1200], cwd[1024];
      strlcpy(sub, path(root, "relwork"), sizeof sub); make_dir(sub);
      make_dir(path(sub, "mods/romfs"));
      wtext(path(sub, "mods/romfs/same.txt"), "rel-same");
      if (getcwd(cwd, sizeof cwd) && !chdir("/tmp")) {
          setenv("DM_ROOT", sub, 1);
          mount_container("mods/romfs");
          CHECK(read_all("rom:/same.txt", buf, sizeof buf) && !strcmp(buf, "rel-same"), "a relative root is found through DM_ROOT (same.txt=rel-same)");
          unsetenv("DM_ROOT"); if (chdir(cwd)) { }
      } }
    { char two[2600]; snprintf(two, sizeof two, "%s:%s", ovl, ovl);
      mount_container(two);
      CHECK(g_mnt[0].ovl_roots == 2, "a ':'-separated list is accepted (2 roots, actually %d)", g_mnt[0].ovl_roots);
      CHECK(read_all("rom:/same.txt", buf, sizeof buf) && !strcmp(buf, "mod-same"), "the first root wins when both have the path"); }

    nxrom_close(g_fs);
    printf("== %d checks, %d failed ==\n", checks, fails);
    return fails ? 1 : 0;
}
