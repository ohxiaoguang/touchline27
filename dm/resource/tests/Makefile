B := $(CURDIR)/build
R := $(abspath ..)
H := $(abspath ../../host)
PROFILE := $(H)/gen/$(GAME)
CC := clang
FLAGS := -O1 -g -Wall -Wextra -Werror -Wno-deprecated-declarations
.PHONY: run core hle mac oracle platform
run: core hle mac
mac: | $(B)
	PYTHONPYCACHEPREFIX=$(B)/pycache python3 generate.py $(B)/mac-fixture
	$(CC) $(FLAGS) -fsanitize=address,undefined t_mac_check.c ../../macos/resource_check.c ../nxrom.c -o $(B)/t_mac_check
	$(B)/t_mac_check $(B)/mac-fixture/base.nsp $(B)/mac-fixture/test.keys $(B)/mac-fixture/update.nsp $(B)
	$(B)/t_mac_check $(B)/mac-fixture/base.xci $(B)/mac-fixture/test.keys $(B)/mac-fixture/update.nsp $(B)
core: | $(B)
	PYTHONPYCACHEPREFIX=$(B)/pycache python3 test_dlc.py -v
	PYTHONPYCACHEPREFIX=$(B)/pycache python3 test_nxrom.py -v
	PYTHONPYCACHEPREFIX=$(B)/pycache python3 test_resourcefs.py -v
	PYTHONPYCACHEPREFIX=$(B)/pycache python3 test_profile_resource.py -v
	PYTHONPYCACHEPREFIX=$(B)/pycache python3 test_shader_stream.py -v
	PYTHONPYCACHEPREFIX=$(B)/pycache python3 test_fifa_shader_image.py -v
	PYTHONPYCACHEPREFIX=$(B)/pycache python3 test_easf_keyfind.py -v
	PYTHONPYCACHEPREFIX=$(B)/pycache python3 test_shader_package.py -v
	PYTHONPYCACHEPREFIX=$(B)/pycache python3 test_nsp_prepare.py -v
	PYTHONPYCACHEPREFIX=$(B)/pycache python3 test_resource_discovery.py -v
	PYTHONPYCACHEPREFIX=$(B)/pycache python3 test_prepared_build.py -v
	PYTHONPYCACHEPREFIX=$(B)/pycache python3 test_mac_prepared_build.py -v
	PYTHONPYCACHEPREFIX=$(B)/pycache python3 test_shader_compile.py -v
	PYTHONPYCACHEPREFIX=$(B)/pycache python3 test_build_pipeline.py -v
	PYTHONPYCACHEPREFIX=$(B)/pycache python3 test_packaging.py -v
	PYTHONPYCACHEPREFIX=$(B)/pycache python3 test_mac_packaging.py -v
	PYTHONPYCACHEPREFIX=$(B)/pycache python3 test_build_modes.py -v
	PYTHONPYCACHEPREFIX=$(B)/pycache python3 test_smoke_runner.py -v
	$(CC) $(FLAGS) -fsanitize=address,undefined -fno-omit-frame-pointer ../inspect.c ../nxrom.c -o $(B)/nxrom-sanitize
	PYTHONPYCACHEPREFIX=$(B)/pycache python3 malformed.py $(B)/nxrom-sanitize $(B)/malformed
hle: | $(B)
	@test "$(GAME)" = 010015100B514000 || { echo 'Synthetic HLE fixture: set GAME=010015100B514000'; exit 2; }
	$(MAKE) -C $(H) GAME=$(GAME) game_profile
	$(CC) -O1 -g -fsanitize=address,undefined -Wno-unused-function -I$(PROFILE) -I../../games/$(GAME) t_hle_nsp.c ../../host/tests/t_fs_stub.c ../../host/hle_bigstack.c ../../host/hle_resource.c -lz -o $(B)/t_hle_nsp
	PYTHONPYCACHEPREFIX=$(B)/pycache python3 generate.py $(B)/hle-fixture
	$(B)/t_hle_nsp $(B)/hle-fixture/base.nsp $(B)/hle-fixture/test.keys
	$(B)/t_hle_nsp $(B)/hle-fixture/base.nsp $(B)/hle-fixture/test.keys $(B)/hle-fixture/update.nsp
	$(B)/t_hle_nsp $(B)/hle-fixture/base.xci $(B)/hle-fixture/test.keys
	$(B)/t_hle_nsp $(B)/hle-fixture/base.xci $(B)/hle-fixture/test.keys $(B)/hle-fixture/update.nsp
	# The same two containers through one mod overlay (DM_ROMFS_OVERLAY): a replaced file, a file only
	# the mod has, a path the mod does not touch, and the merged directory listing.
	rm -rf $(B)/hle-mods
	mkdir -p $(B)/hle-mods/nested
	printf 'ZERO' > $(B)/hle-mods/zero
	printf 'added!' > $(B)/hle-mods/added
	$(B)/t_hle_nsp $(B)/hle-fixture/base.nsp $(B)/hle-fixture/test.keys --mods $(B)/hle-mods
	$(B)/t_hle_nsp $(B)/hle-fixture/base.nsp $(B)/hle-fixture/test.keys $(B)/hle-fixture/update.nsp --mods $(B)/hle-mods
	$(B)/t_hle_nsp $(B)/hle-fixture/base.xci $(B)/hle-fixture/test.keys --mods $(B)/hle-mods
	$(B)/t_hle_nsp $(B)/hle-fixture/base.nsp $(B)/hle-fixture/test.keys $(B)/hle-fixture/update.nsp --mods $(B)/hle-mods --dlc $(B)/hle-fixture/aoc.nsp
	$(B)/t_hle_nsp $(B)/hle-fixture/base.xci $(B)/hle-fixture/test.keys $(B)/hle-fixture/update.nsp --mods $(B)/hle-mods --dlc $(B)/hle-fixture/aoc.nsp
	$(CC) -O1 -g -fsanitize=address,undefined -Wno-unused-function -I$(PROFILE) -I../../games/$(GAME) t_hle_fault.c ../../host/tests/t_fs_stub.c ../../host/hle_bigstack.c ../../host/hle_resource.c -lz -o $(B)/t_hle_fault
	$(B)/t_hle_fault $(B)/hle-fixture/base.nsp $(B)/hle-fixture/test.keys $(B)
oracle: | $(B)
	@test -f "$(LIBHAC_DLL)" || { echo 'Set LIBHAC_DLL to the existing LibHac 0.19 assembly (no downloads)'; exit 2; }
	DOTNET_CLI_HOME=$(B)/dotnet-home DOTNET_GENERATE_ASPNET_CERTIFICATE=false DOTNET_CLI_TELEMETRY_OPTOUT=1 dotnet build oracle/Oracle.csproj --configfile oracle/NuGet.Config -p:LibHacDll="$(LIBHAC_DLL)" -p:BaseIntermediateOutputPath=$(B)/oracle-obj/ -o $(B)/oracle --verbosity quiet
platform: | $(B)
	xcrun --sdk iphoneos clang -target arm64-apple-ios26.0 $(FLAGS) -c ../nxrom.c -o $(B)/nxrom-ios.o
	# The shared launcher sources must compile for iOS as well: ResourceDiscovery.swift is
	# compiled by both App builds, and the iOS launcher reads it (dm/ios/Sources/Launcher.swift).
	xcrun --sdk iphoneos swiftc -typecheck -disable-sandbox -swift-version 5 -target arm64-apple-ios26.0 -module-cache-path $(B)/swift-cache \
		../../../gui/Sources/PackagingModel/Localization.swift ../../apple/LauncherSettings.swift ../../apple/ResourceDiscovery.swift ../../ios/Sources/Launcher.swift
$(B):
	mkdir -p $@
