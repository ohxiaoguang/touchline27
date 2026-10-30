// SPDX-License-Identifier: MIT
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
int dm_mac_resources_check(const char *,const char *,const char *,const char *,uint64_t,char *,size_t);
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"failed line %d: %s\n",__LINE__,#x); return 1; } } while(0)
static void manifest(const char *path,const char *text) {
    FILE *f=fopen(path,"w"); if(!f) { perror("manifest"); exit(1); }
    fputs(text,f); fclose(f);
}
int main(int argc,char **argv) {
    CHECK(argc==5); char path[1200],error[512];
    snprintf(path,sizeof path,"%s/mac-check-XXXXXX",argv[4]);
    int fd=mkstemp(path);CHECK(fd>=0);close(fd);
    manifest(path,"main\t202122232425262728292a2b2c2d2e2f\n");
    CHECK(!dm_mac_resources_check(argv[1],"",argv[2],path,0x010015100B514000ull,error,sizeof error));
    CHECK(!dm_mac_resources_check(argv[1],argv[3],argv[2],path,0x010015100B514000ull,error,sizeof error));
    manifest(path,"main\t00000000000000000000000000000000\n");
    CHECK(dm_mac_resources_check(argv[1],"",argv[2],path,0x010015100B514000ull,error,sizeof error)==-1);
    CHECK(strstr(error,"prepared module main"));
    for(const char **p=(const char *[]){"", "main invalid\n", "main\t202122232425262728292a2b2c2d2e2f trailing\n",NULL};*p;p++) {
        manifest(path,*p);
        CHECK(dm_mac_resources_check(argv[1],"",argv[2],path,0x010015100B514000ull,error,sizeof error)==-1);
        CHECK(*error);
    }
    puts("Mac resource checks: base/update accepted; wrong build and malformed/empty metadata refused");
    return 0;
}
