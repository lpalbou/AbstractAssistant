import Foundation
import Testing
@testable import AbstractGatewayClient

private func json(_ s: String) throws -> JSONValue { try JSONDecoder().decode(JSONValue.self, from: Data(s.utf8)) }

// The Assistant workflow's image run, as the public gateway returned it (2026-10-18, trimmed).
private let imageOutput = """
{"response": "I'll generate an image of a red apple on a wooden table.", "success": true,
 "meta": {"modality": "image", "provider": "endpoint:airelays", "model": "gpt-image-2"},
 "artifact": {"$artifact": "d0c9a50ce4a51cb207e8c3e0a430cc06", "content_type": "image/png", "size_bytes": 2054680,
              "artifact_id": "d0c9a50ce4a51cb207e8c3e0a430cc06"},
 "content_type": "image/png",
 "outputs": {"image": [{"modality": "image", "content_type": "image/png",
   "artifact_ref": {"$artifact": "d0c9a50ce4a51cb207e8c3e0a430cc06", "content_type": "image/png", "size_bytes": 2054680}}]},
 "image_artifact": {"$artifact": "d0c9a50ce4a51cb207e8c3e0a430cc06", "content_type": "image/png"}}
"""

@Test func aRunsImageIsFoundOnceWhereverTheOutputNamesIt() throws {
    let media = MediaItem.of(output: try json(imageOutput), runId: "d37ebf77-31af-4ae7-b4ac-6dffb278339f")
    #expect(media == [MediaItem(artifactId: "d0c9a50ce4a51cb207e8c3e0a430cc06", runId: "d37ebf77-31af-4ae7-b4ac-6dffb278339f",
                                contentType: "image/png", kind: .image, sizeBytes: 2054680)])
}

@Test func aTextAnswerHasNoMedia() throws {
    #expect(MediaItem.of(output: try json(#"{"response": "Hello", "success": true, "meta": {}}"#), runId: "r").isEmpty)
    #expect(MediaItem.of(output: .string("Hello"), runId: "r").isEmpty)
    // A JSON artifact (a report, a snapshot) is not media to show.
    #expect(MediaItem.of(output: try json(#"{"artifact": {"$artifact": "abc", "content_type": "application/json"}}"#), runId: "r").isEmpty)
}

@Test func aVoiceRecordingIsAudio() throws {
    let out = try json(#"{"response": "Here it is.", "audio_artifact": {"$artifact": "a1", "content_type": "audio/wav"}, "outputs": {"voice": [{"artifact_ref": {"$artifact": "a1", "content_type": "audio/wav"}}]}}"#)
    #expect(MediaItem.of(output: out, runId: "r").map(\.kind) == [.audio])
}

@Test func anIdThatCouldLeaveTheArtifactRouteIsRefused() throws {
    let out = try json(#"{"artifact": {"$artifact": "../../admin", "content_type": "image/png"}}"#)
    #expect(MediaItem.of(output: out, runId: "r").isEmpty)
    let other = try json(#"{"artifact": {"$artifact": "ok", "run_id": "a/b", "content_type": "image/png"}}"#)
    #expect(MediaItem.of(output: other, runId: "r").isEmpty)
}

@Test func aSessionsMediaIsGroupedByTheTurnThatMadeIt() throws {
    let page = try json("""
    {"items": [
      {"artifact_id": "img1", "run_id": "turn1", "content_type": "image/png", "size_bytes": 10, "tags": {"kind": "generated_media"}},
      {"artifact_id": "up1", "run_id": "session_memory_s", "content_type": "image/png", "tags": {"kind": "attachment"}},
      {"artifact_id": "snap", "run_id": "turn1", "content_type": "application/json", "tags": {"kind": "generated_media"}},
      {"artifact_id": "wav1", "run_id": "child", "parent_run_id": "turn2", "content_type": "audio/wav", "tags": {"kind": "generated_media"}}
    ]}
    """)
    let byRun = MediaItem.bySession(page)
    #expect(byRun["turn1"]?.map(\.artifactId) == ["img1"])
    // Made in an agent's own run: shown with the turn (its parent), fetched from its own run.
    #expect(byRun["turn2"]?.first?.runId == "child")
    #expect(byRun["session_memory_s"] == nil)
}

@Test func aChosenWorkflowIsWhatTheRunStarts() throws {
    let orchestrator = WorkflowChoice(bundleId: "abstractassistant-orchestrator", bundleVersion: "0.0.0", flowId: "d5d4e5a1",
                                      name: "AbstractAssistant Orchestrator", interface: WorkflowChoice.assistantInterface, registryScope: "private")
    let body = try JSONSerialization.jsonObject(with: JSONEncoder().encode(
        StartRunRequest(prompt: "draw an apple", sessionId: "s", workflow: orchestrator))) as! [String: Any]
    #expect(body["bundle_id"] as? String == "abstractassistant-orchestrator")
    #expect(body["bundle_version"] as? String == "0.0.0")
    #expect(body["flow_id"] as? String == "d5d4e5a1")
    #expect(body["interface"] as? String == "abstractassistant.agent.v1")
    #expect(body["registry_scope"] as? String == "private")
    // None chosen: the gateway's default agent, as before.
    let plain = try JSONSerialization.jsonObject(with: JSONEncoder().encode(StartRunRequest(prompt: "hi", sessionId: "s"))) as! [String: Any]
    #expect(plain["flow_id"] as? String == "@default" && plain["interface"] as? String == "abstractcode.agent.v1")
    #expect(plain["bundle_id"] == nil)
}

@Test func theAssistantsWorkflowStartsFromTheConversationsNewestImage() throws {
    let orchestrator = WorkflowChoice(bundleId: "abstractassistant-orchestrator", bundleVersion: "0.0.15", flowId: "c53b1579",
                                      name: "AbstractAssistant Orchestrator", interface: WorkflowChoice.assistantInterface)
    let image = MediaItem(artifactId: "9e95848e506f", runId: "6a27d3a7", contentType: "image/png", kind: .image, sizeBytes: 1_851_974)
    let body = try JSONSerialization.jsonObject(with: JSONEncoder().encode(
        StartRunRequest(prompt: "make it simpler", sessionId: "s", workflow: orchestrator, primaryImage: image))) as! [String: Any]
    let input = body["input_data"] as! [String: Any]
    let ref = input["primary_image_artifact"] as? [String: String]
    #expect(ref == ["$artifact": "9e95848e506f", "run_id": "6a27d3a7", "content_type": "image/png"])
    #expect(input["has_primary_image_context"] as? Bool == true)
    #expect((input["context"] as? [String: Any])?["primary_image_artifact"] as? [String: String] == ref)
    // No image yet: the workflow is told so (it then asks for one rather than guessing).
    let none = try JSONSerialization.jsonObject(with: JSONEncoder().encode(
        StartRunRequest(prompt: "make it simpler", sessionId: "s", workflow: orchestrator))) as! [String: Any]
    #expect((none["input_data"] as! [String: Any])["has_primary_image_context"] as? Bool == false)
    // An agent has no such input: nothing is sent to it.
    let agent = try JSONSerialization.jsonObject(with: JSONEncoder().encode(
        StartRunRequest(prompt: "hi", sessionId: "s", primaryImage: image))) as! [String: Any]
    let agentInput = agent["input_data"] as! [String: Any]
    #expect(agentInput["primary_image_artifact"] == nil && agentInput["has_primary_image_context"] == nil)
}

@Test func aConversationListsTheDefaultAgentThenTheAssistantsWorkflows() throws {
    let page = try json("""
    {"default_agent_workflows": {"abstractassistant.agent.v1": {"workflow_id": "abstractassistant-orchestrator@0.0.0:d5d4e5a1"}},
     "items": [{"bundle_id": "abstractassistant-orchestrator", "bundle_version": "0.0.0", "registry_scope": "private",
                "entrypoints": [{"flow_id": "d5d4e5a1", "name": "AbstractAssistant Orchestrator"}]}]}
    """)
    let assistant = WorkflowChoice.choices(from: page, interface: WorkflowChoice.assistantInterface)
    #expect(assistant.first?.interface == WorkflowChoice.assistantInterface && assistant.first?.registryScope == "private")
    let agents = [WorkflowChoice(bundleId: "deep-research", bundleVersion: "1", flowId: "d", name: "Deep research"),
                  WorkflowChoice(bundleId: "basic-agent", bundleVersion: "1", flowId: "b", name: "Basic agent", isDefault: true)]
    let all = WorkflowChoice.conversation(agents: agents, assistant: assistant)
    #expect(all.map(\.bundleId) == ["basic-agent", "abstractassistant-orchestrator", "deep-research"])
    #expect(all.filter(\.isDefault).map(\.bundleId) == ["basic-agent"])
}

@Test func theMockMakesAPictureWithTheAssistantsWorkflow() async throws {
    let mock = MockGatewayClient(wordInterval: 0.001)
    let orchestrator = try await mock.conversationWorkflows().first { $0.interface == WorkflowChoice.assistantInterface }
    let id = try await mock.startRun(prompt: "Draw an apple", sessionId: "s", toolPolicy: nil, tools: nil, workflow: orchestrator, primaryImage: nil)
    try await Task.sleep(for: .milliseconds(1400))
    let run = try await mock.run(id: id)
    let media = MediaItem.of(output: run.output, runId: id)
    #expect(run.status == "completed" && media.map(\.kind) == [.image])
    let png = try await mock.mediaData(media[0])
    #expect(png.starts(with: [0x89, 0x50, 0x4E, 0x47]))
}

@Test func aBundleListedTwiceShowsItsNewestVersionOnce() {
    let shipped = WorkflowChoice(bundleId: "abstractassistant-orchestrator", bundleVersion: "0.0.9", flowId: "a", name: "AbstractAssistant Orchestrator",
                                 interface: WorkflowChoice.assistantInterface)
    var published = shipped; published.bundleVersion = "0.0.12"; published.flowId = "b"
    let list = WorkflowChoice.conversation(agents: [], assistant: [shipped, published])
    #expect(list.map(\.bundleVersion) == ["0.0.12"])
    #expect(WorkflowChoice.isNewer("0.0.11", than: "0.0.9") && !WorkflowChoice.isNewer("0.1", than: "0.1.0"))
}

@Test func aRunFromTheWorkflowCatalogNamesItsPublicBundle() {
    // As the gateway mints it: catalog_internal_bundle_id(tenant_id="default", bundle_id="abstractassistant-orchestrator").
    let host = "__catalog__v2__tenant_catalog__ZGVmYXVsdA__YWJzdHJhY3Rhc3Npc3RhbnQtb3JjaGVzdHJhdG9y"
    #expect(WorkflowChoice.bundleId(ofRunWorkflow: "\(host)@0.0.11:c53b1579") == "abstractassistant-orchestrator")
    #expect(WorkflowChoice.bundleId(ofRunWorkflow: "basic-agent@0.0.5:81795ea9") == "basic-agent")
    #expect(WorkflowChoice.bundleId(ofRunWorkflow: "__catalog__tenant__default__deep-research@1:x") == "deep-research")
}

/// A conversation's files: generated media and attachments; the person's spoken questions (the
/// uploads a transcript names as its source) and the transcripts themselves are not files.
@Test func aConversationsFilesLeaveOutItsSpokenQuestions() throws {
    let json = #"""
    {"items": [
      {"artifact_id": "t1", "run_id": "session_memory_s", "content_type": "text/plain", "created_at": "2026-10-19T10:00:05Z",
       "tags": {"kind": "derived_text", "task": "stt", "source_audio_artifact": "a1"}},
      {"artifact_id": "a1", "run_id": "session_memory_s", "content_type": "audio/wav", "filename": "ask.wav", "size_bytes": 480810,
       "created_at": "2026-10-19T10:00:00Z", "tags": {"kind": "attachment", "source": "upload"}},
      {"artifact_id": "img1", "run_id": "r1", "content_type": "image/png", "size_bytes": 2904892, "created_at": "2026-10-19T10:01:00Z",
       "tags": {"kind": "generated_media", "task": "image_generation"}},
      {"artifact_id": "doc1", "run_id": "session_memory_s", "content_type": "application/pdf", "filename": "report.pdf",
       "created_at": "2026-10-19T09:00:00Z", "tags": {"kind": "attachment", "source": "upload"}}
    ]}
    """#
    let page = try JSONDecoder().decode(JSONValue.self, from: Data(json.utf8))
    let f = SessionFiles.of(page)
    #expect(f.files.map(\.artifactId) == ["img1", "doc1"])
    #expect(f.spokenQuestions == 1)
    #expect(f.files[0].origin == .made && f.files[0].media?.kind == .image)
    #expect(f.files[1].origin == .attached && f.files[1].media == nil && f.files[1].fileName == "report.pdf")
    #expect(f.files[0].fileName == "image-img1.png")
}

@Test func aConversationsFolderFilesAreListedWithItsOtherFiles() throws {
    let json = #"""
    {"path": "", "entries": [
      {"name": "charts", "path": "charts", "type": "dir", "mtime": "2026-10-19T15:50:00Z"},
      {"name": "hero.svg", "path": "hero.svg", "type": "file", "size_bytes": 1986, "mtime": "2026-10-19T15:52:44Z"},
      {"name": "cv.png", "path": "charts/cv.png", "type": "file", "size_bytes": 4096, "mtime": "2026-10-19T15:53:00Z"},
      {"name": ".DS_Store", "path": ".DS_Store", "type": "file", "size_bytes": 6148},
      {"name": "HEAD", "path": ".git/HEAD", "type": "file", "size_bytes": 21},
      {"name": "m.pyc", "path": "tools/__pycache__/m.pyc", "type": "file", "size_bytes": 900}
    ], "truncated": false}
    """#
    let folder = SessionFiles.folder(try JSONDecoder().decode(JSONValue.self, from: Data(json.utf8)), runId: "r9")
    #expect(folder.map(\.folderPath) == ["hero.svg", "charts/cv.png"])
    #expect(folder[0].contentType == "image/svg+xml" && folder[0].media == nil && folder[0].fileName == "hero.svg")
    #expect(folder[1].fileName == "cv.png" && folder[1].name == "charts/cv.png" && folder[1].runId == "r9")
    #expect(folder[1].media == nil)                                   // shared, not opened
    let kept = SessionFiles(files: [SessionFile(artifactId: "img1", runId: "r1", contentType: "image/png",
                                                createdAt: ISO8601.date("2026-10-19T15:52:50Z"), origin: .made)], spokenQuestions: 1)
    let all = kept.adding(folder)
    #expect(all.files.map(\.id) == ["folder:charts/cv.png", "img1", "folder:hero.svg"])   // newest first
    #expect(all.spokenQuestions == 1)
}

/// Records each request's path and query, and answers from a table keyed by path.
final class PathStub: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var seen: [String] = []
    nonisolated(unsafe) static var answers: [String: (Int, String)] = [:]
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let url = request.url!
        Self.seen.append(url.path + (url.query.map { "?" + $0 } ?? ""))
        let (status, body) = Self.answers[url.path] ?? (404, "{}")
        let resp = HTTPURLResponse(url: url, statusCode: status, httpVersion: "HTTP/1.1", headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: resp, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(body.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@Suite(.serialized) struct FolderFilesTransportTests {
    private func client() -> LiveGatewayClient {
        let cfg = URLSessionConfiguration.ephemeral
        cfg.protocolClasses = [PathStub.self]
        return LiveGatewayClient(baseURL: URL(string: "https://gateway.example")!, token: "t", session: URLSession(configuration: cfg))
    }

    @Test func theFolderIsReadThroughARunAndItsFilesDownloadFromIt() async throws {
        PathStub.seen = []
        PathStub.answers = [
            "/api/gateway/sessions/s1/artifacts": (200, #"{"items": []}"#),
            "/api/gateway/runs/r9/workspace": (200, #"{"kind": "session", "exists": true}"#),
            "/api/gateway/runs/r9/workspace/files": (200, #"{"entries": [{"name": "a.svg", "path": "a.svg", "type": "file", "size_bytes": 5}], "truncated": true}"#),
            "/api/gateway/runs/r9/workspace/content": (200, "<svg>"),
        ]
        let files = try await client().sessionFiles(sessionId: "s1", folderRunId: "r9")
        #expect(files.files.map(\.folderPath) == ["a.svg"])
        #expect(files.folderTruncated)
        #expect(PathStub.seen.contains("/api/gateway/runs/r9/workspace/files?recursive=true&limit=500"))
        let data = try await client().fileData(files.files[0])
        #expect(String(decoding: data, as: UTF8.self) == "<svg>")
        #expect(PathStub.seen.last == "/api/gateway/runs/r9/workspace/content?path=a.svg")
    }

    @Test func noFolderYetIsNoFilesNotAFailure() async throws {
        PathStub.seen = []
        PathStub.answers = ["/api/gateway/sessions/s1/artifacts": (200, #"{"items": []}"#)]   // the folder: 404
        let files = try await client().sessionFiles(sessionId: "s1", folderRunId: "r9")
        #expect(files.files.isEmpty)
    }

    private static let oneImage = #"{"items": [{"artifact_id": "img1", "run_id": "r1", "content_type": "image/png", "tags": {"kind": "generated_media"}}]}"#

    @Test func aRefusedFolderLeavesTheOtherFilesShown() async throws {
        for status in [403, 409] {
            PathStub.answers = [
                "/api/gateway/sessions/s1/artifacts": (200, Self.oneImage),
                "/api/gateway/runs/r9/workspace": (200, #"{"kind": "session", "exists": true}"#),
                "/api/gateway/runs/r9/workspace/files": (status, #"{"detail": "no"}"#),
            ]
            let files = try await client().sessionFiles(sessionId: "s1", folderRunId: "r9")
            #expect(files.files.map(\.id) == ["img1"], "status \(status)")
        }
    }

    @Test func aFolderOfThePersonsOwnIsNotListed() async throws {
        PathStub.seen = []
        PathStub.answers = [
            "/api/gateway/sessions/s1/artifacts": (200, Self.oneImage),
            "/api/gateway/runs/r9/workspace": (200, #"{"kind": "launch_folder", "exists": true}"#),
            "/api/gateway/runs/r9/workspace/files": (200, #"{"entries": [{"name": "a.txt", "path": "a.txt", "type": "file"}]}"#),
        ]
        let files = try await client().sessionFiles(sessionId: "s1", folderRunId: "r9")
        #expect(files.files.map(\.id) == ["img1"])
        #expect(!PathStub.seen.contains { $0.hasPrefix("/api/gateway/runs/r9/workspace/files") })
    }
}
