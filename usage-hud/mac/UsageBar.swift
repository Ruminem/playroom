// SPDX-License-Identifier: Apache-2.0
// usage-hud 의 맥 메뉴 막대판. 값은 ../usage.py 의 JSON 을 그대로 읽는다 — 단가 표와
// 헤더 검증을 한 곳(파이썬)에만 두려는 것이다. AppKit 만 씀.
//
//   ./build.sh && ./UsageBar          메뉴 막대에 ♥(7일) ⚡(5시간) 남은 양을 띄움
//   ./UsageBar --check                자체 점검

import AppKit

let EVERY: TimeInterval = 5 * 60  // usage.py 는 부를 때마다 한도 요청을 하나 보내므로 5분에 한 번
let PYTHON = "/usr/bin/python3"
let PAGE_URL = URL(string: "http://127.0.0.1:8765/")!
let AGENT_LABEL = "com.ruminem.playroom.usage-bar"

// ── 값 ──────────────────────────────────────────────────────────────────
struct Bar: Decodable {
    let left: Double
    let resetIn: String
    enum CodingKeys: String, CodingKey { case left, resetIn = "in" }
}

struct Bars: Decodable {
    let h5: Bar?
    let d7: Bar?
    enum CodingKeys: String, CodingKey { case h5 = "5h", d7 = "7d" }
}

struct Snapshot: Decodable {
    let bars: Bars
    let expired: Bool
    let today: Double
}

func decode(_ data: Data) -> Snapshot? {
    try? JSONDecoder().decode(Snapshot.self, from: data)
}

func pct(_ b: Bar?) -> String {
    guard let b = b else { return "--" }
    return "\(Int((b.left * 100).rounded()))%"
}

/// 메뉴 막대 글자. 값을 못 받았으면 --, 토큰이 만료됐으면 LOGIN.
func titleText(_ s: Snapshot?) -> String {
    guard let s = s else { return "♥-- ⚡--" }
    if s.expired { return "♥ LOGIN" }
    return "♥\(pct(s.bars.d7)) ⚡\(pct(s.bars.h5))"
}

/// 10% 아래면 빨강. HUD 의 깜빡임 대신이다 — 메뉴 막대가 깜빡이면 눈에 너무 걸린다.
func isLow(_ b: Bar?) -> Bool { (b?.left ?? 1) < 0.1 }

func menuLine(_ name: String, _ b: Bar?) -> String {
    guard let b = b else { return "\(name)  --" }
    return "\(name)  \(pct(b)) 남음 · \(b.resetIn) 뒤 재설정"
}

// ── 로그인 시 실행 (LaunchAgent) ─────────────────────────────────────────
// 번들 없는 바이너리라 SMAppService 를 못 써서 plist 를 직접 둔다. 로그인 때 launchd 가 읽는다.
// 경로가 지금 실행 파일과 다르면(폴더를 옮김) 꺼진 것으로 본다 — 다시 켜면 새 경로로 씀.
let agentFile = FileManager.default.homeDirectoryForCurrentUser
    .appendingPathComponent("Library/LaunchAgents/\(AGENT_LABEL).plist")

func agentPlist(_ exe: String) -> [String: Any] {
    ["Label": AGENT_LABEL, "ProgramArguments": [exe], "RunAtLoad": true]
}

func agentIsOn(_ exe: String) -> Bool {
    guard let d = NSDictionary(contentsOf: agentFile),
          let args = d["ProgramArguments"] as? [String] else { return false }
    return args.first == exe
}

func setAgent(_ on: Bool, _ exe: String) {
    if on {
        try? FileManager.default.createDirectory(
            at: agentFile.deletingLastPathComponent(), withIntermediateDirectories: true)
        (agentPlist(exe) as NSDictionary).write(to: agentFile, atomically: true)
    } else {
        try? FileManager.default.removeItem(at: agentFile)
    }
}

// ── 앱 ──────────────────────────────────────────────────────────────────
final class App: NSObject, NSApplicationDelegate {
    let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    let exe = Bundle.main.executableURL!.resolvingSymlinksInPath()
    var dir: URL { exe.deletingLastPathComponent().deletingLastPathComponent() }  // usage-hud/
    var snap: Snapshot?
    var page: Process?
    var busy = false
    var tried = false  // 첫 값을 받기 전엔 "못 받음" 대신 "받는 중"

    func applicationDidFinishLaunching(_ n: Notification) {
        show()
        refresh()
        Timer.scheduledTimer(withTimeInterval: EVERY, repeats: true) { [weak self] _ in self?.refresh() }
    }

    func refresh() {
        if busy { return }
        busy = true
        DispatchQueue.global().async {
            let p = Process()
            p.executableURL = URL(fileURLWithPath: PYTHON)
            p.arguments = [self.dir.appendingPathComponent("usage.py").path]
            let out = Pipe()
            p.standardOutput = out
            p.standardError = FileHandle.nullDevice
            var s: Snapshot?
            if (try? p.run()) != nil {
                let data = out.fileHandleForReading.readDataToEndOfFile()
                p.waitUntilExit()
                s = decode(data)
            }
            DispatchQueue.main.async {
                self.snap = s
                self.tried = true
                self.busy = false
                self.show()
            }
        }
    }

    func show() {
        let font = NSFont.monospacedDigitSystemFont(ofSize: NSFont.systemFontSize, weight: .medium)
        let t = NSMutableAttributedString(string: titleText(snap), attributes: [.font: font])
        let red = NSColor.systemRed
        t.addAttribute(.foregroundColor, value: red, range: NSRange(location: 0, length: 1))
        if let s = snap, !s.expired {
            let str = t.string as NSString
            if isLow(s.bars.d7) {
                t.addAttribute(.foregroundColor, value: red, range: str.range(of: pct(s.bars.d7)))
            }
            let bolt = str.range(of: "⚡")
            if isLow(s.bars.h5) {
                let rest = NSRange(location: bolt.location + bolt.length,
                                   length: str.length - bolt.location - bolt.length)
                t.addAttribute(.foregroundColor, value: red, range: rest)
            }
        }
        item.button?.attributedTitle = t
        item.menu = menu()
    }

    func menu() -> NSMenu {
        let m = NSMenu()
        func add(_ title: String, _ action: Selector?, on: Bool = false) {
            let i = NSMenuItem(title: title, action: action, keyEquivalent: "")
            i.target = self
            i.state = on ? .on : .off
            if action == nil { i.isEnabled = false }
            m.addItem(i)
        }
        if let s = snap {
            if s.expired {
                add("로그인 토큰 만료 — 터미널에서 claude 를 한 번 여세요", nil)
            } else {
                add(menuLine("HP (7일)", s.bars.d7), nil)
                add(menuLine("ST (5시간)", s.bars.h5), nil)
            }
            add(String(format: "오늘 정가 $%.2f", s.today), nil)
        } else {
            add(tried ? "값을 못 받음 — usage.py 를 직접 돌려 보세요" : "받는 중…", nil)
        }
        m.addItem(.separator())
        add("지금 새로 받기", #selector(onRefresh))
        add("페이지 열기 (7일치)", #selector(onPage))
        add("로그인 시 실행", #selector(onAgent), on: agentIsOn(exe.path))
        m.addItem(.separator())
        add("끝내기", #selector(onQuit))
        return m
    }

    @objc func onRefresh() { refresh() }

    @objc func onPage() {
        // 이미 떠 있으면 새 서버는 포트가 겹쳐 바로 끝나고, 열리는 것은 원래 서버다
        if page?.isRunning != true {
            let p = Process()
            p.executableURL = URL(fileURLWithPath: PYTHON)
            p.arguments = [dir.appendingPathComponent("page.py").path, "--no-open"]
            p.standardOutput = FileHandle.nullDevice
            p.standardError = FileHandle.nullDevice
            try? p.run()
            page = p
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 1) { NSWorkspace.shared.open(PAGE_URL) }
    }

    @objc func onAgent() {
        setAgent(!agentIsOn(exe.path), exe.path)
        show()
    }

    @objc func onQuit() {
        page?.terminate()
        NSApp.terminate(nil)
    }
}

// ── 자체 점검 ───────────────────────────────────────────────────────────
func check() {
    let json = """
    {"bars": {"5h": {"left": 0.97, "reset": 1.0, "in": "4H32M"}, "7d": null},
     "expired": false, "today": 1.27, "days": [], "unknown": []}
    """
    let s = decode(json.data(using: .utf8)!)
    precondition(s != nil, "null 창이 섞인 JSON 을 못 읽음")
    precondition(titleText(s) == "♥-- ⚡97%", titleText(s))
    precondition(menuLine("ST", s!.bars.h5) == "ST  97% 남음 · 4H32M 뒤 재설정")
    precondition(titleText(nil) == "♥-- ⚡--")
    let gone = decode(#"{"bars": {"5h": null, "7d": null}, "expired": true, "today": 0}"#.data(using: .utf8)!)
    precondition(titleText(gone) == "♥ LOGIN")
    precondition(decode("0.78초".data(using: .utf8)!) == nil)  // 깨진 출력은 nil
    precondition(isLow(Bar(left: 0.09, resetIn: "")) && !isLow(Bar(left: 0.1, resetIn: "")) && !isLow(nil))
    precondition(pct(Bar(left: 0.125, resetIn: "")) == "13%")
    let p = agentPlist("/x/UsageBar")
    precondition((p["ProgramArguments"] as? [String]) == ["/x/UsageBar"] && p["RunAtLoad"] as? Bool == true)
    print("ok")
}

// ── 시작 ────────────────────────────────────────────────────────────────
if CommandLine.arguments.contains("--check") {
    check()
    exit(0)
}

// 두 번 띄우면 아이콘이 둘 생기므로 사용자 임시 폴더의 잠금 파일로 하나만 둔다
let lock = open(NSTemporaryDirectory() + "\(AGENT_LABEL).lock", O_CREAT | O_RDWR, 0o600)
if lock < 0 || flock(lock, LOCK_EX | LOCK_NB) != 0 {
    exit(0)
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)  // 독에 안 뜸
let delegate = App()
app.delegate = delegate
app.run()
