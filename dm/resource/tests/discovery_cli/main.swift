// Discovery harness for the automated tests: runs the shared module over a
// folder and prints its report as JSON. Not part of either App - the packaged
// launchers call ResourceDiscovery directly.
//
//   discovery_cli <root> <title-hex> <prepared-modules-dir> [chosen-base [chosen-update]]
//   discovery_cli --boot <root> <title-hex>        (the entry dm/ios/Sources/main.m calls)
import Foundation

let arguments = CommandLine.arguments
// The iOS boot path: the same function main.m calls before UIApplicationMain. Running it here
// proves the C boundary, the message buffer and the environment it leaves behind.
if arguments.count == 4, arguments[1] == "--boot" {
    var message = [CChar](repeating: 0, count: 512)
    let ready = message.withUnsafeMutableBufferPointer { buffer in
        arguments[2].withCString { root in
            arguments[3].withCString { title in
                dmResourceDiscoveryBoot(root, title, buffer.baseAddress!, buffer.count)
            }
        }
    }
    var env: [String: String] = [:]
    for key in ["DM_RESOURCE_BACKEND", "DM_RESOURCE_NSP", "DM_RESOURCE_UPDATE", "DM_RESOURCE_KEYS", "DM_AOC_APP_VERSION", "DM_AOC_NSP_1", "DM_AOC_NSP_2"] {
        if let value = getenv(key) { env[key] = String(cString: value) }
    }
    let result: [String: Any] = ["ready": ready == 0, "message": String(cString: message), "env": env]
    let data = try! JSONSerialization.data(withJSONObject: result, options: [.sortedKeys, .prettyPrinted])
    print(String(decoding: data, as: UTF8.self))
    exit(0)
}
guard arguments.count >= 4 else {
    FileHandle.standardError.write(Data("usage: discovery_cli <root> <title-hex> <prepared-dir> [preferred-update]\n".utf8))
    exit(2)
}
let root = URL(fileURLWithPath: arguments[1], isDirectory: true)
guard let title = UInt64(arguments[2], radix: 16) else { exit(2) }
let modules = ResourceDiscovery.preparedBuilds(in: URL(fileURLWithPath: arguments[3], isDirectory: true))
let chosenBase = arguments.count > 4 && !arguments[4].isEmpty ? URL(fileURLWithPath: arguments[4]) : nil
let chosenUpdate = arguments.count > 5 && !arguments[5].isEmpty ? URL(fileURLWithPath: arguments[5]) : nil
let preferred = chosenBase.map { PreferredSelection(base: $0, update: chosenUpdate) }
let report = ResourceDiscovery.scan(root: root, titleID: title, modules: modules, preferred: preferred)

func describe(_ f: ResourceFile) -> [String: Any] {
    var out: [String: Any] = ["name": f.name, "path": f.url.path, "role": f.role.rawValue, "size": f.size]
    if let format = f.format { out["format"] = format.rawValue }
    if let id = f.titleID { out["title"] = ResourceDiscovery.hex(id) }
    if let tag = f.versionTag { out["version"] = tag }
    if !f.tags.isEmpty { out["tags"] = f.tags.sorted() }
    return out
}

var result: [String: Any] = [
    "state": "\(report.state)",
    "message": report.message,
    "ready": report.ready,
    "scanned": report.scanned,
    "notes": report.notes,
    "bases": report.bases.map(describe),
    "updates": report.updates.map(describe),
    "keys": report.keyFiles.map(describe),
    "combinations": report.combinations.map { combo -> [String: Any] in
        var out: [String: Any] = ["base": combo.base.path, "keys": combo.keys.path]
        if let update = combo.update { out["update"] = update.url.path }
        return out
    },
]
if let selection = report.selection {
    result["selection"] = ["base": selection.base.path, "update": selection.update?.url.path ?? "", "keys": selection.keys.path,
                           "dlcs": selection.dlcs.map { ["index": $0.index, "path": $0.url.path] as [String: Any] }]
}
let data = try! JSONSerialization.data(withJSONObject: result, options: [.sortedKeys, .prettyPrinted])
print(String(decoding: data, as: UTF8.self))
