# Touchline 27 首次公开发布文档复核

复核日期：2026-10-30（Asia/Shanghai）。文档整理阶段记录保留；本次补充原始开发仓库的 R3 来源调查。**R3 已建立来源链，可解除“来源不明 DLL”的阻断，待维护者审核接受。当前仍不建议直接公开 GitHub 仓库**：R5、旧素材可达历史及 helper 来源评估没有因此解决。

> **收尾轮更新（同日，用户明确授权）**：R3 已按证据链关闭，三个 DLL 保留；R5 完成针对性表达比对，仅地址、数值与调节方案被参考，未发现复制的独特表达；四个 MSL helper 确认为上游 `seedds/nxnative` 继承代码（`d1b1708`）；`profile_guess.py` 的机器默认路径已改为 `$DM_NSP_ROOT`/当前目录；41 张旧图与 PDB 不再存在于新公开历史（单一 orphan 根提交，旧历史只保留在仓库外私有备份）；关于页面已实现，两份 IPA 已本地构建并验证。下文“仍不建议公开”“R5 未解决”“历史未整理”等句子描述的是收尾轮之前的时点。最终结果见 [final-publication-report.md](final-publication-report.md)。

## 1. 文档整理阶段修改清单（原记录）

本轮共修改/新增 33 份 Markdown：新增 10 份，修订已有 23 份。以下清单相对于本轮开始时的工作区，**不是相对于 HEAD**；此前代码注释、profile 注释、ignore 规则、图片/PDB 删除等改动原样保留。

| 文件 | 目的 |
|---|---|
| [CHANGELOG.md](../CHANGELOG.md) | 新增 Unreleased 记录，不编造版本号、发布日期或测试结果。 |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | 新增问题报告、证据分级、私有输入及归属要求。 |
| [README.md](../README.md) | 重写独立项目入口：功能边界、三平台状态、构建/导入流程、致谢与阻断项。 |
| [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) | 统一来源与实际许可证；纠正 stb_vorbis 修改状态；保留 R3/R5 与新增 helper 来源事项。 |
| [dm/games/README.md](../dm/games/README.md) | 明确唯一 FC 27 profile、代码适配边界及生成命令的输出目录。 |
| [dm/gfx/README.md](../dm/gfx/README.md) | 修正其他游戏映射、494 条目、源码路径、默认输出和帧率变量，移除过时限制清单。 |
| [dm/gfx/metal/README.md](../dm/gfx/metal/README.md) | 更正指针型创建函数返回说明，区分开发命令与本轮未执行状态。 |
| [dm/gfx/nvn_metal_mapping.md](../dm/gfx/nvn_metal_mapping.md) | 明确实现参考范围，不再把对象映射等同完整游戏/设备正确性。 |
| [dm/gfx/tex/README.md](../dm/gfx/tex/README.md) | 消除 BC 解压前后矛盾，区分格式支持、deswizzle 和部分 shadow 路径。 |
| [dm/third_party/README.md](../dm/third_party/README.md) | 纠正修改记录、MIT 选项与非 FC 渲染器的产品范围描述。 |
| [dm/third_party/dmsh_xlate_dependencies/README.md](../dm/third_party/dmsh_xlate_dependencies/README.md) | 补本轮固定上游/历史快照比对，保留旧哈希清单的时点和证据边界。 |
| [dm/third_party/libvpx/README.md](../dm/third_party/libvpx/README.md) | 保留导入记录，移除其他游戏产品例子，标记配置代码块。 |
| [dm/third_party/ryujinx/README.md](../dm/third_party/ryujinx/README.md) | 将既有改动记录标为非完整 diff，补源文件/程序集的实际比对边界。 |
| [dm/third_party/stb_vorbis/README.md](../dm/third_party/stb_vorbis/README.md) | 补标题、来源链接和已有多声道修改事实，移除其他游戏专属用途说明。 |
| [dm/third_party/vulkan-headers/README.md](../dm/third_party/vulkan-headers/README.md) | 明确 FC 27 不用该渲染路径，保留原双 SPDX 与本分发选择 MIT。 |
| [docs/README.md](README.md) | 新增面向用户、开发者和发布审核的统一导航。 |
| [docs/architecture.md](architecture.md) | 明确独立 wrapper 的 NSP 路径、模块归属及虚拟内存/设备限制。 |
| [docs/building.md](building.md) | 围绕两个独立脚本整理环境、私有输入、双平台构建、复用和签名前提。 |
| [docs/development.md](development.md) | 新增开发环境、生成物、Shader chain 和测试证据分级说明。 |
| [docs/external-nsp.md](external-nsp.md) | 保留 reader 技术资料，标为实现档案，去除其他游戏产品介绍并指向当前流程。 |
| [docs/faq.md](faq.md) | 新增文件识别、版本、keys、签名、内存、图形、帧率、DLC 和存档排障。 |
| [docs/fpslocker-provenance.md](fpslocker-provenance.md) | 强化本地 C 与参考数据的区分，给出不联系作者的后续技术路径。 |
| [docs/release-audit.md](release-audit.md) | 标明上一轮修复快照，隐去真实备份目录，补本轮来源比对入口。 |
| [docs/research/README.md](research/README.md) | 新增时间线及 superseded 结论索引，不删技术研究。 |
| [docs/research/fc27-bringup.md](research/fc27-bringup.md) | 修正误导性标题/无游戏数据表述、个人远程和临时路径，保留测量及其限制。 |
| [docs/research/fc27-feasibility.md](research/fc27-feasibility.md) | 标明早期阶段，去除旧 GUI/其他游戏专属使用路径，保留技术来源比较。 |
| [docs/research/fc27-input-integrity-audit.md](research/fc27-input-integrity-audit.md) | 将“无 profile”明确限定到历史阶段，补归档范围和当前状态入口。 |
| [docs/research/fc27-two-areas-and-bringup.md](research/fc27-two-areas-and-bringup.md) | 标明旧内存/Shader 阶段，修正文档源码路径及代码块语言。 |
| [docs/resource-discovery.md](resource-discovery.md) | 区分运行时/构建扫描、验证读取与文件元数据，以及历史测试和当前支持。 |
| [docs/support-status.md](support-status.md) | 新增逐平台 build/start/gameplay/performance 证据矩阵与版本/GPU/内存限制。 |
| [docs/upstream-provenance.md](upstream-provenance.md) | 新增固定 nxnative revision、三 DLL blob、15 历史快照及 358 源文件对照。 |
| [docs/user-guide.md](user-guide.md) | 新增启动、资源导入、签名、完整按键、设置、真实存档/日志位置。 |
| [docs/public-release-review.md](public-release-review.md) | 本报告：本轮清单、验收、风险、人工决策与公开前操作。 |

`docs/image-publication-inventory.md`、deko3d 的现有来源说明和原始许可材料已检查，内容未改。没有重新加入任何图片或私有资源。研究资料保留在原路径，未迁移或删除；新增索引区分现状与历史。

## 2. 当前公开发布状态

| 事项 | 本轮后的状态 | 公开前要求 |
|---|---|---|
| 独立命名/用户说明 | 统一 Touchline 27，只支持 FC 27 | 无文档层面的阻断；不得把通用后端当作额外游戏支持 |
| 平台证据 | Mac 历史运行与测量、旧版 iPhone 用户报告、iPad 目标配置分别列明 | 不得宣称当前 IPA 已真机验证或 iPad 已实测 |
| MIT/上游归属 | 根 LICENSE 与所有原始许可条款逐字节不变；保留 seedds 与维护者归属 | 第三方许可证分别适用，不将 MsgPack 的 Apache-2.0 改称 MIT |
| R2 许可材料 | 前轮补齐的 deko3d 原 notice、Vulkan MIT 选项原文继续保留 | deko3d 精确历史导入点未知，不编造 |
| R3 三 DLL | 已匹配原始仓库重建提交 `674c2e14…`、本地/个人远程 `f312a719…` 与 Touchline 初始提交；对应源码树及许可保留；收尾轮按此关闭 R3 | 保留现有 DLL；无需为匹配官方字节重建 |
| R5 FPS 数据参考 | 实现与参考关系准确说明；未确认配置再使用许可；收尾轮针对性比对未见复制表达 | 保留参考披露与致谢；不宣称参数原创，不把 Warehouse 称为 GPL |
| R1/R4 图片与历史 | 已从工作区移除；新的公开历史为单一 orphan 根提交，不含 41 图与 PDB；原历史仅存于仓库外私有备份 | 不再推送旧 refs；私有备份不入库 |
| 新增来源核对事项 | 四个反汇编等价 MSL kernel 为上游 `d1b1708` 继承代码，非 FC 27 专属 | 无需改写；归属已记录 |
| App/IPA | 收尾轮本地构建两份未签名 IPA（内置资源、NSP 外置），未上传 | 安装包分发仍是单独决定；仓库只发布源代码 |

## 3. 已解决的文档问题

- README 不再采用多游戏工程/GUI 打包介绍；两个独立脚本、默认输出和预处理输入是唯一公开用户流程。未编造尚未分配的 GitHub clone 地址。
- 当前 Shader map 静态计数为 **494**，修正旧 496；同时说明 captured coverage 不是完整游戏覆盖。首次构建需要 NRO、shader pack 和解码器的限制不再藏在研发日志里。
- 纠正 stb_vorbis“未修改”说明：源码和原 README 均表明保留了 type-2 residue 多声道修复。
- 图形文档不再声称当前表覆盖 Mario 版本，也不再指示把编译移到手机；修正 wrapper 的平台输出位置、NVN 文件路径和 `DM_FPS_TARGET` 用途。
- 纹理说明不再同时声称“有 BC 软件解压”与“没有 BC 解压”；区分 BC Metal 格式、deswizzle 及部分 raw-block shadow 操作。
- 由实际 profile 行和 `hle_svc.c` 分区公式核算 heap 为 1,232 MiB（1.203125 GiB），更正文档原先的 1.25 GiB；源码中的旧估计注释本轮未改。
- 区分虚拟地址预留、实际占用及设备进程限制，撤回“5.03 GiB 就证明任意 iOS App 能运行”的推论。
- Mac/手机/平板的编译、启动、进入比赛、实际游戏和测量分开。没有新性能数据、支持机型名单、正式 60 FPS 或 DLC 成功承诺。
- 研究记录的早期黑屏、12 GiB 估计、无 profile 和待解码阶段均标为历史；保留原实验而不作为当前支持说明。早期 Shader 捕获轮次表的累计数无法完整反推，保留原值并明确限制。
- 真实个人目录、旧个人远程地址、临时测试绝对路径已从 Markdown 叙述移除/改为占位符；必要作者名、公开源码 URL、版权署名不按“个人信息”误删。

## 4. 公开声明的依据

| 声明 | 实际依据 | 本轮可以/不能推断 |
|---|---|---|
| 独立入口/产物/Bundle ID | `scripts/build-mac.sh`、`build-ios.sh`、`touchline_build.py` | 选项/路径真实存在；未运行构建 |
| macOS 26、iOS/iPadOS 26 目标 | `scripts/build_mac_app.py`、`dm/ios/project.yml`（device family 1,2） | 配置目标存在；不是最低设备名单/真机结果 |
| 输入、语言、设置 | shared ResourceDiscovery、`settings.tsv`/`settings.py`、平台 Launcher | 已实现的路径/条件，不保证每个语言包、控制器、DLC 成功 |
| 鼠标/触摸/键盘/控制器 | `front_mac.m`、iOS Launcher/DmGamepad 和 touch bridge | 存在对应输入路径；不承诺鼠标完整操控或全部本地多人模式 |
| 音频/本地保存 | `hle_audio.c`、movie codecs、平台启动/存储代码 | 路径实现存在；历史听音与保存相关观察不等于设备长期可靠性 |
| 30/60 FPS | `fpslock_fc27.h`、`hle_fpslock.c`、合成测试源码及研究第 21 节 | 本地 C/完整 BID/内存保护/写参逻辑存在；测试源码未运行，M1 结果不外推到手机 |
| 5.03125 GiB | `game.tsv` 的 `0x142000000` 和研究第 20 节 | 配置与历史推导一致；不等于物理 RAM 门槛/签名成功 |
| 许可与二进制身份 | 根/组件 LICENSE、既有 package 清单、固定 GitHub source/blob 比对 | 保留原文和证据边界；不能替来源未知的 DLL 作完整授权保证 |

独立包装器会跳过不属于 base/update 的容器；共享运行时有 DLC 验证/AOC 读取实现。这不构成 FC 27 commentary/DLC 已实测的证据。用户文档据此采用“实现存在、游戏兼容未验证”。

## 5. R3 原始开发仓库补充调查（最新结论）

**原先的“源码/产物关系未确认”结论已被补充证据更新。** 先前官方当前版及 15 个快照不匹配的观察本身仍正确，但不能据此推断用户自己的本地重建件没有来源。完整逐文件、元数据、历史版本和许可证据见 [来源报告的补充章节](upstream-provenance.md#original-repository-investigation-r3-supplement)。

### 来源链已确认

1. 三个 DLL 路径首次进入原始项目历史：`e6b5333a1b15ee21ae2279d1ff4b7792fd7349d7`（2026-10-14 03:06:56 +08:00）。当时文件内容不同于现在。
2. 当前三个精确 blob 均首次由 `674c2e141cf87917271858c455657aa8637f22d0` 引入（2026-10-25 03:42:11 +08:00）。该提交明确记录从仓库源码重建译码器，同时替换三 DLL/伴随产物、重测 lock；没有改 C# 源码或许可证。
3. 从该提交到原始开发分支 `f312a719f5b8eaa3c95a18662b1b4e868ea4a6d0`，工具目录未再改变。本地 tracked worktree 干净。
4. 个人远程 `research/fifa27` 由授权 GitHub 只读查询确认也指向 `f312a719…`，根 tree 为 `4f2e496c7d647db877eab3fbbb177ddfb97f250e`，与本地相同；三文件通过授权连接分别提取并计算 SHA-256/Git blob/PE 元数据，均与 Touchline 一致。
5. Touchline 27 初始提交已含同一批次字节，非本地未提交/来源未知的临时 DLL。仅凭一直未变的三个文件，不能唯一推断迁移时使用的是重建之后的哪个具体 checkout；可以确认产物批次来自 `674c2e14…`。

### 源码与官方关系

- 官方历史 `bb585cd5f2e97d957b66629083b0b366b9c1fb88`、原始重建提交、研究分支和 Touchline 初始提交的 Ryujinx src tree 都是 `eb03ac436a486e3bf4e003af125be706eea7e403`。
- 364 个非 README 的源码、项目/共享配置、许可文件与该重建快照逐字节一致。实际 ProjectReference 链连接 translator、Shader、Common 与 Spv；AssemblyVersion 为 1.0.0.0，TargetFramework 为 .NET 10，Configuration 为 Release。
- 额外静态比对当前三文件与相同源码线的官方历史产物：2,044 / 5,489 / 806 个可读取方法的 IL 指令体分别全部相同，共 8,339 个。这不是所有元数据/异常表/资源/行为的完整等价证明。
- 本轮固定官方 main 核对点为 `6d880d237a7684365ca88236e5a5ff34921adf7d`。它的三个 DLL 确实不同；历史基线 DLL 也不同。不同 MVID/信息版本与整文件 hash 不会否定已查明的本地重建来源。
- 原始 seedds MIT、Ryujinx MIT、Spv/Khronos 声明仍在；该重建没有新改授权文本，也没有发现新增未说明来源的第三方源码。既有 56 个 NuGet 依赖的包字节记录和许可材料继续适用，未改 manifest、lock 或二进制。

### 保留的限制与分发含义

原始个人仓库为 **private**。文中链接须有访问权限；不能当作匿名读者可直接访问的公共链接。本次使用现有授权连接读取，没有暴露凭据，也不需要公开原仓库全部内容。

已找到提交/源码对象、重建提交说明、lock、项目引用及历史构建文档，未找到完整原始命令行、translator raw log/binlog 和确切 SDK 补丁版本。不能把推测的 `dotnet publish` 命令写成当年真实执行命令。三 DLL 的 InformationalVersion 中 `2b2a900998d6eef827c5cdfa83fc00ac9413847e` 未在所查原始 Git 对象库中找到，不冒充已确认的源码 revision；精确源码以已核对的 tree/blob 和重建提交记录为准。

这些是不具备逐位可复现构建配方的限制，不再等于“DLL 来源未知”。**建议解除 R3 原来源阻断，保留当前 DLL，由维护者审阅接受本证据链；无需仅为追求官方字节一致而重新构建。** 本来源报告补充了所缺的 producer/source 说明；本轮只更新指定的两份报告，其他旧 notices 中 R3 尚未核实的句子属于补充前时点，不作为否定新证据的结论。需要统一旧文案时可在后续文档审核中同步，不影响已建立的事实来源链。

## 6. FPSLocker 的准确表述及无需联系作者的路径

本项目的 Host 侧 C 执行逻辑独立编写；相关地址、参数和调节研究参考 FPSLocker-Warehouse 的公开 FC 27 配置。既没有直接包含 FPSLocker 运行时，也没有分发原 YAML 或 ARM64 汇编补丁，但不能据此声称所有数据独立原创或已获授权。

`v4` 是参考分支。没有把 Warehouse 的许可证写成 GPLv2。源码、测试源码和研究记录用于区分行为和证据，不作为自动解决授权问题的替代品。**本轮未联系任何作者。**

不联系作者的后续方案见 [来源核对](fpslocker-provenance.md#不联系作者情况下的后续技术路径)：以自有游戏输入建立真实独立定位/验证资料并针对表达作分发判断；若仍无法确认，另行授权从拟分发源码排除有争议地址适配/相关表达，保留原生帧率或采用可追溯的独立替代。后来的验证不能伪造“从未参考”的历史；仅默认关闭 60 FPS 但继续分发同一源码，也不等于来源问题解决。本轮不修改功能。

`nvn_builtin.h` 的额外事项同样需要核对原始出处/版本、各简单 kernel 的算法事实与表达。该问题来自明确源码注释，不是根据扩展名猜测；当前未认定侵权，也未宣称根 MIT 足以替原游戏授权。后续可补原始依据或在另行授权范围中审阅独立功能等价实现，本轮 Shader 保持不变。

## 7. 格式、链接、隐私与范围验收

- 检查最终 36 份 Markdown 的标题递进、围栏平衡、表格和引用结构；本地文件链接及文档锚点已核对。项目文档无未标语言围栏；原封保留的 Vulkan `LICENSE.md` 原文有一个不带语言的示例围栏，这是有效 Markdown，未为消除样式提示改动授权原文。
- 外链核对以实际来源读取和拼写为范围；没有声称所有历史远程证据/网页都做过 HTTP 可用性测试。
- 扫描未发现 Markdown 中残留真实机器 `/Users`、`/Volumes`、系统临时目录形式的路径或旧个人远程账号；`/path/to/...`、私有 scratch 标识和 API 文档路径属于占位符/技术内容。必要贡献者/第三方版权信息保留。
- **仍有一处二进制路径元数据**：`profile_guess.py` 的机器默认目录已改为 `$DM_NSP_ROOT`/当前目录（收尾轮）；锁定 `dmsh_xlate.dll` 内仍有原构建的 PDB 绝对路径字符串。按要求未改写 DLL，该历史元数据不影响运行时，也不含密钥；新历史中不会出现该路径对应的构建输出。没有发现新的秘密值证据。
- 相对本轮开始时的指纹，**994 个非 Markdown 文件均未改变且未删除**，包括生产代码、Shader、构建脚本、DLL、metadata/manifest、`.gitignore` 及原始许可证。此前工作区已有的代码注释变更和删除不会被冒充成本轮新修改。
- 根 LICENSE、索引、HEAD 和 refs 与本轮开始时相同；分支 `main`，HEAD `786f3db37429c9333d10f3d2513280287556310c`，可达 commit 1 个，无 remote。原 41 图/PDB 的删除仍未暂存/提交，历史状态未改变。
- 未编译、运行游戏/测试、重新打包、编译 Shader/NSO、签名、删除二进制、改 FPS/内存/Bundle ID、创建提交或推送。

## 8. 需要维护者决策及公开前最后步骤

1. ~~审核 R3 证据并关闭“来源不明”记录~~（收尾轮已按证据链关闭，DLL 保留）。
2. ~~完成 R5 的针对性表达判断~~（收尾轮已比对：仅地址、数值与调节方案参考，未见复制的独特表达；明示许可仍未取得，已如实披露）。
3. ~~核对四个 inherited MSL helper 及工具/二进制路径元数据~~（helper 确认为上游 `d1b1708` 继承；`profile_guess.py` 已改为环境变量/当前目录；DLL 内 PDB 路径作为历史元数据记录，不改写二进制）。
4. 审阅文档差异和 [图片清单](image-publication-inventory.md)，确认公开集合不含游戏内容/秘密；私有备份保持在仓库外。
5. ~~历史整理~~（收尾轮以单一 orphan 根提交建立新公开历史，不包含旧图、PDB 或旧 refs；原历史仅在私有备份）。
6. 仓库 URL 已定为 <https://github.com/ohxiaoguang/touchline27>；版本号、发布范围和平台声明仍按证据表述，没有虚构“首发已完成”。

拟议 GitHub Description（仅建议，未设置）：

> An unofficial FC 27 runtime and porting project for Apple silicon macOS, iOS and iPadOS. Requires privately supplied game files.

拟议 Topics（未设置）：`touchline27`、`fc27`、`macos`、`ios`、`ipados`、`apple-silicon`、`metal`、`arm64`、`game-porting`。它们不表示官方隶属、已测试全机型或当前已可公开。

## 9. 结论

用户/开发者文档已按独立 FC 27 项目整理，原始 MIT 与归属保留，所有本轮变更限于 Markdown。**不建议现在公开或推送现有仓库**：R3 的原始来源已追溯、可关闭该项；R5 和旧素材可达历史仍未解决，另有明确记录的 helper 来源核对事项。文档整理不能替代这些决定。本轮到此停止，保持未提交状态供维护者审核。

## 10. 本次 R3 调查的改动与保护范围

本次仅更新 `docs/upstream-provenance.md` 与本文件，不重新执行上一轮文档整理。原始开发仓库的工作文件、tracked 状态、HEAD、索引和 refs 保持不变；目标仓库除两份指定文档外保持开始时内容，既有未提交修改没有暂存、覆盖或回退。

调查使用只读 Git 对象/历史、授权 GitHub API、仓库外提取副本和静态 PE/.NET 解析；没有 fetch/pull、切分支、DLL 执行/替换/重建、改生产代码/许可证/历史、提交或推送。元数据/哈希/源码与提交摘录已保存在仓库外证据目录；可由维护者在人工审核时结合完整提交对象复核。
