#define _POSIX_C_SOURCE 200809L
#include "nxdata.h"
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <pthread.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include <zlib.h>

#define INDEX_LIMIT (256u * 1024u * 1024u)
struct nxdata {
    int fd;
    uint32_t bs;
    uint64_t ne, nb;
    unsigned char *index, *blocks;
    char *paths;
    unsigned char *cache, *scratch;
    uint64_t cached;
    pthread_mutex_t lock;
};
static uint32_t u32(const unsigned char *p) {
    return (uint32_t)p[0] | (uint32_t)p[1]<<8 | (uint32_t)p[2]<<16 | (uint32_t)p[3]<<24;
}
static uint64_t u64(const unsigned char *p) { return u32(p) | (uint64_t)u32(p+4)<<32; }
static int bad(int e) { errno = e; return -1; }
static int read_at(int fd, void *buf, size_t len, uint64_t at) {
    while (len) {
        ssize_t n = pread(fd, buf, len, (off_t)at);
        if (n < 0) { if (errno == EINTR) continue; return -1; }
        if (!n) return bad(EIO);
        buf = (unsigned char *)buf+n; len -= (size_t)n; at += (size_t)n;
    }
    return 0;
}
/* Strict UTF-8: reject overlongs, surrogate code points and > U+10FFFF. */
static int valid_utf8(const unsigned char *s, size_t n) {
    size_t i = 0;
    while (i < n) {
        uint32_t c = s[i++], min; unsigned k;
        if (c < 128) { if (!c) return 0; continue; }
        if (c >= 0xc2 && c <= 0xdf) { k=1; min=128; c &= 31; }
        else if (c >= 0xe0 && c <= 0xef) { k=2; min=2048; c &= 15; }
        else if (c >= 0xf0 && c <= 0xf4) { k=3; min=65536; c &= 7; }
        else return 0;
        if (k > n-i) return 0;
        while (k--) { unsigned v=s[i++]; if ((v & 0xc0) != 0x80) return 0; c=c<<6 | (v & 63); }
        if (c < min || c > 0x10ffff || (c >= 0xd800 && c <= 0xdfff)) return 0;
    }
    return 1;
}
static int valid_path(const char *s, size_t n) {
    if (n > 767 || !valid_utf8((const unsigned char *)s, n)) return 0;
    if (!n) return 1;
    size_t start=0;
    for (size_t i=0; i<=n; i++) {
        if (i<n && (s[i]=='\\' || s[i]==':')) return 0;
        if (i==n || s[i]=='/') {
            size_t k=i-start;
            if (!k || (k==1 && s[start]=='.') || (k==2 && s[start]=='.' && s[start+1]=='.')) return 0;
            start=i+1;
        }
    }
    return 1;
}
static const unsigned char *ent(const nxdata *a, uint64_t i) { return a->index+i*32; }
static const char *name(const nxdata *a, uint64_t i) { return a->paths+u32(ent(a,i)); }
int nxdata_find(const nxdata *a, const char *path, uint64_t *entry) {
    if (!path || !valid_path(path, strlen(path))) return bad(EINVAL);
    uint64_t lo=0, hi=a->ne;
    while (lo<hi) { uint64_t m=lo+(hi-lo)/2; int c=strcmp(path,name(a,m));
        if (!c) { *entry=m; return 0; } if (c<0) hi=m; else lo=m+1; }
    return bad(ENOENT);
}
int nxdata_stat(const nxdata *a, uint64_t i, nxdata_info *out) {
    if (i>=a->ne) return bad(EINVAL);
    const unsigned char *e=ent(a,i);
    *out=(nxdata_info){name(a,i), u64(e+8), (int)u32(e+28)}; return 0;
}
void nxdata_close(nxdata *a) {
    if (!a) return;
    close(a->fd); pthread_mutex_destroy(&a->lock);
    free(a->index); free(a->cache); free(a->scratch); free(a);
}
int nxdata_open(const char *path, nxdata **out) {
    *out=NULL;
    int fd=open(path,O_RDONLY); if (fd<0) return -1;
    unsigned char h[64]; struct stat st;
    if (fstat(fd,&st) || read_at(fd,h,64,0)) { int e=errno; close(fd); return bad(e); }
    if (memcmp(h,"NXDATA\0\0",8) || u32(h+8)!=1 || u32(h+12)!=64 || u32(h+20)) { close(fd); return bad(ENOTSUP); }
    uint32_t bs=u32(h+16); uint64_t at=u64(h+24), size=u64(h+32), ne=u64(h+40), nb=u64(h+48);
    if (bs<4096 || bs>1048576 || crc32(0,h,60)!=u32(h+60) || at<64 || size>INDEX_LIMIT ||
        st.st_size<0 || at>(uint64_t)st.st_size || size!=(uint64_t)st.st_size-at ||
        !ne || ne>size/32 || nb>(size-ne*32)/24) { close(fd); return bad(EBADMSG); }
    nxdata *a=calloc(1,sizeof *a); if (!a) { close(fd); return -1; }
    a->fd=fd; a->bs=bs; a->ne=ne; a->nb=nb; a->cached=UINT64_MAX;
    int pe=pthread_mutex_init(&a->lock,NULL); if (pe) { close(fd); free(a); return bad(pe); }
    a->index=malloc((size_t)size); a->cache=malloc(bs); a->scratch=malloc(bs);
    if (!a->index || !a->cache || !a->scratch) { nxdata_close(a); return bad(ENOMEM); }
    if (read_at(fd,a->index,(size_t)size,at)) { int e=errno; nxdata_close(a); return bad(e); }
    if (crc32(0,a->index,(uInt)size)!=u32(h+56)) goto corrupt;
    a->blocks=a->index+ne*32; a->paths=(char *)(a->blocks+nb*24);
    uint64_t pool_size=size-ne*32-nb*24, pool_end=0, next=0, data=64;
    for (uint64_t i=0;i<ne;i++) {
        const unsigned char *e=ent(a,i);
        uint32_t po=u32(e), pl=u32(e+4), count=u32(e+24), kind=u32(e+28);
        uint64_t len=u64(e+8), first=u64(e+16);
        if (po!=pool_end || po>=pool_size || pl>=pool_size-po || a->paths[po+pl] ||
            !valid_path(a->paths+po,pl) || kind>1 || len>INT64_MAX ||
            first!=next || first>nb || count>nb-first ||
            (kind && (len || count)) || (!kind && count!=len/bs+(len%bs!=0)) ||
            (!i && (pl || kind!=1)) || (i && strcmp(name(a,i-1),name(a,i))>=0)) goto corrupt;
        if (i) {
            char parent[768]; memcpy(parent,name(a,i),pl+1); char *slash=strrchr(parent,'/');
            if (slash) *slash=0; else parent[0]=0;
            /* Only search validated entries: later names need not yet have valid offsets. */
            uint64_t all=a->ne, pi; a->ne=i;
            int ok=nxdata_find(a,parent,&pi); a->ne=all;
            if (ok || u32(ent(a,pi)+28)!=1) goto corrupt;
        }
        for (uint32_t j=0;j<count;j++) {
            const unsigned char *b=a->blocks+(first+j)*24;
            uint64_t off=u64(b), remain=len-(uint64_t)j*bs;
            uint32_t stored=u32(b+8), raw=u32(b+12), codec=u32(b+16);
            if (off!=data || off>at || !stored || stored>bs || stored>at-off ||
                raw!=(remain>bs?bs:remain) || codec>1 || (!codec && stored!=raw) ||
                (codec && stored>=raw)) goto corrupt;
            data+=stored;
        }
        next+=count; pool_end+=(uint64_t)pl+1;
    }
    if (next!=nb || data!=at || pool_end!=pool_size) goto corrupt;
    *out=a; return 0;
corrupt:
    nxdata_close(a); return bad(EBADMSG);
}
ssize_t nxdata_read(nxdata *a, uint64_t i, void *buf, size_t len, int64_t offset) {
    if (i>=a->ne || offset<0 || len>SSIZE_MAX || (!buf && len)) return bad(EINVAL);
    const unsigned char *e=ent(a,i); if (u32(e+28)) return bad(EISDIR);
    uint64_t size=u64(e+8), pos=(uint64_t)offset, first=u64(e+16);
    if (pos>=size) return 0;
    if (len>size-pos) len=(size_t)(size-pos);
    size_t got=0;
    pthread_mutex_lock(&a->lock);
    while (got<len) {
        uint64_t k=first+pos/a->bs; size_t within=(size_t)(pos%a->bs);
        const unsigned char *b=a->blocks+k*24;
        uint32_t raw=u32(b+12), stored=u32(b+8);
        if (a->cached!=k) {
            a->cached=UINT64_MAX;
            if (read_at(a->fd,a->scratch,stored,u64(b))) goto fail;
            if (u32(b+16)) {
                z_stream z={0}; z.next_in=a->scratch; z.avail_in=stored; z.next_out=a->cache; z.avail_out=raw;
                if (inflateInit(&z)!=Z_OK) { errno=ENOMEM; goto fail; }
                int r=inflate(&z,Z_FINISH);
                int ok=r==Z_STREAM_END && z.total_out==raw && z.total_in==stored;
                inflateEnd(&z);
                if (!ok) { errno=EBADMSG; goto fail; }
            } else memcpy(a->cache,a->scratch,raw);
            if (crc32(0,a->cache,raw)!=u32(b+20)) { errno=EBADMSG; goto fail; }
            a->cached=k;
        }
        size_t n=raw-within; if (n>len-got) n=len-got;
        memcpy((unsigned char *)buf+got,a->cache+within,n); got+=n; pos+=n;
    }
    pthread_mutex_unlock(&a->lock); return (ssize_t)got;
fail: { int ecode=errno; pthread_mutex_unlock(&a->lock); return bad(ecode); }
}
int nxdata_next(const nxdata *a, uint64_t dir, uint64_t *cursor, nxdata_info *out) {
    if (dir>=a->ne) return bad(EINVAL);
    if (!u32(ent(a,dir)+28)) return bad(ENOTDIR);
    const char *p=name(a,dir); size_t len=strlen(p);
    if (!*cursor) *cursor=dir+1;
    while (*cursor<a->ne) {
        uint64_t i=(*cursor)++; const char *n=name(a,i);
        if (len && (strncmp(p,n,len) || n[len]!='/')) {
            /* A prefix such as 'a!' sorts before the children of 'a'. */
            if (strncmp(p,n,len)>0 || (strlen(n)>=len && !strncmp(p,n,len) && n[len]<'/')) continue;
            return 0;
        }
        const char *child=n+len+(len!=0);
        if (!strchr(child,'/')) { nxdata_stat(a,i,out); return 1; }
    }
    return 0;
}
int nxdata_dup(const nxdata *a) { return dup(a->fd); }
size_t nxdata_cache_bytes(const nxdata *a) { return (size_t)a->bs*2; }
