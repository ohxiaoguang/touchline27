# Ryujinx shader translator (vendored subset)

Three projects from Ryujinx 1.3.2: `Ryujinx.Graphics.Shader`, `Ryujinx.Common` and `Spv.Generator`, with inherited changes. The following records describe several of them; they are not
a complete diff against a verified original import revision:

- `Ryujinx.Graphics.Shader/CodeGen/Spirv/Instructions.cs`, `GenerateTextureSample`:
  - Texel offsets that are not constants (Maxwell AOFFI / TLD4.PTP offsets read from a register) are built with `OpCompositeConstruct` and passed as `Offset`. A four-offset gather becomes four one-offset gathers, each giving component w. Upstream wrote them as an `OpConstantComposite` with `ConstOffset(s)`, which is invalid SPIR-V; SPIRV-Cross threw `nullptr` and the shader never built (2026-10-18: eight historical shader cases). Marked `nxnative:` in the code.
  - Texture coordinates that are NaN are replaced by 0 (the `nfZero` select). This came with the first import.
- `Ryujinx.Graphics.Shader/Translation/Optimizations/BindlessElimination.cs`, `TryGetOperation` / `IsSameOperand`: a bindless handle that reaches the texture instruction through a phi is followed through the phis that feed it (a handle kept in a loop variable comes back through the loop's own phi), and two `constant buffer | constant` handles count as the same value. Upstream compared only the phi's direct inputs, so such handles fell to the texture-pool array of 32 (`*_t2d_cb0_40000000`), which cannot be bound; 218 pixel shaders in an upstream validation case (2026-10-20). Marked `nxnative:` in the code.

- `Ryujinx.Graphics.Shader/Instructions/InstEmitTexture.cs`, `EmitTex` (TLD 1D with integer coordinates only) and `EmitTexs` (TLDS `Texture1DLodZero`), with `IGpuAccessor.RecordTexelFetch1D`: Maxwell reads a 1D texture and a texture buffer with the same instruction, and the bound descriptor decides. When the texture type query does not answer "buffer", the read is translated as 2D at `(x & 0x3FFF, x >> 14)` instead of `(x, 0)`, and the handle is reported. A 1D texture (one row at most 16384 wide on the host) reads the same; the host binds a texture buffer in such a slot as a linear 2D texture of 16384-texel rows over its memory (`nvn_mtl.m` `tbuf_as_2d`). Upstream read `(x, 0)` and the host had only a dummy texture to give: historical light/decal-list shaders read zeros (2026-10-21). Marked `nxnative:` in the code.

The shader translation tool in `dm/gfx/tools/dmsh_xlate` references them to translate the original Switch shaders to SPIR-V.
License: MIT, see `LICENSE.txt`. Upstream: <https://github.com/Ryubing>.

## Source and binary evidence

The recorded 1.3.2 label does not identify an exact import/build commit. The current
[source comparison](../../../docs/upstream-provenance.md) finds 344 matching and 14
differing source-tree files against the specified nxnative revision, while the three
local Ryujinx/Spv DLLs differ from all checked upstream binary snapshots. Do not infer
binary identity or full build provenance from source presence or assembly names.

The license files and all existing source headers are retained. `Spv.Generator/spirv.cs`
also has the original Khronos copyright and permission notice. These inherited changes
do not add product support for the original upstream validation titles.
