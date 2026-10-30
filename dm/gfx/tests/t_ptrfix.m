// Synthetic GPU read contract. MSL is generated from dmsh_ptrfix.body, not a game.
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <stdio.h>
int main(int argc, char **argv) { @autoreleasepool {
    if (argc != 2) return 2;
    id<MTLDevice> dev = MTLCreateSystemDefaultDevice();
    if (!dev) { fprintf(stderr, "[RED] No Metal device for pointer regression\n"); return 2; }
    NSError *error = nil;
    NSString *source = [NSString stringWithContentsOfFile:@(argv[1]) encoding:NSUTF8StringEncoding error:&error];
    id<MTLLibrary> lib = [dev newLibraryWithSource:source options:nil error:&error];
    if (!lib) { fprintf(stderr, "[RED] %s\n", error.localizedDescription.UTF8String); return 1; }
    id<MTLComputePipelineState> ps = [dev newComputePipelineStateWithFunction:[lib newFunctionWithName:@"probe"] error:&error];
    if (!ps) return 1;
    id<MTLBuffer> pool = [dev newBufferWithLength:1024 options:MTLResourceStorageModeShared];
    id<MTLBuffer> out = [dev newBufferWithLength:14 * 4 options:MTLResourceStorageModeShared];
    uint32_t *words = pool.contents; words[32] = 42; words[192] = 77; words[255] = 99;
    id<MTLCommandQueue> queue = [dev newCommandQueue];
    id<MTLCommandBuffer> cb = [queue commandBuffer];
    id<MTLComputeCommandEncoder> en = [cb computeCommandEncoder];
    [en setComputePipelineState:ps]; [en setBuffer:pool offset:0 atIndex:0]; [en setBuffer:out offset:0 atIndex:1];
    [en dispatchThreads:MTLSizeMake(7, 1, 1) threadsPerThreadgroup:MTLSizeMake(7, 1, 1)];
    [en endEncoding]; [cb commit]; [cb waitUntilCompleted];
    if (cb.status == MTLCommandBufferStatusError) return 1;
    int expected[14] = {42, 77, 0, 0, 99, 0, 0, 0, 77, 0, 0, 99, 0, 0}, failures = 0;
    int *actual = out.contents;
    for (int i = 0; i < 14; i++) if (actual[i] != expected[i]) { fprintf(stderr, "[RED] Pointer case %d: %d != %d\n", i, actual[i], expected[i]); failures++; }
    printf("Pointer GPU regression: 14 checks, %d failures (whole-pool and old-origin control)\n", failures);
    return failures != 0;
} }
