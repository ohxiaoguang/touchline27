// Read-only acceptance harness: real AOC ABI -> mount -> compare payload bytes.
// No guest executable is launched, no input is changed, no save is mounted.
#include "../../host/hle_fs.c"
#include "../../host/hle_misc.c"
void *guest_sym(const char *name) { (void)name; return NULL; }
module_t *module_of(const void *p) { (void)p; return NULL; }
void hle_bind_system_event(void *g,int clear) { (void)g; (void)clear; }
struct dm_flags g_flag; uint64_t g_t0_ns;
uint64_t now_ns(void) { return 0; }
void dm_guest_write_prepare(void *a,size_t n) { (void)a; (void)n; }
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"failed line %d: %s (errno=%d)\n",__LINE__,#x,errno); return 1; } } while(0)
int main(int argc,char **argv) {
    CHECK(argc>=5); int ids[2047],index=1; int expected=argc>5?1:0;
    const char *count_env=getenv("DM_TEST_AOC_COUNT"),*index_env=getenv("DM_TEST_AOC_INDEX");
    if(count_env) expected=atoi(count_env);
    if(index_env) index=atoi(index_env);
    setenv("DM_RESOURCE_KEYS",argv[1],1); setenv("DM_AOC_APP_VERSION",argv[2],1);
    unsetenv("DM_AOC_NSP_1"); unsetenv("DM_AOC_DIR"); unsetenv("DM_AOC_OWNED");
    if(strcmp(argv[3],"-")) {
        nxrom_content content; char error[256],key[48];
        CHECK(!nxrom_content_meta(argv[3],argv[1],&content,error,sizeof error));index=(int)content.index;
        snprintf(key,sizeof key,"DM_AOC_NSP_%d",index);setenv(key,argv[3],1);
    }
    if(!strcmp(argv[3],"-")&&strcmp(argv[4],"-")) setenv("DM_AOC_DIR",argv[4],1);
    CHECK(h_aoc_Count()==expected); CHECK(h_aoc_List(ids,0,2047)==expected);
    if(!expected) { CHECK(h_fs_MountAoc("missing",1,NULL,0)==RES_TARGET_NOT_FOUND); puts("AOC count=0; not-installed mount refused"); return 0; }
    int present=0;for(int i=0;i<expected;i++) if(ids[i]==index) present=1; CHECK(present);
    size_t cache=0; CHECK(!h_fs_QueryAocCache(&cache,index)&&cache>0);
    CHECK(!h_fs_MountAoc("dlc",index,NULL,cache));
    uint64_t total=0;
    for(int a=5;a<argc;a++) {
        char guest[1024],host[2048]; CHECK(snprintf(guest,sizeof guest,"dlc:/%s",argv[a])<(int)sizeof guest);
        CHECK(snprintf(host,sizeof host,"%s/%d/%s",argv[4],index,argv[a])<(int)sizeof host);
        uint64_t handle=0; int64_t size=-1; CHECK(!h_fs_OpenFile(&handle,guest,MODE_READ));
        CHECK(!h_fs_GetFileSize(&size,handle)&&size>=0);
        FILE *oracle=fopen(host,"rb"); CHECK(oracle!=NULL);
        size_t got=0; uint8_t data[4096],reference[4096]; int64_t offset=0;
        do {
            CHECK(!h_fs_ReadFile(&got,handle,offset,data,sizeof data));
            CHECK(fread(reference,1,got,oracle)==got&&!memcmp(data,reference,got));
            offset+=(int64_t)got;
        } while(got);
        CHECK(offset==size&&fgetc(oracle)==EOF&&!ferror(oracle)); fclose(oracle); h_fs_CloseFile(handle);
        CHECK(h_fs_OpenFile(&handle,guest,MODE_WRITE)!=RES_OK);
        total+=(uint64_t)size;
    }
    printf("AOC count=%d index=%d cache=%zu files=%d bytes=%llu; all reads match LibHac extraction; writes refused\n",expected,index,cache,argc-5,(unsigned long long)total);
    return 0;
}
