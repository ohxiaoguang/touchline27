// Synthetic descriptor-array contracts; no game shader data.
#import "../nvn/nvn_refl.h"
#import <Foundation/Foundation.h>
#include <stdio.h>
#include <stdlib.h>
static int checks, failed;
static void check(int ok, const char *label) { checks++; if (!ok) { failed++; printf("FAIL %s\n", label); } }
int main(int argc, const char **argv) { @autoreleasepool {
    nvn_refl r; char err[256];
    for (int pool = 0; pool <= 1; pool++) {
        int tn = pool ? 16384 : 32, sn = pool ? 4096 : 32;
        NSDictionary *j = @{@"route": @"B", @"bindless_pool": @(pool), @"bindings": @[
            @{@"kind": @"tex", @"msl_name": @"fp_t2d_cb0_40000000", @"msl_type": [NSString stringWithFormat:@"array<texture2d<float>, %d>",tn], @"arg_id": @0},
            @{@"kind": @"?", @"msl_name": @"fp_s_cb0_40000000", @"msl_type": [NSString stringWithFormat:@"array<sampler, %d>",sn], @"arg_id": @(tn)}]};
        check(!nvn_refl_from_json(j,&r,err,sizeof err), "array conversion");
        check(r.dyn == (pool ? 2 : 1), "pool and legacy semantics differ");
        check(r.b[0].n == tn && r.b[1].n == sn, "large lengths do not truncate");
        check(r.b[0].kind == NVN_RB_TEXD && r.b[1].kind == NVN_RB_SAMPD, "resource kinds");
        free(r.c1);
    }
    NSDictionary *bad = @{@"route": @"B", @"bindless_pool": @YES, @"bindings": @[
        @{@"kind": @"tex", @"msl_name": @"fp_t2d_cb0_40000000", @"msl_type": @"array<texture2d<float>, 16385>", @"arg_id": @0}]};
    check(nvn_refl_from_json(bad,&r,err,sizeof err) != 0, "over-capacity array rejected");
    if (argc > 1) {
        NSString *dir = @(argv[1]); int samples = 0;
        for (NSString *name in [[NSFileManager defaultManager] contentsOfDirectoryAtPath:dir error:nil]) {
            if (![name hasSuffix:@"_b.json"]) continue;
            NSData *data = [NSData dataWithContentsOfFile:[dir stringByAppendingPathComponent:name]];
            NSDictionary *j = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
            int rc = nvn_refl_from_json(j,&r,err,sizeof err);
            check(!rc, "generated reflection converts");
            if (rc) printf("[RED] %s: %s\n", name.UTF8String,err);
            free(r.c1); samples++;
        }
        check(samples > 0, "generated samples found");
        printf("Converted %d generated reflection files\n",samples);
    }
    printf("Reflection arrays: %d checks, %d failed\n",checks,failed);
    return failed != 0;
} }
