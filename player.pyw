"""Мини-плеер · Dynamic Island v3.0 — Enhanced"""

import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageTk
import threading, asyncio, io, sys, time, ctypes, ctypes.wintypes
import json, os, webbrowser, math, logging
from urllib.parse import quote
from datetime import datetime

# ── SDK ────────────────────────────────────────────────────────────
try:
    from winsdk.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as MM)
    from winsdk.windows.storage.streams import DataReader, Buffer, InputStreamOptions
except ImportError:
    sys.exit("pip install winsdk")

try:
    import pystray; HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

try:
    if getattr(sys, 'frozen', False):
        os.add_dll_directory(os.path.join(sys._MEIPASS, "vosk"))
    import vosk, sounddevice as sd; HAS_VOICE = True; vosk.SetLogLevel(-1)
except (ImportError, OSError):
    HAS_VOICE = False

try:
    from pypresence import Presence, ActivityType; HAS_RPC = True
except ImportError:
    HAS_RPC = False

try:
    import numpy as np; HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

# ── Constants ──────────────────────────────────────────────────────
VERSION = "3.0"
DISCORD_APP_ID = "1483924932261056522"

WIN_W, WIN_H = 436, 96
CORNER_RADIUS = 22
COVER_SIZE = 62
PILL_W, PILL_H = 120, 38
IDLE_W, IDLE_H = 76, 32

BG_COLOR = "#0d0d0d"
BG_RGB = (13, 13, 13)
ACCENT_DEFAULT = "#ffcc00"
TEXT_COLOR = "#eee"
SUBTEXT_COLOR = "#777"
BTN_COLOR = "#a0a0a0"
BTN_ACTIVE = "#ddd"
GRAD_DEFAULT = ("#3b82f6", "#8b5cf6")

EXPAND_DUR = 0.55
SHRINK_DUR = 0.40
STARTUP_RISE = 0.6
STARTUP_HOLD = 0.4
STARTUP_FADE = 0.35
CROSSFADE_DUR = 0.4
MARQUEE_SPEED = 1.5
MARQUEE_PAUSE = 80

PROG_BAR_H = 4
PROG_GLOW = 6
TICK_MS = 16

HK_PLAY = 1
HK_NEXT = 2
HK_PREV = 3
HK_VUP = 4
HK_VDOWN = 5
MOD_CTRL_ALT = 0x0002 | 0x0001
MOD_NOREPEAT = 0x4000
VK_SPACE = 0x20
VK_LEFT = 0x25
VK_RIGHT = 0x27
VK_UP = 0x26
VK_DOWN = 0x28

HISTORY_MAX = 500

# ── Paths ──────────────────────────────────────────────────────────
DIR = os.path.dirname(os.path.abspath(
    sys.executable if getattr(sys, 'frozen', False) else __file__))
CFG = os.path.join(DIR, "player_config.json")
HISTORY_FILE = os.path.join(DIR, "listening_history.json")
LOG_FILE = os.path.join(DIR, "player.log")

# ── Logging ────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8")]
)
log = logging.getLogger("DI")

# ── DPI & Theme ────────────────────────────────────────────────────
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except OSError:
    pass
ctk.set_appearance_mode("dark")

DEFAULT_CFG = {
    "x": None, "y": 16, "monitor": 0,
    "hotkeys": True, "idle_clock": True, "gestures": True,
    "marquee": True, "visualization": True, "crossfade": True,
    "discord_rpc": True,
}

# ── Config ─────────────────────────────────────────────────────────
def _cfg_load():
    try:
        with open(CFG) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}

def _cfg_save(d):
    try:
        old = _cfg_load()
        old.update(d)
        with open(CFG, "w") as f:
            json.dump(old, f)
    except OSError:
        log.warning("Failed to save config")

# ── Media control ──────────────────────────────────────────────────
_ctrl_mgr = None

def _ctrl(action):
    def run():
        global _ctrl_mgr
        lp = asyncio.new_event_loop()
        try:
            if _ctrl_mgr is None:
                _ctrl_mgr = lp.run_until_complete(MM.request_async())
            se = _ctrl_mgr.get_current_session()
            if se:
                lp.run_until_complete(action(se))
        except Exception:
            _ctrl_mgr = None
        finally:
            lp.close()
    threading.Thread(target=run, daemon=True).start()

# ── Icons (4× supersample) ────────────────────────────────────────
def _ico(fn, col="#ccc", sz=20):
    s = sz * 4
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    fn(ImageDraw.Draw(im), s, col)
    return ctk.CTkImage(im.resize((sz, sz), Image.LANCZOS), size=(sz, sz))

def _d_prev(d, s, c):
    d.rectangle([int(s*.12), int(s*.22), int(s*.19), int(s*.78)], fill=c)
    d.polygon([(int(s*.82), int(s*.18)), (int(s*.82), int(s*.82)),
               (int(s*.25), int(s*.5))], fill=c)

def _d_nxt(d, s, c):
    d.polygon([(int(s*.18), int(s*.18)), (int(s*.18), int(s*.82)),
               (int(s*.75), int(s*.5))], fill=c)
    d.rectangle([int(s*.81), int(s*.22), int(s*.88), int(s*.78)], fill=c)

def _d_pause(d, s, c):
    d.rounded_rectangle([int(s*.24), int(s*.18), int(s*.43), int(s*.82)],
                        radius=int(s*.04), fill=c)
    d.rounded_rectangle([int(s*.57), int(s*.18), int(s*.76), int(s*.82)],
                        radius=int(s*.04), fill=c)

def _d_play(d, s, c):
    d.polygon([(int(s*.28), int(s*.15)), (int(s*.28), int(s*.85)),
               (int(s*.78), int(s*.5))], fill=c)

def _d_x(d, s, c):
    w = max(2, int(s * .07))
    d.line([(int(s*.28), int(s*.28)), (int(s*.72), int(s*.72))], fill=c, width=w)
    d.line([(int(s*.72), int(s*.28)), (int(s*.28), int(s*.72))], fill=c, width=w)

# ── Helpers ────────────────────────────────────────────────────────
def _hide_tb(hwnd):
    GWL = -20
    s = ctypes.windll.user32.GetWindowLongW(hwnd, GWL)
    ctypes.windll.user32.SetWindowLongW(hwnd, GWL, (s | 0x80) & ~0x40000)

def _vol(vk):
    for _ in range(2):
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk, 0, 2, 0)

def _beep():
    """Short soft chime using synthesized sine wave."""
    def play():
        try:
            import wave, struct, tempfile, winsound
            sr = 22050
            dur = 0.12
            n = int(sr * dur)
            samples = []
            for i in range(n):
                t = i / sr
                fade = 1.0 - (i / n)  # fade out
                fade *= fade  # exponential decay
                val = math.sin(2 * math.pi * 1100 * t) * 0.3 * fade
                val += math.sin(2 * math.pi * 1650 * t) * 0.15 * fade
                samples.append(int(val * 32767))
            path = os.path.join(DIR, "_chime.wav")
            with wave.open(path, "w") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(sr)
                w.writeframes(struct.pack(f"<{n}h", *samples))
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_NODEFAULT)
        except Exception:
            pass
    threading.Thread(target=play, daemon=True).start()

def _pad(src, tw, th):
    out = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    out.paste(src, (0, 0))
    return out

def _autostart_on():
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
        winreg.QueryValueEx(k, "YMMiniPlayer"); winreg.CloseKey(k)
        return True
    except OSError:
        return False

def _autostart_set(on):
    import winreg
    k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
    if on:
        pw = sys.executable.replace("python.exe", "pythonw.exe")
        winreg.SetValueEx(k, "YMMiniPlayer", 0, winreg.REG_SZ,
                          f'"{pw}" "{os.path.join(DIR, "player.pyw")}"')
    else:
        try:
            winreg.DeleteValue(k, "YMMiniPlayer")
        except OSError:
            pass
    winreg.CloseKey(k)

def _ts(v):
    if v is None:
        return 0.0
    if hasattr(v, "total_seconds"):
        return v.total_seconds()
    try:
        return float(v) / 10_000_000
    except (TypeError, ValueError):
        return 0.0

# ── Track URL helpers ─────────────────────────────────────────────
_APP_URLS = {
    "spotify":  lambda t, a: f"https://open.spotify.com/search/{quote(f'{t} {a}')}",
    "yandex":   lambda t, a: f"https://music.yandex.ru/search?text={quote(f'{t} {a}')}",
    "vk":       lambda t, a: f"https://vk.com/audio?q={quote(f'{t} {a}')}",
    "deezer":   lambda t, a: f"https://www.deezer.com/search/{quote(f'{t} {a}')}",
    "apple":    lambda t, a: f"https://music.apple.com/search?term={quote(f'{t} {a}')}",
    "youtube":  lambda t, a: f"https://music.youtube.com/search?q={quote(f'{t} {a}')}",
}

def _detect_source(app_id):
    if not app_id:
        return None
    a = app_id.lower()
    for key in _APP_URLS:
        if key in a:
            return key
    if any(b in a for b in ("chrome", "firefox", "edge", "opera", "browser")):
        return "yandex"
    return None

def _track_url(source, title, artist):
    fn = _APP_URLS.get(source)
    art = artist or ""
    if fn and title:
        return fn(title, art)
    if title:
        return f"https://music.yandex.ru/search?text={quote(f'{title} {art}')}"
    return None

# ── Cover art URL (Deezer → iTunes fallback) ─────────────────────
_art_cache = {}

def _fetch_art_url(title, artist):
    key = f"{title}|{artist}"
    if key in _art_cache:
        return _art_cache[key]
    import urllib.request
    q = quote(f"{title} {artist}")
    try:
        url = f"https://api.deezer.com/search?q={q}&limit=1"
        with urllib.request.urlopen(url, timeout=5) as r:
            data = json.loads(r.read())
        if data.get("data"):
            art = data["data"][0]["album"]["cover_big"]
            _art_cache[key] = art
            return art
    except Exception:
        pass
    try:
        url = f"https://itunes.apple.com/search?term={q}&media=music&limit=1"
        with urllib.request.urlopen(url, timeout=5) as r:
            data = json.loads(r.read())
        if data.get("resultCount", 0) > 0:
            art = data["results"][0].get("artworkUrl100", "")
            art = art.replace("100x100", "600x600")
            _art_cache[key] = art
            return art
    except Exception:
        pass
    _art_cache[key] = None
    return None

# ── Lyrics fetcher ────────────────────────────────────────────────
_lyrics_cache = {}

def _fetch_lyrics(title, artist):
    key = f"{title}|{artist}"
    if key in _lyrics_cache:
        return _lyrics_cache[key]
    import urllib.request
    try:
        url = f"https://api.lyrics.ovh/v1/{quote(artist or 'unknown')}/{quote(title)}"
        with urllib.request.urlopen(url, timeout=8) as r:
            data = json.loads(r.read())
        lyrics = data.get("lyrics", "").strip()
        if lyrics:
            _lyrics_cache[key] = lyrics
            return lyrics
    except Exception:
        pass
    _lyrics_cache[key] = None
    return None


# ── Monitor detection ─────────────────────────────────────────────
def _get_monitors():
    monitors = []
    try:
        MONITORENUMPROC = ctypes.WINFUNCTYPE(
            ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p,
            ctypes.POINTER(ctypes.wintypes.RECT), ctypes.c_void_p)

        def cb(hmon, hdc, rect, data):
            r = rect.contents
            monitors.append({
                "left": r.left, "top": r.top,
                "right": r.right, "bottom": r.bottom,
                "width": r.right - r.left, "height": r.bottom - r.top
            })
            return True
        ctypes.windll.user32.EnumDisplayMonitors(
            None, None, MONITORENUMPROC(cb), 0)
    except Exception:
        pass
    if not monitors:
        w = ctypes.windll.user32.GetSystemMetrics(0)
        h = ctypes.windll.user32.GetSystemMetrics(1)
        monitors = [{"left": 0, "top": 0, "right": w, "bottom": h,
                     "width": w, "height": h}]
    return monitors

# ── Listening history ─────────────────────────────────────────────
class ListeningHistory:
    def __init__(self):
        self._data = []
        try:
            with open(HISTORY_FILE, encoding="utf-8") as f:
                self._data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass

    def add(self, title, artist, source=None):
        if not title:
            return
        if self._data and self._data[-1].get("title") == title \
                and self._data[-1].get("artist") == (artist or ""):
            return
        self._data.append({
            "title": title, "artist": artist or "",
            "source": source or "",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        if len(self._data) > HISTORY_MAX:
            self._data = self._data[-HISTORY_MAX:]
        self._save()

    def _save(self):
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=1)
        except OSError:
            log.warning("History save failed")

    @property
    def entries(self):
        return list(reversed(self._data))

# ── Win32 structures ──────────────────────────────────────────────
class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

class _SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]

class _BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_byte), ("BlendFlags", ctypes.c_byte),
                ("SourceConstantAlpha", ctypes.c_byte),
                ("AlphaFormat", ctypes.c_byte)]

class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
                ("biClrImportant", ctypes.c_uint32)]

class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER)]

# ── Easing ────────────────────────────────────────────────────────
def _ease_out_cubic(t):
    return 1 - (1 - t) ** 3

def _ease_out_expo(t):
    return 1.0 if t >= 1.0 else 1 - pow(2, -10 * t)

def _ease_out_back(t):
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * pow(t - 1, 3) + c1 * pow(t - 1, 2)

def _ease_in_cubic(t):
    return t * t * t

def _ease_in_out_cubic(t):
    return 4 * t * t * t if t < 0.5 else 1 - pow(-2 * t + 2, 3) / 2

def _spring(t, damping=12, freq=4.5):
    return 1 - math.exp(-damping * t) * math.cos(freq * math.pi * t)

# ── Hotkey manager (dedicated thread with own message loop) ──────
class HotkeyManager:
    WM_HOTKEY = 0x0312
    WM_USER_REGISTER = 0x0400 + 1
    WM_USER_STOP = 0x0400 + 2

    def __init__(self):
        self._enabled = True
        self._pending = []      # [(hk_id, mods, vk, cb)]
        self._cbs = {}
        self._root = None
        self._tid = None        # thread id for PostThreadMessage

    def start(self, root):
        """Must be called from main thread after Tk is ready."""
        self._root = root
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def register(self, hk_id, mods, vk, cb):
        self._pending.append((hk_id, mods, vk, cb))
        self._cbs[hk_id] = cb

    def _loop(self):
        """Dedicated thread: registers hotkeys HERE, runs own GetMessage."""
        self._tid = ctypes.windll.kernel32.GetCurrentThreadId()
        # Force message queue creation
        msg = ctypes.wintypes.MSG()
        ctypes.windll.user32.PeekMessageW(
            ctypes.byref(msg), None, 0, 0, 0)

        for hk_id, mods, vk, cb in self._pending:
            try:
                ok = ctypes.windll.user32.RegisterHotKey(
                    None, hk_id, mods | MOD_NOREPEAT, vk)
                if ok:
                    log.info("Hotkey %d registered", hk_id)
                else:
                    log.warning("Hotkey %d failed (occupied?)", hk_id)
            except Exception as e:
                log.warning("Hotkey error: %s", e)

        while ctypes.windll.user32.GetMessageW(
                ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == self.WM_HOTKEY:
                if self._enabled:
                    cb = self._cbs.get(msg.wParam)
                    if cb and self._root:
                        self._root.after(0, cb)
            elif msg.message == self.WM_USER_STOP:
                break
            ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
            ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))

        # Unregister on this thread (same thread that registered)
        for hk_id in self._cbs:
            ctypes.windll.user32.UnregisterHotKey(None, hk_id)

    def unregister_all(self):
        if self._tid:
            ctypes.windll.user32.PostThreadMessageW(
                self._tid, self.WM_USER_STOP, 0, 0)
            self._tid = None

    def poll(self):
        pass  # no-op, handled by dedicated thread

    @property
    def enabled(self):
        return self._enabled

    def toggle(self):
        self._enabled = not self._enabled

# ── Tooltip ───────────────────────────────────────────────────────
class Tooltip:
    def __init__(self, widget, text):
        self._w = widget
        self._text = text
        self._tip = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, e):
        x = self._w.winfo_rootx() + 20
        y = self._w.winfo_rooty() + self._w.winfo_height() + 4
        self._tip = tk.Toplevel(self._w)
        self._tip.wm_overrideredirect(True)
        self._tip.attributes("-topmost", True)
        self._tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self._tip, text=self._text, bg="#1a1a1a", fg="#bbb",
                 font=("Segoe UI", 9), padx=8, pady=4).pack()

    def _hide(self, _):
        if self._tip:
            self._tip.destroy()
            self._tip = None

# ── Discord Rich Presence ─────────────────────────────────────────
class DiscordRPC:
    def __init__(self):
        self._rpc = None
        self._connected = False
        self._enabled = True
        self._lock = threading.Lock()
        self._title = self._artist = ""
        self._source = None
        self._playing = False
        self._pos = self._dur = 0.0
        self._pos_time = 0.0
        self._dirty = False
        self._art_url = None
        self._last_art_key = ""
        if HAS_RPC:
            threading.Thread(target=self._loop, daemon=True).start()

    @property
    def enabled(self):
        return self._enabled

    def toggle(self):
        self._enabled = not self._enabled
        if not self._enabled:
            self._disconnect()

    def update(self, title, artist, playing, pos, dur, pos_time, source=None):
        with self._lock:
            changed = (title != self._title or artist != self._artist
                       or playing != self._playing)
            self._title, self._artist = title, artist
            self._source = source
            self._playing, self._pos, self._dur = playing, pos, dur
            self._pos_time = pos_time
            if changed:
                self._dirty = True

    def _connect(self):
        try:
            self._rpc = Presence(DISCORD_APP_ID)
            self._rpc.connect()
            self._connected = True
        except Exception:
            self._rpc = None
            self._connected = False

    def _disconnect(self):
        try:
            if self._rpc:
                self._rpc.clear()
                self._rpc.close()
        except Exception:
            pass
        self._rpc = None
        self._connected = False

    def _loop(self):
        while True:
            try:
                if not self._enabled:
                    time.sleep(5); continue
                if not self._connected:
                    self._connect()
                    if not self._connected:
                        time.sleep(15); continue
                with self._lock:
                    title, artist = self._title, self._artist
                    source = self._source
                    playing, pos, dur = self._playing, self._pos, self._dur
                    pos_time = self._pos_time
                    self._dirty = False
                if not title:
                    time.sleep(5); continue
                art_key = f"{title}|{artist}"
                if art_key != self._last_art_key:
                    self._last_art_key = art_key
                    self._art_url = _fetch_art_url(title, artist)
                track = _track_url(source, title, artist)
                btns = [{"label": "Слушать", "url": track}] if track else None
                kwargs = dict(
                    details=title[:128],
                    state=artist[:128] if artist else "Unknown",
                    activity_type=ActivityType.LISTENING,
                    buttons=btns,
                )
                if self._art_url:
                    kwargs["large_image"] = self._art_url
                    kwargs["large_text"] = f"{title} — {artist}"
                if playing and dur > 0:
                    elapsed = pos + (time.time() - pos_time)
                    start_ts = time.time() - elapsed
                    kwargs["start"] = int(start_ts)
                    kwargs["end"] = int(start_ts + dur)
                self._rpc.update(**kwargs)
            except Exception:
                self._connected = False
                self._rpc = None
            time.sleep(5)

    def stop(self):
        self._enabled = False
        self._disconnect()

# ── Settings window ───────────────────────────────────────────────
class SettingsWindow:
    _instance = None

    @classmethod
    def show(cls, parent, cfg, on_save):
        if cls._instance and cls._instance.win.winfo_exists():
            cls._instance.win.lift()
            return
        cls._instance = cls(parent, cfg, on_save)

    def __init__(self, parent, cfg, on_save):
        self.win = ctk.CTkToplevel(parent)
        self.win.title("Настройки Dynamic Island")
        self.win.geometry("400x540")
        self.win.resizable(False, False)
        self.win.attributes("-topmost", True)
        self._cfg = dict(cfg)
        self._on_save = on_save

        self.win.grid_columnconfigure(0, weight=1)
        row = 0

        ctk.CTkLabel(self.win, text=f"Dynamic Island v{VERSION}",
                     font=ctk.CTkFont("Segoe UI", 16, "bold")).grid(
            row=row, column=0, padx=20, pady=(16, 10)); row += 1

        # Monitor selection
        monitors = _get_monitors()
        names = [f"Монитор {i+1} ({m['width']}×{m['height']})"
                 for i, m in enumerate(monitors)]
        ctk.CTkLabel(self.win, text="Монитор:", anchor="w").grid(
            row=row, column=0, padx=20, pady=(10, 2), sticky="w"); row += 1
        idx = min(cfg.get("monitor", 0), len(names) - 1)
        self._mon_var = ctk.StringVar(value=names[idx])
        ctk.CTkOptionMenu(self.win, values=names,
                          variable=self._mon_var).grid(
            row=row, column=0, padx=20, sticky="ew"); row += 1

        # Switches
        self._vars = {}
        switches = [
            ("hotkeys",       "Горячие клавиши (Ctrl+Alt+…)"),
            ("discord_rpc",   "Discord Rich Presence"),
            ("idle_clock",    "Часы / погода в режиме ожидания"),
            ("gestures",      "Жесты (свайпы влево / вправо)"),
            ("marquee",       "Бегущая строка"),
            ("visualization", "Визуализация"),
            ("crossfade",     "Crossfade обложек"),
        ]
        for key, label in switches:
            var = ctk.BooleanVar(value=cfg.get(key, DEFAULT_CFG.get(key, True)))
            sw = ctk.CTkSwitch(self.win, text=label, variable=var)
            sw.grid(row=row, column=0, padx=20, pady=5, sticky="w"); row += 1
            self._vars[key] = var

        # Hotkey hints
        hint = ("  Ctrl+Alt+Space — Play/Pause\n"
                "  Ctrl+Alt+← — Назад    Ctrl+Alt+→ — Далее\n"
                "  Ctrl+Alt+↑ — Громче   Ctrl+Alt+↓ — Тише")
        ctk.CTkLabel(self.win, text=hint, text_color="#666",
                     font=ctk.CTkFont("Segoe UI", 10),
                     anchor="w", justify="left").grid(
            row=row, column=0, padx=28, sticky="w"); row += 1

        ctk.CTkButton(self.win, text="Сохранить", command=self._save,
                      fg_color="#2563eb", hover_color="#1d4ed8").grid(
            row=row, column=0, padx=20, pady=20, sticky="ew")

    def _save(self):
        for key, var in self._vars.items():
            self._cfg[key] = var.get()
        monitors = _get_monitors()
        names = [f"Монитор {i+1} ({m['width']}×{m['height']})"
                 for i, m in enumerate(monitors)]
        sel = self._mon_var.get()
        self._cfg["monitor"] = names.index(sel) if sel in names else 0
        self._on_save(self._cfg)
        self.win.destroy()

# ── Lyrics window ─────────────────────────────────────────────────
class LyricsWindow:
    _instance = None

    @classmethod
    def show(cls, parent, title, artist):
        if cls._instance and cls._instance.win.winfo_exists():
            cls._instance.win.destroy()
        cls._instance = cls(parent, title, artist)

    def __init__(self, parent, title, artist):
        self.win = ctk.CTkToplevel(parent)
        self.win.title(f"Текст — {title}")
        self.win.geometry("440x520")
        self.win.attributes("-topmost", True)
        self._tb = ctk.CTkTextbox(self.win, wrap="word",
                                  font=ctk.CTkFont("Segoe UI", 12))
        self._tb.pack(fill="both", expand=True, padx=12, pady=12)
        self._tb.insert("1.0", "Загрузка…")
        self._tb.configure(state="disabled")
        threading.Thread(target=self._load,
                         args=(title, artist), daemon=True).start()

    def _load(self, title, artist):
        lyrics = _fetch_lyrics(title, artist)
        txt = lyrics or "Текст не найден 😕"
        self._tb.after(0, lambda: (
            self._tb.configure(state="normal"),
            self._tb.delete("1.0", "end"),
            self._tb.insert("1.0", txt),
            self._tb.configure(state="disabled")
        ))

# ── History window ────────────────────────────────────────────────
class HistoryWindow:
    _instance = None

    @classmethod
    def show(cls, parent, history):
        if cls._instance and cls._instance.win.winfo_exists():
            cls._instance.win.lift()
            return
        cls._instance = cls(parent, history)

    def __init__(self, parent, history):
        self.win = ctk.CTkToplevel(parent)
        self.win.title("История прослушивания")
        self.win.geometry("500x600")
        self.win.attributes("-topmost", True)
        sf = ctk.CTkScrollableFrame(self.win, fg_color="transparent")
        sf.pack(fill="both", expand=True, padx=10, pady=10)
        entries = history.entries[:200]
        if not entries:
            ctk.CTkLabel(sf, text="Пусто", text_color="#666").pack(pady=20)
            return
        for e in entries:
            row = ctk.CTkFrame(sf, fg_color="#141414", corner_radius=8, height=38)
            row.pack(fill="x", pady=2, padx=2)
            row.pack_propagate(False)
            ctk.CTkLabel(row, text=f"♪  {e['title']}  —  {e['artist']}",
                         anchor="w", font=ctk.CTkFont("Segoe UI", 11)).pack(
                side="left", padx=10, fill="x", expand=True)
            ctk.CTkLabel(row, text=e.get("time", ""), text_color="#555",
                         font=ctk.CTkFont("Segoe UI", 10)).pack(
                side="right", padx=10)

# ═══════════════════════════════════════════════════════════════════
# ── Player ─────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════
class MiniPlayer:

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.0)
        self.root.configure(bg=BG_COLOR)

        # ── Config ──
        self._cfg = {**DEFAULT_CFG, **_cfg_load()}
        monitors = _get_monitors()
        mon_idx = min(self._cfg.get("monitor", 0), len(monitors) - 1)
        mon = monitors[mon_idx]
        scr_w = mon["width"]
        if self._cfg.get("x") is None:
            self._cfg["x"] = mon["left"] + (scr_w - WIN_W) // 2
        self.x = self._cfg["x"]
        self.y_show = self._cfg.get("y", mon["top"] + 16)
        self.y_hide = -WIN_H - 60
        self.pos_y = float(self.y_hide)
        self.vel_y = 0.0
        self.tgt_y = float(self.y_hide)
        self.cur_a, self.tgt_a = 0.0, 0.0
        self.root.geometry(f"{WIN_W}x{WIN_H}+{self.x}+{self.y_hide}")

        self.visible = self.dismissed = False
        self.running = True
        self.last_track = ""
        self._accent_hex = ACCENT_DEFAULT
        self._last_th = None
        self._pos = self._dur = 0.0
        self._playing = False
        self._pos_time = time.time()
        self._cov_ref = None
        self._track_url = None
        self._hwnd = None
        self._title_full = ""
        self._artist_full = ""
        self._source = None

        # Animation state
        self._animating = False
        self._anim_phase = None
        self._anim_id = None
        self._anim_start = 0.0

        # Crossfade
        self._crossfading = False
        self._cur_cov_pil = None
        self._old_cov_pil = None
        self._new_cov_pil = None
        self._crossfade_t0 = 0.0

        # Marquee
        self._marquee_active = False
        self._marquee_state = "pause"
        self._marquee_wait = MARQUEE_PAUSE
        self._title_y = 10

        # Idle clock
        self._idle_visible = False

        # Bounce notification
        self._bouncing = False
        self._bounce_t0 = 0.0

        # Gesture state
        self._swipe_x0 = 0
        self._swipe_y0 = 0
        self._swipe_t0 = 0.0
        self._is_drag = False

        # Icons
        self._ip  = _ico(_d_prev, BTN_COLOR)
        self._in  = _ico(_d_nxt,  BTN_COLOR)
        self._ipa = _ico(_d_pause, BTN_ACTIVE, 22)
        self._ipl = _ico(_d_play,  BTN_ACTIVE, 22)
        self._ix  = _ico(_d_x,     "#555", 14)

        # Subsystems
        self._discord = DiscordRPC() if HAS_RPC else None
        if self._discord and not self._cfg.get("discord_rpc", True):
            self._discord.toggle()
        self._history = ListeningHistory()
        self._hotkeys = HotkeyManager()

        self._build_ui()

        # Window region
        self.root.update_idletasks()
        try:
            hw = ctypes.windll.user32.GetParent(self.root.winfo_id())
            rgn = ctypes.windll.gdi32.CreateRoundRectRgn(
                0, 0, WIN_W + 1, WIN_H + 1, CORNER_RADIUS * 2, CORNER_RADIUS * 2)
            ctypes.windll.user32.SetWindowRgn(hw, rgn, True)
            _hide_tb(hw)
            self._hwnd = hw
        except Exception:
            pass

        self._setup_aa_overlay()
        self._setup_idle_pill()

        # ── Bindings ──
        self.root.bind("<MouseWheel>",
                       lambda e: _vol(0xAF if e.delta > 0 else 0xAE))
        for w in [self.main, self.info, self.a_lbl]:
            w.bind("<Button-1>", self._ds)
            w.bind("<B1-Motion>", self._dm)
            w.bind("<ButtonRelease-1>", self._de)
        self.t_canvas.bind("<Button-1>", self._ds)
        self.t_canvas.bind("<B1-Motion>", self._dm)
        self.t_canvas.bind("<ButtonRelease-1>", self._de)
        self.cov_lbl.bind("<Button-1>", self._open_track)
        self.cov_lbl.configure(cursor="hand2")
        self.prog.bind("<Button-1>", self._on_seek)
        self.root.bind("<Button-3>", self._context_menu)

        # ── Tooltips ──
        Tooltip(self.b_prev, "Предыдущий (Ctrl+Alt+←)")
        Tooltip(self.b_play, "Play / Pause (Ctrl+Alt+Space)")
        Tooltip(self.b_next, "Следующий (Ctrl+Alt+→)")
        Tooltip(self.cov_lbl, "Открыть в браузере")

        # ── Start systems ──
        self._tick()
        threading.Thread(target=self._wloop, daemon=True).start()
        if HAS_TRAY:
            self._mk_tray()
        if HAS_VOICE:
            self._start_voice()
        self._register_hotkeys()
        self.root.protocol("WM_DELETE_WINDOW", self._quit)
        self.root.after(300, self._startup_anim)
        log.info("Dynamic Island v%s started", VERSION)

    # ── UI ────────────────────────────────────────────────────────
    def _build_ui(self):
        self.main = ctk.CTkFrame(self.root, corner_radius=0,
                                 fg_color=BG_COLOR, border_width=0)
        self.main.pack(fill="both", expand=True)
        self.main.grid_columnconfigure(1, weight=1)

        # Cover
        cf = ctk.CTkFrame(self.main, corner_radius=0, fg_color=BG_COLOR,
                          width=COVER_SIZE + 4, height=COVER_SIZE + 4,
                          border_width=0)
        cf.grid(row=0, column=0, rowspan=2, padx=(16, 10), pady=13)
        cf.grid_propagate(False)
        self.cov_lbl = ctk.CTkLabel(cf, text="", fg_color="transparent")
        self.cov_lbl.place(relx=.5, rely=.5, anchor="center")
        ph = Image.new("RGBA", (COVER_SIZE, COVER_SIZE), (0, 0, 0, 0))
        ImageDraw.Draw(ph).rounded_rectangle(
            [0, 0, COVER_SIZE - 1, COVER_SIZE - 1], radius=14, fill="#161616")
        self._ph = ctk.CTkImage(ph, size=(COVER_SIZE, COVER_SIZE))
        self.cov_lbl.configure(image=self._ph)

        # Info area
        self.info = ctk.CTkFrame(self.main, fg_color="transparent", border_width=0)
        self.info.grid(row=0, column=1, sticky="sew", padx=(0, 4), pady=(16, 0))
        self.info.grid_columnconfigure(0, weight=1)

        # Title — Canvas for marquee
        self.t_canvas = tk.Canvas(self.info, height=20, bg=BG_COLOR,
                                  highlightthickness=0, bd=0)
        self.t_canvas.grid(row=0, column=0, sticky="ew")
        self._title_id = self.t_canvas.create_text(
            0, self._title_y, anchor="w", text="",
            font=("Segoe UI", 14, "bold"), fill=TEXT_COLOR)

        # Artist
        self.a_lbl = ctk.CTkLabel(self.info, text="",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=SUBTEXT_COLOR, anchor="w", fg_color="transparent")
        self.a_lbl.grid(row=1, column=0, sticky="ew")

        # Progress bar
        self._prog_h = PROG_BAR_H
        self._prog_glow = PROG_GLOW
        ch = self._prog_h + self._prog_glow * 2
        self.prog = tk.Canvas(self.main, height=ch, bg=BG_COLOR,
                              highlightthickness=0, bd=0)
        self.prog.grid(row=1, column=1, sticky="new", padx=(0, 4), pady=(2, 0))
        self._prog_val = 0.0
        self._prog_colors = GRAD_DEFAULT

        # Controls
        ct = ctk.CTkFrame(self.main, fg_color="transparent", border_width=0)
        ct.grid(row=0, column=2, rowspan=2, padx=(4, 16))

        def btn(img, cmd, sz=36, hc="#1a1a1a"):
            return ctk.CTkButton(ct, image=img, text="", command=cmd,
                width=sz, height=sz, corner_radius=10,
                fg_color="transparent", hover_color=hc,
                border_width=0, border_spacing=0)

        self.b_prev = btn(self._ip, self._do_prev)
        self.b_prev.pack(side="left", padx=1)
        self.b_play = btn(self._ipa, self._do_toggle, 40)
        self.b_play.pack(side="left", padx=2)
        self.b_next = btn(self._in, self._do_next)
        self.b_next.pack(side="left", padx=1)
        btn(self._ix, self._dismiss, 28, "#1c1010").pack(side="left", padx=(8, 0))


    # ── Context menu ──────────────────────────────────────────────
    def _context_menu(self, event):
        m = tk.Menu(self.root, tearoff=0, bg="#1a1a1a", fg="#ddd",
                    activebackground="#333", activeforeground="#fff",
                    font=("Segoe UI", 10), bd=0, relief="flat")
        m.add_command(label="♪  Текст песни", command=self._show_lyrics)
        m.add_command(label="⏱  История", command=self._show_history)
        m.add_separator()
        m.add_command(label="⚙  Настройки", command=self._show_settings)
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    def _show_lyrics(self):
        if self._title_full:
            LyricsWindow.show(self.root, self._title_full, self._artist_full)

    def _show_history(self):
        HistoryWindow.show(self.root, self._history)

    def _show_settings(self):
        SettingsWindow.show(self.root, self._cfg, self._on_settings_save)

    def _on_settings_save(self, new_cfg):
        self._cfg.update(new_cfg)
        _cfg_save(new_cfg)
        # Apply hotkeys toggle
        if self._cfg.get("hotkeys", True) != self._hotkeys.enabled:
            self._hotkeys.toggle()
        # Apply Discord RPC toggle
        if self._discord:
            want = self._cfg.get("discord_rpc", True)
            if want != self._discord.enabled:
                self._discord.toggle()
        log.info("Settings saved")

    # ── Hotkeys ───────────────────────────────────────────────────
    def _register_hotkeys(self):
        if not self._cfg.get("hotkeys", True):
            return
        m = MOD_CTRL_ALT
        self._hotkeys.register(HK_PLAY,  m, VK_SPACE, self._do_toggle)
        self._hotkeys.register(HK_NEXT,  m, VK_RIGHT, self._do_next)
        self._hotkeys.register(HK_PREV,  m, VK_LEFT,  self._do_prev)
        self._hotkeys.register(HK_VUP,   m, VK_UP,    lambda: _vol(0xAF))
        self._hotkeys.register(HK_VDOWN, m, VK_DOWN,  lambda: _vol(0xAE))
        self._hotkeys.start(self.root)

    # ── Startup droplet animation ─────────────────────────────────
    def _startup_anim(self):
        if self.visible or self._animating:
            return
        self._animating = True
        self._anim_phase = "startup"
        self._startup_t0 = time.time()
        self.pos_y = float(self.y_show + 50)
        self.root.geometry(f"{WIN_W}x{WIN_H}+{self.x}+{int(self.pos_y)}")
        self.root.attributes("-alpha", 0.01)
        sz = 44
        self._set_rgn((WIN_W - sz) // 2, (WIN_H - sz) // 2, sz, sz, sz, sz)
        self._startup_frame()

    def _startup_frame(self):
        t = time.time() - self._startup_t0
        TOTAL = STARTUP_RISE + STARTUP_HOLD + STARTUP_FADE

        if t < STARTUP_RISE:
            p = t / STARTUP_RISE
            ep = _ease_out_cubic(p)
            self.pos_y = self.y_show + 50 * (1 - ep)
            self.root.geometry(f"+{self.x}+{int(self.pos_y)}")
            a = min(0.95, ep * 1.8)
            self.cur_a = a
            self.root.attributes("-alpha", max(0.01, a))
            sz = int(44 + 8 * ep)
            self._set_rgn((WIN_W - sz) // 2, (WIN_H - sz) // 2, sz, sz, sz, sz)
        elif t < STARTUP_RISE + STARTUP_HOLD:
            p = (t - STARTUP_RISE) / STARTUP_HOLD
            pulse = math.sin(p * math.pi * 2) * 2
            sz = int(52 + pulse)
            self._set_rgn((WIN_W - sz) // 2, (WIN_H - sz) // 2, sz, sz, sz, sz)
        else:
            p = min(1.0, (t - STARTUP_RISE - STARTUP_HOLD) / STARTUP_FADE)
            e = _ease_in_cubic(p)
            sz = max(4, int(52 * (1 - e)))
            self._set_rgn((WIN_W - sz) // 2, (WIN_H - sz) // 2, sz, sz, sz, sz)
            self.pos_y = self.y_show + 15 * e
            self.root.geometry(f"+{self.x}+{int(self.pos_y)}")
            a = 0.95 * (1 - e)
            self.cur_a = a
            self.root.attributes("-alpha", max(0.01, a))

        if t < TOTAL:
            self.root.after(16, self._startup_frame)
        else:
            self._animating = False
            self._anim_phase = None
            self.visible = False
            self.pos_y = float(self.y_hide)
            self.tgt_y = float(self.y_hide)
            self.cur_a = 0.0
            self.tgt_a = 0.0
            self.root.attributes("-alpha", 0.0)
            self.root.geometry(f"+{self.x}+{self.y_hide}")
            self._set_full_rgn()

    # ── Per-pixel alpha overlay ───────────────────────────────────
    def _setup_aa_overlay(self):
        if not HAS_NUMPY:
            self._ov_hdc = None
            return
        sc = 8
        self._ov_margin = 6
        self._ov_w = WIN_W + self._ov_margin * 2
        self._ov_h = WIN_H + self._ov_margin * 2

        big = Image.new("L", (self._ov_w * sc, self._ov_h * sc), 0)
        ImageDraw.Draw(big).rounded_rectangle(
            [self._ov_margin * sc, self._ov_margin * sc,
             (self._ov_margin + WIN_W) * sc - 1,
             (self._ov_margin + WIN_H) * sc - 1],
            radius=CORNER_RADIUS * sc, fill=255)
        aa_mask = big.resize((self._ov_w, self._ov_h), Image.LANCZOS)

        hard_mask = Image.new("L", (self._ov_w, self._ov_h), 0)
        ImageDraw.Draw(hard_mask).rounded_rectangle(
            [self._ov_margin, self._ov_margin,
             self._ov_margin + WIN_W - 1,
             self._ov_margin + WIN_H - 1], radius=CORNER_RADIUS, fill=255)

        edge_mask = ImageChops.subtract(aa_mask, hard_mask)
        small = Image.new("RGBA", (self._ov_w, self._ov_h), (*BG_RGB, 0))
        small.putalpha(edge_mask)

        arr = np.array(small, dtype=np.float64)
        a = arr[:, :, 3:4] / 255.0
        arr[:, :, :3] *= a
        bgra = np.empty((self._ov_h, self._ov_w, 4), dtype=np.uint8)
        bgra[:, :, 0] = arr[:, :, 2].astype(np.uint8)
        bgra[:, :, 1] = arr[:, :, 1].astype(np.uint8)
        bgra[:, :, 2] = arr[:, :, 0].astype(np.uint8)
        bgra[:, :, 3] = arr[:, :, 3].astype(np.uint8)
        pixels = bytes(bgra)

        u32 = ctypes.windll.user32
        g32 = ctypes.windll.gdi32
        hdc_scr = u32.GetDC(0)
        self._ov_hdc = g32.CreateCompatibleDC(hdc_scr)

        bmi = _BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = self._ov_w
        bmi.bmiHeader.biHeight = -self._ov_h
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32

        ppv = ctypes.c_void_p()
        self._ov_bm = g32.CreateDIBSection(
            self._ov_hdc, ctypes.byref(bmi), 0,
            ctypes.byref(ppv), None, 0)
        if not self._ov_bm or not ppv.value:
            g32.DeleteDC(self._ov_hdc)
            u32.ReleaseDC(0, hdc_scr)
            self._ov_hdc = None
            return
        ctypes.memmove(ppv, pixels, len(pixels))
        self._ov_old = g32.SelectObject(self._ov_hdc, self._ov_bm)
        u32.ReleaseDC(0, hdc_scr)

        self._overlay = tk.Toplevel(self.root)
        self._overlay.overrideredirect(True)
        self._overlay.attributes("-topmost", True)
        self._overlay.geometry(
            f"{self._ov_w}x{self._ov_h}"
            f"+{self.x - self._ov_margin}+{int(self.pos_y) - self._ov_margin}")
        self._overlay.update_idletasks()

        self._ov_hwnd = ctypes.windll.user32.GetParent(self._overlay.winfo_id())
        GWL = -20
        es = u32.GetWindowLongW(self._ov_hwnd, GWL)
        es = (es | 0x80000 | 0x20 | 0x80) & ~0x40000
        u32.SetWindowLongW(self._ov_hwnd, GWL, es)
        self._ov_update(self.x, int(self.pos_y), 0)

    def _ov_update(self, x, y, alpha):
        if not getattr(self, '_ov_hdc', None):
            return
        blend = _BLENDFUNCTION(0, 0, alpha, 1)
        ctypes.windll.user32.UpdateLayeredWindow(
            self._ov_hwnd, None,
            ctypes.byref(_POINT(x - self._ov_margin, y - self._ov_margin)),
            ctypes.byref(_SIZE(self._ov_w, self._ov_h)),
            self._ov_hdc, ctypes.byref(_POINT(0, 0)),
            0, ctypes.byref(blend), 2)
        if self._hwnd:
            SWP = 0x0001 | 0x0002 | 0x0010
            ctypes.windll.user32.SetWindowPos(
                self._ov_hwnd, -1, 0, 0, 0, 0, SWP)

    def _ov_cleanup(self):
        if getattr(self, '_ov_hdc', None):
            try:
                ctypes.windll.gdi32.SelectObject(self._ov_hdc, self._ov_old)
                ctypes.windll.gdi32.DeleteObject(self._ov_bm)
                ctypes.windll.gdi32.DeleteDC(self._ov_hdc)
            finally:
                self._ov_hdc = None
        if hasattr(self, '_overlay'):
            try:
                self._overlay.destroy()
            except Exception:
                pass

    # ── Region helper ─────────────────────────────────────────────
    def _set_rgn(self, x, y, w, h, rx, ry):
        if not self._hwnd:
            return
        try:
            rgn = ctypes.windll.gdi32.CreateRoundRectRgn(
                x, y, x + w + 1, y + h + 1, rx, ry)
            ctypes.windll.user32.SetWindowRgn(self._hwnd, rgn, True)
        except Exception:
            pass

    def _set_full_rgn(self):
        if self._hwnd:
            try:
                rgn = ctypes.windll.gdi32.CreateRoundRectRgn(
                    0, 0, WIN_W + 1, WIN_H + 1,
                    CORNER_RADIUS * 2, CORNER_RADIUS * 2)
                ctypes.windll.user32.SetWindowRgn(self._hwnd, rgn, True)
            except Exception:
                pass

    # ── Animation: expand (show) ──────────────────────────────────
    def _show(self):
        if self.dismissed:
            return
        if self.visible:
            return

        from_idle = self._idle_visible
        if from_idle:
            self._idle_pill_hide()
            self._idle_visible = False

        if self._anim_id:
            self.root.after_cancel(self._anim_id)
            self._anim_id = None

        self.visible = True
        self._animating = True
        self._anim_phase = "expand"
        self._anim_start = time.time()

        if from_idle:
            self.pos_y = float(self.y_show)
        else:
            self.pos_y = float(self.y_show + 35)
        self.tgt_y = float(self.y_show)
        self.vel_y = 0
        self.root.geometry(f"{WIN_W}x{WIN_H}+{self.x}+{int(self.pos_y)}")

        pw, ph = PILL_W, PILL_H
        x_off = (WIN_W - pw) // 2
        self._set_rgn(x_off, 0, pw, ph, ph, ph)
        self.root.attributes("-alpha", 0.97)
        self.cur_a = 0.97
        self.tgt_a = 0.97
        self._anim_expand()

    def _anim_expand(self):
        t = min(1.0, (time.time() - self._anim_start) / EXPAND_DUR)

        tw = min(1.0, t * 1.15)
        ew = _spring(tw, damping=10, freq=3.2) if tw < 1 else 1.0
        th = max(0.0, (t - 0.06) / 0.94)
        eh = _ease_out_cubic(min(1.0, th))
        ey = _ease_out_expo(t)
        ea = min(1.0, t * 5)

        sw, sh = PILL_W, PILL_H
        cur_w = int(sw + (WIN_W - sw) * min(1.0, ew))
        cur_h = int(sh + (WIN_H - sh) * min(1.0, eh))

        pill_r = min(cur_w, cur_h)
        tr = max(0.0, (t - 0.3) / 0.7)
        er = _ease_out_cubic(min(1.0, tr))
        cur_rx = max(44, min(int(pill_r + (44 - pill_r) * er), cur_h))
        cur_ry = cur_rx

        x_off = (WIN_W - cur_w) // 2
        self._set_rgn(x_off, 0, cur_w, cur_h, cur_rx, cur_ry)

        rise = 35
        cur_y = self.y_show + rise * (1 - ey)
        self.pos_y = cur_y
        self.root.geometry(f"+{self.x}+{int(cur_y)}")

        self.cur_a = 0.97 * ea
        self.root.attributes("-alpha", max(0.01, self.cur_a))

        if t < 1.0:
            self._anim_id = self.root.after(12, self._anim_expand)
        else:
            self._finish_expand()

    def _finish_expand(self):
        self._animating = False
        self._anim_phase = None
        self._anim_id = None
        self.pos_y = float(self.y_show)
        self.tgt_y = float(self.y_show)
        self.vel_y = 0
        self.cur_a = 0.97
        self.tgt_a = 0.97
        self.root.attributes("-alpha", 0.97)
        self.root.geometry(f"+{self.x}+{int(self.y_show)}")
        self._set_full_rgn()

    # ── Animation: shrink (hide) ──────────────────────────────────
    def _hide(self):
        if not self.visible:
            return
        if self._anim_id:
            self.root.after_cancel(self._anim_id)
            self._anim_id = None

        self.visible = False
        self._animating = True
        self._anim_phase = "shrink"
        self._anim_start = time.time()
        self._shrink_y0 = self.pos_y
        self._anim_shrink()

    def _anim_shrink(self):
        t = min(1.0, (time.time() - self._anim_start) / SHRINK_DUR)
        ew = _ease_in_cubic(t)
        eh = _ease_in_cubic(t)
        ey = _ease_in_cubic(t)
        ea = _ease_in_cubic(t)

        sw, sh = PILL_W, PILL_H
        cur_w = int(WIN_W + (sw - WIN_W) * ew)
        cur_h = int(WIN_H + (sh - WIN_H) * eh)

        pill_r = min(cur_w, cur_h)
        tr = _ease_in_cubic(t)
        cur_rx = max(44, min(int(44 + (pill_r - 44) * tr), cur_h))
        cur_ry = cur_rx

        x_off = (WIN_W - cur_w) // 2
        self._set_rgn(x_off, 0, cur_w, cur_h, cur_rx, cur_ry)

        drop = 25
        cur_y = self._shrink_y0 + drop * ey
        self.pos_y = cur_y
        self.root.geometry(f"+{self.x}+{int(cur_y)}")

        self.cur_a = 0.97 * (1 - ea)
        self.root.attributes("-alpha", max(0.01, self.cur_a))

        if t < 1.0:
            self._anim_id = self.root.after(12, self._anim_shrink)
        else:
            self._finish_shrink()

    def _finish_shrink(self):
        self._animating = False
        self._anim_phase = None
        self._anim_id = None

        # Hide main window fully
        self.pos_y = float(self.y_hide)
        self.tgt_y = float(self.y_hide)
        self.vel_y = 0
        self.cur_a = 0.0
        self.tgt_a = 0.0
        self.root.attributes("-alpha", 0.0)
        self.root.geometry(f"+{self.x}+{self.y_hide}")
        self._set_full_rgn()

        # Show idle pill overlay if enabled
        if self._cfg.get("idle_clock", True) and not self.dismissed:
            self._idle_visible = True
            self._idle_pill_show()
            self._update_idle_clock()
        else:
            self._idle_visible = False

    # ── Idle pill (per-pixel-alpha overlay) ──────────────────────
    def _setup_idle_pill(self):
        """Dedicated layered window for idle clock — smooth AA, click-through."""
        from PIL import ImageFont
        pw, ph = IDLE_W, IDLE_H
        self._idle_pw, self._idle_ph = pw, ph
        self._idle_font = None
        for path in ("C:/Windows/Fonts/segoeuib.ttf", "segoeuib.ttf",
                      "C:/Windows/Fonts/segoeui.ttf", "segoeui.ttf"):
            try:
                self._idle_font = ImageFont.truetype(path, 15)
                break
            except (OSError, IOError):
                pass
        if not self._idle_font:
            self._idle_font = ImageFont.load_default()

        # Pre-render base pill with AA (4× supersample)
        sc = 4
        big = Image.new("RGBA", (pw * sc, ph * sc), (0, 0, 0, 0))
        ImageDraw.Draw(big).rounded_rectangle(
            [0, 0, pw * sc - 1, ph * sc - 1],
            radius=ph * sc // 2, fill=(*BG_RGB, 230))
        self._idle_pill_base = big.resize((pw, ph), Image.LANCZOS)

        # Toplevel — centered on screen same as player
        self._idle_win = tk.Toplevel(self.root)
        self._idle_win.overrideredirect(True)
        self._idle_win.attributes("-topmost", True)
        ix = self.x + (WIN_W - pw) // 2
        iy = int(self.y_show)
        self._idle_win.geometry(f"{pw}x{ph}+{ix}+{iy}")
        self._idle_win.update_idletasks()

        self._idle_hwnd = ctypes.windll.user32.GetParent(
            self._idle_win.winfo_id())
        GWL = -20
        es = ctypes.windll.user32.GetWindowLongW(self._idle_hwnd, GWL)
        es = (es | 0x80000 | 0x20 | 0x80) & ~0x40000
        ctypes.windll.user32.SetWindowLongW(self._idle_hwnd, GWL, es)

        # GDI resources
        u32 = ctypes.windll.user32
        g32 = ctypes.windll.gdi32
        hdc_scr = u32.GetDC(0)
        self._idle_hdc = g32.CreateCompatibleDC(hdc_scr)

        bmi = _BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = pw
        bmi.bmiHeader.biHeight = -ph
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32

        self._idle_ppv = ctypes.c_void_p()
        self._idle_bm = g32.CreateDIBSection(
            self._idle_hdc, ctypes.byref(bmi), 0,
            ctypes.byref(self._idle_ppv), None, 0)
        self._idle_old_bm = g32.SelectObject(self._idle_hdc, self._idle_bm)
        u32.ReleaseDC(0, hdc_scr)

        # Initial render
        self._render_idle_pill("")
        self._idle_win.withdraw()

    def _render_idle_pill(self, text):
        """Draw pill + text, push to layered window."""
        if not HAS_NUMPY or not getattr(self, '_idle_hdc', None):
            return
        pw, ph = self._idle_pw, self._idle_ph
        img = self._idle_pill_base.copy()
        if text:
            draw = ImageDraw.Draw(img)
            draw.text((pw // 2, ph // 2), text, fill=(210, 210, 210, 255),
                      font=self._idle_font, anchor="mm")

        # Premultiply alpha → BGRA
        arr = np.array(img, dtype=np.float64)
        a = arr[:, :, 3:4] / 255.0
        arr[:, :, :3] *= a
        bgra = np.empty((ph, pw, 4), dtype=np.uint8)
        bgra[:, :, 0] = arr[:, :, 2].astype(np.uint8)  # B
        bgra[:, :, 1] = arr[:, :, 1].astype(np.uint8)  # G
        bgra[:, :, 2] = arr[:, :, 0].astype(np.uint8)  # R
        bgra[:, :, 3] = arr[:, :, 3].astype(np.uint8)  # A
        raw = bytes(bgra)
        ctypes.memmove(self._idle_ppv, raw, len(raw))

        blend = _BLENDFUNCTION(0, 0, 255, 1)
        ix = self.x + (WIN_W - pw) // 2
        iy = int(self.y_show)
        ctypes.windll.user32.UpdateLayeredWindow(
            self._idle_hwnd, None,
            ctypes.byref(_POINT(ix, iy)),
            ctypes.byref(_SIZE(pw, ph)),
            self._idle_hdc, ctypes.byref(_POINT(0, 0)),
            0, ctypes.byref(blend), 2)

    def _idle_pill_show(self):
        if hasattr(self, '_idle_win'):
            self._render_idle_pill(time.strftime("%H:%M"))
            self._idle_win.deiconify()
            self._idle_win.attributes("-topmost", True)

    def _idle_pill_hide(self):
        if hasattr(self, '_idle_win'):
            self._idle_win.withdraw()

    def _idle_pill_cleanup(self):
        if getattr(self, '_idle_hdc', None):
            try:
                ctypes.windll.gdi32.SelectObject(self._idle_hdc, self._idle_old_bm)
                ctypes.windll.gdi32.DeleteObject(self._idle_bm)
                ctypes.windll.gdi32.DeleteDC(self._idle_hdc)
            finally:
                self._idle_hdc = None
        if hasattr(self, '_idle_win'):
            try:
                self._idle_win.destroy()
            except Exception:
                pass

    def _update_idle_clock(self):
        if not self._idle_visible:
            return
        self._render_idle_pill(time.strftime("%H:%M"))
        self.root.after(1000, self._update_idle_clock)

    # ── Gradient progress bar ─────────────────────────────────────
    def _build_grad_strip(self, total_w):
        bar_h = self._prog_h
        glow = self._prog_glow
        h = bar_h + glow * 2
        cy = h // 2

        c1 = tuple(int(self._prog_colors[0][i:i+2], 16) for i in (1, 3, 5))
        c2 = tuple(int(self._prog_colors[1][i:i+2], 16) for i in (1, 3, 5))

        if HAS_NUMPY:
            t = np.linspace(0, 1, total_w)
            r = (c1[0] + (c2[0] - c1[0]) * t).astype(np.uint8)
            g = (c1[1] + (c2[1] - c1[1]) * t).astype(np.uint8)
            b = (c1[2] + (c2[2] - c1[2]) * t).astype(np.uint8)

            # Bar strip (vectorized)
            strip_arr = np.zeros((bar_h, total_w, 4), dtype=np.uint8)
            strip_arr[:, :, 0] = r
            strip_arr[:, :, 1] = g
            strip_arr[:, :, 2] = b
            strip_arr[:, :, 3] = 255
            strip = Image.fromarray(strip_arr, "RGBA")

            # Glow strip (vectorized)
            glow_arr = np.zeros((h, total_w, 4), dtype=np.uint8)
            for dy in range(-glow, glow + 1):
                a = int(70 * max(0, 1 - abs(dy) / glow))
                py = cy + dy
                if 0 <= py < h:
                    glow_arr[py, :, 0] = r
                    glow_arr[py, :, 1] = g
                    glow_arr[py, :, 2] = b
                    glow_arr[py, :, 3] = a
            glow_strip = Image.fromarray(glow_arr, "RGBA")
        else:
            strip = Image.new("RGBA", (total_w, bar_h), (0, 0, 0, 0))
            glow_strip = Image.new("RGBA", (total_w, h), (0, 0, 0, 0))
            for x in range(total_w):
                frac = x / max(1, total_w - 1)
                r = int(c1[0] + (c2[0] - c1[0]) * frac)
                g = int(c1[1] + (c2[1] - c1[1]) * frac)
                b = int(c1[2] + (c2[2] - c1[2]) * frac)
                for y in range(bar_h):
                    strip.putpixel((x, y), (r, g, b, 255))
                for dy in range(-glow, glow + 1):
                    a = int(70 * max(0, 1 - abs(dy) / glow))
                    py = cy + dy
                    if 0 <= py < h:
                        glow_strip.putpixel((x, py), (r, g, b, a))

        glow_strip = glow_strip.filter(ImageFilter.GaussianBlur(radius=4))
        self._grad_strip = strip
        self._glow_strip = glow_strip
        self._grad_w = total_w
        self._grad_colors_key = self._prog_colors

    def _draw_prog(self, frac):
        c = self.prog
        c.update_idletasks()
        w, h_c = c.winfo_width(), c.winfo_height()
        if w < 4:
            return

        viz_active = self._playing and self._cfg.get("visualization", True)
        # Reserve space for viz bars so progress doesn't overlap them
        viz_reserve = 24 if viz_active else 0
        max_pw = w - viz_reserve
        pw = max(0, min(int(w * frac), max_pw))
        pw_q = max(0, pw // 2 * 2)

        # Rebuild heavy progress bar image only when progress changes
        prog_changed = not hasattr(self, '_last_pw') \
                or self._last_pw != pw_q \
                or not hasattr(self, '_grad_colors_key') \
                or self._grad_colors_key != self._prog_colors
        if prog_changed:
            self._last_pw = pw_q
            bar_h = self._prog_h
            glow = self._prog_glow
            h = bar_h + glow * 2
            cy = h // 2
            y0 = cy - bar_h // 2

            if not hasattr(self, '_grad_strip') or self._grad_w != w \
                    or self._grad_colors_key != self._prog_colors:
                self._build_grad_strip(w)

            img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            track_end = w - viz_reserve - 1 if viz_reserve else w - 1
            draw.rounded_rectangle([0, y0, track_end, y0 + bar_h - 1],
                                   radius=bar_h // 2, fill=(255, 255, 255, 18))

            if pw_q > 2:
                bar = self._grad_strip.crop((0, 0, pw_q, bar_h))
                mask = Image.new("L", (pw_q, bar_h), 0)
                ImageDraw.Draw(mask).rounded_rectangle(
                    [0, 0, pw_q - 1, bar_h - 1], radius=bar_h // 2, fill=255)
                bar.putalpha(mask)
                glow_crop = self._glow_strip.crop((0, 0, pw_q, h))
                img = Image.alpha_composite(img, _pad(glow_crop, w, h))
                img.paste(bar, (0, y0), bar)

            self._prog_base = img
            self._prog_tk = ImageTk.PhotoImage(img)
            c.delete("all")
            c.create_image(0, 0, anchor="nw", image=self._prog_tk)
            # Reset viz items so they get recreated
            self._viz_ids = []

        # Lightweight viz bars drawn directly on Canvas (no PIL rebuild)
        if viz_active:
            self._draw_viz_canvas(c)
        elif hasattr(self, '_viz_ids') and self._viz_ids:
            for vid in self._viz_ids:
                c.delete(vid)
            self._viz_ids = []

    def _draw_viz_canvas(self, c):
        """Lightweight animated eq bars drawn directly on tk Canvas."""
        # Delete previous bars
        for vid in getattr(self, '_viz_ids', []):
            c.delete(vid)
        self._viz_ids = []

        w = c.winfo_width()
        h = c.winfo_height()
        if w < 20 or h < 4:
            return

        t = time.time()
        c1 = tuple(int(self._prog_colors[0][i:i+2], 16) for i in (1, 3, 5))
        c2 = tuple(int(self._prog_colors[1][i:i+2], 16) for i in (1, 3, 5))
        bar_w, gap, num = 3, 2, 4
        total = num * bar_w + (num - 1) * gap
        start_x = w - total - 4
        cy = h // 2

        for i in range(num):
            frac = 0.3 + 0.7 * abs(math.sin(t * (3.2 + i * 0.8) + i * 1.4))
            bh = max(2, int(frac * (h - 2)))
            x = start_x + i * (bar_w + gap)
            y = cy - bh // 2
            ct = i / max(1, num - 1)
            r = int(c1[0] + (c2[0] - c1[0]) * ct)
            g = int(c1[1] + (c2[1] - c1[1]) * ct)
            b = int(c1[2] + (c2[2] - c1[2]) * ct)
            color = f"#{r:02x}{g:02x}{b:02x}"
            vid = c.create_rectangle(x, y, x + bar_w, y + bh,
                                     fill=color, outline="")
            self._viz_ids.append(vid)

    # ── Marquee ───────────────────────────────────────────────────
    def _set_title(self, title):
        self._title_full = title
        self.t_canvas.itemconfig(self._title_id, text=title)
        self.t_canvas.coords(self._title_id, 0, self._title_y)
        self.t_canvas.update_idletasks()
        bbox = self.t_canvas.bbox(self._title_id)
        cw = self.t_canvas.winfo_width()
        if bbox and cw > 1 and (bbox[2] - bbox[0]) > cw \
                and self._cfg.get("marquee", True):
            self._marquee_active = True
            self._marquee_state = "pause"
            self._marquee_wait = MARQUEE_PAUSE
        else:
            self._marquee_active = False

    def _marquee_tick(self):
        if not self._marquee_active or not self.visible:
            return
        cw = self.t_canvas.winfo_width()
        if cw <= 1:
            return

        if self._marquee_state == "pause":
            self._marquee_wait -= 1
            if self._marquee_wait <= 0:
                self._marquee_state = "scroll"
        elif self._marquee_state == "scroll":
            self.t_canvas.move(self._title_id, -MARQUEE_SPEED, 0)
            bbox = self.t_canvas.bbox(self._title_id)
            if bbox and bbox[2] <= cw:
                self._marquee_state = "pause_end"
                self._marquee_wait = MARQUEE_PAUSE
        elif self._marquee_state == "pause_end":
            self._marquee_wait -= 1
            if self._marquee_wait <= 0:
                self.t_canvas.coords(self._title_id, 0, self._title_y)
                self._marquee_state = "pause"
                self._marquee_wait = MARQUEE_PAUSE

    # ── Crossfade cover ───────────────────────────────────────────
    def _apply_cover_img(self, rgba_img):
        hi = COVER_SIZE * 2
        bg = Image.new("RGB", (hi, hi), BG_RGB)
        bg.paste(rgba_img, (0, 0), rgba_img)
        ci = ctk.CTkImage(bg, size=(COVER_SIZE, COVER_SIZE))
        self.cov_lbl.configure(image=ci)
        self._cov_ref = ci

    def _crossfade_tick(self):
        if not self._crossfading:
            return
        t = (time.time() - self._crossfade_t0) / CROSSFADE_DUR
        if t >= 1.0:
            self._crossfading = False
            self._cur_cov_pil = self._new_cov_pil
            self._apply_cover_img(self._new_cov_pil)
        else:
            blended = Image.blend(self._old_cov_pil, self._new_cov_pil, t)
            self._apply_cover_img(blended)

    # ── Tick ──────────────────────────────────────────────────────
    def _tick(self):
        if not self._animating:
            if self.visible and self._bouncing:
                bt = time.time() - self._bounce_t0
                if bt < 0.25:
                    off = -6 * math.sin(bt / 0.25 * math.pi)
                    self.pos_y = self.y_show + off
                else:
                    self._bouncing = False
                    self.pos_y = float(self.y_show)
                self.root.geometry(f"+{self.x}+{int(self.pos_y)}")
            else:
                dy = self.pos_y - self.tgt_y
                self.vel_y += (-120 * dy - 14 * self.vel_y) * 0.016
                self.pos_y += self.vel_y * 0.016
                self.root.geometry(f"+{self.x}+{int(self.pos_y)}")
            self.cur_a += (self.tgt_a - self.cur_a) * 0.14
            self.root.attributes("-alpha", max(0, min(1, self.cur_a)))

        # AA overlay
        a_byte = max(0, min(255, int(self.cur_a * 255)))
        if self._animating or not self.visible:
            a_byte = 0
        self._ov_update(self.x, int(self.pos_y), a_byte)

        # Progress — always update
        if self._dur > 0:
            cur = self._pos + (time.time() - self._pos_time
                               if self._playing else 0)
            self._prog_val = max(0, min(1, cur / self._dur))
            self._draw_prog(self._prog_val)

        # Crossfade
        if self._crossfading:
            self._crossfade_tick()

        # Marquee
        if self.visible:
            self._marquee_tick()

        self.root.after(TICK_MS, self._tick)

    # ── Drag & Gestures ───────────────────────────────────────────
    def _ds(self, e):
        self._dx, self._dy = e.x, e.y
        self._swipe_x0 = e.x
        self._swipe_y0 = e.y
        self._swipe_t0 = time.time()
        self._is_drag = False

    def _dm(self, e):
        if self._is_drag or not self._cfg.get("gestures", True):
            self._do_drag(e)
            return
        dy = abs(e.y - self._swipe_y0)
        dx = abs(e.x - self._swipe_x0)
        dt = time.time() - self._swipe_t0
        if dy > 10:
            self._is_drag = True
            self._do_drag(e)
        elif dx > 15 and dt > 0.25:
            # Slow horizontal move = drag, not swipe
            self._is_drag = True
            self._do_drag(e)

    def _do_drag(self, e):
        self.x = self.root.winfo_x() + e.x - self._dx
        ny = self.root.winfo_y() + e.y - self._dy
        self.pos_y = self.tgt_y = self.y_show = float(ny)
        self.vel_y = 0
        self.root.geometry(f"+{self.x}+{ny}")

    def _de(self, e):
        dt = time.time() - self._swipe_t0
        dx = e.x - self._swipe_x0
        dy = abs(e.y - self._swipe_y0)

        if self._cfg.get("gestures", True) and not self._is_drag \
                and dt < 0.4 and abs(dx) > 50 and dy < 30:
            if dx < 0:
                self._do_next()
            else:
                self._do_prev()
        else:
            _cfg_save({"x": self.x, "y": self.y_show})

    def _on_seek(self, e):
        if self._dur <= 0:
            return
        w = self.prog.winfo_width()
        if w <= 0:
            return
        frac = max(0, min(1, e.x / w))
        self._pos = frac * self._dur
        self._pos_time = time.time()
        self._prog_val = frac
        tgt = frac * self._dur

        async def do(se):
            from datetime import timedelta
            try:
                await se.try_change_playback_position_async(
                    timedelta(seconds=tgt))
            except Exception:
                try:
                    await se.try_change_playback_position_async(int(tgt * 1e7))
                except Exception:
                    pass
        _ctrl(do)

    def _open_track(self, _=None):
        if self._track_url:
            webbrowser.open(self._track_url)

    # ── Controls ──────────────────────────────────────────────────
    def _do_toggle(self):
        _ctrl(lambda se: se.try_toggle_play_pause_async())

    def _do_play(self):
        _ctrl(lambda se: se.try_play_async())

    def _do_pause(self):
        _ctrl(lambda se: se.try_pause_async())

    def _do_next(self):
        _ctrl(lambda se: se.try_skip_next_async())

    def _do_prev(self):
        _ctrl(lambda se: se.try_skip_previous_async())

    def _dismiss(self):
        self.dismissed = True
        self._hide()

    # ── Track change notification ─────────────────────────────────
    def _notify_track_change(self):
        if not self.visible or self._animating:
            return
        self._bouncing = True
        self._bounce_t0 = time.time()

    # ── Watcher ───────────────────────────────────────────────────
    def _wloop(self):
        lp = asyncio.new_event_loop()
        mgr = None
        prev = ""
        while self.running:
            try:
                if mgr is None:
                    mgr = lp.run_until_complete(MM.request_async())
                se = mgr.get_current_session()
                if not se:
                    time.sleep(0.5); continue
                pr = lp.run_until_complete(
                    se.try_get_media_properties_async())
                pb = se.get_playback_info()
                tl = se.get_timeline_properties()
                pl = pb.playback_status == 4
                ps = _ts(tl.position)
                dr = _ts(tl.end_time)
                try:
                    ts = tl.last_updated_time.timestamp()
                except Exception:
                    ts = time.time()
                try:
                    src = _detect_source(se.source_app_user_model_id)
                except Exception:
                    src = None
                tk_ = f"{pr.title}|{pr.artist}"
                th = None
                if tk_ != prev and tk_ != "|" and pr.thumbnail:
                    prev = tk_
                    th = lp.run_until_complete(self._rthumb(pr.thumbnail))
                self.root.after(0, self._upd,
                    pr.title or "", pr.artist or "", pl, ps, dr, ts, th, src)
            except Exception:
                mgr = None
            time.sleep(0.15)
        lp.close()

    async def _rthumb(self, ref):
        try:
            s = await ref.open_read_async()
            if not s.size:
                return None
            b = Buffer(s.size)
            await s.read_async(b, s.size, InputStreamOptions.READ_AHEAD)
            r = DataReader.from_buffer(b)
            d = bytearray(b.length)
            r.read_bytes(d)
            return bytes(d)
        except Exception:
            return None

    def _upd(self, title, artist, playing, pos, dur, ts, thumb, source=None):
        tk_ = f"{title}|{artist}"
        is_new_track = tk_ != self.last_track and tk_ != "|"
        if is_new_track:
            self.last_track = tk_
            self.dismissed = False
            self._history.add(title, artist, source)
            if self.visible:
                self._notify_track_change()

        if playing and not self.dismissed:
            self._show()
        if not playing and not self.visible:
            return

        self._set_title(title)
        self._artist_full = artist
        self.a_lbl.configure(text=artist)
        self._pos, self._dur, self._playing = pos, dur, playing
        self._pos_time = ts
        self._source = source
        self._track_url = _track_url(source, title, artist)
        self.b_play.configure(image=self._ipa if playing else self._ipl)

        if self._discord:
            self._discord.update(title, artist, playing, pos, dur, ts, source)
        if not playing and self.visible:
            self._hide()

        if thumb:
            h = hash(thumb[:256])
            if h != self._last_th:
                self._last_th = h
                self._setcov(thumb)

    def _setcov(self, data):
        try:
            hi = COVER_SIZE * 2
            raw = Image.open(io.BytesIO(data)).convert("RGBA").resize(
                (hi, hi), Image.LANCZOS)

            # Apply rounded mask
            mask = Image.new("L", (hi, hi), 0)
            ImageDraw.Draw(mask).rounded_rectangle(
                [0, 0, hi - 1, hi - 1], radius=28, fill=255)
            raw.putalpha(mask)

            # Crossfade
            if self._cfg.get("crossfade", True) and self._cur_cov_pil:
                self._old_cov_pil = self._cur_cov_pil
                self._new_cov_pil = raw
                self._crossfade_t0 = time.time()
                self._crossfading = True
            else:
                self._cur_cov_pil = raw
                self._apply_cover_img(raw)

            # Extract accent colors
            sm = raw.convert("RGB").resize((6, 6), Image.LANCZOS)
            px = list(sm.getdata())
            scored = sorted(px,
                            key=lambda p: max(p) - min(p) + max(p) * 0.3,
                            reverse=True)

            def boost(c):
                f = min(1.6, 200 / max(max(c), 1))
                return "#{:02x}{:02x}{:02x}".format(
                    *(min(255, int(v * f)) for v in c))

            c1 = boost(scored[0])
            c2 = boost(scored[min(2, len(scored) - 1)])
            self._prog_colors = (c1, c2)
            self._accent_hex = c1
        except Exception:
            log.warning("Cover set failed", exc_info=True)

    # ── Voice ─────────────────────────────────────────────────────
    def _vlog(self, msg):
        log.info("[VOICE] %s", msg)

    def _start_voice(self):
        if not os.path.isdir(os.path.join(DIR, "vosk-model")):
            return
        os.chdir(DIR)
        threading.Thread(target=self._voice_loop, daemon=True).start()

    def _voice_loop(self):
        import queue
        if not HAS_NUMPY:
            return
        try:
            os.chdir(DIR)
            model = vosk.Model("vosk-model")
            rec = vosk.KaldiRecognizer(model, 16000)
            # Small queue — drop old audio, always process fresh data
            q = queue.Queue(maxsize=5)
            dev = sd.query_devices(kind="input")
            sr = int(dev["default_samplerate"])
            ratio = sr / 16000

            def cb(indata, frames, t, status):
                a = np.frombuffer(indata, dtype="int16").astype("float32")
                p = np.max(np.abs(a))
                if p < 40:
                    return
                if p > 10:
                    a = a * (16000 / p)
                ix = np.arange(0, len(a), ratio).astype(int)
                ix = ix[ix < len(a)]
                chunk = np.clip(a[ix], -32768, 32767).astype("int16").tobytes()
                try:
                    q.put_nowait(chunk)
                except queue.Full:
                    # Drop oldest, put fresh
                    try:
                        q.get_nowait()
                    except queue.Empty:
                        pass
                    try:
                        q.put_nowait(chunk)
                    except queue.Full:
                        pass

            def flush_queue():
                while not q.empty():
                    try:
                        q.get_nowait()
                    except queue.Empty:
                        break

            self._vlog(f"Mic: {dev['name']}")
            with sd.RawInputStream(samplerate=sr, blocksize=int(sr * 0.05),
                                   dtype="int16", channels=1, callback=cb):
                self._vlog("Listening...")
                cd = 0
                while self.running:
                    try:
                        data = q.get(timeout=0.15)
                    except Exception:
                        continue
                    if time.time() < cd:
                        # In cooldown — just drain, don't recognize
                        continue
                    if rec.AcceptWaveform(data):
                        t = json.loads(rec.Result()).get("text", "").lower()
                        if t:
                            cmd = self._vcmd(t)
                            if cmd:
                                self._vlog(f"FINAL: {t}")
                                cd = time.time() + 1.5
                                rec.Reset()
                                flush_queue()
                                _beep()
                                self.root.after(0, cmd)
                    else:
                        t = json.loads(
                            rec.PartialResult()).get("partial", "").lower()
                        if t:
                            cmd = self._vcmd(t)
                            if cmd:
                                self._vlog(f"FAST: {t}")
                                cd = time.time() + 1.5
                                rec.Reset()
                                flush_queue()
                                _beep()
                                self.root.after(0, cmd)
        except Exception as e:
            self._vlog(f"ERROR: {e}")

    def _vcmd(self, t):
        if "стоп" in t:
            return self._do_pause
        if "играй" in t:
            return self._do_play
        if "следующ" in t:
            return self._do_next
        if "назад" in t:
            return self._do_prev
        return None

    # ── Tray ──────────────────────────────────────────────────────
    def _mk_tray(self):
        ico = Image.new("RGB", (64, 64), "#111")
        d = ImageDraw.Draw(ico)
        d.rounded_rectangle([4, 4, 59, 59], radius=14, fill=ACCENT_DEFAULT)
        d.polygon([(24, 16), (24, 48), (48, 32)], fill="#111")
        rpc_items = []
        if HAS_RPC and self._discord:
            rpc_items = [pystray.MenuItem("Discord RPC",
                lambda *_: self._discord.toggle(),
                checked=lambda _: self._discord.enabled)]
        menu = pystray.Menu(
            pystray.MenuItem("Показать", lambda *_: self.root.after(0,
                lambda: (setattr(self, 'dismissed', False), self._show()))),
            pystray.MenuItem("Настройки",
                lambda *_: self.root.after(0, self._show_settings)),
            pystray.MenuItem("История",
                lambda *_: self.root.after(0, self._show_history)),
            pystray.MenuItem("Автозапуск",
                lambda *_: _autostart_set(not _autostart_on()),
                checked=lambda _: _autostart_on()),
            *rpc_items,
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Выход",
                lambda *_: self.root.after(0, self._quit)))
        self._tray = pystray.Icon(
            "YMMiniPlayer", ico, f"Dynamic Island v{VERSION}", menu)
        threading.Thread(target=self._tray.run, daemon=True).start()

    # ── Quit ──────────────────────────────────────────────────────
    def _quit(self):
        self.running = False
        self._hotkeys.unregister_all()
        if self._discord:
            self._discord.stop()
        _cfg_save({"x": self.x, "y": self.y_show})
        self._ov_cleanup()
        self._idle_pill_cleanup()
        if HAS_TRAY and hasattr(self, "_tray"):
            try:
                self._tray.stop()
            except Exception:
                pass
        log.info("Exiting")
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    MiniPlayer().run()
