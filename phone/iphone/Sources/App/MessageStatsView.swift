import SwiftUI

/// One optional, answer-owned line. Missing measurements stay absent rather than becoming zero.
struct MessageStatsView: View {
    var wallTimeSeconds: Double? = nil
    var inputTokens: Int? = nil
    var outputTokens: Int? = nil
    var totalTokens: Int? = nil
    var toolCalls: Int? = nil

    private var duration: Double? { wallTimeSeconds.flatMap { $0.isFinite && $0 >= 0 ? $0 : nil } }
    private func count(_ value: Int?) -> Int? { value.flatMap { $0 >= 0 ? $0 : nil } }
    private func compact(_ value: Int) -> String { value.formatted(.number.notation(.compactName).precision(.fractionLength(0...1))) }
    private struct Metric: Identifiable {
        var icon: String
        var value: String
        var id: String { icon }
    }
    private var metrics: [Metric] {
        var values: [Metric] = []
        if let duration { values.append(.init(icon: "clock", value: duration.formatted(.number.precision(.fractionLength(0...1))) + " s")) }
        let input = count(inputTokens), output = count(outputTokens)
        if input != nil || output != nil {
            values.append(.init(icon: "number", value: [input.map { compact($0) + " in" }, output.map { compact($0) + " out" }].compactMap { $0 }.joined(separator: " / ")))
        } else if let total = count(totalTokens) { values.append(.init(icon: "number", value: compact(total) + " tokens")) }
        if let tools = count(toolCalls), tools > 0 { values.append(.init(icon: "wrench.and.screwdriver", value: "\(tools) " + (tools == 1 ? "call" : "calls"))) }
        return values
    }
    private var spoken: String {
        var values: [String] = []
        if let duration { values.append("Elapsed time: \(duration.formatted(.number.precision(.fractionLength(0...1)))) seconds") }
        if let input = count(inputTokens) { values.append("Input: \(input.formatted()) tokens") }
        if let output = count(outputTokens) { values.append("Output: \(output.formatted()) tokens") }
        if count(inputTokens) == nil && count(outputTokens) == nil, let total = count(totalTokens) { values.append("Total: \(total.formatted()) tokens") }
        if let tools = count(toolCalls) { values.append("\(tools) tool " + (tools == 1 ? "call" : "calls")) }
        return values.joined(separator: ", ")
    }
    var body: some View {
        if !metrics.isEmpty {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .firstTextBaseline, spacing: 14) {
                    ForEach(metrics) { metric in metricView(metric).fixedSize() }
                }
                VStack(alignment: .leading, spacing: 5) {
                    ForEach(metrics) { metric in metricView(metric) }
                }
            }
            .font(.caption2).foregroundStyle(PhoneTheme.secondary)
            .accessibilityElement(children: .ignore).accessibilityLabel(spoken)
            .accessibilityIdentifier("message.stats")
        }
    }
    private func metricView(_ metric: Metric) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 5) {
            Image(systemName: metric.icon).foregroundStyle(metric.icon == "wrench.and.screwdriver" ? PhoneTheme.tool : PhoneTheme.secondary)
            Text(metric.value).fixedSize(horizontal: false, vertical: true)
        }
    }
}
