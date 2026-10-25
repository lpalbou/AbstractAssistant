#if DEBUG
import SwiftUI

/// `--screen face`: the Assistant complication on each slot of a watch face, at their sizes, with
/// and without something waiting for you, and as a face in one tint draws it (the simulator
/// cannot screenshot a real face).
struct FacePreview: View {
    var body: some View {
        ScrollView {
            VStack(spacing: 10) {
                HStack(spacing: 10) {
                    circular(FaceSnapshot.read())
                    circular(FaceSnapshot())
                    circular(FaceSnapshot(newResults: 3))
                    circular(.sample)
                }
                FaceCard(date: Date(), face: .sample)
                    .frame(width: 180, height: 56).padding(4).background(.white.opacity(0.08), in: .rect(cornerRadius: 12))
                FaceCard(date: Date(), face: FaceSnapshot(nextName: "Morning digest", nextAt: Date().addingTimeInterval(5400), newResults: 3))
                    .frame(width: 180, height: 56).padding(4).background(.white.opacity(0.08), in: .rect(cornerRadius: 12))
                HStack(spacing: 6) {
                    Image(systemName: "circle.hexagongrid.fill")
                    FaceLine.text(.sample, at: Date())
                }
                .font(.footnote)
                FaceOrb(face: .sample, showsCount: false).frame(width: 30, height: 30)
                HStack(spacing: 10) {
                    circular(FaceSnapshot.read())
                    circular(FaceSnapshot(newResults: 3))
                    circular(.sample)
                    FaceCard(date: Date(), face: .sample).frame(width: 100, height: 54)
                }
                .environment(\.widgetRenderingMode, .accented)
                .accessibilityIdentifier("face.tinted")
            }
            .padding(.top, 40)
        }
        .background(Color.black)
    }

    private func circular(_ face: FaceSnapshot) -> some View {
        FaceOrb(face: face).frame(width: 54, height: 54)
    }
}
#endif
