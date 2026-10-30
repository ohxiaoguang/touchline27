// SPDX-License-Identifier: MIT
// Visibility only. Physical pad state and touch-to-game routing remain separate.
static inline int dm_touch_pad_visible(int enabled, int physical) { return enabled && !physical; }
static inline int dm_touch_right_visible(int enabled, int full) { return enabled && full; }
