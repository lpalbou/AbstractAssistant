// swift-tools-version: 6.2
import PackageDescription

// What the AbstractAssistant apps (iPhone and Apple Watch) and their notification service
// extensions share: the sign-in kept sealed in the app group, the push registration with the
// gateway (framework backlog 1049) and how a push is rendered from the gateway's event.
// No dependency on either gateway client, so the extensions stay small.
let package = Package(
    name: "AssistantPush",
    platforms: [.iOS(.v26), .watchOS(.v26), .macOS(.v14)],
    products: [.library(name: "AssistantPush", targets: ["AssistantPush"])],
    targets: [
        .target(name: "AssistantPush"),
        .testTarget(name: "AssistantPushTests", dependencies: ["AssistantPush"]),
    ]
)
