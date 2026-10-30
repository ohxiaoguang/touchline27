# Vulkan headers

The C headers from Khronos's Vulkan-Headers, version 1.4.363 (`VK_HEADER_VERSION 363`), unmodified:

- `include/vulkan/vk_platform.h` and `vulkan_core.h`, the core API and its extensions;
- `include/vulkan/vulkan_vi.h`, for `VK_NN_vi_surface` (the Switch's window surface);
- `include/vk_video/*.h`, which `vulkan_core.h` includes.

They are used by the host's Vulkan layer (`dm/gfx/vk/hle_vk.m`), retained as shared infrastructure; FC 27 uses the NVN backend. The headers retain their dual SPDX expressions; this distribution selects the MIT alternative described below.

## Distribution license and source verification

On 2026-10-30 all 15 vendored headers were compared byte-for-byte with
[Vulkan-Headers v1.4.363](https://github.com/KhronosGroup/Vulkan-Headers/tree/v1.4.363).
All matched, and every header declares `SPDX-License-Identifier: Apache-2.0 OR MIT`.
This distribution selects the MIT alternative for these headers; the original SPDX
expressions and copyright headers are unchanged. The complete upstream MIT text is in
[LICENSES/MIT.txt](LICENSES/MIT.txt). The upstream license file's 2015-2023 date and
the individual headers' 2015-2026 dates are both preserved as supplied.

The original `LICENSE.md` index remains unchanged. No Apache-only file is included in this
vendored header subset. The v1.4.363 annotated tag object is
`7feeb71f59b8c1531ef5f7bb4b36e1aac46a0acb`; no unverified commit ID is asserted.
