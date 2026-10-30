"""Patch-area geometry for dm/tools/patch_nso.py: one area, or two when the text is
too long for a single AArch64 B reach.

`plan` is the original conservative model (kept for its tests); `two_area` is what
the rewriter uses when the module's text does not fit one area, and `Area` is the
placement state the rewriter emits through.  Offsets are relative to the module
base, so the area before the base has a negative `off`.

Reach: an AArch64 `B` encodes a signed 27-bit word displacement, i.e. a target
within (1 << 27) bytes of the instruction.  Every site is entered through one B
from the original instruction to its stub, and the stub leaves through B back to
the original code, so both sides must lie inside one reach window per site.  A
site is therefore assigned to an area whose *current* emission point is inside its
reach, and the areas are laid out so that the low half of the text is served by
the area before the base and the high half by the area after the image.
"""
from dataclasses import dataclass

PAGE = 0x4000            # host page: 16 KB on Apple silicon
MAX_OFFSET = (1 << 63) - 1
REACH = 1 << 27          # AArch64 B: signed 26-bit word displacement


class LayoutError(ValueError):
    pass


@dataclass(frozen=True)
class Unit:
    low: int
    high: int
    size: int


@dataclass(frozen=True)
class Allocation:
    area: str
    start: int
    end: int                  # exclusive


def reachable(source, target, reach_bits=27):
    """Whether one aligned AArch64 B can encode this signed displacement."""
    if not 2 <= reach_bits <= 27 or source % 4 or target % 4:
        return False
    return -(1 << reach_bits) <= target - source < (1 << reach_bits)


def page_up(x):
    return (x + PAGE - 1) & ~(PAGE - 1)


def plan(image_size, pre_size, after_size, units, reach_bits=27):
    """Return disjoint allocations or raise before any output is emitted.

    The two reservations are [-pre_size, 0) and [page_up(image_size),
    page_up(image_size)+after_size). Both must be host-page aligned. The
    optional smaller reach exists for compact boundary fixtures only.
    """
    if not 2 <= reach_bits <= 27:
        raise LayoutError('invalid branch reach')
    if not all(type(n) is int for n in (image_size, pre_size, after_size)):
        raise LayoutError('layout dimensions must be integers')
    if image_size <= 0 or pre_size < 0 or after_size < 0:
        raise LayoutError('invalid image or island size')
    if pre_size % PAGE or after_size % PAGE:
        raise LayoutError('island sizes must be page aligned')
    after = (image_size + PAGE - 1) & ~(PAGE - 1)
    if pre_size > MAX_OFFSET or after + after_size > MAX_OFFSET:
        raise LayoutError('layout exceeds signed offset range')
    cursor = {'pre': -pre_size, 'after': after}
    limit = {'pre': 0, 'after': after + after_size}
    result = []
    for unit in units:
        if not isinstance(unit, Unit) or not all(type(n) is int for n in (unit.low, unit.high, unit.size)):
            raise LayoutError('invalid patch unit')
        if (unit.low < 0 or unit.high < unit.low or unit.high >= image_size
                or unit.low % 4 or unit.high % 4 or unit.size <= 0 or unit.size % 4):
            raise LayoutError('invalid patch unit bounds or size')
        for area in ('after', 'pre'):
            start = cursor[area]
            end = start + unit.size
            if end > limit[area]:
                continue
            if all(reachable(src, dst, reach_bits) and reachable(dst, src, reach_bits)
                   for src in (unit.low, unit.high) for dst in (start, end - 4)):
                result.append(Allocation(area, start, end))
                cursor[area] = end
                break
        else:
            raise LayoutError(f'cannot place unit [{unit.low:#x}, {unit.high:#x}] with size {unit.size:#x}')
    return result


class Area:
    """One executable patch area: `off` relative to the module base (negative when
    it lies before the base), `cap` its size in bytes (None = unbounded, the file
    grows) and `buf` the words emitted into it so far."""

    def __init__(self, name, off, cap=None):
        if off % PAGE:
            raise LayoutError(f'{name}: area offset {off:#x} is not page aligned')
        if cap is not None and (cap <= 0 or cap % PAGE):
            raise LayoutError(f'{name}: area size {cap:#x} is not a positive multiple of the page size')
        self.name, self.off, self.cap = name, off, cap
        self.buf = bytearray()

    @property
    def next(self):
        """Address of the next word emitted into this area."""
        return self.off + len(self.buf)

    @property
    def end(self):
        return self.off + len(self.buf)

    def reaches(self, site, margin=0x1000):
        """Whether a stub emitted at `next` can be entered from `site` and return:
        every generated B stays inside the stub or goes back near the site."""
        d = self.next - site
        return -REACH + margin <= d < REACH - margin

    def room(self):
        return None if self.cap is None else self.cap - len(self.buf)

    def emit(self, word):
        if self.cap is not None and len(self.buf) + 4 > self.cap:
            raise LayoutError(f'{self.name}: patch area full at {len(self.buf):#x} of {self.cap:#x} bytes '
                              f'(raise DM_PATCH_PRE)')
        self.buf += (word & 0xFFFFFFFF).to_bytes(4, 'little')


@dataclass
class TwoArea:
    pre: Area
    after: Area
    split: int               # sites below this address are served by `pre`
    image_size: int

    def areas(self):
        return (self.pre, self.after)


def two_area(image_size, text_end, pre_size=0x1000000, margin=0x200000):
    """Layout for a module whose text one area cannot reach.

    `pre` sits at [-pre_size, 0). `after` starts at page_up(image_size) (past bss,
    the key page and the frame-step state page) and grows as needed. Every site
    below `split` is served by `pre`, everything above by `after`.

    Feasible when the two reach windows overlap:
        after_off - REACH + margin  <=  split  <  REACH - pre_size
    The upper bound keeps the longest pre -> site distance (split + pre_size)
    inside one B, the lower bound keeps the first after stub in reach of `split`.
    """
    if not all(isinstance(n, int) for n in (image_size, text_end, pre_size, margin)):
        raise LayoutError('layout dimensions must be integers')
    if image_size <= 0 or text_end <= 0 or text_end > image_size:
        raise LayoutError('invalid image or text size')
    if pre_size <= 0 or pre_size % PAGE or margin < PAGE:
        raise LayoutError('the pre area size must be a positive multiple of the page size')
    after_off = page_up(image_size)
    split = after_off - REACH + margin
    if split % 4:
        split = (split + 3) & ~3
    hi = REACH - pre_size                       # exclusive upper bound for split
    if split >= hi:
        raise LayoutError(
            f'two patch areas cannot reach this text: image {image_size:#x} puts the area after it at '
            f'{after_off:#x}, so sites from {split:#x} up needs that area, but a site at {hi:#x} is the '
            f'farthest the {pre_size:#x}-byte area before the base reaches; text ends at {text_end:#x}')
    return TwoArea(Area('pre', -pre_size, cap=pre_size), Area('after', after_off), split, image_size)
