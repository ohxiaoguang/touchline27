// SPDX-License-Identifier: MIT
// Shared game-resource discovery for the macOS and iOS launchers.
//
// Both platforms run exactly this code; only where the scan root comes from
// differs (the folder the player picks / the App's Documents). The launchers
// never parse a file name and never decide which container is a base game on
// their own: they hand over a root and a title ID and show what comes back.
//
// What it does, in order:
//   1. walk the root recursively (any depth), skipping links and unreadable
//      entries, and sniff each regular file's first bytes;
//   2. read the console keys (names only: no value is ever read out);
//   3. probe each container's own table (dm/resource/nxrom.c) for its format,
//      its Program NCA's title ID and whether its RomFS is a PatchRomFS;
//   4. pair the base game with updates and keys for one title ID;
//   5. verify every candidate pair against this App's prepared modules, so a
//      file from another build is refused instead of silently started;
//   6. report either one usable selection, several (a conflict to resolve in
//      the UI) or a state that says what is missing.
//
// Cost: a few KiB read per candidate whatever its size. No payload is read, no
// full-file hash is computed, nothing is copied, moved or modified.

import Foundation
import Darwin

// MARK: - The reader's probes (dm/resource/nxrom.c)

@_silgen_name("nxrom_probe_container")
private func nxrom_probe_container(_ path: UnsafePointer<CChar>, _ keys: UnsafePointer<CChar>?,
                                   _ format: UnsafeMutablePointer<Int32>?, _ programs: UnsafeMutablePointer<Int32>?,
                                   _ patched: UnsafeMutablePointer<Int32>?, _ title: UnsafeMutablePointer<UInt64>?,
                                   _ error: UnsafeMutablePointer<CChar>?, _ capacity: Int) -> Int32
@_silgen_name("nxrom_keys_usable")
private func nxrom_keys_usable(_ path: UnsafePointer<CChar>, _ error: UnsafeMutablePointer<CChar>?, _ capacity: Int) -> Int32
// const char *const * is ABI-identical to a pointer to pointers of CChar.
@_silgen_name("nxrom_verify")
private func nxrom_verify(_ base: UnsafePointer<CChar>, _ update: UnsafePointer<CChar>?, _ keys: UnsafePointer<CChar>?,
                          _ title: UInt64, _ modules: UnsafePointer<UnsafeMutablePointer<CChar>?>?,
                          _ builds: UnsafePointer<UnsafeMutablePointer<CChar>?>?, _ count: Int,
                          _ error: UnsafeMutablePointer<CChar>?, _ capacity: Int) -> Int32

@_silgen_name("nxrom_content_meta")
private func nxrom_content_meta(_ path: UnsafePointer<CChar>, _ keys: UnsafePointer<CChar>,
                                _ content: UnsafeMutablePointer<UInt64>, _ error: UnsafeMutablePointer<CChar>, _ capacity: Int) -> Int32
@_silgen_name("nxrom_open_aoc")
private func nxrom_open_aoc(_ path: UnsafePointer<CChar>, _ keys: UnsafePointer<CChar>, _ application: UInt64,
                            _ version: UInt32, _ fs: UnsafeMutablePointer<OpaquePointer?>,
                            _ error: UnsafeMutablePointer<CChar>, _ capacity: Int) -> Int32
@_silgen_name("nxrom_validate_aoc")
private func nxrom_validate_aoc(_ fs: OpaquePointer, _ error: UnsafeMutablePointer<CChar>, _ capacity: Int) -> Int32
@_silgen_name("nxrom_close")
private func nxrom_close(_ fs: OpaquePointer)
@_silgen_name("nxrom_title")
private func nxrom_title(_ fs: OpaquePointer) -> UInt64

public struct AddOnFile: Hashable, Sendable {
    public let url: URL
    public let title: UInt64
    public let index: UInt32
}

public enum ResourceRole: String, Sendable { case base, update, keys }

public enum ContainerFormat: String, Sendable { case nsp, xci
    public var label: String { self == .xci ? "XCI" : "NSP" }
}

/// One prepared module of this App: its name in ExeFS and the Build ID the
/// rewriter recorded, i.e. the only thing a game file has to match.
public struct ModuleBuild: Equatable, Sendable {
    public let module: String, build: String
    public init(module: String, build: String) { self.module = module; self.build = build }
}

/// A file the scan accepted as a resource, with what was learned about it.
public struct ResourceFile: Identifiable, Hashable, Sendable {
    public let url: URL
    public let role: ResourceRole
    public let size: Int64
    public let format: ContainerFormat?     // nil for a keys file
    public let titleID: UInt64?             // from the container itself
    public let nameTitleID: UInt64?         // a hint from the file name, never trusted
    public let tags: Set<String>            // APP / UPD / DLC in the name
    public let versionTag: UInt64?          // [v262144] in the name
    public var id: String { url.path }
    public var path: String { url.path }
    public var name: String { url.lastPathComponent }
    public var sizeText: String { ByteCountFormatter.string(fromByteCount: size, countStyle: .file) }
    /// What the UI shows under the role: the file itself, its format and size.
    public var detail: String { [format?.label, sizeText].compactMap { $0 }.joined(separator: " · ") }
}

/// A base game with the update chosen for it (nil: the base game alone) and the
/// keys that read them.
public struct ResourceCombination: Identifiable, Hashable, Sendable {
    public let base: ResourceFile
    public let update: ResourceFile?
    public let keys: ResourceFile
    public var dlcs: [AddOnFile] = []
    public var applicationVersion: UInt32 = 0
    public var aocEnvironment: [String: String] {
        var env = ["DM_AOC_APP_VERSION": String(applicationVersion)]
        for dlc in dlcs { env["DM_AOC_NSP_" + String(dlc.index)] = dlc.url.path }
        return env
    }
    public var id: String { base.url.path + "\u{0}" + (update?.url.path ?? "") }
    public var summary: String {
        guard let update else { return base.name + " (base game only)" }
        return base.name + " + " + update.name
    }
}

public enum DiscoveryState: Equatable, Sendable {
    case ready            // one verified selection
    case conflict         // several verified selections: the player picks
    case missingKeys      // no usable prod.keys below the root
    case missingBase      // files for this game, but no base game
    case versionMismatch  // files for this game, none matching this App's build
    case updateMismatch   // the base game matches, the update beside it does not
    case nothingFound     // no container at all
    case unavailable      // the App carries no prepared module metadata
}

/// What the player (or the boot code) asked for: a folder, and optionally a
/// combination they already picked, which wins over the automatic result.
public struct PreferredSelection: Sendable {
    public let base: URL
    public let update: URL?
    public init(base: URL, update: URL?) { self.base = base; self.update = update }
}

public struct DiscoveryReport: Sendable {
    public let root: URL
    public let titleID: UInt64
    public let state: DiscoveryState
    public let message: String
    public let selection: ResourceCombination?
    public let combinations: [ResourceCombination]
    public let bases: [ResourceFile]
    public let updates: [ResourceFile]
    public let keyFiles: [ResourceFile]
    /// The base game alone, when an update was found but does not match and the
    /// player may still choose to run without it. Never used automatically.
    public let fallback: ResourceCombination?
    public let notes: [String]
    public let scanned: Int
    public let seconds: TimeInterval
    public var ready: Bool { state == .ready && selection != nil }
}

// MARK: - Discovery

public enum ResourceDiscovery {
    /// Bounds, so a folder nobody curated cannot turn a scan into a hang.
    private static let maxDepth = 64
    private static let maxFiles = 200_000
    private static let maxVerifyAttempts = 8
    /// Smaller files cannot hold a container's table and a Program NCA header.
    private static let minContainerSize: Int64 = 0x200
    /// Names that mean "container" - a hint for which files to look into, never a
    /// decision: the bytes decide, and anything this large is inspected whatever it
    /// is called. Together they keep a folder full of unrelated files cheap: a
    /// 150k-file tree costs a few hundred opens instead of one per file.
    private static let containerExtensions: Set<String> = ["nsp", "xci", "nsz", "ncz", "xcz"]
    private static let probeEveryFileAbove: Int64 = 4 << 20

    // MARK: Entry point

    /// Scan `root` for this game's base game, update and console keys.
    /// - Parameters:
    ///   - titleID: the title this App was packaged for (Info.plist NXTitleID,
    ///     or the game profile's DM_GAME_ID on iOS). Never guessed from names.
    ///   - modules: this App's prepared modules (see `preparedBuilds`); an empty
    ///     list is refused rather than skipping the version check.
    ///   - keysOverride: a keys file the player picked explicitly.
    ///   - preferred: a combination the player picked in a conflict.
    public static func scan(root: URL, titleID: UInt64, modules: [ModuleBuild],
                            keysOverride: URL? = nil, preferred: PreferredSelection? = nil) -> DiscoveryReport {
        let started = Date()
        var notes: [String] = []
        var containers: [(url: URL, size: Int64, format: ContainerFormat)] = []
        var keyCandidates: [URL] = []
        var scanned = 0

        for entry in walk(root, notes: &notes) {
            scanned += 1
            if isKeysName(entry.url.lastPathComponent) { keyCandidates.append(entry.url) }
            guard isContainerCandidate(entry.url, size: entry.size) else { continue }
            let suffix = entry.url.pathExtension.lowercased()
            if let format = sniff(entry.url) { containers.append((entry.url, entry.size, format)) }
            else if ["nsz", "ncz", "xcz"].contains(suffix) {
                notes.append(entry.url.lastPathComponent + ": compressed containers are not supported; supply the decompressed NSP or XCI")
            }
        }
        // Stable, repeatable order: the file system's enumeration order is not.
        containers.sort { $0.url.path < $1.url.path }
        keyCandidates.sort { lhs, rhs in
            let lp = lhs.lastPathComponent.lowercased(), rp = rhs.lastPathComponent.lowercased()
            if (lp == "prod.keys") != (rp == "prod.keys") { return lp == "prod.keys" }
            return lhs.path < rhs.path
        }

        func report(_ state: DiscoveryState, _ message: String, selection: ResourceCombination? = nil,
                    combinations: [ResourceCombination] = [], bases: [ResourceFile] = [],
                    updates: [ResourceFile] = [], keys: [ResourceFile] = [],
                    fallback: ResourceCombination? = nil) -> DiscoveryReport {
            DiscoveryReport(root: root, titleID: titleID, state: state, message: message, selection: selection,
                            combinations: combinations, bases: bases, updates: updates, keyFiles: keys,
                            fallback: fallback, notes: notes, scanned: scanned,
                            seconds: Date().timeIntervalSince(started))
        }

        guard !modules.isEmpty else {
            return report(.unavailable, "This App carries no prepared module list, so the game version cannot be checked. Rebuild the App.")
        }
        guard titleID != 0 else {
            return report(.unavailable, "This App does not declare its game title ID, so its files cannot be identified.")
        }
        guard !containers.isEmpty else {
            return report(.nothingFound, "No NSP or XCI file was found in this folder. Add the game's own files; they may sit in any sub-folder.")
        }

        // 2. The keys. Without them no NCA header can be read, and guessing from
        //    file names is exactly what this module must not do.
        var keyFile: ResourceFile?
        var keyList: [ResourceFile] = []
        var rejectedKeys = 0
        for url in ([keysOverride].compactMap { $0 } + keyCandidates) {
            guard !keyList.contains(where: { $0.url.path == url.path }) else { continue }
            let size = ((try? FileManager.default.attributesOfItem(atPath: url.path))?[.size] as? NSNumber)?.int64Value ?? 0
            let entry = ResourceFile(url: url, role: .keys, size: size, format: nil, titleID: nil,
                                     nameTitleID: nameTitleID(url.lastPathComponent), tags: nameTags(url.lastPathComponent),
                                     versionTag: nil)
            keyList.append(entry)
            guard keyFile == nil else { continue }
            var error = [CChar](repeating: 0, count: 256)
            let usable = url.path.withCString { nxrom_keys_usable($0, &error, error.count) } == 0
            if usable { keyFile = entry } else { rejectedKeys += 1; notes.append(url.lastPathComponent + ": " + text(error)) }
        }
        guard let keys = keyFile else {
            let message = rejectedKeys == 0
                ? "No console keys (prod.keys) were found in this folder. Add your own prod.keys; its contents are never read out."
                : "The keys file in this folder cannot be used: " + (notes.last ?? "unknown reason")
            return report(.missingKeys, message, keys: keyList)
        }

        // 3. Each container's own facts.
        var bases: [ResourceFile] = [], updates: [ResourceFile] = []
        var addons: [AddOnFile] = []
        var contentProblem: String?
        for candidate in containers {
            var format: Int32 = 0, programs: Int32 = 0, patched: Int32 = 0
            var title: UInt64 = 0
            var error = [CChar](repeating: 0, count: 256)
            let ok = candidate.url.path.withCString { path in
                keys.url.path.withCString { keypath in
                    nxrom_probe_container(path, keypath, &format, &programs, &patched, &title, &error, error.count)
                }
            } == 0
            guard ok else {
                let name = candidate.url.lastPathComponent
                if let meta = contentMetadata(candidate.url, keys: keys.url), meta.type == 0x82 {
                    if meta.application != titleID {
                        notes.append(name + ": DLC belongs to another application")
                    } else if let prior = addons.first(where: { $0.title == meta.title }) {
                        if identical(prior.url, candidate.url) { notes.append(name + ": identical duplicate DLC ignored") }
                        else { contentProblem = name + ": conflicting DLC copies/revisions" }
                    } else {
                        addons.append(AddOnFile(url: candidate.url, title: meta.title, index: meta.index))
                    }
                } else {
                    notes.append(name + ": " + text(error))
                    contentProblem = name + ": unreadable or unsupported non-program container; DLC identity cannot be verified"
                }
                continue
            }
            let name = candidate.url.lastPathComponent
            let tags = nameTags(name), nameID = nameTitleID(name)
            // The container says whether it is a base game or a patch; the name
            // only breaks the tie when the container has no readable Program NCA.
            let isUpdate = patched != 0 || (programs == 0 && tags.contains("UPD"))
            guard title == titleID || title == titleID &+ 0x800 else {
                notes.append(name + ": title ID " + hex(title) + " is not this game (" + hex(titleID) + ")"
                             + (isAddOn(title, of: titleID) ? ", add-on content is not used by this launcher" : ""))
                continue
            }
            let entry = ResourceFile(url: candidate.url, role: isUpdate ? .update : .base, size: candidate.size,
                                     format: candidate.format, titleID: title, nameTitleID: nameID,
                                     tags: tags, versionTag: nameVersion(name))
            if isUpdate { updates.append(entry) } else { bases.append(entry) }
        }
        if let contentProblem { return report(.unavailable, contentProblem, keys: keyList) }
        addons.sort { $0.index < $1.index }
        bases = dedupe(bases, notes: &notes)
        updates = dedupe(updates, notes: &notes)

        guard !bases.isEmpty else {
            let message = updates.isEmpty
                ? "No base game for this title (" + hex(titleID) + ") was found in this folder."
                : "An update for this game was found, but not its base game. Add the base game NSP or XCI."
            return report(.missingBase, message, updates: updates, keys: keyList)
        }

        // 5. Only a selection that matches this App's prepared modules is usable.
        //    Pairs with an update and the base alone are tried separately: an App
        //    built for a version runs with that version's files, and a present
        //    update that does not match is reported, never quietly dropped.
        var withUpdate: [ResourceCombination] = [], baseOnly: [ResourceCombination] = []
        var failure: String?
        var contentFailure: String?
        var attempts = 0
        combos: for base in bases {
            for update in updates.map({ Optional($0) }) + [nil] {
                if withUpdate.count > 1 { break combos }
                // A verified pair settles it: this App was packaged from that update,
                // so the base game alone cannot match it as well (and costs a mount).
                if update == nil, !withUpdate.isEmpty { break }
                if attempts >= maxVerifyAttempts {
                    notes.append("Stopped after \(maxVerifyAttempts) candidate pairs; narrow the folder if the right version is missing.")
                    break combos
                }
                attempts += 1
                var combination = ResourceCombination(base: base, update: update, keys: keys)
                if let problem = verify(base: base, update: update, keys: keys, titleID: titleID, modules: modules) {
                    if failure == nil { failure = problem }
                    notes.append((update?.name ?? base.name) + ": " + problem)
                    continue
                }
                if !addons.isEmpty {
                    guard let meta = contentMetadata(update?.url ?? base.url, keys: keys.url),
                          meta.application == titleID, meta.type == (update == nil ? 0x80 : 0x81) else {
                        contentFailure = "DLC requires verified application CNMT version metadata."
                        continue
                    }
                    combination.dlcs = addons; combination.applicationVersion = meta.version
                    if let problem = verifyAddons(combination, titleID: titleID) {
                        contentFailure = problem
                        continue
                    }
                }
                if update == nil { baseOnly.append(combination) }
                else { withUpdate.append(combination) }
            }
        }

        let found = withUpdate.isEmpty ? baseOnly : withUpdate
        guard !found.isEmpty else {
            if let contentFailure { return report(.unavailable, contentFailure, keys: keyList) }
            let detail = failure ?? "The files found do not match this App's prepared build."
            return report(.versionMismatch, detail, updates: updates, keys: keyList)
        }
        // An update of this game is here but none matches this App, while the base
        // game alone does: say so, and leave running without it to the player.
        if withUpdate.isEmpty, !updates.isEmpty, let fallback = baseOnly.first {
            return report(.updateMismatch,
                          "The update file found does not match this App's prepared build. Add the update this App was packaged from, or play without it.",
                          combinations: [fallback], bases: bases, updates: updates, keys: keyList, fallback: fallback)
        }
        if let preferred, let chosen = found.first(where: {
            $0.base.url.standardizedFileURL == preferred.base.standardizedFileURL
                && $0.update?.url.standardizedFileURL == preferred.update?.standardizedFileURL
        }) {
            return report(.ready, "Found this game's files. Ready to play.", selection: chosen,
                          combinations: found, bases: bases, updates: updates, keys: keyList)
        }
        if found.count == 1, let only = found.first {
            return report(.ready, "Found this game's files. Ready to play.", selection: only,
                          combinations: found, bases: bases, updates: updates, keys: keyList)
        }
        return report(.conflict, "More than one matching combination was found. Choose the one to play with.",
                      combinations: found, bases: bases, updates: updates, keys: keyList)
    }

    private struct ContentMetadata {
        let title: UInt64, application: UInt64
        let version: UInt32, type: UInt32, index: UInt32
    }
    private static func contentMetadata(_ url: URL, keys: URL) -> ContentMetadata? {
        // Four naturally aligned words match nxrom_content's 32-byte C layout.
        var words = [UInt64](repeating: 0, count: 4), error = [CChar](repeating: 0, count: 512)
        let result = url.path.withCString { p in keys.path.withCString { k in
            words.withUnsafeMutableBufferPointer { w in nxrom_content_meta(p, k, w.baseAddress!, &error, error.count) }
        } }
        guard result == 0 else { return nil }
        return ContentMetadata(title: words[0], application: words[1], version: UInt32(truncatingIfNeeded: words[2]),
                               type: UInt32(truncatingIfNeeded: words[3]), index: UInt32(words[3] >> 32))
    }
    private static func identical(_ a: URL, _ b: URL) -> Bool {
        guard let lhs = try? FileHandle(forReadingFrom: a), let rhs = try? FileHandle(forReadingFrom: b) else { return false }
        defer { try? lhs.close(); try? rhs.close() }
        while true {
            do {
                let l = try lhs.read(upToCount: 1 << 20), r = try rhs.read(upToCount: 1 << 20)
                guard l == r else { return false }
                if l?.isEmpty != false { return true }
            } catch { return false }
        }
    }
    public static func verifyAddons(_ selection: ResourceCombination, titleID: UInt64) -> String? {
        for addon in selection.dlcs {
            var fs: OpaquePointer?, error = [CChar](repeating: 0, count: 512)
            let result = addon.url.path.withCString { p in selection.keys.path.withCString { k in
                nxrom_open_aoc(p, k, titleID, selection.applicationVersion, &fs, &error, error.count)
            } }
            guard result == 0, let fs else { return addon.url.lastPathComponent + ": " + text(error) }
            let identity = nxrom_title(fs) == addon.title
            let valid = nxrom_validate_aoc(fs, &error, error.count) == 0
            nxrom_close(fs)
            if !identity { return addon.url.lastPathComponent + ": DLC identity changed; rescan the resource folder." }
            if !valid { return addon.url.lastPathComponent + ": " + text(error) }
        }
        return nil
    }

    // MARK: Prepared modules

    /// This App's prepared modules, read from the metadata the build already
    /// packages: `prepared_builds.tsv` (macOS) or the rewriter tables
    /// `*.fixups.tsv` (both platforms). An empty result means the App was built
    /// without them and a version check is impossible - callers refuse to play.
    public static func preparedBuilds(in directory: URL) -> [ModuleBuild] {
        var found: [String: String] = [:]
        // A module the game loads at run time with nn::ro is not in the container's ExeFS at all:
        // `nro.tsv` names it by SHA-256 and the host matches that when the game asks for it
        // (hle_ro.c). Its rewriter table still carries a Build ID, but no base game or update can
        // match it, so leaving it in the list refused every matching pair in a real App.
        var runtime: Set<String> = []
        if let text = try? String(contentsOf: directory.appendingPathComponent("nro.tsv"), encoding: .utf8) {
            for line in text.split(separator: "\n") where !line.hasPrefix("#") {
                guard let name = line.split(separator: "\t").first, !name.isEmpty else { continue }
                runtime.insert(String(name))
            }
        }
        let manifest = directory.appendingPathComponent("prepared_builds.tsv")
        if let text = try? String(contentsOf: manifest, encoding: .utf8) {
            for line in text.split(separator: "\n") {
                let fields = line.split(whereSeparator: { $0 == "\t" || $0 == " " }).map(String.init)
                guard fields.count == 2, isBuildID(fields[1]), !runtime.contains(fields[0]) else { continue }
                if found[fields[0]] == nil { found[fields[0]] = fields[1].lowercased() }
            }
        }
        if let names = try? FileManager.default.contentsOfDirectory(atPath: directory.path) {
            for name in names.sorted() where name.hasSuffix(".fixups.tsv") {
                let module = String(name.dropLast(".fixups.tsv".count))
                if runtime.contains(module) { continue }
                guard let text = try? String(contentsOf: directory.appendingPathComponent(name), encoding: .utf8) else { continue }
                for line in text.split(separator: "\n") where line.hasPrefix("# BUILD_ID") {
                    let fields = line.split(whereSeparator: { $0 == "\t" || $0 == " " }).map(String.init)
                    guard let build = fields.last, isBuildID(build) else { continue }
                    if found[module] == nil { found[module] = build.lowercased() }
                }
            }
        }
        return found.keys.sorted().map { ModuleBuild(module: $0, build: found[$0]!) }
    }

    /// Where a packaged App keeps them: macOS `profile/` (the manifest) and
    /// `program/` (the rewriter tables), iOS `dm/`.
    public static func preparedBuilds(bundle: Bundle = .main) -> [ModuleBuild] {
        guard let resources = bundle.resourceURL else { return [] }
        var merged: [String: String] = [:]
        for folder in ["profile", "program", "dm"] {
            for item in preparedBuilds(in: resources.appendingPathComponent(folder)) where merged[item.module] == nil {
                merged[item.module] = item.build
            }
        }
        return merged.keys.sorted().map { ModuleBuild(module: $0, build: merged[$0]!) }
    }

    // MARK: Verification

    /// Open the selection the way the host will and compare every prepared
    /// module's Build ID. Returns nil when it matches, else the reason.
    public static func verify(base: ResourceFile, update: ResourceFile?, keys: ResourceFile,
                              titleID: UInt64, modules: [ModuleBuild]) -> String? {
        guard !modules.isEmpty else { return "This App carries no prepared module list." }
        var error = [CChar](repeating: 0, count: 512)
        let names = modules.map { strdup($0.module) }
        let builds = modules.map { strdup($0.build) }
        defer { names.forEach { free($0) }; builds.forEach { free($0) } }
        let result = base.url.path.withCString { b in
            (update?.url.path ?? "").withCString { u in
                keys.url.path.withCString { k in
                    names.withUnsafeBufferPointer { n in
                        builds.withUnsafeBufferPointer { v in
                            nxrom_verify(b, u, k, titleID, n.baseAddress, v.baseAddress, modules.count, &error, error.count)
                        }
                    }
                }
            }
        }
        return result == 0 ? nil : text(error)
    }

    // MARK: File names (hints only, never trusted over the container)

    /// The 16-digit title ID a name carries in brackets. Only the 0100 prefix
    /// (the retail application range) is accepted, so an arbitrary 16-character
    /// hex run is not mistaken for a title.
    public static func nameTitleID(_ name: String) -> UInt64? {
        for token in bracketedTokens(name) where token.count == 16 {
            guard token.allSatisfy({ $0.isHexDigit }), let value = UInt64(token, radix: 16) else { continue }
            if value >> 48 == 0x0100 { return value }
        }
        // "[UPD][0100152000022800]" and "[0100152000022800]" share the form; a
        // bare 16-digit run is accepted only with a bracketed tag around it.
        return nil
    }

    /// APP / UPD / DLC tags, upper-cased.
    public static func nameTags(_ name: String) -> Set<String> {
        var tags = Set<String>()
        for token in bracketedTokens(name) {
            let upper = token.uppercased()
            if ["APP", "UPD", "DLC", "BASE"].contains(upper) { tags.insert(upper) }
        }
        return tags
    }

    /// `[v262144]` in the name. Display and ordering only: this module never
    /// picks the highest version, the Build ID check decides.
    public static func nameVersion(_ name: String) -> UInt64? {
        for token in bracketedTokens(name) where token.count > 1 {
            guard token.first == "v" || token.first == "V" else { continue }
            let digits = token.dropFirst()
            guard digits.allSatisfy({ $0.isNumber }), let value = UInt64(digits) else { continue }
            return value
        }
        return nil
    }

    private static func bracketedTokens(_ name: String) -> [String] {
        var tokens: [String] = [], current = ""
        var inside = false
        for character in name {
            if character == "[" { inside = true; current = "" }
            else if character == "]" { if inside { tokens.append(current) }; inside = false; current = "" }
            else if inside { current.append(character) }
        }
        return tokens
    }

    /// Worth looking into: a container's own extension, or a file large enough that
    /// it can only be game data whatever it is called.
    private static func isContainerCandidate(_ url: URL, size: Int64) -> Bool {
        guard size >= minContainerSize else { return false }
        if containerExtensions.contains(url.pathExtension.lowercased()) { return true }
        return size >= probeEveryFileAbove
    }

    private static func isKeysName(_ name: String) -> Bool {
        let lower = name.lowercased()
        return lower.hasSuffix(".keys")
    }

    private static func isBuildID(_ text: String) -> Bool {
        text.count == 32 && text.allSatisfy { $0.isHexDigit }
    }

    private static func isAddOn(_ title: UInt64, of application: UInt64) -> Bool {
        guard title > application else { return false }
        let delta = title - application
        return delta != 0x800 && delta % 0x1000 == 0
    }

    // MARK: Walking

    private struct Entry { let url: URL, size: Int64 }

    private static func walk(_ root: URL, notes: inout [String]) -> [Entry] {
        let fm = FileManager.default
        var isDirectory: ObjCBool = false
        guard fm.fileExists(atPath: root.path, isDirectory: &isDirectory), isDirectory.boolValue else {
            notes.append("Not a folder: " + root.path)
            return []
        }
        var log: [String] = []   // an escaping handler cannot write an inout array
        let keys: [URLResourceKey] = [.isRegularFileKey, .isDirectoryKey, .isSymbolicLinkKey, .fileSizeKey]
        guard let enumerator = fm.enumerator(at: root, includingPropertiesForKeys: keys,
                                             options: [.skipsHiddenFiles],
                                             errorHandler: { url, error in
                                                 log.append("Skipped " + url.lastPathComponent + ": " + error.localizedDescription)
                                                 return true
                                             }) else {
            notes.append("Cannot read " + root.path)
            return []
        }
        var entries: [Entry] = [], links = 0
        let keySet = Set(keys)   // built once: a per-file Set costs more than the read itself
        while let item = enumerator.nextObject() {
            guard let url = item as? URL else { continue }
            if enumerator.level > maxDepth {
                log.append("Skipped " + url.lastPathComponent + ": folder nesting is deeper than \(maxDepth)")
                enumerator.skipDescendants()
                continue
            }
            let values = try? url.resourceValues(forKeys: keySet)
            if values?.isSymbolicLink == true { links += 1; continue }   // never followed: no loops, no escapes from the root
            if values?.isDirectory == true { continue }
            guard values?.isRegularFile == true, let size = values?.fileSize else { continue }
            entries.append(Entry(url: url, size: Int64(size)))
            if entries.count >= maxFiles {
                log.append("Stopped after \(maxFiles) files; the folder holds more than a launcher should scan.")
                break
            }
        }
        if links > 0 { log.append("Ignored \(links) symbolic link(s); a resource must be a real file.") }
        entries.sort { $0.url.path < $1.url.path }
        notes.append(contentsOf: log)
        return entries
    }

    /// The container's own magic, not the extension: a renamed XCI is still an
    /// XCI, and a `.nsp` that is not a container is not one. One open/pread/close
    /// per file, with no object allocation, because a large folder has many files
    /// that are not containers (a scan of 150k files must stay a few seconds).
    private static func sniff(_ url: URL) -> ContainerFormat? {
        let fd = open(url.path, O_RDONLY)
        guard fd >= 0 else { return nil }
        defer { close(fd) }
        var head = [UInt8](repeating: 0, count: 0x104)
        let count = head.withUnsafeMutableBytes { read(fd, $0.baseAddress, 0x104) }
        guard count >= 4 else { return nil }
        if head[0] == 0x50, head[1] == 0x46, head[2] == 0x53, head[3] == 0x30 { return .nsp }          // "PFS0"
        if count >= 0x104, head[0x100] == 0x48, head[0x101] == 0x45, head[0x102] == 0x41, head[0x103] == 0x44 { return .xci }   // "HEAD"
        return nil
    }

    // MARK: Helpers

    /// The same file reached twice (a hard link, or one folder linked inside
    /// another) is one candidate. Identity comes from the file system - never
    /// from hashing gigabytes.
    private static func dedupe(_ files: [ResourceFile], notes: inout [String]) -> [ResourceFile] {
        var seen = Set<String>(), result: [ResourceFile] = []
        for file in files {
            var info = stat()
            let identity = stat(file.url.path, &info) == 0 ? "\(info.st_dev):\(info.st_ino)" : file.url.path
            if seen.insert(identity).inserted { result.append(file) }
            else { notes.append("Ignored a second path to the same file: " + file.name) }
        }
        return result
    }

    private static func text(_ buffer: [CChar]) -> String {
        let value = String(cString: buffer)
        return value.isEmpty ? "unreadable" : value
    }

    public static func hex(_ value: UInt64) -> String { String(format: "%016llX", value) }
}

// MARK: - Handing the result on

extension DiscoveryReport {
    /// This report with one combination chosen by the player (a resolved conflict).
    public func selecting(_ combination: ResourceCombination) -> DiscoveryReport {
        DiscoveryReport(root: root, titleID: titleID, state: .ready,
                        message: "Using " + combination.summary + ".",
                        selection: combination, combinations: combinations, bases: bases,
                        updates: updates, keyFiles: keyFiles, fallback: fallback,
                        notes: notes, scanned: scanned, seconds: seconds)
    }

    /// The environment the host reads when it mounts: set by the program, never
    /// by a hand-written env.txt. `overwrite: false` keeps a value an env file
    /// set (the diagnostic path), which is what the boot code does.
    @discardableResult
    public func applyEnvironment(overwrite: Bool = true) -> Bool {
        guard let selection else { return false }
        func put(_ key: String, _ value: String) {
            value.withCString { _ = setenv(key, $0, overwrite ? 1 : 0) }
        }
        put("DM_RESOURCE_BACKEND", "nsp")
        put("DM_RESOURCE_NSP", selection.base.url.path)
        put("DM_RESOURCE_UPDATE", selection.update?.url.path ?? "")
        put("DM_RESOURCE_KEYS", selection.keys.url.path)
        for index in 1...2047 { unsetenv("DM_AOC_NSP_" + String(index)) }
        for (key, value) in selection.aocEnvironment { put(key, value) }
        return true
    }

    /// iOS only: keep the game's own containers out of iCloud/iTunes backups,
    /// now that they may sit in Documents' root instead of `resources/`.
    /// Metadata only - nothing is moved, renamed or deleted, and saves, logs and
    /// settings stay in the backup.
    public func excludeResourcesFromBackup() {
        #if os(iOS)
        guard let selection else { return }
        let files = [selection.base.url, selection.update?.url, selection.keys.url].compactMap({ $0 }) + selection.dlcs.map(\.url)
        for url in files {
            var target = url
            let values = try? target.resourceValues(forKeys: [.isExcludedFromBackupKey])
            if values?.isExcludedFromBackup == true { continue }
            var update = URLResourceValues()
            update.isExcludedFromBackup = true
            do { try target.setResourceValues(update); fputs("discovery: excluded from backup: \(url.lastPathComponent)\n", stderr) }
            catch { fputs("discovery: cannot exclude \(url.lastPathComponent) from backup: \(error.localizedDescription)\n", stderr) }
        }
        #endif
    }
}

// MARK: - iOS boot

/// Called by main.m before `dm_host_preload_start`, so the paths the host will
/// read are already this App's real files: the preload and the later mount can
/// never disagree about which container to use. Never blocks on a container's
/// payload, only on headers.
/// Returns 0 when a selection is ready and applied, 1 with a message when not.
@_cdecl("dm_resource_discovery_boot")
public func dmResourceDiscoveryBoot(_ documents: UnsafePointer<CChar>, _ title: UnsafePointer<CChar>,
                                    _ message: UnsafeMutablePointer<CChar>, _ capacity: Int) -> Int32 {
    let root = URL(fileURLWithPath: String(cString: documents), isDirectory: true)
    let titleID = UInt64(String(cString: title), radix: 16) ?? 0
    let modules = ResourceDiscovery.preparedBuilds()
    let report = ResourceDiscovery.scan(root: root, titleID: titleID, modules: modules)
    func say(_ text: String) { _ = text.withCString { strlcpy(message, $0, capacity) } }
    if report.ready, report.applyEnvironment(overwrite: false) {
        report.excludeResourcesFromBackup()
        let chosen = report.selection!
        fputs("discovery: \(chosen.base.format?.label ?? "") \(chosen.base.url.path)"
              + (chosen.update.map { ", update " + $0.url.path } ?? ", no update")
              + ", keys \(chosen.keys.url.path)\n", stderr)
        say("ok")
        return 0
    }
    fputs("discovery: \(report.message)\n", stderr)
    say(report.message)
    return 1
}
