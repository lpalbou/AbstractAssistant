// swift-tools-version: 6.2
import PackageDescription

let package = Package(
    name: "AssistantKit",
    platforms: [.iOS(.v26), .macOS(.v14)],
    products: [.library(name: "AssistantKit", targets: ["AssistantKit"]),
               .library(name: "PhoneGatewayClient", targets: ["PhoneGatewayClient"])],
    targets: [.target(name: "PhoneGatewayClient"),
              .target(name: "AssistantKit", dependencies: ["PhoneGatewayClient"]),
              .testTarget(name: "PhoneGatewayClientTests", dependencies: ["PhoneGatewayClient"]),
              .testTarget(name: "AssistantKitTests", dependencies: ["AssistantKit", "PhoneGatewayClient"])]
)
