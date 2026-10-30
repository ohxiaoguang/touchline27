// SPDX-License-Identifier: MIT
#include "../../host/hle_fs.c"
struct dm_flags g_flag; uint64_t g_t0_ns;
uint64_t now_ns(void) { return 0; }
void dm_guest_write_prepare(void *a,size_t n) { (void)a; (void)n; }
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"failed line %d: %s\n",__LINE__,#x); return 1; } } while(0)
int main(int argc,char **argv) {
    // Positional: <base.nsp> <keys> [<update.nsp>]; optional "--mods <dir>" mounts that directory as
    // DM_ROMFS_OVERLAY on the very same container mount the guest reads through.
    const char *pos[3], *mods=NULL, *dlc=NULL; int npos=0;
    for(int i=1;i<argc;i++) { if(!strcmp(argv[i],"--mods")&&i+1<argc) mods=argv[++i]; else if(!strcmp(argv[i],"--dlc")&&i+1<argc) dlc=argv[++i]; else if(npos<3) pos[npos++]=argv[i]; }
    CHECK(npos==2 || npos==3);
    setenv("DM_RESOURCE_BACKEND","nsp",1); setenv("DM_RESOURCE_NSP",pos[0],1); setenv("DM_RESOURCE_KEYS",pos[1],1);
    if(npos==3) setenv("DM_RESOURCE_UPDATE",pos[2],1);
    if(mods) setenv("DM_ROMFS_OVERLAY",mods,1);
    g_nmod=1; strlcpy(g_mod[0].name,"main",sizeof g_mod[0].name);
    strlcpy(g_mod[0].build_id,"00000000000000000000000000000000",sizeof g_mod[0].build_id);
    CHECK(h_fs_MountRom("rom",NULL,0)!=RES_OK);
    strlcpy(g_mod[0].build_id,"202122232425262728292a2b2c2d2e2f",sizeof g_mod[0].build_id);
    CHECK(!h_fs_MountRom("rom",NULL,0));
    uint64_t h=0; CHECK(!h_fs_OpenFile(&h,"rom:/nested/../small",MODE_READ));
    char buf[16]={0}; size_t n=0; int64_t size=-1;
    CHECK(!h_fs_GetFileSize(&size,h) && size==5);
    CHECK(!h_fs_ReadFile(&n,h,1,buf,sizeof buf) && n==4 && !memcmp(buf,"ello",4));
    CHECK(h_fs_ReadFileExact(h,0,buf,6)!=RES_OK);
    CHECK(h_fs_WriteFile(h,0,"x",1,NULL)!=RES_OK);
    CHECK(h_fs_SetFileSize(h,0)!=RES_OK); h_fs_CloseFile(h);
    CHECK(h_fs_OpenFile(&h,"rom:/../../small",MODE_READ)==RES_PATH_NOT_FOUND);
    CHECK(h_fs_CreateFile("rom:/new",0)!=RES_OK);
    int32_t type=-1; CHECK(!h_fs_GetEntryType(&type,"rom:/empty") && type==ENT_DIR);
    int extra=mods?1:0;   // the mod adds one entry at the RomFS root, so every root count is one higher
    uint64_t d=0; int64_t count=-1; CHECK(!h_fs_OpenDirectory(&d,"rom:/",3));
    CHECK(!h_fs_DirCount(&count,d) && count==4+extra);
    DirectoryEntry entries[8]; CHECK(!h_fs_ReadDirectory(&count,entries,d,1) && count==1);
    CHECK(!h_fs_DirCount(&count,d) && count==4+extra);
    CHECK(!h_fs_ReadDirectory(&count,entries,d,8) && count==3+extra);
    CHECK(!h_fs_ReadDirectory(&count,entries,d,8) && count==0); h_fs_CloseDirectory(d);
    CHECK(!h_fs_OpenDirectory(&d,"rom:/empty",3)); CHECK(!h_fs_DirCount(&count,d) && count==0); h_fs_CloseDirectory(d);
    if(mods) {
        // The overlay must be visible through this exact mount, and a path no mod has must still be
        // the container's (the mod covers the same file and adds a new one).
        char mb[16]={0}; size_t mn=0; int64_t ms=-1;
        CHECK(!h_fs_OpenFile(&h,"rom:/zero",MODE_READ));                  // empty in the container, 4 bytes in the mod
        CHECK(!h_fs_GetFileSize(&ms,h) && ms==4);
        CHECK(!h_fs_ReadFile(&mn,h,0,mb,sizeof mb) && mn==4 && !memcmp(mb,"ZERO",4));
        h_fs_CloseFile(h);
        CHECK(!h_fs_OpenFile(&h,"rom:/added",MODE_READ));                 // a file only the mod has
        CHECK(!h_fs_ReadFile(&mn,h,0,mb,sizeof mb) && mn==6 && !memcmp(mb,"added!",6));
        h_fs_CloseFile(h);
        CHECK(!h_fs_OpenFile(&h,"rom:/nested/big",MODE_READ));            // not in the mod: the container answers
        CHECK(!h_fs_GetFileSize(&ms,h) && ms==256*1200); h_fs_CloseFile(h);
        CHECK(h_fs_OpenFile(&h,"rom:/no-such-file",MODE_READ)==RES_PATH_NOT_FOUND);
        CHECK(!h_fs_OpenDirectory(&d,"rom:/",3));
        CHECK(!h_fs_DirCount(&count,d) && count==4+extra);                // the container's entries + the mod's file
        h_fs_CloseDirectory(d);
        puts("HLE NSP + mod overlay: hit, added file, fallback and listing passed");
    }
    if(dlc) {
        setenv("DM_AOC_NSP_1",dlc,1);setenv("DM_AOC_APP_VERSION","0",1);
        int indices[8];CHECK(dm_aoc_list(indices,8)==1&&indices[0]==1);
        CHECK(!h_fs_MountAoc("aoc",1,NULL,0));
        char data[32]={0};size_t read=0;
        CHECK(!h_fs_OpenFile(&h,"aoc:/small",MODE_READ));
        CHECK(!h_fs_ReadFile(&read,h,0,data,sizeof data)&&read==11&&!memcmp(data,"DLC content",11));h_fs_CloseFile(h);
        CHECK(!h_fs_OpenFile(&h,"rom:/small",MODE_READ));
        CHECK(!h_fs_ReadFile(&read,h,0,data,sizeof data)&&read==5&&!memcmp(data,"hello",5));h_fs_CloseFile(h);
        CHECK(h_fs_OpenFile(&h,"aoc:/added",MODE_READ)==RES_PATH_NOT_FOUND); // MOD-only file cannot enter DLC.
        puts("HLE: base/update/MOD and nonempty AOC namespaces stay independent");
    }
    puts("HLE NSP: file/directory/read-only checks passed"); return 0;
}
