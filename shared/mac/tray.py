# SPDX-License-Identifier: Apache-2.0
"""shared/tray.py 의 맥판: 메뉴 막대 아이콘(NSStatusItem)과 그 메뉴.

윈도우판은 제 스레드에서 메시지 루프를 돌리지만, AppKit 은 메인 스레드에서만 만져야 하므로 여기서는
스레드가 없다. 아이콘 클릭은 그리는 쪽이 surface.pump() 로 이벤트를 돌릴 때 처리되고, 메뉴는 열릴 때마다
menu() 로 새로 짠다. 고른 명령은 on_command(id), close() 하면 on_command(None) 을 한 번 부른다.
"""
import ctypes as C

from cocoa import Size, cls, drain, new_object, nsstring, objc, pool, send
from icon import write_ico  # noqa: F401 — 윈도우판과 같은 자리에서 가져가게

ICON_PT = 16  # 메뉴 막대 아이콘 크기. .ico 의 32px 벌이 레티나 2배에 딱 맞음
ON = 1  # NSControlStateValueOn
PICK = objc.sel_registerName(b"pick:")


class Tray:
    """menu() 항목: (글, id, 체크?) · (글, [하위 항목]) · None(구분선). 윈도우판과 같다."""

    def __init__(self, class_name, icon_path, tip, menu, on_command):
        self.menu, self.on_command = menu, on_command
        p = pool()
        bar = send(cls("NSStatusBar"), "systemStatusBar")
        self.item = send(send(bar, "statusItemWithLength:", -1.0, argtypes=(C.c_double,)), "retain")  # 가변 폭
        button = send(self.item, "button")
        img = send(send(cls("NSImage"), "alloc"), "initWithContentsOfFile:", nsstring(str(icon_path)),
                   argtypes=(C.c_void_p,))
        if img:
            send(img, "setSize:", Size(ICON_PT, ICON_PT), restype=None, argtypes=(Size,))
            send(button, "setImage:", img, restype=None, argtypes=(C.c_void_p,))
        else:
            send(button, "setTitle:", nsstring(tip), restype=None, argtypes=(C.c_void_p,))
        send(button, "setToolTip:", nsstring(tip), restype=None, argtypes=(C.c_void_p,))
        # 메뉴 동작을 받을 ObjC 객체. 클래스 이름을 class_name 으로 해 오버레이마다 따로 둔다
        self.target = new_object(class_name, {"pick:": self._pick, "menuNeedsUpdate:": self._fill})
        self.nsmenu = send(send(cls("NSMenu"), "alloc"), "init")
        send(self.nsmenu, "setDelegate:", self.target, restype=None, argtypes=(C.c_void_p,))
        send(self.item, "setMenu:", self.nsmenu, restype=None, argtypes=(C.c_void_p,))
        drain(p)

    def set_tip(self, tip):
        send(send(self.item, "button"), "setToolTip:", nsstring(tip), restype=None, argtypes=(C.c_void_p,))

    def close(self):
        if self.item:
            send(send(cls("NSStatusBar"), "systemStatusBar"), "removeStatusItem:", self.item, restype=None,
                 argtypes=(C.c_void_p,))
            self.item = None
            self.on_command(None)

    def _pick(self, sender):
        self.on_command(send(sender, "tag", restype=C.c_long))

    def _fill(self, nsmenu):
        send(nsmenu, "removeAllItems", restype=None)
        self._build(nsmenu, self.menu())

    def _build(self, nsmenu, items):
        add = lambda it: send(nsmenu, "addItem:", it, restype=None, argtypes=(C.c_void_p,))
        for item in items:
            if item is None:
                add(send(cls("NSMenuItem"), "separatorItem"))
                continue
            label = item[0]
            sub = isinstance(item[1], list)
            it = send(send(cls("NSMenuItem"), "alloc"), "initWithTitle:action:keyEquivalent:", nsstring(label),
                      None if sub else PICK, nsstring(""),
                      argtypes=(C.c_void_p, C.c_void_p, C.c_void_p))
            if sub:
                m = send(send(cls("NSMenu"), "alloc"), "initWithTitle:", nsstring(label), argtypes=(C.c_void_p,))
                self._build(m, item[1])
                send(it, "setSubmenu:", m, restype=None, argtypes=(C.c_void_p,))
                send(m, "release", restype=None)
            else:
                send(it, "setTarget:", self.target, restype=None, argtypes=(C.c_void_p,))
                send(it, "setTag:", item[1], restype=None, argtypes=(C.c_long,))
                if item[2]:
                    send(it, "setState:", ON, restype=None, argtypes=(C.c_long,))
            add(it)
            send(it, "release", restype=None)  # 메뉴가 붙들고 있으니 만든 몫은 놓음

