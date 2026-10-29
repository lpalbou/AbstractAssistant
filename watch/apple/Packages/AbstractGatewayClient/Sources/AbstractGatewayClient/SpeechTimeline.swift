import Foundation

/// Where each received speech segment plays on the audio clock (operator 2026-10-29: the watch cut
/// the voice for 2–4 s between segments while the gateway sent them with no gap). A segment is
/// booked the moment it arrives: exactly where the previous one ends, or at once when the voice has
/// already run dry (a late segment). Nothing waits for a "finished" callback to start the next.
/// Times are in frames of the player's format; pure, so it is tested here.
public struct SpeechTimeline: Sendable, Equatable {
    public struct Booking: Sendable, Equatable {
        /// Where the segment starts on the player's clock.
        public let start: Int64
        public let frames: Int64
        /// Silence before it: 0 when it follows the previous segment; how late it came otherwise.
        public let gap: Int64
        public var end: Int64 { start + frames }
    }

    public let sampleRate: Double
    /// Speech queued before the first start (a first piece alone would break the voice after it).
    public let startBuffer: Double
    public private(set) var bookings: [Booking] = []
    /// Frames received but not booked yet (before the first start).
    public private(set) var waiting: [Int64] = []
    public private(set) var started = false

    public init(sampleRate: Double, startBuffer: Double = 1.5) {
        self.sampleRate = sampleRate
        self.startBuffer = startBuffer
    }

    /// The end of what is booked.
    public var bookedEnd: Int64 { bookings.last?.end ?? 0 }

    /// A segment arrived (`rendered`: where the player's clock is now). Returns the bookings to make
    /// now, in order: none while the first start waits for `startBuffer` (unless `streamDone`).
    public mutating func receive(frames: Int64, rendered: Int64, streamDone: Bool = false) -> [Booking] {
        waiting.append(max(0, frames))
        return flush(rendered: rendered, streamDone: streamDone)
    }

    /// The stream ended: whatever waits for the first start is booked now.
    public mutating func finish(rendered: Int64) -> [Booking] { flush(rendered: rendered, streamDone: true) }

    private mutating func flush(rendered: Int64, streamDone: Bool) -> [Booking] {
        if !started {
            let queued = Double(waiting.reduce(0, +)) / sampleRate
            guard queued >= startBuffer || (streamDone && !waiting.isEmpty) else { return [] }
            started = true
        }
        var out: [Booking] = []
        for frames in waiting {
            let end = bookedEnd
            let start = max(end, rendered)          // back to back; a late segment starts at once
            let booking = Booking(start: start, frames: frames, gap: bookings.isEmpty ? 0 : start - end)
            bookings.append(booking)
            out.append(booking)
        }
        waiting.removeAll()
        return out
    }

    /// The largest silence between two booked segments, in milliseconds.
    public var maxGapMilliseconds: Double {
        Double(bookings.map(\.gap).max() ?? 0) / sampleRate * 1000
    }

    /// The segment playing at `rendered` (its index), and how far into it, in frames.
    public func segment(at rendered: Int64) -> (index: Int, offset: Int64)? {
        guard let i = bookings.lastIndex(where: { $0.start <= rendered }) else { return nil }
        let b = bookings[i]
        return rendered < b.end ? (i, rendered - b.start) : nil
    }
}
