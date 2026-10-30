# Touchline 27 发布前修复报告

> 本文记录上一轮修复回合的范围、检查计数和决定，不是本轮文档整理的新运行结果。
> 当前文档修改和新增来源核对见 [公开发布复核](public-release-review.md) 与
> [上游比对](upstream-provenance.md)。未解决的 R3/R5 和可达历史问题继续有效。
>
> **收尾轮更新（2026-10-30）**：R3 已按来源链关闭，R5 完成针对性表达比对，旧图与 PDB
> 不再存在于新的公开历史（单一 orphan 根提交）；结果见 [最终发布报告](final-publication-report.md)。

更新日期：2026-10-30（Asia/Shanghai）。本轮执行仓库内容、版权材料、来源记录及文档修复。此前静态审查报告原件已保存在仓库外备份中。

**当前仍不能作为已整理完成的源码仓库公开发布。** 工作区中的游戏图片和非必要 PDB 已移除；源码许可材料及可验证的 NuGet 依赖材料已补齐。R3 的三份本地程序集构建来源与 R5 的许可／独立表达问题尚未解决，因此依照用户明确条件，**没有重写初始提交，也没有暂存或提交**。旧 main 和其他 ref 仍能到达已排除图片，不能直接推送。

## 1. R1–R8 最新状态

| 编号 | 问题 | 修复状态 | 实际处理 | 是否仍阻断发布 |
|---|---|---|---|---|
| R1 | 两张解码纹理 | 工作区完成；历史未完成 | 两张图校验备份后移除，加忽略规则；研究引用改为私有证据名称 | **是**：唯一初始提交仍含原图；须待其他关键项解决再整理历史 |
| R2 | 第三方源码许可 | 已完成明确缺失材料的修复 | 补 deko3d 原文及来源；15 个 Vulkan 头逐字节对应 v1.4.363，选择其允许的 MIT，补原文 | 否；deko3d 精确历史导入 revision 未记录，未虚构 |
| R3 | 预编译 DLL 来源和许可 | 大部分完成，3 份来源未完全核实 | 56 个外部 DLL 精确包字节匹配；补 8 份原始许可／notices、metadata 和 61 文件哈希清单；translator 嵌入源码匹配，apphost 静态定位 | **是**：`Ryujinx.Common.dll`、`Ryujinx.Graphics.Shader.dll`、`Spv.Generator.dll` 缺原始构建输入／产出关联记录 |
| R4 | 其余 39 张图片 | 工作区完成；历史未完成 | 12 张渲染中间结果、27 张运行截图一并私有备份后移除；逐项清单见下 | **是，随历史整理关闭**；不再需要为这批图片取得授权才能发布不含它们的源码 |
| R5 | FPSLocker | 来源比对及致谢完成；许可边界未解决 | 定位具体文件／修订，区分偏移事实、本地 C 逻辑及未复制的汇编块；只加注释不改功能 | **是**：无明确配置再使用许可，尚缺特定许可或独立表达确认依据 |
| R6 | App/IPA 分发 | 源码与产物边界已明确 | 保留外部游戏文件构建方式，不加入 App、IPA、Shader pack、key、字体；不改变打包逻辑 | 对源码不是独立阻断；对安装包分发仍需另审 |
| R7 | 历史路径 | 文档已处理，工具默认值记待办 | 个人 Mac／NSP 目录改 `/path/to/...`；保留有意义的历史 branch／作者归属 | 否；低层工具默认路径及锁定 DLL 的 build-path 元数据见第 6 节 |
| R8 | 通用工具及调试文件 | 已执行可确定整理 | 备份后排除 PDB；其余通用工具保留并说明依据，不为“单游戏化”删除共享修复 | 否 |

根 `LICENSE` **逐字节未变**，仍为 MIT，保留 seedds 与 Touchline 27 contributors 的版权。没有改成 GPL，也没有把 Apache-2.0 依赖重新授权为 MIT。

## 2. 私有备份与内容保护

备份位于仓库外的维护者私有位置（本文用 `PRIVATE_RELEASE_BACKUP` 标识），复制后已逐文件校验。为避免公开机器目录布局，不在版本化文档中列出真实恢复路径；维护者应在私下记录中保存该位置。原备份未删除。

备份内容：

- `git-directory/`：本轮操作前完整 `.git` 副本，含原始 main、索引和其他 ref。
- `working-files.tar.gz`：开始时全部 1,041 个 tracked／非忽略未跟踪工作区文件，包含上一轮全部未提交修改和审查报告；归档后逐文件按 SHA-256 校验。
- `worktree.patch`、`index.patch`、`status.txt`、`refs.txt`、`sha256.json`：开始时差异、索引状态、引用和内容清单。
- `excluded-files/`：移除前单独复制的 41 张图片和 PDB；原图哈希均与备份一致。
- `upstream/`、来源 URL 清单及静态核验记录：公开许可证、包及元数据，未放入游戏容器或真实密钥。
- `final-working-files.tar.gz`、`final-worktree.patch`：本轮完成时工作文件及差异快照。

没有通过访问原研究项目来证明图片副本存在，而是采用用户允许的仓库外备份方案。未修改原研究项目或其他仓库。备份不是新 Git ref，也不在公开文件集合内。

## 3. 图片处理（R1、R4）

[逐文件图片清单](image-publication-inventory.md) 列出全部 41 个原路径、类型、处理和 SHA-256。核对依据为研究记录的 pass／纹理解码说明及全部图片的静态目视检查，未按文件名或扩展名单独判断。

| 类型 | 数量 | 保留在公开文件集合 | 依据和处理 |
|---|---|---|---|
| 原始纹理解码图 | 2 | 0 | 球衣 BC1 图集与场线 BC4 遮罩；明确源自游戏素材，备份后移除 |
| 渲染目标及画面中间结果 | 12 | 0 | composition、LUT 阶段预览、crowd pass、world target 等；有游戏画面表达，不作为必要源码发布 |
| 普通游戏运行截图（含诊断截图） | 27 | 0 | 菜单、比赛、修复前后画面及高亮诊断；风险不同于原纹理，但没有核实的展示许可，非必要内容，保守排除 |
| 项目自行绘制图 | 0 | 0 | 没有发现此类图片 |
| 来源不明图 | 0 | 0 | 本批可用研究记录和目视内容分类；不代表已取得任何图片授权 |

指定的 `fifa27-kit-albedo-decoded.png`、`fifa27-pitch-line-mask.png` 均已从工作区移除。图片名称留在研究记录中作为私有证据标识，去掉旧 `docs/images/...` 发布路径／下载承诺。后续重新公开任何图片仍须确认对应权限。

**当前索引与 main 仍包含 41 张原图**，工作区表现为 41 项删除。没有声称 `.gitignore` 可以清除历史。

## 4. 第三方源码许可（R2）

### deko3d

- `dm/gfx/nvn/nvn_tex.c` 原头部明确是 deko3d `source/dk_image.cpp` 算法的 C 适配，已有 fincs、2018–2020、zlib 来源信息。
- 新增 [原始完整许可](../dm/third_party/deko3d/LICENSE)，保持字节原文；补 [来源记录](../dm/third_party/deko3d/README.md)，源码仅增加指向该 notice 的注释。
- 本次上游 master 核对点为 [`373bfd43d8b2d805fa2eb7d406dbb823032df958`](https://github.com/devkitPro/deko3d/blob/373bfd43d8b2d805fa2eb7d406dbb823032df958/source/dk_image.cpp)。**该点是审查参考，不伪称为原导入 revision**。
- 原许可证所要求随源分发的 notice 已补齐；没有更改它的原始条款，也没有把适配后的文件说成未修改上游源码。

### Vulkan-Headers

- 实际 15 个头文件全部与 [v1.4.363](https://github.com/KhronosGroup/Vulkan-Headers/tree/v1.4.363) 对应文件逐字节一致；每个都声明 `Apache-2.0 OR MIT`。
- 选择其允许的 MIT 替代许可，新增上游原文 [LICENSES/MIT.txt](../dm/third_party/vulkan-headers/LICENSES/MIT.txt)。原 `LICENSE.md` 索引和所有 header SPDX／作者年份不变。
- 上游 MIT 文件的 2015–2023 年份、header 的 2015–2026 年份均原样保留，未自行统一年份。
- annotated tag 对象为 `7feeb71f59b8c1531ef5f7bb4b36e1aac46a0acb`；后续 tag-object API 受限流，未虚构其指向的 commit。

### 其他保留材料

Ryujinx、Spv.Generator、libvpx 的 LICENSE／PATENTS／AUTHORS、stb_vorbis、FLIP 附带单头文件许可、MacNativeGames 和 nvn.h 的现有声明均未删除或替换。[THIRD_PARTY_NOTICES](../THIRD_PARTY_NOTICES.md) 与 [第三方目录说明](../dm/third_party/README.md) 已同步。

## 5. 预编译工具（R3）

采用保留必要二进制并补材料的方案，没有删除整个 `dmsh_xlate_bin/`，没有引入新构建系统。

详细材料见 [依赖说明](../dm/third_party/dmsh_xlate_dependencies/README.md) 和 [完整来源／哈希清单](../dm/third_party/dmsh_xlate_dependencies/binary-provenance.json)。包从 NuGet 的固定版本下载，未执行 DLL；匹配的是包内实际文件字节，不只看 deps.json 或名称。

| 文件组 | 验证结果 | 许可处理 |
|---|---|---|
| Gommon 2.8.1.2 | 1 DLL 与 NuGet 包成员字节一致 | 包内 MIT 原文（Evan Husted）保留 |
| Humanizer.Core 3.0.10 及 locale 包 | 主 DLL 与 51 个 locale DLL 全部匹配 | 固定包 source commit 的 MIT 及 Inflector／ByteSize 归属保留 |
| Microsoft.IO.RecyclableMemoryStream 3.0.1 | 1 DLL 匹配 | 固定包 source commit 的 Microsoft MIT 原文保留 |
| MsgPack.Cli 1.0.1 | `MsgPack.dll` 匹配 | 1.0.1 tag 的 Apache-2.0 全文及包中 FUJIWARA, Yusuke 版权记录保留；未定位到该 tag 独立 NOTICE，未修改包内 DLL |
| System.CodeDom 4.4.0 | 1 DLL 匹配 | 包内 LICENSE 和完整 THIRD-PARTY-NOTICES 原样保留 |
| `dmsh_xlate.dll` | 两份嵌入源码逐字节等于当前 Program.cs／csproj，哈希也匹配 lock | 使用已有 nxnative／本项目 MIT；没有执行其 `--source-sha` |
| `Ryujinx.Common.dll`、`Ryujinx.Graphics.Shader.dll` | 身份／项目引用及哈希与 lock 一致；Shader DLL 的 3 份 GLSL 资源等于当前源文件 | 对应 MIT 文件已保留；**lock 不是完整构建来源证明** |
| `Spv.Generator.dll` | 对应 vendored project，Assembly 身份相符，有 MIT／Khronos 源码声明 | 许可已保留；**无原始 binary-to-source 构建关联记录** |
| Mach-O `dmsh_xlate` | .NET 10.0.13、内嵌 commit；只归一化 app 名缓冲、LINKEDIT 大小和签名后，与本机同版 SDK apphost 模板余下字节完全一致 | 同版本 NuGet host 包的完整 LICENSE／THIRD-PARTY-NOTICES 保留；不同 native layout，未伪称原始 NuGet 字节匹配 |
| `dmsh_xlate.pdb` | 调试符号，不在现有 loader／工具必需引用中 | 私有备份后移除；忽略防止重加 |

外部 56 个 DLL 的许可及包来源问题已实际补齐，不是仅增加文字。所有保留二进制和 runtimeconfig／deps 文件与本轮开始时的哈希相同。`dmsh_build.py`、`dmsh_chain.py`、`own_compilers.py`、`tools/nxrom/shader_compile.py` 和通用 packager 的调用路径未变，保留既有 Shader 构建所需依赖；**没有运行构建以承诺其通过**。

剩余 R3 阻断仅针对这 3 个路径：

- `dm/gfx/tools/dmsh_xlate_bin/Ryujinx.Common.dll`
- `dm/gfx/tools/dmsh_xlate_bin/Ryujinx.Graphics.Shader.dll`
- `dm/gfx/tools/dmsh_xlate_bin/Spv.Generator.dll`

已证明它们与项目预期身份／部分资源相符，但不能把它们的完整二进制视为已经核实来自当前 MIT 源码的构建。不能仅因名字相同就替其所有字节作许可来源保证，也不应为消除疑问而删掉它们破坏现有构建。

**最小解决方案**：取得生成这三个准确 SHA-256 文件的 source revision／内容清单、构建命令与产出哈希关联记录，确认本地修改来源。若原生产记录不可得，另开允许构建的维护轮，使用现有 csproj 生成可追溯替代件并按现有机制处理 lock／兼容性；本轮禁止编译，未走该方案。无需新建 Shader 系统或更换根许可证。

## 6. FPSLocker、路径与通用工具（R5、R7、R8）

- [FPS 来源核对](fpslocker-provenance.md) 定位到 v4 **分支**中的 FC 27 1.8c.fd45 YAML，核对修订 `ec9c0b4fe6043a1ff825627517ad3008e1b03e60`，提交署名 MasaGratoR。上游根目录、README、FORMAT 和固定修订 LICENSE 路径未给出明确配置再使用许可；API license 查询限流不作为许可不存在的证明。
- 指针链、地址、字段偏移和数学帧预算与参考配置有关；本地头文件采用 C 回调、校验及数据写入，没有随附 YAML、MASTER_WRITE 指令块或 SaltyNX 解释器。静态对照未见逐字移植这些代码，但尚不足以最终判断事实性信息与表达的法律边界。
- `dm/host/fpslock_fc27.h` 仅补来源注释；README 及第三方声明补致谢。**R5 最小解决方案**：取得权利人对具体配置参考／适配的明确许可，或提供独立逆向推导资料并完成针对本地表达独立性的确认。本轮未联系作者、删除功能或改 FPS 算法，不假设要改 GPL。
- 研究文档及 external-nsp 中 27 处原个人绝对路径已改占位符；旧 branch 名、上游来源及必要历史说明保留。`game.tsv` 只修正过时注释／文档名，非注释数据行逐行不变。
- `dm/games/profile_guess.py --check` 的机器专属容器目录默认仍保留，主入口不使用；改变它会改变工具行为，按用户要求记待办。
- 移除 PDB 后，`dmsh_xlate.dll` 自身仍有 build/PDB 绝对路径标记。为保持 lock 和二进制不变未 patch；这是待确认的路径元数据，不是发现密钥。后续可接受其历史元数据，或在已授权可追溯重建时采用路径映射处理。
- 保留 `smash_arc.py`、`uepak.py`、`unityfs.py`、`vk_shaders.py`、`gl_shaders.py`、`profile_guess.py` 及通用入口：支持其他格式不等于侵权。未证明完全无引用的文件不标成可安全删除。内置 profile 仍只有 FC 27，SDK patch 注册仍只针对 FC 27，未删除由其他游戏带来的共享兼容修复。

## 7. Git、静态核验与历史决定

开始及结束的主分支均为 `main`，HEAD 仍是 `786f3db37429c9333d10f3d2513280287556310c`。可达 commit 数仍为 1，无 remote。索引文件数仍为 1,040，索引本体 SHA-256 与操作前备份一致，没有暂存更改。

开始时有 2 个 Codex tree ref，均指向 `c68ea0daa3133dc78f5074fab75f3c09b0d57737`：一个 capture、一个 checkpoint。它们与 main 一起仍可到达旧图片／PDB。本轮未删 ref，不把它们当成已清理的新发布历史。

静态检查：

- 检查所有 refs 的 1,218 个可达对象、索引、工作区删除／新增文件及 ignore 规则；main 与 capture tree 各仍有 41 个图片路径，对应 39 个不同图像 blob（部分空画面字节相同）。
- 对可达文件的高置信私钥／常见 token 模式做检查；未发现明确凭据，也未发现被跟踪的 NSP、NSO、NRO、真实 keys、IPA 等文件路径。模式检查不是任意二进制无秘密的保证。
- 根 LICENSE、全部保留工具二进制、Bundle ID 和构建执行脚本不变。两处源码修改去掉注释／空白后与 HEAD 相同；profile 非注释数据行相同。
- 新复制的许可原文与上游下载／包提取文件逐字节相同；图片及 PDB 副本已经校验。
- 校对本地 Markdown 文件链接、差异空白和新增清单；未运行测试、编译、游戏、Shader 翻译或安装包流程。

用户明确要求，若关键许可／来源未解决，应保持历史不变。因此没有执行 amend、orphan、新分支、清索引、历史重写、激进 GC 或远程操作。**工作区删除图片不等于 Git 安全：目前既不能直接推送 main，也不能 `--mirror` 推送所有 refs。**

待 R3／R5 解决后，应先保存当时最新工作文件和完整原历史，再按已确认的公开集合建立单一独立初始提交，并处理仍能到达旧素材的非发布 ref；最后重新扫描所有可达对象。已有本轮授权受这些先决条件约束，未被当成现在可以重写的无条件授权。

## 8. 文档及实际改动范围

保留上一轮全部文档修订。本轮新增／更新：

- README：区分源码与嵌入游戏代码的安装包；加入 FPS 来源、私有图片清单和未完成历史状态。
- `THIRD_PARTY_NOTICES.md`、第三方 README：改为实际已补齐材料的路径，明确 MsgPack 的 Apache-2.0、Vulkan 选择 MIT、剩余来源边界。
- 新增 deko3d 来源／原许可、Vulkan MIT 原文、translator 依赖的 8 份原始许可／notices、包 metadata、61 文件来源／哈希清单。
- 新增图片逐项清单与 FPS 来源对照文档；更新研究记录图片引用与个人路径；只修 game.tsv 注释。
- `.gitignore` 防止已排除游戏图片及 PDB 被再次加入；工作区删除 41 张图和 1 个 PDB，均可从私有备份恢复。
- `nvn_tex.c` 与 `fpslock_fc27.h` 只加 notice／来源注释，不改算法、运行逻辑、补丁、内存布局或 Bundle ID。
- 更新本报告，准确区分工作区修复与历史可达对象。

没有重新打包／构建／运行自动化测试，没有改其他仓库，没有 Push。所有当前差异保留，供维护者审查。

## 9. 发布结论

**目前不能把 Touchline 27 当作已完成合规整理的源码项目公开到 GitHub。** 两个剩余实质阻断是上述三个程序集的构建来源关联记录（R3）与具体 FPS 配置适配的许可／独立表达确认（R5）；旧历史素材仍可达是尚未执行历史整理的直接后果（R1／R4），不是新发现的素材。

无需改根 MIT、删 FPS 功能、删 Shader 工具目录或重开发游戏。先针对准确文件解决两项剩余问题，再完成独立初始提交及 refs 整理，就能继续执行源码公开准备。App/IPA、游戏代码、派生 Shader、图标和字体的安装包分发仍是另一项决定，本轮没有授权其公开。

## 文档复核补充

新复核不再以程序集来自上游为由推断字节一致；固定 nxnative 修订与 15 个历史 binary 快照的比对均未匹配这三个本地 DLL。详见 [上游来源比对](upstream-provenance.md)。本轮另记录 `dm/gfx/nvn/nvn_builtin.h` 的反汇编等价 helper 来源评估事项，没有修改 Shader 或据此宣称已授权。本文原修复记录的“本轮”仍指前述修复回合；最终修改清单以 [公开发布复核](public-release-review.md) 为准。
