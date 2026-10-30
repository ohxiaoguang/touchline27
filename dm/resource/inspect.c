// SPDX-License-Identifier: MIT
// Standalone bounded-memory inspector; no HLE/game profile dependency.
#include "nxrom.h"
#include <CommonCrypto/CommonDigest.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <getopt.h>
#include <errno.h>
#include <inttypes.h>
#include <limits.h>
static void usage(void) { fprintf(stderr,"nxrom-inspect --base FILE --keys FILE [--update FILE] [--title HEX] [--verify | --read PATH [--offset N] [--length N]]\n"); }
static int number(const char *text,int base,uint64_t *out) {
    char *end; if(!text||!*text||*text=='-') return -1; errno=0; unsigned long long n=strtoull(text,&end,base); if(errno||*end) return -1; *out=n; return 0;
}
int main(int argc,char **argv) {
    const char *base=NULL,*update=NULL,*keys=NULL,*path=NULL; uint64_t title=0,offset=0,length=UINT64_MAX; int verify=0,opt;
    const struct option options[]={ {"base",1,0,'b'},{"update",1,0,'u'},{"keys",1,0,'k'},{"title",1,0,'t'},{"verify",0,0,'v'},{"read",1,0,'r'},{"offset",1,0,'o'},{"length",1,0,'l'},{0,0,0,0} };
    while((opt=getopt_long(argc,argv,"",options,NULL))!=-1) {
        switch(opt) { case 'b':base=optarg;break;case 'u':update=optarg;break;case 'k':keys=optarg;break;case 'v':verify=1;break;case 'r':path=optarg;break;
            case 't':if(number(optarg,16,&title)) { usage(); return 2; } break;
            case 'o':if(number(optarg,0,&offset)||offset>INT64_MAX) { usage(); return 2; } break;
            case 'l':if(number(optarg,0,&length)) { usage(); return 2; } break;
            default:usage();return 2;
        }
    }
    if(!base||!keys||optind!=argc||(verify&&path)) { usage(); return 2; }
    nxrom *fs=NULL; char error[512]; if(nxrom_open(base,update,keys,title,&fs,error,sizeof error)) { fprintf(stderr,"[RED] %s\n",error); return 1; }
    uint8_t buffer[65536]; int result=0;
    if(path) {
        uint64_t id; nxrom_info info;
        if(nxrom_find(fs,path,&id)||nxrom_stat(fs,id,&info)||info.directory) { fprintf(stderr,"[RED] resource path unavailable\n"); result=1; goto done; }
        if(offset>=info.size) length=0; else if(length>info.size-offset) length=info.size-offset;
        while(length) { size_t n=length<sizeof buffer?(size_t)length:sizeof buffer;
            if(nxrom_read(fs,id,buffer,n,(int64_t)offset)!=(ssize_t)n||fwrite(buffer,1,n,stdout)!=n) { result=1; break; } length-=n; offset+=n;
        }
    } else {
        nxrom_info info;
        for(uint64_t id=0;!nxrom_stat(fs,id,&info);id++) {
            if(!*info.path) continue;
            printf("%c\t/%s",info.directory?'d':'f',info.path);
            if(!info.directory) {
                printf("\t%"PRIu64,info.size);
                if(verify) {
                    CC_SHA256_CTX hash; CC_SHA256_Init(&hash);
                    for(uint64_t at=0;at<info.size;) { size_t n=info.size-at<sizeof buffer?(size_t)(info.size-at):sizeof buffer;
                        if(nxrom_read(fs,id,buffer,n,(int64_t)at)!=(ssize_t)n) { fprintf(stderr,"[RED] read/integrity failure: %s, errno=%d\n",info.path,errno); result=1; goto done; }
                        CC_SHA256_Update(&hash,buffer,(CC_LONG)n); at+=n;
                    }
                    uint8_t digest[32]; CC_SHA256_Final(digest,&hash); putchar('\t'); for(unsigned i=0;i<32;i++) printf("%02x",digest[i]);
                }
            } putchar('\n');
        }
    }
done:
    if(ferror(stdout)||fflush(stdout)) result=1; nxrom_close(fs); return result;
}
