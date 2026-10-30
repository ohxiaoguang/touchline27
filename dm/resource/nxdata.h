#ifndef NXDATA_H
#define NXDATA_H
#include <stddef.h>
#include <stdint.h>
#include <sys/types.h>
/* Immutable index; concurrent lookup/read supported. Close requires quiescent callers.
 * Errors use errno: ENOENT, ENOTDIR, EISDIR, EINVAL, EBADMSG, ENOTSUP, ENOMEM, I/O.
 * Open validates all index structure. Payload CRCs are verified on demand.
 * One cached decoded block per archive (<=1 MiB); serialized cache access.
 * The archive must not be modified/replaced in place while open. */
typedef struct nxdata nxdata;
typedef struct { const char *path; uint64_t size; int directory; } nxdata_info;
int nxdata_open(const char *path, nxdata **out);
void nxdata_close(nxdata *a);
int nxdata_find(const nxdata *a, const char *path, uint64_t *entry);
int nxdata_stat(const nxdata *a, uint64_t entry, nxdata_info *out);
ssize_t nxdata_read(nxdata *a, uint64_t entry, void *buf, size_t len, int64_t offset);
/* Cursor initially 0. Immediate children only; returns 1/0/-1 (entry/end/error).
 * Paths and stat strings borrow the archive index, valid until close. */
int nxdata_next(const nxdata *a, uint64_t directory, uint64_t *cursor, nxdata_info *out);
/* A read-only descriptor to reserve a host handle number; caller closes it. */
int nxdata_dup(const nxdata *a);
size_t nxdata_cache_bytes(const nxdata *a);
#endif
