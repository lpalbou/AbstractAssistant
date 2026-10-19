import Foundation

public struct AppUpdateInfo: Equatable, Sendable {
    public enum Channel: String, Sendable { case development, testFlight, appStore, unknown }
    public var version: String
    public var build: String
    public var channel: Channel
    public var storeID: UInt64?
    public init(version: String?, build: String?, channel: Channel = .unknown, storeID: UInt64? = nil) {
        self.version = AutomationRunExplanation.nonempty(version) ?? "Unknown"
        self.build = AutomationRunExplanation.nonempty(build) ?? "Unknown"
        self.channel = channel; self.storeID = storeID
    }
    public var installedVersion: String { "\(version) (\(build))" }
    public var channelTitle: String {
        switch channel { case .development: "Development"; case .testFlight: "TestFlight"; case .appStore: "App Store"; case .unknown: "Not verified" }
    }
    public var checkTitle: String {
        switch channel {
        case .testFlight: "Check for updates in TestFlight"
        case .appStore: storeID == nil ? "How to check for updates" : "Check for updates in App Store"
        case .development: "View installation instructions"
        case .unknown: "Open TestFlight"
        }
    }
    public var destination: URL {
        switch channel {
        case .testFlight, .unknown: URL(string: "itms-beta://")!
        case .appStore: storeID.map { URL(string: "https://apps.apple.com/app/id\($0)")! } ?? Self.appStoreHelp
        case .development: URL(string: "https://github.com/lpalbou/AbstractAssistant/blob/main/phone/iphone/BUILD.md")!
        }
    }
    public static let betaHelp = URL(string: "https://testflight.apple.com/")!
    public static let appStoreHelp = URL(string: "https://support.apple.com/en-us/102629")!
}
