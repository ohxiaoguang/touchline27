# Touchline 27 最终发布报告

日期：2026-10-30（Asia/Shanghai）。本报告记录收尾轮实际完成的代码、文档、构建、Git 历史与推送结果。
前几轮的审计与文档整理记录保留在 [release-audit.md](release-audit.md)、[public-release-review.md](public-release-review.md)
和 [upstream-provenance.md](upstream-provenance.md)；本报告只写本轮结论与可复核的事实。

## 1. 剩余发布问题的处理结果

### 1.1 R3：三个预编译 DLL

R3 按已有证据链关闭：`Ryujinx.Common.dll`、`Ryujinx.Graphics.Shader.dll` 与
`Spv.Generator.dll` 的当前字节由原始开发仓库的重建提交
`674c2e141cf87917271858c455657aa8637f22d0` 引入，并在个人远程 `research/fifa27`
（`f312a719…`）与 Touchline 27 初始提交中逐字节一致；对应源码树
`eb03ac436a486e3bf4e003af125be706eea7e403`、构建关系与 MIT/Khronos 许可材料均保留。
三个 DLL 未删除、未替换、未重建，也没有为匹配官方当前版本而修改。逐位可复现的
构建命令/SDK 补丁仍未记录，这一点如实保留，但不再等于“来源不明”。

旧文档中“R3 未解决”的表述已更新：[upstream-provenance.md](upstream-provenance.md)、
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)、[public-release-review.md](public-release-review.md)、
[release-audit.md](release-audit.md)。

### 1.2 FPSLocker / Warehouse 参考关系

本轮对 `dm/host/fpslock_fc27.h` 与 `dm/host/hle_fpslock.c` 的 FC 27 分支做了针对性对照
（上游为 FPSLocker-Warehouse `v4` 分支、文件 `9636BCD68E2EF2C8.yaml`、修订
`ec9c0b4fe6043a1ff825627517ad3008e1b03e60`）：

- 共同点只有游戏身份、指针链（`MAIN+0xDA1EE38+8`、`MAIN+0xDE81DA0→+0x14C8→+0xC/+0x10`）、
  RenderSettings 字段偏移 `+0xF8/+0x144`、以及 `1000/fps` 的帧预算关系；
- 本地是 C 回调、指针对齐/范围检查、`vm_region` 写保护与位掩码返回，和上游 YAML
  的变量、`type:` 结构、指令数组、`MASTER_WRITE` 汇编块没有对应物；
- 未发现复制的独特代码表达。

结论：保留实现，不重写 FPS 功能；来源说明与致谢保留；不宣称参数原创，也没有把
Warehouse 描述为 GPL。上游未提供明确再使用许可，这一点仍在文档中如实说明。
详见 [fpslocker-provenance.md](fpslocker-provenance.md)。

### 1.3 四个 MSL helper

`dm/gfx/nvn/nvn_builtin.h` 的 `q_val0/q_val8/q_dlt0/q_dlt8` 已核对为**上游继承代码**：
与 `seedds/nxnative` 提交 `d1b17080ede20b89fffdfb570f80d46369433b21`（2026-10-12）
引入的文件逐字节一致，研究 fork `f312a71` 与 Touchline 27 中均未改动。它们不是 FC 27
专属代码，而是通用的计数读取/差值 kernel（一次 load、一次减法、一次 store，带边界检查），
已由上游 MIT 许可覆盖。没有重写，也没有仅凭“反汇编等价”作出侵权判断。
详见 [upstream-provenance.md](upstream-provenance.md#built-in-msl-helper-kernels-four-functions-in-nvn_builtinh)。

### 1.4 个人路径与构建元数据

- `dm/games/profile_guess.py` 的机器专属默认目录 `/Volumes/T7/nsp` 已移除；
  `--check` 的默认值改为 `$DM_NSP_ROOT`，未设置时使用当前目录。显式传参行为不变，
  生产入口不受影响。
- `dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate.dll` 内仍嵌入历史构建的 PDB 路径
  （`/Volumes/MacData/code/nxnative-zzg-xci/…/dmsh_xlate.pdb`）。按要求没有为清理
  元数据改写 DLL；它不含密钥，不影响运行，作为历史构建元数据记录在此。该 DLL 的
  包来源、许可与哈希清单沿用既有材料。
- 公开工作区与提交树中没有 `prod.keys`、密钥、签名证书、描述文件或游戏容器；
  文本文件中没有 `/Users/…`、`/Volumes/…` 之类的机器路径。

### 1.5 打包工具的实际缺陷修复

内置资源模式首次打包被 `dm/ios/tools/pack_ipa.py` 误判：FC 27 的 RomFS 里有游戏资源
`oo2tex.key`（128 字节纹理密钥，属于游戏数据），旧规则把任何 `.key` 一律当成主机密钥而
中止。修复保持原有安全边界：`prod.keys` 与 `*.keys` 在任何位置仍然拒绝，`.key` 只在
游戏自身的 `romfs/`、`aoc/` 树内放行。NSP 外置模式仍然拒绝整个 RomFS/AOC 树与容器。

## 2. 关于页面（实际实现）

修改：

- `dm/ios/Sources/Launcher.swift`：设置列表末尾新增「关于 Touchline 27」入口，
  以 sheet 呈现 `AboutView`，只有三个内容——项目主页、问题反馈、开源说明与免责声明。
  两个链接使用 `Link(destination:)`，由系统浏览器打开；没有 Releases、版本更新、
  版本检查、遥测或登录。
- `dm/apple/Localization.swift`：新增中文条目，英文原文作为 key 与兜底，沿用现有
  `GUIText`/`InterfaceLanguage` 机制（跟随系统 / English / 简体中文）。

链接与文案：

- 项目主页：<https://github.com/ohxiaoguang/touchline27>
- 问题反馈：<https://github.com/ohxiaoguang/touchline27/issues>
- 中文与英文免责声明采用任务指定文案，英文原文即本地化 key。

未增加任何其他启动器改动或页面层级；iPhone 与 iPad 共用同一 SwiftUI 布局（`Form` + sheet）。
本轮没有 macOS 启动器改动，关于页面只在两个 iOS IPA 中。

## 3. 两份 IPA

两份 IPA 来自同一份最终源码（同一 `dm/` 工作树、同一 shader chain
`b-32e83615bd74`、同一提交前状态），仅资源模式不同。输出目录在仓库之外：
`/Volumes/MacData/code2/touchline27-release-20261030/`。

| | IPA A：内置资源 | IPA B：NSP 外置资源 |
|---|---|---|
| 文件 | `Touchline27-Embedded.ipa` | `Touchline27-External-NSP.ipa` |
| 完整路径 | `/Volumes/MacData/code2/touchline27-release-20261030/Touchline27-Embedded.ipa` | `/Volumes/MacData/code2/touchline27-release-20261030/Touchline27-External-NSP.ipa` |
| 资源模式 | `DM_RESOURCE_BACKEND=directory`（RomFS 在 App 内） | `DM_RESOURCE_BACKEND=nsp`（游戏容器与密钥留在设备） |
| 大小 | 32,262,033,991 字节（30.05 GiB） | 139,829,048 字节（133.4 MiB） |
| SHA-256 | `c89e070cf62456653394fb09a96c10def12745a354a12a7b648ed734ac0aa0c4` | `25c4266843c8dfd0e7216eefae9790e980f346d4e18da452c4f4b5d859e1f4fa` |
| Bundle ID | `org.nxnative.0100c49025d3e000` | 同左 |
| 显示名称 / 版本 | Touchline 27 / 1.8 | 同左 |
| 目标 | iOS/iPadOS 26.0，arm64，UIDeviceFamily 1,2 | 同左 |
| 签名 | 未签名（项目既有管线；Team 占位 `0000000000`） | 同左 |
| RomFS 标记 | `Data/NX/fc/fcgame/fcgame.toc` 存在 | 不存在（无 romfs/aoc） |
| Shader 库 | `msl/b-32e83615bd74`，1101 个文件 | 同左 |
| 条目数 | 1436 | 1134 |

### 3.1 构建方式与参数

内置资源（使用项目既有低层入口，因为顶层 wrapper 只实现外置模式）：

```sh
./build/tools/nx_extract/nx_extract "/path/to/prod.keys" \
    "/path/to/base.nsp" "/path/to/update.nsp" "/path/to/work-embed/res"   # 合并 base+update RomFS

GAME=0100C49025D3E000 W=/path/to/work-embed \
PATCHED=/path/to/patched ROMFS=/path/to/work-embed/res/RomFS \
MSL_IOS=/path/to/ios-msl DM_IOS_BUILD_DIR=/path/to/work-embed/proj \
DM_RESOURCE_BACKEND=directory DM_BUNDLE_ID=org.nxnative.0100c49025d3e000 \
DM_DISPLAY_NAME="Touchline 27" DM_APP_VERSION=1.8 FONT_PY=/path/to/python bash dm/ios/tools/build_ipa.sh /path/to/Touchline27-Embedded.ipa
```

外置资源（项目顶层入口）：

```sh
./scripts/build-ios.sh --nsp-dir "/path/to/fc27" --patched "/path/to/patched" \
    --shaders "/path/to/ios-msl" --work "/path/to/work-ios-nsp" --out "/path/to/Touchline27-External-NSP.ipa"
```

两者都沿用了既有 Bundle ID、显示名称、应用图标、Entitlements 判定与未签名管线；
没有更换签名身份，也没有降低安全配置。FC 27 的 guest 保留为 5.03 GiB（低于 6 GiB 门槛），
因此管线不写扩展虚拟地址的 entitlements 文件，与既有构建一致。

### 3.2 构建后验证

| 检查项 | 内置资源版 | NSP 外置资源版 |
|---|---|---|
| 解压 / zip 结构 | 通过 | 通过 |
| App Bundle（Info.plist、PkgInfo、Assets.car、dm/、msl/） | 通过 | 通过 |
| `CFBundleIdentifier` | `org.nxnative.0100c49025d3e000` | 同左 |
| `CFBundleShortVersionString` / 显示名 | 1.8 / Touchline 27 | 1.8 / Touchline 27 |
| 架构 / 设备族 | arm64 / [1,2] | arm64 / [1,2] |
| `DMResourceBackend` | `directory` | `nsp` |
| 关于页面代码 | 有（编译进主二进制） | 有 |
| 两个 GitHub URL 字符串 | 均存在 | 均存在 |
| 中英文免责声明 | 均存在 | 均存在 |
| 游戏数据 | RomFS 在内（约 32 GB） | 无 romfs/aoc、无容器或密钥 |
| 外置 NSP 机制 | 不适用 | 保留（backend nsp，启动前扫描设备文件） |
| `codesign --verify` | 未签名（管线设计） | 未签名（管线设计） |
| Entitlements | 无（< 6 GiB 保留） | 同左 |

验证方法：`unzip -l`、`plutil`、`lipo -archs`、`codesign --verify --deep --strict`，
以及直接在主二进制中检索 About 文案与 URL（UTF-8）。没有在真机或模拟器上启动游戏或
点击关于页面：项目现有工具不支持自动化安装/启动，设备也不在本轮环境内。

## 4. Git 历史清理

- 新公开历史是**单一 root commit**（无父提交），从整理后的工作树创建，未把旧历史作为父提交。
- 提交树共 1,031 个文件；不含 41 张研究图片、`dmsh_xlate.pdb`、游戏容器、密钥、
  IPA、签名材料或构建产物。
- 旧 `main`（`786f3db…`）与 Codex tree refs 没有推送；没有 push `--mirror`，
  也没有推送旧 tag 或研究分支。
- 原历史在重写前已再次完整备份到仓库外：
  `/Volumes/MacData/touchline27-private-release-backup-20261030/pre-orphan-20261030/`
  （完整 `.git` 副本、全部 refs 的 bundle、refs 清单），加上此前的
  `git-directory/`、工作区归档与 41 张图/PDB 备份。备份没有加入 Git。
- 本地整理分支：`public-release-candidate`；旧 `main` 保持指向原提交，未被删除。

## 5. GitHub 推送

- 远程：`origin` → <https://github.com/ohxiaoguang/touchline27.git>（此前无 origin，
  新增，未覆盖任何既有远程）。
- 推送前确认仓库为空（`git ls-remote` 无 refs）。
- 推送方式：`git push -u origin public-release-candidate:main`（非强制、非 mirror）。
- 远程 `main` 的起点是根提交 `3d8ab9c70892a018f87a1b65a3d2bcd4a194d6a7`（源代码与本报告初版）；
  随后只有一个修订本报告计数的文档提交，因此 `refs/heads/main` 指向它。
  最终 HEAD 可用 `git ls-remote origin refs/heads/main` 复核。
- 上游跟踪已设置（`origin/main`）。

## 6. 尚未解决的真实问题

1. 两份 IPA 均为**未签名**，与项目既有管线一致。安装需要使用者自己的签名/侧载环境；
   FC 27 需要扩展虚拟地址相关能力时的签名由安装工具处理。
2. 没有真机或模拟器启动验证；关于页面的可点击性只经过编译与静态字符串验证。
3. 三个 DLL 的来源链已确认，但仍没有逐位可复现的构建命令与确切 SDK 补丁版本；
   `InformationalVersion` 中的 `2b2a9009…` 标记仍未在原始对象库中找到。
4. FPSLocker-Warehouse 的具体配置没有明确再使用许可。本轮只确认未复制其独特表达，
   这不等同于取得明示许可；文档保持该披露。
5. `dmsh_xlate.dll` 仍带历史构建的绝对 PDB 路径字符串；按约束未改写二进制。
6. 内置资源 IPA 约 30 GiB，仅适合本地/自用；它不是可公开再分发的安装包，
   其中包含游戏数据与派生资源，分发仍需单独评估。
7. macOS 启动器没有对应的关于页面；本轮范围是两个 iOS IPA。

## 7. 本轮改动文件

代码与工具：

- `dm/ios/Sources/Launcher.swift`（关于入口与 `AboutView`）
- `dm/apple/Localization.swift`（中英文条目）
- `dm/games/profile_guess.py`（默认路径改为 `$DM_NSP_ROOT`/当前目录）
- `dm/ios/tools/pack_ipa.py`（`.key` 误判修复，保持密钥拒绝边界）

文档：

- `README.md`、`THIRD_PARTY_NOTICES.md`、`CHANGELOG.md`
- `docs/public-release-review.md`、`docs/upstream-provenance.md`、`docs/fpslocker-provenance.md`
- `docs/release-audit.md`、`docs/image-publication-inventory.md`、`docs/building.md`
- `docs/development.md`、`docs/user-guide.md`、`docs/README.md`
- 本报告 `docs/final-publication-report.md`

未改动：根 `LICENSE`（MIT）、三个 DLL、FPS 执行逻辑、NVN/Metal 渲染、游戏运行时、
第三方依赖版本、Bundle ID 与签名配置。
