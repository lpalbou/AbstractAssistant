// swift-tools-version: 6.2
import PackageDescription

let package = Package(
    name: "AbstractGatewayClient",
    platforms: [.watchOS(.v26), .iOS(.v26), .macOS(.v26)],
    products: [
        .library(name: "AbstractGatewayClient", targets: ["AbstractGatewayClient"]),
    ],
    targets: [
        .target(name: "AbstractGatewayClient"),
        .testTarget(name: "AbstractGatewayClientTests", dependencies: ["AbstractGatewayClient"]),
    ]
)
