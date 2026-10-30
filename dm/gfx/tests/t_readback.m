// NVN readback contract: a pending clear must reach both GPU buffer copies and CPU reads.
// Expected 8x4 RGBA values are literal bytes, independent of the Metal replay's state.
#define nvn_game_fps nvn_game_fps_mtl_default
#include "../nvn/nvn_mtl.m"
#undef nvn_game_fps
#define g_ft g_ft_hle
#include "../nvn/hle_nvn.c"
#undef g_ft
uint64_t g_t0_ns;
void *front_metal_layer(void) { return NULL; }
module_t *module_of(const void *p) { (void)p; return NULL; }
module_t g_mod[MAX_MOD]; int g_nmod;
void svc_thread_dump(void) {}
uint64_t now_ns(void) { return bp_now(); }
static int cases, failed;
#define EXPECT(n,w,v) do { int a=(w), b=(v); cases++; printf("%s expected %d -> got %d %s\n",n,a,b,a==b?"PASS":"FAIL"); failed+=a!=b; } while (0)
// A texture in a virtual pool the host aliases in place: MapVirtual points the pool straight at a physical pool's memory, so the pool is no
// page table (nvn_sparse_pool() is 0) and its bytes are the ones the GPU samples. Its first-use content is therefore its storage, like any
// other pool's texture — FC 27 streams every pitch and kit material into such a pool from its loader, and the host left them all as zeros, so
// the pitch and the players came out black (section 16 of docs/research/fc27-bringup.md). A uniform texel makes the check independent
// of the block-linear layout, which only permutes texels.
static void virtual_pool_fill_case(void) {
    void *mem = NULL; if (posix_memalign(&mem, getpagesize(), 262144)) abort();
    for (int i = 0; i < 262144; i += 4) { uint8_t *p = (uint8_t *)mem + i; p[0] = 51; p[1] = 102; p[2] = 153; p[3] = 255; }
    pool_t pool = {.mem = mem, .size = 262144, .flags = 0x221}; mtl_pool_add(mem, 262144);   // VIRTUAL | CPU_NO_ACCESS | GPU_CACHED, aliased in place
    NVNtextureBuilder tb; NVNtexture tex; h_nvnTextureBuilderSetDefaults(&tb);
    h_nvnTextureBuilderSetWidth(&tb, 16); h_nvnTextureBuilderSetHeight(&tb, 16); h_nvnTextureBuilderSetFormat(&tb, NVN_FORMAT_RGBA8);
    h_nvnTextureBuilderSetStorage(&tb, (const NVNmemoryPool *)&pool, 65536);
    EXPECT("virtual (aliased) pool texture init", 1, h_nvnTextureInitialize(&tex, &tb));
    mtl_sub_begin(); id<MTLTexture> ht = tex_mtl((const tex_t *)&tex);
    EXPECT("virtual (aliased) pool texture resolved", 1, ht != nil);
    EXPECT("virtual (aliased) pool texture upload committed", 1, mtl_wait(mtl_sub_commit(), 5000000000ull) && !mtl_last_commit_error());
    mtl_finish_gpu();
    id<MTLBuffer> rb = [g_dev newBufferWithLength:16 * 16 * 4 options:MTLResourceStorageModeShared];
    id<MTLCommandBuffer> cb = q_cb(); id<MTLBlitCommandEncoder> be = [cb blitCommandEncoder];
    [be copyFromTexture:ht sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0, 0, 0) sourceSize:MTLSizeMake(16, 16, 1)
               toBuffer:rb destinationOffset:0 destinationBytesPerRow:64 destinationBytesPerImage:1024];
    [be endEncoding]; [cb commit]; [cb waitUntilCompleted];
    static const uint8_t want[] = {51, 102, 153, 255}; int bad = 0;
    for (int i = 0; i < 16 * 16; i++) bad += memcmp((uint8_t *)rb.contents + i * 4, want, 4) != 0;
    EXPECT("virtual (aliased) pool texture -> its storage's content, 256 literal pixels", 0, bad);
    h_nvnTextureFinalize(&tex);
    // A virtual pool that has no address yet (created before its first MapVirtual) has no storage to read: the texture is zeros, not a crash
    pool_t npool = {.mem = NULL, .size = 65536, .flags = 0x221};
    NVNtexture ntex; h_nvnTextureBuilderSetStorage(&tb, (const NVNmemoryPool *)&npool, 0);
    EXPECT("unmapped virtual pool texture init", 1, h_nvnTextureInitialize(&ntex, &tb));
    mtl_sub_begin(); id<MTLTexture> nt = tex_mtl((const tex_t *)&ntex);
    EXPECT("unmapped virtual pool texture resolved", 1, nt != nil); mtl_sub_commit(); mtl_finish_gpu();
    memset(rb.contents, 0xEE, 16 * 16 * 4);
    id<MTLCommandBuffer> cb2 = q_cb(); id<MTLBlitCommandEncoder> be2 = [cb2 blitCommandEncoder];
    [be2 copyFromTexture:nt sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0, 0, 0) sourceSize:MTLSizeMake(16, 16, 1)
                toBuffer:rb destinationOffset:0 destinationBytesPerRow:64 destinationBytesPerImage:1024];
    [be2 endEncoding]; [cb2 commit]; [cb2 waitUntilCompleted];
    bad = 0; for (int i = 0; i < 16 * 16 * 4; i++) bad += ((uint8_t *)rb.contents)[i] != 0;
    EXPECT("virtual pool without an address -> zeros, no crash", 0, bad);
    h_nvnTextureFinalize(&ntex);
    mtl_pool_del(mem); free(mem);
}

// A pool's CPU cache attribute decides whether nvnMemoryPoolFlushMappedRange is needed at all: it publishes a CPU_CACHED pool's writes, while a
// CPU_UNCACHED pool's stores are already in memory, so the GPU reads them without one. FC 27 fills 95 textures in CPU_UNCACHED pools from its own
// loader and never flushes them; the host used to insist on a flush for every CPU-visible pool and left them as GPU textures of zeros (section 17 of
// docs/research/fc27-bringup.md). The three cases below pin the rule: uncached is content, cached without a flush is zeros, cached with a
// flush that covers the texture is content again. The texel is uniform, so the block-linear layout only permutes it.
static NVNtexture tex_dummy;   // cpu_pool_texels' texture object
static pool_t cpu_pools[4];     // one pool object per case: the host shares a texture by pool object, offset and description, so they must differ
static int cpu_pool_texels(uint32_t flags, int flush, int slot) {   // texels of a 16x16 RGBA8 texture at a pool's offset 65536 that do not read the uniform {51,102,153,255}
    void *mem = NULL; if (posix_memalign(&mem, getpagesize(), 262144)) abort();
    for (int i = 0; i < 262144; i += 4) { uint8_t *p = (uint8_t *)mem + i; p[0] = 51; p[1] = 102; p[2] = 153; p[3] = 255; }
    pool_t *pool = &cpu_pools[slot]; *pool = (pool_t){.mem = mem, .size = 262144, .flags = flags}; mtl_pool_add(mem, 262144);
    NVNtextureBuilder tb; h_nvnTextureBuilderSetDefaults(&tb);
    h_nvnTextureBuilderSetWidth(&tb, 16); h_nvnTextureBuilderSetHeight(&tb, 16); h_nvnTextureBuilderSetFormat(&tb, NVN_FORMAT_RGBA8);
    h_nvnTextureBuilderSetStorage(&tb, (NVNmemoryPool *)pool, 65536);
    if (!h_nvnTextureInitialize(&tex_dummy, &tb)) { mtl_pool_del(mem); free(mem); return -1; }
    if (flush) h_nvnMemoryPoolFlushMappedRange((NVNmemoryPool *)pool, 0, 262144);
    mtl_sub_begin(); id<MTLTexture> ht = tex_mtl((const tex_t *)&tex_dummy); mtl_sub_commit(); mtl_finish_gpu();
    int nz = -1;
    if (ht) {
        id<MTLBuffer> rb = [g_dev newBufferWithLength:16 * 16 * 4 options:MTLResourceStorageModeShared];
        memset(rb.contents, 0xEE, 16 * 16 * 4);
        id<MTLCommandBuffer> cb = q_cb(); id<MTLBlitCommandEncoder> be = [cb blitCommandEncoder];
        [be copyFromTexture:ht sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0, 0, 0) sourceSize:MTLSizeMake(16, 16, 1)
                   toBuffer:rb destinationOffset:0 destinationBytesPerRow:64 destinationBytesPerImage:1024];
        [be endEncoding]; [cb commit]; [cb waitUntilCompleted];
        static const uint8_t want[] = {51, 102, 153, 255};
        nz = 0; for (int i = 0; i < 16 * 16; i++) nz += memcmp((uint8_t *)rb.contents + i * 4, want, 4) != 0;
    }
    h_nvnTextureFinalize(&tex_dummy); mtl_pool_del(mem); free(mem);
    return nz;
}
static void cpu_pool_cache_case(void) {
    EXPECT("CPU_UNCACHED pool, no flush -> its storage's content, 256 literal pixels", 0, cpu_pool_texels(0x22, 0, 0));
    EXPECT("CPU_CACHED pool, no flush -> zeros, 256 texels", 256, cpu_pool_texels(0x24, 0, 1));
    EXPECT("CPU_CACHED pool with a flush covering it -> its storage's content, 256 literal pixels", 0, cpu_pool_texels(0x24, 1, 2));
}

int main(void) { @autoreleasepool {
    mtl_init();
    void *mem = NULL; if (posix_memalign(&mem, getpagesize(), 262144)) abort(); memset(mem, 0, 262144);
    pool_t pool = {.mem=mem, .size=262144}; mtl_pool_add(mem, 262144);
    NVNtextureBuilder tb; NVNtexture tex; h_nvnTextureBuilderSetDefaults(&tb); h_nvnTextureBuilderSetWidth(&tb, 8);
    h_nvnTextureBuilderSetHeight(&tb, 4); h_nvnTextureBuilderSetFormat(&tb, NVN_FORMAT_RGBA8);
    h_nvnTextureBuilderSetStorage(&tb, (const NVNmemoryPool *)&pool, 131072); EXPECT("texture init", 1, h_nvnTextureInitialize(&tex, &tb));
    NVNcommandBuffer cmd; EXPECT("command init", 1, h_nvnCommandBufferInitialize(&cmd, NULL));
    h_nvnCommandBufferAddCommandMemory(&cmd, (const NVNmemoryPool *)&pool, 0, 65536);
    h_nvnCommandBufferBeginRecording(&cmd);
    const NVNtexture *targets[] = {&tex}; const NVNtextureView *views[] = {NULL};
    h_nvnCommandBufferSetRenderTargets(&cmd, 1, targets, views, NULL, NULL);
    float color[] = {0.2f, 0.4f, 0.6f, 1.f}; h_nvnCommandBufferClearColor(&cmd, 0, color, 15);
    NVNcopyRegion region = {0, 0, 0, 8, 4, 1}; uint8_t *out = (uint8_t *)mem + 196608; memset(out, 0xEE, 256);
    h_nvnCommandBufferSetCopyRowStride(&cmd, 64);
    h_nvnCommandBufferCopyTextureToBuffer(&cmd, &tex, NULL, &region, (NVNbufferAddress)out, 0);
    NVNsync sync; h_nvnSyncInitialize(&sync, NULL);
    h_nvnCommandBufferFenceSync(&cmd, &sync, NVN_SYNC_CONDITION_ALL_GPU_COMMANDS_COMPLETE, 0);
    NVNcommandHandle h = h_nvnCommandBufferEndRecording(&cmd);
    state_reset(); memset(&R, 0, sizeof R); mtl_sub_begin(); mtl_exec((const uint8_t *)h); mtl_sub_commit();
    int wait = h_nvnSyncWait(&sync, 5000000000ull); EXPECT("recorded fence wait", 1, wait == 0 || wait == 1);
    EXPECT("GPU success", 0, mtl_last_commit_error());
    static const uint8_t expected[] = {51, 102, 153, 255}; int bad = 0;
    for (int y=0; y<4; y++) { for (int x=0; x<8; x++) bad += memcmp(out+y*64+x*4, expected, 4) != 0;
        for (int x=32; x<64; x++) bad += out[y*64+x] != 0xEE; }
    EXPECT("pending clear -> GPU copy, literal pixels and untouched row padding", 0, bad);
    uint8_t cpu[128]; memset(cpu, 0xEE, sizeof cpu); h_nvnTextureReadTexels(&tex, NULL, &region, cpu); bad = 0;
    for (int i=0; i<32; i++) bad += memcmp(cpu+i*4, expected, 4) != 0;
    EXPECT("GPU clear -> CPU ReadTexels, 32 literal pixels", 0, bad);
    // FC 27 copies the depth plane of D32S8 into a D32F sampled texture.
    // Stencil is absent from the destination; it must not make the depth copy fail.
    MTLTextureDescriptor *sd = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatDepth32Float_Stencil8 width:8 height:4 mipmapped:NO];
    sd.usage = MTLTextureUsageRenderTarget | MTLTextureUsageShaderRead | MTLTextureUsagePixelFormatView;
    id<MTLTexture> srcDepth = [g_dev newTextureWithDescriptor:sd];
    sd.pixelFormat = MTLPixelFormatDepth32Float;
    id<MTLTexture> dstDepth = [g_dev newTextureWithDescriptor:sd]; res_add(srcDepth); res_add(dstDepth);
    id<MTLCommandBuffer> init = q_cb(); MTLRenderPassDescriptor *rd = [MTLRenderPassDescriptor renderPassDescriptor];
    rd.depthAttachment.texture = srcDepth; rd.depthAttachment.loadAction = MTLLoadActionClear;
    rd.depthAttachment.storeAction = MTLStoreActionStore; rd.depthAttachment.clearDepth = 0.375;
    id<MTLRenderCommandEncoder> ie = [init renderCommandEncoderWithDescriptor:rd]; [ie endEncoding]; [init commit]; [init waitUntilCompleted];
    NVNcopyRegion dr = {0,0,0,8,4,1};
    mtl_sub_begin();
    EXPECT("D32S8 -> D32F depth-plane conversion accepted", 1, copy_t2t_draw(srcDepth, dstDepth, 0,0,0,0,&dr,&dr,0,0));
    mtl_sub_commit(); mtl_finish_gpu();
    id<MTLBuffer> db = [g_dev newBufferWithLength:128 options:MTLResourceStorageModeShared];
    id<MTLCommandBuffer> read = q_cb(); id<MTLBlitCommandEncoder> de = [read blitCommandEncoder];
    [de copyFromTexture:dstDepth sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0,0,0) sourceSize:MTLSizeMake(8,4,1)
              toBuffer:db destinationOffset:0 destinationBytesPerRow:32 destinationBytesPerImage:128];
    [de endEncoding]; [read commit]; [read waitUntilCompleted]; bad = 0;
    for (int i=0;i<32;i++) bad += ((float *)db.contents)[i] != 0.375f;
    EXPECT("D32S8 -> D32F preserves all depth values", 0, bad);
    // The optional draw attribution copies must land on the replay queue and be
    // published only after its fence; row padding is deterministic too.
    char roiDir[] = "/tmp/dm_drawroi_XXXXXX"; mkdtemp(roiDir);
    char roiReq[1200]; snprintf(roiReq,sizeof roiReq,"0,0,8,4,%s",roiDir); setenv("DM_NVN_DRAWROI",roiReq,1);
    g_pd_a0 = g_pd_a1 = atomic_load(&g_cur_frame);
    R.rt.n=1; R.rt.color[0]=TX(&tex); R.rt.depth=NULL;
    mtl_sub_begin(); EXPECT("draw ROI arms explicitly",1,drawroi(1));
    EXPECT("draw ROI pending until submit",1,g_roi_pending.count);
    NSString *roiStem=[g_roi_pending.lastObject->stem copy];
    mtl_sub_commit(); mtl_finish_gpu(); g_pd_a0=-1; drawroi(1);
    EXPECT("draw ROI released after completed fence",0,g_roi_pending.count);
    FILE *rf=fopen([[roiStem stringByAppendingString:@".raw"] UTF8String],"rb");
    EXPECT("draw ROI raw published",1,rf!=NULL); bad=0;
    if (rf) { unsigned rw,rh,pf,rs; fscanf(rf,"%u %u %u %u\n",&rw,&rh,&pf,&rs);
        EXPECT("draw ROI row stride",128,rs); uint8_t pixels[512]; bad=fread(pixels,1,sizeof pixels,rf)!=sizeof pixels; fclose(rf);
        for(int y=0;y<4;y++) for(int x=0;x<8;x++) bad+=memcmp(pixels+y*128+x*4,expected,4)!=0;
        EXPECT("draw ROI exact texels",0,bad);
    }
    unsetenv("DM_NVN_DRAWROI");
    h_nvnTextureFinalize(&tex); mtl_pool_del(mem); free(mem);
    virtual_pool_fill_case();
    cpu_pool_cache_case();
    printf("READBACK cases=%d failed=%d\n", cases, failed); return failed != 0;
} }
