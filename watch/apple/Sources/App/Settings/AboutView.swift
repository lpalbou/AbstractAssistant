import SwiftUI

/// About, as in every AbstractFramework app: this app's version and build, then the framework's
/// facts (author, copyright, website, source, docs, issues, feedback, contact) read from the
/// framework's identity descriptor bundled with the app (`abstractframework_identity.json`, the
/// same file AbstractCore ships), so none of them is typed here.
struct AboutView: View {
    private let identity = AppIdentity.load()

    var body: some View {
        ScrollView {
            VStack(spacing: 6) {
                LogoMark(size: 40)
                Text(identity?.app.name ?? "AbstractAssistant").font(.rounded(.headline, weight: .bold)).foregroundStyle(Theme.text)
                Text("for Apple Watch").font(.rounded(.caption2)).foregroundStyle(Theme.muted)
                Text("Version \(AppIdentity.version) (\(AppIdentity.build))")
                    .font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.cyan).padding(.bottom, 6)
                if let id = identity {
                    VStack(alignment: .leading, spacing: 8) {
                        row("Part of", id.framework.name)
                        row("Author", "\(id.framework.author) (\(id.framework.years))")
                        row("Copyright", id.framework.copyright)
                        link("Website", id.app.website)
                        link("Source", id.app.repo)
                        link("Documentation", id.app.docs)
                        link("Report an issue", id.app.issues)
                        link("Give feedback", id.app.feedback)
                        mail("Contact", id.framework.contactEmail)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                } else {
                    Text("The framework's identity file is missing from this build.")
                        .font(.rounded(.caption2)).foregroundStyle(Theme.red).multilineTextAlignment(.center)
                }
            }
            .padding(.horizontal, 4)
        }
        .screen("About")
    }

    private func row(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(label).font(.rounded(.caption2)).foregroundStyle(Theme.muted)
            Text(value).font(.rounded(.footnote)).foregroundStyle(Theme.text)
        }
    }

    /// An email address opens a new message in the watch's Mail.
    @ViewBuilder private func mail(_ label: String, _ address: String) -> some View {
        if let url = URL(string: "mailto:" + address) {
            Link(destination: url) {
                VStack(alignment: .leading, spacing: 1) {
                    Text(label).font(.rounded(.caption2)).foregroundStyle(Theme.muted)
                    Text(address).font(.rounded(.footnote)).foregroundStyle(Theme.cyan)
                }
            }
            .buttonStyle(.tap)
            .accessibilityHint("Writes an email")
        } else {
            row(label, address)
        }
    }

    /// A link opens in the app's page reader (the watch has no browser an app can open).
    @ViewBuilder private func link(_ label: String, _ value: String) -> some View {
        if let url = URL(string: value) {
            NavigationLink(value: Route.link(url)) {
                VStack(alignment: .leading, spacing: 1) {
                    Text(label).font(.rounded(.caption2)).foregroundStyle(Theme.muted)
                    Text(value.replacingOccurrences(of: "https://", with: "")).font(.rounded(.footnote))
                        .foregroundStyle(Theme.cyan).multilineTextAlignment(.leading)
                }
            }
            .buttonStyle(.tap)
        } else {
            row(label, value)
        }
    }
}

/// The framework's identity descriptor (`abstractframework.identity.v1`): the framework's facts
/// and this app's links.
struct AppIdentity: Decodable {
    struct Framework: Decodable {
        let name, website, author, years, license, copyright, contactEmail: String
        enum CodingKeys: String, CodingKey { case name, website, author, years, license, copyright, contactEmail = "contact_email" }
    }
    struct App: Decodable { let name, website, repo, docs, issues, feedback: String }
    let framework: Framework
    let apps: [String: App]
    var app: App { apps["abstractassistant"]! }

    static func load() -> AppIdentity? {
        guard let url = Bundle.main.url(forResource: "abstractframework_identity", withExtension: "json"),
              let data = try? Data(contentsOf: url),
              let id = try? JSONDecoder().decode(AppIdentity.self, from: data), id.apps["abstractassistant"] != nil else { return nil }
        return id
    }

    static var version: String { Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "?" }
    static var build: String { Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "?" }
}
