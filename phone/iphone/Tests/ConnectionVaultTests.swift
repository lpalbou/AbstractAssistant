import XCTest
import AssistantKit
import AssistantPush
import AbstractGatewayClient
@testable import AbstractAssistantPhone

final class ConnectionVaultTests: XCTestCase {
    func testOfflineKeepAndForgetForTokenAndSessionWithoutUsername() throws {
        for session in [false, true] {
            let store = MemorySecretStore()
            let saved = SharedSignIn(gateway: URL(string: "http://127.0.0.1:9")!, user: nil,
                token: session ? nil : "token", session: session ? "session" : nil, csrf: session ? "csrf" : nil)
            try SharedSignInStore.save(saved, to: store)
            try ConnectionVault.signOut(saved, keep: true, store)
            XCTAssertNil(try store.read("signin"))
            let kept = try XCTUnwrap(ConnectionVault.kept(store).first)
            XCTAssertEqual(kept, saved)
            let restored = ConnectionVault.signIn(ConnectionVault.connection(kept))
            XCTAssertNotEqual(restored.reg, saved.reg)
            XCTAssertEqual(restored.token, saved.token)
            XCTAssertEqual(restored.session, saved.session)
            try SharedSignInStore.save(restored, to: store)
            try ConnectionVault.signOut(restored, keep: false, store)
            XCTAssertNil(try store.read("signin"))
            XCTAssertTrue(try ConnectionVault.kept(store).isEmpty)
        }
    }

    func testKeepFailurePreservesActiveCredential() throws {
        let store = FailingKeepStore()
        let saved = SharedSignIn(gateway: URL(string: "http://127.0.0.1:9")!, user: nil, token: "token")
        try SharedSignInStore.save(saved, to: store)
        XCTAssertThrowsError(try ConnectionVault.signOut(saved, keep: true, store))
        XCTAssertEqual(SharedSignInStore.load(from: store), saved)
    }

    func testDistinctUnidentifiedCredentialsAreNotOverwritten() throws {
        let store = MemorySecretStore()
        let first = SharedSignIn(gateway: URL(string: "https://example.test")!, user: nil, token: "one")
        let second = SharedSignIn(gateway: first.gateway, user: nil, token: "two")
        try ConnectionVault.signOut(first, keep: true, store)
        try ConnectionVault.signOut(second, keep: true, store)
        XCTAssertEqual(try ConnectionVault.kept(store).count, 2)
        try ConnectionVault.forgetKept(first, store)
        XCTAssertEqual(try ConnectionVault.kept(store), [second])
    }

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

private final class FailingKeepStore: SecretStore, @unchecked Sendable {
    private let base = MemorySecretStore()
    func read(_ name: String) throws -> Data? { try base.read(name) }
    func write(_ name: String, _ data: Data) throws {
        if name == "phone-kept-signins" { throw CocoaError(.fileWriteNoPermission) }
        try base.write(name, data)
    }
    func remove(_ name: String) throws { try base.remove(name) }
}
