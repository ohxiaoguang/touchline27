import sys
from pathlib import Path
import unittest

from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nso_code


class Stream(unittest.TestCase):
    def test_invalid_words_at_chunk_boundaries(self):
        md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
        data = bytearray(bytes.fromhex('1f2003d5') * (0x4000 // 4 + 20))
        for offset in (0, 0x3ffc, 0x4000, len(data) - 4):
            data[offset:offset + 4] = bytes.fromhex('ffffffff')
        expected = sum(next(md.disasm_lite(data[i:i + 4], i), None) is None
                       for i in range(0, len(data), 4))
        self.assertEqual(nso_code.count_undecodable(data, 0, len(data), md), expected)


if __name__ == '__main__': unittest.main()
