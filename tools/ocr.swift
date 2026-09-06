// On-device OCR for shopper-app screenshots. Apple Vision, no network, no key.
//
//   tools/bin/ocr shot1.png shot2.png ...   ->  one JSON object per image on stdout
//
// Each line carries normalised coordinates with the origin at TOP-left (Vision's
// native origin is bottom-left; flipped here so sorting by y gives reading order).
// Language correction is OFF on purpose: it "fixes" $40.05 and 12:59pm into words.
import Foundation
import Vision
import AppKit

struct Line: Codable { let text: String; let x: Double; let y: Double; let w: Double; let h: Double; let conf: Double }
struct Shot: Codable { let file: String; let width: Int; let height: Int; let lines: [Line] }

func ocr(_ path: String) -> Shot? {
    let url = URL(fileURLWithPath: path)
    guard let img = NSImage(contentsOf: url),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        FileHandle.standardError.write("cannot read \(path)\n".data(using: .utf8)!); return nil
    }
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.recognitionLanguages = ["en-US"]
    req.usesLanguageCorrection = false
    let handler = VNImageRequestHandler(cgImage: cg, options: [:])
    do { try handler.perform([req]) } catch {
        FileHandle.standardError.write("vision failed on \(path): \(error)\n".data(using: .utf8)!); return nil
    }
    var lines: [Line] = []
    for obs in (req.results ?? []) {
        guard let top = obs.topCandidates(1).first else { continue }
        let b = obs.boundingBox
        lines.append(Line(text: top.string, x: b.minX, y: 1.0 - b.maxY, w: b.width, h: b.height,
                          conf: Double(top.confidence)))
    }
    // reading order: top to bottom, then left to right, with a small y tolerance
    lines.sort { a, b in abs(a.y - b.y) > 0.006 ? a.y < b.y : a.x < b.x }
    return Shot(file: path, width: cg.width, height: cg.height, lines: lines)
}

let enc = JSONEncoder()
for p in CommandLine.arguments.dropFirst() {
    if let s = ocr(p), let d = try? enc.encode(s), let str = String(data: d, encoding: .utf8) { print(str) }
}
