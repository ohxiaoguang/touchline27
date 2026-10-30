import Foundation
@main struct SettingsChecks {
    @MainActor static func main() {
        let suite = "org.nxnative.launcher-test." + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let pad = Setting(env: "DM_TOUCH_CONTROLS", kind: "toggle", label: "Show virtual controller", note: "", def: "1", options: nil, min: nil, max: nil, step: nil)
        let right = Setting(env: "DM_RIGHT_STICK_VISIBLE", kind: "toggle", label: "Show right stick in 3D mode", note: "", def: "0", options: nil, min: nil, max: nil, step: nil)
        let model = LauncherModel([pad, right], defaults: defaults)
        assert(model.values[pad.env] == "1" && model.values[right.env] == "0")
        model.binding(pad).wrappedValue = "0"
        model.binding(right).wrappedValue = "1"
        let restored = LauncherModel([pad, right], defaults: defaults)
        assert(restored.values[pad.env] == "0" && restored.values[right.env] == "1")
        defaults.set(1, forKey: "DmPadLayout")
        assert(!restored.rightStickSettingEnabled)
        restored.set(pad, "1")
        assert(restored.rightStickSettingEnabled)
        defaults.set(0, forKey: "DmPadLayout")
        assert(!restored.rightStickSettingEnabled)
        setenv("DM_ENV_FILE_KEYS", "DM_TOUCH_CONTROLS", 1)
        setenv("DM_TOUCH_CONTROLS", "0", 1)
        let locked = LauncherModel([pad, right], defaults: defaults)
        locked.set(pad, "1")
        assert(locked.values[pad.env] == "0")
        print("Launcher defaults, persistence, layout gating and env override checks passed")
    }
}
