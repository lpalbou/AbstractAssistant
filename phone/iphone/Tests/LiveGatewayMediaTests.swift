import XCTest
import AVFoundation
import UIKit
import AssistantKit
import AbstractGatewayClient
@testable import AbstractAssistantPhone

/// Explicit device-only verification. It uses the host app's keychain in place;
/// credentials are never exported, logged, passed through launch arguments or stored in a report.
final class LiveGatewayMediaTests: XCTestCase {
    @MainActor func testDiscoverSavedGateway() async throws {
        #if LIVE_MEDIA_VERIFICATION && !targetEnvironment(simulator)
        var report: [String: JSONValue] = ["stage": .string("discovery")]
        defer { try? write(report, name: "discovery.json") }
        guard let connection = try ConnectionVault.read() else {
            report["outcome"] = .string("no_saved_connection"); XCTFail("This iPhone has no saved gateway connection."); return
        }
        report["gateway"] = .string(connection.gateway.absoluteString)
        let client = LiveGatewayClient(baseURL: connection.gateway, credential: connection.credential, session: PhoneTransport.makeSession())
        do {
            _ = try await client.me()
            report["voice_defaults"] = try await raw(connection, path: "api/gateway/voice/defaults")
            let profiles = try await raw(connection, path: "api/gateway/config/provider-endpoint-profiles")
            if case .array(let rows)? = profiles["profiles"] {
                report["profiles"] = .array(rows.map { row in .object(Dictionary(uniqueKeysWithValues:
                    ["id", "virtual_provider", "provider_family", "scope", "enabled", "allowed_models"].compactMap { key in row[key].map { (key, $0) } })) })
            }
            let defaults = try await raw(connection, path: "api/gateway/config/capability-defaults")
            report["capability_defaults"] = safeRoutes(defaults)
            report["health"] = try await raw(connection, path: "api/health")
            report["versions"] = try await raw(connection, path: "api/gateway/about")
            let choices = try await client.workflows(forInterface: "abstractassistant.agent.v1")
            report["orchestrators"] = .array(choices.filter { $0.bundleId == "abstractassistant-orchestrator" }.map {
                .object(["version": .string($0.bundleVersion), "flow_id": .string($0.flowId)])
            })
            report["outcome"] = .string("authenticated")
        } catch { report["outcome"] = .string("failed"); report["error"] = .string(error.localizedDescription); throw error }
        #else
        throw XCTSkip("Run explicitly with scripts/build.py --live-media-test DEVICE --team TEAM.")
        #endif
    }

    @MainActor func testGenerateImageAndEdit() async throws { try await verifyMedia(voiceOnly: false) }
    @MainActor func testGenerateVoice() async throws { try await verifyMedia(voiceOnly: true) }

    @MainActor private func verifyMedia(voiceOnly: Bool) async throws {
        #if LIVE_MEDIA_VERIFICATION && !targetEnvironment(simulator)
        let reportName = voiceOnly ? "voice-generation.json" : "generation.json"
        var report: [String: JSONValue] = ["stage": .string(voiceOnly ? "voice" : "images")]
        defer { try? write(report, name: reportName) }
        let connection = try XCTUnwrap(ConnectionVault.read())
        report["gateway"] = .string(connection.gateway.absoluteString)
        let transport = PhoneTransport.makeSession()
        let client = LiveGatewayClient(baseURL: connection.gateway, credential: connection.credential, session: transport)
        do {
            _ = try await client.me() // One auth failure stops here; never retry credentials.
            var choices = try await client.workflows(forInterface: "abstractassistant.agent.v1")
            if !choices.contains(where: { $0.bundleId == "abstractassistant-orchestrator" && $0.bundleVersion == "0.0.13" }) {
                let url = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "AssistantOrchestrator", withExtension: "flow"))
                let boundary = "media-proof-" + UUID().uuidString
                var body = Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\nfalse\r\n--\(boundary)\r\nContent-Disposition: form-data; name=\"reload\"\r\n\r\ntrue\r\n--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"abstractassistant-orchestrator@0.0.13.flow\"\r\nContent-Type: application/octet-stream\r\n\r\n".utf8)
                body.append(try Data(contentsOf: url)); body.append(Data("\r\n--\(boundary)--\r\n".utf8))
                let result = try await raw(connection, path: "api/gateway/bundles/upload", method: "POST", data: body, contentType: "multipart/form-data; boundary=\(boundary)")
                report["bundle_uploaded"] = .bool(true)
                report["gateway_reloaded"] = result["gateway_reloaded"]
                choices = try await client.workflows(forInterface: "abstractassistant.agent.v1")
            }
            let choice = try XCTUnwrap(choices.first { $0.bundleId == "abstractassistant-orchestrator" && $0.bundleVersion == "0.0.13" && $0.flowId == "c53b1579" })
            if let saved = try? Data(contentsOf: evidenceDirectory().appending(path: reportName)),
               let previous = try? JSONDecoder().decode([String: JSONValue].self, from: saved),
               previous["gateway"]?.stringValue == connection.gateway.absoluteString,
               previous["bundle_version"]?.stringValue == choice.bundleVersion,
               previous["session_id"]?.stringValue?.hasPrefix("iphone-media-verification-") == true {
                report = previous
            }
            let session = report["session_id"]?.stringValue ?? "iphone-media-verification-" + UUID().uuidString.lowercased()
            report["session_id"] = .string(session)
            report["bundle_version"] = .string(choice.bundleVersion)
            func generate(_ name: String, _ prompt: String, source: PhoneArtifact? = nil) async throws -> PhoneArtifact {
                var body = StartRunRequest(prompt: prompt, sessionId: session, system: nil)
                body.bundleId = choice.bundleId; body.bundleVersion = choice.bundleVersion; body.flowId = choice.flowId
                body.inputData.tools = []
                if let source {
                    body.inputData.primaryImageArtifact = source.ref; body.inputData.hasPrimaryImageContext = true
                    body.inputData.context = .object(["primary_image_artifact": source.ref])
                }
                // Resume our own saved proof run after a Watch-priority interruption, avoiding duplicate generation.
                let id: String
                if let existing = report[name]?["run_id"]?.stringValue { id = existing }
                else { id = try await client.startRun(body) }
                report[name] = .object(["run_id": .string(id), "status": .string("running")]); try write(report, name: reportName)
                let deadline = Date().addingTimeInterval(600)
                var final: RunSummary?
                while Date() < deadline {
                    let run = try await client.run(id: id)
                    if run.isTerminal { final = run; break }
                    if run.waitsOnPerson { throw VerificationError.message("Unexpected approval required during media generation.") }
                    try await Task.sleep(for: .seconds(2))
                }
                guard let final, final.status == "completed" else {
                    try? await client.cancel(runId: id)
                    throw VerificationError.message(final?.error ?? "Generation did not complete within ten minutes.")
                }
                let file = try XCTUnwrap(final.mediaArtifacts.first { name == "voice" ? $0.isAudio : $0.isImage })
                let folder = FileManager.default.temporaryDirectory.appending(path: UUID().uuidString)
                try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
                defer { try? FileManager.default.removeItem(at: folder) }
                let url = folder.appending(path: file.filename)
                try await client.download(file, to: url)
                let bytes = try Data(contentsOf: url)
                if file.isImage { XCTAssertNotNil(UIImage(data: bytes), "Generated image must decode on iPhone") }
                else { XCTAssertGreaterThan(try AVAudioPlayer(contentsOf: url).duration, 0.1) }
                // Keep only our own test image for visual inspection; voice is checked then discarded.
                if file.isImage { try bytes.write(to: evidenceDirectory().appending(path: name + ".png"), options: .atomic) }
                let restored = try await client.run(id: id)
                XCTAssertEqual(restored.mediaArtifacts, final.mediaArtifacts)
                let sessionFiles = try await client.artifacts(sessionId: session)
                XCTAssertTrue(sessionFiles.contains { $0.id == file.id })
                report[name] = .object(["run_id": .string(id), "status": .string(final.status), "artifact_id": .string(file.artifactId), "content_type": .string(file.contentType), "bytes": .number(Double(bytes.count)), "decoded_on_iphone": .bool(true)])
                try write(report, name: reportName)
                return file
            }
            if voiceOnly {
                _ = try await generate("voice", "Generate a voice audio file speaking exactly these words: Hello Laurent. Images and voice are ready in your assistant.")
            } else {
                let image = try await generate("image", "Generate an image: a minimalist indigo and mint landscape with one coral sun. No text. Wide composition.")
                _ = try await generate("edit", "Edit the attached image: make the sun bright gold and add a second small moon. Preserve the landscape.", source: image)
            }
            report["outcome"] = .string("passed")
        } catch { report["outcome"] = .string("failed"); report["error"] = .string(error.localizedDescription); throw error }
        #else
        throw XCTSkip("Live media generation is opt-in and device-only.")
        #endif
    }
    private func safeRoutes(_ value: JSONValue) -> JSONValue {
        switch value {
        case .array(let rows): return .array(rows.map(safeRoutes))
        case .object(let row): return .object(row.reduce(into: [String: JSONValue]()) { result, item in
            let (key, value) = item
            if ["routes", "default", "effective", "value", "defaults", "provider", "model", "source", "kind", "modality", "task", "route", "configured", "available", "id", "name", "warnings", "errors"].contains(key) { result[key] = safeRoutes(value) }
        })
        default: return value
        }
    }
    private enum VerificationError: LocalizedError { case message(String); var errorDescription: String? { if case .message(let value) = self { value } else { "Verification failed" } } }
    @MainActor private func raw(_ connection: SavedConnection, path: String, method: String = "GET", data: Data? = nil, contentType: String? = nil) async throws -> JSONValue {
        var request = URLRequest(url: connection.gateway.appending(path: path)); request.httpMethod = method; request.httpBody = data; request.timeoutInterval = 120
        connection.credential.apply(to: &request, write: method != "GET")
        if let contentType { request.setValue(contentType, forHTTPHeaderField: "Content-Type") }
        let (bytes, response) = try await PhoneTransport.makeSession().data(for: request)
        guard let http = response as? HTTPURLResponse else { throw GatewayError.invalidResponse }
        if http.statusCode == 401 { throw GatewayError.unauthorized }
        guard (200..<300).contains(http.statusCode) else { throw GatewayError.http(status: http.statusCode, body: "") }
        return try JSONDecoder().decode(JSONValue.self, from: bytes)
    }
    private func evidenceDirectory() throws -> URL {
        let folder = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appending(path: "media-verification")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true); return folder
    }
    private func write(_ report: [String: JSONValue], name: String) throws {
        let encoder = JSONEncoder(); encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        try encoder.encode(report).write(to: evidenceDirectory().appending(path: name), options: .atomic)
    }
}
