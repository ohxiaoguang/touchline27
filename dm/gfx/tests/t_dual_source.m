// Run with a generated library source containing main0 and main0_dual.
#import <Metal/Metal.h>
#import <Foundation/Foundation.h>
#include <math.h>
int main(int argc, const char **argv) { @autoreleasepool {
    if (argc != 2) return 2;
    id<MTLDevice> dev = MTLCreateSystemDefaultDevice();
    NSError *err = nil;
    NSString *src = [NSString stringWithContentsOfFile:@(argv[1]) encoding:NSUTF8StringEncoding error:&err];
    src = [src stringByAppendingString:@"\nvertex float4 probe_vs(uint i [[vertex_id]]) { return float4(i==1?3.0:-1.0,i==2?3.0:-1.0,0,1); }\n"];
    id<MTLLibrary> lib = [dev newLibraryWithSource:src options:nil error:&err];
    if (!lib) { NSLog(@"%@",err); return 3; }
    id<MTLCommandQueue> queue = [dev newCommandQueue];
    for (int dual = 0; dual < 2; dual++) {
        MTLRenderPipelineDescriptor *pd = [MTLRenderPipelineDescriptor new];
        pd.vertexFunction = [lib newFunctionWithName:@"probe_vs"];
        pd.fragmentFunction = [lib newFunctionWithName:dual?@"main0_dual":@"main0"];
        pd.colorAttachments[0].pixelFormat = MTLPixelFormatRGBA16Float;
        if (dual) {
            pd.colorAttachments[0].blendingEnabled = YES;
            pd.colorAttachments[0].sourceRGBBlendFactor = MTLBlendFactorSource1Color;
            pd.colorAttachments[0].destinationRGBBlendFactor = MTLBlendFactorZero;
            pd.colorAttachments[0].sourceAlphaBlendFactor = MTLBlendFactorSource1Alpha;
            pd.colorAttachments[0].destinationAlphaBlendFactor = MTLBlendFactorZero;
        } else pd.colorAttachments[1].pixelFormat = MTLPixelFormatRGBA16Float;
        id<MTLRenderPipelineState> ps = [dev newRenderPipelineStateWithDescriptor:pd error:&err];
        if (!ps) { NSLog(@"%@",err); return 4; }
        MTLTextureDescriptor *td = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA16Float width:1 height:1 mipmapped:NO];
        td.usage = MTLTextureUsageRenderTarget; td.storageMode = MTLStorageModeShared;
        id<MTLTexture> a = [dev newTextureWithDescriptor:td], b = [dev newTextureWithDescriptor:td];
        MTLRenderPassDescriptor *rp = [MTLRenderPassDescriptor renderPassDescriptor];
        rp.colorAttachments[0].texture = a; rp.colorAttachments[0].loadAction = MTLLoadActionClear; rp.colorAttachments[0].storeAction = MTLStoreActionStore;
        if (!dual) { rp.colorAttachments[1].texture = b; rp.colorAttachments[1].loadAction = MTLLoadActionClear; rp.colorAttachments[1].storeAction = MTLStoreActionStore; }
        id<MTLCommandBuffer> cb = [queue commandBuffer];
        id<MTLRenderCommandEncoder> en = [cb renderCommandEncoderWithDescriptor:rp];
        [en setRenderPipelineState:ps]; [en drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:3]; [en endEncoding];
        [cb commit]; [cb waitUntilCompleted];
        if (cb.status == MTLCommandBufferStatusError) return 5;
        _Float16 v[4]; [a getBytes:v bytesPerRow:8 fromRegion:MTLRegionMake2D(0,0,1,1) mipmapLevel:0];
        for (int c=0;c<4;c++) if (fabsf((float)v[c]-(dual?0.125f:0.25f))>0.001f) return 6;
        if (!dual) { [b getBytes:v bytesPerRow:8 fromRegion:MTLRegionMake2D(0,0,1,1) mipmapLevel:0];
            for (int c=0;c<4;c++) if (fabsf((float)v[c]-0.5f)>0.001f) return 7; }
    }
    puts("dual-source and MRT GPU values pass"); return 0;
} }
