import CryptoKit
import Foundation
import Testing
@testable import AssistantPush

private func scratch() -> URL {
    FileManager.default.temporaryDirectory.appending(path: "assistant-push-\(UUID().uuidString)", directoryHint: .isDirectory)
}

private let gateway = URL(string: "https://gateway.example")!

@Suite struct SignInStoreTests {
    @Test func aSignInRoundTripsThroughTheStoreAndClearLeavesNothing() throws {
        let store = MemorySecretStore(), dir = scratch()
        defer { try? FileManager.default.removeItem(at: dir) }
        let s = SharedSignIn(gateway: gateway, user: "ana", tenant: "default", session: "sid-1", csrf: "csrf-1")
        try SharedSignInStore.save(s, to: store)
        #expect(SharedSignInStore.load(from: store, legacy: dir) == s)
        #expect(store.names == ["signin"])
        SharedSignInStore.clear(store, legacy: dir)
        #expect(SharedSignInStore.load(from: store, legacy: dir) == nil)
        #expect(store.names.isEmpty)
    }

    /// A sign-in an earlier build kept in a file (`signin.json`) is read once, moved into the store,
    /// and the file is gone: the person stays signed in across the change.
    @Test func aFileOfAnEarlierBuildIsMovedIntoTheStoreOnFirstRead() throws {
        let store = MemorySecretStore(), dir = scratch()
        defer { try? FileManager.default.removeItem(at: dir) }
        let s = SharedSignIn(gateway: gateway, user: "ana", token: "tok-1")
        try ProtectedFile(directory: dir, name: "signin").write(JSONEncoder().encode(s))
        #expect(SharedSignInStore.load(from: store, legacy: dir) == s)
        #expect(store.names == ["signin"])
        #expect(!FileManager.default.fileExists(atPath: dir.appending(path: "signin.json").path))
        #expect(SharedSignInStore.load(from: store, legacy: dir) == s)
    }

    /// The sealed pair of 0.15 (ChaChaPoly under a key file) moves the same way.
    @Test func aSealedSignInOf015IsMovedIntoTheStoreOnFirstRead() throws {
        let store = MemorySecretStore(), dir = scratch()
        defer { try? FileManager.default.removeItem(at: dir) }
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let s = SharedSignIn(gateway: gateway, user: "ana", token: "tok-1")
        let key = SymmetricKey(size: .bits256)
        try key.withUnsafeBytes { Data($0) }.write(to: dir.appending(path: "sealing.key"))
        try ChaChaPoly.seal(JSONEncoder().encode(s), using: key).combined.write(to: dir.appending(path: "signin.sealed"))
        #expect(SharedSignInStore.load(from: store, legacy: dir) == s)
        for name in ["signin.sealed", "sealing.key", "signin.json"] {
            #expect(!FileManager.default.fileExists(atPath: dir.appending(path: name).path), Comment(rawValue: name))
        }
    }

    /// Other named secrets (the watch's kept sign-ins) live in the same store, apart from the sign-in.
    @Test func namedSecretsAreKeptApart() throws {
        let store = MemorySecretStore(), dir = scratch()
        defer { try? FileManager.default.removeItem(at: dir) }
        try SharedSignInStore.write(named: "kept-signins", Data("[1]".utf8), to: store)
        #expect(try SharedSignInStore.read(named: "kept-signins", from: store, legacy: dir) == Data("[1]".utf8))
        #expect(SharedSignInStore.load(from: store, legacy: dir) == nil)
        SharedSignInStore.remove(named: "kept-signins", from: store, legacy: dir)
        #expect(try SharedSignInStore.read(named: "kept-signins", from: store, legacy: dir) == nil)
    }

    @Test func everySignInHasItsOwnHandle() {
        let a = SharedSignIn(gateway: gateway, user: "ana", token: "t"), b = SharedSignIn(gateway: gateway, user: "ana", token: "t")
        #expect(a.reg != b.reg)
        #expect(a.reg.count == 32 && a.reg.allSatisfy { $0.isHexDigit && !$0.isUppercase })
        #expect(a.sameCredential(as: b))
    }

    @Test func headersFollowTheCredential() {
        var r = URLRequest(url: gateway)
        SharedSignIn(gateway: gateway, user: "a", token: "tok").authorize(&r, write: true)
        #expect(r.value(forHTTPHeaderField: "Authorization") == "Bearer tok")
        var s = URLRequest(url: gateway)
        SharedSignIn(gateway: gateway, user: "a", session: "sid", csrf: "c").authorize(&s, write: false)
        #expect(s.value(forHTTPHeaderField: "X-AbstractGateway-Session") == "sid" && s.value(forHTTPHeaderField: "X-AbstractGateway-CSRF") == nil)
        SharedSignIn(gateway: gateway, user: "a", session: "sid", csrf: "c").authorize(&s, write: true)
        #expect(s.value(forHTTPHeaderField: "X-AbstractGateway-CSRF") == "c")
    }
}

@Suite struct HandoffTests {
    @Test func theWatchTakesANewerSignInFromTheIPhone() throws {
        let phone = SharedSignIn(gateway: gateway, user: "ana", session: "sid", csrf: "c", signedInAt: Date(timeIntervalSince1970: 200))
        let h = try #require(SignInHandoff(message: SignInHandoff(phone).message))
        #expect(h.signIn.sameCredential(as: phone) && h.signIn.reg != phone.reg)
        #expect(h.shouldAdopt(over: nil))
        let older = SharedSignIn(gateway: gateway, user: "bob", token: "t", signedInAt: Date(timeIntervalSince1970: 100))
        #expect(h.shouldAdopt(over: older))
        // The watch signed in on its own after the iPhone: it keeps its own.
        let newer = SharedSignIn(gateway: gateway, user: "bob", token: "t", signedInAt: Date(timeIntervalSince1970: 300))
        #expect(!h.shouldAdopt(over: newer))
        // The same credential again (a redelivered context) changes nothing.
        var same = h.signIn; same.signedInAt = Date(timeIntervalSince1970: 50)
        #expect(!h.shouldAdopt(over: same))
    }

    @Test func aMessageWithoutCredentialIsIgnored() {
        #expect(SignInHandoff(message: ["other": 1]) == nil)
        let empty = SignInHandoff(SharedSignIn(gateway: gateway, user: "a"))
        #expect(!empty.shouldAdopt(over: nil))
    }
}

/// The suites that share the stubbed network run one test at a time.
@Suite(.serialized) enum Network {}

extension Network {
@Suite struct RegistrationTests {
    let device = PushDevice(deviceID: "4f1c9a0b2d3e4f56", app: .watch, topic: "ai.abstractframework.assistant.watchkitapp",
                            env: "sandbox", name: "Wrist")
    let token = Data([0xab, 0xcd]) + Data(repeating: 0x01, count: 30)

    func registrar(at clock: Date) -> PushRegistrar {
        PushRegistrar(defaults: UserDefaults(suiteName: "push-\(UUID())")!, session: StubProtocol.session(), now: { clock })
    }

    @Test func theBodyIsExactlyTheGatewaysFields() throws {
        let body = PushRegistrationBody(token: "ab", device: device, reg: "0123456789abcdef")
        let json = try #require(JSONSerialization.jsonObject(with: JSONEncoder().encode(body)) as? [String: Any])
        #expect(Set(json.keys) == ["token", "topic", "env", "app", "reg", "name"])
        var nameless = device; nameless.name = nil
        let bare = try #require(JSONSerialization.jsonObject(with: JSONEncoder().encode(PushRegistrationBody(token: "ab", device: nameless, reg: "0123456789abcdef"))) as? [String: Any])
        #expect(Set(bare.keys) == ["token", "topic", "env", "app", "reg"])
    }

    @Test func aSignInRegistersThenOnlyDaily() async throws {
        StubProtocol.reset(200, #"{"ok": true, "relay": "off"}"#)
        let t0 = Date(timeIntervalSince1970: 1_000_000)
        let signIn = SharedSignIn(gateway: gateway, user: "ana", session: "sid", csrf: "csrf")
        let r = registrar(at: t0)
        #expect(await r.refresh(device: device, signIn: signIn) == .skipped("no token yet"))
        #expect(await r.tokenArrived(token, device: device, signIn: signIn) == .registered(relay: "off"))
        let req = try #require(StubProtocol.requests.first)
        #expect(req.httpMethod == "PUT")
        #expect(req.url?.absoluteString == "https://gateway.example/api/gateway/me/push/devices/4f1c9a0b2d3e4f56")
        #expect(req.value(forHTTPHeaderField: "X-AbstractGateway-CSRF") == "csrf")
        let sent = try #require(JSONSerialization.jsonObject(with: StubProtocol.bodies[0]) as? [String: Any])
        #expect(sent["token"] as? String == PushRegistrar.hex(token) && sent["reg"] as? String == signIn.reg && sent["app"] as? String == "watch")
        // The same token again within a day: nothing sent (relay off changes nothing).
        #expect(await r.tokenArrived(token, device: device, signIn: signIn) == .skipped("registered recently"))
        #expect(StubProtocol.requests.count == 1)
        // A new sign-in (new handle) registers again at once.
        let again = SharedSignIn(gateway: gateway, user: "ana", session: "sid", csrf: "csrf")
        #expect(await r.refresh(device: device, signIn: again) == .registered(relay: "off"))
        #expect(StubProtocol.requests.count == 2)
    }

    @Test func aDayLaterItRegistersAgain() {
        let rec = PushRecord(token: "ab", reg: "r", gateway: "g", user: "u", deviceID: "d", topic: "t", env: "sandbox",
                             at: Date(timeIntervalSince1970: 0), relay: "on")
        var next = rec; next.at = Date(timeIntervalSince1970: 86_399)
        #expect(!PushSchedule.needsPut(last: rec, next: next, now: next.at))
        next.at = Date(timeIntervalSince1970: 86_400)
        #expect(PushSchedule.needsPut(last: rec, next: next, now: next.at))
        var other = rec; other.token = "cd"
        #expect(PushSchedule.needsPut(last: rec, next: other, now: rec.at))
        #expect(PushSchedule.needsPut(last: nil, next: rec, now: rec.at))
    }

    @Test func aRefusedRegistrationIsTriedAgain() async {
        StubProtocol.reset(422, #"{"detail": "unknown app topic"}"#)
        let r = registrar(at: Date())
        let signIn = SharedSignIn(gateway: gateway, user: "ana", token: "tok")
        #expect(await r.tokenArrived(token, device: device, signIn: signIn) == .failed("HTTP 422"))
        #expect(await r.lastRecord == nil)
        StubProtocol.reset(200, #"{"ok": true, "relay": "on"}"#)
        #expect(await r.refresh(device: device, signIn: signIn) == .registered(relay: "on"))
    }

    @Test func signOutDeletesTheDevice() async throws {
        StubProtocol.reset(200, #"{"ok": true, "deleted": true}"#)
        let r = registrar(at: Date())
        let signIn = SharedSignIn(gateway: gateway, user: "ana", token: "tok")
        #expect(await r.signedOut(signIn, deviceID: "dev-1"))
        let req = try #require(StubProtocol.requests.first)
        #expect(req.httpMethod == "DELETE" && req.url?.path == "/api/gateway/me/push/devices/dev-1")
        #expect(req.value(forHTTPHeaderField: "Authorization") == "Bearer tok")
    }

    @Test func theProfileNamesTheEnvironment() {
        func profile(_ aps: String) -> Data {
            Data("garbage<?xml version=\"1.0\"?><plist version=\"1.0\"><dict><key>Entitlements</key><dict><key>aps-environment</key><string>\(aps)</string></dict></dict></plist>garbage".utf8)
        }
        #expect(PushEnvironment.parse(provision: profile("development")) == "sandbox")
        #expect(PushEnvironment.parse(provision: profile("production")) == "production")
        #expect(PushEnvironment.parse(provision: Data("none".utf8)) == nil)
    }
}

@Suite struct RenderingTests {
    let strings: [String: String] = [
        "push.approval.title": "Approval needed", "push.approval.body": "Open the Assistant to answer.",
        "push.question.title": "A question for you", "push.question.body": "Open the Assistant to answer.",
        "push.notify.title": "New alert", "push.notify.body": "Tap to read it.",
        "push.result.title": "An automation has a result", "push.result.body": "Tap to read it.",
        "push.failure.title": "An automation failed", "push.failure.body": "Tap to read it.",
        "push.result.named": "%@ has a result", "push.failure.named": "%@ failed", "push.earlier": "From an earlier sign-in",
    ]
    func text(_ k: String) -> String { strings[k] ?? k }
    func raised(_ data: [String: Any]) -> [String: Any] { ["type": "attention.raised", "sequence": 7, "data": data] }

    @Test func theCollapseIdIsTheGatewaysOne() {
        // abstractgateway push/dispatcher.py collapse_id: sha256("attention:" + record_key)[:32]
        #expect(AttentionID.collapse("wait:r1:k1:st") == "c9ece7c314e9a39da7d4407c0aa87900")
        #expect(AttentionID.collapse("publish:run-1:step-2") == "835a2e3ebff4bdbe3a277c79d502c9cf")
    }

    @Test func thePayloadNamesTheEventAndTheSignIn() {
        let p = PushPayload(userInfo: ["aps": ["thread-id": "approval"], "s": 42, "r": "0123456789abcdef"])
        #expect(p == PushPayload(seq: 42, reg: "0123456789abcdef", kind: "approval"))
        #expect(PushPayload(userInfo: ["aps": [:]]) == nil)
    }

    @Test func approvalsAndQuestionsAreTimeSensitive() throws {
        let a = try #require(PushRenderer.render(event: raised(["kind": "approval", "wait_key": "k", "run_id": "r1", "record_key": "wait:r1:k:s"]),
                                                 platform: .watch, text: text, name: { _ in nil }))
        #expect(a == PushRendering(title: "Approval needed", body: "Open the Assistant to answer.", timeSensitive: true, info: ["needs": "r1"]))
        let q = try #require(PushRenderer.render(event: raised(["kind": "question", "wait_key": "k", "run_id": "r1"]),
                                                 platform: .phone, text: text, name: { _ in nil }))
        #expect(q.title == "A question for you" && q.timeSensitive && q.tab == 1 && q.info["needs"] == "r1")
    }

    @Test func resultsAndFailuresArePassiveWithTheName() throws {
        let r = try #require(PushRenderer.render(event: raised(["kind": "notify", "automation_id": "a1", "seq": 3, "record_key": "automation:completed:a1:3"]),
                                                 platform: .phone, text: text, name: { $0 == "a1" ? "Morning digest" : nil }))
        #expect(r == PushRendering(title: "Morning digest has a result", body: "Tap to read it.", timeSensitive: false, info: ["automation": "a1"], tab: 2))
        let f = try #require(PushRenderer.render(event: raised(["kind": "failure", "automation_id": "a2", "record_key": "x"]),
                                                 platform: .watch, text: text, name: { _ in nil }))
        #expect(f.title == "An automation failed" && !f.timeSensitive && f.tab == nil)
    }

    @Test func aPublishedAlertShowsItsTitle() throws {
        let n = try #require(PushRenderer.render(event: raised(["kind": "notify", "record_key": "publish:run-1:step-2", "title": "Rain at 5 pm"]),
                                                 platform: .watch, text: text, name: { _ in nil }))
        #expect(n == PushRendering(title: "Rain at 5 pm", body: "Tap to read it.", timeSensitive: false, info: ["notify": "publish:run-1:step-2"]))
        #expect(PushRenderer.render(event: ["type": "run.finished", "data": [:]], platform: .watch, text: text, name: { _ in nil }) == nil)
    }

    @Test func anotherSignInsPushSaysSo() async {
        let current = SharedSignIn(gateway: gateway, user: "ana", token: "t")
        let strings = self.strings
        let r = await PushRenderer.content(for: PushPayload(seq: 3, reg: "ffffffffffffffff", kind: "approval"), platform: .watch,
                                           signIn: current, session: StubProtocol.session(), text: { strings[$0] ?? $0 }, name: { _ in nil })
        #expect(r == PushRendering(title: "Approval needed", body: "From an earlier sign-in", timeSensitive: false))
    }

    @Test func theExtensionReadsExactlyThatEvent() async throws {
        StubProtocol.reset(200, #"{"events": [{"id": "e", "type": "attention.raised", "sequence": 42, "data": {"kind": "approval", "wait_key": "k", "run_id": "r9", "record_key": "wait:r9:k:s"}}], "next_after": 42, "head": 50, "more": true}"#)
        let current = SharedSignIn(gateway: gateway, user: "ana", session: "sid", csrf: "c")
        let strings = self.strings
        let r = await PushRenderer.content(for: PushPayload(seq: 42, reg: current.reg, kind: "approval"), platform: .phone,
                                           signIn: current, session: StubProtocol.session(), text: { strings[$0] ?? $0 }, name: { _ in nil })
        #expect(r?.info["needs"] == "r9" && r?.timeSensitive == true)
        let req = try #require(StubProtocol.requests.first)
        #expect(req.url?.path == "/api/gateway/me/events" && req.url?.query == "after=41&limit=1")
        #expect(req.value(forHTTPHeaderField: "X-AbstractGateway-Session") == "sid")
        // The gateway cannot be read: nil keeps the generic text.
        StubProtocol.reset(503, "{}")
        #expect(await PushRenderer.content(for: PushPayload(seq: 42, reg: current.reg, kind: "approval"), platform: .phone,
                                           signIn: current, session: StubProtocol.session(), text: { strings[$0] ?? $0 }, name: { _ in nil }) == nil)
    }

    @Test func namesAreKeptForTheExtension() {
        let d = UserDefaults(suiteName: "names-\(UUID())")!
        AutomationNameBook.remember(["a1": "Morning digest", "a2": ""], in: d)
        #expect(AutomationNameBook.name("a1", in: d) == "Morning digest" && AutomationNameBook.name("a2", in: d) == nil)
    }
}
}
