# Third-party notices

**English** · [한국어](#korean)

The code in this repository is Apache-2.0 (see [LICENSE](LICENSE)) and uses only the Python standard library. Running the `.py` files, or anything on macOS, uses your own Python and bundles nothing.

The Windows `.exe` files on the Releases page are built with PyInstaller, which packs a Python runtime into each one. Those files therefore also carry the components below. Not every `.exe` holds every item: each gets only what its tool imports (Tcl/Tk only goes into the ones with a window).

| Component | Why it is in the `.exe` | License |
|---|---|---|
| [CPython](https://www.python.org/) 3.14 | the Python runtime and standard library | [PSF License v2](https://docs.python.org/3.14/license.html) |
| [PyInstaller](https://pyinstaller.org/) bootloader | starts the packed program | [GPL-2.0-or-later with the bootloader exception](https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt), which allows bundling it with programs under any license |
| [Tcl/Tk](https://www.tcl-lang.org/) | `tkinter` windows and dialogs | [Tcl/Tk license](https://www.tcl-lang.org/software/tcltk/license.html) (BSD-style) |
| [OpenSSL](https://openssl-library.org/) | `hashlib`, HTTPS in `urllib` | [Apache-2.0](https://openssl-library.org/source/license/) |
| [libffi](https://sourceware.org/libffi/) | `ctypes` calls into Windows | [MIT](https://github.com/libffi/libffi/blob/master/LICENSE) |
| [zlib](https://zlib.net/), [bzip2](https://sourceware.org/bzip2/), [XZ Utils](https://tukaani.org/xz/) (liblzma) | compression modules pulled in by `shutil` | [zlib](https://zlib.net/zlib_license.html), [bzip2](https://sourceware.org/bzip2/) (BSD-style), 0BSD / public domain |
| Microsoft Visual C++ runtime (`vcruntime140.dll`) | needed by the Python runtime | [Visual Studio redistributable terms](https://learn.microsoft.com/cpp/windows/redistributing-visual-cpp-files) |

This list was made from the imports in the source. The CPython license page linked above lists, with full texts, every other library that ships inside the Windows build of Python.

---

## Korean

[English](#third-party-notices) · **한국어**

이 저장소의 코드는 Apache-2.0([LICENSE](LICENSE) 참고)이고 Python 표준 라이브러리만 씀. `.py` 를 직접 돌리거나 맥에서 쓸 때는 각자의 Python 을 쓰므로 같이 묶이는 것이 없음.

Releases 페이지의 윈도우 `.exe` 는 PyInstaller 로 구워서 파일마다 Python 런타임이 들어 있음. 그래서 아래 구성 요소도 같이 실림. 모든 `.exe` 에 전부 들어 있지는 않고 그 도구가 import 하는 것만 들어감(Tcl/Tk 는 창이 있는 도구에만).

| 구성 요소 | `.exe` 에 들어간 까닭 | 라이선스 |
|---|---|---|
| [CPython](https://www.python.org/) 3.14 | Python 런타임과 표준 라이브러리 | [PSF License v2](https://docs.python.org/3.14/license.html) |
| [PyInstaller](https://pyinstaller.org/) 부트로더 | 묶인 프로그램을 띄움 | [GPL-2.0-or-later + 부트로더 예외](https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt). 예외 조항 덕에 어떤 라이선스의 프로그램과도 같이 묶을 수 있음 |
| [Tcl/Tk](https://www.tcl-lang.org/) | `tkinter` 창과 대화상자 | [Tcl/Tk license](https://www.tcl-lang.org/software/tcltk/license.html) (BSD 꼴) |
| [OpenSSL](https://openssl-library.org/) | `hashlib`, `urllib` 의 HTTPS | [Apache-2.0](https://openssl-library.org/source/license/) |
| [libffi](https://sourceware.org/libffi/) | `ctypes` 로 윈도우 API 부르기 | [MIT](https://github.com/libffi/libffi/blob/master/LICENSE) |
| [zlib](https://zlib.net/), [bzip2](https://sourceware.org/bzip2/), [XZ Utils](https://tukaani.org/xz/) (liblzma) | `shutil` 이 끌어오는 압축 모듈 | [zlib](https://zlib.net/zlib_license.html), [bzip2](https://sourceware.org/bzip2/) (BSD 꼴), 0BSD / 퍼블릭 도메인 |
| Microsoft Visual C++ 런타임 (`vcruntime140.dll`) | Python 런타임이 필요로 함 | [Visual Studio 재배포 조건](https://learn.microsoft.com/cpp/windows/redistributing-visual-cpp-files) |

이 목록은 소스의 import 를 보고 만들었음. 위에 건 CPython 라이선스 페이지에 윈도우판 Python 안에 같이 실리는 나머지 라이브러리가 전문과 함께 다 있음.
