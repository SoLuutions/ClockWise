"""
ClockWise Desktop Application
==============================
Strictly designed for Windows according to the ClockWise Design Bible (Kairos Identity System).
Features:
- Full ClockWise Day & Night Design System (#F3EEE7 / #103C3A / #E75B3C)
- C-Wing Logo & custom UI panels (1px hairlines, 4px max corners, 8px spacing scale)
- Supabase Server Authentication & 30-Day Subscription Payment Verifier
- Restricts access if account is missing or last payment > 30 days
- Full background automation engine (mouse curves, browser interaction, window slots)
- Window switching via simulated Alt+Tab (default) or title-matched window slots
- Activity Level duty cycle (e.g. 80% active / 20% natural idle pauses)
- Global Hotkeys (F9 Start, F10 Stop, F11 Quit, Ctrl+Alt+1..5 Window Switcher)
- System Tray with C-Wing icon and 'ClockWise' tooltip
"""

import sys
import os

# Ensure the script directory is always on sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import threading
from time import sleep, time
from random import randint, random, choice, uniform
from datetime import datetime
import json
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageDraw, ImageTk

# ── Supabase Authentication Service (with standalone fallback) ────────────────
try:
    import auth_service
except ImportError:
    # If auth_service.py was not copied or found, provide full embedded fallback
    import hashlib
    import urllib.request
    import urllib.parse
    from datetime import timezone

    class EmbeddedAuthService:
        CURRENT_VERSION = "1.0.2"
        GITHUB_REPO = "SoLuutions/ClockWise"

        @classmethod
        def get_app_data_dir(cls):
            if sys.platform == 'win32':
                base = os.environ.get('APPDATA') or os.path.expanduser('~')
            else:
                base = os.path.expanduser('~/.config')
            app_dir = os.path.join(base, 'ClockWise')
            os.makedirs(app_dir, exist_ok=True)
            return app_dir

        @classmethod
        def get_config_file(cls):
            return os.path.join(cls.get_app_data_dir(), 'supabase_config.json')

        @classmethod
        def get_session_file(cls):
            return os.path.join(cls.get_app_data_dir(), 'session.json')

        @classmethod
        def get_settings_file(cls):
            return os.path.join(cls.get_app_data_dir(), 'settings.json')

        DEFAULT_CONFIG = {
            "supabase_url": "https://xlcbhhrmibkaeyalsflk.supabase.co",
            "supabase_anon_key": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhsY2JoaHJtaWJrYWV5YWxzZmxrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTMwNjk4ODksImV4cCI6MjEwODY0NTg4OX0.FQzWER765hCO61idza84f8bRTJlG_u59UNTXw9v7USU",
            "subscription_max_days": 30
        }

        @classmethod
        def load_settings(cls):
            s_file = cls.get_settings_file()
            if os.path.exists(s_file):
                try:
                    with open(s_file, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except Exception:
                    pass
            return {}

        @classmethod
        def save_settings(cls, data):
            s_file = cls.get_settings_file()
            try:
                cur = cls.load_settings()
                cur.update(data)
                with open(s_file, 'w', encoding='utf-8') as f:
                    json.dump(cur, f, indent=4)
            except Exception:
                pass

        @classmethod
        def load_config(cls):
            local_cfg = os.path.join(SCRIPT_DIR, 'supabase_config.json')
            for path in (local_cfg, cls.get_config_file()):
                if os.path.exists(path):
                    try:
                        with open(path, 'r', encoding='utf-8') as f:
                            cfg = json.load(f)
                            if cfg.get('supabase_url') and 'YOUR_PROJECT_REF' not in cfg.get('supabase_url'):
                                return cfg
                    except Exception:
                        pass
            return cls.DEFAULT_CONFIG.copy()

        @classmethod
        def save_config(cls, url, key, max_days=30):
            cfg = {
                "supabase_url": url.strip().rstrip('/'),
                "supabase_anon_key": key.strip(),
                "subscription_max_days": max_days
            }
            try:
                with open(cls.get_config_file(), 'w', encoding='utf-8') as f:
                    json.dump(cfg, f, indent=4)
            except Exception:
                pass
            return cfg

        @classmethod
        def _hash_password(cls, raw_pass):
            return hashlib.sha256(raw_pass.encode('utf-8')).hexdigest()

        @classmethod
        def parse_semver(cls, ver_str):
            clean = str(ver_str).strip().lstrip('v').split('-')[0]
            parts = []
            for p in clean.split('.'):
                try: parts.append(int(p))
                except ValueError: parts.append(0)
            while len(parts) < 3:
                parts.append(0)
            return tuple(parts[:3])

        @classmethod
        def check_for_updates(cls, timeout=4):
            url = f"https://api.github.com/repos/{cls.GITHUB_REPO}/releases/latest"
            req = urllib.request.Request(url, headers={
                'User-Agent': 'ClockWise-Updater/1.0',
                'Accept': 'application/vnd.github.v3+json'
            })
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    tag = data.get('tag_name', '')
                    latest_v = cls.parse_semver(tag)
                    curr_v = cls.parse_semver(cls.CURRENT_VERSION)
                    if latest_v > curr_v:
                        return tag, True, data
                    return tag, False, data
            except Exception:
                return None, False, None

        @classmethod
        def check_account_subscription(cls, email, password_input):
            cfg = cls.load_config()
            base_url = cfg.get("supabase_url", "").strip().rstrip('/')
            anon_key = cfg.get("supabase_anon_key", "").strip()
            max_days = cfg.get("subscription_max_days", 30)

            if not base_url or 'YOUR_PROJECT_REF' in base_url or not anon_key or 'YOUR_SUPABASE_ANON_KEY' in anon_key:
                return False, "Database connection not configured yet. Please enter your Supabase URL & Anon Key in Database Settings.", None

            clean_email = email.strip().lower()
            if not clean_email:
                return False, "Email or username cannot be empty.", None

            headers = {
                'apikey': anon_key,
                'Authorization': f'Bearer {anon_key}',
                'Content-Type': 'application/json',
                'User-Agent': 'ClockWise-Windows/1.0'
            }

            # Method A: Secure Server-Side RPC Function
            rpc_url = f"{base_url}/rest/v1/rpc/verify_subscription"
            rpc_payload = json.dumps({"p_email": clean_email, "p_password": password_input}).encode('utf-8')
            req_rpc = urllib.request.Request(rpc_url, data=rpc_payload, headers=headers, method='POST')

            use_fallback = False
            try:
                with urllib.request.urlopen(req_rpc, timeout=8) as resp:
                    res = json.loads(resp.read().decode('utf-8'))
                    if isinstance(res, dict):
                        if res.get('success'):
                            days_left = res.get('days_remaining', 30)
                            session_data = {
                                "email": clean_email,
                                "password": password_input,
                                "full_name": res.get('full_name', ''),
                                "last_payment_date": str(res.get('last_payment_date', '')),
                                "days_remaining": days_left,
                                "version": cls.CURRENT_VERSION,
                                "verified_at": datetime.now(timezone.utc).isoformat()
                            }
                            cls.save_session(session_data)
                            return True, res.get('message', f'Subscription Active: {days_left}d remaining'), session_data
                        else:
                            return False, res.get('message', 'Subscription expired or invalid.'), None
            except urllib.error.HTTPError as e:
                if e.code in (404, 400):
                    use_fallback = True
                else:
                    err_body = e.read().decode('utf-8', errors='ignore')
                    return False, f"Server Error ({e.code}): {err_body or e.reason}", None
            except Exception:
                use_fallback = True

            # Method B: Fallback Direct REST Table Query
            if use_fallback:
                query_url = f"{base_url}/rest/v1/clockwise_users?email=eq.{urllib.parse.quote(clean_email)}&select=*"
                req_table = urllib.request.Request(query_url, headers=headers, method='GET')
                try:
                    with urllib.request.urlopen(req_table, timeout=8) as resp:
                        data = json.loads(resp.read().decode('utf-8'))
                except Exception as e:
                    return False, f"Database connection error: {str(e)}", None

                if not data:
                    return False, "Account not found. Please verify your email.", None

                user = data[0]
                db_pass = str(user.get('password', ''))
                input_hashed = cls._hash_password(password_input)
                if db_pass != password_input and db_pass != input_hashed:
                    return False, "Incorrect password. Please try again.", None

                if not user.get('is_active', True):
                    return False, "Account has been deactivated. Please contact support.", None

                raw_date = user.get('last_payment_date')
                if not raw_date:
                    return False, "No payment record found for this account. Access restricted.", None

                try:
                    date_str = str(raw_date).split('T')[0]
                    pay_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                except Exception:
                    return False, f"Invalid date format: {raw_date}", None

                today = datetime.now(timezone.utc).date()
                days_elapsed = (today - pay_date).days

                if days_elapsed > max_days:
                    return False, (
                        f"Subscription Expired: Last payment was on {pay_date.strftime('%b %d, %Y')} "
                        f"({days_elapsed} days ago - limit is 30 days). Access restricted."
                    ), user

                days_remaining = max(0, max_days - max(0, days_elapsed))
                session_data = {
                    "email": clean_email,
                    "password": password_input,
                    "full_name": user.get('full_name', ''),
                    "last_payment_date": str(pay_date),
                    "days_remaining": days_remaining,
                    "version": cls.CURRENT_VERSION,
                    "verified_at": datetime.now(timezone.utc).isoformat()
                }
                cls.save_session(session_data)
                return True, f"Subscription Active: {days_remaining}d remaining", session_data

            return False, "Unknown verification error.", None

        @classmethod
        def save_session(cls, session_data):
            try:
                with open(cls.get_session_file(), 'w', encoding='utf-8') as f:
                    json.dump(session_data, f, indent=4)
            except Exception:
                pass

        @classmethod
        def load_cached_session(cls):
            sess_file = cls.get_session_file()
            if os.path.exists(sess_file):
                try:
                    with open(sess_file, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except Exception:
                    pass
            return None

        @classmethod
        def clear_session(cls):
            sess_file = cls.get_session_file()
            if os.path.exists(sess_file):
                try:
                    os.remove(sess_file)
                except Exception:
                    pass

        @classmethod
        def verify_cached_session(cls, enforce_update_check=True):
            cached = cls.load_cached_session()
            if not cached:
                return False, "No saved session found.", None

            if enforce_update_check:
                tag, has_update, _ = cls.check_for_updates(timeout=3)
                if has_update and tag:
                    cls.clear_session()
                    return False, f"UPDATE_DETECTED:{tag}", {"update_tag": tag}

            email = cached.get('email', '')
            password = cached.get('password', '')
            if not email or not password:
                return False, "Session incomplete.", None

            ok, msg, udata = cls.check_account_subscription(email, password)
            if ok:
                return True, msg, udata

            # Offline grace check
            if "expired" not in msg.lower() and "incorrect password" not in msg.lower() and "not found" not in msg.lower():
                raw_date = cached.get('last_payment_date')
                if raw_date:
                    try:
                        date_str = str(raw_date).split('T')[0]
                        pay_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                        days_elapsed = (datetime.now(timezone.utc).date() - pay_date).days
                        if days_elapsed <= 30:
                            cached['days_remaining'] = max(0, 30 - days_elapsed)
                            return True, f"Subscription active: {cached['days_remaining']}d remaining", cached
                    except Exception:
                        pass
            return False, msg, None

    auth_service = EmbeddedAuthService

# ── Windows Platform Setup ────────────────────────────────────────────────────
IS_WINDOWS = sys.platform == 'win32'

if IS_WINDOWS:
    import ctypes
    import ctypes.wintypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    # Configure 64-bit safe signatures for user32 and kernel32
    try:
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        user32.EnumWindows.argtypes = [WNDENUMPROC, ctypes.wintypes.LPARAM]
        user32.EnumWindows.restype = ctypes.wintypes.BOOL
        user32.IsWindowVisible.argtypes = [ctypes.wintypes.HWND]
        user32.IsWindowVisible.restype = ctypes.wintypes.BOOL
        user32.GetWindowTextLengthW.argtypes = [ctypes.wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.IsWindow.argtypes = [ctypes.wintypes.HWND]
        user32.IsWindow.restype = ctypes.wintypes.BOOL
        user32.IsIconic.argtypes = [ctypes.wintypes.HWND]
        user32.IsIconic.restype = ctypes.wintypes.BOOL
        user32.ShowWindow.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = ctypes.wintypes.BOOL
        user32.SetForegroundWindow.argtypes = [ctypes.wintypes.HWND]
        user32.SetForegroundWindow.restype = ctypes.wintypes.BOOL
        user32.BringWindowToTop.argtypes = [ctypes.wintypes.HWND]
        user32.BringWindowToTop.restype = ctypes.wintypes.BOOL
        user32.GetForegroundWindow.restype = ctypes.wintypes.HWND
        user32.GetForegroundWindow.argtypes = []
        user32.GetWindowThreadProcessId.argtypes = [ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = ctypes.wintypes.DWORD
        user32.AttachThreadInput.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.DWORD, ctypes.wintypes.BOOL]
        user32.AttachThreadInput.restype = ctypes.wintypes.BOOL
        user32.SwitchToThisWindow.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.BOOL]
        user32.SwitchToThisWindow.restype = None
        user32.keybd_event.argtypes = [ctypes.c_byte, ctypes.c_byte, ctypes.wintypes.DWORD, ctypes.c_void_p]
        user32.keybd_event.restype = None
    except Exception:
        pass

    import pyautogui
    import keyboard
    import pystray
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.0
else:
    # Stubs for non-Windows environments for linting / safety
    user32 = None
    kernel32 = None
    pyautogui = None
    keyboard = None
    pystray = None

# ── ClockWise Design Bible: THEME DICT ────────────────────────────────────────
THEME = {
    'day': {
        'name': 'Day',
        'window': '#F3EEE7',       # Canvas 70%
        'panel': '#FAF7F2',        # Panel
        'hairline': '#D9D4CB',     # 1px border
        'trough': '#E5DFD6',       # Slider track
        'text': '#103C3A',         # Primary text (Deep Forest Teal)
        'secondary_text': '#3F605D',# Secondary text
        'accent': '#E75B3C',       # Warm Coral 10% (Live status marker)
        'button_bg': '#103C3A',    # Inverse of window: deep teal
        'button_fg': '#F3EEE7',    # Inverse text: warm off-white
        'button_hover': '#164846',
        'input_bg': '#FAF7F2',
        'input_fg': '#103C3A',
        'input_border': '#D9D4CB',
        'badge_active_bg': '#FAF7F2',
        'badge_active_fg': '#103C3A',
        'badge_inactive_bg': '#FAF7F2',
        'badge_inactive_fg': '#3F605D',
    },
    'night': {
        'name': 'Night',
        'window': '#103C3A',       # Deep Forest Teal Canvas
        'panel': '#164846',        # Panel
        'hairline': '#2A5C59',     # 1px border
        'trough': '#0F3331',       # Slider track
        'text': '#F3EEE7',         # Warm Off-White text
        'secondary_text': '#A9BDB9',# Secondary text
        'accent': '#E75B3C',       # Warm Coral
        'button_bg': '#F3EEE7',    # Inverse of window: warm off-white
        'button_fg': '#103C3A',    # Inverse text: deep teal
        'button_hover': '#FAF7F2',
        'input_bg': '#164846',
        'input_fg': '#F3EEE7',
        'input_border': '#2A5C59',
        'badge_active_bg': '#164846',
        'badge_active_fg': '#F3EEE7',
        'badge_inactive_bg': '#164846',
        'badge_inactive_fg': '#A9BDB9',
    }
}

CURRENT_THEME = 'night'  # Default to Night (deep teal) or Day

# ── Core Automation Config ───────────────────────────────────────────────────
CFG = {
    # Activity duty cycle (fraction of time active; rest is natural idle pauses)
    'activity_level': 0.8,
    # Timing
    'tick_min': 1.0, 'tick_max': 4.0,
    # Mouse
    'mouse_speed': 1.0, 'curve_intensity': 150,
    'micro_jitter': True,
    # Actions
    'rightclick_chance': 0.3,
    'scroll_chance': 0.4, 'scroll_max_bursts': 8, 'scroll_max_clicks': 10,
    'arrow_chance': 0.33, 'arrow_max_keys': 4,
    # Browser
    'browser_chance': 0.15,
    'browser_search_limit': 3,
    'browser_search_chance': 0.5,
    'search_interval_min': 15.0,  # minutes
    'chrome_tab_chance': 0.05,
    'auto_switch_chance': 0.08,
    # Window switching: 'alt_tab' (default) or 'slots' (title-matched windows)
    'switch_mode': 'alt_tab',
    'alt_tab_max_depth': 2,       # max Tab presses while holding Alt
    # Break reminder
    'break_enabled': False,
    'break_interval': 45.0,       # minutes
    'break_duration': 5.0,        # minutes
    # Stealth
    'stealth_mode': True,
    'randomize_patterns': True,
}

# Factory defaults snapshot (taken before persisted settings are applied)
DEFAULT_CFG = dict(CFG)

# ── State ─────────────────────────────────────────────────────────────────────
running = False
exit_program = False
tray_icon = None
main_window = None
login_window = None
current_user = None               # Set upon Supabase auth & valid payment
_last_break = time()
_last_search_time = 0.0
searches_done = 0
_used_queries = set()
_idle_debt = 0.0                  # Accumulated idle time owed to honour activity_level

# Window switcher
NUM_SLOTS = 5
window_slots = [{'title_fragment': '', 'hwnd': None} for _ in range(NUM_SLOTS)]
_win_hotkeys = []

def init_persisted_settings():
    global CURRENT_THEME
    try:
        settings = auth_service.load_settings()
        if 'theme' in settings:
            CURRENT_THEME = settings['theme']
        if 'window_slots' in settings and isinstance(settings['window_slots'], list):
            for i, frag in enumerate(settings['window_slots'][:NUM_SLOTS]):
                if isinstance(frag, str):
                    window_slots[i]['title_fragment'] = frag
        if 'cfg' in settings and isinstance(settings['cfg'], dict):
            for k, v in settings['cfg'].items():
                if k not in CFG:
                    continue
                d = CFG[k]
                if isinstance(d, bool) or isinstance(v, bool):
                    if type(v) == type(d):
                        CFG[k] = v
                elif isinstance(d, (int, float)) and isinstance(v, (int, float)):
                    CFG[k] = type(d)(v)   # sliders may store int/float interchangeably
                elif type(v) == type(d):
                    CFG[k] = v
    except Exception as e:
        print(f"[Settings init error] {e}")

def persist_cfg():
    try:
        auth_service.save_settings({'cfg': dict(CFG)})
    except Exception as e:
        print(f"[Settings save error] {e}")

# ── Font Helper (Inter with fallback to Segoe UI) ─────────────────────────────
def get_font(weight='regular', size=13):
    """Returns Inter if installed on Windows, else falls back to Segoe UI."""
    wt_map = {
        'regular': 'normal',
        'medium': 'normal',
        'semibold': 'bold',
        'bold': 'bold'
    }
    # Tkinter handles family tuple fallback in modern versions
    return ('Inter', size, wt_map.get(weight, 'normal'))

# ── C-Wing Logo Renderer (Vector Drawing to PIL) ──────────────────────────────
def cubic_bezier_points(p0, p1, p2, p3, n=24):
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1.0 - t
        x = (u**3 * p0[0] + 3*u**2 * t * p1[0] + 3*u * t**2 * p2[0] + t**3 * p3[0])
        y = (u**3 * p0[1] + 3*u**2 * t * p1[1] + 3*u * t**2 * p2[1] + t**3 * p3[1])
        pts.append((x, y))
    return pts

def get_c_wing_polygon(canvas_size=200):
    cmds = [
        ('M', (172, 42)),
        ('C', (135, 36), (68, 58), (42, 106)),
        ('C', (24, 142), (42, 182), (86, 188)),
        ('C', (116, 192), (146, 186), (170, 170)),
        ('L', (155, 148)),
        ('C', (136, 160), (116, 164), (96, 162)),
        ('C', (68, 158), (58, 134), (62, 112)),
        ('C', (68, 88), (92, 72), (122, 72)),
        ('C', (138, 72), (154, 78), (168, 88)),
        ('C', (156, 76), (148, 68), (152, 62)),
        ('C', (158, 54), (166, 48), (172, 42))
    ]
    poly = []
    curr = cmds[0][1]
    poly.append(curr)
    for cmd in cmds[1:]:
        if cmd[0] == 'C':
            pts = cubic_bezier_points(curr, cmd[1], cmd[2], cmd[3], n=24)
            poly.extend(pts[1:])
            curr = cmd[3]
        elif cmd[0] == 'L':
            poly.append(cmd[1])
            curr = cmd[1]
    return poly

def create_c_wing_image(size=64, color='#E75B3C', bg_color=None):
    """Renders crisp anti-aliased C-Wing logo at specified size."""
    super_size = size * 4
    img = Image.new('RGBA', (super_size, super_size), bg_color or (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    base_poly = get_c_wing_polygon()
    scaled_poly = [((x * super_size / 200.0), (y * super_size / 200.0)) for x, y in base_poly]
    draw.polygon(scaled_poly, fill=color)
    resample_filter = getattr(getattr(Image, 'Resampling', Image), 'LANCZOS', getattr(Image, 'ANTIALIAS', 1))
    return img.resize((size, size), resample_filter)

# ── Window Automation Helpers ─────────────────────────────────────────────────
def _enum_visible_windows():
    if not IS_WINDOWS or not user32:
        return []
    results = []
    # 64-bit compatible HWND and LPARAM types
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n > 0:
                b = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, b, n + 1)
                title = b.value
                if title and title not in ('Default IME', 'MSCTFIME UI'):
                    results.append((hwnd, title))
        return True
    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return results

def _find_hwnd(fragment):
    if not fragment or not fragment.strip() or not IS_WINDOWS:
        return None
    fl = fragment.strip().lower()
    # 1. Search for other application windows first (ignore ClockWise window itself)
    for hwnd, title in _enum_visible_windows():
        t_low = title.lower()
        if 'clockwise' not in t_low and fl in t_low:
            return hwnd
    # 2. Fallback to any window containing the fragment
    for hwnd, title in _enum_visible_windows():
        if fl in title.lower():
            return hwnd
    return None

def _focus_hwnd(hwnd):
    if not IS_WINDOWS or not hwnd or not user32 or not user32.IsWindow(hwnd):
        return False
    try:
        # 1. Un-minimize if minimized
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        else:
            user32.ShowWindow(hwnd, 5)  # SW_SHOW

        # 2. Windows Focus-Stealing Lock Bypass: Simulate Alt key tap to obtain foreground permission
        try:
            user32.keybd_event(0x12, 0, 0, 0)  # VK_MENU (Alt) down
            user32.keybd_event(0x12, 0, 2, 0)  # VK_MENU (Alt) up
        except Exception:
            pass

        # 3. Attach thread input to bypass Windows Focus-Stealing restriction
        cur_tid = kernel32.GetCurrentThreadId() if kernel32 else 0
        fg_hwnd = user32.GetForegroundWindow()
        fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0

        if fg_tid and cur_tid and fg_tid != cur_tid:
            user32.AttachThreadInput(cur_tid, fg_tid, True)
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.AttachThreadInput(cur_tid, fg_tid, False)
        else:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)

        # 4. Use SwitchToThisWindow API
        try:
            user32.SwitchToThisWindow(hwnd, True)
        except Exception:
            pass

        user32.SetActiveWindow(hwnd)
        return True
    except Exception as e:
        print(f"[Focus window error] {e}")
        return False

def switch_to_slot(idx):
    if idx < 0 or idx >= NUM_SLOTS: return False
    slot = window_slots[idx]
    frag = slot.get('title_fragment', '').strip()
    if not frag: return False
    hwnd = _find_hwnd(frag)
    if hwnd:
        slot['hwnd'] = hwnd
        return _focus_hwnd(hwnd)
    return False

def _do_alt_tab():
    """Simulates a natural Alt+Tab (hold Alt, tap Tab 1..N times, release Alt)."""
    if not IS_WINDOWS or not keyboard:
        return False
    max_depth = max(1, int(CFG.get('alt_tab_max_depth', 2)))
    # Humans mostly flip to the previous window; deeper jumps are rarer
    presses = 1 if (max_depth == 1 or random() < 0.6) else randint(2, max_depth)
    try:
        keyboard.press('alt')
        sleep(uniform(0.05, 0.12))
        for _ in range(presses):
            keyboard.press_and_release('tab')
            sleep(uniform(0.12, 0.3))
    except Exception as e:
        print(f"[Alt+Tab error] {e}")
        return False
    finally:
        try: keyboard.release('alt')
        except Exception: pass
    return True

def do_window_switch():
    """Switches window using the configured mode (Alt+Tab default, slots optional)."""
    if CFG.get('switch_mode') == 'slots':
        active_slots = [i for i in range(NUM_SLOTS) if window_slots[i]['title_fragment'].strip()]
        if active_slots and switch_to_slot(choice(active_slots)):
            return True
        return False
    return _do_alt_tab()

def _idle_pause(seconds):
    """Interruptible idle (no input at all) so Stop/Quit stay responsive."""
    end = time() + seconds
    while running and not exit_program and time() < end:
        sleep(0.2)

def _register_window_hotkeys():
    global _win_hotkeys
    if not IS_WINDOWS or not keyboard: return
    for hk in _win_hotkeys:
        try: keyboard.remove_hotkey(hk)
        except: pass
    _win_hotkeys = []
    for i in range(NUM_SLOTS):
        try:
            hk = keyboard.add_hotkey(f'ctrl+alt+{i+1}', lambda n=i: switch_to_slot(n), suppress=False)
            _win_hotkeys.append(hk)
        except Exception:
            pass

# ── Break Reminder Notification ───────────────────────────────────────────────
def _show_break_popup():
    t = THEME[CURRENT_THEME]
    def _popup():
        w = tk.Tk()
        w.overrideredirect(True)
        w.attributes('-topmost', True)
        w.configure(bg=t['panel'], highlightthickness=1, highlightbackground=t['hairline'])
        sw, sh = w.winfo_screenwidth(), w.winfo_screenheight()
        pw, ph = 340, 130
        w.geometry(f'{pw}x{ph}+{sw - pw - 24}+{sh - ph - 60}')

        tk.Label(w, text='ClockWise — Rest Reminder', bg=t['panel'], fg=t['accent'],
                 font=get_font('semibold', 12)).pack(pady=(16, 4))
        dur = int(CFG['break_duration'])
        tk.Label(w, text=f"Steady time, well spent.\nSuggested break: {dur} min",
                 bg=t['panel'], fg=t['text'], font=get_font('regular', 10), justify='center').pack()

        btn = tk.Button(w, text='Dismiss', command=w.destroy,
                        bg=t['button_bg'], fg=t['button_fg'], relief='flat',
                        activebackground=t['button_hover'], activeforeground=t['button_fg'],
                        font=get_font('semibold', 9), padx=18, pady=4, cursor='hand2')
        btn.pack(pady=12)
        w.after(30000, w.destroy)
        w.mainloop()
    threading.Thread(target=_popup, daemon=True).start()

def _check_break():
    global _last_break
    if not CFG['break_enabled']: return
    elapsed = (time() - _last_break) / 60.0
    if elapsed >= CFG['break_interval']:
        _last_break = time()
        _show_break_popup()

# ── Browser Automation ────────────────────────────────────────────────────────
SEARCH_CATEGORIES = {
    'productivity': [
        'how to prioritize tasks effectively', 'best time management apps 2026',
        'deep work techniques for developers', 'how to avoid burnout at work',
        'pomodoro technique for productivity'
    ],
    'tech_support': [
        'how to clear browser cache chrome', 'why is my computer running slow',
        'fix wifi connection issues windows 11', 'how to take a screenshot on pc',
        'keyboard keys not working fix'
    ],
    'lifestyle': [
        'easy 15 minute healthy lunch ideas', 'best exercises for desk workers',
        'how to stay hydrated during work', 'desk setup for better posture',
        'meditation for stress relief at work'
    ],
    'worktools': [
        'google calendar tips and tricks', 'how to use microsoft teams efficiently',
        'best slack integrations for teams', 'zoom meeting shortcuts windows',
        'how to organize google drive files'
    ]
}

def _get_foreground_title():
    if not IS_WINDOWS or not user32: return ''
    hwnd = user32.GetForegroundWindow()
    if not hwnd: return ''
    n = user32.GetWindowTextLengthW(hwnd)
    if n == 0: return ''
    b = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, b, n + 1)
    return b.value.lower()

def _is_browser_active():
    t = _get_foreground_title()
    return any(b in t for b in ('chrome', 'firefox', 'edge', 'chromium', 'brave', 'opera'))

def _do_google_search():
    global searches_done, _last_search_time, _used_queries
    if not IS_WINDOWS or searches_done >= CFG['browser_search_limit']: return
    elapsed = (time() - _last_search_time) / 60.0
    if _last_search_time > 0 and elapsed < CFG['search_interval_min']: return

    title = _get_foreground_title()
    if 'chrome' not in title and 'chromium' not in title: return

    keyboard.press_and_release('ctrl+t')
    sleep(uniform(0.8, 1.5))
    if not running: return

    keyboard.write('google.com', delay=uniform(0.04, 0.07))
    keyboard.press_and_release('enter')
    sleep(uniform(3.0, 5.0))
    if not running: return

    all_queries = [q for cat in SEARCH_CATEGORIES.values() for q in cat]
    available = [q for q in all_queries if q not in _used_queries]
    if not available:
        _used_queries.clear()
        available = all_queries
    query = choice(available)
    _used_queries.add(query)

    sw, sh = pyautogui.size()
    search_box_x = sw // 2 + randint(-30, 30)
    search_box_y = sh // 2 + randint(-20, 20)
    _curved_move_to(search_box_x, search_box_y)
    sleep(uniform(0.3, 0.6))
    pyautogui.click()
    sleep(uniform(0.5, 1.0))

    keyboard.write(query, delay=uniform(0.05, 0.09))
    sleep(uniform(0.4, 0.8))
    keyboard.press_and_release('enter')
    sleep(uniform(3.0, 5.0))
    if not running: return

    for _ in range(randint(3, 6)):
        tx = sw // 2 + randint(-200, 200)
        ty = randint(200, 450)
        _curved_move_to(tx, ty)
        sleep(uniform(1.5, 3.0))
    if not running: return

    for _ in range(randint(5, 10)):
        pyautogui.scroll(-randint(4, 12))
        sleep(uniform(0.6, 1.5))
    if not running: return

    if random() < 0.8:
        click_x = sw // 2 + randint(-150, 150)
        click_y = randint(350, 700)
        _curved_move_to(click_x, click_y)
        sleep(uniform(0.5, 1.0))
        pyautogui.click()
        sleep(uniform(8.0, 18.0))
        if not running:
            keyboard.press_and_release('ctrl+w')
            searches_done += 1
            _last_search_time = time()
            return
        for _ in range(randint(2, 5)):
            pyautogui.scroll(-randint(2, 6))
            sleep(uniform(2.0, 4.0))
            if random() < 0.4:
                _curved_move_to(sw // 2 + randint(-100, 100), randint(300, 600))
            if not running: break

    keyboard.press_and_release('ctrl+w')
    searches_done += 1
    _last_search_time = time()
    sleep(uniform(1.0, 2.0))

def _do_browser_interaction():
    if not _is_browser_active() or not IS_WINDOWS: return
    if random() < CFG['browser_search_chance']:
        _do_google_search()
    else:
        action = choice(['ctrl+tab', 'ctrl+shift+tab', 'alt+left'])
        keyboard.press_and_release(action)
        sleep(uniform(0.5, 1.5))

# ── Mouse Smoothing Helpers ───────────────────────────────────────────────────
def _jitter(x, y, amount=3):
    if CFG.get('micro_jitter'):
        return x + randint(-amount, amount), y + randint(-amount, amount)
    return x, y

def _bezier_move(x1, y1, x2, y2, steps=40):
    if not IS_WINDOWS or not pyautogui: return
    ci = CFG['curve_intensity']
    cx = (x1 + x2) / 2 + uniform(-ci, ci)
    cy = (y1 + y2) / 2 + uniform(-ci, ci)
    steps = max(10, int(steps))
    for i in range(1, steps + 1):
        t = i / steps
        u = 1 - t
        px = int(u**2 * x1 + 2*u*t * cx + t**2 * x2)
        py = int(u**2 * y1 + 2*u*t * cy + t**2 * y2)
        px, py = _jitter(px, py)
        pyautogui.moveTo(px, py)
        speed_factor = 1.0 - abs(t - 0.5) * 0.6
        sleep(CFG['mouse_speed'] * 0.005 / max(speed_factor, 0.3))
        if CFG.get('stealth_mode') and random() < 0.03:
            sleep(uniform(0.05, 0.15))

def _curved_move_to(x, y):
    if not IS_WINDOWS or not pyautogui: return
    cx, cy = pyautogui.position()
    dist = ((x - cx)**2 + (y - cy)**2)**0.5
    steps = max(10, int(dist / 10))
    _bezier_move(cx, cy, x, y, steps)

def _do_scroll():
    if not IS_WINDOWS or not pyautogui: return
    direction = choice(['up', 'down'])
    bursts = randint(1, max(1, CFG['scroll_max_bursts']))
    for _ in range(bursts):
        clicks = randint(1, max(1, CFG['scroll_max_clicks']))
        pyautogui.scroll(clicks if direction == 'up' else -clicks)
        sleep(uniform(0.4, 1.2))

def _press_arrow_keys():
    if not IS_WINDOWS or not keyboard: return
    for _ in range(randint(1, max(1, CFG['arrow_max_keys']))):
        keyboard.press_and_release(choice(['up', 'down', 'left', 'right']))
        sleep(random() * 0.3 + 0.05)

# ── Main Background Loop ──────────────────────────────────────────────────────
def click_loop():
    global exit_program, running, _idle_debt
    if not IS_WINDOWS or not pyautogui: return
    sw, sh = pyautogui.size()
    m = 100
    x_lo, x_hi = m, sw - m
    y_lo, y_hi = m, sh - m

    while not exit_program:
        if not running:
            sleep(0.2)
            continue
        try:
            tick_start = time()
            _check_break()
            if CFG.get('randomize_patterns'):
                t_min = CFG['tick_min'] + uniform(-0.2, 0.2)
                t_max = max(t_min + 0.1, CFG['tick_max'] + uniform(-0.3, 0.3))
            else:
                t_min = CFG['tick_min']
                t_max = max(t_min + 0.1, CFG['tick_max'])

            _curved_move_to(randint(x_lo, x_hi), randint(y_lo, y_hi))

            if random() < CFG['rightclick_chance']:
                _curved_move_to(randint(x_lo, x_hi), randint(y_lo, y_hi))
                pyautogui.click(button='right')
                sleep(random() * 0.4 + 0.1)
                keyboard.press_and_release('escape')

            if random() < CFG['scroll_chance']:
                _do_scroll()

            if random() < CFG['arrow_chance']:
                _press_arrow_keys()

            if random() < CFG['browser_chance']:
                _do_browser_interaction()

            if random() < CFG['chrome_tab_chance']:
                title = _get_foreground_title()
                if 'chrome' in title or 'chromium' in title:
                    keyboard.press_and_release('ctrl+tab')

            if random() < CFG['auto_switch_chance']:
                if do_window_switch():
                    sleep(uniform(2.0, 5.0))

            sleep(uniform(t_min, t_max))

            # Activity duty cycle: for every second active, owe (1-a)/a seconds idle.
            # Idle is paid back in natural-length pauses rather than every tick.
            a = min(1.0, max(0.1, float(CFG.get('activity_level', 0.8))))
            if a < 0.99:
                _idle_debt += (time() - tick_start) * (1.0 - a) / a
                if _idle_debt >= uniform(6.0, 25.0):
                    pause = _idle_debt * uniform(0.85, 1.15)
                    _idle_debt = 0.0
                    _idle_pause(pause)
        except Exception as exc:
            print(f'[ClockWise worker] {exc}')
            sleep(1.0)

# ── App Control (Start / Stop / Quit) ──────────────────────────────────────────
def start(icon=None, item=None):
    global running, searches_done, _last_break, _last_search_time, _used_queries, _idle_debt
    # Subscription Access Restriction Gate
    if not current_user:
        if main_window:
            messagebox.showwarning("Access Restricted", "Please log in with an active subscription to start ClockWise.")
        return
    running = True
    searches_done = 0
    _last_break = time()
    _last_search_time = 0.0
    _used_queries = set()
    _idle_debt = 0.0
    _rebuild_tray_menu()

def stop(icon=None, item=None):
    global running
    running = False
    _rebuild_tray_menu()

def quit_app(icon=None, item=None):
    global running, exit_program
    running = False
    exit_program = True
    if tray_icon:
        try: tray_icon.stop()
        except: pass
    if main_window:
        try: main_window.destroy()
        except: pass
    if login_window:
        try: login_window.destroy()
        except: pass
    sys.exit(0)

# ── Tray Management ───────────────────────────────────────────────────────────
def _build_tray_menu():
    lbl = 'Stop ClockWise (F10)' if running else 'Start ClockWise (F9)'
    act = stop if running else start
    return pystray.Menu(
        pystray.MenuItem(lbl, act),
        pystray.MenuItem('Open ClockWise Settings', lambda: show_main_window()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('Quit ClockWise (F11)', quit_app)
    )

def _rebuild_tray_menu():
    if tray_icon:
        try:
            tray_icon.menu = _build_tray_menu()
            tray_icon.update_menu()
        except Exception:
            pass

def tray_thread_func():
    global tray_icon
    if not IS_WINDOWS or not pystray: return
    # Create C-Wing silhouette icon for tray
    tray_img = create_c_wing_image(size=64, color='#E75B3C', bg_color=(16, 60, 58, 255))
    tray_icon = pystray.Icon('ClockWise', tray_img, 'ClockWise — Wise about time', menu=_build_tray_menu())
    tray_icon.run()

def hotkey_thread_func():
    if not IS_WINDOWS or not keyboard: return
    keyboard.add_hotkey('f9',  start,    suppress=True)
    keyboard.add_hotkey('f10', stop,     suppress=True)
    keyboard.add_hotkey('f11', quit_app, suppress=True)
    _register_window_hotkeys()
    keyboard.wait()

# ── ClockWise Modern UI Windows (Tkinter) ─────────────────────────────────────

def toggle_theme():
    global CURRENT_THEME
    CURRENT_THEME = 'day' if CURRENT_THEME == 'night' else 'night'
    if main_window:
        main_window.destroy()
        show_main_window()

def show_main_window():
    global main_window
    if main_window:
        try:
            main_window.deiconify()
            main_window.lift()
            main_window.focus_force()
            return
        except Exception:
            main_window = None

    t = THEME[CURRENT_THEME]
    root = tk.Tk()
    main_window = root
    root.title('ClockWise')
    root.resizable(True, True)
    root.minsize(540, 500)
    root.configure(bg=t['window'])

    # Apply modern ttk styles for clam theme
    style = ttk.Style(root)
    try:
        style.theme_use('clam')
    except Exception:
        pass
    style.configure('TScale', background=t['panel'], troughcolor=t['trough'],
                    slidercolor=t['text'], sliderrelief='flat', borderwidth=0)
    style.configure('Vertical.TScrollbar', background=t['window'], troughcolor=t['window'],
                    bordercolor=t['hairline'], arrowcolor=t['secondary_text'], relief='flat')

    # Set Windows window icon if available
    ico_path = os.path.join(os.path.dirname(__file__), 'icons', 'clockwise.ico')
    if os.path.exists(ico_path):
        try: root.iconbitmap(ico_path)
        except Exception: pass

    # ── 1. Top Header Lockup: C-Wing Logo + "ClockWise" + Theme Toggle + Account info
    header = tk.Frame(root, bg=t['window'], padx=20, pady=14)
    header.pack(side='top', fill='x')

    # Logo image
    logo_color = t['accent'] if CURRENT_THEME == 'night' else t['text']
    logo_pil = create_c_wing_image(size=28, color=logo_color)
    logo_tk = ImageTk.PhotoImage(logo_pil)
    root._logo_tk = logo_tk  # Keep reference

    logo_label = tk.Label(header, image=logo_tk, bg=t['window'])
    logo_label.pack(side='left', padx=(0, 10))

    title_label = tk.Label(header, text='ClockWise', font=get_font('bold', 20),
                           bg=t['window'], fg=t['text'])
    title_label.pack(side='left')

    # Theme Switcher Button
    theme_btn = tk.Button(header, text=f"Theme: {t['name']}", command=toggle_theme,
                          bg=t['panel'], fg=t['secondary_text'], relief='flat',
                          font=get_font('medium', 9), padx=10, pady=3,
                          highlightthickness=1, highlightbackground=t['hairline'], cursor='hand2')
    theme_btn.pack(side='right', padx=(10, 0))

    # User Subscription Pill & Log out
    if current_user:
        days_left = current_user.get('days_remaining', 30)
        user_email = current_user.get('email', 'User')
        user_tag = f"{user_email} • {days_left}d left"
        user_pill = tk.Label(header, text=user_tag, bg=t['badge_active_bg'],
                             fg=t['badge_active_fg'], font=get_font('semibold', 9),
                             highlightthickness=1, highlightbackground=t['hairline'],
                             padx=10, pady=3)
        user_pill.pack(side='right')

        def _do_logout():
            if messagebox.askyesno('Log Out', 'Are you sure you want to log out of ClockWise?'):
                auth_service.clear_session()
                root.destroy()
                show_login_window()

        logout_btn = tk.Button(header, text="Log out", command=_do_logout,
                               bg=t['window'], fg=t['secondary_text'], relief='flat',
                               font=get_font('regular', 8), cursor='hand2')
        logout_btn.pack(side='right', padx=(0, 6))

    # Background update checker for header
    def _check_update_for_header():
        tag, has_update, rdata = auth_service.check_for_updates(timeout=3)
        if has_update and tag:
            def _inject_pill():
                update_btn = tk.Button(header, text=f"Update: {tag}",
                                       command=lambda: show_update_modal(root, tag, rdata),
                                       bg=t['accent'], fg='#FFFFFF', relief='flat',
                                       font=get_font('bold', 9), padx=8, pady=2, cursor='hand2')
                update_btn.pack(side='right', padx=(6, 0))
            root.after(0, _inject_pill)
    threading.Thread(target=_check_update_for_header, daemon=True).start()

    # ── 2. Live Status Sub-header ─────────────────────────────────────────────
    status_frame = tk.Frame(root, bg=t['window'], padx=20, pady=2)
    status_frame.pack(side='top', fill='x')
    
    live_dot = tk.Label(status_frame, text='■', fg=t['accent'], bg=t['window'], font=get_font('bold', 12))
    live_dot.pack(side='left', padx=(0, 6))
    live_text = tk.Label(status_frame, text='Running' if running else 'Stopped',
                         font=get_font('semibold', 12), bg=t['window'], fg=t['text'])
    live_text.pack(side='left')

    # ── 3. Bottom Action Bar (PACKED BEFORE CANVAS to guarantee visibility) ────
    bar = tk.Frame(root, bg=t['window'], padx=20, pady=12,
                   highlightthickness=1, highlightbackground=t['hairline'])
    bar.pack(side='bottom', fill='x')

    hotkey_hint = tk.Label(bar, text='F9 Start   •   F10 Stop   •   F11 Quit',
                           font=get_font('regular', 10), bg=t['window'], fg=t['secondary_text'])
    hotkey_hint.pack(side='left')

    def on_start_stop():
        if running: stop()
        else: start()
        update_live_ui()

    start_btn = tk.Button(bar, text='Stop' if running else 'Start',
                          command=on_start_stop, bg=t['button_bg'], fg=t['button_fg'],
                          activebackground=t['button_hover'], activeforeground=t['button_fg'],
                          font=get_font('semibold', 12), padx=26, pady=6, relief='flat',
                          cursor='hand2')
    start_btn.pack(side='right')

    def on_logout():
        auth_service.clear_session()
        root.destroy()
        show_login_window()

    logout_btn = tk.Button(bar, text='Log out', command=on_logout,
                           bg=t['window'], fg=t['secondary_text'], relief='flat',
                           font=get_font('regular', 10), padx=12, pady=6, cursor='hand2')
    logout_btn.pack(side='right', padx=(0, 8))

    # ── 4. Scrollable Container (Canvas + Content) ─────────────────────────────
    canvas_wrap = tk.Frame(root, bg=t['window'])
    canvas_wrap.pack(side='top', fill='both', expand=True, padx=4, pady=4)

    scrollbar = ttk.Scrollbar(canvas_wrap, orient='vertical', style='Vertical.TScrollbar')
    scrollbar.pack(side='right', fill='y')

    canvas = tk.Canvas(canvas_wrap, bg=t['window'], highlightthickness=0, yscrollcommand=scrollbar.set)
    canvas.pack(side='left', fill='both', expand=True)
    scrollbar.config(command=canvas.yview)

    content = tk.Frame(canvas, bg=t['window'], padx=16, pady=4)
    content_window_id = canvas.create_window((0, 0), window=content, anchor='nw')

    def _on_canvas_configure(e):
        canvas.itemconfig(content_window_id, width=e.width)
    canvas.bind('<Configure>', _on_canvas_configure)
    content.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
    root.bind_all('<MouseWheel>', lambda e: canvas.yview_scroll((-1)*(e.delta//120), 'units'))

    # Helper: Panel Card (1px hairline, 4px max corner, calm background)
    def create_panel(parent, title):
        card = tk.Frame(parent, bg=t['panel'], highlightthickness=1,
                        highlightbackground=t['hairline'], padx=16, pady=10)
        card.pack(fill='x', expand=True, pady=5)
        card.columnconfigure(1, weight=1)
        # Eyebrow label (Inter 700 caps 11px)
        tk.Label(card, text=title.upper(), font=get_font('bold', 10),
                 bg=t['panel'], fg=t['secondary_text']).grid(row=0, column=0, columnspan=4, sticky='w', pady=(0, 6))
        return card

    # Debounced auto-save of CFG to settings.json
    _save_job = [None]
    def schedule_save():
        if _save_job[0]:
            try: root.after_cancel(_save_job[0])
            except Exception: pass
        _save_job[0] = root.after(600, persist_cfg)

    # Helper: Slider row with grid layout
    def slider_row(card, row_idx, label, key, lo, hi, fmt='{:.1f} s', is_int=False):
        tk.Label(card, text=label, font=get_font('regular', 11), bg=t['panel'],
                 fg=t['text']).grid(row=row_idx, column=0, sticky='w', padx=(0, 10), pady=4)

        val_lbl = tk.Label(card, text=fmt.format(CFG[key]), font=get_font('semibold', 11),
                           bg=t['panel'], fg=t['secondary_text'], width=8, anchor='e')
        val_lbl.grid(row=row_idx, column=2, sticky='e', padx=(10, 0), pady=4)

        var = tk.DoubleVar(value=CFG[key])
        def on_slide(v):
            val = float(v)
            if is_int: val = int(round(val))
            CFG[key] = val
            val_lbl.config(text=fmt.format(val))
            schedule_save()

        scale = ttk.Scale(card, from_=lo, to=hi, orient='horizontal',
                          variable=var, command=on_slide, style='TScale')
        scale.grid(row=row_idx, column=1, sticky='ew', pady=4)

    # Helper: Toggle row with grid layout
    def toggle_row(card, row_idx, label, key):
        tk.Label(card, text=label, font=get_font('regular', 11), bg=t['panel'],
                 fg=t['text']).grid(row=row_idx, column=0, sticky='w', padx=(0, 10), pady=4)
        var = tk.BooleanVar(value=CFG[key])
        def on_toggle():
            CFG[key] = var.get()
            schedule_save()
        chk = tk.Checkbutton(card, variable=var, command=on_toggle, bg=t['panel'],
                             selectcolor=t['window'], activebackground=t['panel'],
                             relief='flat', highlightthickness=0)
        chk.grid(row=row_idx, column=2, sticky='e', pady=4)

    # 0. ACTIVITY LEVEL PANEL
    p0 = create_panel(content, 'Activity Level')
    slider_row(p0, 1, 'Active time (rest = natural idle)', 'activity_level', 0.3, 1.0, '{:.0%}')
    tk.Label(p0, text='80% means ~8 of every 10 minutes active, with realistic idle pauses in between.',
             font=get_font('regular', 9), bg=t['panel'], fg=t['secondary_text'],
             wraplength=460, justify='left').grid(row=2, column=0, columnspan=3, sticky='w', pady=(0, 2))

    # 1. TICK INTERVAL PANEL
    p1 = create_panel(content, 'Tick Interval')
    slider_row(p1, 1, 'Min delay between ticks', 'tick_min', 0.5, 10.0, '{:.1f} s')
    slider_row(p1, 2, 'Max delay between ticks', 'tick_max', 1.0, 30.0, '{:.1f} s')

    # 2. MOUSE MOVEMENT PANEL
    p2 = create_panel(content, 'Mouse Movement')
    slider_row(p2, 1, 'Speed (lower = faster)', 'mouse_speed', 0.1, 3.0, '{:.2f}×')
    slider_row(p2, 2, 'Curve intensity', 'curve_intensity', 0, 400, '{:.0f} px', is_int=True)
    toggle_row(p2, 3, 'Micro-jitter (humanizes cursor path)', 'micro_jitter')

    # 3. ACTIONS PANEL
    p3 = create_panel(content, 'Actions & Clicks')
    slider_row(p3, 1, 'Right-click chance', 'rightclick_chance', 0, 1, '{:.0%}')
    slider_row(p3, 2, 'Scroll wheel chance', 'scroll_chance', 0, 1, '{:.0%}')
    slider_row(p3, 3, 'Max bursts per scroll', 'scroll_max_bursts', 1, 8, '{:.0f}', is_int=True)
    slider_row(p3, 4, 'Arrow keys chance', 'arrow_chance', 0, 1, '{:.0%}')

    # 4. BROWSER AUTOMATION PANEL
    p4 = create_panel(content, 'Browser Automation')
    slider_row(p4, 1, 'Browser search chance', 'browser_chance', 0, 1, '{:.0%}')
    slider_row(p4, 2, 'Search limit per session', 'browser_search_limit', 1, 10, '{:.0f}', is_int=True)
    slider_row(p4, 3, 'Min interval between searches', 'search_interval_min', 5, 60, '{:.0f} min', is_int=True)
    slider_row(p4, 4, 'Chrome Ctrl+Tab chance', 'chrome_tab_chance', 0, 1, '{:.0%}')

    # 5. BREAK REMINDERS PANEL
    p5 = create_panel(content, 'Break Reminders')
    toggle_row(p5, 1, 'Enable periodic break reminders', 'break_enabled')
    slider_row(p5, 2, 'Remind interval', 'break_interval', 5, 120, '{:.0f} min', is_int=True)
    slider_row(p5, 3, 'Suggested break duration', 'break_duration', 1, 30, '{:.0f} min', is_int=True)

    test_break_btn = tk.Button(p5, text='Preview Break Notification', command=_show_break_popup,
                               bg=t['panel'], fg=t['secondary_text'], relief='flat',
                               font=get_font('semibold', 9), padx=10, pady=3,
                               highlightthickness=1, highlightbackground=t['hairline'], cursor='hand2')
    test_break_btn.grid(row=4, column=0, sticky='w', pady=(6, 2))

    # 6. STEALTH & ANTI-DETECTION PANEL
    p6 = create_panel(content, 'Stealth & Anti-Detection')
    toggle_row(p6, 1, 'Stealth mode (natural hesitations)', 'stealth_mode')
    toggle_row(p6, 2, 'Randomize tick patterns', 'randomize_patterns')

    # 7. WINDOW SWITCHING PANEL (Alt+Tab default, slots optional)
    pws = create_panel(content, 'Window Switching')
    tk.Label(pws, text='Method', font=get_font('regular', 11), bg=t['panel'],
             fg=t['text']).grid(row=1, column=0, sticky='w', padx=(0, 10), pady=4)
    mode_var = tk.StringVar(value=CFG.get('switch_mode', 'alt_tab'))
    mode_wrap = tk.Frame(pws, bg=t['panel'])
    mode_wrap.grid(row=1, column=1, columnspan=2, sticky='w', pady=4)

    def on_mode_change():
        CFG['switch_mode'] = mode_var.get()
        schedule_save()

    for val, txt in (('alt_tab', 'Alt+Tab (default)'), ('slots', 'Window Slots')):
        tk.Radiobutton(mode_wrap, text=txt, value=val, variable=mode_var, command=on_mode_change,
                       indicatoron=0, font=get_font('semibold', 9), padx=12, pady=3,
                       bg=t['panel'], fg=t['secondary_text'],
                       selectcolor=t['button_bg'], activebackground=t['panel'],
                       relief='flat', offrelief='flat', borderwidth=0,
                       highlightthickness=1, highlightbackground=t['hairline'],
                       cursor='hand2').pack(side='left', padx=(0, 6))
    # Keep selected segment text readable on the inverted background
    def _style_segments(*_):
        for w in mode_wrap.winfo_children():
            sel = (w.cget('value') == mode_var.get())
            w.config(fg=t['button_fg'] if sel else t['secondary_text'])
    mode_var.trace_add('write', _style_segments)
    _style_segments()

    slider_row(pws, 2, 'Switch chance per tick', 'auto_switch_chance', 0, 0.5, '{:.0%}')
    slider_row(pws, 3, 'Alt+Tab max depth', 'alt_tab_max_depth', 1, 4, '{:.0f} tab', is_int=True)

    def _test_switch():
        # Short delay so the click on this button finishes first
        root.after(800, do_window_switch)
    tk.Button(pws, text='Test Switch Now', command=_test_switch,
              bg=t['panel'], fg=t['secondary_text'], relief='flat',
              font=get_font('semibold', 9), padx=10, pady=3,
              highlightthickness=1, highlightbackground=t['hairline'],
              cursor='hand2').grid(row=4, column=0, sticky='w', pady=(6, 2))

    # 8. WINDOW SWITCHER SLOTS PANEL
    p7 = create_panel(content, 'Window Slots (optional · Ctrl+Alt+1 … 5)')
    p7.columnconfigure(1, weight=1)
    slot_vars = []
    status_lbls = []

    def _refresh_slot(idx, sv, lbl):
        frag = sv.get().strip()
        window_slots[idx]['title_fragment'] = frag
        # Persist slot settings to disk
        try:
            frags = [slot_vars[j].get().strip() for j in range(NUM_SLOTS)]
            auth_service.save_settings({'window_slots': frags})
        except Exception:
            pass
        if not frag:
            lbl.config(text='—', fg=t['secondary_text'])
            return
        hwnd = _find_hwnd(frag)
        window_slots[idx]['hwnd'] = hwnd
        if hwnd:
            n = user32.GetWindowTextLengthW(hwnd) if user32 else 0
            b = ctypes.create_unicode_buffer(n + 1) if user32 else None
            if user32: user32.GetWindowTextW(hwnd, b, n + 1)
            txt = (b.value[:18] + '…') if b and len(b.value) > 18 else (b.value if b else 'Found')
            lbl.config(text=f'✔ {txt}', fg=t['text'])
        else:
            lbl.config(text='✘ Not found', fg=t['accent'])

    for i in range(NUM_SLOTS):
        r_idx = i + 1
        tk.Label(p7, text=f'Ctrl+Alt+{i+1}', font=get_font('semibold', 9),
                 bg=t['panel'], fg=t['secondary_text'], width=11, anchor='w').grid(row=r_idx, column=0, sticky='w', pady=3)
        sv = tk.StringVar(value=window_slots[i]['title_fragment'])
        slot_vars.append(sv)
        entry = tk.Entry(p7, textvariable=sv, font=get_font('regular', 10),
                         bg=t['input_bg'], fg=t['input_fg'], highlightthickness=1,
                         highlightbackground=t['input_border'], relief='flat')
        entry.grid(row=r_idx, column=1, sticky='ew', padx=6, pady=3)
        lbl = tk.Label(p7, text='—', font=get_font('regular', 9), bg=t['panel'],
                       fg=t['secondary_text'], anchor='w', width=16)
        lbl.grid(row=r_idx, column=2, sticky='w', padx=(4, 6), pady=3)
        status_lbls.append(lbl)

        # Immediate Test / Jump button
        def _make_jump(slot_num, lb):
            def _jump():
                ok = switch_to_slot(slot_num)
                if ok:
                    lb.config(text='✔ Focused!', fg=t['text'])
                else:
                    lb.config(text='✘ Not found', fg=t['accent'])
            return _jump
        jump_btn = tk.Button(p7, text='Jump', command=_make_jump(i, lbl),
                             bg=t['panel'], fg=t['text'], relief='flat',
                             font=get_font('medium', 8), padx=6, pady=1,
                             highlightthickness=1, highlightbackground=t['hairline'], cursor='hand2')
        jump_btn.grid(row=r_idx, column=3, sticky='e', pady=3)

        sv.trace_add('write', lambda *_, idx=i, s=sv, lb=lbl: root.after(300, _refresh_slot, idx, s, lb))

    def scan_all_slots():
        for i in range(NUM_SLOTS):
            _refresh_slot(i, slot_vars[i], status_lbls[i])
        _register_window_hotkeys()

    scan_btn = tk.Button(p7, text='Scan & Bind Windows', command=scan_all_slots,
                         bg=t['panel'], fg=t['secondary_text'], relief='flat',
                         font=get_font('semibold', 9), padx=10, pady=3,
                         highlightthickness=1, highlightbackground=t['hairline'], cursor='hand2')
    scan_btn.grid(row=NUM_SLOTS + 1, column=0, sticky='w', pady=(6, 2))
    root.after(400, scan_all_slots)

    # 9. DEFAULTS PANEL
    pdef = create_panel(content, 'Defaults')
    tk.Label(pdef, text='Changes are saved automatically and become your new defaults.',
             font=get_font('regular', 9), bg=t['panel'], fg=t['secondary_text'],
             wraplength=460, justify='left').grid(row=1, column=0, columnspan=3, sticky='w')

    def reset_defaults():
        if not messagebox.askyesno('Reset Settings', 'Restore all automation settings to factory defaults?'):
            return
        CFG.update(DEFAULT_CFG)
        persist_cfg()
        root.destroy()
        show_main_window()

    tk.Button(pdef, text='Reset to Factory Defaults', command=reset_defaults,
              bg=t['panel'], fg=t['accent'], relief='flat',
              font=get_font('semibold', 9), padx=10, pady=3,
              highlightthickness=1, highlightbackground=t['hairline'],
              cursor='hand2').grid(row=2, column=0, sticky='w', pady=(6, 2))

    def update_live_ui():
        if running:
            live_dot.config(text='■', fg=t['accent'])
            live_text.config(text='Running', fg=t['text'])
            start_btn.config(text='Stop')
        else:
            live_dot.config(text='□', fg=t['secondary_text'])
            live_text.config(text='Stopped', fg=t['secondary_text'])
            start_btn.config(text='Start')
        root.after(500, update_live_ui)

    root.after(0, update_live_ui)

    # Center window with comfortable initial geometry
    root.update_idletasks()
    win_w, win_h = 620, 750
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f'{win_w}x{win_h}+{(sw - win_w)//2}+{(sh - win_h)//2}')
    root.protocol("WM_DELETE_WINDOW", lambda: root.withdraw()) # Minimize to tray on close
    root.mainloop()



# ── Login & Subscription Verification Window ──────────────────────────────────
def show_login_window(update_notice=None):
    global login_window, current_user
    t = THEME[CURRENT_THEME]

    root = tk.Tk()
    login_window = root
    root.title('ClockWise — Login')
    root.resizable(False, False)
    root.configure(bg=t['window'])

    # Set icon
    ico_path = os.path.join(os.path.dirname(__file__), 'icons', 'clockwise.ico')
    if os.path.exists(ico_path):
        try: root.iconbitmap(ico_path)
        except Exception: pass

    # Header with large C-Wing logo
    header = tk.Frame(root, bg=t['window'], pady=20)
    header.pack(fill='x')

    logo_color = t['accent'] if CURRENT_THEME == 'night' else t['text']
    logo_pil = create_c_wing_image(size=48, color=logo_color)
    logo_tk = ImageTk.PhotoImage(logo_pil)
    root._logo_tk = logo_tk

    logo_label = tk.Label(header, image=logo_tk, bg=t['window'])
    logo_label.pack(pady=(0, 6))

    tk.Label(header, text='ClockWise', font=get_font('bold', 22),
             bg=t['window'], fg=t['text']).pack()
    tk.Label(header, text='Steady time, well spent.', font=get_font('regular', 11),
             bg=t['window'], fg=t['secondary_text']).pack(pady=(2, 0))

    # Update Notice Banner (Shown only when update detected or subscription expired)
    if update_notice:
        banner = tk.Frame(root, bg=t['accent'], padx=14, pady=8)
        banner.pack(fill='x', padx=28, pady=(0, 10))
        tk.Label(banner, text=update_notice, font=get_font('semibold', 9),
                 bg=t['accent'], fg='#FFFFFF', wraplength=340, justify='center').pack()

    # Login Card Panel
    card = tk.Frame(root, bg=t['panel'], highlightthickness=1,
                    highlightbackground=t['hairline'], padx=24, pady=20)
    card.pack(fill='both', expand=True, padx=28, pady=(0, 20))

    tk.Label(card, text='EMAIL OR USERNAME', font=get_font('bold', 9),
             bg=t['panel'], fg=t['secondary_text']).pack(anchor='w', pady=(4, 2))
    email_entry = tk.Entry(card, font=get_font('regular', 11),
                           bg=t['input_bg'], fg=t['input_fg'], highlightthickness=1,
                           highlightbackground=t['input_border'], relief='flat')
    email_entry.pack(fill='x', pady=(0, 12), ipady=4)

    tk.Label(card, text='PASSWORD', font=get_font('bold', 9),
             bg=t['panel'], fg=t['secondary_text']).pack(anchor='w', pady=(4, 2))
    pass_entry = tk.Entry(card, show='•', font=get_font('regular', 11),
                          bg=t['input_bg'], fg=t['input_fg'], highlightthickness=1,
                          highlightbackground=t['input_border'], relief='flat')
    pass_entry.pack(fill='x', pady=(0, 16), ipady=4)

    status_label = tk.Label(card, text='', font=get_font('regular', 10),
                            bg=t['panel'], fg=t['accent'], wraplength=340, justify='center')
    status_label.pack(fill='x', pady=(0, 10))

    def attempt_login():
        email = email_entry.get().strip()
        pwd = pass_entry.get().strip()
        if not email or not pwd:
            status_label.config(text='Please enter both email and password.', fg=t['accent'])
            return

        status_label.config(text='Checking subscription with database...', fg=t['secondary_text'])
        root.update_idletasks()

        # Run query in background thread to avoid freezing UI
        def _verify_task():
            ok, msg, udata = auth_service.check_account_subscription(email, pwd)
            def _apply():
                global current_user
                if ok:
                    current_user = udata
                    status_label.config(text='✔ Access Granted!', fg=t['text'])
                    root.after(400, lambda: [root.destroy(), show_main_window()])
                else:
                    status_label.config(text=msg, fg=t['accent'])
            root.after(0, _apply)

        threading.Thread(target=_verify_task, daemon=True).start()

    login_btn = tk.Button(card, text='Sign In & Verify Access', command=attempt_login,
                          bg=t['button_bg'], fg=t['button_fg'], activebackground=t['button_hover'],
                          activeforeground=t['button_fg'], font=get_font('semibold', 11),
                          relief='flat', pady=8, cursor='hand2')
    login_btn.pack(fill='x', pady=(4, 10))

    # Pre-fill cached credentials if existing
    cached = auth_service.load_cached_session()
    if cached:
        email_entry.insert(0, cached.get('email', ''))
        pass_entry.insert(0, cached.get('password', ''))

    # Footer (Theme toggle)
    footer = tk.Frame(root, bg=t['window'], padx=28, pady=8)
    footer.pack(fill='x', side='bottom')

    theme_toggle = tk.Button(footer, text=f"Theme: {t['name']}",
                             command=lambda: [root.destroy(), toggle_theme(), show_login_window()],
                             bg=t['window'], fg=t['secondary_text'], relief='flat',
                             font=get_font('regular', 9), cursor='hand2')
    theme_toggle.pack(anchor='center')

    # Center window
    root.update_idletasks()
    win_w, win_h = 420, 530
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f'{win_w}x{win_h}+{(sw - win_w)//2}+{(sh - win_h)//2}')
    root.mainloop()

# ── App Startup Verification ──────────────────────────────────────────────────
def bootstrap():
    global current_user
    init_persisted_settings()
    # Attempt silent verification with cached session (only log out if update detected)
    ok, msg, udata = auth_service.verify_cached_session(enforce_update_check=True)
    if ok and udata:
        current_user = udata
        show_main_window()
    else:
        update_notice = None
        if msg and msg.startswith("UPDATE_DETECTED:"):
            tag = msg.split(":", 1)[1]
            update_notice = f"⚡ New update {tag} detected!\nPlease update ClockWise to continue using the application."
        elif "expired" in (msg or '').lower():
            update_notice = msg
        show_login_window(update_notice=update_notice)

# ── Main Entrypoint ───────────────────────────────────────────────────────────
def main():
    if IS_WINDOWS:
        threading.Thread(target=click_loop, daemon=True).start()
        threading.Thread(target=hotkey_thread_func, daemon=True).start()
        threading.Thread(target=tray_thread_func, daemon=True).start()
    
    bootstrap()

if __name__ == '__main__':
    main()
