# Shader translator binary dependencies

This directory supplies provenance and original license material for the retained
`dm/gfx/tools/dmsh_xlate_bin/` binaries. The project remains MIT; individual dependencies
retain their own terms, including Apache-2.0 for MsgPack.Cli.

## External assemblies

All **56 external DLLs** were compared byte-for-byte against the exact NuGet package
members on 2026-10-30. This is stronger evidence than the assembly version alone.
[The manifest](binary-provenance.json) records each path, full SHA-256, package identity,
package SHA-256, download URL and matched member. `metadata/` contains original package
metadata for the main components. It is not an inventory of every dependency in the
full Ryujinx application; only this translator's distributed files are covered.

| Distributed files | Package / version | Terms and original material |
|---|---|---|
| `Gommon.dll` | Gommon 2.8.1.2 | [MIT](licenses/Gommon-MIT.txt), original from package; repository commit `222084874ac473e02f27faeb10e540f926702976` |
| `Humanizer.dll` and 51 locale `Humanizer.resources.dll` files | Humanizer.Core and locale packages 3.0.10 | [MIT plus Inflector/ByteSize attributions](licenses/Humanizer-MIT.txt), from package source commit `90f0cb1d7427635f38b46350bb1dc5fca2164f2d` |
| `Microsoft.IO.RecyclableMemoryStream.dll` | Microsoft.IO.RecyclableMemoryStream 3.0.1 | [MIT](licenses/RecyclableMemoryStream-MIT.txt), from package source commit `e29a28387da9018fa9605a1dcb3f7a0435aa9974` |
| `MsgPack.dll` | MsgPack.Cli 1.0.1 | [Apache-2.0](licenses/MsgPack-Apache-2.0.txt); package copyright: Copyright 2010-2016 FUJIWARA, Yusuke, all rights reserved. Source: [1.0.1 LICENSE.txt](https://github.com/msgpack/msgpack-cli/blob/1.0.1/LICENSE.txt). No separate upstream NOTICE was located at that tag; no downloaded DLL was modified. |
| `System.CodeDom.dll` | System.CodeDom 4.4.0 | [Original MIT license](licenses/System.CodeDom-LICENSE.txt) and [full package third-party notices](licenses/System.CodeDom-THIRD-PARTY-NOTICES.txt), both copied from the package |

These licenses permit redistribution subject to their conditions; retain this material
when redistributing the tool. The Humanizer metapackage itself contains no runtime DLL;
only the 51 satellite assemblies actually present in the tool directory were matched.

## Source-backed assemblies

`dmsh_xlate.dll` embeds `Program.cs` and `dmsh_xlate.csproj` as `src0` and `src1`. Static
PE/CLI resource extraction found both byte-identical to the current source. The hashes
of this DLL, `Ryujinx.Common.dll` and `Ryujinx.Graphics.Shader.dll` also match the
committed `dmsh_chain.lock` prefixes. `Spv.Generator.dll` has its source and project
reference in the vendored subset; its source includes Khronos attribution and MIT terms.

Ryujinx source and licenses remain in `dm/third_party/ryujinx/`; the translator comes
from nxnative and local changes under the root MIT license. No compilation was used
to prove instruction-for-instruction equivalence of the Ryujinx/Spv assemblies. Their
manifest distinguishes source-backed evidence from the exact NuGet byte matches.
**The exact historical build inputs for the three Ryujinx/Spv assemblies remain a provenance question;
see [the upstream source/binary comparison](../../../docs/upstream-provenance.md).** A lock hash proves identity
with the chosen binary, not equivalence to source.

## Native apphost

The Mach-O `dmsh_xlate` embeds .NET host version 10.0.13 and source commit
`4099f83977f4d29604a9aeb971fb0a7bc1d5f699` (the `dotnet/dotnet` repository,
not `dotnet/runtime`). It matches the installed 10.0.13 SDK template before the
code-signature payload after accounting for only these generated fields:

- application name buffer at `0x10228` (1024 bytes), containing `dmsh_xlate.dll`;
- `__LINKEDIT` vmsize/filesize fields at `0x520`/`0x530`;
- `LC_CODE_SIGNATURE` size and payload (payload starts at `0x1d990`).

This was a static byte comparison, not execution. The same-version NuGet apphost has
a different native build layout, so it is **not** claimed as an exact package-byte match.
The [original package MIT license](licenses/Dotnet-AppHost-LICENSE.txt) and
[complete third-party notices](licenses/Dotnet-AppHost-THIRD-PARTY-NOTICES.txt)
are preserved; the manifest records the package and SDK template hashes separately.

## Build behavior

The existing build scripts still invoke the same locked translator, DLLs and runtime
configuration. No retained binary was changed. The retained `dmsh_xlate.dll` still embeds an absolute build/PDB path marker; changing
it would change the locked binary hash, so it was not patched.
Only the non-runtime `dmsh_xlate.pdb`
was excluded after private backup; no loader/tool reference requires it. The existing
`dmsh_xlate.csproj` supports source builds, but replacing locked assemblies changes
fingerprints and is a separate developer action. This audit did not rebuild, regenerate
the lock, execute the translator, compile shaders or run tests.

## Current upstream comparison

The [2026-10-30 comparison](../../../docs/upstream-provenance.md) checks fixed nxnative
Git blobs and source-tree files, including 15 historical binary snapshots. None of the
three local Ryujinx/Spv DLLs matches those checked upstream files. This updates the
source evidence without modifying `binary-provenance.json`, the lock or any binary.
That manifest remains the prior audit's byte/package record; it is not a new upstream
equivalence claim. The original source/build revision remains unresolved.
