"""TeamSpeak 3 Overlay — PySide6 overlay for TeamSpeak 3 ClientQuery API."""
from __future__ import annotations

import sys, json, math, socket, threading, time, traceback
from collections import deque
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (
    Qt, QTimer, QThread, Signal, QObject, QPropertyAnimation,
    QEasingCurve, QMetaObject, Q_ARG
)
from PySide6.QtGui import (
    QColor, QPainter, QPainterPath, QBrush, QPen, QFont,
    QLinearGradient, QPixmap, QIcon, QCursor, QRadialGradient
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QFrame, QVBoxLayout, QHBoxLayout,
    QScrollArea, QPushButton, QCheckBox, QSpinBox, QLineEdit,
    QListWidget, QListWidgetItem, QDialog, QTextEdit, QSlider,
    QSystemTrayIcon, QMenu, QGraphicsOpacityEffect, QColorDialog
)

try:
    from pynput import keyboard as pynput_keyboard
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False

try:
    import ctypes
    WINDOWS_API_AVAILABLE = (sys.platform == "win32")
except ImportError:
    WINDOWS_API_AVAILABLE = False


TS3_HOST    = "localhost"
CONFIG_FILE = Path.home() / ".ts3overlay_config.json"
LOG_FILE    = Path.home() / "ts3overlay_log.txt"
_BASE_DIR   = (Path(sys.executable).parent
               if getattr(sys, "frozen", False) else Path(__file__).parent)
ICONS_DIR   = _BASE_DIR / "icons"


DEFAULT_CFG: dict = {
    "api_key":              "",
    "port":                 25639,
    "opacity":              0.90,
    "font_size":            10,
    "bg_dim":               0.0,
    "hotkey":               "f9",
    "hotkey_config":        "f10",
    "hotkey_quit":          "",
    "hotkey_notifications": "f8",
    "hide_alone":           True,
    "show_channel_msg":     True,
    "show_private_msg":     True,
    "show_whisper_msg":     True,
    "toast_seconds":        5,
    "win_x":                20,
    "win_y":                20,
    "whispers_x":           40,
    "whispers_y":           40,
    "toast_chan_x":         -1,
    "toast_chan_y":         -1,
    "toast_priv_x":         -1,
    "toast_priv_y":         -1,
    "border_color":         "#7c6af5",
    "status_icons":         True,
    "join_color":           "#4ade80",
    "leave_color":          "#f87171",
    "move_color":           "#fbbf24",
    "anim_seconds":         3,
    "click_through":        False,
    "show_all_users":       False,
    "max_notifications":    50,
    "silent_join_leave":    False,
    "blur_behind":          True,
    "pulse_on_talk":        True,
    "keep_on_top_ms":       500,
}


BG       = "#09090f"
BG2      = "#0f0f1a"
PANEL    = "#13131f"
PANEL2   = "#1a1a2e"
BORDER   = "#2a2a45"
ACCENT   = "#7c6af5"
ACCENT2  = "#a78bfa"
SPEAKING = "#4ade80"
MUTED    = "#f87171"
DEAF_C   = "#fbbf24"
MOVE_C   = "#fbbf24"
FG       = "#e2e8f0"
DIM      = "#4a5568"
DIM2     = "#64748b"
SEP      = "#1e1e30"
PRIV_C   = "#c084fc"
CHAN_C   = "#34d399"
WHIS_C   = "#f472b6"
DANGER   = "#f87171"
JOIN_C   = "#4ade80"
LEAVE_C  = "#f87171"


def log(msg: str, level: str = "INFO"):
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] [{level}] {msg}\n")
    except:
        pass


def load_config() -> dict:
    cfg = dict(DEFAULT_CFG)
    if CONFIG_FILE.exists():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
        except:
            pass
    return cfg

def save_config(cfg: dict):
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except:
        pass

def reset_config() -> dict:
    cfg = dict(DEFAULT_CFG)
    if CONFIG_FILE.exists():
        try:
            saved = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            cfg["api_key"] = saved.get("api_key", "")
            cfg["port"]    = saved.get("port", 25639)
        except:
            pass
    save_config(cfg)
    return cfg


_WS_EX_LAYERED     = 0x00080000
_WS_EX_TRANSPARENT = 0x00000020
_WS_EX_NOACTIVATE  = 0x08000000
_GWL_EXSTYLE       = -20
_SWP_NOMOVE        = 0x0002
_SWP_NOSIZE        = 0x0001
_SWP_FRAMECHANGED  = 0x0020
_SWP_NOACTIVATE    = 0x0010
_HWND_TOPMOST      = -1
_DWM_BB_ENABLE     = 0x00000001

def _u32():
    return ctypes.windll.user32 if WINDOWS_API_AVAILABLE else None

def set_click_through(hwnd, enable: bool):
    u = _u32()
    if not u or not hwnd: return
    try:
        ex = u.GetWindowLongW(hwnd, _GWL_EXSTYLE)
        ex = (ex | _WS_EX_LAYERED | _WS_EX_TRANSPARENT) if enable else (ex & ~_WS_EX_TRANSPARENT)
        u.SetWindowLongW(hwnd, _GWL_EXSTYLE, ex)
        u.SetWindowPos(hwnd, 0, 0, 0, 0, 0, _SWP_NOMOVE | _SWP_NOSIZE | _SWP_FRAMECHANGED)
    except Exception as e:
        log(f"set_click_through: {e}", "WARN")

def set_noactivate(hwnd):
    u = _u32()
    if not u or not hwnd: return
    try:
        ex = u.GetWindowLongW(hwnd, _GWL_EXSTYLE)
        u.SetWindowLongW(hwnd, _GWL_EXSTYLE, ex | _WS_EX_NOACTIVATE)
    except Exception as e:
        log(f"set_noactivate: {e}", "WARN")

def force_topmost(hwnd):
    u = _u32()
    if not u or not hwnd: return
    try:
        u.SetWindowPos(hwnd, _HWND_TOPMOST, 0, 0, 0, 0,
                       _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE)
    except:
        pass

def enable_blur_behind(hwnd, enable=True):
    if not WINDOWS_API_AVAILABLE or not hwnd: return
    try:
        dwm = ctypes.windll.dwmapi
        class BB(ctypes.Structure):
            _fields_ = [("dwFlags", ctypes.c_uint32), ("fEnable", ctypes.c_bool),
                        ("hRgnBlur", ctypes.c_void_p),
                        ("fTransitionOnMaximized", ctypes.c_bool)]
        bb = BB(); bb.dwFlags = _DWM_BB_ENABLE; bb.fEnable = enable; bb.hRgnBlur = None
        dwm.DwmEnableBlurBehindWindow(hwnd, ctypes.byref(bb))
    except:
        pass


_ICON_CACHE: dict[str, QPixmap | None] = {}

def load_icon(name: str, size: int = 16) -> QPixmap | None:
    key = f"{name}:{size}"
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]
    for ext in ("png", "svg", "ico"):
        path = ICONS_DIR / f"{name}.{ext}"
        if path.exists():
            pix = QPixmap(str(path))
            if not pix.isNull():
                pix = pix.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
                _ICON_CACHE[key] = pix
                return pix
    _ICON_CACHE[key] = None
    return None


APP_QSS = f"""
QWidget {{
    background: {BG};
    color: {FG};
    font-family: 'Segoe UI', 'SF Pro Display', 'Helvetica Neue', sans-serif;
    font-size: 13px;
}}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{
    background: transparent; width: 5px; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER}; border-radius: 3px; min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: {ACCENT}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
QLineEdit {{
    background: {PANEL2}; color: {FG}; border: 1.5px solid {BORDER};
    border-radius: 8px; padding: 8px 12px; font-size: 13px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus {{ border-color: {ACCENT}; }}
QCheckBox {{ spacing: 8px; color: {FG}; }}
QCheckBox::indicator {{
    width: 18px; height: 18px; border-radius: 5px;
    border: 1.5px solid {BORDER}; background: {PANEL2};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT}; border-color: {ACCENT};
}}
QCheckBox::indicator:hover {{ border-color: {ACCENT2}; }}
QSlider::groove:horizontal {{
    height: 4px; background: {PANEL2}; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    width: 16px; height: 16px; margin: -6px 0;
    background: {ACCENT}; border-radius: 8px;
    border: 2px solid {BG};
}}
QSlider::handle:horizontal:hover {{ background: {ACCENT2}; }}
QSlider::sub-page:horizontal {{
    background: {ACCENT}; border-radius: 2px;
}}
QMenu {{
    background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px; padding: 6px;
}}
QMenu::item {{ padding: 8px 20px; border-radius: 6px; }}
QMenu::item:selected {{ background: {ACCENT}; color: white; }}
QToolTip {{
    background: {PANEL}; color: {FG}; border: 1px solid {BORDER}; border-radius: 6px; padding: 4px 8px;
}}
"""


def mk_btn(text: str, primary=False, danger=False, small=False) -> QPushButton:
    btn = QPushButton(text)
    fs  = "11px" if small else "13px"
    px  = "12px" if small else "20px"
    py  = "5px"  if small else "9px"
    if primary:
        bg, hov, fg = ACCENT,  ACCENT2, "#fff"
    elif danger:
        bg, hov, fg = DANGER,  "#ef4444", "#fff"
    else:
        bg, hov, fg = PANEL2,  BORDER,  DIM2
    btn.setStyleSheet(f"""
        QPushButton {{
            background:{bg}; color:{fg}; border:none;
            border-radius:8px; padding:{py} {px};
            font-size:{fs}; font-weight:{'700' if primary else '400'};
        }}
        QPushButton:hover {{ background:{hov}; color:{'white' if primary or danger else FG}; }}
        QPushButton:pressed {{ opacity:0.8; }}
    """)
    btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    return btn

def mk_div() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet(f"background:{BORDER}; max-height:1px; border:none; margin:0;")
    return f


class TS3Connection:
    def __init__(self, host, port, api_key):
        self.host=host; self.port=port; self.api_key=api_key
        self.sock=None; self._cmd_lock=threading.Lock(); self._buf=""

    def connect(self):
        log(f"Conectando {self.host}:{self.port}")
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(8); self.sock.connect((self.host, self.port))
        self._buf=""; time.sleep(0.25); self.sock.settimeout(0.5)
        try: self.sock.recv(8192)
        except socket.timeout: pass
        resp = self._cmd("auth apikey="+self.api_key)
        if "error id=0" not in resp:
            raise ConnectionError(f"Auth fallida: {resp.strip()}")
        log("Auth OK")

    def disconnect(self):
        try:
            if self.sock: self.sock.close()
        except: pass
        self.sock=None; self._buf=""

    def read_line(self, timeout=1.0):
        deadline = time.time()+timeout
        while time.time()<deadline:
            if "\n" in self._buf:
                line, self._buf = self._buf.split("\n", 1)
                line = line.strip()
                if line: return line
                continue
            self.sock.settimeout(max(0.05, deadline-time.time()))
            try:
                chunk = self.sock.recv(65536)
                if not chunk: raise ConnectionError("Socket cerrado")
                self._buf += chunk.decode("utf-8", errors="replace")
            except socket.timeout: pass
        return None

    def _recv_until_ok(self, timeout=8.0):
        deadline=time.time()+timeout; lines=[]; local_buf=""
        while time.time()<deadline:
            self.sock.settimeout(max(0.05, deadline-time.time()))
            try:
                chunk=self.sock.recv(65536)
                if not chunk: raise ConnectionError("Socket cerrado")
                local_buf+=chunk.decode("utf-8", errors="replace")
            except socket.timeout: pass
            while "\n" in local_buf:
                line, local_buf = local_buf.split("\n", 1)
                line=line.strip()
                if not line: continue
                if line.startswith("notify"):
                    self._buf=line+"\n"+self._buf; continue
                lines.append(line)
                if line.startswith("error id="): return "\n".join(lines)
        return "\n".join(lines)

    def _cmd(self, command):
        with self._cmd_lock:
            self.sock.setblocking(True)
            self.sock.sendall((command+"\n").encode("utf-8"))
            return self._recv_until_ok()

    @staticmethod
    def unescape(s):
        return (s.replace("\\s"," ").replace("\\p","|")
                 .replace("\\n","\n").replace("\\/","/").replace("\\\\","\\"))

    @classmethod
    def parse(cls, raw):
        r={}
        for t in raw.strip().split():
            if "=" in t:
                k,_,v=t.partition("="); r[k]=cls.unescape(v)
        return r

    def whoami(self):
        resp=self._cmd("whoami")
        for line in resp.splitlines():
            if "clid=" in line and not line.startswith("error"):
                return self.parse(line)
        return {}

    def clientlist_voice_info(self):
        resp=self._cmd("clientlist -voice -info -groups"); clients=[]
        for line in resp.splitlines():
            if "clid=" not in line or line.startswith("error"): continue
            for entry in line.split("|"):
                entry=entry.strip()
                if "clid=" in entry: clients.append(self.parse(entry))
        return clients

    def clientinfo(self, clid):
        resp=self._cmd(f"clientinfo clid={clid}")
        for line in resp.splitlines():
            if "client_nickname=" in line and not line.startswith("error"):
                return self.parse(line)
        return {}

    def channel_name(self, cid):
        resp=self._cmd("channellist")
        for line in resp.splitlines():
            if "cid=" not in line or line.startswith("error"): continue
            for entry in line.split("|"):
                d=self.parse(entry)
                if d.get("cid")==str(cid): return d.get("channel_name","")
        return ""

    def server_name(self):
        resp=self._cmd("serverinfo")
        for line in resp.splitlines():
            if line.startswith("virtualserver_name="):
                return self.parse(line).get("virtualserver_name","")
        return ""

    def channelgrouplist(self):
        groups={}
        try:
            resp=self._cmd("channelgrouplist")
            for line in resp.splitlines():
                if "cgid=" in line and not line.startswith("error"):
                    for entry in line.split("|"):
                        d=self.parse(entry)
                        if d.get("cgid"): groups[d["cgid"]]=d.get("name","")
        except: pass
        return groups

    def subscribe_events(self):
        for ev in ["notifytalkstatuschange","notifyclientmoved","notifycliententerview",
                   "notifyclientleftview","notifyconnectstatuschange","notifyclientupdated",
                   "notifytextmessage","notifywhisper"]:
            resp=self._cmd(f"clientnotifyregister schandlerid=0 event={ev}")
            log(f"Sub {ev}: {resp.strip()}")


class ChannelState:
    def __init__(self):
        self._lock=threading.Lock()
        self.my_clid=""; self.my_cid=""; self.ch_name=""; self.server_name=""
        self.clients={}; self.group_names={}

    def snapshot(self):
        with self._lock:
            return (list(self.clients.values()), self.ch_name,
                    self.server_name, dict(self.group_names), self.my_cid)

    def set_group_names(self, n):
        with self._lock: self.group_names=n

    def set_me(self, clid, cid, ch, srv):
        with self._lock:
            self.my_clid=clid; self.my_cid=cid
            self.ch_name=ch; self.server_name=srv; self.clients={}

    def set_clients(self, clients):
        with self._lock:
            self.clients={c["clid"]:c for c in clients if "clid" in c}

    def upsert(self, clid, data):
        with self._lock:
            if clid in self.clients: self.clients[clid].update(data)
            else: self.clients[clid]=data

    def remove(self, clid):
        with self._lock: self.clients.pop(clid, None)

    def set_talking(self, clid, talking):
        with self._lock:
            if clid in self.clients:
                self.clients[clid]["client_flag_talking"]="1" if talking else "0"

    def set_whisper_talking(self, clid, talking):
        with self._lock:
            if clid in self.clients:
                self.clients[clid]["client_flag_whisper"]="1" if talking else "0"

    def get_my_cid(self):
        with self._lock: return self.my_cid

    def get_my_clid(self):
        with self._lock: return self.my_clid

    def has(self, clid):
        with self._lock: return clid in self.clients


class Signals(QObject):
    update_users    = Signal(list, str, str, dict, str)
    show_message    = Signal(str, str, str, str)
    show_error      = Signal(str)
    notify_join     = Signal(str, str)
    notify_leave    = Signal(str, str)
    notify_moved    = Signal(str, str)
    whisper_talk    = Signal(str, bool)
    whisper_leave   = Signal(str)
    channel_changed = Signal()
    notif_message   = Signal(str, str, str)
    open_settings   = Signal()


class MessageToast(QWidget):
    _active: list["MessageToast"] = []
    _MARGIN = 50
    _HEIGHT = 86

    _cfg: dict = {}

    def __init__(self, sender: str, text: str, msg_type: str, seconds: int):
        super().__init__(None)
        MessageToast._active.append(self)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.BypassWindowManagerHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(320, self._HEIGHT)

        self._msg_type = msg_type
        color = PRIV_C if msg_type=="private" else CHAN_C if msg_type=="channel" else WHIS_C
        kind  = "PRIVADO" if msg_type=="private" else "CANAL" if msg_type=="channel" else "WHISPER"

        root_l = QVBoxLayout(self); root_l.setContentsMargins(0,0,0,0)
        card = QFrame(); card.setStyleSheet(f"""
            QFrame{{background:{PANEL};border:1px solid {color};border-radius:10px;}}
        """)
        root_l.addWidget(card)
        cl = QVBoxLayout(card); cl.setContentsMargins(0,0,0,0); cl.setSpacing(0)
        top = QFrame(); top.setFixedHeight(3)
        top.setStyleSheet(f"background:{color};border-radius:10px 10px 0 0;border:none;")
        cl.addWidget(top)
        body = QWidget(); body.setStyleSheet("background:transparent;border:none;")
        bl = QVBoxLayout(body); bl.setContentsMargins(14,10,14,10); bl.setSpacing(4)
        hr = QHBoxLayout()
        pill = QLabel(kind); pill.setStyleSheet(f"background:{color};color:white;border-radius:4px;padding:1px 7px;font-size:10px;font-weight:700;")
        sl = QLabel(sender); sl.setStyleSheet(f"color:{FG};font-weight:600;font-size:13px;")
        xl = QLabel("✕"); xl.setStyleSheet(f"color:{DIM2};font-size:12px;")
        xl.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        xl.mousePressEvent = lambda e: self._dismiss()
        hr.addWidget(pill); hr.addSpacing(8); hr.addWidget(sl,1); hr.addWidget(xl)
        bl.addLayout(hr)
        if text:
            sep=QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet(f"background:{BORDER};max-height:1px;border:none;")
            ml = QLabel(text[:80]+("…" if len(text)>80 else ""))
            ml.setWordWrap(True); ml.setStyleSheet(f"color:{DIM2};font-size:12px;")
            bl.addWidget(sep); bl.addWidget(ml)
        cl.addWidget(body)

        self._position(); self.setWindowOpacity(0.0); self.show()
        self._in = QPropertyAnimation(self, b"windowOpacity")
        self._in.setDuration(180); self._in.setStartValue(0.0); self._in.setEndValue(0.95)
        self._in.setEasingCurve(QEasingCurve.Type.OutCubic); self._in.start()
        if WINDOWS_API_AVAILABLE:
            QTimer.singleShot(60, lambda: set_noactivate(int(self.winId())))
        self._t = QTimer(self); self._t.setSingleShot(True)
        self._t.timeout.connect(self._dismiss); self._t.start(seconds*1000)
        self.mousePressEvent = lambda e: self._dismiss()

    def _position(self):
        scr = QApplication.primaryScreen().geometry()
        try: idx = MessageToast._active.index(self)
        except ValueError: idx=0
        cfg = MessageToast._cfg

        if self._msg_type == "channel":
            bx = cfg.get("toast_chan_x", -1); by = cfg.get("toast_chan_y", -1)
        elif self._msg_type == "private":
            bx = cfg.get("toast_priv_x", -1); by = cfg.get("toast_priv_y", -1)
        else:
            bx = -1; by = -1
        if bx != -1 and by != -1:

            self.move(bx, by - idx*(self._HEIGHT+8))
        else:
            self.move(scr.right()-320-self._MARGIN,
                      scr.bottom()-self._MARGIN-(self._HEIGHT+8)*(idx+1))

    def _dismiss(self):
        self._t.stop()
        try: MessageToast._active.remove(self)
        except ValueError: pass
        self.hide(); self.deleteLater()
        for t in MessageToast._active:
            try: t._position()
            except: pass

    def paintEvent(self, e): pass


class WhispersWindow(QWidget):
    _instance: "WhispersWindow|None" = None
    _MAX = 8

    def __init__(self, cfg: dict):
        super().__init__(None)
        WhispersWindow._instance = self
        self._cfg=cfg; self._entries=[]; self._talking=set(); self._drag=None
        self._timer=QTimer(self); self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._dismiss)

        self._watchdog=QTimer(self); self._watchdog.timeout.connect(self._watchdog_tick)
        self._watchdog.start(15000)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint|
                            Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.move(cfg.get("whispers_x",40), cfg.get("whispers_y",40))
        root=QVBoxLayout(self); root.setContentsMargins(0,0,0,0)
        card=QFrame(); card.setStyleSheet(f"QFrame{{background:{PANEL};border:1px solid {WHIS_C};border-radius:10px;}}")
        root.addWidget(card)
        cl=QVBoxLayout(card); cl.setContentsMargins(0,0,0,0); cl.setSpacing(0)
        top=QFrame(); top.setFixedHeight(3); top.setStyleSheet(f"background:{WHIS_C};border-radius:10px 10px 0 0;border:none;"); cl.addWidget(top)
        inner=QWidget(); inner.setStyleSheet("background:transparent;border:none;")
        il=QVBoxLayout(inner); il.setContentsMargins(12,8,12,8); il.setSpacing(4)
        hr=QHBoxLayout(); hr.addWidget(QLabel("⬤  Whispers", styleSheet=f"color:{WHIS_C};font-weight:700;font-size:12px;"),1)
        xl=QLabel("✕",styleSheet=f"color:{DIM2};font-size:11px;"); xl.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        xl.mousePressEvent=lambda e: self._dismiss(); hr.addWidget(xl); il.addLayout(hr)
        sep=QFrame(); sep.setFrameShape(QFrame.Shape.HLine); sep.setStyleSheet(f"background:{BORDER};max-height:1px;border:none;"); il.addWidget(sep)
        self._el=QVBoxLayout(); self._el.setSpacing(2); il.addLayout(self._el)
        cl.addWidget(inner); self.adjustSize(); self.show()
        if WINDOWS_API_AVAILABLE:
            def _w32():
                hwnd=int(self.winId()); set_noactivate(hwnd)
                set_click_through(hwnd, not self._cfg.get("click_through",False))
            QTimer.singleShot(60, _w32)

    def mousePressEvent(self,e):
        if not self._cfg.get("click_through",False): return
        if e.button()==Qt.MouseButton.LeftButton:
            self._drag=e.globalPosition().toPoint()-self.frameGeometry().topLeft()
    def mouseMoveEvent(self,e):
        if not self._cfg.get("click_through",False): return
        if self._drag and e.buttons()==Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint()-self._drag)
    def mouseReleaseEvent(self,e):
        if not self._cfg.get("click_through",False): return
        if self._drag:
            self._drag=None; self._cfg["whispers_x"]=self.x(); self._cfg["whispers_y"]=self.y(); save_config(self._cfg)

    def add_whisper(self, clid, sender, text):
        self._timer.stop()
        for e in self._entries:
            if e["clid"]==clid:
                if text and e["txt"]: e["txt"].setText(text[:60]+("…" if len(text)>60 else ""))
                self._upd_color(e, True); return
        if len(self._entries)>=self._MAX:
            old=self._entries.pop(0)
            try: self._el.removeWidget(old["w"]); old["w"].deleteLater()
            except: pass
        row=self._mk_row(clid,sender,text,True); self._entries.append(row)
        self._el.addWidget(row["w"]); self.adjustSize()

    def _mk_row(self, clid, sender, text, talking):
        c=WHIS_C if talking else DIM2
        w=QWidget(); w.setStyleSheet("background:transparent;")
        rl=QHBoxLayout(w); rl.setContentsMargins(0,4,0,4); rl.setSpacing(6)
        bar=QFrame(); bar.setFixedWidth(3); bar.setStyleSheet(f"background:{c};border-radius:2px;"); rl.addWidget(bar)

        icon_lbl=QLabel(); icon_lbl.setFixedSize(14,14); icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pix=load_icon("whisp",13)
        if pix:
            icon_lbl.setPixmap(pix); icon_lbl.setText("")
        else:
            icon_lbl.setText("●"); icon_lbl.setStyleSheet(f"color:{WHIS_C};font-size:9px;")
        rl.addWidget(icon_lbl)
        vl=QVBoxLayout(); vl.setSpacing(0); vl.setContentsMargins(0,0,0,0)
        nl=QLabel(sender); nl.setStyleSheet(f"color:{c};font-weight:600;font-size:12px;"); vl.addWidget(nl)
        tl=None
        if text and text.strip():
            tl=QLabel(text[:60]+("…" if len(text)>60 else ""))
            tl.setStyleSheet(f"color:{DIM2};font-size:11px;"); vl.addWidget(tl)
        rl.addLayout(vl,1)
        return {"clid":clid,"w":w,"bar":bar,"icon":icon_lbl,"nl":nl,"txt":tl,"talking":talking,"last_talk_ts":time.time()}

    def _upd_color(self, e, talking):
        c=WHIS_C if talking else DIM2
        try:
            e["bar"].setStyleSheet(f"background:{c};border-radius:2px;")
            e["nl"].setStyleSheet(f"color:{c};font-weight:600;font-size:12px;")
            e["talking"]=talking
        except: pass

    def on_talk(self, clid, talking):
        for e in self._entries:
            if e["clid"]==clid:
                self._upd_color(e, talking)
                if not talking: e["last_talk_ts"] = time.time()
                break
        else: return
        if talking: self._talking.add(clid); self._timer.stop()
        else:
            self._talking.discard(clid)
            if not self._talking: self._timer.start(self._cfg.get("toast_seconds",5)*1000)

    def update_name(self, clid, name):
        for e in self._entries:
            if e["clid"]==clid:
                try: e["nl"].setText(name)
                except: pass; break

    def remove_entry(self, clid):
        
        for e in list(self._entries):
            if e["clid"]==clid:
                self._entries.remove(e)
                self._talking.discard(clid)
                try: self._el.removeWidget(e["w"]); e["w"].deleteLater()
                except: pass
                break
        self.adjustSize()

        if not self._entries:
            self._timer.stop(); self._dismiss()
        elif not self._talking:
            self._timer.start(self._cfg.get("toast_seconds",5)*1000)

    def _watchdog_tick(self):
        
        now = time.time()
        stale = [e["clid"] for e in self._entries
                 if not e.get("talking", False)
                 and (now - e.get("last_talk_ts", now)) > 20]
        for clid in stale:
            self.remove_entry(clid)

    def _dismiss(self):
        self._timer.stop()
        self._watchdog.stop()
        if WhispersWindow._instance is self: WhispersWindow._instance=None
        self.hide(); self.deleteLater()

    def paintEvent(self, e): pass


class UserRow(QWidget):
    """Una fila de usuario en el overlay con soporte para íconos y animaciones."""
    def __init__(self, clid, name, speaking, muted, deaf, cfg, parent=None, whispering=False):
        super().__init__(parent)
        self._cfg=cfg; self._speaking=speaking; self._muted=muted; self._deaf=deaf
        self._whispering=whispering
        self.setStyleSheet("background:transparent;")
        self._effect=QGraphicsOpacityEffect(self); self.setGraphicsEffect(self._effect)
        self._effect.setOpacity(0.0)
        self._in_anim=QPropertyAnimation(self._effect, b"opacity")
        self._in_anim.setDuration(250); self._in_anim.setStartValue(0.0)
        self._in_anim.setEndValue(1.0); self._in_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        layout=QHBoxLayout(self); layout.setContentsMargins(0,3,0,3); layout.setSpacing(8)

        self._bar=QFrame(); self._bar.setFixedWidth(3); self._bar.setFixedHeight(20)
        self._bar.setStyleSheet(f"border-radius:2px;")
        layout.addWidget(self._bar)


        self._icon_lbl=QLabel()
        self._icon_lbl.setFixedSize(16,16)
        self._icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._icon_lbl)

        self._name_lbl=QLabel(name[:28])
        fs=cfg.get("font_size",10)+2
        self._name_lbl.setStyleSheet(f"font-size:{fs}px;")
        layout.addWidget(self._name_lbl,1)

        self._refresh_style()
        self._in_anim.start()

    def _status_color(self):
        if self._whispering: return WHIS_C
        if self._speaking: return SPEAKING
        if self._muted or self._deaf: return DIM
        return FG

    def _refresh_style(self):
        c=self._status_color()
        self._bar.setStyleSheet(f"background:{c};border-radius:2px;")
        self._name_lbl.setStyleSheet(f"color:{c};font-size:{self._cfg.get('font_size',10)+2}px;")

        icon_pix=None
        if self._whispering:
            icon_pix=load_icon("whisp",14)
        elif self._speaking:
            icon_pix=load_icon("speaking",14)
        elif self._deaf:
            icon_pix=load_icon("deaf",14)
        elif self._muted:
            icon_pix=load_icon("muted",14)
        if icon_pix:
            self._icon_lbl.setPixmap(icon_pix)
            self._icon_lbl.setText("")
            self._icon_lbl.setStyleSheet("")
        else:
            self._icon_lbl.setPixmap(QPixmap())
            if self._whispering:

                self._icon_lbl.setText("●"); self._icon_lbl.setStyleSheet(f"color:{WHIS_C};font-size:10px;")
            elif self._speaking:
                self._icon_lbl.setText("◀"); self._icon_lbl.setStyleSheet(f"color:{SPEAKING};font-size:11px;")
            elif self._deaf:
                self._icon_lbl.setText("⊘"); self._icon_lbl.setStyleSheet(f"color:{DEAF_C};font-size:11px;")
            elif self._muted:
                self._icon_lbl.setText("⊗"); self._icon_lbl.setStyleSheet(f"color:{MUTED};font-size:11px;")
            else:
                self._icon_lbl.setText(""); self._icon_lbl.setStyleSheet("")

    def update_state(self, speaking, muted, deaf, name=None, whispering=False):
        self._speaking=speaking; self._muted=muted; self._deaf=deaf
        self._whispering=whispering
        if name: self._name_lbl.setText(name[:28])
        self._refresh_style()

    def flash_join(self, color, secs):
        
        orig_name=self._name_lbl.text().replace(" ↗","")
        self._name_lbl.setText(orig_name+" ↗")
        self._bar.setStyleSheet(f"background:{color};border-radius:2px;")
        self._name_lbl.setStyleSheet(f"color:{color};font-size:{self._cfg.get('font_size',10)+2}px;font-weight:600;")
        self._icon_lbl.setText("↗"); self._icon_lbl.setStyleSheet(f"color:{color};font-size:12px;font-weight:700;")
        QTimer.singleShot(secs*1000, self._restore_join)

    def _restore_join(self):
        name=self._name_lbl.text().replace(" ↗","")
        self._name_lbl.setText(name); self._refresh_style()

    def flash_leave(self, color, secs):
        
        orig=self._name_lbl.text().replace(" ↙","")
        self._name_lbl.setText(orig+" ↙")
        self._bar.setStyleSheet(f"background:{color};border-radius:2px;")
        self._name_lbl.setStyleSheet(f"color:{color};font-size:{self._cfg.get('font_size',10)+2}px;")
        self._icon_lbl.setText("↙"); self._icon_lbl.setStyleSheet(f"color:{color};font-size:12px;font-weight:700;")

    def flash_move(self, color):
        
        orig=self._name_lbl.text().replace(" ⟳","")
        self._name_lbl.setText(orig+" ⟳")
        self._bar.setStyleSheet(f"background:{color};border-radius:2px;")
        self._name_lbl.setStyleSheet(f"color:{color};font-size:{self._cfg.get('font_size',10)+2}px;")
        self._icon_lbl.setText("⟳"); self._icon_lbl.setStyleSheet(f"color:{color};font-size:12px;")

    def fade_out(self, callback):
        out=QPropertyAnimation(self._effect, b"opacity")
        out.setDuration(400); out.setStartValue(1.0); out.setEndValue(0.0)
        out.setEasingCurve(QEasingCurve.Type.InCubic)
        out.finished.connect(callback); out.start()
        self._out_anim=out

    def paintEvent(self, e): pass


class OverlayWindow(QWidget):
    _SPINNER = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
    _SETTINGS_REQUESTED = Signal()

    def __init__(self, cfg: dict, signals: Signals, app: QApplication):
        super().__init__(None)
        self._cfg=cfg; self._signals=signals; self._app=app
        self._rows: dict[str,UserRow]={};  self._leaving=set()
        self._leave_timers: dict[str,QTimer]={}
        self._pulse_step=0; self._spin_idx=0; self._drag=None

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint|
                            Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        border=cfg.get("border_color",ACCENT)
        self._card=QFrame(self); self._card.setObjectName("card")
        self._set_card_style(border)
        cl=QVBoxLayout(self._card); cl.setContentsMargins(0,0,0,0); cl.setSpacing(0)

        self._top_bar=QFrame(); self._top_bar.setFixedHeight(3)
        self._top_bar.setStyleSheet(f"background:{border};border-radius:10px 10px 0 0;border:none;")
        cl.addWidget(self._top_bar)

        inner=QWidget(); inner.setStyleSheet("background:transparent;border:none;")
        il=QVBoxLayout(inner); il.setContentsMargins(12,8,12,8); il.setSpacing(6)

        hdr=QHBoxLayout()
        self._dot=QLabel("●"); self._dot.setStyleSheet(f"color:{border};font-size:8px;")
        self._title=QLabel(" TS3"); self._title.setStyleSheet(f"color:{FG};font-weight:700;font-size:13px;")
        self._srv=QLabel(""); self._srv.setStyleSheet(f"color:{DIM};font-size:10px;")
        self._ch=QLabel("conectando…"); self._ch.setStyleSheet(f"color:{DIM};font-size:10px;")
        xl=QLabel("✕"); xl.setStyleSheet(f"color:{DIM2};font-size:11px;")
        xl.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        xl.mousePressEvent=lambda e: QApplication.quit()
        hdr.addWidget(self._dot); hdr.addWidget(self._title); hdr.addSpacing(4)
        hdr.addWidget(self._srv); hdr.addWidget(self._ch,1); hdr.addWidget(xl)
        il.addLayout(hdr)

        sep=QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background:{BORDER};max-height:1px;border:none;"); il.addWidget(sep)

        self._users_w=QWidget(); self._users_w.setStyleSheet("background:transparent;")
        self._users_w.setSizePolicy(
            self._users_w.sizePolicy().horizontalPolicy(),
            __import__("PySide6.QtWidgets", fromlist=["QSizePolicy"]).QSizePolicy.Policy.Minimum
        )
        self._users_l=QVBoxLayout(self._users_w)
        self._users_l.setContentsMargins(0,0,0,0); self._users_l.setSpacing(1)
        self._users_l.setSizeConstraint(
            __import__("PySide6.QtWidgets", fromlist=["QLayout"]).QLayout.SizeConstraint.SetMinimumSize
        )
        il.addWidget(self._users_w); cl.addWidget(inner)

        ol=QVBoxLayout(self); ol.setContentsMargins(0,0,0,0); ol.addWidget(self._card)
        self.move(cfg.get("win_x",20), cfg.get("win_y",20))
        self.setWindowOpacity(cfg.get("opacity",0.90))
        self.adjustSize(); self.show()


        self._pulse_t=QTimer(self); self._pulse_t.timeout.connect(self._pulse)
        self._spin_t=QTimer(self); self._spin_t.timeout.connect(self._spin)
        ms=max(200, cfg.get("keep_on_top_ms",500))
        self._kot_t=QTimer(self); self._kot_t.timeout.connect(self._keep_top); self._kot_t.start(ms)


        signals.update_users.connect(self._render)
        signals.show_error.connect(self._show_err)
        signals.notify_join.connect(self._on_join)
        signals.notify_leave.connect(self._on_leave)
        signals.notify_moved.connect(self._on_moved)
        signals.show_message.connect(self._on_msg)
        signals.whisper_talk.connect(self._on_wt)
        signals.whisper_leave.connect(self._on_whisper_leave)
        signals.channel_changed.connect(self._on_channel_changed)
        signals.open_settings.connect(self._open_settings)

        QTimer.singleShot(100, self._init_win32)
        MessageToast._cfg = cfg

    def _set_card_style(self, border):
        self._card.setStyleSheet(f"QFrame#card{{background:{PANEL};border:1px solid {border};border-radius:10px;}}")

    def _init_win32(self):
        if WINDOWS_API_AVAILABLE:
            hwnd=int(self.winId()); set_noactivate(hwnd)
            if self._cfg.get("blur_behind",True): enable_blur_behind(hwnd)


            interactive=self._cfg.get("click_through",False)
            set_click_through(hwnd, not interactive)

    def _keep_top(self):
        self.raise_()
        if WINDOWS_API_AVAILABLE:
            try: force_topmost(int(self.winId()))
            except: pass


    def mousePressEvent(self,e):
        if not self._cfg.get("click_through",False): return
        if e.button()==Qt.MouseButton.LeftButton:
            self._drag=e.globalPosition().toPoint()-self.frameGeometry().topLeft()
        elif e.button()==Qt.MouseButton.RightButton:
            self._open_settings()
    def mouseMoveEvent(self,e):
        if not self._cfg.get("click_through",False): return
        if self._drag and e.buttons()==Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint()-self._drag)
    def mouseReleaseEvent(self,e):
        if not self._cfg.get("click_through",False): return
        if self._drag:
            self._drag=None; self._cfg["win_x"]=self.x(); self._cfg["win_y"]=self.y(); save_config(self._cfg)

    def _open_settings(self):
        dlg=SettingsDialog(self._cfg, self._apply_cfg, self)
        dlg.exec()

    def _apply_cfg(self, cfg):
        self._cfg=cfg
        MessageToast._cfg = cfg
        border=cfg.get("border_color",ACCENT)
        self._set_card_style(border)
        self._top_bar.setStyleSheet(f"background:{border};border-radius:10px 10px 0 0;border:none;")
        self._dot.setStyleSheet(f"color:{border};font-size:8px;")
        self.setWindowOpacity(cfg.get("opacity",0.90))

        for row in self._rows.values():
            try: row._cfg=cfg; row._refresh_style()
            except: pass
        self.adjustSize()
        QTimer.singleShot(50, self._init_win32)

        if WhispersWindow._instance and WINDOWS_API_AVAILABLE:
            def _apply_wsp():
                try:
                    hwnd=int(WhispersWindow._instance.winId())
                    interactive=cfg.get("click_through",False)
                    set_click_through(hwnd, not interactive)
                except: pass
            QTimer.singleShot(80, _apply_wsp)


    def _start_spinner(self): self._spin_idx=0; self._spin_t.start(100)
    def _stop_spinner(self): self._spin_t.stop(); self._title.setText(" TS3")
    def _spin(self): self._title.setText(f" {self._SPINNER[self._spin_idx%len(self._SPINNER)]}"); self._spin_idx+=1


    def _pulse(self):
        if not self._cfg.get("pulse_on_talk",True): self._pulse_t.stop(); return
        border=self._cfg.get("border_color",ACCENT)
        t=(math.sin(self._pulse_step*0.3)+1)/2
        def lh(c1,c2,t):
            r1,g1,b1=int(c1[1:3],16),int(c1[3:5],16),int(c1[5:7],16)
            r2,g2,b2=int(c2[1:3],16),int(c2[3:5],16),int(c2[5:7],16)
            return f"#{int(r1+(r2-r1)*t):02x}{int(g1+(g2-g1)*t):02x}{int(b1+(b2-b1)*t):02x}"
        col=lh(border,SPEAKING,t)
        self._dot.setStyleSheet(f"color:{col};font-size:8px;"); self._pulse_step+=1


    def _render(self, clients, channel, server, group_names, my_cid):
        self._srv.setText(server or ""); self._ch.setText(f"· {channel[:28]}" if channel else "")
        if server or channel: self._stop_spinner()
        alone=len(clients)<=1
        if self._cfg.get("hide_alone",True) and alone:
            self.hide(); return
        if not self.isVisible():


            for clid, row in list(self._rows.items()):
                self._users_l.removeWidget(row); row.hide(); row.deleteLater()
            self._rows.clear()
            self._leaving.clear()
            for t in self._leave_timers.values():
                try: t.stop()
                except: pass
            self._leave_timers.clear()
            self.show(); QTimer.singleShot(50, self._init_win32)

        any_talk=any(c.get("client_flag_talking","0")=="1" for c in clients)
        if any_talk: self._pulse_t.start(50)
        else:
            self._pulse_t.stop()
            self._dot.setStyleSheet(f"color:{self._cfg.get('border_color',ACCENT)};font-size:8px;")

        ids={c.get("clid","") for c in clients}
        for clid in list(self._rows):
            if clid not in ids and clid not in self._leaving:
                row=self._rows.pop(clid)
                self._users_l.removeWidget(row)
                row.hide()
                row.deleteLater()

        for c in clients:
            clid=c.get("clid",""); name=c.get("client_nickname","?")
            sp=c.get("client_flag_talking","0")=="1"
            mu=c.get("client_input_muted","0")=="1"
            de=c.get("client_output_muted","0")=="1"
            wsp=c.get("client_flag_whisper","0")=="1"

            if clid in self._leaving:
                self._leaving.discard(clid)
                if clid in self._leave_timers:
                    self._leave_timers[clid].stop()
                    del self._leave_timers[clid]
            if clid in self._rows:
                self._rows[clid].update_state(sp,mu,de,name,whispering=wsp)
            else:
                row=UserRow(clid,name,sp,mu,de,self._cfg,whispering=wsp)
                self._rows[clid]=row; self._users_l.addWidget(row)


        self._users_w.updateGeometry()
        self._card.updateGeometry()
        self.adjustSize()

    def _show_err(self, msg):
        for clid,row in list(self._rows.items()):
            self._users_l.removeWidget(row); row.hide(); row.deleteLater()
        self._rows.clear(); self._leaving.clear()
        for t in self._leave_timers.values():
            try: t.stop()
            except: pass
        self._leave_timers.clear()
        self._ch.setText("error"); self._srv.setText("")
        self._start_spinner()
        self._users_w.updateGeometry(); self._card.updateGeometry(); self.adjustSize()


    def _on_join(self, clid, name):
        if self._cfg.get("silent_join_leave",False): return
        secs=self._cfg.get("anim_seconds",3)
        color=self._cfg.get("join_color",JOIN_C)
        QTimer.singleShot(120, lambda: self._do_join(clid, color, secs))

    def _do_join(self, clid, color, secs):
        if clid in self._rows:
            self._rows[clid].flash_join(color, secs)

    def _on_leave(self, clid, name):
        if self._cfg.get("silent_join_leave",False): return
        if clid not in self._rows: return
        if clid in self._leave_timers:
            self._leave_timers[clid].stop()
        self._leaving.add(clid)
        color=self._cfg.get("leave_color",LEAVE_C)
        secs=self._cfg.get("anim_seconds",3)
        row=self._rows[clid]; row.flash_leave(color, secs)
        t=QTimer(self); t.setSingleShot(True)
        def _rm():
            r=self._rows.pop(clid, None)
            if r:
                self._users_l.removeWidget(r)
                self._users_w.updateGeometry()
            def after_fade():
                if r: r.deleteLater()
            if r: r.fade_out(after_fade)
            self._leaving.discard(clid)
            self._users_w.updateGeometry(); self._card.updateGeometry(); self.adjustSize()
        t.timeout.connect(_rm); t.start(secs*1000); self._leave_timers[clid]=t

    def _on_moved(self, clid, name):
        if self._cfg.get("silent_join_leave",False): return
        if clid in self._rows:
            self._rows[clid].flash_move(self._cfg.get("move_color",MOVE_C))


    def _on_msg(self, sender, text, msg_type, clid):
        cfg=self._cfg
        if msg_type=="private" and not cfg.get("show_private_msg",True): return
        if msg_type=="channel" and not cfg.get("show_channel_msg",True): return
        if msg_type=="whisper" and not cfg.get("show_whisper_msg",True): return
        secs=cfg.get("toast_seconds",5)
        if msg_type=="whisper":
            if WhispersWindow._instance is None: WhispersWindow(cfg)
            WhispersWindow._instance.add_whisper(clid or sender, sender, text)
        else:
            MessageToast(sender, text, msg_type, secs)

    def _on_wt(self, clid, talking):
        if WhispersWindow._instance: WhispersWindow._instance.on_talk(clid, talking)

    def _on_whisper_leave(self, clid):
        if WhispersWindow._instance: WhispersWindow._instance.remove_entry(clid)

    def _on_channel_changed(self):
        
        for clid, t in list(self._leave_timers.items()):
            try: t.stop()
            except: pass
        self._leave_timers.clear()
        self._leaving.clear()
        for clid, row in list(self._rows.items()):
            self._users_l.removeWidget(row); row.hide(); row.deleteLater()
        self._rows.clear()
        self._users_w.updateGeometry(); self._card.updateGeometry(); self.adjustSize()

    def toggle_visibility(self):
        if self.isVisible(): self.hide()
        else: self.show(); QTimer.singleShot(50, self._init_win32)

    def paintEvent(self, e): pass


class SettingsDialog(QDialog):
    """Panel de configuración estilo glassmorphism con sliders y cards."""

    def __init__(self, cfg: dict, on_save, parent=None):
        super().__init__(parent)
        self._cfg=cfg; self._on_save=on_save
        self.setWindowTitle("Configuración")
        self.setModal(True)
        self.setStyleSheet(f"""
            QDialog{{background:{BG};color:{FG};}}
            QLabel{{background:transparent;}}
        """)

        root=QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)


        grad_bar=QFrame(); grad_bar.setFixedHeight(4)
        grad_bar.setStyleSheet(f"background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {ACCENT},stop:1 {ACCENT2});border:none;")
        root.addWidget(grad_bar)


        hdr_frame=QFrame(); hdr_frame.setStyleSheet(f"background:{PANEL};border:none;")
        hdr_l=QHBoxLayout(hdr_frame); hdr_l.setContentsMargins(24,14,16,14)
        title_lbl=QLabel("Configuración"); title_lbl.setStyleSheet(f"color:{FG};font-size:18px;font-weight:700;")
        x_btn=QPushButton("✕"); x_btn.setStyleSheet(f"background:none;color:{DIM2};border:none;font-size:14px;")
        x_btn.clicked.connect(self._close_dialog)
        hdr_l.addWidget(title_lbl,1); hdr_l.addWidget(x_btn)
        root.addWidget(hdr_frame)

        sep=QFrame(); sep.setFrameShape(QFrame.Shape.HLine); sep.setStyleSheet(f"background:{BORDER};max-height:1px;border:none;")
        root.addWidget(sep)


        scroll=QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"QScrollArea{{background:{BG};border:none;}}")
        root.addWidget(scroll, 1)

        body=QWidget(); body.setStyleSheet(f"background:{BG};")
        bl=QVBoxLayout(body); bl.setContentsMargins(20,16,20,16); bl.setSpacing(12)
        scroll.setWidget(body)


        def card_widget(layout_func):
            
            card=QFrame()
            card.setStyleSheet(f"QFrame{{background:{PANEL};border:1px solid {BORDER};border-radius:12px;}}")
            il=QVBoxLayout(card); il.setContentsMargins(16,14,16,14); il.setSpacing(10)
            layout_func(il)
            return card

        def section_title(text, icon=""):
            lbl=QLabel(f"{icon}  {text}" if icon else text)
            lbl.setStyleSheet(f"color:{ACCENT};font-size:11px;font-weight:700;letter-spacing:1.5px;")
            return lbl

        def color_row(label_text, current_color, on_change):
            
            row=QHBoxLayout()
            lbl=QLabel(label_text); lbl.setStyleSheet(f"color:{FG};font-size:13px;")
            swatch=QFrame(); swatch.setFixedSize(28,20)
            swatch.setStyleSheet(f"background:{current_color};border-radius:5px;border:1.5px solid {BORDER};")
            pick_btn=QPushButton("Elegir color")
            pick_btn.setStyleSheet(f"""
                QPushButton{{background:{PANEL2};color:{DIM2};border:1px solid {BORDER};
                    border-radius:6px;padding:4px 10px;font-size:11px;}}
                QPushButton:hover{{background:{BORDER};color:{FG};}}
            """)
            pick_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            state={"color": current_color}
            def _pick():
                c=QColorDialog.getColor(QColor(state["color"]), None, label_text)
                if c.isValid():
                    state["color"]=c.name()
                    swatch.setStyleSheet(f"background:{c.name()};border-radius:5px;border:1.5px solid {BORDER};")
                    on_change(c.name())
            pick_btn.clicked.connect(_pick)
            row.addWidget(lbl,1); row.addWidget(swatch); row.addSpacing(6); row.addWidget(pick_btn)
            return row, state

        def row_check(lbl_text, checked):
            row=QHBoxLayout()
            lbl=QLabel(lbl_text); lbl.setStyleSheet(f"color:{FG};font-size:13px;")
            cb=QCheckBox(); cb.setChecked(checked); cb.setStyleSheet("")
            row.addWidget(lbl,1); row.addWidget(cb)
            return row, cb

        def slider_row(label, val, lo, hi, unit="%", decimals=False):
            
            row=QVBoxLayout(); row.setSpacing(6)
            top=QHBoxLayout()
            lbl=QLabel(label); lbl.setStyleSheet(f"color:{FG};font-size:13px;")
            fmt=f"{val}{unit}"
            val_lbl=QLabel(fmt); val_lbl.setStyleSheet(f"color:{ACCENT};font-size:13px;font-weight:700;min-width:40px;")
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
            top.addWidget(lbl,1); top.addWidget(val_lbl)
            sl=QSlider(Qt.Orientation.Horizontal)
            sl.setRange(lo, hi); sl.setValue(val)
            sl.valueChanged.connect(lambda v,l=val_lbl,u=unit: l.setText(f"{v}{u}"))
            sl.setStyleSheet("")
            row.addLayout(top); row.addWidget(sl)
            return row, sl, val_lbl


        self._sl_opacity = self._sl_fontsize = self._sl_bgdim = None


        bl.addWidget(section_title("VISUALIZACIÓN", "🎨"))

        def vis_card(il):
            row_op, sl_op, _ = slider_row("Escala de Opacidad", int(cfg.get("opacity",0.9)*100), 10, 100, "%")
            self._sl_opacity=sl_op
            def _live_opacity(v):
                cfg["opacity"]=round(v/100,2); self._on_save(cfg)
            sl_op.valueChanged.connect(_live_opacity)
            il.addLayout(row_op)
            il.addWidget(mk_div())
            row_fs, sl_fs, _ = slider_row("Tamaño de Texto", cfg.get("font_size",10), 8, 24, "px")
            self._sl_fontsize=sl_fs
            def _live_fontsize(v):
                cfg["font_size"]=v; self._on_save(cfg)
            sl_fs.valueChanged.connect(_live_fontsize)
            il.addLayout(row_fs)
            il.addWidget(mk_div())
            row_dim, sl_dim, _ = slider_row("Oscurecimiento de Fondo", int(cfg.get("bg_dim",0)*100), 0, 80, "%")
            self._sl_bgdim=sl_dim
            def _live_bgdim(v):
                cfg["bg_dim"]=round(v/100,2); self._on_save(cfg)
            sl_dim.valueChanged.connect(_live_bgdim)
            il.addLayout(row_dim)
        bl.addWidget(card_widget(vis_card))


        bl.addWidget(section_title("COMPORTAMIENTO", "⚙"))


        self._cb_hide_alone=self._cb_show_all=self._cb_silent=self._cb_ct=None
        self._cb_pulse=self._cb_blur=self._cb_icons=None

        def behav_card(il):
            r,cb=row_check("Ocultar si estás solo", cfg.get("hide_alone",True))
            self._cb_hide_alone=cb; il.addLayout(r)
            il.addWidget(mk_div())
            r,cb=row_check("Mostrar todos los usuarios", cfg.get("show_all_users",False))
            self._cb_show_all=cb; il.addLayout(r)
            il.addWidget(mk_div())
            r,cb=row_check("Sin notificación entrada/salida", cfg.get("silent_join_leave",False))
            self._cb_silent=cb; il.addLayout(r)
            il.addWidget(mk_div())
            r,cb=row_check("Modo interactivo (mover overlay)", cfg.get("click_through",False))
            self._cb_ct=cb; il.addLayout(r)
            il.addWidget(mk_div())
            r,cb=row_check("Pulso del dot al hablar", cfg.get("pulse_on_talk",True))
            self._cb_pulse=cb; il.addLayout(r)
            il.addWidget(mk_div())
            r,cb=row_check("Blur DWM (Win10/11)", cfg.get("blur_behind",True))
            self._cb_blur=cb; il.addLayout(r)
            il.addWidget(mk_div())
            r,cb=row_check("Íconos de estado (muted/deaf)", cfg.get("status_icons",True))
            self._cb_icons=cb; il.addLayout(r)
        bl.addWidget(card_widget(behav_card))


        bl.addWidget(section_title("COLORES", "🎨"))
        self._color_border=cfg.get("border_color",ACCENT)
        self._color_join=cfg.get("join_color",JOIN_C)
        self._color_leave=cfg.get("leave_color",LEAVE_C)
        self._color_move=cfg.get("move_color",MOVE_C)

        def colors_card(il):
            r,st=color_row("Color del borde / acento", self._color_border,
                           lambda v: self.__dict__.__setitem__("_color_border",v) or self._on_save({**self._cfg,"border_color":v}))
            il.addLayout(r); il.addWidget(mk_div())
            r,st=color_row("Color entrada al canal", self._color_join,
                           lambda v: self.__dict__.__setitem__("_color_join",v))
            il.addLayout(r); il.addWidget(mk_div())
            r,st=color_row("Color salida del canal", self._color_leave,
                           lambda v: self.__dict__.__setitem__("_color_leave",v))
            il.addLayout(r); il.addWidget(mk_div())
            r,st=color_row("Color movimiento de canal", self._color_move,
                           lambda v: self.__dict__.__setitem__("_color_move",v))
            il.addLayout(r)
        bl.addWidget(card_widget(colors_card))


        bl.addWidget(section_title("MENSAJES", "💬"))
        self._cb_ch_msg=self._cb_prv_msg=self._cb_wsp_msg=None
        self._sl_toast=None

        def msg_card(il):
            r,cb=row_check("Mensajes de canal", cfg.get("show_channel_msg",True))
            self._cb_ch_msg=cb; il.addLayout(r)
            il.addWidget(mk_div())
            r,cb=row_check("Mensajes privados", cfg.get("show_private_msg",True))
            self._cb_prv_msg=cb; il.addLayout(r)
            il.addWidget(mk_div())
            r,cb=row_check("Whispers", cfg.get("show_whisper_msg",True))
            self._cb_wsp_msg=cb; il.addLayout(r)
            il.addWidget(mk_div())
            row_t,sl_t,_=slider_row("Duración del toast (s)", cfg.get("toast_seconds",5), 1, 30, "s")
            self._sl_toast=sl_t; il.addLayout(row_t)
        bl.addWidget(card_widget(msg_card))


        bl.addWidget(section_title("HOTKEYS", "⌨"))
        self._hk=self._hk_cfg=self._hk_q=self._hk_n=None

        def hk_card(il):
            def hk_row(label, val):
                row=QHBoxLayout(); lbl=QLabel(label); lbl.setStyleSheet(f"color:{FG};font-size:13px;")
                le=QLineEdit(val); le.setFixedWidth(120); row.addWidget(lbl,1); row.addWidget(le)
                return row, le
            r,self._hk    =hk_row("Toggle overlay",      cfg.get("hotkey","f9")); il.addLayout(r)
            il.addWidget(mk_div())
            r,self._hk_cfg=hk_row("Abrir configuración", cfg.get("hotkey_config","f10")); il.addLayout(r)
            il.addWidget(mk_div())
            r,self._hk_q  =hk_row("Salir",               cfg.get("hotkey_quit","")); il.addLayout(r)
            il.addWidget(mk_div())
            r,self._hk_n  =hk_row("Notificaciones",      cfg.get("hotkey_notifications","f8")); il.addLayout(r)
        bl.addWidget(card_widget(hk_card))


        bl.addWidget(section_title("PROBAR NOTIFICACIONES", "🧪"))

        def test_card(il):
            row=QHBoxLayout(); row.setSpacing(8)
            for label, mtype, color in [("Canal", "channel", CHAN_C),
                                         ("Privado","private",PRIV_C),
                                         ("Whisper","whisper",WHIS_C)]:
                btn=QPushButton(label)
                btn.setStyleSheet(f"""
                    QPushButton{{background:{PANEL2};color:{color};border:1.5px solid {color};
                        border-radius:8px;padding:8px 16px;font-size:12px;font-weight:600;}}
                    QPushButton:hover{{background:{color};color:white;}}
                """)
                btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                btn.clicked.connect(lambda _=None,t=mtype: self._test(t))
                row.addWidget(btn)
            row.addStretch(); il.addLayout(row)
        bl.addWidget(card_widget(test_card))
        bl.addStretch()


        root.addWidget(mk_div())
        footer_w=QWidget(); footer_w.setStyleSheet(f"background:{BG2};")
        footer_vl=QVBoxLayout(footer_w); footer_vl.setContentsMargins(20,10,20,10); footer_vl.setSpacing(8)


        btn_prev=mk_btn("🖼  Previsualizar y posicionar ventanas", primary=False)
        btn_prev.clicked.connect(self._preview_windows)
        footer_vl.addWidget(btn_prev)


        footer_l=QHBoxLayout(); footer_l.setSpacing(10)
        btn_save=mk_btn("💾  Guardar cambios", primary=True)
        btn_rst =mk_btn("↺  Restablecer", danger=True)
        btn_save.clicked.connect(self._save); btn_rst.clicked.connect(self._reset)
        footer_l.addWidget(btn_save,1); footer_l.addWidget(btn_rst)
        footer_vl.addLayout(footer_l)

        root.addWidget(footer_w)


        scr=QApplication.primaryScreen().geometry()
        self.resize(480, min(700, scr.height()-80))
        self.move((scr.width()-480)//2, (scr.height()-self.height())//2)

    def _close_dialog(self):
        PreviewOverlay.close_all()
        self.reject()

    def _test(self, msg_type):
        secs=5
        MessageToast("UsuarioPrueba", f"Mensaje de prueba ({msg_type})", msg_type, secs)

    def _save(self):
        c=self._cfg
        c["opacity"]           = round(self._sl_opacity.value()/100, 2)
        c["font_size"]         = self._sl_fontsize.value()
        c["bg_dim"]            = round(self._sl_bgdim.value()/100, 2)
        c["hide_alone"]        = self._cb_hide_alone.isChecked()
        c["show_all_users"]    = self._cb_show_all.isChecked()
        c["silent_join_leave"] = self._cb_silent.isChecked()
        c["click_through"]     = self._cb_ct.isChecked()
        c["pulse_on_talk"]     = self._cb_pulse.isChecked()
        c["blur_behind"]       = self._cb_blur.isChecked()
        c["status_icons"]      = self._cb_icons.isChecked()
        c["show_channel_msg"]  = self._cb_ch_msg.isChecked()
        c["show_private_msg"]  = self._cb_prv_msg.isChecked()
        c["show_whisper_msg"]  = self._cb_wsp_msg.isChecked()
        c["toast_seconds"]     = self._sl_toast.value()
        c["hotkey"]            = self._hk.text().strip().lower()
        c["hotkey_config"]     = self._hk_cfg.text().strip().lower()
        c["hotkey_quit"]       = self._hk_q.text().strip().lower()
        c["hotkey_notifications"] = self._hk_n.text().strip().lower()
        c["border_color"]      = getattr(self, "_color_border", c.get("border_color", ACCENT))
        c["join_color"]        = getattr(self, "_color_join",   c.get("join_color",   JOIN_C))
        c["leave_color"]       = getattr(self, "_color_leave",  c.get("leave_color",  LEAVE_C))
        c["move_color"]        = getattr(self, "_color_move",   c.get("move_color",   MOVE_C))
        save_config(c); self._on_save(c); self.accept()

    def _reset(self):
        new=reset_config(); self._cfg.update(new); self._on_save(new); self.accept()

    def _reset_pos(self):
        self._cfg["win_x"]=20; self._cfg["win_y"]=20; save_config(self._cfg); self._on_save(self._cfg)

    def _preview_windows(self):
        
        from PySide6.QtWidgets import QApplication as _QApp

        overlay_ref = None; whispers_ref = None
        for w in _QApp.topLevelWidgets():
            if isinstance(w, OverlayWindow): overlay_ref = w
            if isinstance(w, WhispersWindow): whispers_ref = w
        PreviewOverlay.show_all(self._cfg, overlay_ref=overlay_ref,
                                whispers_ref=whispers_ref, parent=self)


class PreviewSaveBar(QWidget):
    """Barra flotante que aparece al previsualizar ventanas, para guardar y cerrar."""
    def __init__(self, cfg: dict):
        super().__init__(None, Qt.WindowType.FramelessWindowHint |
                        Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self._cfg = cfg
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedHeight(54)

        scr = QApplication.primaryScreen().geometry()
        self.setFixedWidth(360)
        self.move((scr.width()-360)//2, scr.height()-80)

        l = QHBoxLayout(self); l.setContentsMargins(12,8,12,8); l.setSpacing(10)

        info = QLabel("📐  Arrastrá las ventanas a la posición deseada")
        info.setStyleSheet(f"color:{DIM2};font-size:11px;background:transparent;border:none;")
        l.addWidget(info, 1)

        save_btn = QPushButton("✔  Guardar posiciones")
        save_btn.setStyleSheet(f"""
            QPushButton{{background:{ACCENT};color:white;border:none;border-radius:8px;
                padding:6px 14px;font-size:12px;font-weight:700;}}
            QPushButton:hover{{background:{ACCENT2};}}
        """)
        save_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        save_btn.clicked.connect(self._save_and_close)
        l.addWidget(save_btn)

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath(); path.addRoundedRect(0, 0, self.width(), self.height(), 10, 10)
        p.fillPath(path, QColor(13, 13, 26, 220))
        pen = QPen(QColor(BORDER), 1); p.setPen(pen); p.drawPath(path)

    def _save_and_close(self):
        for prev in PreviewOverlay._active_previews:
            self._cfg[prev._pos_x_key] = prev.x()
            self._cfg[prev._pos_y_key] = prev.y()
        save_config(self._cfg)
        PreviewOverlay.close_all()


class PreviewOverlay(QWidget):
    """Ventana de previsualización semi-transparente para posicionar el overlay."""
    _active_previews: list["PreviewOverlay"] = []

    def __init__(self, cfg: dict, label: str, pos_x_key: str, pos_y_key: str,
                 width: int, height: int, color: str, on_move=None, parent=None):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint |
                        Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self._cfg = cfg
        self._pos_x_key = pos_x_key
        self._pos_y_key = pos_y_key
        self._drag = None
        self._color = color
        self._on_move = on_move

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.setFixedSize(width, height)

        l = QVBoxLayout(self); l.setContentsMargins(8,6,8,6); l.setSpacing(4)

        title_bar = QHBoxLayout()
        icon_lbl = QLabel("✥")
        icon_lbl.setStyleSheet(f"color:{color};font-size:14px;background:transparent;border:none;")
        name_lbl = QLabel(label)
        name_lbl.setStyleSheet(f"color:white;font-size:12px;font-weight:700;background:transparent;border:none;")
        close_lbl = QLabel("✕")
        close_lbl.setStyleSheet(f"color:{DIM2};font-size:11px;background:transparent;border:none;")
        close_lbl.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        close_lbl.mousePressEvent = lambda e: self._close_self()
        title_bar.addWidget(icon_lbl); title_bar.addSpacing(4); title_bar.addWidget(name_lbl,1); title_bar.addWidget(close_lbl)
        l.addLayout(title_bar)

        hint = QLabel("Arrastrá para mover · guarda al soltar")
        hint.setStyleSheet(f"color:{DIM2};font-size:10px;background:transparent;border:none;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(hint)

        self.move(cfg.get(pos_x_key, 20), cfg.get(pos_y_key, 20))
        self.show()
        PreviewOverlay._active_previews.append(self)

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath(); path.addRoundedRect(0, 0, self.width(), self.height(), 10, 10)
        p.fillPath(path, QColor(0,0,0,160))
        pen = QPen(QColor(self._color), 1.5)
        pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen); p.drawPath(path)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag and e.buttons() == Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag)

            if self._on_move:
                try: self._on_move(self.x(), self.y())
                except: pass

    def mouseReleaseEvent(self, e):
        if self._drag:
            self._drag = None
            self._cfg[self._pos_x_key] = self.x()
            self._cfg[self._pos_y_key] = self.y()
            save_config(self._cfg)
            if self._on_move:
                try: self._on_move(self.x(), self.y())
                except: pass

    def _close_self(self):
        try: PreviewOverlay._active_previews.remove(self)
        except ValueError: pass
        self.hide(); self.deleteLater()

    @staticmethod
    def show_all(cfg: dict, overlay_ref=None, whispers_ref=None, toast_ref=None, parent=None):
        PreviewOverlay.close_all()


        def _move_overlay(x, y):
            if overlay_ref:
                try: overlay_ref.move(x, y)
                except: pass

        def _move_whispers(x, y):
            if whispers_ref:
                try: whispers_ref.move(x, y)
                except: pass

        def _move_toast_chan(x, y):
            cfg["toast_chan_x"] = x; cfg["toast_chan_y"] = y

        def _move_toast_priv(x, y):
            cfg["toast_priv_x"] = x; cfg["toast_priv_y"] = y

        PreviewOverlay(cfg, "🖥  Overlay Principal",
                       "win_x",      "win_y",      240, 90,  ACCENT,  _move_overlay, parent)
        PreviewOverlay(cfg, "💬  Whispers",
                       "whispers_x", "whispers_y", 220, 80,  WHIS_C,  _move_whispers, parent)
        PreviewOverlay(cfg, "📨  Mensajes de Canal",
                       "toast_chan_x","toast_chan_y",260, 80, CHAN_C,  _move_toast_chan, parent)
        PreviewOverlay(cfg, "🔒  Mensajes Privados",
                       "toast_priv_x","toast_priv_y",260, 80, PRIV_C, _move_toast_priv, parent)


        bar = PreviewSaveBar(cfg)
        bar.show()
        PreviewOverlay._save_bar = bar

    @staticmethod
    def close_all():
        for p in list(PreviewOverlay._active_previews):
            try: p.hide(); p.deleteLater()
            except: pass
        PreviewOverlay._active_previews.clear()

        bar = getattr(PreviewOverlay, "_save_bar", None)
        if bar:
            try: bar.hide(); bar.deleteLater()
            except: pass
            PreviewOverlay._save_bar = None


class NotificationsWindow(QWidget):
    def __init__(self, cfg: dict, signals: Signals):
        super().__init__(None)
        self._cfg=cfg; self._messages=deque(maxlen=cfg.get("max_notifications",50))
        self._drag=None
        self.setWindowTitle("TS3 Notificaciones")
        self.setWindowFlags(Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet(f"background:{BG};border:1px solid {BORDER};border-radius:10px;")
        self.resize(420,340); self.hide()
        signals.notif_message.connect(self._add)

        l=QVBoxLayout(self); l.setContentsMargins(16,14,16,14); l.setSpacing(10)
        hdr=QHBoxLayout()
        hdr.addWidget(QLabel("NOTIFICACIONES",styleSheet=f"color:{ACCENT};font-weight:700;font-size:12px;letter-spacing:1px;"),1)
        xl=QPushButton("✕"); xl.setStyleSheet(f"background:none;color:{DIM2};border:none;font-size:12px;"); xl.clicked.connect(self.hide)
        hdr.addWidget(xl); l.addLayout(hdr); l.addWidget(mk_div())
        fr=QHBoxLayout(); fr.setSpacing(8)
        self._cb_p=QCheckBox("Privados"); self._cb_p.setChecked(True); self._cb_p.setStyleSheet(f"color:{PRIV_C};")
        self._cb_c=QCheckBox("Canal");    self._cb_c.setChecked(True); self._cb_c.setStyleSheet(f"color:{CHAN_C};")
        self._cb_w=QCheckBox("Whispers"); self._cb_w.setChecked(True); self._cb_w.setStyleSheet(f"color:{WHIS_C};")
        for cb in (self._cb_p, self._cb_c, self._cb_w): cb.stateChanged.connect(self._refresh); fr.addWidget(cb)
        fr.addStretch(); clr=mk_btn("Limpiar",small=True); clr.clicked.connect(self._clear); fr.addWidget(clr)
        l.addLayout(fr)
        self._list=QListWidget()
        self._list.setStyleSheet(f"QListWidget{{background:{PANEL};border:1px solid {BORDER};border-radius:8px;outline:none;}}QListWidget::item{{padding:8px 12px;border-radius:4px;}}QListWidget::item:selected{{background:{ACCENT};color:white;}}")
        self._list.itemDoubleClicked.connect(self._full)
        l.addWidget(self._list,1)

    def mousePressEvent(self,e):
        if e.button()==Qt.MouseButton.LeftButton: self._drag=e.globalPosition().toPoint()-self.frameGeometry().topLeft()
    def mouseMoveEvent(self,e):
        if self._drag and e.buttons()==Qt.MouseButton.LeftButton: self.move(e.globalPosition().toPoint()-self._drag)
    def mouseReleaseEvent(self,e): self._drag=None

    def _add(self, sender, text, msg_type):
        self._messages.append((datetime.now().strftime("%H:%M"), sender, text, msg_type))
        self._refresh()

    def _refresh(self):
        self._list.clear()
        for ts,s,t,typ in self._messages:
            if typ=="private" and not self._cb_p.isChecked(): continue
            if typ=="channel" and not self._cb_c.isChecked(): continue
            if typ=="whisper" and not self._cb_w.isChecked(): continue
            disp=f"[{ts}] {s}: {t[:45]}{'…' if len(t)>45 else ''}"
            item=QListWidgetItem(disp)
            item.setForeground(QColor(PRIV_C if typ=="private" else CHAN_C if typ=="channel" else WHIS_C))
            item.setData(Qt.ItemDataRole.UserRole,(s,t,typ))
            self._list.addItem(item)
        self._list.scrollToBottom()

    def _full(self, item):
        s,t,typ=item.data(Qt.ItemDataRole.UserRole)
        dlg=QDialog(self); dlg.setWindowTitle("Mensaje completo")
        dlg.setStyleSheet(f"background:{BG};color:{FG};"); dlg.resize(400,200)
        l=QVBoxLayout(dlg)
        l.addWidget(QLabel(f"{typ.upper()} de {s}",styleSheet=f"color:{ACCENT};font-weight:700;"))
        te=QTextEdit(t); te.setReadOnly(True)
        te.setStyleSheet(f"background:{PANEL};color:{FG};border:1px solid {BORDER};border-radius:6px;")
        cl=mk_btn("Cerrar",primary=True); cl.clicked.connect(dlg.accept)
        l.addWidget(te,1); l.addWidget(cl); dlg.exec()

    def _clear(self): self._messages.clear(); self._list.clear()
    def toggle(self): self.hide() if self.isVisible() else self.show()


class ConnectDialog(QDialog):
    def __init__(self, cfg: dict):
        super().__init__(None)
        self._cfg=cfg; self._result=None
        self.setWindowTitle("TS3 Overlay")
        self.setWindowFlags(Qt.WindowType.Dialog|Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(440,400)
        self.setStyleSheet(f"QDialog{{background:{BG};border:1px solid {BORDER};border-radius:12px;}}QLabel{{background:transparent;}}")

        root=QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        grad=QFrame(); grad.setFixedHeight(4)
        grad.setStyleSheet(f"background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {ACCENT},stop:1 {ACCENT2});border-radius:12px 12px 0 0;border:none;")
        root.addWidget(grad)

        body=QWidget(); body.setStyleSheet(f"background:{BG};")
        bl=QVBoxLayout(body); bl.setContentsMargins(40,32,40,32); bl.setSpacing(0)
        hdr=QHBoxLayout(); dot=QLabel("●",styleSheet=f"color:{ACCENT};font-size:10px;")
        title=QLabel("TS3 Overlay",styleSheet=f"color:{FG};font-size:24px;font-weight:700;")
        hdr.addWidget(dot); hdr.addSpacing(10); hdr.addWidget(title); hdr.addStretch()
        bl.addLayout(hdr); bl.addSpacing(6)
        bl.addWidget(QLabel("Conectá con el cliente TeamSpeak 3",styleSheet=f"color:{DIM2};font-size:12px;"))
        bl.addSpacing(28)

        def fld(lbl,w,hint=""):
            bl.addWidget(QLabel(lbl,styleSheet=f"color:{DIM2};font-size:10px;font-weight:700;letter-spacing:1px;"))
            bl.addSpacing(4); bl.addWidget(w)
            if hint: bl.addWidget(QLabel(hint,styleSheet=f"color:{DIM};font-size:10px;padding-top:2px;"))
            bl.addSpacing(16)

        self._key=QLineEdit(cfg.get("api_key","")); self._key.setPlaceholderText("xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
        fld("API KEY",self._key,"Herramientas → Addons → ClientQuery → Ajustes")
        self._port=QLineEdit(str(cfg.get("port",25639)))
        fld("PUERTO",self._port,"Puerto TCP de ClientQuery (default 25639)")

        br=QHBoxLayout()
        ok=mk_btn("Conectar →",primary=True); ok.clicked.connect(self._ok)
        cn=mk_btn("Cancelar"); cn.clicked.connect(self.reject)
        br.addWidget(ok); br.addWidget(cn); br.addStretch(); bl.addLayout(br); bl.addStretch()
        root.addWidget(body,1); root.addWidget(mk_div())
        ft=QFrame(); ft.setStyleSheet(f"background:{BG2};border:none;")
        fl=QHBoxLayout(ft); fl.setContentsMargins(16,8,16,8)
        fl.addWidget(QLabel(f"Log: {LOG_FILE}  ·  Click derecho → Configuración",styleSheet=f"color:{DIM};font-size:10px;"))
        root.addWidget(ft)
        self._key.returnPressed.connect(self._ok); self._port.returnPressed.connect(self._ok)
        scr=QApplication.primaryScreen().geometry()
        self.move((scr.width()-440)//2,(scr.height()-400)//2)

    def _ok(self):
        key=self._key.text().strip()
        if not key: return
        try: port=int(self._port.text().strip())
        except: return
        self._cfg["api_key"]=key; self._cfg["port"]=port
        save_config(self._cfg); self._result=self._cfg; self.accept()

    def result_cfg(self): return self._result


class TS3EventThread(QThread):
    def __init__(self, cfg, state, signals):
        super().__init__()
        self._cfg=cfg; self.state=state; self.signals=signals
        self._stop=threading.Event(); self._conn=None; self._nc={}; self._delay=2

    def stop(self):
        self._stop.set()
        if self._conn: self._conn.disconnect()

    def _name(self, conn, clid, d=None):
        if d:
            for f in ("client_nickname","invokername","client_base64HashClientUID"):
                v=d.get(f,"")
                if v and v not in ("?","","0"):
                    n=TS3Connection.unescape(v)
                    if clid: self._nc[clid]=n
                    return n

        if clid and clid in self._nc:
            cached = self._nc[clid]
            if cached and cached not in ("?","Desconocido"): return cached

        if clid:
            for attempt in range(4):
                try:
                    info=self._conn.clientinfo(clid) if self._conn else {}
                    if info:
                        for field in ("client_nickname","client_base64HashClientUID"):
                            v=info.get(field,"")
                            if v and v not in ("?","","0"):
                                n=TS3Connection.unescape(v)
                                self._nc[clid]=n; return n
                except: pass
                time.sleep(0.1 * (attempt+1))

        if clid and self._conn:
            try:
                all_c=self._conn.clientlist_voice_info()
                for c in all_c:
                    if c.get("clid")==clid:
                        n=TS3Connection.unescape(c.get("client_nickname",""))
                        if n and n not in ("?",""):
                            self._nc[clid]=n; return n
            except: pass

        if clid and clid in self._nc and self._nc[clid] not in ("?",""):
            return self._nc[clid]
        return f"Usuario-{clid[-4:]}" if clid else "Desconocido"

    def run(self):
        log("EventThread iniciado")
        while not self._stop.is_set():
            conn=TS3Connection(TS3_HOST, self._cfg["port"], self._cfg["api_key"])
            self._conn=conn
            try:
                conn.connect(); self._delay=2
                self._init(conn); conn.subscribe_events(); self._push()
                self._loop(conn)
            except Exception as e:
                if self._stop.is_set(): break
                log(f"Error: {e}\n{traceback.format_exc()}","ERROR")
                self.signals.show_error.emit(str(e))
            finally:
                conn.disconnect(); self._conn=None
            if not self._stop.is_set():
                log(f"Reconectando en {self._delay}s…")
                self.signals.show_error.emit("Reconectando…")
                for _ in range(self._delay*10):
                    if self._stop.is_set(): break
                    time.sleep(0.1)
                self._delay=min(self._delay*2,30)
        log("EventThread terminado")

    def _init(self, conn):
        me=conn.whoami()
        if not me: raise ConnectionError("whoami vacío")
        my_clid=me.get("clid",""); my_cid=me.get("cid","")
        if not my_cid: raise ConnectionError("No conectado a TS3")
        ch=conn.channel_name(my_cid); srv=conn.server_name()
        self.state.set_me(my_clid,my_cid,ch,srv)
        self.state.set_group_names(conn.channelgrouplist())
        log(f"Yo: clid={my_clid} cid={my_cid} canal='{ch}'")
        all_c=conn.clientlist_voice_info()
        self.state.set_clients([c for c in all_c if c.get("cid")==my_cid])
        self._nc={c["clid"]:c.get("client_nickname","?") for c in all_c if "clid" in c}

        if WhispersWindow._instance:
            QMetaObject.invokeMethod(WhispersWindow._instance, "_dismiss",
                                     Qt.ConnectionType.QueuedConnection)

    def _loop(self, conn):
        log("Escuchando eventos…")
        consecutive_empty = 0
        while not self._stop.is_set():
            try:
                line=conn.read_line(timeout=1.0)
                consecutive_empty = 0
            except ConnectionError:
                if self._stop.is_set(): return
                raise
            except Exception as ex:
                if self._stop.is_set(): return
                log(f"_loop error: {ex}", "WARN")
                consecutive_empty += 1
                if consecutive_empty > 10: raise
                continue
            if not line:
                consecutive_empty += 1
                if consecutive_empty > 30:
                    raise ConnectionError("Sin datos por demasiado tiempo")
                continue
            consecutive_empty = 0
            log(f"EVT: {line[:140]}")
            self._handle(conn, line)

    def _handle(self, conn, line):
        if   line.startswith("notifytalkstatuschange"):   self._on_talk(conn, line)
        elif line.startswith("notifyclientupdated"):      self._on_upd(line)
        elif line.startswith("notifyclientmoved"):        self._on_move(conn, line)
        elif line.startswith("notifycliententerview"):    self._on_enter(conn, line)
        elif line.startswith("notifyclientleftview"):     self._on_left(line)
        elif line.startswith("notifytextmessage"):        self._on_msg(line)
        elif line.startswith("notifywhisper"):            self._on_whisper(conn, line)
        elif line.startswith("notifyconnectstatuschange"):
            if TS3Connection.parse(line).get("status")=="disconnected":
                raise ConnectionError("TS3 desconectado")

    def _on_talk(self, conn, line):
        d=TS3Connection.parse(line)
        clid=d.get("clid",""); talking=d.get("status","0")=="1"
        is_wsp=d.get("isreceivedwhisper")=="1"
        log(f"_on_talk: clid={clid} talking={talking} whisper={is_wsp}")
        self.state.set_talking(clid, talking)

        if is_wsp:
            self.state.set_whisper_talking(clid, talking)
        elif talking:

            self.state.set_whisper_talking(clid, False)
        self._push()
        if is_wsp:
            if talking:
                already=(WhispersWindow._instance is not None and
                         any(e["clid"]==clid for e in WhispersWindow._instance._entries))
                if not already:
                    sender=self._nc.get(clid,"") or f"Usuario ({clid})"
                    self.signals.show_message.emit(sender,"","whisper",clid)
                    self.signals.notif_message.emit(sender,"Susurro","whisper")
                    if not self._nc.get(clid) and self._conn:
                        def _res(clid=clid,conn=self._conn):
                            try:
                                info=conn.clientinfo(clid)
                                if info and info.get("client_nickname"):
                                    n=TS3Connection.unescape(info["client_nickname"])
                                    self._nc[clid]=n
                                    if WhispersWindow._instance:
                                        WhispersWindow._instance.update_name(clid,n)
                            except: pass
                        threading.Thread(target=_res,daemon=True).start()
            self.signals.whisper_talk.emit(clid, talking)

    def _on_upd(self, line):
        d=TS3Connection.parse(line); clid=d.get("clid","")
        if not clid or not self.state.has(clid): return
        upd={k:d[k] for k in ("client_input_muted","client_output_muted","client_nickname","client_flag_talking") if k in d}
        if upd: self.state.upsert(clid,upd); self._push()

    def _on_move(self, conn, line):
        d=TS3Connection.parse(line)
        clid=d.get("clid",""); new_cid=d.get("ctid",""); old_cid=d.get("cfid","")
        if not clid: return
        my_clid=self.state.get_my_clid(); my_cid=self.state.get_my_cid()
        if clid==my_clid:
            ch=conn.channel_name(new_cid); srv=conn.server_name()
            self.state.set_me(my_clid,new_cid,ch,srv); self._push()
            all_c=conn.clientlist_voice_info()
            self._nc={c["clid"]:c.get("client_nickname","?") for c in all_c if "clid" in c}
            self.state.set_clients([c for c in all_c if c.get("cid")==new_cid])

            self.signals.channel_changed.emit()
            self._push(); return
        in_before=self.state.has(clid)
        if new_cid==my_cid and not in_before:
            name=self._name(conn,clid,d)
            info=conn.clientinfo(clid)
            if info: info["clid"]=clid; info["cid"]=new_cid; info.setdefault("client_nickname",name); self.state.upsert(clid,info)
            else: self.state.upsert(clid,{"clid":clid,"cid":new_cid,"client_nickname":name})
            self._nc[clid]=name; log(f"Entró: {name}")
            self.signals.notify_join.emit(clid,name)
        elif in_before and new_cid!=my_cid:
            name=self._nc.get(clid,clid)
            self.state.remove(clid); log(f"Salió (movido): {name}")
            self.signals.notify_leave.emit(clid,name)
            self.signals.notify_moved.emit(clid,name)
            self.signals.whisper_leave.emit(clid)
        self._push()

    def _on_enter(self, conn, line):
        d=TS3Connection.parse(line); clid=d.get("clid",""); new_cid=d.get("ctid","")
        if new_cid!=self.state.get_my_cid(): return

        if self.state.has(clid):
            log(f"_on_enter: clid={clid} ya en state (procesado por _on_move), ignorando")
            return
        name=self._name(conn,clid,d)
        info=conn.clientinfo(clid)
        if info: info["clid"]=clid; info["cid"]=new_cid; info.setdefault("client_nickname",name); self.state.upsert(clid,info)
        else: self.state.upsert(clid,{"clid":clid,"cid":new_cid,"client_nickname":name})
        self._nc[clid]=name; log(f"Conectó: {name}")
        self.signals.notify_join.emit(clid,name); self._push()

    def _on_left(self, line):
        d=TS3Connection.parse(line); clid=d.get("clid","")

        self.signals.whisper_leave.emit(clid)
        if not self.state.has(clid): return
        name=self._nc.get(clid,clid)
        self.state.remove(clid); log(f"Desconectó: {name}")
        self.signals.notify_leave.emit(clid,name); self._push()

    def _on_msg(self, line):
        d=TS3Connection.parse(line)
        tm=d.get("targetmode","0"); sender=d.get("invokername","?")
        text=d.get("msg",""); invoker=d.get("invokerid",""); my=self.state.get_my_clid()
        if invoker==my: return
        typ="private" if tm=="1" else "channel" if tm=="2" else None
        if typ:
            self.signals.show_message.emit(sender,text,typ,"")
            self.signals.notif_message.emit(sender,text,typ)

    def _on_whisper(self, conn, line):
        d=TS3Connection.parse(line)
        sender=TS3Connection.unescape(d.get("invokername",""))
        clid=d.get("clid",d.get("invokerid",""))
        text=TS3Connection.unescape(d.get("msg",""))
        if not sender and clid: sender=self._nc.get(clid) or self._name(conn,clid,d)
        if not sender: sender="Susurro"
        if clid and sender: self._nc[clid]=sender
        self.signals.show_message.emit(sender,text or "","whisper",clid or sender)
        self.signals.notif_message.emit(sender,text or "Susurro","whisper")

    def _push(self):
        clients,ch,srv,grp,my_cid=self.state.snapshot()
        self.signals.update_users.emit(clients,ch,srv,grp,my_cid)


class HotkeyManager:
    """Gestiona hotkeys con pynput. IMPORTANTE: pynput corre en su propio hilo.
    Todas las llamadas a GUI se hacen via QMetaObject.invokeMethod con
    Qt.QueuedConnection para evitar freeze/crash."""

    def __init__(self, overlay: OverlayWindow, notif: NotificationsWindow,
                 cfg: dict, signals: Signals):
        self._overlay=overlay; self._notif=notif; self._cfg=cfg; self._signals=signals
        self._listener=None; self._start()

    def _fmt(self, key):
        if not key: return ""
        if key.startswith("<") and key.endswith(">"): return key
        if "+" in key:
            return "+".join(f"<{p}>" if not p.startswith("<") else p for p in key.split("+"))
        return f"<{key}>"

    def _start(self):
        if not PYNPUT_AVAILABLE: return
        hk =self._fmt(self._cfg.get("hotkey","f9"))
        hkc=self._fmt(self._cfg.get("hotkey_config",""))
        hkq=self._fmt(self._cfg.get("hotkey_quit",""))
        hkn=self._fmt(self._cfg.get("hotkey_notifications",""))
        hotkeys={}
        if hk:

            hotkeys[hk]=lambda: QMetaObject.invokeMethod(
                self._overlay, "toggle_visibility", Qt.ConnectionType.QueuedConnection)
        if hkc:

            hotkeys[hkc]=lambda: self._signals.open_settings.emit()
        if hkq:
            hotkeys[hkq]=lambda: QMetaObject.invokeMethod(
                QApplication.instance(), "quit", Qt.ConnectionType.QueuedConnection)
        if hkn:
            hotkeys[hkn]=lambda: QMetaObject.invokeMethod(
                self._notif, "toggle", Qt.ConnectionType.QueuedConnection)
        if not hotkeys: return
        try:
            self._listener=pynput_keyboard.GlobalHotKeys(hotkeys); self._listener.start()
            log(f"Hotkeys: {hk} {hkc} {hkq} {hkn}")
        except Exception as e:
            log(f"Hotkey error: {e}","WARN")

    def stop(self):
        if self._listener:
            try: self._listener.stop()
            except: pass

    def restart(self, cfg):
        self._cfg=cfg; self.stop(); self._listener=None; self._start()


class TrayManager:
    def __init__(self, overlay, notif, cfg):
        self._icon=None
        if not QSystemTrayIcon.isSystemTrayAvailable(): return
        self._icon=QSystemTrayIcon()
        pix=QPixmap(32,32); pix.fill(QColor(ACCENT))
        self._icon.setIcon(QIcon(pix)); self._icon.setToolTip("TS3 Overlay")
        menu=QMenu(); menu.setStyleSheet(APP_QSS)
        menu.addAction("Mostrar/Ocultar").triggered.connect(overlay.toggle_visibility)
        menu.addAction("Notificaciones").triggered.connect(notif.toggle)
        menu.addAction("Configuración").triggered.connect(overlay._open_settings)
        menu.addSeparator()
        menu.addAction("Salir").triggered.connect(QApplication.quit)
        self._icon.setContextMenu(menu); self._icon.show()

    def stop(self):
        if self._icon: self._icon.hide()


def main():
    log("="*40+" START v29 (PySide6)")
    app=QApplication(sys.argv)
    app.setApplicationName("TS3 Overlay")
    app.setStyleSheet(APP_QSS)
    app.setQuitOnLastWindowClosed(False)

    cfg=load_config()
    dlg=ConnectDialog(cfg)
    if dlg.exec()!=QDialog.DialogCode.Accepted: return
    cfg=dlg.result_cfg()
    if not cfg: return

    log(f"Config: port={cfg['port']} hotkey={cfg.get('hotkey')}")

    signals=Signals()
    state  =ChannelState()
    overlay=OverlayWindow(cfg, signals, app)
    notif  =NotificationsWindow(cfg, signals)

    thread=TS3EventThread(cfg, state, signals)
    thread.start()


    hotkeys=HotkeyManager(overlay, notif, cfg, signals)
    tray   =TrayManager(overlay, notif, cfg)

    orig_apply=overlay._apply_cfg
    def apply_all(new_cfg):
        orig_apply(new_cfg)
        hotkeys.restart(new_cfg)
        notif._cfg=new_cfg
        notif._messages=deque(maxlen=new_cfg.get("max_notifications",50))
    overlay._apply_cfg=apply_all

    def on_quit():
        log("Cerrando…"); hotkeys.stop(); thread.stop(); thread.wait(3000); tray.stop()
    app.aboutToQuit.connect(on_quit)
    sys.exit(app.exec())

if __name__=="__main__":
    main()