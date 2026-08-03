import AppKit
import CoreGraphics
import Foundation
import ScreenCaptureKit

enum CaptureFailure: LocalizedError {
    case message(String)

    var errorDescription: String? {
        switch self {
        case .message(let text): return text
        }
    }
}
@main
struct NativeCapture {
    static func scale(for frame: CGRect) -> CGFloat {
        let midpoint = CGPoint(x: frame.midX, y: frame.midY)
        for screen in NSScreen.screens {
            guard
                let number = screen.deviceDescription[
                    NSDeviceDescriptionKey("NSScreenNumber")
                ] as? NSNumber
            else { continue }
            let bounds = CGDisplayBounds(CGDirectDisplayID(number.uint32Value))
            if bounds.contains(midpoint) {
                return screen.backingScaleFactor
            }
        }
        return NSScreen.main?.backingScaleFactor ?? 1
    }

    static func matchingApplication(_ query: String) throws -> NSRunningApplication {
        let wanted = query.lowercased()
        guard let app = NSWorkspace.shared.runningApplications.first(where: {
            ($0.localizedName ?? "").lowercased() == wanted
                || ($0.bundleIdentifier ?? "").lowercased() == wanted
        }) else {
            throw CaptureFailure.message("Running application not found: \(query)")
        }
        return app
    }

    static func run(appName: String, outputPath: String) async throws -> [String: Any] {
        let app = try matchingApplication(appName)
        let content = try await SCShareableContent.excludingDesktopWindows(
            false,
            onScreenWindowsOnly: false
        )
        let candidates = content.windows.filter {
            guard $0.owningApplication?.processID == app.processIdentifier else {
                return false
            }
            return $0.frame.width >= 200 && $0.frame.height >= 120
        }
        guard let window = candidates.max(by: {
            $0.frame.width * $0.frame.height < $1.frame.width * $1.frame.height
        }) else {
            throw CaptureFailure.message("No capturable window found for \(appName).")
        }

        let scale = scale(for: window.frame)
        let configuration = SCStreamConfiguration()
        configuration.width = max(1, Int((window.frame.width * scale).rounded()))
        configuration.height = max(1, Int((window.frame.height * scale).rounded()))
        configuration.showsCursor = false
        configuration.scalesToFit = false
        let filter = SCContentFilter(desktopIndependentWindow: window)
        let image = try await SCScreenshotManager.captureImage(
            contentFilter: filter,
            configuration: configuration
        )
        let representation = NSBitmapImageRep(cgImage: image)
        guard let data = representation.representation(
            using: .png,
            properties: [:]
        ) else {
            throw CaptureFailure.message("Could not encode screenshot as PNG.")
        }
        try data.write(to: URL(fileURLWithPath: outputPath), options: .atomic)

        return [
            "application": app.localizedName ?? appName,
            "bundle_id": app.bundleIdentifier ?? "",
            "pid": Int(app.processIdentifier),
            "window_id": Int(window.windowID),
            "window_title": window.title ?? "",
            "backing_scale": Double(scale),
            "window_bounds_points": [
                "x": Double(window.frame.origin.x),
                "y": Double(window.frame.origin.y),
                "width": Double(window.frame.width),
                "height": Double(window.frame.height),
            ],
            "screenshot_size_pixels": [
                "width": configuration.width,
                "height": configuration.height,
            ],
        ]
    }

    static func main() async {
        guard CommandLine.arguments.count == 3 else {
            FileHandle.standardError.write(
                Data("usage: native-capture APP OUTPUT.png\n".utf8)
            )
            exit(2)
        }
        do {
            let payload = try await run(
                appName: CommandLine.arguments[1],
                outputPath: CommandLine.arguments[2]
            )
            let data = try JSONSerialization.data(withJSONObject: payload)
            FileHandle.standardOutput.write(data)
        } catch {
            FileHandle.standardError.write(
                Data("\(error.localizedDescription)\n".utf8)
            )
            exit(1)
        }
    }
}
