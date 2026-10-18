import Foundation

public enum LedgerStreamEvent: Sendable {
    case record(cursor: Int, record: LedgerRecord)
    case done
}
public enum LedgerStreamError: Error, Sendable {
    case malformedFrame, bufferOverflow, invalidCursor
}

/// SSE framing only: model token/reasoning deltas never enter the activity projection.
struct LedgerSSEParser {
    private var lineBytes = Data()
    private var event = ""
    private var data: [String] = []
    private var frameBytes = 0
    mutating func feed(_ chunk: Data) throws -> [LedgerStreamEvent] {
        var events: [LedgerStreamEvent] = []
        for byte in chunk { if let value = try feed(byte: byte) { events.append(value) } }
        return events
    }
    mutating func feed(byte: UInt8) throws -> LedgerStreamEvent? {
        if byte != 10 {
            lineBytes.append(byte)
            guard lineBytes.count + frameBytes <= 1_048_576 else { throw LedgerStreamError.malformedFrame }
            return nil
        }
        if lineBytes.last == 13 { lineBytes.removeLast() }
        guard let line = String(data: lineBytes, encoding: .utf8) else { throw LedgerStreamError.malformedFrame }
        lineBytes.removeAll(keepingCapacity: true)
        if line.isEmpty {
            defer { event = ""; data = []; frameBytes = 0 }
            if event == "done" { return .done }
            guard event == "step" else { return nil }
            struct Frame: Decodable { var cursor: Int; var record: LedgerRecord }
            guard let frame = try? JSONDecoder().decode(Frame.self, from: Data(data.joined(separator: "\n").utf8)),
                  frame.cursor > 0, frame.record.stepId?.isEmpty == false, frame.record.status?.isEmpty == false else { throw LedgerStreamError.malformedFrame }
            return .record(cursor: frame.cursor, record: frame.record)
        }
        if line.hasPrefix(":") { return nil }
        let parts = line.split(separator: ":", maxSplits: 1, omittingEmptySubsequences: false)
        let field = String(parts[0])
        var value = parts.count > 1 ? String(parts[1]) : ""
        if value.hasPrefix(" ") { value.removeFirst() }
        if field == "event" { event = value }
        if field == "data" { data.append(value); frameBytes += line.utf8.count }
        return nil
    }
}

func yieldLedger(_ event: LedgerStreamEvent, to continuation: AsyncThrowingStream<LedgerStreamEvent, Error>.Continuation) throws {
    switch continuation.yield(event) {
    case .enqueued: break
    case .dropped: throw LedgerStreamError.bufferOverflow
    case .terminated: throw CancellationError()
    @unknown default: throw LedgerStreamError.bufferOverflow
    }
}

func pollLedger(client: any GatewayClient, runID: String, after: Int,
                continuation: AsyncThrowingStream<LedgerStreamEvent, Error>.Continuation) async throws {
    var cursor = after
    while !Task.isCancelled {
        let page = try await client.ledger(runId: runID, after: cursor)
        let next = page.nextAfter ?? cursor + page.items.count
        guard next == cursor + page.items.count else { throw LedgerStreamError.invalidCursor }
        for record in page.items {
            cursor += 1
            try yieldLedger(.record(cursor: cursor, record: record), to: continuation)
        }
        if page.items.count >= 200 { continue }
        let run = try await client.run(id: runID)
        if run.isTerminal {
            if !page.items.isEmpty { continue } // final durable drain before done
            try yieldLedger(.done, to: continuation); return
        }
        try await Task.sleep(for: .seconds(1))
    }
    throw CancellationError()
}

public extension GatewayClient {
    func childRuns(ofRunID: String) async throws -> [RunSummary] { [] }
    nonisolated func ledgerEvents(runID: String, after: Int) -> AsyncThrowingStream<LedgerStreamEvent, Error> {
        AsyncThrowingStream(bufferingPolicy: .bufferingOldest(128)) { continuation in
            let task = Task {
                do { try await pollLedger(client: self, runID: runID, after: after, continuation: continuation); continuation.finish() }
                catch { continuation.finish(throwing: error) }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }
    func entityLedger(name: String, runID: String, after: Int) async throws -> LedgerPage {
        throw PhoneAttachmentError.unsupported
    }
}

/// No redirected request may carry gateway credentials to another destination.
final class LedgerRedirectGuard: NSObject, URLSessionTaskDelegate, Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping @Sendable (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}
