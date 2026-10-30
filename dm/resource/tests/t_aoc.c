// Synthetic end-to-end enumeration -> mount -> real content access, with removal.
#include "../../host/hle_fs.c"
#include "../../host/hle_misc.c"
void *guest_sym(const char *name) { (void)name; return NULL; }
module_t *module_of(const void *p) { (void)p; return NULL; }
void hle_bind_system_event(void *g,int clear) { (void)g; (void)clear; }
struct dm_flags g_flag; uint64_t g_t0_ns;
uint64_t now_ns(void) { return 0; }
void dm_guest_write_prepare(void *a,size_t n) { (void)a; (void)n; }
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"failed line %d: %s\n",__LINE__,#x); return 1; } } while(0)
int main(int argc,char **argv) {
    CHECK(argc==5); int ids[2047]; char path[2048];
    setenv("DM_RESOURCE_KEYS",argv[1],1); setenv("DM_AOC_APP_VERSION","0",1);
    CHECK(dm_aoc_list(ids,2047)==0&&h_aoc_Count()==0);
    setenv("DM_AOC_NSP_1",argv[2],1); setenv("DM_AOC_NSP_2",argv[3],1);
    CHECK(dm_aoc_list(ids,2047)==2&&ids[0]==1&&ids[1]==2);
    CHECK(h_aoc_Count()==2&&h_aoc_List(ids,0,2047)==2&&ids[0]==1&&ids[1]==2);
    size_t cache=0;
    CHECK(!h_fs_QueryAocCache(&cache,1)&&cache>0&&cache<0x1000);
    CHECK(!h_fs_MountAoc("aoc1",1,NULL,0));
    uint64_t handle=0; int64_t size=-1;
    CHECK(!h_fs_OpenFile(&handle,"aoc1:/marker",MODE_READ));
    CHECK(!h_fs_GetFileSize(&size,handle)&&size==17);
    char data[64]={0}; size_t read=0;
    CHECK(!h_fs_ReadFile(&read,handle,0,data,sizeof data)&&read==17&&!memcmp(data,"first DLC payload",17)); h_fs_CloseFile(handle);
    CHECK(!h_fs_MountAoc("aoc2",2,NULL,0));
    CHECK(!h_fs_OpenFile(&handle,"aoc2:/marker",MODE_READ));
    CHECK(!h_fs_ReadFile(&read,handle,0,data,sizeof data)&&read==18&&!memcmp(data,"second DLC payload",18)); h_fs_CloseFile(handle);
    CHECK(h_fs_CreateFile("aoc1:/bad",1)!=RES_OK);
    CHECK(!unlink(argv[2]));
    CHECK(dm_aoc_list(ids,2047)==1&&ids[0]==2);
    CHECK(h_fs_MountAoc("removed",1,NULL,0)==RES_TARGET_NOT_FOUND);
    setenv("DM_AOC_NSP_4",argv[3],1); // same payload under a forged index
    CHECK(dm_aoc_list(ids,2047)==1);
    unsetenv("DM_AOC_NSP_1"); unsetenv("DM_AOC_NSP_2"); unsetenv("DM_AOC_NSP_4");
    setenv("DM_AOC_DIR",argv[4],1);
    CHECK(dm_aoc_list(ids,2047)==100&&ids[99]==100);
    snprintf(path,sizeof path,"%s/100/marker",argv[4]); CHECK(!unlink(path));
    CHECK(dm_aoc_list(ids,2047)==99); // empty directory no longer advertises ownership
    setenv("DM_AOC_OWNED","0",1); CHECK(dm_aoc_list(ids,2047)==0);
    CHECK(h_fs_MountAoc("disabled",2,NULL,0)==RES_TARGET_NOT_FOUND);
    puts("AOC: enumeration, real mount/read, write protection, >64 entries, removal and forged index passed");
    return 0;
}
