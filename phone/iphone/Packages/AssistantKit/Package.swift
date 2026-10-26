// swift-tools-version: 6.2
import PackageDescription

// The iPhone's own logic on top of the gateway client every Apple client shares
// (watch/apple/Packages/AbstractGatewayClient, module AbstractGatewayClient).
let package = Package(
    name: "AssistantKit",
    platforms: [.iOS(.v26), .macOS(.v26)],
    products: [.library(name: "AssistantKit", targets: ["AssistantKit"])],
    dependencies: [.package(path: "../../../../watch/apple/Packages/AbstractGatewayClient")],
    targets: [.target(name: "AssistantKit", dependencies: [.product(name: "AbstractGatewayClient", package: "AbstractGatewayClient")]),
              .testTarget(name: "AssistantKitTests", dependencies: ["AssistantKit", .product(name: "AbstractGatewayClient", package: "AbstractGatewayClient")])]
)
