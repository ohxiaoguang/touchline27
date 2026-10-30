// Synthetic GPU contract: the Direct-array prefilter must preserve a legal layer-0 view.
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#import "../nvn/nvn_tex_view.h"
int main(void) { @autoreleasepool {
    if (!nvn_tex_view_possible(MTLTextureType2DArray, MTLTextureType2D)
        || !nvn_tex_view_possible(MTLTextureType2D, MTLTextureType2DArray)
        || !nvn_tex_view_possible(MTLTextureTypeTextureBuffer, MTLTextureTypeTextureBuffer)
        || nvn_tex_view_possible(MTLTextureTypeCube, MTLTextureType2D)
        || nvn_tex_view_possible(MTLTextureType3D, MTLTextureType2D)) return 1;
    id<MTLDevice> d=MTLCreateSystemDefaultDevice(); if(!d)return 2;
    MTLTextureDescriptor *td=[MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA8Unorm width:2 height:2 mipmapped:NO];
    td.textureType=MTLTextureType2DArray;td.arrayLength=2;td.storageMode=MTLStorageModeShared;td.usage=MTLTextureUsageShaderRead;
    id<MTLTexture> a=[d newTextureWithDescriptor:td]; unsigned char red[16]={255,0,0,255,255,0,0,255,255,0,0,255,255,0,0,255};
    unsigned char green[16]={0,255,0,255,0,255,0,255,0,255,0,255,0,255,0,255};
    [a replaceRegion:MTLRegionMake2D(0,0,2,2) mipmapLevel:0 slice:0 withBytes:red bytesPerRow:8 bytesPerImage:16];
    [a replaceRegion:MTLRegionMake2D(0,0,2,2) mipmapLevel:0 slice:1 withBytes:green bytesPerRow:8 bytesPerImage:16];
    if (!nvn_tex_view_possible(a.textureType, MTLTextureType2D)) return 3;
    id<MTLTexture> v=[a newTextureViewWithPixelFormat:a.pixelFormat textureType:MTLTextureType2D levels:NSMakeRange(0,1) slices:NSMakeRange(0,1)];if(!v)return 3;
    NSError *err=nil;id<MTLLibrary> l=[d newLibraryWithSource:@"#include <metal_stdlib>\nusing namespace metal; kernel void read0(texture2d<float,access::read> t [[texture(0)]],device float4* o [[buffer(0)]]) { o[0]=t.read(uint2(0)); }" options:nil error:&err];
    if(!l){puts(err.description.UTF8String);return 4;}
    id<MTLComputePipelineState> ps=[d newComputePipelineStateWithFunction:[l newFunctionWithName:@"read0"] error:&err];if(!ps)return 5;
    id<MTLBuffer> b=[d newBufferWithLength:16 options:MTLResourceStorageModeShared];id<MTLCommandBuffer> cb=[[d newCommandQueue] commandBuffer];id<MTLComputeCommandEncoder> e=[cb computeCommandEncoder];
    [e setComputePipelineState:ps];[e setTexture:v atIndex:0];[e setBuffer:b offset:0 atIndex:0];[e dispatchThreads:MTLSizeMake(1,1,1) threadsPerThreadgroup:MTLSizeMake(1,1,1)];[e endEncoding];[cb commit];[cb waitUntilCompleted];
    float *p=b.contents;int ok=cb.status==MTLCommandBufferStatusCompleted && p[0]>.99 && p[1]<.01 && p[2]<.01 && p[3]>.99;
    printf("Synthetic 2D-array to 2D view: first layer sampled correctly=%d\n",ok);return !ok;
} }
