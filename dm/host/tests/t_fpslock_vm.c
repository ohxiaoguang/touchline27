// Exercise the production Mach write boundary, including a page that cannot be written.
#include "../hle_fpslock.c"
#include <sys/mman.h>
#include <assert.h>
#include <unistd.h>
module_t g_mod[MAX_MOD]; int g_nmod;
static uint8_t *region; static size_t region_size; static int prepared;
void svc_guest_range(uint8_t **base,size_t *size){*base=region;*size=region_size;}
void dm_guest_write_prepare(void *addr,size_t n){(void)addr;(void)n;prepared++;}
int main(void){
 region_size=(size_t)getpagesize();region=mmap(NULL,region_size,PROT_READ|PROT_WRITE,MAP_ANON|MAP_PRIVATE,-1,0);assert(region!=MAP_FAILED);
 double value=60;uint64_t a=(uint64_t)(uintptr_t)region;
 assert(fc27_write(a,&value,8));assert(*(double *)region==60 && prepared==1);
 assert(!fc27_write(a-1,&value,8));assert(!fc27_write(a+region_size-4,&value,8));
 assert(mprotect(region,region_size,PROT_READ)==0);assert(!fc27_write(a,&value,8));assert(prepared==1);
 // A dangling guest address must fail without a userspace access/fault.
 assert(munmap(region,region_size)==0);assert(!fc27_write(a,&value,8));
 g_nmod=1;strcpy(g_mod[0].name,"main");strcpy(g_mod[0].build_id,"c2a256339b29922415331fab57de2565");
 dm_fps_lock_tick();assert(dm_fps_lock_present_cap()==0); // v0 keeps its present semantics
 puts("FC27 Mach writes: guest bounds, read-only, unmapped, build/present fallback OK");
}
