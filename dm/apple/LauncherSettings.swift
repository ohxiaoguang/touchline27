// SPDX-License-Identifier: MIT
// Shared iOS/macOS settings schema, persistence and controls.
import SwiftUI
import Foundation
import Darwin

struct Setting: Decodable, Identifiable {
    let env, kind, label, note, def: String
    let options: [[String]]?   // choice: [value, label]
    let min, max, step: Double?   // range
    var id: String { env }
    enum CodingKeys: String, CodingKey { case env, kind, label, note, def = "default", options, min, max, step }
}
struct SettingsFile: Decodable { let settings: [Setting] }


final class LauncherModel: ObservableObject {
    private let defaults: UserDefaults
    let settings: [Setting]
    let fromFile: Set<String>   // set by an env file: shown, not changed
    @Published var values: [String: String] = [:]

    init(_ settings: [Setting], defaults: UserDefaults = .standard) {
        self.defaults = defaults
        #if os(iOS)
        let settings = settings + [
            Setting(env: "DM_TOUCH_CONTROLS", kind: "toggle", label: "Show virtual controller", note: "External controllers and game touch input remain available.", def: "1", options: nil, min: nil, max: nil, step: nil),
            Setting(env: "DM_RIGHT_STICK_VISIBLE", kind: "toggle", label: "Show right stick in 3D mode", note: "Changes appearance only. Available in the 3D layout.", def: "0", options: nil, min: nil, max: nil, step: nil)]
        #endif
        self.settings = settings
        fromFile = Set((ProcessInfo.processInfo.environment["DM_ENV_FILE_KEYS"] ?? "").split(separator: " ").map(String.init))
        for s in settings {
            if fromFile.contains(s.env), let v = ProcessInfo.processInfo.environment[s.env] { values[s.env] = v; continue }
            let saved = defaults.string(forKey: "launcher." + s.env)
            values[s.env] = saved.flatMap { v in s.options == nil || s.options!.contains { $0[0] == v } ? v : nil } ?? s.def   // a saved choice the game no longer offers: its default
        }
    }

    func set(_ s: Setting, _ value: String) {
        guard !fromFile.contains(s.env) else { return }
        values[s.env] = value
        defaults.set(value, forKey: "launcher." + s.env)
    }
    func binding(_ s: Setting) -> Binding<String> { Binding(get: { self.values[s.env] ?? s.def }, set: { self.set(s, $0) }) }
    var rightStickSettingEnabled: Bool {
        let layout = defaults.object(forKey: "DmPadLayout") as? Int
            ?? Int(ProcessInfo.processInfo.environment["DM_PAD_LAYOUT_DEFAULT"] ?? "0") ?? 0
        return values["DM_TOUCH_CONTROLS"] != "0" && layout == 1
    }

    // Before the game starts: every setting not set by an env file goes into the environment (DM_LANG replaces the packed language main.m set as a default)
    func apply() {
        for s in settings {
            let v = values[s.env] ?? s.def
            if fromFile.contains(s.env) { fputs("launcher: \(s.env) kept at \(v) (env file)\n", stderr); continue }
            defaults.set(v, forKey: "launcher." + s.env)
            setenv(s.env, v, 1); fputs("launcher: \(s.env)=\(v)\n", stderr)
        }
    }
}

struct SettingRow: View {
    let s: Setting
    @ObservedObject var m: LauncherModel
    @EnvironmentObject private var language: LanguagePreferences
    private func l(_ s: String) -> String { GUIText(key: s).render(language.language) }
    var body: some View {
        let locked = m.fromFile.contains(s.env)
        Section {
            switch s.kind {
            case "choice":
                Picker(l(s.label), selection: m.binding(s)) { ForEach(s.options ?? [], id: \.[0]) { Text(l($0[1])).tag($0[0]) } }
            case "range":
                let lo = s.min ?? 0, hi = s.max ?? 1
                let v = Binding<Double>(get: { Double(m.values[s.env] ?? s.def) ?? hi }, set: { m.set(s, String(format: "%.2f", $0)) })
                HStack {
                    Text(l(s.label))
                    Slider(value: v, in: lo...hi, step: s.step ?? 0.05)
                    Text("\(Int((v.wrappedValue * 100).rounded())) %").monospacedDigit().foregroundStyle(.secondary).frame(width: 56, alignment: .trailing)
                }
            default:
                Toggle(l(s.label), isOn: Binding(get: { (m.values[s.env] ?? s.def) == "1" }, set: { m.set(s, $0 ? "1" : "0") }))
            }
        } footer: {
            let note = locked ? (s.note.isEmpty ? "" : l(s.note) + " · ") + l("Set by an env file") : l(s.note)
            if !note.isEmpty { Text(l(note)) }
        }
        .disabled(locked || (s.env == "DM_RIGHT_STICK_VISIBLE" && !m.rightStickSettingEnabled))
    }
}



struct LauncherLanguageRow: View {
    @EnvironmentObject private var language: LanguagePreferences
    var body: some View {
        Picker(GUIText(key: "Interface language").render(language.language), selection: $language.language) {
            ForEach(InterfaceLanguage.allCases, id: \.self) { item in Text(item == .system ? GUIText(key: "System language").render(language.language) : item.displayName).tag(item) }
        }
    }
}

struct ResourceStatusView: View {
    let external, busy, verified: Bool
    let count: Int?
    let message: String
    let notes: [String]
    @EnvironmentObject private var language: LanguagePreferences
    private func l(_ text: GUIText) -> String { text.render(language.language) }
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(l(busy ? "Checking the selected files…" : verified ? (external ? "Resources verified for this App." : "The game files are inside this App; they are read only.") : "Resources need attention. Open the diagnostics below."))
                .font(.footnote).foregroundStyle(verified ? Color.green : Color.secondary)
            Text(l(DLCDiscoveryText.summary(external: external, busy: busy, verified: verified, count: count)))
                .font(.footnote)
            Text(l("This count is discovery only, not a runtime loaded count.")).font(.caption2).foregroundStyle(.secondary)
            if !notes.isEmpty && !busy {
                Text(l("Resource notices: \(notes.count). Open diagnostics.")).font(.caption).foregroundStyle(.orange)
            }
            DisclosureGroup(l("Resource diagnostics")) {
                ScrollView {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(GUIText(key: message).render(language.language)).font(.caption)
                        ForEach(Array(notes.prefix(20).enumerated()), id: \.offset) { _, note in
                            Text(GUIText(key: note).render(language.language)).font(.caption)
                        }
                        if notes.count > 20 { Text(l("Showing the first 20 of \(notes.count) diagnostics.")).font(.caption2) }
                    }.frame(maxWidth: .infinity, alignment: .leading)
                }.frame(maxHeight: 160)
            }
        }
    }
}
