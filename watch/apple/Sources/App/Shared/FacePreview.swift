#if DEBUG
import SwiftUI

/// `--screen face`: the Orb clock on each slot of a watch face, at their sizes, now and at ten past
/// ten, with and without something waiting for you (the simulator cannot screenshot a real face).
struct FacePreview: View {
    private let tenPastTen = Calendar.current.date(bySettingHour: 10, minute: 10, second: 0, of: Date()) ?? Date()
    private let quarterTo = Calendar.current.date(bySettingHour: 15, minute: 44, second: 0, of: Date()) ?? Date()

    var body: some View {
        ScrollView {
            VStack(spacing: 10) {
                HStack(spacing: 10) {
                    circular(Date(), FaceSnapshot.read())
                    circular(tenPastTen, FaceSnapshot())
                    circular(quarterTo, .sample)
                }
                OrbClockCard(date: Date(), face: .sample)
                    .frame(width: 180, height: 56).padding(4).background(.white.opacity(0.08), in: .rect(cornerRadius: 12))
                OrbClockCard(date: tenPastTen, face: FaceSnapshot(nextName: "Morning digest", nextAt: tenPastTen.addingTimeInterval(5400), newResults: 3))
                    .frame(width: 180, height: 56).padding(4).background(.white.opacity(0.08), in: .rect(cornerRadius: 12))
                HStack(spacing: 6) {
                    Image(systemName: "circle.hexagongrid.fill")
                    OrbClockLine.text(.sample, at: Date())
                }
                .font(.footnote)
                OrbClockDial(date: quarterTo, needYou: 2, showsCount: false).frame(width: 30, height: 30)
            }
            .padding(.top, 40)
        }
        .background(Color.black)
    }

    private func circular(_ date: Date, _ face: FaceSnapshot) -> some View {
        ZStack {
            Circle().fill(.white.opacity(0.1))
            OrbClockDial(date: date, needYou: face.needYou).padding(2)
        }
        .frame(width: 54, height: 54)
    }
}
#endif
