# SPDX-License-Identifier: Apache-2.0
"""맥판 공용: ctypes 로 ObjC 런타임을 직접 부른다. PyObjC 는 최신판이 3.10 이상이라 맥 기본 3.9 에 없다.

objc_msgSend 는 인자·반환 타입마다 모양이 달라 셀렉터마다 맞는 CFUNCTYPE 로 바꿔 부른다(send).
NSApplication 은 처음 import 할 때 한 번 띄우고, 독에 안 뜨게 accessory 로 둔다.
"""
import ctypes as C
import ctypes.util

objc = C.cdll.LoadLibrary(C.util.find_library("objc"))
C.cdll.LoadLibrary("/System/Library/Frameworks/AppKit.framework/AppKit")
FOUNDATION = C.cdll.LoadLibrary("/System/Library/Frameworks/Foundation.framework/Foundation")
objc.objc_getClass.restype = C.c_void_p
objc.objc_getClass.argtypes = [C.c_char_p]
objc.sel_registerName.restype = C.c_void_p
objc.sel_registerName.argtypes = [C.c_char_p]
objc.objc_allocateClassPair.restype = C.c_void_p
objc.objc_allocateClassPair.argtypes = [C.c_void_p, C.c_char_p, C.c_size_t]
objc.objc_registerClassPair.argtypes = [C.c_void_p]
objc.class_addMethod.restype = C.c_bool
objc.class_addMethod.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p, C.c_char_p]
_SEND = C.cast(objc.objc_msgSend, C.c_void_p).value
_fns = {}


def send(obj, sel, *args, restype=C.c_void_p, argtypes=()):
    key = (restype, tuple(argtypes))
    f = _fns.get(key)
    if f is None:
        f = _fns[key] = C.CFUNCTYPE(restype, C.c_void_p, C.c_void_p, *argtypes)(_SEND)
    return f(obj, objc.sel_registerName(sel.encode()), *args)


def cls(name):
    return objc.objc_getClass(name.encode())


def nsstring(s):
    return send(cls("NSString"), "stringWithUTF8String:", s.encode(), argtypes=(C.c_char_p,))


IMP = C.CFUNCTYPE(None, C.c_void_p, C.c_void_p, C.c_void_p)  # -(void)name:(id)arg
_keep = []  # 등록한 함수가 GC 되면 ObjC 가 죽은 주소를 부른다


def new_object(class_name, methods):
    """methods = {'셀렉터:': fn(arg)} 를 받는 NSObject 하위 클래스를 등록하고 객체 하나를 만든다."""
    k = cls(class_name)
    if not k:
        k = objc.objc_allocateClassPair(cls("NSObject"), class_name.encode(), 0)
        for sel, fn in methods.items():
            imp = IMP(lambda self, _cmd, arg, fn=fn: fn(arg))
            _keep.append(imp)
            objc.class_addMethod(k, objc.sel_registerName(sel.encode()), C.cast(imp, C.c_void_p), b"v@:@")
        objc.objc_registerClassPair(k)
    return send(send(k, "alloc"), "init")


class Point(C.Structure):
    _fields_ = [("x", C.c_double), ("y", C.c_double)]


class Size(C.Structure):
    _fields_ = [("w", C.c_double), ("h", C.c_double)]


class Rect(C.Structure):
    _fields_ = [("o", Point), ("s", Size)]


app = send(cls("NSApplication"), "sharedApplication")
send(app, "setActivationPolicy:", 1, restype=C.c_bool, argtypes=(C.c_long,))  # accessory: 독에 안 뜸
send(app, "finishLaunching", restype=None)
RUN_LOOP_MODE = C.c_void_p.in_dll(FOUNDATION, "NSDefaultRunLoopMode").value


def pool():
    return send(send(cls("NSAutoreleasePool"), "alloc"), "init")


def drain(p):
    send(p, "drain", restype=None)


def pump():
    """쌓인 이벤트를 다 돌림. 메뉴를 열면 닫힐 때까지 여기서 안 돌아온다(그동안 그림이 멈춤)."""
    p = pool()
    while True:
        ev = send(app, "nextEventMatchingMask:untilDate:inMode:dequeue:", 0xFFFFFFFFFFFFFFFF, None, RUN_LOOP_MODE,
                  True, argtypes=(C.c_uint64, C.c_void_p, C.c_void_p, C.c_bool))
        if not ev:
            break
        send(app, "sendEvent:", ev, restype=None, argtypes=(C.c_void_p,))
    drain(p)


def main_screen():
    """(전체 frame, 메뉴 막대·독을 뺀 visibleFrame). 좌표는 코코아식 — 원점이 왼쪽 아래."""
    s = send(cls("NSScreen"), "mainScreen")
    return send(s, "frame", restype=Rect), send(s, "visibleFrame", restype=Rect)
