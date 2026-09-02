# btabswitch.py
# Always-on-top Browser Tab Switcher

import ctypes
try:
    hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, 0)
except Exception:
    pass

import sys
import os
import io
import time
import math
import ctypes
import ctypes.wintypes

# Force stdout/stderr to UTF-8 to prevent charmap encoding errors with unicode titles, or dummy writer if None (pythonw.exe)
class DummyWriter:
    def write(self, *args, **kwargs): pass
    def flush(self, *args, **kwargs): pass

if sys.stdout is None:
    sys.stdout = DummyWriter()
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

if sys.stderr is None:
    sys.stderr = DummyWriter()
else:
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from PyQt5.QtWidgets import QApplication, QWidget, QSystemTrayIcon, QMenu, QAction
from PyQt5.QtCore import Qt, QPoint, QPointF, QTimer, QRectF
from PyQt5.QtGui import (
    QColor, QPainter, QPen, QBrush, QRadialGradient,
    QPainterPath, QFont, QIcon, QPixmap
)
from PyQt5.QtWinExtras import QtWin

# ── Win32 ─────────────────────────────────────────────────────────────────────
user32   = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

VK_CONTROL      = 0x11
VK_SHIFT        = 0x10
VK_TAB          = 0x09
VK_PRIOR        = 0x21  # Page Up
VK_NEXT         = 0x22  # Page Down
KEYEVENTF_KEYUP = 0x0002
GWL_EXSTYLE     = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
SW_RESTORE       = 9
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

if hasattr(user32, 'GetWindowLongPtrW'):
    user32.GetWindowLongPtrW.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongPtrW.restype = ctypes.c_void_p
    _GetWindowLong = user32.GetWindowLongPtrW
else:
    user32.GetWindowLongW.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = ctypes.c_long
    _GetWindowLong = user32.GetWindowLongW

if hasattr(user32, 'SetWindowLongPtrW'):
    user32.SetWindowLongPtrW.argtypes = [ctypes.wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
    user32.SetWindowLongPtrW.restype = ctypes.c_void_p
    _SetWindowLong = user32.SetWindowLongPtrW
else:
    user32.SetWindowLongW.argtypes = [ctypes.wintypes.HWND, ctypes.c_int, ctypes.c_long]
    user32.SetWindowLongW.restype = ctypes.c_long
    _SetWindowLong = user32.SetWindowLongW

user32.IsWindow.argtypes = [ctypes.wintypes.HWND]
user32.IsWindow.restype = ctypes.wintypes.BOOL

user32.IsIconic.argtypes = [ctypes.wintypes.HWND]
user32.IsIconic.restype = ctypes.wintypes.BOOL

user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = ctypes.wintypes.HWND

user32.SetForegroundWindow.argtypes = [ctypes.wintypes.HWND]
user32.SetForegroundWindow.restype = ctypes.wintypes.BOOL

user32.ShowWindow.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = ctypes.wintypes.BOOL

IsWindow            = user32.IsWindow
IsIconic            = user32.IsIconic
GetForegroundWindow = user32.GetForegroundWindow
SetForegroundWindow = user32.SetForegroundWindow
ShowWindow          = user32.ShowWindow

user32.GetWindowTextLengthW.argtypes = [ctypes.wintypes.HWND]
user32.GetWindowTextLengthW.restype  = ctypes.c_int
user32.GetWindowTextW.argtypes       = [ctypes.wintypes.HWND, ctypes.c_wchar_p, ctypes.c_int]
user32.GetWindowTextW.restype        = ctypes.c_int
user32.GetClassNameW.argtypes        = [ctypes.wintypes.HWND, ctypes.c_wchar_p, ctypes.c_int]
user32.GetClassNameW.restype         = ctypes.c_int
user32.keybd_event.argtypes          = [ctypes.c_byte, ctypes.c_byte,
                                        ctypes.c_ulong, ctypes.c_void_p]
user32.keybd_event.restype = None

user32.GetWindowThreadProcessId.argtypes = [ctypes.wintypes.HWND,
                                             ctypes.POINTER(ctypes.c_ulong)]
user32.GetWindowThreadProcessId.restype  = ctypes.c_ulong

kernel32.OpenProcess.argtypes  = [ctypes.c_ulong, ctypes.c_bool, ctypes.c_ulong]
kernel32.OpenProcess.restype   = ctypes.wintypes.HANDLE
kernel32.CloseHandle.argtypes  = [ctypes.wintypes.HANDLE]
kernel32.CloseHandle.restype   = ctypes.c_bool

# QueryFullProcessImageNameW: safer than psapi on 64-bit (Vista+, no psapi needed)
kernel32.QueryFullProcessImageNameW.argtypes = [
    ctypes.wintypes.HANDLE,
    ctypes.c_ulong,
    ctypes.c_wchar_p,
    ctypes.POINTER(ctypes.c_ulong),
]
kernel32.QueryFullProcessImageNameW.restype = ctypes.c_bool

shell32 = ctypes.windll.shell32
shell32.ExtractIconW.argtypes = [ctypes.wintypes.HINSTANCE, ctypes.c_wchar_p, ctypes.c_int]
shell32.ExtractIconW.restype = ctypes.wintypes.HICON
if hasattr(user32, 'DestroyIcon'):
    user32.DestroyIcon.argtypes = [ctypes.wintypes.HICON]
    user32.DestroyIcon.restype = ctypes.wintypes.BOOL

# ── Browser detection ─────────────────────────────────────────────────────────
BROWSER_CLASSES = {'Chrome_WidgetWin_1', 'MozillaWindowClass', 'IEFrame'}

BROWSER_KEYWORDS = {
    'chrome', 'firefox', 'edge', 'brave', 'opera', 'vivaldi', 'browser',
    'explorer', 'safari', 'arc', 'thorium', 'wolf', 'waterfox', 'maxthon',
    'yandex', 'coccoc', 'whale', 'sidekick', 'slimjet', 'seamonkey', 'avant',
    'tor', 'wave'
}

BROWSER_PROCS = frozenset([
    'chrome.exe', 'firefox.exe', 'msedge.exe', 'brave.exe', 'opera.exe',
    'operagx.exe', 'vivaldi.exe', 'iexplore.exe', 'waterfox.exe',
    'librewolf.exe', 'arc.exe', 'thorium.exe', 'yandex.exe'
])

def _window_class(hwnd) -> str:
    try:
        buf = ctypes.create_unicode_buffer(260)
        user32.GetClassNameW(hwnd, buf, 260)
        return buf.value.strip()
    except Exception:
        return ''

def _proc_name(hwnd) -> str:
    try:
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return ''
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not h:
            return ''
        buf  = ctypes.create_unicode_buffer(260)
        size = ctypes.c_ulong(260)
        kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
        kernel32.CloseHandle(h)
        return os.path.basename(buf.value).lower()
    except Exception:
        return ''

def is_browser(hwnd) -> bool:
    if not hwnd or not IsWindow(hwnd):
        return False
    proc = _proc_name(hwnd)
    if not proc:
        return False
    # 1. Direct match on common executables
    if proc in BROWSER_PROCS:
        return True
    # 2. Check window class name combined with process name keywords (to filter electron apps)
    cls = _window_class(hwnd)
    if cls in BROWSER_CLASSES:
        proc_lower = proc.lower()
        if any(kw in proc_lower for kw in BROWSER_KEYWORDS):
            return True
    return False

def get_title(hwnd) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    if not n:
        return ''
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value.strip()

def get_window_icon(hwnd) -> QPixmap:
    if not hwnd or not IsWindow(hwnd):
        return None
    try:
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value:
            h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
            if h:
                buf = ctypes.create_unicode_buffer(512)
                size = ctypes.c_ulong(512)
                if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                    path = buf.value
                    hicon = shell32.ExtractIconW(0, path, 0)
                    if hicon and int(hicon) > 1:
                        pixmap = QtWin.fromHICON(hicon)
                        user32.DestroyIcon(hicon)
                        if not pixmap.isNull():
                            return pixmap
                kernel32.CloseHandle(h)
    except Exception as e:
        print(f"[BTab] Error extracting icon: {e}", flush=True)

    try:
        if hasattr(user32, 'SendMessageW'):
            SendMessageW = user32.SendMessageW
            SendMessageW.argtypes = [ctypes.wintypes.HWND, ctypes.c_uint, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM]
            SendMessageW.restype = ctypes.c_void_p
            for icon_type in (2, 0, 1):
                hicon = SendMessageW(hwnd, 0x007F, icon_type, 0)
                if hicon:
                    pixmap = QtWin.fromHICON(hicon)
                    if not pixmap.isNull():
                        return pixmap
    except Exception as e:
        print(f"[BTab] Fallback WM_GETICON error: {e}", flush=True)

    try:
        if hasattr(user32, 'GetClassLongPtrW'):
            GetClassLongPtr = user32.GetClassLongPtrW
            GetClassLongPtr.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
            GetClassLongPtr.restype = ctypes.c_void_p
        else:
            GetClassLongPtr = user32.GetClassLongW
            GetClassLongPtr.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
            GetClassLongPtr.restype = ctypes.c_ulong

        for gcl in (-34, -14):
            hicon = GetClassLongPtr(hwnd, gcl)
            if hicon:
                pixmap = QtWin.fromHICON(hicon)
                if not pixmap.isNull():
                    return pixmap
    except Exception as e:
        print(f"[BTab] Fallback GetClassLong error: {e}", flush=True)

    return None

# ── Key helpers ───────────────────────────────────────────────────────────────
def _press(vk):   user32.keybd_event(vk, 0, 0, 0)
def _release(vk): user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)

def send_ctrl_tab():
    _press(VK_CONTROL);  time.sleep(0.02)
    _press(VK_TAB);      time.sleep(0.02)
    _release(VK_TAB);    time.sleep(0.02)
    _release(VK_CONTROL)

def send_ctrl_shift_tab():
    _press(VK_CONTROL);  time.sleep(0.02)
    _press(VK_SHIFT);    time.sleep(0.02)
    _press(VK_TAB);      time.sleep(0.02)
    _release(VK_TAB);    time.sleep(0.02)
    _release(VK_SHIFT);  time.sleep(0.02)
    _release(VK_CONTROL)

def send_ctrl_pageup():
    _press(VK_CONTROL);  time.sleep(0.02)
    _press(VK_PRIOR);    time.sleep(0.02)
    _release(VK_PRIOR);  time.sleep(0.02)
    _release(VK_CONTROL)

def send_ctrl_pagedown():
    _press(VK_CONTROL);  time.sleep(0.02)
    _press(VK_NEXT);     time.sleep(0.02)
    _release(VK_NEXT);   time.sleep(0.02)
    _release(VK_CONTROL)


# ── Circle button widget ──────────────────────────────────────────────────────
def lerp_color(c1: QColor, c2: QColor, t: float) -> QColor:
    r = c1.red()   + (c2.red()   - c1.red())   * t
    g = c1.green() + (c2.green() - c1.green()) * t
    b = c1.blue()  + (c2.blue()  - c1.blue())  * t
    a = c1.alpha() + (c2.alpha() - c1.alpha()) * t
    return QColor(int(r), int(g), int(b), int(a))

class BTabButton(QWidget):
    OUTER_R     = 26
    INNER_R     = 11
    WIDGET_SIZE = 56

    def __init__(self, parent):
        super().__init__(parent)
        self._p = parent
        self.setFixedSize(self.WIDGET_SIZE, self.WIDGET_SIZE)

        self._drag_pos   = QPoint()
        self._is_drag    = False
        self._hover_zone = None   # None | 'inner' | 'left' | 'right'
        self._press_zone = None

        # Animated transition progress states (0.0 to 1.0)
        self._hover_inner_val = 0.0
        self._hover_left_val  = 0.0
        self._hover_right_val = 0.0

        self._press_inner_val = 0.0
        self._press_left_val  = 0.0
        self._press_right_val = 0.0

        # Smooth active browser theme fade progress
        self._browser_active_val = 0.0

        self._pt = 0.0
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(28)

        self.setMouseTracking(True)

    def _tick(self):
        self._pt = (self._pt + 0.062) % (2 * math.pi)
        
        # Targets
        ti = 1.0 if self._hover_zone == 'inner' else 0.0
        tl = 1.0 if self._hover_zone == 'left' else 0.0
        tr = 1.0 if self._hover_zone == 'right' else 0.0

        tb = 1.0 if self._p.browser_active else 0.0

        # Interpolate progress (ease-out ~15% per step)
        self._hover_inner_val += (ti - self._hover_inner_val) * 0.15
        self._hover_left_val  += (tl - self._hover_left_val) * 0.15
        self._hover_right_val += (tr - self._hover_right_val) * 0.15

        self._browser_active_val += (tb - self._browser_active_val) * 0.12

        # Press states: snap to 1.0 on press, slowly decay on release for a smooth ripple trail
        for zone, attr in [('inner', '_press_inner_val'), ('left', '_press_left_val'), ('right', '_press_right_val')]:
            current = getattr(self, attr)
            if self._press_zone == zone:
                setattr(self, attr, 1.0)
            else:
                new_val = current - 0.07  # smooth decay over ~400ms
                if new_val < 0.0: new_val = 0.0
                setattr(self, attr, new_val)

        self.update()

    def _zone(self, pos):
        cx = cy = self.WIDGET_SIZE / 2
        dx, dy = pos.x() - cx, pos.y() - cy
        r = math.hypot(dx, dy)
        if r <= self.INNER_R:
            return 'inner'
        if r <= self.OUTER_R:
            return 'left' if dx < 0 else 'right'
        return None

    # ── Paint ─────────────────────────────────────────────────────────────────
    def paintEvent(self, _ev):
        try:
            self._paint_impl()
        except Exception as e:
            print(f"[BTab] paintEvent error: {e}", flush=True)

    def _paint_impl(self):
        p   = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        S   = self.WIDGET_SIZE
        cx  = cy = S / 2.0
        pls = 0.5 + 0.5 * math.sin(self._pt)
        bra = self._p.browser_active   # True = browser focused
        mid_r = (self.INNER_R + 2 + self.OUTER_R) / 2.0

        # Base colors for btabswitch (Deep Teal/Emerald theme)
        c_base  = QColor(20, 38, 32, 191)    # rgba(20, 38, 32, 0.75)
        c_hover = QColor(30, 58, 48, 217)    # rgba(30, 58, 48, 0.85)
        c_press = QColor(0, 180, 120, 204)   # rgba(0, 180, 120, 0.80)

        def get_zone_color(hover_val, press_val):
            c = lerp_color(c_base, c_hover, hover_val)
            c = lerp_color(c, c_press, press_val)
            return c

        p.setPen(Qt.NoPen)
        
        # Draw Left Half outer disc
        left_color = get_zone_color(self._hover_left_val, self._press_left_val)
        p.setBrush(QBrush(left_color))
        p.drawPie(QRectF(cx - self.OUTER_R, cy - self.OUTER_R, self.OUTER_R * 2, self.OUTER_R * 2), 90 * 16, 180 * 16)
        
        # Draw Right Half outer disc
        right_color = get_zone_color(self._hover_right_val, self._press_right_val)
        p.setBrush(QBrush(right_color))
        p.drawPie(QRectF(cx - self.OUTER_R, cy - self.OUTER_R, self.OUTER_R * 2, self.OUTER_R * 2), 270 * 16, 180 * 16)

        # ─ Vertical divider line in donut (shows left / right split) ─
        div = QPen(QColor(255, 255, 255, 12))
        div.setWidthF(1.0)
        div.setStyle(Qt.DashLine)
        p.setPen(div)
        ie = self.INNER_R + 2.5
        oe = self.OUTER_R - 1.0
        p.drawLine(QPointF(cx, cy - oe), QPointF(cx, cy - ie))
        p.drawLine(QPointF(cx, cy + ie), QPointF(cx, cy + oe))

        # ─ Separator ring (between inner circle and outer ring) ─
        sp = QPen(QColor(255, 255, 255, 15))
        sp.setWidthF(1.0)
        p.setPen(sp)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(cx, cy), self.INNER_R + 2, self.INNER_R + 2)

        # ─ Inner circle background ─
        inner_color = get_zone_color(self._hover_inner_val, self._press_inner_val)
        p.setBrush(QBrush(inner_color))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, cy), self.INNER_R, self.INNER_R)

        # ─ Inner circle content ─
        if bra:
            if self._p.browser_icon_pixmap:
                icon_sz = 18
                rx = cx - icon_sz / 2.0
                ry = cy - icon_sz / 2.0
                p.drawPixmap(QRectF(rx, ry, icon_sz, icon_sz), self._p.browser_icon_pixmap, QRectF(self._p.browser_icon_pixmap.rect()))
            else:
                sw = QPen(QColor(255, 255, 255, 180))
                sw.setWidthF(1.8)
                sw.setCapStyle(Qt.RoundCap)
                p.setPen(sw)
                sa = 4.0
                p.drawLine(QPointF(cx - sa, cy), QPointF(cx + sa, cy))
                p.drawLine(QPointF(cx - sa, cy), QPointF(cx - sa + 2.5, cy - 2.0))
                p.drawLine(QPointF(cx - sa, cy), QPointF(cx - sa + 2.5, cy + 2.0))
                p.drawLine(QPointF(cx + sa, cy), QPointF(cx + sa - 2.5, cy - 2.0))
                p.drawLine(QPointF(cx + sa, cy), QPointF(cx + sa - 2.5, cy + 2.0))

        # ─ Outer border (matching windowswitch look and lock states) ─
        is_locked = self._p.is_locked
        overall_hover = max(self._hover_left_val, self._hover_right_val, self._hover_inner_val)
        overall_press = max(self._press_left_val, self._press_right_val, self._press_inner_val)
        
        if is_locked:
            b_base  = QColor(255, 165, 0, 153)
            b_hover = QColor(255, 165, 0, 217)
            border_color = lerp_color(b_base, b_hover, overall_hover)
        else:
            b_base  = QColor(200, 255, 230, 38)   # rgba(200, 255, 230, 0.15)
            b_hover = QColor(0, 230, 150, 128)    # rgba(0, 230, 150, 0.50)
            b_press = QColor(0, 230, 150, 255)    # rgba(0, 230, 150, 1.00)
            border_color = lerp_color(b_base, b_hover, overall_hover)
            border_color = lerp_color(border_color, b_press, overall_press)

        b_pen = QPen(border_color)
        b_pen.setWidthF(2.0)
        p.setPen(b_pen)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(cx, cy), self.OUTER_R, self.OUTER_R)

        p.end()

    # ── Mouse events ──────────────────────────────────────────────────────────
    def mouseMoveEvent(self, event):
        z = self._zone(event.pos())
        if z != self._hover_zone:
            self._hover_zone = z
            self.update()

        if event.buttons() & Qt.LeftButton and not self._p.is_locked:
            diff = event.globalPos() - (self._p.frameGeometry().topLeft() + self._drag_pos)
            if diff.manhattanLength() > 5:
                self._is_drag = True
            if self._is_drag:
                self._p.move(event.globalPos() - self._drag_pos)
        self.update()
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            mods = event.modifiers()
            if mods & Qt.AltModifier:
                QApplication.quit(); return
            if mods & Qt.ShiftModifier:
                self._p.toggle_lock(); event.accept(); return
            self._drag_pos  = event.globalPos() - self._p.frameGeometry().topLeft()
            self._is_drag   = False
            self._press_zone = self._zone(event.pos())
            self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            pz = self._press_zone
            self._press_zone = None
            self.update()
            if not self._is_drag:
                z = self._zone(event.pos())
                if z == pz:
                    if z == 'inner':
                        self._p.do_switch()
                    elif z == 'left':
                        self._p.do_cycle_left()
                    elif z == 'right':
                        self._p.do_cycle_right()
            self._is_drag = False
        event.accept()

    def leaveEvent(self, _ev):
        self._hover_zone = None
        self.update()


# ── Main window ───────────────────────────────────────────────────────────────
class BTabWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint |
            Qt.Tool | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        S = BTabButton.WIDGET_SIZE
        self.setFixedSize(S, S)
        self.setWindowTitle("BTab Switcher")

        self._idle_op  = 0.50
        self._hover_op = 0.90
        self.setWindowOpacity(self._idle_op)

        self.is_locked      = False
        self.browser_active = False
        self._switch_dir    = 1   # 1 -> next inner click sends Ctrl+Shift+Tab
        self.last_hwnd      = None
        self.browser_icon_pixmap = None

        self._btn = BTabButton(self)
        self._btn.move(0, 0)

        # Lightweight fade (step-based, no QPropertyAnimation)
        self._fade_target = self._idle_op
        self._fade_timer  = QTimer(self)
        self._fade_timer.setInterval(16)   # ~60fps
        self._fade_timer.timeout.connect(self._fade_step)

        self.drag_pos = QPoint()
        self.setMouseTracking(True)

        # WS_EX_NOACTIVATE
        hwnd  = int(self.winId())
        style = _GetWindowLong(hwnd, GWL_EXSTYLE)
        _SetWindowLong(hwnd, GWL_EXSTYLE,
                       style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)

        # Browser poll
        self._poll = QTimer(self)
        self._poll.timeout.connect(self._poll_browser)
        self._poll.start(150)

        self._setup_tray()

    # ── Browser polling ───────────────────────────────────────────────────────
    def _poll_browser(self):
        try:
            hwnd = GetForegroundWindow()
            if hwnd and hwnd != int(self.winId()):
                br = is_browser(hwnd)
                if br:
                    if hwnd != self.last_hwnd or self.browser_icon_pixmap is None:
                        print(f"[BTab] Browser: '{get_title(hwnd)}'", flush=True)
                        self.last_hwnd = hwnd
                        self.browser_icon_pixmap = get_window_icon(hwnd)
                if br != self.browser_active:
                    self.browser_active = br
                self._btn.update()
        except Exception as e:
            print(f"[BTab] poll error: {e}", flush=True)

    # ── Opacity ───────────────────────────────────────────────────────────────
    def _fade_to(self, target: float):
        self._fade_target = target
        if not self._fade_timer.isActive():
            self._fade_timer.start()

    def _fade_step(self):
        cur = self.windowOpacity()
        diff = self._fade_target - cur
        if abs(diff) < 0.02:
            self.setWindowOpacity(self._fade_target)
            self._fade_timer.stop()
        else:
            self.setWindowOpacity(cur + diff * 0.15)  # ease-out

    def enterEvent(self, e):
        self._fade_to(self._hover_op); super().enterEvent(e)

    def leaveEvent(self, e):
        self._fade_to(self._idle_op); super().leaveEvent(e)

    # ── Focus helper ──────────────────────────────────────────────────────────
    def _focus_browser(self):
        h = self.last_hwnd
        if h and IsWindow(h):
            if IsIconic(h):
                ShowWindow(h, SW_RESTORE)
            SetForegroundWindow(h)
            time.sleep(0.05)

    # ── Actions ───────────────────────────────────────────────────────────────
    def do_switch(self):
        """Toggle between two tabs (inner circle)."""
        self._focus_browser()
        if self._switch_dir == 1:
            print("[BTab] Switch → Ctrl+PageUp", flush=True)
            send_ctrl_pageup()
            self._switch_dir = -1
        else:
            print("[BTab] Switch → Ctrl+PageDown", flush=True)
            send_ctrl_pagedown()
            self._switch_dir = 1

    def do_cycle_left(self):
        print("[BTab] Cycle Left ←", flush=True)
        self._focus_browser()
        send_ctrl_pageup()
        self._switch_dir = -1

    def do_cycle_right(self):
        print("[BTab] Cycle Right →", flush=True)
        self._focus_browser()
        send_ctrl_pagedown()
        self._switch_dir = 1

    def toggle_lock(self):
        self.is_locked = not self.is_locked
        s = "locked" if self.is_locked else "unlocked"
        print(f"[BTab] {s}", flush=True)
        self._tray.showMessage("BTab Switcher", f"Position {s}.",
                               QSystemTrayIcon.Information, 1500)

    # ── Drag (fallback on widget background) ──────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self.is_locked:
            self.drag_pos = event.globalPos() - self.frameGeometry().topLeft()
        event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and not self.is_locked:
            self.move(event.globalPos() - self.drag_pos)
        event.accept()

    def mouseReleaseEvent(self, event): event.accept()

    # ── Tray ──────────────────────────────────────────────────────────────────
    def _setup_tray(self):
        pix = QPixmap(16, 16)
        pix.fill(Qt.transparent)
        pp = QPainter(pix)
        pp.setRenderHint(QPainter.Antialiasing)
        pp.setBrush(QBrush(QColor(0, 210, 100)))
        pp.setPen(Qt.NoPen)
        pp.drawEllipse(2, 2, 12, 12)
        pp.end()

        self._tray = QSystemTrayIcon(QIcon(pix), self)
        self._tray.setToolTip("BTab Switcher")

        menu = QMenu()
        for txt in ("● Inner circle  — Switch (last ↔ current tab)",
                    "◀ Outer left    — Cycle ← (Ctrl+Shift+Tab)",
                    "▶ Outer right   — Cycle → (Ctrl+Tab)"):
            a = QAction(txt, self); a.setEnabled(False); menu.addAction(a)
        menu.addSeparator()

        tv = QAction("Hide / Show", self)
        tv.triggered.connect(self._toggle_vis)
        menu.addAction(tv)

        la = QAction("Toggle Lock", self)
        la.triggered.connect(self.toggle_lock)
        menu.addAction(la)
        menu.addSeparator()

        qa = QAction("Quit", self)
        qa.triggered.connect(QApplication.quit)
        menu.addAction(qa)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(
            lambda r: self._toggle_vis() if r == QSystemTrayIcon.Trigger else None)
        self._tray.show()

    def _toggle_vis(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()


# ── Entry ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app.setQuitOnLastWindowClosed(False)

    w = BTabWidget()
    scr = QApplication.primaryScreen().geometry()
    w.move(scr.width() - 80, scr.height() - 180)
    w.show()

    sys.exit(app.exec_())
