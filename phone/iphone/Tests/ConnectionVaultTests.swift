import XCTest
import AssistantKit
import PhoneGatewayClient
@testable import AbstractAssistantPhone

final class ConnectionVaultTests: XCTestCase {
    func testCredentialRoundTripUpdateAndRemoval() throws {
        let original = try ConnectionVault.read()
        defer { if let original { try? ConnectionVault.save(original) } else { try? ConnectionVault.remove() } }
        let first = SavedConnection(gateway: URL(string: "https://gateway.example")!, user: "storage-test", credential: .token("local-test-token"))
        try ConnectionVault.save(first)
        XCTAssertEqual(try ConnectionVault.read(), first)
        let second = SavedConnection(gateway: first.gateway, user: first.user, credential: .session(id: "local-test-session", csrf: "local-test-csrf"))
        try ConnectionVault.save(second)
        XCTAssertEqual(try ConnectionVault.read(), second)
        // Each save is a sign-in: a new push registration handle.
        let handle = try XCTUnwrap(ConnectionVault.current()?.reg)
        try ConnectionVault.save(second)
        XCTAssertNotEqual(ConnectionVault.current()?.reg, handle)
        try ConnectionVault.remove()
        XCTAssertNil(try ConnectionVault.read())
    }
}
