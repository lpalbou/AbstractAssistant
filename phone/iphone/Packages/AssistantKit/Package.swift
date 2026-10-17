// swift-tools-version: 6.2
import PackageDescription

let package = Package(
    name: "AssistantKit",
    platforms: [.iOS(.v26), .macOS(.v14)],
    products: [.library(name: "AssistantKit", targets: ["AssistantKit"]),
               .library(name: "AbstractGatewayClient", targets: ["AbstractGatewayClient"])],
    targets: [.target(name: "AbstractGatewayClient"),
              .target(name: "AssistantKit", dependencies: ["AbstractGatewayClient"]),
              .testTarget(name: "AbstractGatewayClientTests", dependencies: ["AbstractGatewayClient"]),
              .testTarget(name: "AssistantKitTests", dependencies: ["AssistantKit", "AbstractGatewayClient"])]
)
