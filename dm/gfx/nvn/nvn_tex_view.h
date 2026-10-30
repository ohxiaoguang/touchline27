// A typed resource array may contain descriptors of many kinds. Keep exact
// matches and the view conversions tex_fit supports; layer counts are checked
// against the actual Metal texture before creating a view. Rejecting by exact
// type alone loses Maxwell's layer-0 reads of a 2D array through a 2D sample.
#ifndef NVN_TEX_VIEW_H
#define NVN_TEX_VIEW_H
#import <Metal/Metal.h>
static inline int nvn_tex_view_possible(MTLTextureType have, MTLTextureType want) {
    return have == want
        || (have == MTLTextureType2DArray && (want == MTLTextureType2D || want == MTLTextureTypeCube || want == MTLTextureTypeCubeArray))
        || (have == MTLTextureType2D && want == MTLTextureType2DArray)
        || (have == MTLTextureTypeCubeArray && want == MTLTextureTypeCube);
}
#endif
