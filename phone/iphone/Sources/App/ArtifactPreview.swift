import SwiftUI
import ImageIO
@preconcurrency import QuickLook

/// Native zooming and document support, with controls that remain visible over the image.
struct ArtifactPreview: View {
    let url: URL
    var close: () -> Void
    @State private var previewImage: UIImage?
    @State private var loading = true
    private func decodeImage() -> UIImage? {
        guard let source = CGImageSourceCreateWithURL(url as CFURL, [kCGImageSourceShouldCache: false] as CFDictionary),
              let image = CGImageSourceCreateThumbnailAtIndex(source, 0, [kCGImageSourceCreateThumbnailFromImageAlways: true,
                  kCGImageSourceCreateThumbnailWithTransform: true, kCGImageSourceThumbnailMaxPixelSize: 4096] as CFDictionary) else { return nil }
        return UIImage(cgImage: image)
    }
    var body: some View {
        ZStack(alignment: .top) {
            Group {
                if loading { ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity) }
                else if let image = previewImage { ZoomableImage(image: image) }
                else { QuickLookSurface(url: url) }
            }.frame(maxWidth: .infinity, maxHeight: .infinity).ignoresSafeArea()
            HStack {
                ShareLink(item: url) { Image(systemName: "square.and.arrow.up").frame(width: 44, height: 44) }
                    .accessibilityLabel("Share file")
                Spacer()
                Button(action: close) { Image(systemName: "xmark").frame(width: 44, height: 44) }
                    .accessibilityLabel("Close preview").accessibilityIdentifier("media.preview.close")
            }
            .font(.body.weight(.semibold)).foregroundStyle(.white)
            .buttonStyle(.bordered).buttonBorderShape(.circle)
            .padding(.horizontal, 16).padding(.top, 8)
        }
        .background(.black).preferredColorScheme(.dark)
        .task(id: url) { previewImage = decodeImage(); loading = false }
    }
}

private struct QuickLookSurface: UIViewControllerRepresentable {
    let url: URL
    func makeCoordinator() -> Coordinator { Coordinator(url: url) }
    func makeUIViewController(context: Context) -> QLPreviewController {
        let preview = QLPreviewController()
        preview.dataSource = context.coordinator
        return preview
    }
    func updateUIViewController(_ controller: QLPreviewController, context: Context) {}
    @MainActor final class Coordinator: NSObject, QLPreviewControllerDataSource {
        let url: URL
        init(url: URL) { self.url = url }
        func numberOfPreviewItems(in controller: QLPreviewController) -> Int { 1 }
        func previewController(_ controller: QLPreviewController, previewItemAt index: Int) -> any QLPreviewItem { url as NSURL }
    }
}

private struct ZoomableImage: UIViewControllerRepresentable {
    let image: UIImage
    func makeUIViewController(context: Context) -> ImageCanvas { ImageCanvas(image: image) }
    func updateUIViewController(_ controller: ImageCanvas, context: Context) {}
}

private final class ImageCanvas: UIViewController, UIScrollViewDelegate {
    private let scroll = UIScrollView()
    private let imageView: UIImageView
    private var fittedSize = CGSize.zero
    init(image: UIImage) { imageView = UIImageView(image: image); super.init(nibName: nil, bundle: nil) }
    required init?(coder: NSCoder) { nil }
    override func viewDidLoad() {
        super.viewDidLoad(); view.backgroundColor = .black
        scroll.delegate = self; scroll.showsHorizontalScrollIndicator = false; scroll.showsVerticalScrollIndicator = false
        scroll.contentInsetAdjustmentBehavior = .never
        imageView.frame = CGRect(origin: .zero, size: imageView.image!.size)
        imageView.isAccessibilityElement = true; imageView.accessibilityLabel = "Image preview"; imageView.accessibilityIdentifier = "media.preview.image"
        scroll.addSubview(imageView); view.addSubview(scroll)
        let doubleTap = UITapGestureRecognizer(target: self, action: #selector(zoom)); doubleTap.numberOfTapsRequired = 2; scroll.addGestureRecognizer(doubleTap)
    }
    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews(); scroll.frame = view.bounds
        guard fittedSize != view.bounds.size, let image = imageView.image else { return }
        fittedSize = view.bounds.size
        let fit = min(view.bounds.width / image.size.width, view.bounds.height / image.size.height)
        scroll.minimumZoomScale = fit; scroll.maximumZoomScale = max(1, fit * 4)
        scroll.zoomScale = fit; scroll.contentSize = imageView.frame.size; centerImage()
    }
    func viewForZooming(in scrollView: UIScrollView) -> UIView? { imageView }
    func scrollViewDidZoom(_ scrollView: UIScrollView) { centerImage() }
    private func centerImage() {
        imageView.center = CGPoint(x: max(scroll.contentSize.width, scroll.bounds.width) / 2,
                                   y: max(scroll.contentSize.height, scroll.bounds.height) / 2)
    }
    @objc private func zoom(_ tap: UITapGestureRecognizer) {
        if scroll.zoomScale > scroll.minimumZoomScale * 1.1 { scroll.setZoomScale(scroll.minimumZoomScale, animated: true); return }
        let scale = min(scroll.maximumZoomScale, scroll.minimumZoomScale * 2.5)
        let point = tap.location(in: imageView), size = CGSize(width: scroll.bounds.width / scale, height: scroll.bounds.height / scale)
        scroll.zoom(to: CGRect(x: point.x - size.width / 2, y: point.y - size.height / 2, width: size.width, height: size.height), animated: true)
    }
}
