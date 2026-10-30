# The rewriter's patches of Nintendo SDK module builds (sdk): dm/tools/patch_nso.py applies those of a module's NSO build ID.
# Only FC 27's SDK 22.2.0 build is registered here; a patch of a game's own module (main) would go in dm/games/<id>/patches.py.
# CUTS as described in patch_nso.py ("Registered patches")
CUTS = {
  # FC 27 (EA SPORTS FC 27 1.8c.fd45, v327680) sdk (SDK 22.2.0): the AddressRegionManager node area 0x3fe00000 (about 1 GB) -> 0x3e00000 (62 MB), the same cut other SDK builds need.
  # The constructor is at sdk+0x14def0 (the limit = alias start + 0x3fe00000 at +0x14df00, registered as an occupied region of that length at +0x14df6c);
  # VammManager::AllocateAddressRegion (sdk+0x14e010) places regions after it. Frostbite asks for its virtual address memory in 512 MB regions and less (main+0x17f9884):
  # 3.03 GiB of regions in a full match, behind a node area of about 1 GB. With the node area at 62 MB the same route fits a 3.5 GiB alias region
  # (docs/research/fc27-bringup.md section 20); 3.375 GiB is fatal at boot.
  # Unlike SDK 18, this build aligns regions of 1 GB and more to 2 MB (the size classes are 64 KB / 2 MB, sdk+0x14e060), so there is no 1 GB alignment to cut.
  'fed212d6e0963706f9f4b16ea5d65879': [
    (0x14df00, '08fca752', '087ca052', 'AddressRegionManager constructor: node area limit mov w8,#0x3fe00000 -> mov w8,#0x3e00000'),
    (0x14df6c, '09fca752', '097ca052', 'AddressRegionManager constructor: length of the node area registered as an occupied region mov w9,#0x3fe00000 -> mov w9,#0x3e00000'),
  ],
}
