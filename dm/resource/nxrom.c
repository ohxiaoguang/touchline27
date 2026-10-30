// SPDX-License-Identifier: MIT
// Independent native reader. Format boundaries mirror nx_extract's logical
// storage layering; no Mush8 source is incorporated. Apple SDK crypto only.
#define _DARWIN_C_SOURCE
#include "nxrom.h"
#include <CommonCrypto/CommonCryptor.h>
#include <CommonCrypto/CommonDigest.h>
#include <stdatomic.h>
#include <pthread.h>
#include <errno.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <dirent.h>
#include <unistd.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <limits.h>

#define NR_LIMIT (128u*1024u*1024u)
#define NR_MAX_FILES 1000000u
#define NR_NONE UINT32_MAX
static uint32_t nr32(const void *vp) { const uint8_t *p=vp; return p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24; }
static uint64_t nr64(const void *p) { return nr32(p)|(uint64_t)nr32((const uint8_t*)p+4)<<32; }
static int nr_path(const char *p);
static int nr_bad(int e) { errno=e; return -1; }
static void nr_wipe(void *p,size_t n) { volatile uint8_t *v=p; while(n--) *v++=0; }
static int nr_range(uint64_t o,uint64_t n,uint64_t total) { return o<=total && n<=total-o; }
static int nr_full(int fd,void *p,size_t n,uint64_t off) {
    while(n) { ssize_t k=pread(fd,p,n,(off_t)off); if(k<0) { if(errno==EINTR) continue; return -1; }
        if(!k) return nr_bad(EIO); p=(uint8_t*)p+k; off+=(uint64_t)k; n-=(size_t)k; } return 0;
}
static int nr_aes(const uint8_t key[16],const uint8_t in[16],uint8_t out[16],int decrypt) {
    size_t n=0; if(CCCrypt(decrypt?kCCDecrypt:kCCEncrypt,kCCAlgorithmAES,kCCOptionECBMode,key,16,NULL,in,16,out,16,&n)!=kCCSuccess || n!=16) return nr_bad(EIO); return 0;
}
/* NCA header XTS uses a big-endian sector number in the 128-bit tweak input. */
static int nr_header(uint8_t *data,const uint8_t key[32]) {
    for(unsigned sector=0;sector<6;sector++) {
        uint8_t tweak[16]={0}, seed[16]={0}; seed[15]=(uint8_t)sector;
        if(nr_aes(key+16,seed,tweak,0)) return -1;
        for(unsigned off=0;off<512;off+=16) {
            uint8_t in[16],out[16]; uint8_t *p=data+sector*512+off;
            for(int k=0;k<16;k++) in[k]=p[k]^tweak[k];
            if(nr_aes(key,in,out,1)) return -1;
            for(int k=0;k<16;k++) p[k]=out[k]^tweak[k];
            unsigned carry=0; for(int k=0;k<16;k++) { unsigned v=(unsigned)tweak[k]*2+carry; tweak[k]=(uint8_t)v; carry=v>>8; } if(carry) tweak[0]^=0x87;
        }
    } return 0;
}
typedef struct nr_store nr_store;
typedef struct { uint64_t logical,physical; uint32_t source; } nr_map;
struct nr_store {
    _Atomic unsigned refs;
    int kind,fd; uint64_t size,base,ctr_hi,absolute;
    uint8_t key[16]; nr_store *a,*b;
    nr_map *map; size_t count;
    uint32_t block; int unpadded;
    uint8_t *hashes;
    pthread_mutex_t cache_lock; uint8_t *cache; uint64_t cached;
};
enum { NR_FILE,NR_SLICE,NR_CTR,NR_INDIRECT,NR_CTREM,NR_HASH };
static nr_store *nr_new(int kind,uint64_t size) { nr_store *s=calloc(1,sizeof *s); if(s) { atomic_init(&s->refs,1); s->kind=kind; s->size=size; s->fd=-1; s->cached=UINT64_MAX;
        if(pthread_mutex_init(&s->cache_lock,NULL)) { free(s); errno=ENOMEM; return NULL; } } return s; }
static nr_store *nr_ref(nr_store *s) { if(s) atomic_fetch_add(&s->refs,1); return s; }
static void nr_drop(nr_store *s) { if(!s || atomic_fetch_sub(&s->refs,1)!=1) return; nr_drop(s->a); nr_drop(s->b); if(s->fd>=0) close(s->fd); free(s->map); free(s->hashes); free(s->cache); pthread_mutex_destroy(&s->cache_lock); nr_wipe(s->key,16); free(s); }
static nr_store *nr_file(const char *p) {
    int fd=open(p,O_RDONLY|O_CLOEXEC); if(fd<0) return NULL; struct stat st;
    if(fstat(fd,&st)||!S_ISREG(st.st_mode)||st.st_size<0) { close(fd); errno=EINVAL; return NULL; }
    nr_store *s=nr_new(NR_FILE,(uint64_t)st.st_size); if(!s) { close(fd); errno=ENOMEM; return NULL; } s->fd=fd; return s;
}
static nr_store *nr_sub(nr_store *in,uint64_t off,uint64_t size) {
    if(!nr_range(off,size,in->size)) { errno=EBADMSG; return NULL; }
    nr_store *s=nr_new(NR_SLICE,size); if(s) { s->a=nr_ref(in); s->base=off; } return s;
}
static nr_store *nr_ctr(nr_store *in,const uint8_t key[16],uint64_t hi,uint64_t absolute) {
    nr_store *s=nr_new(NR_CTR,in->size); if(s) { s->a=nr_ref(in); memcpy(s->key,key,16); s->ctr_hi=hi; s->absolute=absolute; } return s;
}
static int nr_read(nr_store *s,uint64_t off,void *buf,size_t len);
static int nr_cryptread(nr_store *s,uint64_t off,void *buf,size_t len,uint64_t hi) {
    if(nr_read(s->a,off,buf,len)) return -1;
    uint64_t address=s->absolute+off, lo=address>>4;
    uint8_t iv[16]; for(int k=0;k<8;k++) { iv[k]=(uint8_t)(hi>>(56-8*k)); iv[k+8]=(uint8_t)(lo>>(56-8*k)); }
    CCCryptorRef crypt=NULL;
    if(CCCryptorCreateWithMode(kCCEncrypt,kCCModeCTR,kCCAlgorithmAES,ccNoPadding,iv,s->key,16,NULL,0,0,kCCModeOptionCTR_BE,&crypt)!=kCCSuccess) return nr_bad(EIO);
    size_t produced=0,skip=(size_t)(address&15); uint8_t zeros[16]={0},discard[16];
    CCCryptorStatus r=kCCSuccess;
    if(skip) r=CCCryptorUpdate(crypt,zeros,skip,discard,sizeof discard,&produced);
    if(r==kCCSuccess) r=CCCryptorUpdate(crypt,buf,len,buf,len,&produced);
    CCCryptorRelease(crypt);
    return r==kCCSuccess&&produced==len?0:nr_bad(EIO);
}
static size_t nr_segment(nr_store *s,uint64_t off) {
    size_t lo=0,hi=s->count; while(lo<hi) { size_t mid=lo+(hi-lo)/2; if(s->map[mid].logical<=off) lo=mid+1; else hi=mid; } return lo?lo-1:SIZE_MAX;
}
static int nr_read(nr_store *s,uint64_t off,void *buf,size_t len) {
    if(!nr_range(off,len,s->size)) return nr_bad(EINVAL);
    if(!len) return 0;
    if(s->kind==NR_FILE) return nr_full(s->fd,buf,len,off);
    if(s->kind==NR_SLICE) return nr_read(s->a,s->base+off,buf,len);
    if(s->kind==NR_CTR) return nr_cryptread(s,off,buf,len,s->ctr_hi);
    if(s->kind==NR_HASH) {
        pthread_mutex_lock(&s->cache_lock);
        if(!s->cache) s->cache=malloc(s->block);
        if(!s->cache) { pthread_mutex_unlock(&s->cache_lock); return -1; }
        uint8_t *block=s->cache; int result=0;
        while(len) {
            uint64_t id=off/s->block,start=id*s->block; size_t valid=(size_t)((s->size-start)<s->block?s->size-start:s->block);
            if(s->cached!=id) {
                s->cached=UINT64_MAX;
                memset(block,0,s->block); if(nr_read(s->a,start,block,valid)) { result=-1; break; }
                uint8_t digest[32],want[32]; CC_SHA256(block,s->unpadded?(CC_LONG)valid:s->block,digest);
                if(s->hashes) memcpy(want,s->hashes+id*32,32);
                else if(nr_read(s->b,id*32,want,32)) { result=-1; break; }
                if(memcmp(digest,want,32)) { result=nr_bad(EBADMSG); break; }
                s->cached=id;
            }
            size_t within=(size_t)(off-start),n=valid-within; if(n>len) n=len;
            memcpy(buf,block+within,n); buf=(uint8_t*)buf+n; off+=n; len-=n;
        }
        int e=errno; pthread_mutex_unlock(&s->cache_lock); if(result) errno=e; return result;
    }
    while(len) {
        size_t i=nr_segment(s,off); if(i==SIZE_MAX) return nr_bad(EBADMSG);
        nr_map *m=&s->map[i]; uint64_t end=i+1<s->count?s->map[i+1].logical:s->size;
        if(end<=off) return nr_bad(EBADMSG);
        size_t n=(size_t)((end-off)<len?end-off:len);
        int r;
        if(s->kind==NR_CTREM) r=nr_cryptread(s,off,buf,n,m->source?((s->ctr_hi&UINT64_C(0xffffffff00000000))|m->physical):s->ctr_hi);
        else r=nr_read(m->source?s->b:s->a,m->physical+(off-m->logical),buf,n);
        if(r) return -1; off+=n; buf=(uint8_t*)buf+n; len-=n;
    } return 0;
}
/* Keys are parsed into a bounded temporary table and erased after mount. */
typedef struct { char name[80]; uint8_t value[32]; size_t size; } nr_key;
typedef struct { nr_key *items; size_t count; } nr_keys;
static void nr_keys_free(nr_keys *k) { if(k->items) { nr_wipe(k->items,k->count*sizeof *k->items); free(k->items); } }
static int nr_keys_load(const char *p,nr_keys *keys) {
    if(!p) return nr_bad(ENOENT); FILE *f=fopen(p,"r"); if(!f) return -1;
    char line[512]; int r=0;
    while(fgets(line,sizeof line,f)) {
        char *eq=strchr(line,'='); if(!eq) continue; *eq++=0;
        char *name=line; while(*name==' '||*name=='\t') name++;
        size_t n=strlen(name); while(n&&(name[n-1]==' '||name[n-1]=='\t')) name[--n]=0;
        while(*eq==' '||*eq=='\t') eq++; size_t digits=strcspn(eq," \t\r\n#");
        if(!n||n>=80||(digits!=32&&digits!=64)) continue;
        if(keys->count>=4096) { r=nr_bad(E2BIG); break; }
        nr_key key={0}; memcpy(key.name,name,n); key.size=digits/2;
        int valid=1; for(size_t i=0;i<key.size;i++) { unsigned v; char h[3]={eq[i*2],eq[i*2+1],0}; if(strspn(h,"0123456789abcdefABCDEF")!=2||sscanf(h,"%x",&v)!=1) { valid=0; break; } key.value[i]=(uint8_t)v; }
        if(!valid) continue;
        nr_key *a=realloc(keys->items,(keys->count+1)*sizeof *a); if(!a) { r=-1; break; } keys->items=a; keys->items[keys->count++]=key; nr_wipe(&key,sizeof key);
    }
    if(ferror(f)) r=-1; int saved=errno; fclose(f); nr_wipe(line,sizeof line); errno=r?(saved?saved:EIO):0; return r;
}
static const uint8_t *nr_key_get(const nr_keys *k,const char *name,size_t size) {
    for(size_t i=0;i<k->count;i++) if(k->items[i].size==size&&!strcmp(k->items[i].name,name)) return k->items[i].value;
    errno=EACCES; return NULL;
}
typedef struct { char *name; nr_store *storage; } nr_member;
typedef struct { nr_member *members; size_t count; } nr_pfs;
static void nr_pfs_free(nr_pfs *p) { for(size_t i=0;i<p->count;i++) { free(p->members[i].name); nr_drop(p->members[i].storage); } free(p->members); }
static int nr_pfs_open(nr_store *s,nr_pfs *p) {
    uint8_t h[16]; if(nr_read(s,0,h,16)) return -1;
    if(memcmp(h,"PFS0",4)) return nr_bad(ENOTSUP);
    uint64_t n=nr32(h+4),strings=nr32(h+8),ts=n*24+strings;
    if(n>4096||ts>NR_LIMIT||!nr_range(16,ts,s->size)) return nr_bad(EBADMSG);
    uint8_t *table=malloc((size_t)ts+1); if(!table) return -1;
    if(nr_read(s,16,table,(size_t)ts)) { free(table); return -1; }
    p->members=calloc((size_t)n,sizeof *p->members); if(n&&!p->members) { free(table); return -1; }
    uint64_t previous=0;
    for(size_t i=0;i<n;i++) {
        if(!nr_range(i*24,24,ts)) { free(table); return nr_bad(EBADMSG); }
        uint8_t *e=table+i*24; uint64_t off=nr64(e),size=nr64(e+8); uint32_t so=nr32(e+16);
        if(so>=strings||!memchr(table+n*24+so,0,strings-so<768?(size_t)strings-so:768)||off<previous||!nr_range(16+ts,s->size-(16+ts),s->size)||!nr_range(off,size,s->size-16-ts)) { free(table); return nr_bad(EBADMSG); }
        char *name=(char*)table+n*24+so;
        if(!*name||!nr_path(name)||strchr(name,'/')||strchr(name,'\\')||!strcmp(name,"..")) { free(table); return nr_bad(EBADMSG); }
        for(size_t j=0;j<i;j++) if(!strcmp(p->members[j].name,name)) { free(table); return nr_bad(EBADMSG); }
        nr_member *m=&p->members[p->count++]; m->name=strdup(name); m->storage=nr_sub(s,16+ts+off,size);
        if(!m->name||!m->storage) { free(table); return -1; } previous=off+size;
        size_t l=strlen(name); if(l>=4&&!strcmp(name+l-4,".ncz")) { free(table); return nr_bad(ENOTSUP); }
    } free(table); return 0;
}
/* Gamecard HFS0 partitions share PFS0's member model with 0x40-byte entries:
 * offset, size, name offset, hashed size, reserved and the SHA-256 of the
 * member's first hashed bytes. The format does not fix the entry order, so
 * overlap is rejected through a sort rather than input order. */
typedef struct { uint64_t off,size; } nr_span;
static int nr_span_cmp(const void *a,const void *b) {
    uint64_t x=((const nr_span*)a)->off,y=((const nr_span*)b)->off; return x<y?-1:x>y;
}
static int nr_hfs0(nr_store *s,nr_pfs *p) {
    uint8_t h[16]; if(nr_read(s,0,h,16)) return -1;
    if(memcmp(h,"HFS0",4)) return nr_bad(ENOTSUP);
    uint64_t n=nr32(h+4),strings=nr32(h+8),ts=n*64+strings;
    if(n>4096||ts>NR_LIMIT||!nr_range(16,ts,s->size)) return nr_bad(EBADMSG);
    uint8_t *table=malloc((size_t)ts+1); if(!table) return -1;
    if(nr_read(s,16,table,(size_t)ts)) { free(table); return -1; }
    p->members=calloc((size_t)n,sizeof *p->members);
    nr_span *spans=calloc((size_t)n+1,sizeof *spans);
    if(!spans||(n&&!p->members)) { free(table); free(spans); return -1; }
    for(size_t i=0;i<n;i++) {
        uint8_t *e=table+i*64; uint64_t off=nr64(e),size=nr64(e+8); uint32_t so=nr32(e+16),hashed=nr32(e+20);
        if(so>=strings||!memchr(table+n*64+so,0,strings-so<768?(size_t)strings-so:768)||hashed>size||!nr_range(off,size,s->size-16-ts)) { free(table); free(spans); return nr_bad(EBADMSG); }
        char *name=(char*)table+n*64+so;
        if(!*name||!nr_path(name)||strchr(name,'/')||strchr(name,'\\')||!strcmp(name,"..")) { free(table); free(spans); return nr_bad(EBADMSG); }
        for(size_t j=0;j<p->count;j++) if(!strcmp(p->members[j].name,name)) { free(table); free(spans); return nr_bad(EBADMSG); }
        size_t l=strlen(name); if(l>=4&&!strcasecmp(name+l-4,".ncz")) { free(table); free(spans); return nr_bad(ENOTSUP); }
        nr_member *m=&p->members[p->count]; m->name=strdup(name); m->storage=nr_sub(s,16+ts+off,size);
        spans[p->count]=(nr_span){off,size};
        if(!m->name||!m->storage) { free(table); free(spans); return -1; }
        p->count++;
    }
    free(table);
    qsort(spans,(size_t)n,sizeof *spans,nr_span_cmp);
    for(size_t i=1;i<n;i++) if(spans[i].off<spans[i-1].off+spans[i-1].size) { free(spans); return nr_bad(EBADMSG); }
    free(spans); return 0;
}
/* Gamecard image: "HEAD" at 0x100, the root partition's offset and header
 * size at 0x130/0x138 and that header's SHA-256 at 0x140, inside the signed
 * header region. Only the secure partition's NCA members are mounted: the
 * on-card firmware update, normal and logo partitions are not game content.
 * Root-declared partition sizes are advisory (a trimmed dump's secure
 * partition can claim bytes past the file's end), so members are bounds
 * checked against the bytes that physically exist. Gamecard Program NCAs
 * carry their keys in the key area; a rights ID cannot be served because
 * that title key exists only in the per-console encrypted InitialData. */
static int nr_xci_probe(nr_store *s) {
    if(s->size<0x104) return 0;
    uint8_t m[4]; return nr_read(s,0x100,m,4)?-1:!memcmp(m,"HEAD",4);
}
static int nr_xci(nr_store *file,nr_pfs *out) {
    if(file->size<0x160) return nr_bad(EBADMSG);
    uint8_t h[0x160]; if(nr_read(file,0,h,sizeof h)) return -1;
    uint64_t root_off=nr64(h+0x130),root_hdr=nr64(h+0x138);
    if(root_off<0x160||!root_hdr||root_hdr>NR_LIMIT||!nr_range(root_off,root_hdr,file->size)) return nr_bad(EBADMSG);
    uint8_t *root=malloc((size_t)root_hdr); if(!root) return -1;
    if(nr_read(file,root_off,root,(size_t)root_hdr)) { free(root); return -1; }
    uint8_t digest[32]; CC_SHA256(root,(CC_LONG)root_hdr,digest);
    if(memcmp(digest,h+0x140,32)) { free(root); return nr_bad(EBADMSG); }
    uint64_t n=nr32(root+4),strings=nr32(root+8);
    if(memcmp(root,"HFS0",4)||n>4096||16+n*64+strings!=root_hdr) { free(root); return nr_bad(EBADMSG); }
    size_t secure=SIZE_MAX;
    for(size_t i=0;i<n;i++) {
        uint32_t so=nr32(root+0x10+i*64+0x10);
        if(so>=strings) { free(root); return nr_bad(EBADMSG); }
        char *name=(char*)root+16+n*64+so;
        if(!memchr(name,0,strings-so<768?(size_t)strings-so:768)||!*name||strchr(name,'/')||strchr(name,'\\')||!strcmp(name,"..")) { free(root); return nr_bad(EBADMSG); }
        if(!strcmp(name,"secure")) { if(secure!=SIZE_MAX) { free(root); return nr_bad(EBADMSG); } secure=i; }
    }
    if(secure==SIZE_MAX) { free(root); return nr_bad(ENOTSUP); }
    uint64_t sec_off=nr64(root+0x10+secure*64); uint32_t hashed=nr32(root+0x10+secure*64+0x14);
    if(hashed>nr64(root+0x10+secure*64+8)||hashed>NR_LIMIT||!nr_range(sec_off,16,file->size-root_off-root_hdr)) { free(root); return nr_bad(EBADMSG); }
    nr_store *region=nr_sub(file,root_off+root_hdr+sec_off,file->size-root_off-root_hdr-sec_off);
    if(!region) { free(root); return -1; }
    if(hashed&&hashed<=1024*1024) {
        uint8_t *head=malloc(hashed); if(!head) { free(root); nr_drop(region); return -1; }
        uint8_t want[32],d[32]; memcpy(want,root+0x10+secure*64+0x20,32);
        int r=nr_read(region,0,head,hashed);
        if(!r) CC_SHA256(head,(CC_LONG)hashed,d);
        free(head); free(root);
        if(r||memcmp(d,want,32)) { nr_drop(region); return r?-1:nr_bad(EBADMSG); }
    } else free(root);
    int r=nr_hfs0(region,out); nr_drop(region); return r;
}
typedef struct { nr_store *raw; uint8_t h[0xc00],key[16]; uint64_t title; } nr_nca;
static int nr_suffix(const char *s,const char *suffix) { size_t a=strlen(s),b=strlen(suffix); return a>=b&&!strcasecmp(s+a-b,suffix); }
static int nr_title_key(const nr_pfs *p,const nr_keys *keys,const uint8_t rights[16],uint8_t out[16]) {
    for(size_t i=0;i<p->count;i++) if(nr_suffix(p->members[i].name,".tik")) {
        uint8_t t[0x2c0]; if(nr_read(p->members[i].storage,0,t,sizeof t)) return -1;
        if(memcmp(t+0x2a0,rights,16)) continue;
        if(nr32(t)!=0x10004||t[0x281]) return nr_bad(ENOTSUP);
        char name[80]; unsigned gen=rights[15]; snprintf(name,sizeof name,"titlekek_%02x",gen?gen-1:0);
        const uint8_t *k=nr_key_get(keys,name,16); if(!k) return -1; return nr_aes(k,t+0x180,out,1);
    }
    return nr_bad(EACCES);
}
static int nr_select_kind(const nr_pfs *p,const nr_keys *keys,uint64_t expected,int kind,nr_nca *out) {
    const uint8_t *hk=nr_key_get(keys,"header_key",32); if(!hk) return -1;
    int found=0;
    for(size_t i=0;i<p->count;i++) if(nr_suffix(p->members[i].name,".nca")) {
        nr_nca n={0}; n.raw=p->members[i].storage;
        if(nr_read(n.raw,0,n.h,sizeof n.h)||nr_header(n.h,hk)) return -1;
        if(memcmp(n.h+0x200,"NCA3",4)) return nr_bad(ENOTSUP);
        if(n.h[0x205]!=kind) continue;
        n.title=nr64(n.h+0x210); if(expected&&n.title!=expected) continue;
        if(found++) return nr_bad(ENOTSUP); // Never guess between multiple programs.
        if(nr64(n.h+0x208)!=n.raw->size) return nr_bad(EBADMSG);
        uint8_t zero[16]={0};
        if(memcmp(n.h+0x230,zero,16)) { if(nr_title_key(p,keys,n.h+0x230,n.key)) return -1; }
        else {
            const char *types[]={"application","ocean","system"}; unsigned type=n.h[0x207],gen=n.h[0x206]>n.h[0x220]?n.h[0x206]:n.h[0x220];
            if(type>=3) return nr_bad(ENOTSUP);
            char kn[80]; snprintf(kn,sizeof kn,"key_area_key_%s_%02x",types[type],gen?gen-1:0);
            const uint8_t *k=nr_key_get(keys,kn,16); if(!k||nr_aes(k,n.h+0x320,n.key,1)) return -1;
        }
        *out=n; nr_wipe(&n,sizeof n);
    }
    return found?0:nr_bad(ENOENT);
}
static int nr_select(const nr_pfs *p,const nr_keys *keys,uint64_t expected,nr_nca *out) {
    return nr_select_kind(p,keys,expected,0,out);
}
static int nr_rom_section(nr_nca *n,unsigned *index) {
    unsigned found=0;
    for(unsigned i=0;i<4;i++) if(nr32(n->h+0x244+i*16)) {
        const uint8_t *h=n->h+0x400+i*512; uint8_t digest[32]; CC_SHA256(h,512,digest);
        if(memcmp(digest,n->h+0x280+i*32,32)) return nr_bad(EBADMSG);
        if(h[2]==0) { *index=i; found++; }
    }
    return found==1?0:nr_bad(ENOTSUP);
}
static nr_store *nr_section(nr_nca *n,unsigned i) {
    uint64_t lo=(uint64_t)nr32(n->h+0x240+i*16)*512,hi=(uint64_t)nr32(n->h+0x244+i*16)*512;
    const uint8_t *h=n->h+0x400+i*512;
    if(lo<0xc00||hi<lo) { errno=EBADMSG; return NULL; }
    // Sparse and compressed NCA storages require additional translation layers.
    for(unsigned j=0x148;j<0x1a0;j++) if(h[j]) { errno=ENOTSUP; return NULL; }
    nr_store *raw=nr_sub(n->raw,lo,hi-lo); if(!raw) return NULL;
    if(h[4]==1) return raw;
    if(h[4]!=3&&h[4]!=4) { nr_drop(raw); errno=ENOTSUP; return NULL; }
    nr_store *s=nr_ctr(raw,n->key,nr64(h+0x140),lo); nr_drop(raw); return s;
}
/* Parse a bounded single-root bucket tree (the common retail BKTR form).
 * Reject deeper trees rather than guessing at layout or accepting partial maps. */
static int nr_buckets(nr_store *tables,uint64_t off,uint64_t size,int subsection,
                      nr_map **result,size_t *count,uint64_t *total) {
    if(size<0x8000||size>NR_LIMIT||!nr_range(off,size,tables->size)) return nr_bad(EBADMSG);
    uint8_t *b=malloc((size_t)size); if(!b) return -1;
    if(nr_read(tables,off,b,(size_t)size)) { free(b); return -1; }
    uint32_t buckets=nr32(b+4); uint64_t end=nr64(b+8); size_t stride=subsection?16:20;
    if(!buckets||buckets>(0x4000-16)/8||((uint64_t)buckets+1)*0x4000!=size) { free(b); return nr_bad(ENOTSUP); }
    size_t entries=0;
    for(uint32_t k=0;k<buckets;k++) { uint32_t n=nr32(b+(k+1)*0x4000+4); if(!n||n>(0x4000-16)/stride) { free(b); return nr_bad(EBADMSG); } entries+=n; }
    nr_map *maps=calloc(entries+1,sizeof *maps); if(!maps) { free(b); return -1; }
    size_t at=0;
    for(uint32_t k=0;k<buckets;k++) {
        uint8_t *bucket=b+(k+1)*0x4000; uint32_t n=nr32(bucket+4);
        for(uint32_t j=0;j<n;j++) {
            uint8_t *v=bucket+16+j*stride; nr_map m={nr64(v),subsection?nr32(v+12):nr64(v+8),subsection?1:nr32(v+16)};
            if((at&&m.logical<=maps[at-1].logical)||(!at&&m.logical)||m.logical>=end||m.source>1) { free(maps); free(b); return nr_bad(EBADMSG); }
            maps[at++]=m;
        }
    }
    free(b); *result=maps; *count=at; *total=end; return 0;
}
static nr_store *nr_patch(nr_store *base,nr_store *update,const uint8_t *h) {
    if(memcmp(h+0x110,"BKTR",4)||memcmp(h+0x130,"BKTR",4)||nr32(h+0x114)!=1||nr32(h+0x134)!=1) { errno=ENOTSUP; return NULL; }
    nr_map *rel=NULL,*sub=NULL; size_t nr=0,ns=0; uint64_t total=0,subend=0;
    uint64_t ro=nr64(h+0x100),rs=nr64(h+0x108),so=nr64(h+0x120),ss=nr64(h+0x128);
    if(nr_buckets(update,ro,rs,0,&rel,&nr,&total)||nr_buckets(update,so,ss,1,&sub,&ns,&subend)) { free(rel); free(sub); return NULL; }
    // The tables are read with the section's natural counter, so the region the
    // subsection table describes must not climb past that table itself. It may
    // cover the relative table: FIFA 23 declares the region right up to the
    // subsection table's start and gives the subsection that covers both tables
    // the natural counter, which keeps the layout self-consistent.
    if(!ns||subend>so||sub[ns-1].logical>=subend||so>update->size) { free(rel); free(sub); errno=EBADMSG; return NULL; }
    sub[ns++]=(nr_map){subend,0,0};
    nr_store *ex=nr_new(NR_CTREM,update->size); if(!ex) { free(rel); free(sub); return NULL; }
    ex->a=nr_ref(update->a); memcpy(ex->key,update->key,16); ex->absolute=update->absolute; ex->ctr_hi=update->ctr_hi; ex->map=sub; ex->count=ns;
    for(size_t i=0;i<nr;i++) {
        uint64_t end=i+1<nr?rel[i+1].logical:total; nr_store *src=rel[i].source?ex:base;
        if(end<=rel[i].logical||!nr_range(rel[i].physical,end-rel[i].logical,src->size)) { nr_drop(ex); free(rel); errno=EBADMSG; return NULL; }
    }
    nr_store *s=nr_new(NR_INDIRECT,total); if(!s) { nr_drop(ex); free(rel); return NULL; }
    s->a=nr_ref(base); s->b=ex; s->map=rel; s->count=nr; return s;
}
static nr_store *nr_ivfc(nr_store *section,const uint8_t *h) {
    // NCA IVFC: six levels beneath one 32-byte master hash. SHA-256,
    // zero-padding each final block; reject alternate hash constructions.
    if(h[3]!=3||memcmp(h+8,"IVFC",4)||nr32(h+0x10)!=32||nr32(h+0x14)!=7) { errno=ENOTSUP; return NULL; }
    nr_store *parent=NULL;
    for(unsigned i=0;i<6;i++) {
        const uint8_t *v=h+0x18+i*24; uint64_t off=nr64(v),size=nr64(v+8); uint32_t shift=nr32(v+16);
        if(!size||shift<5||shift>20||nr32(v+20)) { nr_drop(parent); errno=ENOTSUP; return NULL; }
        uint32_t block=1u<<shift; uint64_t hashes=size/block+(size%block!=0);
        if((!i&&hashes!=1)||(parent&&hashes>parent->size/32)) { nr_drop(parent); errno=EBADMSG; return NULL; }
        nr_store *raw=nr_sub(section,off,size); if(!raw) { nr_drop(parent); return NULL; }
        nr_store *checked=nr_new(NR_HASH,size); if(!checked) { nr_drop(raw); nr_drop(parent); return NULL; }
        checked->a=raw; checked->b=parent; checked->block=block;
        if(!i) { checked->hashes=malloc(32); if(!checked->hashes) { nr_drop(checked); return NULL; } memcpy(checked->hashes,h+0xc8,32); }
        parent=checked;
    } return parent;
}
static nr_store *nr_code(nr_nca *n) {
    for(unsigned i=0;i<4;i++) {
        const uint8_t *h=n->h+0x400+i*512;
        if(!nr32(n->h+0x244+i*16)||h[2]!=1) continue;
        uint8_t digest[32]; CC_SHA256(h,512,digest);
        if(memcmp(digest,n->h+0x280+i*32,32)) { errno=EBADMSG; return NULL; }
        if(h[3]!=2||nr32(h+0x2c)!=2||h[4]==4) { errno=ENOTSUP; return NULL; }
        uint32_t block=nr32(h+0x28);
        if(block<32||block>(1u<<20)||(block&(block-1))) { errno=ENOTSUP; return NULL; }
        nr_store *section=nr_section(n,i); if(!section) return NULL;
        nr_store *parent=NULL;
        for(unsigned level=0;level<2;level++) {
            const uint8_t *v=h+0x30+level*16; uint64_t off=nr64(v),size=nr64(v+8);
            uint64_t hashes=size/block+(size%block!=0);
            if(!size||(!level&&hashes!=1)||(parent&&hashes>parent->size/32)) { nr_drop(parent); nr_drop(section); errno=EBADMSG; return NULL; }
            nr_store *raw=nr_sub(section,off,size); if(!raw) { nr_drop(parent); nr_drop(section); return NULL; }
            nr_store *checked=nr_new(NR_HASH,size); if(!checked) { nr_drop(raw); nr_drop(parent); nr_drop(section); return NULL; }
            checked->a=raw; checked->b=parent; checked->block=block; checked->unpadded=1;
            if(!level) { checked->hashes=malloc(32); if(!checked->hashes) { nr_drop(checked); nr_drop(section); return NULL; } memcpy(checked->hashes,h+8,32); }
            parent=checked;
        }
        nr_drop(section); return parent;
    }
    errno=ENOTSUP; return NULL;
}
typedef struct { char *path; uint64_t offset,size; int directory; uint64_t child,next; } nr_entry;
struct nxrom { nr_store *storage,*code; int fd; uint64_t title; nr_entry *entries; size_t count,capacity,pathbytes; };
static int nr_utf8(const unsigned char *s, size_t n) {
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
static int nr_path(const char *p) {
    size_t n=strlen(p); if(n>767||!nr_utf8((const unsigned char*)p,n)) return 0;
    if(!n) return 1;
    const char *start=p;
    for(const char *c=p;;c++) {
        if(*c=='\\'||*c==':'||(*c&&(unsigned char)*c<32)||(unsigned char)*c==127) return 0;
        if(!*c||*c=='/') { size_t k=(size_t)(c-start); if(!k||(k==1&&*start=='.')||(k==2&&start[0]=='.'&&start[1]=='.')) return 0; if(!*c) break; start=c+1; }
    } return 1;
}
static int nr_add(nxrom *fs,const char *path,int dir,uint64_t off,uint64_t size) {
    if(!nr_path(path)||fs->count>=NR_MAX_FILES||size>INT64_MAX||strlen(path)+1>NR_LIMIT-fs->pathbytes) return nr_bad(EBADMSG);
    if(fs->count==fs->capacity) {
        size_t cap=fs->capacity?fs->capacity*2:128;
        nr_entry *items=realloc(fs->entries,cap*sizeof *items); if(!items) return -1;
        fs->entries=items; fs->capacity=cap;
    } char *copy=strdup(path); if(!copy) return -1;
    fs->entries[fs->count++]=(nr_entry){copy,off,size,dir,UINT64_MAX,UINT64_MAX}; fs->pathbytes+=strlen(path)+1; return 0;
}
static int nr_cmp(const void *a,const void *b) { return strcmp(((const nr_entry*)a)->path,((const nr_entry*)b)->path); }
int nxrom_find(const nxrom *fs,const char *path,uint64_t *id) {
    if(!path||!nr_path(path)) return nr_bad(EINVAL); nr_entry key={.path=(char*)path};
    nr_entry *e=bsearch(&key,fs->entries,fs->count,sizeof *e,nr_cmp); if(!e) return nr_bad(ENOENT);
    *id=(uint64_t)(e-fs->entries); return 0;
}
static int nr_sort(nxrom *fs) {
    qsort(fs->entries,fs->count,sizeof *fs->entries,nr_cmp);
    for(size_t i=0;i<fs->count;i++) {
        if(i&&!strcmp(fs->entries[i-1].path,fs->entries[i].path)) return nr_bad(EBADMSG);
        if(!i) { if(*fs->entries[i].path||!fs->entries[i].directory) return nr_bad(EBADMSG); continue; }
        char parent[768]; strlcpy(parent,fs->entries[i].path,sizeof parent); char *slash=strrchr(parent,'/'); if(slash) *slash=0; else parent[0]=0;
        uint64_t id; if(nxrom_find(fs,parent,&id)||!fs->entries[id].directory) return nr_bad(EBADMSG);
    }
    // Immutable immediate-child links make each enumeration O(children), rather
    // than scanning the entire file index for every directory at game boot.
    for(size_t i=fs->count;i-->1;) {
        char parent[768]; strlcpy(parent,fs->entries[i].path,sizeof parent);
        char *slash=strrchr(parent,'/'); if(slash) *slash=0; else parent[0]=0;
        uint64_t id; if(nxrom_find(fs,parent,&id)) return -1;
        fs->entries[i].next=fs->entries[id].child; fs->entries[id].child=i;
    }
    return 0;
}
static int nr_walk_rom(nxrom *fs,const uint8_t *dirs,size_t nd,const uint8_t *files,size_t nf,
                       uint8_t *seen_d,uint8_t *seen_f,uint32_t at,const char *parent,
                       uint32_t expected_parent,uint64_t data,unsigned depth) {
    if(depth>128||at%4||!nr_range(at,24,nd)||seen_d[at]) return nr_bad(EBADMSG);
    seen_d[at]=1; const uint8_t *d=dirs+at; uint32_t nl=nr32(d+20);
    if(nr32(d)!=expected_parent||!nr_range((uint64_t)at+24,nl,nd)||nl>767||memchr(d+24,0,nl)) return nr_bad(EBADMSG);
    char path[768];
    if(!at) { if(nl) return nr_bad(EBADMSG); path[0]=0; }
    else {
        if(!nl||memchr(d+24,'/',nl)) return nr_bad(EBADMSG);
        if(snprintf(path,sizeof path,"%s%s%.*s",parent,*parent?"/":"",(int)nl,d+24)>=(int)sizeof path) return nr_bad(EBADMSG);
    }
    if(nr_add(fs,path,1,0,0)) return -1;
    uint32_t f=nr32(d+12);
    while(f!=NR_NONE) {
        if(f%4||!nr_range(f,32,nf)||seen_f[f]) return nr_bad(EBADMSG); seen_f[f]=1;
        const uint8_t *e=files+f; nl=nr32(e+28); uint64_t off=nr64(e+8),size=nr64(e+16);
        if(nr32(e)!=at||!nl||nl>767||!nr_range((uint64_t)f+32,nl,nf)||memchr(e+32,0,nl)||memchr(e+32,'/',nl)||!nr_range(data,off,fs->storage->size)||!nr_range(data+off,size,fs->storage->size)) return nr_bad(EBADMSG);
        char full[768]; if(snprintf(full,sizeof full,"%s%s%.*s",path,*path?"/":"",(int)nl,e+32)>=(int)sizeof full||nr_add(fs,full,0,data+off,size)) return -1;
        f=nr32(e+4);
    }
    uint32_t child=nr32(d+8);
    while(child!=NR_NONE) {
        if(nr_walk_rom(fs,dirs,nd,files,nf,seen_d,seen_f,child,path,at,data,depth+1)) return -1;
        child=nr32(dirs+child+4);
    } return 0;
}
static int nr_index(nxrom *fs) {
    uint8_t h[80]; if(nr_read(fs->storage,0,h,sizeof h)) return -1;
    uint64_t od=nr64(h+24),nd=nr64(h+32),of=nr64(h+56),nf=nr64(h+64),data=nr64(h+72);
    if(nr64(h)!=80||nd<24||nd>NR_LIMIT||nf>NR_LIMIT-nd||!nr_range(od,nd,fs->storage->size)||!nr_range(of,nf,fs->storage->size)||data>fs->storage->size) return nr_bad(EBADMSG);
    uint8_t *dirs=malloc((size_t)nd),*files=malloc((size_t)nf+1),*sd=calloc(1,(size_t)nd),*sf=calloc(1,(size_t)nf+1);
    if(!dirs||!files||!sd||!sf) { free(dirs); free(files); free(sd); free(sf); return -1; }
    int r=nr_read(fs->storage,od,dirs,(size_t)nd)||nr_read(fs->storage,of,files,(size_t)nf)?-1:
        nr_walk_rom(fs,dirs,(size_t)nd,files,(size_t)nf,sd,sf,0,"",0,data,0);
    free(dirs); free(files); free(sd); free(sf); return r?r:nr_sort(fs);
}
void nxrom_close(nxrom *fs) {
    if(!fs) return; nr_drop(fs->storage); nr_drop(fs->code); if(fs->fd>=0) close(fs->fd);
    for(size_t i=0;i<fs->count;i++) free(fs->entries[i].path); free(fs->entries); free(fs);
}
int nxrom_open(const char *base,const char *update,const char *keyfile,uint64_t expected,nxrom **out,char *error,size_t cap) {
    *out=NULL; const char *stage="input"; nr_keys keys={0}; nr_pfs bp={0},up={0};
    nr_store *bs=NULL,*us=NULL,*bsec=NULL,*usec=NULL,*logical=NULL; nxrom *fs=NULL; nr_nca bn={0},un={0}; int gamecard;
    if(!base||!*base) { errno=EINVAL; goto fail; }
    if(nr_suffix(base,".nsz")||nr_suffix(base,".ncz")||nr_suffix(base,".xcz")
       ||(update&&(nr_suffix(update,".nsz")||nr_suffix(update,".ncz")||nr_suffix(update,".xcz")))) { errno=ENOTSUP; goto fail; }
    stage="keys (path, key name or generation missing)"; if(nr_keys_load(keyfile,&keys)) goto fail;
    stage="base container (NSP PFS0 / gamecard XCI)"; bs=nr_file(base); if(!bs) goto fail;
    gamecard=nr_xci_probe(bs);
    if(gamecard<0||(gamecard?nr_xci(bs,&bp):nr_pfs_open(bs,&bp))) goto fail;
    stage="base Program NCA selection/header/key"; if(nr_select(&bp,&keys,expected,&bn)) goto fail;
    unsigned bi=0,ui=0; stage="base RomFS section/features"; if(nr_rom_section(&bn,&bi)) goto fail;
    if(bn.h[0x400+bi*512+4]==4) { errno=EINVAL; goto fail; }
    bsec=nr_section(&bn,bi); if(!bsec) goto fail;
    const uint8_t *fh=bn.h+0x400+bi*512;
    if(update&&*update) {
        stage="update PFS0"; us=nr_file(update); if(!us||nr_pfs_open(us,&up)) goto fail;
        stage="update Program NCA identity/header/key"; if(nr_select(&up,&keys,0,&un)) goto fail;
        if(un.title!=bn.title&&un.title!=bn.title+0x800) { errno=EINVAL; goto fail; }
        stage="update RomFS section/features"; if(nr_rom_section(&un,&ui)) goto fail;
        fh=un.h+0x400+ui*512; if(fh[4]!=4) { errno=ENOTSUP; goto fail; }
        usec=nr_section(&un,ui); if(!usec) goto fail;
        stage="BKTR tables/mappings"; logical=nr_patch(bsec,usec,fh); if(!logical) goto fail;
    } else logical=nr_ref(bsec);
    fs=calloc(1,sizeof *fs); if(!fs) goto fail; fs->fd=-1; fs->title=bn.title;
    stage="IVFC logical storage"; fs->storage=nr_ivfc(logical,fh); if(!fs->storage) goto fail;
    stage="RomFS index/integrity"; if(nr_index(fs)) goto fail;
    // ExeFS is optional for an inspector fixture, but actual HLE mounts require
    // every loaded module's build ID to match before guest resource access.
    nr_nca *selected=us?&un:&bn; int has_code=0;
    for(unsigned i=0;i<4;i++) if(nr32(selected->h+0x244+i*16)&&selected->h[0x402+i*512]==1) has_code=1;
    if(has_code) { stage="ExeFS logical storage"; fs->code=nr_code(selected); if(!fs->code) goto fail; }
    fs->fd=dup(bs->fd); if(fs->fd<0) goto fail;
    nr_drop(bs); nr_drop(us); nr_drop(bsec); nr_drop(usec); nr_drop(logical); nr_pfs_free(&bp); nr_pfs_free(&up); nr_keys_free(&keys);
    nr_wipe(&bn,sizeof bn); nr_wipe(&un,sizeof un); *out=fs; if(cap) *error=0; return 0;
fail: {
    int e=errno?errno:EIO; if(cap) snprintf(error,cap,"%s: %s (errno=%d)",stage,strerror(e),e);
    nxrom_close(fs); nr_drop(bs); nr_drop(us); nr_drop(bsec); nr_drop(usec); nr_drop(logical); nr_pfs_free(&bp); nr_pfs_free(&up); nr_keys_free(&keys);
    nr_wipe(&bn,sizeof bn); nr_wipe(&un,sizeof un); return nr_bad(e);
}}
/* CNMT is inside the Meta NCA's integrity-checked PFS0. Layout references:
 * Atmosphere libstratosphere ncm_content_meta.hpp (format only; independent code).
 * Only one title per DLC container is accepted. Content IDs, sizes and NCA
 * identities must agree; an unlisted payload cannot become an installed DLC. */
static int nr_content(const nr_pfs *pkg,const nr_keys *keys,nxrom_content *out,nr_nca *data,const char **stage) {
    nr_nca meta={0}; nr_store *storage=NULL; nr_pfs p={0}; int r=-1;
    *stage="Meta NCA selection/header/key";
    if(nr_select_kind(pkg,keys,0,1,&meta)) goto done;
    *stage="Meta NCA PFS0 integrity";
    storage=nr_code(&meta); if(!storage||nr_pfs_open(storage,&p)) goto done;
    const nr_member *member=NULL;
    for(size_t i=0;i<p.count;i++) if(nr_suffix(p.members[i].name,".cnmt")) {
        if(member) { nr_bad(ENOTSUP); goto done; } member=p.members+i;
    }
    if(!member) { nr_bad(EBADMSG); goto done; }
    *stage="CNMT header, bounds or application metadata";
    uint8_t h[0x38];
    if(member->storage->size<0x30||nr_read(member->storage,0,h,0x30)) goto done;
    unsigned ext=h[14]|(unsigned)h[15]<<8, count=h[16]|(unsigned)h[17]<<8;
    unsigned metas=h[18]|(unsigned)h[19]<<8;
    uint64_t end=0x20ull+ext+count*0x38ull+metas*0x10ull;
    if(!nr_range(0,end+32,member->storage->size)||member->storage->size>NR_LIMIT||h[13]) { nr_bad(EBADMSG); goto done; }
    *out=(nxrom_content){.title=nr64(h),.version=nr32(h+8),.type=h[12]};
    if(out->title!=meta.title) { nr_bad(EBADMSG); goto done; }
    if(out->type==0x80) { if(ext!=16) { nr_bad(ENOTSUP); goto done; } out->application=out->title; }
    else if(out->type==0x81||out->type==0x82) {
        if((out->type==0x81&&ext!=24)||(out->type==0x82&&ext!=16&&ext!=24)) { nr_bad(ENOTSUP); goto done; }
        out->application=nr64(h+0x20);
        if(out->type==0x82) {
            out->required_version=nr32(h+0x28);
            if(ext==24) {
                if(nr_read(member->storage,0x30,h+0x30,8)) goto done;
                if(nr64(h+0x30)) { *stage="DLC DataPatch layering is unsupported"; nr_bad(ENOTSUP); goto done; } // DataPatch needs its own layering.
            }
            if(out->title<=out->application+0x1000||out->title-out->application-0x1000>0x7ff) { *stage="DLC Title ID cannot map to a supported AOC index"; nr_bad(ENOTSUP); goto done; }
            out->index=(uint32_t)(out->title-out->application-0x1000);
        }
    } else { nr_bad(ENOTSUP); goto done; }
    /* The trailing digest is a mastering identifier, not a retail self-hash.
     * Integrity is supplied by the Meta NCA PFS0 hash layers above. */
    uint64_t size=member->storage->size; uint8_t *blob=malloc((size_t)size);
    if(!blob) goto done;
    if(nr_read(member->storage,0,blob,(size_t)size)) { free(blob); goto done; }
    if(out->type==0x82) {
        /* Program/control/multiple data records cannot be safely treated as one
         * RomFS. Reject them instead of dropping any record or code module. */
        *stage="DLC requires one Data content record and no content-meta dependencies";
        if(count!=1||metas) { free(blob); nr_bad(ENOTSUP); goto done; }
        const uint8_t *record=blob+0x20+ext;
        if(record[54]!=2||record[55]) { free(blob); nr_bad(ENOTSUP); goto done; }
        *stage="DLC CNMT content ID, NCA size, type or Title ID mismatch";
        char name[37]; for(unsigned j=0;j<16;j++) snprintf(name+j*2,3,"%02x",record[32+j]);
        strcpy(name+32,".nca");
        const nr_member *payload=NULL;
        for(size_t j=0;j<pkg->count;j++) if(!strcasecmp(pkg->members[j].name,name)) {
            if(payload) { free(blob); nr_bad(EBADMSG); goto done; } payload=pkg->members+j;
        }
        uint64_t bytes=0; for(unsigned j=0;j<6;j++) bytes|=(uint64_t)record[48+j]<<(8*j);
        if(!payload||payload->storage->size!=bytes) { free(blob); nr_bad(EBADMSG); goto done; }
        nr_nca n={0};
        if(nr_select_kind(pkg,keys,out->title,5,&n)) {
            if(errno!=ENOENT||nr_select_kind(pkg,keys,out->title,4,&n)) { free(blob); goto done; }
        }
        if(n.raw!=payload->storage) { free(blob); nr_wipe(&n,sizeof n); nr_bad(EBADMSG); goto done; }
        /* Refuse additional Program/Data/PublicData NCAs even if unlisted. */
        const uint8_t *hk=nr_key_get(keys,"header_key",32);
        for(size_t j=0;j<pkg->count;j++) if(nr_suffix(pkg->members[j].name,".nca")) {
            uint8_t nh[0xc00];
            if(nr_read(pkg->members[j].storage,0,nh,sizeof nh)||nr_header(nh,hk)) { free(blob); nr_wipe(&n,sizeof n); goto done; }
            int kind=nh[0x205]; nr_wipe(nh,sizeof nh);
            if((kind==0||kind==4||kind==5)&&pkg->members[j].storage!=n.raw) { free(blob); nr_wipe(&n,sizeof n); nr_bad(ENOTSUP); goto done; }
        }
        if(data) *data=n;
        nr_wipe(&n,sizeof n);
    }
    free(blob); r=0;
done: {
    int e=errno; nr_pfs_free(&p); nr_drop(storage); nr_wipe(&meta,sizeof meta); return r?nr_bad(e?e:EBADMSG):0;
}}
int nxrom_content_meta(const char *path,const char *keyfile,nxrom_content *content,char *error,size_t cap) {
    nr_keys keys={0}; nr_pfs p={0}; nr_store *file=NULL; int r=-1;
    const char *stage="CNMT input/keys/container";
    if(!content||!path) { errno=EINVAL; goto done; } memset(content,0,sizeof *content);
    if(nr_keys_load(keyfile,&keys)) goto done;
    file=nr_file(path); if(!file) goto done;
    int card=nr_xci_probe(file);
    if(card<0||(card?nr_xci(file,&p):nr_pfs_open(file,&p))) goto done;
    r=nr_content(&p,&keys,content,NULL,&stage);
done: {
    int e=errno; if(cap) { if(r) snprintf(error,cap,"%s: %s",stage,strerror(e?e:EBADMSG)); else *error=0; }
    nr_pfs_free(&p); nr_drop(file); nr_keys_free(&keys); return r?nr_bad(e?e:EBADMSG):0;
}}
int nxrom_open_aoc(const char *path,const char *keyfile,uint64_t application,uint32_t version,nxrom **out,char *error,size_t cap) {
    nr_keys keys={0}; nr_pfs p={0}; nr_store *file=NULL,*section=NULL; nr_nca n={0}; nxrom *fs=NULL;
    nxrom_content content={0}; const char *stage="DLC container/CNMT"; int r=-1; *out=NULL;
    if(!application||nr_keys_load(keyfile,&keys)) goto done;
    file=nr_file(path); if(!file||nr_pfs_open(file,&p)||nr_content(&p,&keys,&content,&n,&stage)) goto done;
    stage="DLC ownership/version";
    if(content.type!=0x82||content.application!=application||content.required_version>version) { errno=EINVAL; goto done; }
    stage="DLC RomFS section/integrity"; unsigned i=0;
    if(nr_rom_section(&n,&i)||n.h[0x404+i*512]==4) { errno=ENOTSUP; goto done; }
    section=nr_section(&n,i); if(!section) goto done;
    fs=calloc(1,sizeof *fs); if(!fs) goto done; fs->fd=-1; fs->title=content.title;
    fs->storage=nr_ivfc(section,n.h+0x400+i*512); if(!fs->storage||nr_index(fs)) goto done;
    fs->fd=dup(file->fd); if(fs->fd<0) goto done;
    *out=fs; fs=NULL; r=0;
done: {
    int e=errno; if(cap) { if(r) snprintf(error,cap,"%s: %s",stage,strerror(e)); else *error=0; }
    nxrom_close(fs); nr_drop(section); nr_pfs_free(&p); nr_drop(file); nr_keys_free(&keys); nr_wipe(&n,sizeof n);
    return r?nr_bad(e?e:EBADMSG):0;
}}

static int nr_dir_walk(nxrom *fs,const char *path,unsigned depth) {
    if(depth>128) return nr_bad(ELOOP);
    int fd=*path?openat(fs->fd,path,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC):dup(fs->fd);
    if(fd<0) return -1; DIR *d=fdopendir(fd); if(!d) { close(fd); return -1; }
    int r=0; struct dirent *e;
    while((e=readdir(d))) {
        if(!strcmp(e->d_name,".")||!strcmp(e->d_name,"..")) continue;
        char full[768]; struct stat st;
        if(snprintf(full,sizeof full,"%s%s%s",path,*path?"/":"",e->d_name)>=(int)sizeof full||fstatat(fd,e->d_name,&st,AT_SYMLINK_NOFOLLOW)) { r=-1; break; }
        if(!S_ISDIR(st.st_mode)&&!S_ISREG(st.st_mode)) { r=nr_bad(ENOTSUP); break; }
        if(nr_add(fs,full,S_ISDIR(st.st_mode),0,S_ISDIR(st.st_mode)?0:(uint64_t)st.st_size)||(S_ISDIR(st.st_mode)&&nr_dir_walk(fs,full,depth+1))) { r=-1; break; }
    } closedir(d); return r;
}
int nxrom_directory(const char *root,nxrom **out) {
    *out=NULL; nxrom *fs=calloc(1,sizeof *fs); if(!fs) return -1;
    fs->fd=open(root,O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
    if(fs->fd<0||nr_add(fs,"",1,0,0)||nr_dir_walk(fs,"",0)||nr_sort(fs)) { int e=errno; nxrom_close(fs); return nr_bad(e); }
    *out=fs; return 0;
}
int nxrom_stat(const nxrom *fs,uint64_t id,nxrom_info *out) {
    if(id>=fs->count) return nr_bad(EINVAL); nr_entry *e=fs->entries+id; *out=(nxrom_info){e->path,e->size,e->directory}; return 0;
}
ssize_t nxrom_read(nxrom *fs,uint64_t id,void *buffer,size_t size,int64_t offset) {
    if(id>=fs->count||offset<0||size>SSIZE_MAX||(!buffer&&size)) return nr_bad(EINVAL);
    nr_entry *e=fs->entries+id; if(e->directory) return nr_bad(EISDIR);
    if((uint64_t)offset>=e->size) return 0; if(size>e->size-(uint64_t)offset) size=(size_t)(e->size-(uint64_t)offset);
    if(!size) return 0;
    if(fs->storage) { if(nr_read(fs->storage,e->offset+(uint64_t)offset,buffer,size)) return -1; }
    else {
        int fd=openat(fs->fd,e->path,O_RDONLY|O_NOFOLLOW|O_CLOEXEC); if(fd<0) return -1;
        int r=nr_full(fd,buffer,size,(uint64_t)offset),err=errno; close(fd); if(r) return nr_bad(err);
    } return (ssize_t)size;
}
int nxrom_next(const nxrom *fs,uint64_t dir,uint64_t *cursor,nxrom_info *info) {
    if(dir>=fs->count) return nr_bad(EINVAL); if(!fs->entries[dir].directory) return nr_bad(ENOTDIR);
    if(*cursor==UINT64_MAX) return 0;
    uint64_t id=*cursor?*cursor-1:fs->entries[dir].child;
    if(id==UINT64_MAX) { *cursor=UINT64_MAX; return 0; }
    if(id>=fs->count) return nr_bad(EINVAL);
    *cursor=fs->entries[id].next==UINT64_MAX?UINT64_MAX:fs->entries[id].next+1;
    nxrom_stat(fs,id,info); return 1;
}
int nxrom_dup(const nxrom *fs) { return dup(fs->fd); }
uint64_t nxrom_title(const nxrom *fs) { return fs->title; }
int nxrom_validate_aoc(nxrom *fs,char *error,size_t cap) {
    for(size_t i=0;i<fs->count;i++) if(!fs->entries[i].directory) {
        const nr_entry *e=fs->entries+i; uint8_t header[0x80]={0};
        size_t n=e->size<sizeof header?(size_t)e->size:sizeof header;
        if(nxrom_read(fs,i,header,n,0)!=(ssize_t)n) {
            if(cap) snprintf(error,cap,"DLC file header/integrity failed: %s",e->path);
            return -1;
        }
        if((n>=0x50&&!memcmp(header,"NSO0",4))||(n>=0x80&&!memcmp(header+0x10,"NRO0",4))) {
            if(cap) snprintf(error,cap,"DLC executable module requires collection and rewriting: %s",e->path);
            return nr_bad(ENOTSUP);
        }
    }
    if(cap) *error=0; return 0;
}
static size_t nr_romfs_buckets(size_t n) {
    if(n<3) return 3;
    if(n<19) return n|1;
    while(!(n%2&&n%3&&n%5&&n%7&&n%11&&n%13&&n%17)) n++;
    return n;
}
size_t nxrom_romfs_cache_size(const nxrom *fs) {
    size_t dirs=0,files=0,bytes=0;
    for(size_t i=0;i<fs->count;i++) {
        const nr_entry *e=fs->entries+i; const char *leaf=strrchr(e->path,'/');
        size_t length=strlen(leaf?leaf+1:e->path);
        if(e->directory) dirs++; else files++;
        bytes+=(e->directory?0x18:0x20)+((length+3)&~(size_t)3);
    }
    return bytes+4*(nr_romfs_buckets(dirs)+nr_romfs_buckets(files));
}

int nxrom_check_build(nxrom *fs,const char *module,const char *hex) {
    if(!fs->code||!module||!hex||strlen(hex)!=32) return nr_bad(ENOTSUP);
    nr_pfs p={0}; if(nr_pfs_open(fs->code,&p)) { nr_pfs_free(&p); return -1; }
    int r=nr_bad(ENOENT);
    for(size_t i=0;i<p.count;i++) if(!strcmp(p.members[i].name,module)) {
        uint8_t h[80]; if(nr_read(p.members[i].storage,0,h,sizeof h)) break;
        if(memcmp(h,"NSO0",4)) { r=nr_bad(EBADMSG); break; }
        char actual[33]; for(unsigned j=0;j<16;j++) snprintf(actual+j*2,3,"%02x",h[64+j]);
        r=strcmp(actual,hex)?nr_bad(EINVAL):0; break;
    }
    int e=errno; nr_pfs_free(&p); if(r) errno=e; return r;
}

/* ---- Front ends: lightweight resource discovery (read-only probes) ----
 * A launcher has to answer "which of these files is this game's base, update and
 * key file?" before it may mount anything. These probes read a container's table
 * and its Program NCA header (a few KiB in total, whatever the file's size) and
 * never look at payload, so scanning a folder of 15 GB dumps stays cheap. */
static int nr_program_flags(const nr_nca *n,int *patched) {
    for(unsigned i=0;i<4;i++) {
        if(!nr32(n->h+0x244+i*16)) continue;
        const uint8_t *h=n->h+0x400+i*512;
        if(h[2]) continue;                       // not the RomFS section (0 = RomFS)
        *patched=h[4]==4;                        // 4 = PatchRomFS (BKTR), the update's storage
        return 0;
    }
    return nr_bad(ENOTSUP);                      // a Program NCA without RomFS is not game content
}
int nxrom_probe_container(const char *path,const char *keyfile,int *format,int *programs,
                          int *patched,uint64_t *title,char *error,size_t cap) {
    if(format) *format=0; if(programs) *programs=0; if(patched) *patched=0; if(title) *title=0;
    if(!path||!*path) { if(cap) snprintf(error,cap,"no path given"); return nr_bad(EINVAL); }
    nr_store *file=nr_file(path); if(!file) { if(cap) snprintf(error,cap,"cannot read the file (%s)",strerror(errno)); return -1; }
    nr_pfs p={0}; nr_keys keys={0}; int r=-1, gamecard, more=0;
    uint64_t program_title=0; int patched_flag=0; size_t programs_seen=0;
    gamecard=nr_xci_probe(file);
    if(gamecard<0) { if(cap) snprintf(error,cap,"cannot read the container header"); }
    else {
        if(format) *format=gamecard?NXROM_XCI:NXROM_NSP;
        if(gamecard?nr_xci(file,&p):nr_pfs_open(file,&p)) {
            if(format) *format=0;
            if(cap) snprintf(error,cap,"%s",errno==ENOTSUP?"not an NSP or XCI container":"the container table is damaged");
        } else if(!keyfile||!*keyfile) { nr_bad(EACCES); if(cap) snprintf(error,cap,"console keys are needed to read the container's headers"); }
        else if(nr_keys_load(keyfile,&keys)) { if(cap) snprintf(error,cap,"cannot read the console keys"); }
        else {
            const uint8_t *hk=nr_key_get(&keys,"header_key",32);
            if(!hk) { nr_bad(EACCES); if(cap) snprintf(error,cap,"the console keys have no header_key entry"); }
            else for(size_t i=0;i<p.count;i++) {
                nr_nca n={0};
                if(!nr_suffix(p.members[i].name,".nca")) continue;
                n.raw=p.members[i].storage;
                if(nr_read(n.raw,0,n.h,sizeof n.h)) { nr_wipe(&n,sizeof n); continue; }   // not a readable member: skip, the mount reports it
                if(nr_header(n.h,hk)) { nr_wipe(&n,sizeof n); continue; }
                if(memcmp(n.h+0x200,"NCA3",4)||n.h[0x205]!=0) { nr_wipe(&n,sizeof n); continue; }   // not a Program NCA (DLC, metadata, tickets)
                programs_seen++;
                if(programs_seen>1) { more=1; nr_wipe(&n,sizeof n); break; }
                program_title=nr64(n.h+0x210);
                { int pf=0; if(!nr_program_flags(&n,&pf)) patched_flag=pf; }
                nr_wipe(&n,sizeof n);
            }
            if(more) { nr_bad(ENOTSUP); if(cap) snprintf(error,cap,"the container holds more than one Program NCA"); }
            else if(!programs_seen) { nr_bad(ENOENT); if(cap) snprintf(error,cap,"no Program NCA: this container is not game content"); }
            else { if(programs) *programs=1; if(patched) *patched=patched_flag; if(title) *title=program_title; r=0; }
        }
    }
    nr_keys_free(&keys); nr_pfs_free(&p); nr_drop(file);
    return r;
}
int nxrom_keys_usable(const char *path,char *error,size_t cap) {
    if(!path||!*path) { if(cap) snprintf(error,cap,"no path given"); return nr_bad(EINVAL); }
    nr_keys keys={0};
    if(nr_keys_load(path,&keys)) { if(cap) snprintf(error,cap,"cannot read the keys file"); nr_keys_free(&keys); return -1; }
    int header=0, area=0;
    for(size_t i=0;i<keys.count;i++) {
        if(!strcmp(keys.items[i].name,"header_key")&&keys.items[i].size==32) header=1;
        if(keys.items[i].size==16&&(!strncmp(keys.items[i].name,"key_area_key_",13)||!strncmp(keys.items[i].name,"titlekek_",9))) area=1;
    }
    nr_keys_free(&keys);
    if(!header||!area) {
        if(cap) snprintf(error,cap,"%s%s%s",header?"":"missing header_key",(!header&&!area)?", ":"",area?"":"missing key_area_key / titlekek");
        return nr_bad(EACCES);
    }
    return 0;
}
int nxrom_verify(const char *base,const char *update,const char *keys,uint64_t title,
                 const char *const *modules,const char *const *builds,size_t count,
                 char *error,size_t cap) {
    if(!base||!*base||!modules||!builds||!count) { if(cap) snprintf(error,cap,"prepared module metadata is unavailable"); return nr_bad(EINVAL); }
    nxrom *fs=NULL;
    if(nxrom_open(base,update&&*update?update:NULL,keys,title,&fs,error,cap)) return -1;
    int r=0;
    for(size_t i=0;i<count&&!r;i++) if(nxrom_check_build(fs,modules[i],builds[i])) {
        if(cap) snprintf(error,cap,"Selected base/update does not match prepared module %s. Choose the matching game version.",modules[i]);
        r=-1;
    }
    nxrom_close(fs);
    if(r) errno=EINVAL;
    return r;
}
