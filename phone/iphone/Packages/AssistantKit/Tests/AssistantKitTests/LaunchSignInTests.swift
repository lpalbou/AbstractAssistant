#if DEBUG
import Foundation
import Testing
@testable import AssistantKit

@Suite struct LaunchSignInTests {
    private let app = "/private/var/containers/Bundle/Application/X/AbstractAssistantPhone.app/AbstractAssistantPhone"

    @Test func noArgumentsKeepTheSavedSignIn() throws {
        #expect(try LaunchSignIn.parse([app]) == nil)
        #expect(try LaunchSignIn.parse([app, "--demo", "--screen", "settings"]) == nil)
    }

    @Test func gatewayAndTokenSignIn() throws {
        let parsed = try LaunchSignIn.parse([app, "--gateway", "https://forge.example.ts.net/", "--token", "secret", "--user", "admin"])
        #expect(parsed == .signIn(gateway: URL(string: "https://forge.example.ts.net")!, token: "secret", user: "admin"))
    }

    @Test func userIsOptionalAndTheAddressIsNormalised() throws {
        let parsed = try LaunchSignIn.parse([app, "--token", " secret ", "--gateway", "forge.example.ts.net/console"])
        #expect(parsed == .signIn(gateway: URL(string: "https://forge.example.ts.net")!, token: "secret", user: nil))
    }

    @Test func forgetClears() throws {
        #expect(try LaunchSignIn.parse([app, "--forget-gateway"]) == .forget)
    }

    @Test(arguments: [
        ["--gateway", "https://g.example"],                      // no token
        ["--token", "secret"],                                    // no gateway
        ["--gateway", "--token", "secret"],                       // flag where the address goes
        ["--gateway", "https://g.example", "--token"],            // token value missing
        ["--gateway", "https://g.example", "--token", "  "],      // blank token
        ["--gateway", "http://public.example", "--token", "t"],   // HTTP off the local network
        ["--gateway", "https://u:p@g.example", "--token", "t"],   // credentials in the address
        ["--user", "admin"],                                      // user alone
        ["--forget-gateway", "--gateway", "https://g.example", "--token", "t"],
    ])
    func refused(_ args: [String]) {
        #expect(throws: LaunchSignIn.Invalid.self) { try LaunchSignIn.parse([app] + args) }
    }

    @Test func refusalNeverEchoesTheToken() {
        do { _ = try LaunchSignIn.parse([app, "--token", "do-not-print"]); Issue.record("accepted") }
        catch { #expect(!error.localizedDescription.contains("do-not-print")) }
    }
}
#endif
