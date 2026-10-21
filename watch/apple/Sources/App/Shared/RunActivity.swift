import AbstractGatewayClient
import SwiftUI

/// What the orb shows of the work at time t: the pulses still travelling, and the tools running now
/// (each one a satellite).
struct OrbWork {
    enum Tone { case tool, thinking, media, failure }
    struct Pulse { let age: Double; let strength: Double; let tone: Tone }
    var pulses: [Pulse] = []
    var satellites = 0
    static let none = OrbWork()
}

/// Follows a question's run while it works: its steps (thinking, each tool call, media being made,
/// a wait on you), read from the step log of the run doing the work. The Assistant's run starts its
/// agent as a child run (which may start others): each tick reads the root's summary, walks down to
/// the run not waiting on a child, and reads that run's new records. A run that handed off to a
/// child is not read again (what it writes after is plumbing and the final answer, the heaviest
/// records of all).
@MainActor
final class RunActivity: ObservableObject {
    @Published private(set) var log = ActivityLog()
    @Published private(set) var since = Date()
    @Published private(set) var ended: Date?
    @Published private(set) var runId: String?

    private var task: Task<Void, Never>?
    private var cursors: [String: Int] = [:]
    private var delegated: Set<String> = []
    /// The run read last: when the work moves to another run, it is read once more (its last steps).
    private var lastFocus: String?
    /// Each run's `updated_at` when its records were last read (unchanged: nothing new to read).
    private var seen: [String: String] = [:]
    /// The watch's screen is off or the app is not in front: no reads (the answer still arrives).
    var paused = false
    private var pulses: [(t: Double, strength: Double, tone: OrbWork.Tone)] = []

    var isFollowing: Bool { task != nil }

    func start(runId id: String, client: any GatewayClient) {
        reset()
        runId = id; since = Date()
        let interval: Duration = client.isMock ? .milliseconds(150) : .seconds(1)
        task = Task { [weak self] in
            var failures = 0
            while !Task.isCancelled {
                guard let self else { return }
                if !self.paused {
                    do { try await self.tick(root: id, client: client); failures = 0 }
                    catch {
                        failures += 1
                        if failures > 20 { if self.runId == id { self.task = nil }; return }   // a later resume starts it again
                    }
                }
                try? await Task.sleep(for: interval)
            }
        }
    }

    /// Stops reading (the run ended); `finish` then reads its last steps.
    func stopLoop() { task?.cancel(); task = nil }

    /// The run ended: one last read (its last steps may have landed after the previous one), then
    /// the steps still open end with it. Returns its work, nil when this follower moved on.
    func finish(success: Bool, client: any GatewayClient) async -> FinishedWork? {
        guard let id = runId else { return nil }
        task?.cancel(); task = nil
        let end = Date()
        try? await tick(root: id, client: client, final: true)
        guard runId == id else { return nil }
        ended = end
        log.close(at: end, success: success)
        return log.steps.isEmpty ? nil : FinishedWork(steps: log.steps, started: since, ended: end)
    }

    func reset() {
        task?.cancel(); task = nil
        log = ActivityLog(); cursors = [:]; delegated = []; pulses = []; ended = nil; runId = nil; lastFocus = nil; seen = [:]
    }

    private func tick(root: String, client: any GatewayClient, final: Bool = false) async throws {
        var focus = root
        var summary = try await client.run(id: root)
        var depth = 0
        while let child = summary.waitingOnChild, depth < 4 {
            delegated.insert(focus)
            focus = child
            summary = try await client.run(id: child)
            depth += 1
        }
        guard runId == root else { return }
        // The work moved on (or ended): the run read last gets one more read, for its last steps.
        if let last = lastFocus, last != focus || final {
            try await read(last, root: root, client: client)
        }
        lastFocus = focus
        guard !delegated.contains(focus) || depth == 4 else { return }
        // Nothing changed in that run since its last read: nothing to read (the gateway loads a
        // run's whole step log to answer any page of it).
        if !final, let at = summary.updatedAt, seen[focus] == at { return }
        try await read(focus, root: root, client: client)
        seen[focus] = summary.updatedAt
    }

    private func read(_ run: String, root: String, client: any GatewayClient) async throws {
        let from = cursors[run] ?? 0
        let page = try await client.activity(runId: run, after: from)
        guard runId == root else { return }
        cursors[run] = page.nextAfter ?? (from + page.items.count)
        guard !page.items.isEmpty else { return }
        var next = log
        let events = next.apply(page.items, runId: run)
        log = next
        // A run opened mid-way reads its past at once: only its newest steps pulse.
        pulse(page.items.count > 8 ? Array(events.suffix(2)) : events)
    }

    /// Each tool call starts a pulse (parallel calls a few tenths apart); new thinking a softer
    /// one; media being made a long, strong one; a tool that fails a short, sharp one.
    private func pulse(_ events: [ActivityLog.Event]) {
        let now = Date().timeIntervalSinceReferenceDate
        var tools = 0
        for e in events {
            switch e {
            case .tool:
                pulses.append((now + 0.18 * Double(tools), 1, .tool)); tools += 1
            case .thinking: pulses.append((now, 0.45, .thinking))
            case .media: pulses.append((now, 1.3, .media))
            case .finished(let ok): if !ok { pulses.append((now, 0.9, .failure)) }
            }
        }
        pulses.removeAll { now - $0.t > 3 }
    }

    func orb(at t: Double) -> OrbWork {
        OrbWork(pulses: pulses.compactMap { p in
                    let age = t - p.t
                    return age >= 0 && age < 1.6 ? .init(age: age, strength: p.strength, tone: p.tone) : nil
                },
                satellites: min(4, log.runningTools))
    }

    /// The status line under the orb: what it is doing now.
    var now: String? {
        guard let s = log.steps.last(where: { $0.state == .running || $0.state == .waiting }) else { return nil }
        return s.state == .waiting ? "Needs you" : s.title
    }
}

extension ActivityLog.Step {
    /// What the step does, in plain words ("Searching the web", "Making an image").
    var title: String {
        switch kind {
        case .thinking: return "Thinking"
        case .routing: return "Choosing how to answer"
        case .question: return "Has a question for you"
        case .tool(let name): return ToolWords.doing([name])
        case .media(let m):
            switch m {
            case "image": return "Making an image"
            case "voice": return "Recording a voice"
            case "video": return "Making a video"
            case "music": return "Making music"
            case "sound": return "Making a sound"
            default: return "Making \(m)"
            }
        }
    }

    func symbol(toolset: String?) -> String {
        switch kind {
        case .thinking: return "sparkles"
        case .routing: return "arrow.triangle.branch"
        case .question: return "questionmark.bubble"
        case .tool: return ToolGroup(id: toolset ?? "other", tools: []).symbol
        case .media(let m):
            switch m {
            case "image": return "photo"
            case "voice": return "waveform"
            case "video": return "film"
            case "music": return "music.note"
            default: return "speaker.wave.2"
            }
        }
    }

    /// "4 s", "1:12": how long it took, or has taken so far.
    func duration(now: Date) -> String? {
        guard let started else { return nil }
        let s = max(0, (ended ?? now).timeIntervalSince(started))
        if s < 1 { return state == .running ? nil : "<1 s" }
        return s < 60 ? "\(Int(s)) s" : String(format: "%d:%02d", Int(s) / 60, Int(s) % 60)
    }
}

/// What a tool call is doing, in plain words ("Searching the web", "Reading 4 web pages").
/// What tools are doing, as a person would say it.
enum ToolWords {
    static func doing(_ names: [String]) -> String {
        guard let first = names.first else { return "Working" }
        let n = names.filter { $0 == first }.count
        switch first {
        case "web_search", "skim_websearch": return "Searching the web"
        case "skim_url", "fetch_url", "render_url_html": return n > 1 ? "Reading \(n) web pages" : "Reading a web page"
        case "read_file", "skim_files": return n > 1 ? "Reading \(n) files" : "Reading a file"
        case "list_files", "search_files", "skim_folders": return "Looking through files"
        case "write_file", "edit_file": return "Writing a file"
        case "execute_command", "shell_exec": return "Running a command"
        case "send_email", "reply_email": return "Sending an email"
        case "read_email", "list_emails", "search_emails": return "Reading email"
        default:
            let w = first.replacingOccurrences(of: "_", with: " ")
            return "Using " + w
        }
    }
}
