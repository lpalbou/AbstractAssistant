import AbstractGatewayClient
import SwiftUI

struct AskUserView: View {
    let wait: Wait
    @EnvironmentObject private var model: AppModel
    @State private var freeText = ""
    @State private var sending = false

    var body: some View {
        FitScroll {
            VStack(alignment: .leading, spacing: 6) {
                Text(wait.headline).font(.rounded(.headline)).foregroundStyle(Theme.text)
                Spacer(minLength: 8)
                ForEach(Array((wait.choices ?? []).enumerated()), id: \.offset) { i, choice in
                    Button(choice) { send(choice) }
                        .buttonStyle(FilledButtonStyle(fill: i == 0 ? Theme.indigoButton : Theme.neutralButton,
                                                       foreground: i == 0 ? Theme.text : Theme.text2,
                                                       font: .rounded(.footnote, weight: .semibold), lines: 2))
                }
                .disabled(sending)
                if wait.allowFreeText ?? true {
                    // watchOS offers dictation and Scribble for a TextField.
                    TextField("Other answer", text: $freeText)
                        .font(.rounded(.footnote))
                        .onSubmit { if !freeText.isEmpty { send(freeText) } }
                }
            }
            .padding(.horizontal, 4)
        }
        .screen("")
    }

    private func send(_ text: String) {
        sending = true
        Task {
            let ok = await model.answer(wait, with: .respond(text))
            sending = false
            if ok || !model.waits.contains(where: { $0.id == wait.id }) { model.markDecided(wait); model.path.removeLast() }
        }
    }
}
