import SwiftUI
import AssistantKit

/// Each connector follows one run's recorded sequence; separate agents have no invented edges.
struct CycleGraphView: View {
    let activity: RunActivity
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            if !activity.cycleLanes.isEmpty {
                ForEach(Array(activity.cycleLanes.enumerated()), id: \.element.id) { laneIndex, lane in
                    VStack(alignment: .leading, spacing: 12) {
                        if activity.cycleLanes.count > 1 {
                            Text("Agent \(laneIndex + 1)").font(.subheadline.weight(.semibold)).foregroundStyle(PhoneTheme.ink)
                        }
                        VStack(spacing: 0) {
                            ForEach(Array(lane.cycles.enumerated()), id: \.element.id) { index, cycle in
                                HStack(alignment: .top, spacing: 12) {
                                    VStack(spacing: 0) {
                                        Text(cycle.model.cycleOrdinal.map(String.init) ?? "•").font(.caption.weight(.semibold)).monospacedDigit()
                                            .foregroundStyle(PhoneTheme.mint).frame(width: 28, height: 28)
                                            .background(PhoneTheme.mint.opacity(0.12), in: Circle())
                                            .overlay(Circle().stroke(PhoneTheme.mint.opacity(0.35)))
                                        if index < lane.cycles.count - 1 {
                                            Rectangle().fill(PhoneTheme.mint.opacity(0.25)).frame(width: 1).frame(maxHeight: .infinity)
                                        }
                                    }.padding(.top, 17)
                                    VStack(alignment: .leading, spacing: 3) {
                                        ActivityEventRow(item: cycle.model, titleOverride: cycle.model.cycleOrdinal.map { "Cycle \($0)" } ?? "Cycle")
                                        if !cycle.tools.isEmpty || !cycle.approvals.isEmpty {
                                            HStack(spacing: 12) {
                                                if !cycle.tools.isEmpty {
                                                    Label("\(cycle.tools.count) \(cycle.tools.count == 1 ? "tool call" : "tool calls")", systemImage: "wrench.and.screwdriver").foregroundStyle(PhoneTheme.tool)
                                                }
                                                if !cycle.approvals.isEmpty {
                                                    Label("\(cycle.approvals.count) \(cycle.approvals.count == 1 ? "approval" : "approvals")", systemImage: "hand.raised").foregroundStyle(PhoneTheme.approval)
                                                }
                                            }.font(.caption).padding(.bottom, 9)
                                            if !cycle.tools.isEmpty {
                                                Text(cycle.tools.map(\.title).joined(separator: " · ")).font(.caption).foregroundStyle(PhoneTheme.secondary).padding(.bottom, 5)
                                            }
                                        }
                                        ForEach(cycle.approvals) { ActivityEventRow(item: $0) }
                                    }.padding(.horizontal, 12).padding(.vertical, 4)
                                        .background(PhoneTheme.surface, in: RoundedRectangle(cornerRadius: 16))
                                        .padding(.bottom, index < lane.cycles.count - 1 ? 14 : 0)
                                }.fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }
                }
                Text("Tools and approvals are grouped by their preceding cycle in the same agent run.")
                    .font(.caption2).foregroundStyle(PhoneTheme.secondary)
            }
            let auxiliary = activity.items.filter { $0.kind == .model && !$0.isAgentCycle }
            if !auxiliary.isEmpty {
                if activity.cycleCount > 0 {
                    DisclosureGroup("Routing & generation") { ForEach(auxiliary) { ActivityEventRow(item: $0) } }
                        .font(.subheadline).tint(PhoneTheme.secondary)
                } else { ForEach(auxiliary) { ActivityEventRow(item: $0) } }
            }
            let outsideIDs = Set((activity.toolsOutsideRecordedCycles + activity.approvalsOutsideRecordedCycles).map(\.id))
            let outside = activity.items.filter { outsideIDs.contains($0.id) }
            if !outside.isEmpty {
                DisclosureGroup("Outside recorded cycles") {
                    Text("Earlier cycle details may be unavailable in this history.").font(.caption).foregroundStyle(PhoneTheme.secondary)
                    ForEach(outside) { ActivityEventRow(item: $0) }
                }.font(.subheadline).tint(PhoneTheme.secondary)
            }
            let failures = activity.items.filter { $0.kind == .failure }
            ForEach(failures) { ActivityEventRow(item: $0) }
        }
    }
}
