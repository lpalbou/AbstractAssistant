import AbstractGatewayClient
import SwiftUI
import WatchKit

/// Below the orb while it works: the question, how long it has worked (and, after an Accept all,
/// the shield that takes it back), then its steps, newest first, on a thin rail: thinking, each
/// tool with what it is about, media being made, a wait on you.
struct ActivityPanel: View {
    @ObservedObject var activity: RunActivity
    let prompt: String
    /// Opens what the run waits on (an approval, a question).
    var openWait: (() -> Void)?
    @EnvironmentObject private var model: AppModel

    private static let shown = 12

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if !prompt.isEmpty {
                Text(prompt).font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text2).lineLimit(3)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            HStack(spacing: 6) {
                TimelineView(.periodic(from: .now, by: 1)) { ctx in
                    Text("Working · " + Clock.text(ctx.date.timeIntervalSince(activity.since)))
                        .font(.rounded(.caption2)).foregroundStyle(Theme.muted).monospacedDigit()
                }
                Spacer(minLength: 4)
            }
            let steps = Array(activity.log.steps.reversed())
            if steps.isEmpty {
                ActivityRow(step: nil, last: true)
            }
            TimelineView(.periodic(from: .now, by: 1)) { ctx in
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(steps.prefix(Self.shown).enumerated()), id: \.element.id) { i, step in
                        if step.state == .waiting, let openWait {
                            Button(action: openWait) { ActivityRow(step: step, last: i == min(steps.count, Self.shown) - 1, now: ctx.date) }
                                .buttonStyle(.tap)
                        } else {
                            ActivityRow(step: step, last: i == min(steps.count, Self.shown) - 1, now: ctx.date)
                        }
                    }
                }
            }
            if steps.count > Self.shown {
                Text("\(steps.count - Self.shown) earlier steps").font(.rounded(.caption2)).foregroundStyle(Theme.muted).padding(.leading, 34)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("activity.panel")
    }
}

/// One step: its symbol in a small disc on the rail (a turning arc while it runs), what it does,
/// what it is about, and how long it took.
struct ActivityRow: View {
    /// nil: the run has not shown a step yet ("Starting").
    let step: ActivityLog.Step?
    var last = false
    var now = Date()
    @EnvironmentObject private var model: AppModel

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            VStack(spacing: 0) {
                disc
                if !last { Rectangle().fill(Theme.line).frame(width: 1.5).frame(maxHeight: .infinity) }
            }
            .frame(width: 26)
            VStack(alignment: .leading, spacing: 1) {
                HStack(spacing: 4) {
                    Text(step?.title ?? "Starting").font(.rounded(.footnote, weight: .semibold))
                        .foregroundStyle(step?.state == .done ? Theme.text2 : Theme.text).lineLimit(2)
                    Spacer(minLength: 2)
                    if let d = step?.duration(now: now) {
                        Text(d).font(.rounded(.caption2)).foregroundStyle(Theme.muted).monospacedDigit()
                    }
                }
                if step?.state == .waiting {
                    Text("Needs you · tap to decide").font(.rounded(.caption2, weight: .semibold)).foregroundStyle(Theme.amber)
                } else if case .failed(let why)? = step?.state {
                    Text(why ?? "Didn't work").font(.rounded(.caption2)).foregroundStyle(Theme.red).lineLimit(2)
                }
                if let detail = step?.detail {
                    Text(detail).font(.rounded(.caption2)).foregroundStyle(Theme.muted).lineLimit(2)
                }
            }
            .padding(.bottom, last ? 0 : 8)
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(spoken)
        .accessibilityIdentifier(step.map { "activity.step.\($0.toolName ?? "\($0.kind)")" } ?? "activity.starting")
    }

    /// "Searching the web, what fills a disk, done, 1 s."
    private var spoken: String {
        guard let step else { return "Starting" }
        let state: String
        switch step.state {
        case .running: state = "now"
        case .waiting: state = "needs you, tap to decide"
        case .done: state = "done"
        case .failed(let why): state = "didn't work" + (why.map { ", " + $0 } ?? "")
        }
        return [step.title, step.detail, state, step.duration(now: now)].compactMap { $0 }.joined(separator: ", ")
    }

    private var tint: Color {
        switch step?.state {
        case .waiting: Theme.amber
        case .failed: Theme.red
        case .done: Theme.muted
        default: Theme.cyan
        }
    }

    private var disc: some View {
        let symbol = step?.symbol(toolset: step?.toolName.flatMap { model.tools[$0]?.toolset }) ?? "sparkles"
        return ZStack {
            Circle().fill(tint.opacity(step?.state == .done ? 0.12 : 0.2))
            Image(systemName: symbol).font(.system(size: 11, weight: .semibold)).foregroundStyle(tint)
            if step == nil || step?.state == .running { RunningArc(color: tint) }
        }
        .frame(width: 24, height: 24)
    }
}

/// A short arc turning around a running step's disc.
private struct RunningArc: View {
    let color: Color
    var body: some View {
        TimelineView(.animation(minimumInterval: 1 / 20)) { ctx in
            let a = ctx.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 1.2) / 1.2 * 360
            Circle().trim(from: 0, to: 0.28)
                .stroke(color, style: StrokeStyle(lineWidth: 1.6, lineCap: .round))
                .rotationEffect(.degrees(a))
        }
        .padding(-2)
    }
}

/// On the orb while it works, after an Accept all: the watch approves those tools for you in this
/// conversation. One tap and they ask again, from the very next call.
struct TrustShield: View {
    @EnvironmentObject private var model: AppModel
    var body: some View {
        Button {
            model.revokeTrust()
            WKInterfaceDevice.current().play(.click)
        } label: {
            Image(systemName: "checkmark.shield.fill")
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(Theme.amber)
                .offset(GlassIcon.optical("checkmark.shield.fill"))
                .frame(width: 35, height: 35)
                .background(Theme.amber.opacity(0.18), in: Circle())
                .overlay(Circle().strokeBorder(Theme.amber.opacity(0.6), lineWidth: 1))
                .frame(width: 44, height: 44)                    // the touch target
                .contentShape(Circle())
        }
        .buttonStyle(GlassPress())
        .accessibilityLabel("Allowed in this conversation: \(model.sessionTrust.count) tools. Ask again")
        .accessibilityIdentifier("activity.trust")
    }
}

/// A finished answer's work, opened from its card: every step in order.
struct ActivityDetailView: View {
    let runId: String
    @EnvironmentObject private var model: AppModel
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                if let work = model.activities[runId] {
                    Text(work.summary).font(.rounded(.caption2)).foregroundStyle(Theme.muted).padding(.bottom, 8)
                    ForEach(Array(work.steps.enumerated()), id: \.element.id) { i, step in
                        ActivityRow(step: step, last: i == work.steps.count - 1, now: work.ended)
                    }
                }
            }
            .padding(.horizontal, 4)
        }
        .screen("Work")
    }
}

/// A finished run's work, kept on the watch while the app runs (the answer card opens it).
struct FinishedWork: Hashable {
    let steps: [ActivityLog.Step]
    let started: Date
    let ended: Date
    /// "6 steps · 1:24"
    var summary: String {
        let n = steps.count
        return "\(n) step\(n == 1 ? "" : "s") · " + Clock.text(ended.timeIntervalSince(started))
    }
}

/// Under a finished answer followed on this watch: how it worked ("6 steps · 1:24"), opening each step.
struct WorkLink: View {
    let runId: String
    @EnvironmentObject private var model: AppModel
    var body: some View {
        if let work = model.activities[runId] {
            NavigationLink(value: Route.activity(runId)) {
                HStack(spacing: 5) {
                    Image(systemName: "list.bullet.below.rectangle").font(.system(size: 11, weight: .semibold))
                    Text(work.summary).font(.rounded(.caption2, weight: .semibold)).monospacedDigit()
                    Image(systemName: "chevron.right").font(.system(size: 9, weight: .bold))
                }
                .foregroundStyle(Theme.cyan)
                .padding(.horizontal, 10).padding(.vertical, 6)
                .background(Theme.cyan.opacity(0.12), in: Capsule())
            }
            .buttonStyle(.tap)
            .accessibilityLabel("How it worked: \(work.summary)")
            .accessibilityIdentifier("work.link")
        }
    }
}

/// "1:05": minutes and seconds of a run so far.
enum Clock {
    static func text(_ s: Double) -> String { String(format: "%d:%02d", Int(max(0, s)) / 60, Int(max(0, s)) % 60) }
}
