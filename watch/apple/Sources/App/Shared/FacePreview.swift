#if DEBUG
import SwiftUI

/// `--screen face`: the Assistant complication on each slot of a watch face, at their sizes, with
/// and without something waiting for you (the simulator cannot screenshot a real face).
struct FacePreview: View {
    var body: some View {
        ScrollView {
            VStack(spacing: 10) {
                HStack(spacing: 10) {
                    circular(FaceSnapshot.read())
                    circular(FaceSnapshot())
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
                FaceOrb(needYou: 2, showsCount: false).frame(width: 30, height: 30)
            }
            .padding(.top, 40)
        }
        .background(Color.black)
    }

    private func circular(_ face: FaceSnapshot) -> some View {
        ZStack {
            Circle().fill(.white.opacity(0.1))
            FaceOrb(needYou: face.needYou)
        }
        .frame(width: 54, height: 54)
    }
}
#endif
