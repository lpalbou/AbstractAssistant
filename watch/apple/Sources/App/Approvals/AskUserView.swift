import AbstractGatewayClient
import SwiftUI

struct AskUserView: View {
    let wait: Wait
    @EnvironmentObject private var model: AppModel
    @State private var freeText = ""
    @State private var sending = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 6) {
                Text("\(wait.workflow ?? "The run") asks").font(.rounded(.headline)).foregroundStyle(Theme.text)
                Text(wait.prompt ?? "").font(.rounded(.footnote)).foregroundStyle(Theme.text2)
                ForEach(Array((wait.choices ?? []).enumerated()), id: \.offset) { i, choice in
                    Button(choice) { send(choice) }
                        .buttonStyle(FilledButtonStyle(fill: i == 0 ? Theme.indigoButton : Theme.neutralButton,
                                                       foreground: i == 0 ? Theme.text : Theme.text2))
                        .font(.rounded(.footnote, weight: .semibold))
                        .lineLimit(2).minimumScaleFactor(0.8)
                }
                .disabled(sending)
                if wait.allowFreeText ?? true {
                    // watchOS offers dictation and Scribble for a TextField.
                    TextField("or dictate another answer", text: $freeText)
                        .font(.rounded(.footnote))
                        .onSubmit { if !freeText.isEmpty { send(freeText) } }
                }
                Footnote(text: "run \(wait.runId.prefix(6)) · the run waits until you answer", mono: true)
            }
        }
        .screen("Question")
    }

    private func send(_ text: String) {
        sending = true
        Task {
            let ok = await model.answer(wait, with: .respond(text))
            sending = false
            if ok { model.markDecided(wait); model.path.removeLast() }
        }
    }
}
