import AbstractGatewayClient
import SwiftUI

/// Your automations, like your conversations: a name, when it runs, how many new results.
struct AutomationsView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        List {
            // A new automation (as Sessions starts a new conversation).
            Button { model.path.append(.newAutomation) } label: {
                Label("New automation", systemImage: "plus")
                    .font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.cyan)
            }
            if model.automations.isEmpty {
                if model.lastRefresh == nil && model.automationsError == nil {
                    ProgressView().frame(maxWidth: .infinity)
                } else {
                    Text(model.automationsError == nil ? "No automations yet" : "Can't load automations")
                        .font(.rounded(.footnote)).foregroundStyle(Theme.muted)
                }
            }
            ForEach(model.automations) { a in
                NavigationLink(value: Route.automation(a)) {
                    VStack(alignment: .leading, spacing: 2) {
                        HStack(spacing: 5) {
                            if a.lastOccurrence?.status == "failed" { StatusDot(color: Theme.red) }
                            Text(a.name ?? "Automation").font(.rounded(.footnote, weight: .semibold))
                                .foregroundStyle(Theme.text).lineLimit(2)
                            Spacer(minLength: 2)
                            if a.currentOccurrence != nil { ProgressView().frame(width: 18, height: 18).accessibilityLabel("Running") }
                            else if let n = a.attention?.unseenCount, n > 0 { Pill(text: "\(n)", color: Theme.amber) }
                        }
                        ScheduleLine(automation: a)
                    }
                    .padding(.vertical, 2)
                }
            }
        }
        .navigationTitle("Automations")
        .containerBackground(Theme.ground, for: .navigation)
        .refreshable { await model.refresh() }
        // While one runs, its row is read again every 5 s: the spinner goes when it is done.
        .task {
            #if DEBUG
            if ProcessInfo.processInfo.arguments.contains("--run-first"), model.client.isMock {
                while model.automations.isEmpty { try? await Task.sleep(for: .milliseconds(200)) }
            }
            if ProcessInfo.processInfo.arguments.contains("--run-first"), model.client.isMock, let a = model.automations.first {
                try? await model.client.runAutomationNow(id: a.id); await model.refresh()
            }
            #endif
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(5))
                for a in model.automations where a.currentOccurrence != nil {
                    if let fresh = try? await model.client.automation(id: a.id) { model.replaceAutomation(fresh) }
                }
            }
        }
    }
}
