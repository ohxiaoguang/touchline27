"""The address-region gates' two searches (nso_syms.defined, nso_code.out_store: patch_nso.py "Address regions"), on hand-built MOD0 symbol tables and hand-encoded AArch64,
without game files. The images are what nso_syms.defined and nso_code.out_store see of a module: the NSO header's MOD0 pointer, a MOD0 header, a .dynamic section, a hash
table (its nchain is the symbol count), a symbol table and a string table."""
import struct
import sys
import unittest
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import nso_code   # noqa: E402
import nso_syms   # noqa: E402

MD = Cs(CS_ARCH_ARM64, CS_MODE_ARM)

MOV_X19_X1 = 0xAA0103F3   # mov x19, x1 (the out pointer, copied once in the prologue)
STR_X0_X19 = 0xF9000260   # str x0, [x19]
STR_X9_X19 = 0xF9000269   # str x9, [x19]
MOV_X20_X1 = 0xAA0103F4   # mov x20, x1
MOV_X9_X1 = 0xAA0103E9    # mov x9, x1
RET = 0xD65F03C0

ASK, FREE = '_ZN2nn2os6detail11VammManager21AllocateAddressRegionEPmm', '_ZN2nn2os6detail11VammManager17FreeAddressRegionEm'
UNDEF = '_ZN2nn2os6detail11VammManager21AllocateAddressRegionEPmmUnused'


def image(symbols, code=b'', code_at=0x1000, size=0x2000):
    """An image with MOD0 at 0x100, .dynamic at 0x120, the hash table at 0x200, the symbol table at 0x300, the string table at 0x500 and `code` at code_at.
    symbols: [(name, defined, value, size)] in table order after the null entry"""
    img = bytearray(size)
    img[:4] = b'NSO0'
    struct.pack_into('<I', img, 4, 0x100)
    img[0x100:0x104] = b'MOD0'
    struct.pack_into('<i', img, 0x104, 0x20)                       # .dynamic at mod0 + 0x20
    struct.pack_into('<QQ', img, 0x120, 5, 0x500)                  # DT_STRTAB
    struct.pack_into('<QQ', img, 0x130, 6, 0x300)                  # DT_SYMTAB
    struct.pack_into('<QQ', img, 0x140, 4, 0x200)                  # DT_HASH
    struct.pack_into('<QQ', img, 0x150, 0, 0)
    struct.pack_into('<II', img, 0x200, 1, len(symbols) + 1)       # nbucket, nchain (= the symbol count, the null entry included)
    strtab = bytearray(b'\0'); offs = [0]
    for name, *_ in symbols: offs.append(len(strtab)); strtab += name.encode() + b'\0'
    img[0x500:0x500 + len(strtab)] = strtab
    for i, (_, defined, value, sz) in enumerate(symbols, start=1):
        struct.pack_into('<IBBHQQ', img, 0x300 + i * 24, offs[i], 0x12, 0, 1 if defined else 0, value, sz)
    img[code_at:code_at + len(code)] = code
    return img


def code(*words): return b''.join(struct.pack('<I', w) for w in words)


class Symbols(unittest.TestCase):
    def test_defined_reads_offsets_and_sizes(self):
        img = image([(ASK, True, 0x1000, 0x10), (FREE, True, 0x1010, 4), (UNDEF, False, 0, 0)], code())
        self.assertEqual(nso_syms.defined(img), {ASK: (0x1000, 0x10), FREE: (0x1010, 4)})

    def test_no_symbol_table_reads_as_empty(self):
        img = image([])
        struct.pack_into('<I', img, 4, 0)                             # MOD0 pointer 0: no MOD0 at all
        self.assertEqual(nso_syms.defined(img), {})
        trunc = image([(ASK, True, 0x1000, 0x10)], code())[:0x200]     # cut before the symbol table
        self.assertEqual(nso_syms.defined(trunc), {})


class OutStore(unittest.TestCase):
    def test_the_one_store_through_the_out_pointer(self):
        img = image([(ASK, True, 0x1000, 0x10)], code(MOV_X19_X1, STR_X9_X19, RET))
        self.assertEqual(nso_code.out_store(img, 0x1000, 0x10, MD), (0x1004, 9))

    def test_two_stores_are_refused(self):
        img = image([(ASK, True, 0x1000, 0x10)], code(MOV_X19_X1, STR_X0_X19, STR_X9_X19, RET))
        with self.assertRaisesRegex(ValueError, '2 stores through the out pointer'):
            nso_code.out_store(img, 0x1000, 0x10, MD)

    def test_the_prologue_must_copy_the_out_pointer_once(self):
        for words in (code(STR_X0_X19, RET), code(MOV_X19_X1, MOV_X20_X1, STR_X0_X19, RET), code(MOV_X9_X1, MOV_X19_X1, STR_X0_X19, RET)):
            with self.subTest(words=words.hex()):
                img = image([(ASK, True, 0x1000, 0x10)], words)
                with self.assertRaisesRegex(ValueError, 'no single copy of the out pointer'):
                    nso_code.out_store(img, 0x1000, len(words), MD)

    def test_a_store_of_the_out_pointer_itself_is_no_return_value(self):
        # the prologue's own spill (str x1, [sp, ...]) and stores through other registers are not the region's address
        spill = 0xF90007E1   # str x1, [sp, #8]
        img = image([(ASK, True, 0x1000, 0x10)], code(spill, MOV_X19_X1, STR_X9_X19, RET))
        self.assertEqual(nso_code.out_store(img, 0x1000, 0x10, MD), (0x1008, 9))


if __name__ == '__main__':
    unittest.main()
