"""Мини-плеер · Dynamic Island v2.4 — Motion Design"""

import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageChops, ImageDraw
import threading, asyncio, io, sys, time, ctypes, json, os, webbrowser, math
from urllib.parse import quote

try:
    from winsdk.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as MM)
    from winsdk.windows.storage.streams import DataReader, Buffer, InputStreamOptions
except ImportError:
    sys.exit("pip install winsdk")

try: import pystray; HAS_TRAY = True
except ImportError: HAS_TRAY = False

try: import vosk, sounddevice as sd; HAS_VOICE = True; vosk.SetLogLevel(-1)
except ImportError: HAS_VOICE = False

try: from pypresence import Presence, ActivityType; HAS_RPC = True
except ImportError: HAS_RPC = False

DISCORD_APP_ID = "1483924932261056522"

try: ctypes.windll.shcore.SetProcessDpiAwareness(1)
except: pass

ctk.set_appearance_mode("dark")
DIR = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
CFG = os.path.join(DIR, "player_config.json")
TRANS = "#010102"

# ── Cached media manager per thread ─────────────────────────────
_ctrl_mgr = None

def _ctrl(action):
    """Run media control in background thread."""
    def run():
        global _ctrl_mgr
        lp = asyncio.new_event_loop()
        try:
            if _ctrl_mgr is None:
                _ctrl_mgr = lp.run_until_complete(MM.request_async())
            se = _ctrl_mgr.get_current_session()
            if se: lp.run_until_complete(action(se))
        except:
            _ctrl_mgr = None
    threading.Thread(target=run, daemon=True).start()

# ── Icons (4x supersample) ──────────────────────────────────────
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

# ── Helpers ──────────────────────────────────────────────────────
def _hide_tb(hwnd):
    GWL = -20
    s = ctypes.windll.user32.GetWindowLongW(hwnd, GWL)
    ctypes.windll.user32.SetWindowLongW(hwnd, GWL, (s | 0x80) & ~0x40000)

def _vol(vk):
    for _ in range(2):
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk, 0, 2, 0)

def _beep():
    try:
        import winsound
        threading.Thread(target=lambda: (
            winsound.Beep(600, 50), winsound.Beep(900, 70)
        ), daemon=True).start()
    except: pass

def _pad(src, tw, th):
    out = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    out.paste(src, (0, 0))
    return out

def _cfg_load():
    try:
        with open(CFG) as f: return json.load(f)
    except: return {}

def _cfg_save(d):
    try:
        with open(CFG, "w") as f: json.dump(d, f)
    except: pass

def _autostart_on():
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
        winreg.QueryValueEx(k, "YMMiniPlayer"); winreg.CloseKey(k)
        return True
    except: return False

def _autostart_set(on):
    import winreg
    k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
    if on:
        pw = sys.executable.replace("python.exe", "pythonw.exe")
        winreg.SetValueEx(k, "YMMiniPlayer", 0, winreg.REG_SZ,
                          f'"{pw}" "{os.path.join(DIR, "player.pyw")}"')
    else:
        try: winreg.DeleteValue(k, "YMMiniPlayer")
        except: pass
    winreg.CloseKey(k)

def _ts(v):
    if v is None: return 0.0
    if hasattr(v, "total_seconds"): return v.total_seconds()
    try: return float(v) / 10_000_000
    except: return 0.0

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
    if not app_id: return None
    a = app_id.lower()
    for key in _APP_URLS:
        if key in a: return key
    if "chrome" in a or "firefox" in a or "edge" in a or "opera" in a or "browser" in a:
        return "yandex"
    return None

def _track_url(source, title, artist):
    fn = _APP_URLS.get(source)
    if fn and title: return fn(title, artist or "")
    if title: return f"https://music.yandex.ru/search?text={quote(f'{title} {artist or ''}')}"
    return None

# ── Cover art URL (Deezer → iTunes fallback) ─────────────────────
_art_cache = {}

def _fetch_art_url(title, artist):
    key = f"{title}|{artist}"
    if key in _art_cache: return _art_cache[key]
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
    except: pass
    try:
        url = f"https://itunes.apple.com/search?term={q}&media=music&limit=1"
        with urllib.request.urlopen(url, timeout=5) as r:
            data = json.loads(r.read())
        if data.get("resultCount", 0) > 0:
            art = data["results"][0].get("artworkUrl100", "")
            art = art.replace("100x100", "600x600")
            _art_cache[key] = art
            return art
    except: pass
    _art_cache[key] = None
    return None

# ── Win32 structures for UpdateLayeredWindow ─────────────────────
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

# ── Easing functions ─────────────────────────────────────────────
def _ease_out_cubic(t):
    return 1 - (1 - t) ** 3

def _ease_out_expo(t):
    return 1.0 if t >= 1.0 else 1 - pow(2, -10 * t)

def _ease_out_back(t):
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * pow(t - 1, 3) + c1 * pow(t - 1, 2)

def _ease_in_cubic(t):
    return t * t * t

def _ease_in_out_cubic(t):
    if t < 0.5:
        return 4 * t * t * t
    return 1 - pow(-2 * t + 2, 3) / 2

def _spring(t, damping=12, freq=4.5):
    """Damped spring — nice iOS-like overshoot."""
    return 1 - math.exp(-damping * t) * math.cos(freq * math.pi * t)


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
    def enabled(self): return self._enabled

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
            if changed: self._dirty = True

    def _connect(self):
        try:
            self._rpc = Presence(DISCORD_APP_ID)
            self._rpc.connect()
            self._connected = True
        except:
            self._rpc = None
            self._connected = False

    def _disconnect(self):
        try:
            if self._rpc:
                self._rpc.clear()
                self._rpc.close()
        except: pass
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
                track_url = _track_url(source, title, artist)
                btns = [{"label": "Слушать", "url": track_url}] if track_url else None
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
                    end_ts = start_ts + dur
                    kwargs["start"] = int(start_ts)
                    kwargs["end"] = int(end_ts)
                self._rpc.update(**kwargs)
            except Exception:
                self._connected = False
                self._rpc = None
            time.sleep(5)

    def stop(self):
        self._enabled = False
        self._disconnect()


# ── Плеер ────────────────────────────────────────────────────────
class MiniPlayer:
    W, H, CR, COV = 436, 96, 22, 62
    BG, BG_RGB = "#0d0d0d", (13, 13, 13)

    # Animation pill start shape
    _PILL_W, _PILL_H = 120, 38

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.0)
        self.root.configure(bg=self.BG)

        cfg = _cfg_load()
        scr = self.root.winfo_screenwidth()
        self.x = cfg.get("x", (scr - self.W) // 2)
        self.y_show = cfg.get("y", 16)
        self.y_hide = -self.H - 60
        self.pos_y = float(self.y_hide)
        self.vel_y = 0.0
        self.tgt_y = float(self.y_hide)
        self.cur_a, self.tgt_a = 0.0, 0.0
        self.root.geometry(f"{self.W}x{self.H}+{self.x}+{self.y_hide}")

        self.visible = self.dismissed = False
        self.running = True
        self.last_track = ""
        self._accent_hex = "#ffcc00"
        self._last_th = None
        self._pos = self._dur = 0.0
        self._playing = False
        self._pos_time = time.time()
        self._cov_ref = None
        self._track_url = None
        self._hwnd = None

        # Animation state
        self._animating = False
        self._anim_phase = None   # "expand" | "shrink"
        self._anim_start = 0.0
        self._anim_id = None

        self._ip  = _ico(_d_prev, "#a0a0a0")
        self._in  = _ico(_d_nxt,  "#a0a0a0")
        self._ipa = _ico(_d_pause, "#ddd", 22)
        self._ipl = _ico(_d_play,  "#ddd", 22)
        self._ix  = _ico(_d_x,     "#555", 14)

        self._discord = DiscordRPC() if HAS_RPC else None

        self._build_ui()

        self.root.update_idletasks()
        try:
            hw = ctypes.windll.user32.GetParent(self.root.winfo_id())
            # Main window keeps the hard silhouette; overlay softens the edge.
            rgn = ctypes.windll.gdi32.CreateRoundRectRgn(
                0, 0, self.W + 1, self.H + 1, self.CR * 2, self.CR * 2)
            ctypes.windll.user32.SetWindowRgn(hw, rgn, True)
            _hide_tb(hw)
            self._hwnd = hw
        except: pass

        self._setup_aa_overlay()

        self.root.bind("<MouseWheel>", lambda e: _vol(0xAF if e.delta > 0 else 0xAE))
        for w in [self.main, self.info, self.t_lbl, self.a_lbl]:
            w.bind("<Button-1>", self._ds)
            w.bind("<B1-Motion>", self._dm)
            w.bind("<ButtonRelease-1>", self._de)
        self.cov_lbl.bind("<Button-1>", self._open_track)
        self.cov_lbl.configure(cursor="hand2")
        self.prog.bind("<Button-1>", self._on_seek)

        self._tick()
        threading.Thread(target=self._wloop, daemon=True).start()
        if HAS_TRAY: self._mk_tray()
        if HAS_VOICE: self._start_voice()
        self.root.protocol("WM_DELETE_WINDOW", self._quit)

        # ── Startup animation: droplet appears on launch ──
        self.root.after(300, self._startup_anim)

    def _build_ui(self):
        self.main = ctk.CTkFrame(self.root, corner_radius=0,
                                 fg_color=self.BG, border_width=0)
        self.main.pack(fill="both", expand=True)
        self.main.grid_columnconfigure(1, weight=1)

        cf = ctk.CTkFrame(self.main, corner_radius=0, fg_color=self.BG,
                          width=self.COV+4, height=self.COV+4, border_width=0)
        cf.grid(row=0, column=0, rowspan=2, padx=(16, 10), pady=13)
        cf.grid_propagate(False)
        self.cov_lbl = ctk.CTkLabel(cf, text="", fg_color="transparent")
        self.cov_lbl.place(relx=.5, rely=.5, anchor="center")
        ph = Image.new("RGBA", (self.COV, self.COV), (0,0,0,0))
        ImageDraw.Draw(ph).rounded_rectangle([0,0,self.COV-1,self.COV-1],
                                              radius=14, fill="#161616")
        self._ph = ctk.CTkImage(ph, size=(self.COV, self.COV))
        self.cov_lbl.configure(image=self._ph)

        self.info = ctk.CTkFrame(self.main, fg_color="transparent", border_width=0)
        self.info.grid(row=0, column=1, sticky="sew", padx=(0, 4), pady=(16, 0))
        self.info.grid_columnconfigure(0, weight=1)
        self.t_lbl = ctk.CTkLabel(self.info, text="",
            font=ctk.CTkFont("Segoe UI", 14, "bold"),
            text_color="#eee", anchor="w", fg_color="transparent")
        self.t_lbl.grid(row=0, column=0, sticky="ew")
        self.a_lbl = ctk.CTkLabel(self.info, text="",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color="#777", anchor="w", fg_color="transparent")
        self.a_lbl.grid(row=1, column=0, sticky="ew")

        self._prog_h = 4
        self._prog_glow = 6
        ch = self._prog_h + self._prog_glow * 2
        self.prog = tk.Canvas(self.main, height=ch, bg=self.BG,
                              highlightthickness=0, bd=0)
        self.prog.grid(row=1, column=1, sticky="new", padx=(0, 4), pady=(2, 0))
        self._prog_val = 0.0
        self._prog_colors = ("#3b82f6", "#8b5cf6")
        self._prog_img_ref = None

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

    # ── Startup droplet animation ─────────────────────────────────
    def _startup_anim(self):
        """Single smooth animation: droplet rises → holds → fades out."""
        if self.visible or self._animating:
            return  # player already shown or animating — skip
        self._animating = True          # block _tick from fighting
        self._anim_phase = "startup"
        self._startup_t0 = time.time()

        # Position at final x, below y_show
        self.pos_y = float(self.y_show + 50)
        self.root.geometry(f"{self.W}x{self.H}+{self.x}+{int(self.pos_y)}")
        self.root.attributes("-alpha", 0.01)

        # Tiny circle region
        sz = 44
        self._set_rgn((self.W - sz) // 2, (self.H - sz) // 2, sz, sz, sz, sz)

        self._startup_frame()

    def _startup_frame(self):
        t = time.time() - self._startup_t0
        RISE = 0.6      # rise duration
        HOLD = 0.4      # hold at top
        FADE = 0.35     # fade out
        TOTAL = RISE + HOLD + FADE

        if t < RISE:
            # ── Phase 1: rise + fade in ──
            p = t / RISE
            ep = _ease_out_cubic(p)

            # Rise from +50 to y_show
            self.pos_y = self.y_show + 50 * (1 - ep)
            self.root.geometry(f"+{self.x}+{int(self.pos_y)}")

            # Fade in (fast)
            a = min(0.95, ep * 1.8)
            self.cur_a = a
            self.root.attributes("-alpha", max(0.01, a))

            # Grow 44 → 52
            sz = int(44 + 8 * ep)
            self._set_rgn((self.W - sz) // 2, (self.H - sz) // 2, sz, sz, sz, sz)

        elif t < RISE + HOLD:
            # ── Phase 2: hold with gentle breathing ──
            p = (t - RISE) / HOLD
            pulse = math.sin(p * math.pi * 2) * 2
            sz = int(52 + pulse)
            self._set_rgn((self.W - sz) // 2, (self.H - sz) // 2, sz, sz, sz, sz)

        else:
            # ── Phase 3: shrink + fade out ──
            p = min(1.0, (t - RISE - HOLD) / FADE)
            e = _ease_in_cubic(p)

            sz = max(4, int(52 * (1 - e)))
            self._set_rgn((self.W - sz) // 2, (self.H - sz) // 2, sz, sz, sz, sz)

            # Drop down a bit
            self.pos_y = self.y_show + 15 * e
            self.root.geometry(f"+{self.x}+{int(self.pos_y)}")

            # Fade out
            a = 0.95 * (1 - e)
            self.cur_a = a
            self.root.attributes("-alpha", max(0.01, a))

        if t < TOTAL:
            self.root.after(16, self._startup_frame)
        else:
            # Done → hidden, ready for watcher
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

    # ── Per-pixel alpha overlay for smooth corners ───────────────
    def _setup_aa_overlay(self):
        """Overlay window BEHIND main — provides AA rounded edges."""
        import numpy as np
        sc = 8
        self._ov_margin = 6
        self._ov_w = self.W + self._ov_margin * 2
        self._ov_h = self.H + self._ov_margin * 2

        # Render AA rounded rect (4× supersample → LANCZOS)
        big = Image.new("L", (self._ov_w * sc, self._ov_h * sc), 0)
        ImageDraw.Draw(big).rounded_rectangle(
            [self._ov_margin * sc, self._ov_margin * sc,
             (self._ov_margin + self.W) * sc - 1,
             (self._ov_margin + self.H) * sc - 1],
            radius=self.CR * sc, fill=255)
        aa_mask = big.resize((self._ov_w, self._ov_h), Image.LANCZOS)

        hard_mask = Image.new("L", (self._ov_w, self._ov_h), 0)
        ImageDraw.Draw(hard_mask).rounded_rectangle(
            [self._ov_margin, self._ov_margin,
             self._ov_margin + self.W - 1,
             self._ov_margin + self.H - 1], radius=self.CR, fill=255)

        edge_mask = ImageChops.subtract(aa_mask, hard_mask)
        small = Image.new("RGBA", (self._ov_w, self._ov_h), (*self.BG_RGB, 0))
        small.putalpha(edge_mask)

        # Premultiply alpha, convert RGBA → BGRA for Win32
        arr = np.array(small, dtype=np.float64)
        a = arr[:, :, 3:4] / 255.0
        arr[:, :, :3] *= a
        bgra = np.empty((self._ov_h, self._ov_w, 4), dtype=np.uint8)
        bgra[:, :, 0] = arr[:, :, 2].astype(np.uint8)
        bgra[:, :, 1] = arr[:, :, 1].astype(np.uint8)
        bgra[:, :, 2] = arr[:, :, 0].astype(np.uint8)
        bgra[:, :, 3] = arr[:, :, 3].astype(np.uint8)
        pixels = bytes(bgra)

        # Create GDI DC + bitmap (kept alive)
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

        # Overlay toplevel
        self._overlay = tk.Toplevel(self.root)
        self._overlay.overrideredirect(True)
        self._overlay.attributes("-topmost", True)
        self._overlay.geometry(
            f"{self._ov_w}x{self._ov_h}+{self.x - self._ov_margin}+{int(self.pos_y) - self._ov_margin}"
        )
        self._overlay.update_idletasks()

        self._ov_hwnd = ctypes.windll.user32.GetParent(
            self._overlay.winfo_id())

        # WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW
        GWL = -20
        es = u32.GetWindowLongW(self._ov_hwnd, GWL)
        es = (es | 0x80000 | 0x20 | 0x80) & ~0x40000
        u32.SetWindowLongW(self._ov_hwnd, GWL, es)

        # Initial render
        self._ov_update(self.x, int(self.pos_y), 0)

    def _ov_update(self, x, y, alpha):
        """Move overlay + set opacity via UpdateLayeredWindow."""
        if not getattr(self, '_ov_hdc', None):
            return
        blend = _BLENDFUNCTION(0, 0, alpha, 1)  # AC_SRC_ALPHA
        ctypes.windll.user32.UpdateLayeredWindow(
            self._ov_hwnd, None,
            ctypes.byref(_POINT(x - self._ov_margin, y - self._ov_margin)),
            ctypes.byref(_SIZE(self._ov_w, self._ov_h)),
            self._ov_hdc,
            ctypes.byref(_POINT(0, 0)),
            0, ctypes.byref(blend), 2)       # ULW_ALPHA
        # Keep overlay above the main window; WS_EX_TRANSPARENT keeps clicks on UI.
        if self._hwnd:
            SWP = 0x0001 | 0x0002 | 0x0010   # NOSIZE|NOMOVE|NOACTIVATE
            ctypes.windll.user32.SetWindowPos(
                self._ov_hwnd, -1, 0, 0, 0, 0, SWP)

    def _ov_cleanup(self):
        if getattr(self, '_ov_hdc', None):
            ctypes.windll.gdi32.SelectObject(self._ov_hdc, self._ov_old)
            ctypes.windll.gdi32.DeleteObject(self._ov_bm)
            ctypes.windll.gdi32.DeleteDC(self._ov_hdc)
            self._ov_hdc = None
        if hasattr(self, '_overlay'):
            try: self._overlay.destroy()
            except: pass

    # ── Region helper ─────────────────────────────────────────────
    def _set_rgn(self, x, y, w, h, rx, ry):
        if not self._hwnd: return
        try:
            rgn = ctypes.windll.gdi32.CreateRoundRectRgn(
                x, y, x + w + 1, y + h + 1, rx, ry)
            ctypes.windll.user32.SetWindowRgn(self._hwnd, rgn, True)
        except: pass

    def _set_full_rgn(self):
        """Restore the full hard region; the AA fringe is handled by overlay."""
        if self._hwnd:
            try:
                rgn = ctypes.windll.gdi32.CreateRoundRectRgn(
                    0, 0, self.W + 1, self.H + 1, self.CR * 2, self.CR * 2)
                ctypes.windll.user32.SetWindowRgn(self._hwnd, rgn, True)
            except: pass

    # ── Animation: expand (show) ──────────────────────────────────
    def _show(self):
        if self.dismissed: return
        if self.visible: return  # already shown or expanding — don't restart

        # Cancel shrink if in progress
        if self._anim_id:
            self.root.after_cancel(self._anim_id)
            self._anim_id = None

        self.visible = True
        self._animating = True
        self._anim_phase = "expand"
        self._anim_start = time.time()

        # Position window at final location + rise offset
        rise = 35
        self.pos_y = float(self.y_show + rise)
        self.tgt_y = float(self.y_show)
        self.vel_y = 0
        self.root.geometry(f"{self.W}x{self.H}+{self.x}+{int(self.pos_y)}")

        # Start with tiny pill region, fully visible
        pw, ph = self._PILL_W, self._PILL_H
        x_off = (self.W - pw) // 2
        self._set_rgn(x_off, 0, pw, ph, ph, ph)
        self.root.attributes("-alpha", 0.97)
        self.cur_a = 0.97
        self.tgt_a = 0.97

        self._anim_expand()

    def _anim_expand(self):
        DURATION = 0.55
        t = min(1.0, (time.time() - self._anim_start) / DURATION)

        # ── Easing curves (different timing per property) ──
        # Width: fast spring overshoot
        tw = min(1.0, t * 1.15)
        ew = _spring(tw, damping=10, freq=3.2) if tw < 1 else 1.0

        # Height: slightly delayed, smooth ease-out
        th = max(0.0, (t - 0.06) / 0.94)
        eh = _ease_out_cubic(min(1.0, th))

        # Y rise: smooth expo
        ey = _ease_out_expo(t)

        # Alpha: instant pop
        ea = min(1.0, t * 5)

        # ── Interpolate shape ──
        sw, sh = self._PILL_W, self._PILL_H
        cur_w = int(sw + (self.W - sw) * min(1.0, ew))
        cur_h = int(sh + (self.H - sh) * min(1.0, eh))

        # Corner radius: pill → rounded rect
        # Pill = fully round (corner = height), final = 44
        pill_r = min(cur_w, cur_h)
        tr = max(0.0, (t - 0.3) / 0.7)  # delayed transition
        er = _ease_out_cubic(min(1.0, tr))
        cur_rx = int(pill_r + (44 - pill_r) * er)
        cur_ry = int(pill_r + (44 - pill_r) * er)

        # Clamp
        cur_rx = max(44, min(cur_rx, cur_h))
        cur_ry = max(44, min(cur_ry, cur_h))

        # Position: centered horizontally, top-anchored
        x_off = (self.W - cur_w) // 2
        y_off = 0

        # Apply region
        self._set_rgn(x_off, y_off, cur_w, cur_h, cur_rx, cur_ry)

        # Y position: rise
        rise = 35
        cur_y = self.y_show + rise * (1 - ey)
        self.pos_y = cur_y
        self.root.geometry(f"+{self.x}+{int(cur_y)}")

        # Alpha
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
        if not self.visible: return
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
        DURATION = 0.40
        t = min(1.0, (time.time() - self._anim_start) / DURATION)

        # ── Easing (accelerating in) ──
        ew = _ease_in_cubic(t)          # width
        eh = _ease_in_cubic(t)          # height (slightly leading)
        ey = _ease_in_cubic(t)          # y drop
        ea = _ease_in_cubic(t)          # alpha fade

        # ── Interpolate ──
        sw, sh = self._PILL_W, self._PILL_H
        cur_w = int(self.W + (sw - self.W) * ew)
        cur_h = int(self.H + (sh - self.H) * eh)

        # Corner: rounded rect → pill
        pill_r = min(cur_w, cur_h)
        tr = _ease_in_cubic(t)
        cur_rx = int(44 + (pill_r - 44) * tr)
        cur_ry = cur_rx
        cur_rx = max(44, min(cur_rx, cur_h))
        cur_ry = cur_rx

        x_off = (self.W - cur_w) // 2
        y_off = 0

        self._set_rgn(x_off, y_off, cur_w, cur_h, cur_rx, cur_ry)

        # Y: drop down slightly
        drop = 25
        cur_y = self._shrink_y0 + drop * ey
        self.pos_y = cur_y
        self.root.geometry(f"+{self.x}+{int(cur_y)}")

        # Alpha: fade
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
        self.pos_y = float(self.y_hide)
        self.tgt_y = float(self.y_hide)
        self.vel_y = 0
        self.cur_a = 0.0
        self.tgt_a = 0.0
        self.root.attributes("-alpha", 0.0)
        self.root.geometry(f"+{self.x}+{self.y_hide}")
        self._set_full_rgn()

    # ── Gradient progress bar ─────────────────────────────────────
    def _build_grad_strip(self, total_w):
        from PIL import ImageFilter
        bar_h = self._prog_h
        glow = self._prog_glow
        h = bar_h + glow * 2
        cy = h // 2
        y0, y1 = cy - bar_h // 2, cy + bar_h // 2

        c1 = tuple(int(self._prog_colors[0][i:i+2], 16) for i in (1, 3, 5))
        c2 = tuple(int(self._prog_colors[1][i:i+2], 16) for i in (1, 3, 5))

        import numpy as np
        t = np.linspace(0, 1, total_w)
        r = (c1[0] + (c2[0] - c1[0]) * t).astype(np.uint8)
        g = (c1[1] + (c2[1] - c1[1]) * t).astype(np.uint8)
        b = (c1[2] + (c2[2] - c1[2]) * t).astype(np.uint8)

        strip = Image.new("RGBA", (total_w, bar_h), (0, 0, 0, 0))
        for x in range(total_w):
            for y in range(bar_h):
                strip.putpixel((x, y), (int(r[x]), int(g[x]), int(b[x]), 255))

        glow_strip = Image.new("RGBA", (total_w, h), (0, 0, 0, 0))
        for x in range(total_w):
            for dy in range(-glow, glow + 1):
                a = int(70 * max(0, 1 - abs(dy) / glow))
                py = cy + dy
                if 0 <= py < h:
                    glow_strip.putpixel((x, py), (int(r[x]), int(g[x]), int(b[x]), a))
        glow_strip = glow_strip.filter(ImageFilter.GaussianBlur(radius=4))

        self._grad_strip = strip
        self._glow_strip = glow_strip
        self._grad_w = total_w
        self._grad_colors_key = self._prog_colors

    def _draw_prog(self, frac):
        c = self.prog
        c.update_idletasks()
        w, h_c = c.winfo_width(), c.winfo_height()
        if w < 4: return

        pw = max(0, min(int(w * frac), w))
        pw_q = max(0, pw // 2 * 2)
        if hasattr(self, '_last_pw') and self._last_pw == pw_q and \
           hasattr(self, '_grad_colors_key') and self._grad_colors_key == self._prog_colors:
            return
        self._last_pw = pw_q

        bar_h = self._prog_h
        glow = self._prog_glow
        h = bar_h + glow * 2
        cy = h // 2
        y0 = cy - bar_h // 2

        if not hasattr(self, '_grad_strip') or self._grad_w != w or \
           self._grad_colors_key != self._prog_colors:
            self._build_grad_strip(w)

        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        draw.rounded_rectangle([0, y0, w - 1, y0 + bar_h - 1],
                               radius=bar_h // 2, fill=(255, 255, 255, 18))

        if pw_q > 2:
            bar = self._grad_strip.crop((0, 0, pw_q, bar_h))
            mask = Image.new("L", (pw_q, bar_h), 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, pw_q - 1, bar_h - 1],
                                                    radius=bar_h // 2, fill=255)
            bar.putalpha(mask)
            glow_crop = self._glow_strip.crop((0, 0, pw_q, h))
            img = Image.alpha_composite(img, _pad(glow_crop, w, h))
            img.paste(bar, (0, y0), bar)

        from PIL import ImageTk
        self._prog_tk = ImageTk.PhotoImage(img)
        c.delete("all")
        c.create_image(0, 0, anchor="nw", image=self._prog_tk)

    # ── Tick ──────────────────────────────────────────────────────
    def _tick(self):
        if not self._animating:
            # Normal spring physics (only when NOT animating)
            dy = self.pos_y - self.tgt_y
            self.vel_y += (-120 * dy - 14 * self.vel_y) * 0.016
            self.pos_y += self.vel_y * 0.016
            self.root.geometry(f"+{self.x}+{int(self.pos_y)}")
            self.cur_a += (self.tgt_a - self.cur_a) * 0.14
            self.root.attributes("-alpha", max(0, min(1, self.cur_a)))

        # Sync AA edge overlay; hide it while shape animations are running.
        a_byte = max(0, min(255, int(self.cur_a * 255)))
        if self._animating or not self.visible:
            a_byte = 0
        self._ov_update(self.x, int(self.pos_y), a_byte)

        if self._dur > 0:
            cur = self._pos + (time.time() - self._pos_time if self._playing else 0)
            self._prog_val = max(0, min(1, cur / self._dur))
            self._draw_prog(self._prog_val)
        self.root.after(16, self._tick)

    # ── Drag ──────────────────────────────────────────────────────
    def _ds(self, e): self._dx, self._dy = e.x, e.y
    def _dm(self, e):
        self.x = self.root.winfo_x() + e.x - self._dx
        ny = self.root.winfo_y() + e.y - self._dy
        self.pos_y = self.tgt_y = self.y_show = float(ny)
        self.vel_y = 0; self.root.geometry(f"+{self.x}+{ny}")
    def _de(self, _): _cfg_save({"x": self.x, "y": self.y_show})

    def _on_seek(self, e):
        if self._dur <= 0: return
        w = self.prog.winfo_width()
        if w <= 0: return
        frac = max(0, min(1, e.x / w))
        self._pos = frac * self._dur; self._pos_time = time.time()
        self._prog_val = frac
        tgt = frac * self._dur
        async def do(se):
            from datetime import timedelta
            try: await se.try_change_playback_position_async(timedelta(seconds=tgt))
            except:
                try: await se.try_change_playback_position_async(int(tgt * 1e7))
                except: pass
        _ctrl(do)

    def _open_track(self, _=None):
        if self._track_url:
            webbrowser.open(self._track_url)

    # ── Controls ──────────────────────────────────────────────────
    def _do_toggle(self): _ctrl(lambda se: se.try_toggle_play_pause_async())
    def _do_next(self):   _ctrl(lambda se: se.try_skip_next_async())
    def _do_prev(self):   _ctrl(lambda se: se.try_skip_previous_async())
    def _dismiss(self):   self.dismissed = True; self._hide()

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
                if not se: time.sleep(0.5); continue
                pr = lp.run_until_complete(se.try_get_media_properties_async())
                pb = se.get_playback_info()
                tl = se.get_timeline_properties()
                pl = pb.playback_status == 4
                ps, dr = _ts(tl.position), _ts(tl.end_time)
                try: ts = tl.last_updated_time.timestamp()
                except: ts = time.time()
                try: src = _detect_source(se.source_app_user_model_id)
                except: src = None
                tk_ = f"{pr.title}|{pr.artist}"
                th = None
                if tk_ != prev and tk_ != "|" and pr.thumbnail:
                    prev = tk_
                    th = lp.run_until_complete(self._rthumb(pr.thumbnail))
                self.root.after(0, self._upd,
                    pr.title or "", pr.artist or "", pl, ps, dr, ts, th, src)
            except:
                mgr = None
            time.sleep(0.15)

    async def _rthumb(self, ref):
        try:
            s = await ref.open_read_async()
            if not s.size: return None
            b = Buffer(s.size)
            await s.read_async(b, s.size, InputStreamOptions.READ_AHEAD)
            r = DataReader.from_buffer(b)
            d = bytearray(b.length); r.read_bytes(d)
            return bytes(d)
        except: return None

    def _upd(self, title, artist, playing, pos, dur, ts, thumb, source=None):
        tk_ = f"{title}|{artist}"
        if tk_ != self.last_track and tk_ != "|":
            self.last_track = tk_; self.dismissed = False
        if playing and not self.dismissed: self._show()
        if not playing and not self.visible: return

        self.t_lbl.configure(text=title[:34] + ("…" if len(title) > 34 else ""))
        self.a_lbl.configure(text=artist)
        self._pos, self._dur, self._playing, self._pos_time = pos, dur, playing, ts
        self._track_url = _track_url(source, title, artist)
        self.b_play.configure(image=self._ipa if playing else self._ipl)
        if self._discord:
            self._discord.update(title, artist, playing, pos, dur, ts, source)
        if not playing and self.visible: self._hide()

        if thumb:
            h = hash(thumb[:256])
            if h != self._last_th:
                self._last_th = h; self._setcov(thumb)

    def _setcov(self, data):
        try:
            hi = self.COV * 2
            img = Image.open(io.BytesIO(data)).convert("RGB").resize(
                (hi, hi), Image.LANCZOS)
            bg = Image.new("RGB", (hi, hi), self.BG_RGB)
            mask = Image.new("L", (hi, hi), 0)
            ImageDraw.Draw(mask).rounded_rectangle([0,0,hi-1,hi-1], radius=28, fill=255)
            bg.paste(img, (0, 0), mask)
            ci = ctk.CTkImage(bg, size=(self.COV, self.COV))
            self.cov_lbl.configure(image=ci); self._cov_ref = ci
            sm = img.resize((6, 6), Image.LANCZOS)
            px = list(sm.getdata())
            scored = sorted(px, key=lambda p: max(p)-min(p)+max(p)*0.3, reverse=True)
            def boost(c):
                f = min(1.6, 200 / max(max(c), 1))
                return "#{:02x}{:02x}{:02x}".format(*(min(255, int(v*f)) for v in c))
            c1 = boost(scored[0])
            c2 = boost(scored[min(2, len(scored)-1)])
            self._prog_colors = (c1, c2)
            self._accent_hex = c1
        except: pass

    # ── Voice ─────────────────────────────────────────────────────
    def _vlog(self, msg):
        try:
            with open(os.path.join(DIR, "voice_log.txt"), "a",
                      encoding="utf-8") as f:
                f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
        except: pass

    def _start_voice(self):
        if not os.path.isdir(os.path.join(DIR, "vosk-model")): return
        os.chdir(DIR)
        threading.Thread(target=self._voice_loop, daemon=True).start()

    def _voice_loop(self):
        import queue
        try: import numpy as np
        except: return
        try:
            os.chdir(DIR)
            model = vosk.Model("vosk-model")
            rec = vosk.KaldiRecognizer(model, 16000)
            q = queue.Queue()
            dev = sd.query_devices(kind="input")
            sr = int(dev["default_samplerate"])
            ratio = sr / 16000

            def cb(indata, frames, t, status):
                a = np.frombuffer(indata, dtype="int16").astype("float32")
                p = np.max(np.abs(a))
                if p > 10: a = a * (16000 / p)
                ix = np.arange(0, len(a), ratio).astype(int)
                ix = ix[ix < len(a)]
                q.put(np.clip(a[ix], -32768, 32767).astype("int16").tobytes())

            self._vlog(f"Mic: {dev['name']}")
            with sd.RawInputStream(samplerate=sr, blocksize=int(sr*0.25),
                                   dtype="int16", channels=1, callback=cb):
                self._vlog("Listening...")
                cd = 0
                while self.running:
                    try: data = q.get(timeout=0.3)
                    except: continue
                    if time.time() < cd: continue
                    if rec.AcceptWaveform(data):
                        t = json.loads(rec.Result()).get("text", "").lower()
                        if t:
                            self._vlog(f"HEARD: {t}")
                            cmd = self._vcmd(t)
                            if cmd:
                                cd = time.time() + 2; _beep()
                                self.root.after(0, cmd)
                    else:
                        t = json.loads(rec.PartialResult()).get("partial", "").lower()
                        if t:
                            cmd = self._vcmd(t)
                            if cmd:
                                self._vlog(f"FAST: {t}")
                                cd = time.time() + 2; rec.Reset(); _beep()
                                self.root.after(0, cmd)
        except Exception as e:
            self._vlog(f"VOICE ERROR: {e}")

    def _vcmd(self, t):
        for w in ("стоп","пауза","останови","стой"):
            if w in t: return self._do_toggle
        for w in ("играй","продолжи","плей","включи","давай"):
            if w in t: return self._do_toggle
        for w in ("следующ","дальше","скип"):
            if w in t: return self._do_next
        for w in ("предыдущ","назад","верни"):
            if w in t: return self._do_prev
        for w in ("громче","прибавь"):
            if w in t: return lambda: _vol(0xAF)
        for w in ("тише","убавь"):
            if w in t: return lambda: _vol(0xAE)
        return None

    # ── Tray ──────────────────────────────────────────────────────
    def _mk_tray(self):
        ico = Image.new("RGB", (64, 64), "#111")
        d = ImageDraw.Draw(ico)
        d.rounded_rectangle([4,4,59,59], radius=14, fill="#ffcc00")
        d.polygon([(24,16),(24,48),(48,32)], fill="#111")
        rpc_items = []
        if HAS_RPC and self._discord:
            rpc_items = [
                pystray.MenuItem("Discord RPC",
                    lambda *_: self._discord.toggle(),
                    checked=lambda _: self._discord.enabled),
            ]
        menu = pystray.Menu(
            pystray.MenuItem("Показать", lambda *_: self.root.after(0,
                lambda: (setattr(self, 'dismissed', False), self._show()))),
            pystray.MenuItem("Автозапуск", lambda *_: _autostart_set(not _autostart_on()),
                             checked=lambda _: _autostart_on()),
            *rpc_items,
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Выход", lambda *_: self.root.after(0, self._quit)))
        self._tray = pystray.Icon("YMMiniPlayer", ico, "Мини-плеер", menu)
        threading.Thread(target=self._tray.run, daemon=True).start()

    def _quit(self):
        self.running = False
        if self._discord: self._discord.stop()
        _cfg_save({"x": self.x, "y": self.y_show})
        self._ov_cleanup()
        if HAS_TRAY and hasattr(self, "_tray"):
            try: self._tray.stop()
            except: pass
        self.root.destroy()

    def run(self): self.root.mainloop()

if __name__ == "__main__":
    MiniPlayer().run()
