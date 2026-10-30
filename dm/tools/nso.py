import sys
import struct
import nsoseg

img, build, sizes, bss = nsoseg.load(sys.argv[1])
with open(sys.argv[2], 'wb') as out:
    out.write(img)
with open(sys.argv[1], 'rb') as src:
    header = src.read(0x100)
segs = [struct.unpack_from('<III', header, 0x10 + i * 0x10) for i in range(3)]
print([hex(x) for s in segs for x in s], hex(bss), 'moduleid', header[0x40:0x60].hex())
