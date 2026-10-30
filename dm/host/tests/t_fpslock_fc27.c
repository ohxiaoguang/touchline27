#include "../fpslock_fc27.h"
#include <assert.h>
#include <stdio.h>
#include <math.h>
static unsigned char mem[0x10000];
static const uint64_t base = 0x100000000, obj = 0x2000, cfg = 0x4000, world = 0x6000, dr = 0x8000;
static int deny, writes;
static int read_mem(uint64_t a, void *p, size_t n) {
    uint64_t v;
    if (a == base+0xda1ee38) v=obj;
    else if (a == base+0xde82020) v=cfg;
    else if (a == base+0xde81da0) v=world;
    else if (a == world+0x14c8) v=dr;
    else { if (a > sizeof mem || n > sizeof mem-a) return 0; memcpy(p,mem+a,n);return 1; }
    assert(n==8);memcpy(p,&v,8);return 1;
}
static int write_mem(uint64_t a, void *p, size_t n) {
    if (deny || a > sizeof mem || n > sizeof mem-a) return 0;
    writes++;memcpy(mem+a,p,n);return 1;
}
static int unreadable(uint64_t a, void *p, size_t n) { (void)a;(void)p;(void)n;return 0; }
static void setd(uint64_t a,double d){memcpy(mem+a,&d,8);}
static void setf(uint64_t a,float f){memcpy(mem+a,&f,4);}
static double getd(uint64_t a){double d;memcpy(&d,mem+a,8);return d;}
static float getf(uint64_t a){float f;memcpy(&f,mem+a,4);return f;}
static void reset(void){memset(mem,0,sizeof mem);deny=writes=0;setd(obj+8,30);setf(cfg+0xf8,33.333333f);setf(cfg+0x144,35);setf(dr+0xc,33.333333f);setf(dr+0x10,35);}
static int tick(int fps){return fc27_tick("0100C49025D3E000",FC27_BUILD,base,fps,read_mem,write_mem);}
int main(void){
 reset();assert(tick(30)==0 && writes==0);assert(getf(cfg+0x144)==35); // original DR preserved
 assert(fabsf(fc27_ms(30)-33.333333f)<0.00001f);assert(fabsf(fc27_ms(60)-16.666667f)<0.00001f);
 assert(tick(60)==31 && getd(obj+8)==60);assert(getf(cfg+0xf8)==fc27_ms(60));assert(getf(cfg+0x144)==getf(dr+0x10));assert(getf(dr+0xc)==getf(dr+0x10));
 writes=0;assert(tick(60)==0 && writes==0); // idempotent
 setd(obj+8,30);setf(cfg+0x144,33);setf(dr+0xc,33);assert(tick(60)==13); // game rewrites/scene reinitialisation
 reset();assert(fc27_tick("0100C49025D3E000","c2a256339b29922415331fab57de2565",base,60,read_mem,write_mem)==0 && writes==0);
 assert(fc27_tick("0100000000010000",FC27_BUILD,base,60,read_mem,write_mem)==0 && writes==0);
 assert(tick(0)==0 && tick(120)==0 && writes==0);
 assert(fc27_tick("0100C49025D3E000",FC27_BUILD,UINT64_MAX,60,read_mem,write_mem)==0);
 deny=1;assert(tick(60)==-1 && writes==0);deny=0;assert(tick(60)==31);
 reset();setd(obj+8,NAN);setf(cfg+0xf8,0);setf(cfg+0x144,INFINITY);assert(tick(60)==26);assert(isnan(getd(obj+8)));
 assert(fc27_field(read_mem,write_mem,0x100000,1,60)==0);assert(fc27_field(read_mem,write_mem,obj+9,1,60)==0);
 reset();assert(fc27_tick("0100C49025D3E000",FC27_BUILD,base,60,unreadable,write_mem)==0 && writes==0);
 memset(mem+obj,0xa5,8);memset(mem+obj+16,0x5a,8);assert(tick(60)==31);
 for(int i=0;i<8;i++){assert(mem[obj+i]==0xa5);assert(mem[obj+16+i]==0x5a);} // exact double field only
 puts("FC27 FPS: default, targets, units, identity, safety, restore, original DR and isolation OK");
}
