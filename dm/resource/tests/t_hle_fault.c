// SPDX-License-Identifier: MIT
// Destroy only an owned synthetic-container clone; never alter the input fixture.
#include "../../host/hle_fs.c"
struct dm_flags g_flag; uint64_t g_t0_ns;
uint64_t now_ns(void) { return 0; }
void dm_guest_write_prepare(void *a,size_t n) { (void)a; (void)n; }
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"failed line %d: %s\n",__LINE__,#x); return 1; } } while(0)
static int save_text(const char *path,const char *text) {
    uint64_t h; if(h_fs_CreateFile(path,0) || h_fs_OpenFile(&h,path,MODE_WRITE)) return 0;
    Result r=h_fs_WriteFile(h,0,text,strlen(text),NULL); h_fs_CloseFile(h); return !r;
}
static int check_save(void) {
    uint64_t h; char b[8]={0}; size_t n=0;
    if(h_fs_OpenFile(&h,"save:/progress",MODE_READ)) return 0;
    Result r=h_fs_ReadFile(&n,h,0,b,sizeof b); h_fs_CloseFile(h);
    return !r && n==4 && !memcmp(b,"GOOD",4);
}
static int check_committed(const char *save) {
    char path[1400],b[8]={0}; snprintf(path,sizeof path,"%s/progress",save);
    int fd=open(path,O_RDONLY); if(fd<0) return 0;
    ssize_t n=pread(fd,b,sizeof b,0); close(fd);
    return n==4 && !memcmp(b,"GOOD",4);
}
int main(int argc,char **argv) {
    CHECK(argc==4);
    char root[1024],source[1200],save[1200];
    CHECK(snprintf(root,sizeof root,"%s/fault-XXXXXX",argv[3])<(int)sizeof root);
    CHECK(mkdtemp(root));
    snprintf(source,sizeof source,"%s/source.nsp",root);
    snprintf(save,sizeof save,"%s/save",root);
    CHECK(!clonefile(argv[1],source,0)); CHECK(!mkdir(save,0700));
    setenv("DM_SAVE",save,1); CHECK(!h_fs_MountSave("save",NULL));
    CHECK(save_text("save:/progress","GOOD") && !h_fs_Commit("save") && check_save());
    setenv("DM_RESOURCE_BACKEND","nsp",1); setenv("DM_RESOURCE_NSP",source,1);
    setenv("DM_RESOURCE_KEYS",argv[2],1); unsetenv("DM_RESOURCE_UPDATE");
    g_nmod=1; strlcpy(g_mod[0].name,"main",sizeof g_mod[0].name);
    strlcpy(g_mod[0].build_id,"202122232425262728292a2b2c2d2e2f",sizeof g_mod[0].build_id);
    CHECK(!h_fs_MountRom("rom",NULL,0));
    uint64_t h=0; CHECK(!h_fs_OpenFile(&h,"rom:/nested/big",MODE_READ));
    int64_t size=0; CHECK(!h_fs_GetFileSize(&size,h) && size>200016);
    CHECK(!truncate(source,0));
    char b[16]; size_t n=SIZE_MAX;
    CHECK(h_fs_ReadFile(&n,h,200000,b,sizeof b)==RES_FAIL && n==0);
    CHECK(h_fs_ReadFileExact(h,200000,b,sizeof b)==RES_FAIL); h_fs_CloseFile(h);
    CHECK(check_save() && check_committed(save));
    CHECK(save_text("save:/after-error","OK") && !h_fs_Commit("save") && check_save() && check_committed(save));
    puts("HLE NSP: storage loss reports failure with zero bytes; committed save survives and remains writable");
    return 0;
}
