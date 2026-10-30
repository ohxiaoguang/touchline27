# stb_vorbis audio decoder

Source: [nothings/stb](https://github.com/nothings/stb) `stb_vorbis.c` at commit 1ee679c (version 1.22). License in LICENSE (MIT or public domain, your choice; the same text ends the source file).
Use: the host decodes the Vorbis sound tracks of the games' WebM movies with it (`dm/host/hle_movie.c` includes the file with `STB_VORBIS_NO_STDIO`, `STB_VORBIS_NO_PULLDATA_API` and `STB_VORBIS_NO_INTEGER_CONVERSION`, and feeds each raw packet in as an Ogg page of its own).

Local change (GitHub PR #60; the retained import had the bug, nothings/stb issues #879 and #1594): a type-2 residue interleaves every channel of its submap, so `decode_residue` reads up to n × the submap's channel count values, not n × 2, and `start_decoder`'s temporary-memory estimate for a caller-owned buffer counts every channel of the stream for type-2 residues. Without it the 5.1 tracks libvorbis encodes can otherwise be distorted. Regression test: `make -C dm/host/tests build/t_vorbis build/t_vorbis_divides`, then run both binaries.

The correction is retained in source. Historical upstream issue/PR references explain its origin,
not additional supported games or a newly passing test result. No tests were run in the
documentation review.
