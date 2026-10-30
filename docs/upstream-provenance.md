# nxnative source and binary provenance

> **R3 supplemental decision, 2026-10-30:** the original research repository and its
> private remote now establish the exact local rebuild lineage. R3 can be closed as an
> unidentified-binary-origin issue, subject to maintainer review of the evidence below.
> A bit-reproducible historical build is not claimed and no rebuild is required merely
> to match current official upstream bytes. The earlier limited-upstream comparison
> is preserved below; its previous “R3 remains open” assessment is superseded by the
> [original-repository investigation](#original-repository-investigation-r3-supplement).

Comparison date: 2026-10-30. Remote reads used the public seedds/nxnative repository;
no DLL was executed, rebuilt or replaced. Git blob IDs below are computed over
`blob <byte-count>\0<content>`, matching GitHub contents/tree object identifiers.

## Upstream identity and license

Reference commit: [`ee6648cb2bb46c19255c1d04f88e9c40d36ef6b4`](https://github.com/seedds/nxnative/tree/ee6648cb2bb46c19255c1d04f88e9c40d36ef6b4).
This is an audit comparison point, **not a claimed import revision**. Its root LICENSE
retains seedds 2026 and MIT terms. This repository keeps that attribution and its own
MIT grant unchanged. Third-party notices remain independently applicable.

## Three local assemblies

| Local file | Local SHA-256 | Local Git blob | Upstream Git blob at reference | Exact match |
|---|---|---|---|---|
| `Ryujinx.Common.dll` | `2a02559c07d4935aacb63edefbd5c7433e06a0817b550ca72a94cc286a5d8376` | `e2294ba305825ccb372547232430f6c52ab6dec1` | `11c9d5f328950dbaca88307f275f0a9c62ae73a0` | No |
| `Ryujinx.Graphics.Shader.dll` | `48fafbf9b0d912bd374ae2b306239d12d8eed4f539499e4b96e8ef3dac8925b3` | `01f55680847718b822a87879b57f1ddfc616c6b3` | `b2f05eb273ad560c87506a3baf3a455efb172047` | No |
| `Spv.Generator.dll` | `b331450d46039db04426f6a6f9a2ee816fcbd4923ca32a54b7fd6360b37a575a` | `56ab6bc9dbd0316f741b9656c1082c684203215f` | `a45543000501f31a9a5d4c7f25efc7e355b98d94` | No |

All three differ from the checked upstream files. The 15 commits returned for the
upstream Shader DLL path history were also checked at the directory level; none of
those snapshots had an exact match for any of these three local assemblies. This is
a bounded history comparison, not a search of every fork, branch or private build.

| Checked upstream snapshot | Exact matches among the three local DLLs |
|---|---|
| [`ed7c473b67dd`](https://github.com/seedds/nxnative/tree/ed7c473b67dd4d542e9f7a74bc8badea2315b2a4) | None |
| [`cf3ec56351e0`](https://github.com/seedds/nxnative/tree/cf3ec56351e06481aafb924c43f7ae73251e6b4c) | None |
| [`364e86a1717a`](https://github.com/seedds/nxnative/tree/364e86a1717a4d2618965d5ad4b193983e78fa61) | None |
| [`2c31212f9d31`](https://github.com/seedds/nxnative/tree/2c31212f9d315048a2c1c444adaa06599c0acbfe) | None |
| [`f8642c480fcf`](https://github.com/seedds/nxnative/tree/f8642c480fcf4ccd769cfdaf4cafabae094c4d9e) | None |
| [`99d0aae38f32`](https://github.com/seedds/nxnative/tree/99d0aae38f329c08fca3552436a23333b34f7bf4) | None |
| [`2e655b79bfdc`](https://github.com/seedds/nxnative/tree/2e655b79bfdc86b2967ad0c0b3305e260ad6228f) | None |
| [`31b5944eb479`](https://github.com/seedds/nxnative/tree/31b5944eb47953b5cfdacf1c7d7f7ef7ee0dab22) | None |
| [`c3a0880304e9`](https://github.com/seedds/nxnative/tree/c3a0880304e9950f12e415572e3e1323d4b0cc43) | None |
| [`bb585cd5f2e9`](https://github.com/seedds/nxnative/tree/bb585cd5f2e97d957b66629083b0b366b9c1fb88) | None |
| [`87e647f5bbb5`](https://github.com/seedds/nxnative/tree/87e647f5bbb54032bb781a4ee8fac0cb18a11259) | None |
| [`56b806155f9d`](https://github.com/seedds/nxnative/tree/56b806155f9deccdd5800c89d89fd6484bbae492) | None |
| [`8d7f957fa2c6`](https://github.com/seedds/nxnative/tree/8d7f957fa2c6e6db06b2b99d8099d28f810d6484) | None |
| [`b3f25a09bb27`](https://github.com/seedds/nxnative/tree/b3f25a09bb27de1a53897d0e44f5c68bd54ea9cb) | None |
| [`e6b5333a1b15`](https://github.com/seedds/nxnative/tree/e6b5333a1b15ee21ae2279d1ff4b7792fd7349d7) | None |

## Vendored source comparison

The reference src tree is `27766463a2724abbad4020015d8946c4a36adced`. Each of the
358 locally retained source-tree files was compared by Git blob identity:

| Project | Same files | Different files | Local-only files |
|---|---|---|---|
| Ryujinx.Common | 146 | 0 | 0 |
| Ryujinx.Graphics.Shader | 180 | 14 | 0 |
| Spv.Generator | 18 | 0 | 0 |

The 14 differing Shader source paths are:

- `Ryujinx.Graphics.Shader/CodeGen/Spirv/Instructions.cs`
- `Ryujinx.Graphics.Shader/Instructions/InstEmitSurface.cs`
- `Ryujinx.Graphics.Shader/IntermediateRepresentation/TextureFlags.cs`
- `Ryujinx.Graphics.Shader/StructuredIr/ShaderProperties.cs`
- `Ryujinx.Graphics.Shader/Translation/EmitterContext.cs`
- `Ryujinx.Graphics.Shader/Translation/HostCapabilities.cs`
- `Ryujinx.Graphics.Shader/Translation/Optimizations/BindlessElimination.cs`
- `Ryujinx.Graphics.Shader/Translation/Optimizations/Optimizer.cs`
- `Ryujinx.Graphics.Shader/Translation/ResourceManager.cs`
- `Ryujinx.Graphics.Shader/Translation/ShaderDefinitions.cs`
- `Ryujinx.Graphics.Shader/Translation/Transforms/GeometryToCompute.cs`
- `Ryujinx.Graphics.Shader/Translation/TranslationFlags.cs`
- `Ryujinx.Graphics.Shader/Translation/Translator.cs`
- `Ryujinx.Graphics.Shader/Translation/TranslatorContext.cs`

A difference from this later upstream point does not establish who changed a file or
prove that it was changed locally rather than upstream. The README records Ryujinx
1.3.2 and inherited modifications, but an exact original import/build revision remains
unrecorded. Common/Spv source equality also does not prove the local DLLs were built
from those files.

## Earlier assessment before the original-repository investigation

- Corresponding source projects, references and MIT/Khronos notices exist locally.
- Two DLL fingerprints match the local committed chain lock; the Spv source project is referenced.
- Prior static resource inspection established that the local translator embeds its current
  Program.cs/csproj and that three GLSL resources match vendored source.
- The previous package audit matched 56 external DLLs exactly to NuGet members; see
  [the dependency material](../dm/third_party/dmsh_xlate_dependencies/README.md).
- The three DLLs in the table are **not verified upstream binaries**, and no exact
  binary-to-source build record had been established at that point. The original R3
  assessment is superseded by the supplemental findings below.

At the time, the proposed next step was to recover the producer's source revision/content hashes,
command/toolchain and output hashes for the exact files. If unavailable, a separately
authorized maintenance task can use the existing csproj projects to create traceable
replacements and review lock/library compatibility. No build or binary change is part
of this documentation task.

See [third-party notices](../THIRD_PARTY_NOTICES.md) and
[public release review](public-release-review.md).

## Original-repository investigation (R3 supplement)

Investigation date: 2026-10-30, Asia/Shanghai. All Git operations were read-only;
no fetch, pull, checkout, commit or ref change was used. DLLs were extracted only to
an audit directory outside both repositories. None was executed, rebuilt or replaced.
Only this document and `docs/public-release-review.md` are updated by this investigation.

### Decision and its scope

**The three DLLs are traceable builds already committed in the original development
project, not unexplained files introduced during Touchline 27 migration.** Their exact
content first appears in the original rebuild commit below, remains unchanged through
the local/remote research branch, and is already in Touchline 27's initial commit.
The corresponding source/configuration/license snapshot is retained locally and matches
the historical official source line. This resolves the missing-origin basis of R3.

This is source and supply-chain traceability, not an independently reproduced build,
a claim that every binary bit comes from an independently proven compiler execution,
or a blanket legal guarantee. The exact historical command line, SDK patch version and
some informational metadata remain unverified. Those limits do not by themselves
justify rebuilding solely to match a different current upstream binary.

### Repository/ref anchors

| Evidence location | Fixed identity | Observation |
|---|---|---|
| Touchline 27 | `786f3db37429c9333d10f3d2513280287556310c` | Three DLLs in initial commit equal current working bytes |
| Original local research checkout | `research/fifa27` at `f312a719f5b8eaa3c95a18662b1b4e868ea4a6d0` | Clean tracked worktree; three DLLs equal HEAD and rebuild commit |
| [Personal remote](https://github.com/ohxiaoguang/nxnative-zzg) | [`research/fifa27` at `f312a719f5b8eaa3c95a18662b1b4e868ea4a6d0`](https://github.com/ohxiaoguang/nxnative-zzg/tree/f312a719f5b8eaa3c95a18662b1b4e868ea4a6d0) | Authenticated GitHub read; same root tree as local |
| [Official upstream](https://github.com/seedds/nxnative) | [`6d880d237a7684365ca88236e5a5ff34921adf7d`](https://github.com/seedds/nxnative/tree/6d880d237a7684365ca88236e5a5ff34921adf7d) | Fixed main ref read for this supplement; bytes differ |
| Historical official source baseline | [`bb585cd5f2e97d957b66629083b0b366b9c1fb88`](https://github.com/seedds/nxnative/tree/bb585cd5f2e97d957b66629083b0b366b9c1fb88) | Same retained source tree/configuration as the rebuild; DLL instruction bodies compared |

The personal repository reports **private** visibility. Its links require authorized
access and are not represented as anonymously accessible public evidence. A raw URL
without authentication returned 404; the existing authorized GitHub connection successfully
retrieved and decoded each DLL as base64. Downloaded Git blob IDs were checked against
the API directory metadata. No token or credential was extracted or stored in this report.
There is no need to make the whole original repository public.

Original local and personal-remote committed root tree:
`4f2e496c7d647db877eab3fbbb177ddfb97f250e`. Equal commit/root-tree IDs establish
that those committed snapshots agree; local `git status` is also clean. The separate
ignored iOS build outputs/logs are not uncommitted versions of these DLLs.

### Four-location file comparison

Each of the twelve location/file pairs was independently extracted/read and hashed.
Git blob SHA means SHA-1 of `blob <size>`, a NUL byte, and content. Hash equality
was also confirmed by direct byte comparison for the three matching locations.

#### `Ryujinx.Common.dll`

| Location | Bytes | SHA-256 | Git blob SHA-1 | AssemblyVersion | MVID |
|---|---|---|---|---|---|
| Touchline 27 | 375808 | `2a02559c07d4935aacb63edefbd5c7433e06a0817b550ca72a94cc286a5d8376` | `e2294ba305825ccb372547232430f6c52ab6dec1` | `1.0.0.0` | `cb57ed74-10e9-4845-84fa-27cb670fd2a2` |
| Original local checkout | 375808 | `2a02559c07d4935aacb63edefbd5c7433e06a0817b550ca72a94cc286a5d8376` | `e2294ba305825ccb372547232430f6c52ab6dec1` | `1.0.0.0` | `cb57ed74-10e9-4845-84fa-27cb670fd2a2` |
| Personal remote, fixed research commit | 375808 | `2a02559c07d4935aacb63edefbd5c7433e06a0817b550ca72a94cc286a5d8376` | `e2294ba305825ccb372547232430f6c52ab6dec1` | `1.0.0.0` | `cb57ed74-10e9-4845-84fa-27cb670fd2a2` |
| Official upstream, fixed main commit | 375808 | `9d72afeb44b3096e6037a839303de1bc692baffdde2e63b1d17f62634d9d6d2b` | `11c9d5f328950dbaca88307f275f0a9c62ae73a0` | `1.0.0.0` | `9dd99006-87bc-448d-9c44-e479daeb0b7f` |

#### `Ryujinx.Graphics.Shader.dll`

| Location | Bytes | SHA-256 | Git blob SHA-1 | AssemblyVersion | MVID |
|---|---|---|---|---|---|
| Touchline 27 | 646144 | `48fafbf9b0d912bd374ae2b306239d12d8eed4f539499e4b96e8ef3dac8925b3` | `01f55680847718b822a87879b57f1ddfc616c6b3` | `1.0.0.0` | `737b68de-f9b5-4c29-97c8-e89eced62551` |
| Original local checkout | 646144 | `48fafbf9b0d912bd374ae2b306239d12d8eed4f539499e4b96e8ef3dac8925b3` | `01f55680847718b822a87879b57f1ddfc616c6b3` | `1.0.0.0` | `737b68de-f9b5-4c29-97c8-e89eced62551` |
| Personal remote, fixed research commit | 646144 | `48fafbf9b0d912bd374ae2b306239d12d8eed4f539499e4b96e8ef3dac8925b3` | `01f55680847718b822a87879b57f1ddfc616c6b3` | `1.0.0.0` | `737b68de-f9b5-4c29-97c8-e89eced62551` |
| Official upstream, fixed main commit | 652800 | `dea593d38ebb2ae62830669a7dd4da728e9c259eaf616160b32fbf541dfbd8eb` | `b2f05eb273ad560c87506a3baf3a455efb172047` | `1.0.0.0` | `73f7dc02-fc47-4a37-be34-e572d034956e` |

#### `Spv.Generator.dll`

| Location | Bytes | SHA-256 | Git blob SHA-1 | AssemblyVersion | MVID |
|---|---|---|---|---|---|
| Touchline 27 | 137216 | `b331450d46039db04426f6a6f9a2ee816fcbd4923ca32a54b7fd6360b37a575a` | `56ab6bc9dbd0316f741b9656c1082c684203215f` | `1.0.0.0` | `c6f6c8de-15c7-49b2-93b7-3cca4fdd40ad` |
| Original local checkout | 137216 | `b331450d46039db04426f6a6f9a2ee816fcbd4923ca32a54b7fd6360b37a575a` | `56ab6bc9dbd0316f741b9656c1082c684203215f` | `1.0.0.0` | `c6f6c8de-15c7-49b2-93b7-3cca4fdd40ad` |
| Personal remote, fixed research commit | 137216 | `b331450d46039db04426f6a6f9a2ee816fcbd4923ca32a54b7fd6360b37a575a` | `56ab6bc9dbd0316f741b9656c1082c684203215f` | `1.0.0.0` | `c6f6c8de-15c7-49b2-93b7-3cca4fdd40ad` |
| Official upstream, fixed main commit | 137216 | `ebe920431c22740a24e88d4a2eb801cdf5dc02f584019fa758558091f9212e12` | `a45543000501f31a9a5d4c7f25efc7e355b98d94` | `1.0.0.0` | `cac60bce-32e3-4403-8809-dd43e637da9a` |

For all twelve files: PE32 (`0x10b`), COFF Machine `0x014c`, CLI flags `0x1`
(`ILONLY`), CLR metadata string `v4.0.30319`, and the expected assembly names.
These are managed IL assemblies; `0x014c` does not mean the native game host is
an x86 build. Local assemblies declare `.NETCoreApp,Version=v10.0` and `Release`.
AssemblyVersion `1.0.0.0` is not the Ryujinx source-release label `1.3.2`.

### First introduction and replacements

All three file paths first appear in the original repository history at
[`e6b5333a1b15ee21ae2279d1ff4b7792fd7349d7`](https://github.com/ohxiaoguang/nxnative-zzg/commit/e6b5333a1b15ee21ae2279d1ff4b7792fd7349d7),
2026-10-14 03:06:56 +08:00. Their initial bytes are different from today's.
The history is not shallow. `--follow --diff-filter=A` was checked per file;
the exact current blobs are introduced by `674c2e141cf87917271858c455657aa8637f22d0`
as confirmed independently with `git log --all --find-object=<blob>`.

The complete seven replacement/introduction events found for these paths are below.
Full SHA-256 values identify the content at each event; the linked commits retain
the corresponding Git blobs. Repeated hashes indicate a file did not change at that event.

| Original commit | Time (+08:00) | Common SHA-256 | Shader SHA-256 | Spv SHA-256 |
|---|---|---|---|---|
| [`e6b5333a1b15ee21ae2279d1ff4b7792fd7349d7`](https://github.com/ohxiaoguang/nxnative-zzg/commit/e6b5333a1b15ee21ae2279d1ff4b7792fd7349d7) | 2026-10-14T03:06:56+08:00 | `74f785bc3a81386e709354dee61c1445d011389a7f66a4b5192a113d6305cbe3` | `950b659a54a52636f717fc93e6fefa1b4bd79b9d4f1a3728dec65691bed4e6a1` | `24304252752b07bc08a74cccde12201ab77882e3022618505b4973522f1ada1c` |
| [`b3f25a09bb27de1a53897d0e44f5c68bd54ea9cb`](https://github.com/ohxiaoguang/nxnative-zzg/commit/b3f25a09bb27de1a53897d0e44f5c68bd54ea9cb) | 2026-10-18T23:55:19+08:00 | `5222da62ffb43db1dc12f17293e42558c1de2945c2fe4fba70a80f294c50bd1e` | `011c50cb1c08e44fa2a5d65fafe58d1e482c70c4f5c77f51a920083a3055449c` | `4ef853035d03b93d4081acf7bd261cfe29733270dd0748615a7fb90b06651af4` |
| [`8d7f957fa2c6e6db06b2b99d8099d28f810d6484`](https://github.com/ohxiaoguang/nxnative-zzg/commit/8d7f957fa2c6e6db06b2b99d8099d28f810d6484) | 2026-10-20T07:17:31+08:00 | `5222da62ffb43db1dc12f17293e42558c1de2945c2fe4fba70a80f294c50bd1e` | `a4b556413e6a98f560153d718beb806740873fb0ba80ad09f3f016c2c380f33b` | `4ef853035d03b93d4081acf7bd261cfe29733270dd0748615a7fb90b06651af4` |
| [`56b806155f9deccdd5800c89d89fd6484bbae492`](https://github.com/ohxiaoguang/nxnative-zzg/commit/56b806155f9deccdd5800c89d89fd6484bbae492) | 2026-10-21T07:16:59+08:00 | `917c02ac432765af0e5c0d94aef1d8bab87fd6bf3040acb86471dfccfb639686` | `6f995909ae6fecb5fc180925c4df85a01094553b925ed7ea255218b58718f0e9` | `aae878447313baeed19dfe9b5676bf08c55d9d82e7185ef7d8503284ab7e8421` |
| [`87e647f5bbb54032bb781a4ee8fac0cb18a11259`](https://github.com/ohxiaoguang/nxnative-zzg/commit/87e647f5bbb54032bb781a4ee8fac0cb18a11259) | 2026-10-22T00:20:43+08:00 | `78c38eb78e9e8b4ca551f89669fa9b33d6af2e119bd54a3e371d48437577abe5` | `d0b54941cc2237d9940122eaec7fb7b2cdd6d3bdc146a0e91454073333cbb844` | `b164bf3cbfd620f7201ffd7f78031559ad275cb621a8ab269f2ae411bb1bf980` |
| [`bb585cd5f2e97d957b66629083b0b366b9c1fb88`](https://github.com/ohxiaoguang/nxnative-zzg/commit/bb585cd5f2e97d957b66629083b0b366b9c1fb88) | 2026-10-23T16:29:24+08:00 | `b99db57e72c1fa162f5f1b7f33def792098db12e0b496ba902bda06fb26b6e82` | `eb315f0da558ca5a8ad9a8b5b8374cc24cc1e73104d759098bc6824c974affa8` | `9ab32752a6941d3db9a513f229b5b69273b50154055cb732312cf8e67beb6003` |
| [`674c2e141cf87917271858c455657aa8637f22d0`](https://github.com/ohxiaoguang/nxnative-zzg/commit/674c2e141cf87917271858c455657aa8637f22d0) | 2026-10-25T03:42:11+08:00 | `2a02559c07d4935aacb63edefbd5c7433e06a0817b550ca72a94cc286a5d8376` | `48fafbf9b0d912bd374ae2b306239d12d8eed4f539499e4b96e8ef3dac8925b3` | `b331450d46039db04426f6a6f9a2ee816fcbd4923ca32a54b7fd6360b37a575a` |

Initial-introduction Git blobs (for independent historical lookup):

- `Ryujinx.Common.dll`: `3ed60709b48711d03db7cd71383090d685fa5e27`, 375808 bytes.
- `Ryujinx.Graphics.Shader.dll`: `d69218b3ba6c81c4a72c9faeb60a1d3c82751041`, 643072 bytes.
- `Spv.Generator.dll`: `c4717731c80e6ed7777c7fe4a29d7c90bda93791`, 137216 bytes.

There are no later changes to `dmsh_xlate_bin/` on the path from rebuild commit
to local/remote `f312a719f5b8eaa3c95a18662b1b4e868ea4a6d0`. Touchline 27's initial commit contains
the rebuild batch's exact three blobs. This identifies **which binary batch** was
copied, but the three unchanged files alone cannot determine which later checkout
between that rebuild and the final research head was used by the migration.

### Recorded rebuild event

Producer record: [`674c2e141cf87917271858c455657aa8637f22d0`](https://github.com/ohxiaoguang/nxnative-zzg/commit/674c2e141cf87917271858c455657aa8637f22d0),
2026-10-25 03:42:11 +08:00; parent `ffb3122026aa9aea4ffe35a1af54146cc7f19d04`.
Commit subject: *re-measure the shader translation chain (translator rebuilt from source,
current spirv-cross)*. The commit records a fresh rebuild from the in-repo translator
source because the earlier publish lacked embedded source, and remeasurement of the lock.

This commit replaces all three investigated DLLs together with the translator DLL,
apphost and PDB; it changes the chain header and lock. It changes **no** translator
C# source, Ryujinx source, project files or licenses. New chain at that point:
`e5ea6dbca04c` (not a requirement to replace Touchline 27's later chain header).
The committed lock gives these exact SHA-256 prefixes:

- `Ryujinx.Common.dll`: `2a02559c07d4935a`;
- `Ryujinx.Graphics.Shader.dll`: `48fafbf9b0d912bd`;
- companion `dmsh_xlate.dll`: `80132fec3fc716df`;
- embedded translator source: `16bbef6c762573ee` (unchanged from the parent).

Spv is not fingerprinted separately by that lock, but its full blob is stored in the
same commit and matches the branch, remote and Touchline copy. The historical
[build record](https://github.com/ohxiaoguang/nxnative-zzg/blob/f312a719f5b8eaa3c95a18662b1b4e868ea4a6d0/docs/fifa23/build.md)
also records the same prefixes and explicitly attributes the rebuild to `674c2e1`.
That record belongs to an earlier validation effort and does not add another supported
game to Touchline 27.

### Corresponding source and build graph

Original source/project introduction:
[`d1b17080ede20b89fffdfb570f80d46369433b21`](https://github.com/seedds/nxnative/commit/d1b17080ede20b89fffdfb570f80d46369433b21),
2026-10-12 22:04:20 +08:00. The retained source label is Ryujinx 1.3.2 plus
nxnative modifications; the exact source snapshot is identified by Git objects below,
rather than by that release label or an assembly version alone.

The Ryujinx `src` tree is **`eb03ac436a486e3bf4e003af125be706eea7e403`** at all of:

- official historical `bb585cd5…`;
- original rebuild parent and `674c2e14…`;
- original research branch HEAD / remote research HEAD;
- Touchline 27 initial commit and current retained source files.

364 non-README source/project/configuration/license files under the translator and
vendored Ryujinx paths match the rebuild snapshot byte-for-byte. README changes are
documentation edits, not source changes. The official historical baseline also has
the same Directory.Build.props, Directory.Packages.props, Program.cs and translator
csproj blobs as the rebuild snapshot.

Project-reference chain (from the committed csproj files):

```text
dm/gfx/tools/dmsh_xlate/dmsh_xlate.csproj
  -> Ryujinx.Graphics.Shader.csproj
       -> Ryujinx.Common.csproj
       -> Spv.Generator.csproj
  -> Ryujinx.Common.csproj
```

- Translator and vendored projects target `net10.0` (shared Directory.Build.props).
- Vendored projects use `LangVersion=preview`; Release disables their separate PDB output.
- Local assembly attributes independently report `Release` and `.NET 10.0`.
- NuGet versions are centrally recorded in Directory.Packages.props, and the committed
  `dmsh_xlate.deps.json` names the actual resolved dependencies: Gommon 2.8.1.2,
  Humanizer 3.0.10, RecyclableMemoryStream 3.0.1, MsgPack.Cli 1.0.1 and CodeDom 4.4.0.
- That deps file is byte-identical in the rebuild snapshot and Touchline 27; SHA-256
  `1c70cee37771ec372510e2246f94798aebd7087ad446eb78432271e8dc6dbac8`.
- Runtime config requests Microsoft.NETCore.App 10.0.0; that is a runtime floor, not
  the exact SDK patch used for the historical build.
- These csproj projects can be built without a `.sln`. No translator-specific NuGet.Config
  or retained build binlog was located; the separate resource-test oracle config is not
  evidence of the translator's restore invocation.

Key rebuild-snapshot source/config/license identities:

| Path at rebuild commit | Git blob SHA-1 | SHA-256 |
|---|---|---|
| `LICENSE` | `ed93689ad6ab59c679f8f92bc05ccf50f4352adc` | `a65554a74de59bf4d2210f3d4381c67d6fc6fa78f237f83c85543773319efa7b` |
| `dm/third_party/ryujinx/LICENSE.txt` | `818ddd76058d49f42eed9c0ecb580777c7f87d7e` | `781bbdf040b7d0286c47cca6bffdb9148dfe751c0c9cabdf1a1752412a2e56b4` |
| `dm/third_party/ryujinx/src/Spv.Generator/LICENSE` | `31aa79387f27e730e33d871925e152e35e428031` | `23f18e03dc49df91622fe2a76176497404e46ced8a715d9d2b67a7446571cca3` |
| `dm/third_party/ryujinx/src/Spv.Generator/spirv.cs` | `7844c97080125bd4492a25b21358e0fc85de5c8c` | `edbe69718c6fd6fa9754fead258bef34d9ea6e93d8a3c2d8db8fdd4436bd831d` |
| `dm/third_party/ryujinx/Directory.Build.props` | `b80d1a8870effc093f7ba9d614d76879b90892a6` | `8d690d6c3b861d7e352359d2ad9f2f0328051d0d1ce80ddb2928b278b7628d27` |
| `dm/third_party/ryujinx/Directory.Packages.props` | `6bf619dd3071b14e4a0b0c7e5b20f58e5d4a15ea` | `7e20a70653c83da80b2ccadeef477933aaccb7e0fd5ffe98436284c9bbf7a9f8` |
| `dm/gfx/tools/dmsh_xlate/Program.cs` | `1b167c6cdda4541ece0ac82e9a0397394e9ba1e2` | `c2165aa2c1ccd980d3771f7ff6c19a419faf2944348719eee236d4f29848d8da` |
| `dm/gfx/tools/dmsh_xlate/dmsh_xlate.csproj` | `463249e275cf972b6302133505c4668d2bdc73e6` | `5374a7e2d3f637cedcbf01081a0e64dbd0fd969857adf2dc3a2be9d185e8712d` |
| `dm/gfx/tools/dmsh_chain.lock` | `d8e9c95d134dc32b4bf504357198093bb0d6b3e5` | `0abd556ffd6d6b8b212751c12359a8ca92e1f75f3f2c7fab644fb6185bd7de13` |

### Static comparison with the matching historical official source line

The official historical binaries from `bb585cd5…` differ byte-for-byte from the local
rebuild (their SHA-256 prefixes are `b99db57e72c1fa16`, `eb315f0da558ca5a` and
`9ab32752a6941d3d`). That is expected for distinct build artifacts and is not evidence
of a missing license or source. Their source tree is exactly the same snapshot above.

As an additional static check, method rows/names and the bytes in every readable IL
instruction body were compared without executing any assembly:

| Assembly | Local method bodies | Historical official bodies | Identical instruction bodies |
|---|---|---|---|
| Ryujinx.Common | 2,044 | 2,044 | 2,044 |
| Ryujinx.Graphics.Shader | 5,489 | 5,489 | 5,489 |
| Spv.Generator | 806 | 806 | 806 |

The serialized row/name/IL-body fingerprints (SHA-256; method index, UTF-8 name,
NUL separator, byte length and instruction bytes) are equal on both sides:

- `Ryujinx.Common.dll`: `0adbd74bd6fe71417c1058d0199a79f2cae27c1077b0f6b4fda7f2e5e4c727f5`.
- `Ryujinx.Graphics.Shader.dll`: `afeccb7bc32e29ac9c65bba7ecdf51a217497feae26de98e2b3027aa77c2bfcc`.
- `Spv.Generator.dll`: `67e84963b626ebae249530b7dbd70fad8035a0c5a28796d0e8ab9ce0f5362bff`.

This supports the same source/build line. The check is deliberately limited to IL
instruction bytes, not a proof of exception tables, metadata-token semantics, all
resources or every behavior. It does not replace the commit/source evidence or claim
a whole-assembly byte match.

### Missing historical build details (not concealed)

No complete original publish/build command line, raw translator build log/binlog,
exact .NET SDK patch, working directory or all environment/override arguments were
located in the inspected original tracked/ignored file inventories and build-source
directories. The commit and project/assembly evidence establish an MSBuild/.NET 10
Release rebuild of the referenced projects; they do **not** establish a literal command
such as `dotnet publish ... -c Release -o ...`. No guessed command is presented as
the historical invocation.

All three local assemblies have InformationalVersion
`1.0.0+2b2a900998d6eef827c5cdfa83fc00ac9413847e`. This marker was not found as an
object in the inspected original repository and is **not** equated with the producer
commit or asserted as a verified Ryujinx import revision. Historical official binaries
instead carry `1.0.0+aea97ec65fa719f912a1a4dca7f43b7538a171aa`; their instruction
bodies still match as described above. MVID and informational-version differences
are retained evidence, not patched away.

Thus the exact committed source version and producer event are identified; an
independently reproducible compiler/environment recipe is not. If that becomes a
separate release requirement, record it in a future authorized maintenance task.
There is no present requirement to rebuild merely to duplicate current upstream bytes.

### License and final R3 assessment

At the producer commit, the root MIT grant retains seedds; the vendored Ryujinx MIT
license retains Ryujinx Team and Contributors; Spv.Generator has its retained grant
and Khronos notice in spirv.cs. These exact materials are still present in Touchline 27.
The rebuild changed outputs/lock only, not those grants or underlying source files.
The source adaptations already existed in the official historical source snapshot; no
new unaccounted-for third-party source addition was found in this rebuild event.

**R3 conclusion: sufficiently traced to remove the “unknown DLL origin” publication
blocker, pending maintainer acceptance of this evidence.** Keep the current DLLs and
existing applicable notices. This document supplies the previously missing producer/
source-chain attribution; no new component or changed license was found requiring
a different grant. Earlier notices that said R3 was unverified describe the assessment
before this supplement and should be read with this updated conclusion.

Only the two requested reports are changed in this task, so the earlier audit and other
notices are not silently rewritten. This does **not** close FPS configuration permission,
game-derived helper review or reachable-image-history issues; the overall publication
decision remains in [the release review](public-release-review.md).

### Direct answers

1. Already in the original project? **Yes**; local working bytes, committed blobs and the
   authenticated private remote are identical to Touchline 27 for all three files.
2. First appearance? All three paths: `e6b5333a…`; the exact current batch: `674c2e14…`.
3. Source available? **Yes**, the retained three projects and translator build graph.
4. Source/build identified? **Yes at commit/tree and producer-event level**; full historical
   command/SDK recipe is not recovered.
5. Official relationship? Inherited official source tree at `bb585cd5…`, locally rebuilt;
   not a copy of current official DLL bytes.
6. Rebuild needed? **No for resolving R3**; no rebuild was performed.
7. Additional notices? Retain the existing MIT/Khronos and dependency materials; this
   provenance supplement supplies the missing source/producer reference.
8. Sufficient for R3? **Yes for source traceability**, with the reproducibility limits
   above disclosed for human review.

## Built-in MSL helper kernels (four functions in `nvn_builtin.h`)

Investigated 2026-10-30, by Git history in the local checkouts of the official
repository and the research fork. No file was edited.

`dm/gfx/nvn/nvn_builtin.h` holds four hand-written MSL kernels (`q_val0`, `q_val8`,
`q_dlt0`, `q_dlt8`) that reproduce Maxwell counter kernels embedded in a game program.
The same file, byte-for-byte, is present in:

| Location | Identity | Note |
|---|---|---|
| [seedds/nxnative](https://github.com/seedds/nxnative) | introduced by `d1b17080ede20b89fffdfb570f80d46369433b21`, 2026-10-12 22:04:20 +08:00 | commit subject: *smbw-mobile: Mac host boots Mario Wonder v0 into its frame loop* |
| Research fork `research/fifa27` | `f312a719…`, unchanged since that introduction | inherited, not written for FC 27 |
| Touchline 27 | initial commit and current tree | identical |

`git log --follow --diff-filter=A` shows a single introduction event for the file in
the official history; no later commit changed these kernels. They were added for
Super Mario Bros. Wonder, because that game embeds its frame-counter compute kernels
in `main` instead of shipping them in a shader archive; FC 27 keeps them only because
the host's NVN path is shared.

**Classification: upstream inherited code (category 1), MIT.** The expressions are
one-load/one-store (plus one subtraction) over a 64-bit counter, with a bounds check;
the header itself records the envydis source offsets and states that the MSL is a
hand-written equivalent. Non-obvious creative expression is minimal, and the project
already carries the upstream MIT grant and attribution. No separate third-party origin
or copied third-party code was found in this file, and “disassembly equivalence” alone
is not treated as a copyright finding. No attribution change is needed beyond the
existing upstream acknowledgement; this note records the origin for future reviews.
