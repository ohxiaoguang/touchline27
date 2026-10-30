// SPDX-License-Identifier: MIT
#ifndef NXROM_H
#define NXROM_H
#include <stdint.h>
#include <stddef.h>
#include <sys/types.h>
typedef struct nxrom nxrom;
typedef struct { const char *path; uint64_t size; int directory; } nxrom_info;
/* All paths are UTF-8, case sensitive and relative to the mount root. No '..'.
 * errno distinguishes missing paths, invalid arguments, unsupported formats,
 * corrupt data and physical I/O. error contains a key-free diagnostic at open.
 * Immutable mounts support concurrent reads. Close requires quiescent callers.
 * No disk extraction/cache. Source files must remain immutable while mounted. */
int nxrom_open(const char *base, const char *update, const char *keys,
               uint64_t expected_title, nxrom **out, char *error, size_t capacity);
/* Independent directory backend for tools/tests; HLE keeps its established
 * APFS case-alias/overlay directory backend for backwards compatibility. */
int nxrom_directory(const char *root, nxrom **out);
void nxrom_close(nxrom *fs);
int nxrom_find(const nxrom *fs, const char *path, uint64_t *id);
int nxrom_stat(const nxrom *fs, uint64_t id, nxrom_info *info);
ssize_t nxrom_read(nxrom *fs, uint64_t id, void *buffer, size_t size, int64_t offset);
int nxrom_next(const nxrom *fs, uint64_t dir, uint64_t *cursor, nxrom_info *info);
int nxrom_dup(const nxrom *fs);
uint64_t nxrom_title(const nxrom *fs);
/* Verified CNMT identity, shared by the packager and both launchers. No title
 * arithmetic establishes ownership: application is read from the extended header.
 * DataPatch, multi-content AOC and nonstandard index mappings fail explicitly. */
typedef struct {
    uint64_t title, application;
    uint32_t version, required_version, type, index;
} nxrom_content;
int nxrom_content_meta(const char *path, const char *keys, nxrom_content *content,
                       char *error, size_t capacity);
int nxrom_open_aoc(const char *path, const char *keys, uint64_t application,
                   uint32_t application_version, nxrom **out, char *error, size_t capacity);
/* Validate readable file headers. Ordinary payload is allowed; standalone guest
 * executables need module collection/rewriting, and are reported explicitly.
 * Payload integrity remains checked by nxrom_read on every accessed IVFC block. */
int nxrom_validate_aoc(nxrom *fs, char *error, size_t capacity);
size_t nxrom_romfs_cache_size(const nxrom *fs);
/* Compare one prepared module against its NSO header in the selected ExeFS. */
int nxrom_check_build(nxrom *fs, const char *module, const char *first16hex);
/* ---- Front ends: lightweight resource discovery (read-only probes) ----
 * Both Apple launchers share one scan, pairing and verification path; these are
 * the only container facts they need beyond nxrom_open itself. Probes read the
 * container table and NCA headers only: no payload, no extraction, no copy. */
#define NXROM_NSP 1
#define NXROM_XCI 2
/* Identify one candidate file. *format is NXROM_NSP or NXROM_XCI as soon as the
 * file's own container table says so (the extension is never consulted).
 * The programs, patched and title outputs describe the Program NCA: patched means
 * its RomFS is a PatchRomFS (BKTR), which is how an update package is told from a
 * base game. Returns 0, or -1 with errno: ENOTSUP (not a container this reader
 * knows), ENOENT (a container without Program NCA: DLC, metadata only), EACCES
 * (keys missing or unusable), EBADMSG (damaged table). error is key-free. */
int nxrom_probe_container(const char *path, const char *keys, int *format, int *programs,
                          int *patched, uint64_t *title, char *error, size_t capacity);
/* Does this file carry the entries a Program NCA needs (header_key plus a
 * key_area_key_* or titlekek_*)? Names only: no key value is ever read out. */
int nxrom_keys_usable(const char *path, char *error, size_t capacity);
/* Verify a selection against the caller's prepared modules (module name and its
 * 32-digit Build ID, from the rewriter tables). Any mismatch fails: a selection
 * for another build is never accepted, and the highest version is never guessed. */
int nxrom_verify(const char *base, const char *update, const char *keys, uint64_t title,
                 const char *const *modules, const char *const *builds, size_t count,
                 char *error, size_t capacity);
#endif
