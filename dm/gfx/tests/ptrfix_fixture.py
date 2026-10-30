"""Write an authored Metal fixture using the production indirect-read helper."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import dmsh_ptrfix
source = '#include <metal_stdlib>\nusing namespace metal;\nstruct Data { uint _m0[1]; };\n'
source += dmsh_ptrfix.STRUCT + dmsh_ptrfix.body('indirect', 'const device Data*', 'lo', 'hi')
source += '''
kernel void probe(const device Data* pool [[buffer(0)]], device int* out [[buffer(1)]], uint id [[thread_position_in_grid]]) {
    const ulong addresses[7] = {0x100000080ul, 0x100000300ul, 0x100000400ul, 0xfffffffcul, 0x1000003fcul, 0x1000003feul, 0ul};
    ulong a = addresses[id]; int lo = int(uint(a)), hi = int(uint(a >> 32));
    dm_ptrfix whole = {0x100000000ul, 1024ul}, old = {0x100000200ul, 512ul};
    out[id] = indirect(lo, hi, pool, whole);
    out[7 + id] = indirect(lo, hi, (const device Data*)((const device uchar*)pool + 512), old);
}
'''
Path(sys.argv[1]).write_text(source)
