# SPDX-License-Identifier: Apache-2.0
"""트레이 아이콘 파일 만들기. OS 를 안 타서 tray.py(윈도우)와 mac/tray.py 가 같이 쓴다."""
import struct


def write_ico(path, art, colors, sizes=(16, 20, 24, 32, 40, 48)):
    """픽셀 그림(글자 하나 = 색 하나, '.' = 비움)을 크기 여러 벌짜리 .ico 로. 32비트 BGRA.

    윈도우가 화면 배율에 맞는 크기를 골라 가므로, 정수배로 키운 벌을 여럿 넣어 흐려지지 않게 한다.
    """
    n = len(art)
    blobs = []
    for size in sizes:
        k = size // n
        off = (size - n * k) // 2
        xor = bytearray()
        for y in reversed(range(size)):  # BMP 는 아래 줄부터
            for x in range(size):
                ax, ay = (x - off) // k, (y - off) // k
                c = art[ay][ax] if off <= x < off + n * k and off <= y < off + n * k else "."
                if c == ".":
                    xor += b"\0\0\0\0"
                else:
                    r, g, b = (int(colors[c][i:i + 2], 16) for i in (1, 3, 5))
                    xor += bytes((b, g, r, 255))
        mask = bytes(((size + 31) // 32) * 4 * size)  # 알파를 쓰므로 AND 마스크는 다 0
        head = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, len(xor) + len(mask), 0, 0, 0, 0)
        blobs.append(head + bytes(xor) + mask)
    out = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    for size, blob in zip(sizes, blobs):
        out += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
    with open(path, "wb") as f:
        f.write(out + b"".join(blobs))
