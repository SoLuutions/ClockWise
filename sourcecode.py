import threading
import tkinter as tk
from tkinter import ttk
import ctypes
import ctypes.wintypes
import pyautogui
from time import sleep, time
from random import randint, random, choice, uniform
import keyboard
import pystray
from PIL import Image, ImageDraw

user32   = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

pyautogui.FAILSAFE = True
pyautogui.PAUSE    = 0.0

# ── Config ────────────────────────────────────────────────────────────────────
CFG = {
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
    'search_interval_min': 15.0,  # minutes between searches
    'chrome_tab_chance': 0.05,
    'auto_switch_chance': 0.08,   # chance to auto-switch windows per tick
    # Break reminder
    'break_enabled': False,
    'break_interval': 45.0,   # minutes
    'break_duration': 5.0,    # minutes (display only)
    # Stealth
    'stealth_mode': True,
    'randomize_patterns': True,
}

# ── State ─────────────────────────────────────────────────────────────────────
running           = False
exit_program      = False
tray_icon         = None
_last_break       = time()
_last_search_time = 0.0
searches_done     = 0
_used_queries     = set()

# ── Window Switcher ───────────────────────────────────────────────────────────
NUM_SLOTS    = 5
window_slots = [{'title_fragment': '', 'hwnd': None} for _ in range(NUM_SLOTS)]
_win_hotkeys = []

def _enum_visible_windows():
    results = []
    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.POINTER(ctypes.c_int))
    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n > 0:
                b = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, b, n + 1)
                results.append((hwnd, b.value))
        return True
    user32.EnumWindows(cb, 0)
    return results

def _find_hwnd(fragment):
    if not fragment.strip():
        return None
    fl = fragment.strip().lower()
    for hwnd, title in _enum_visible_windows():
        if fl in title.lower():
            return hwnd
    return None

def _focus_hwnd(hwnd):
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    user32.ShowWindow(hwnd, 9)
    user32.AllowSetForegroundWindow(0xFFFFFFFF)
    user32.SetForegroundWindow(hwnd)
    return True

def switch_to_slot(idx):
    slot = window_slots[idx]
    hwnd = _find_hwnd(slot['title_fragment'])
    if hwnd:
        slot['hwnd'] = hwnd
        _focus_hwnd(hwnd)

def _register_window_hotkeys():
    global _win_hotkeys
    for hk in _win_hotkeys:
        try: keyboard.remove_hotkey(hk)
        except: pass
    _win_hotkeys = [
        keyboard.add_hotkey(f'ctrl+alt+{i+1}', lambda n=i: switch_to_slot(n), suppress=True)
        for i in range(NUM_SLOTS)
    ]

# ── Break notification ────────────────────────────────────────────────────────
def _show_break_popup():
    def _popup():
        BG = '#0d1117'; ACC = '#58a6ff'
        FG = '#e6edf3'; DIM = '#8b949e'
        BTN = '#21262d'
        w = tk.Tk()
        w.overrideredirect(True)
        w.attributes('-topmost', True)
        w.configure(bg=BG, highlightthickness=1, highlightbackground=ACC)
        sw, sh = w.winfo_screenwidth(), w.winfo_screenheight()
        pw, ph = 320, 110
        w.geometry(f'{pw}x{ph}+{sw - pw - 20}+{sh - ph - 60}')

        tk.Label(w, text='☕  Break Time!', bg=BG, fg=ACC,
                 font=('Segoe UI', 12, 'bold')).pack(pady=(16, 2))
        dur = int(CFG['break_duration'])
        tk.Label(w, text=f"You've been working a while.\nSuggested break: {dur} min",
                 bg=BG, fg=DIM, font=('Segoe UI', 9)).pack()
        tk.Button(w, text='Dismiss', command=w.destroy,
                  bg=BTN, fg=ACC, relief='flat', activebackground='#30363d',
                  activeforeground='#79c0ff', font=('Segoe UI', 9, 'bold'),
                  padx=15, pady=2, cursor='hand2').pack(pady=12)
        # Auto-close after 30 s
        w.after(30000, w.destroy)
        w.mainloop()
    threading.Thread(target=_popup, daemon=True).start()

def _check_break():
    global _last_break
    if not CFG['break_enabled']:
        return
    elapsed = (time() - _last_break) / 60.0
    if elapsed >= CFG['break_interval']:
        _last_break = time()
        _show_break_popup()

# ── Browser interaction ───────────────────────────────────────────────────────
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

BROWSER_NAMES = ('chrome', 'firefox', 'edge', 'chromium', 'brave', 'opera')

def _get_foreground_title():
    hwnd = user32.GetForegroundWindow()
    if not hwnd: return ''
    n = user32.GetWindowTextLengthW(hwnd)
    if n == 0: return ''
    b = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, b, n + 1)
    return b.value.lower()

def _is_browser_active():
    t = _get_foreground_title()
    return any(name in t for name in BROWSER_NAMES)

def _do_google_search():
    global searches_done, _last_search_time, _used_queries
    if searches_done >= CFG['browser_search_limit']:
        return

    # Cooldown: don't search too often
    elapsed = (time() - _last_search_time) / 60.0
    if _last_search_time > 0 and elapsed < CFG['search_interval_min']:
        return

    # Only proceed if Chrome/Chromium is the active window
    title = _get_foreground_title()
    if 'chrome' not in title and 'chromium' not in title:
        return

    # 1. Open a new tab
    keyboard.press_and_release('ctrl+t')
    sleep(uniform(0.8, 1.5))
    if not running: return

    # 2. Navigate to google.com
    keyboard.write('google.com', delay=uniform(0.04, 0.07))
    keyboard.press_and_release('enter')
    sleep(uniform(3.0, 5.0))  # Wait for full page load
    if not running: return

    # 3. Pick a unique query (Bug #2: no repeats)
    all_queries = [q for cat in SEARCH_CATEGORIES.values() for q in cat]
    available = [q for q in all_queries if q not in _used_queries]
    if not available:
        _used_queries.clear()
        available = all_queries
    query = choice(available)
    _used_queries.add(query)

    # 4. Bug #1: Click the search box area first (center of page)
    sw, sh = pyautogui.size()
    search_box_x = sw // 2 + randint(-30, 30)
    search_box_y = sh // 2 + randint(-20, 20)
    _curved_move_to(search_box_x, search_box_y)
    sleep(uniform(0.3, 0.6))
    pyautogui.click()
    sleep(uniform(0.5, 1.0))

    # 5. Type the query with human-like speed
    keyboard.write(query, delay=uniform(0.05, 0.09))
    sleep(uniform(0.4, 0.8))
    keyboard.press_and_release('enter')
    sleep(uniform(3.0, 5.0))  # Wait for results
    if not running: return

    # 6. Simulate reading the AI Overview / top area
    for _ in range(randint(3, 6)):
        tx = sw // 2 + randint(-200, 200)
        ty = randint(200, 450)
        _curved_move_to(tx, ty)
        sleep(uniform(1.5, 3.0))
    if not running: return

    # 7. Deep scroll through results
    for _ in range(randint(5, 10)):
        pyautogui.scroll(-randint(4, 12))
        sleep(uniform(0.6, 1.5))
    if not running: return

    # 8. Click a random result link
    if random() < 0.8:
        click_x = sw // 2 + randint(-150, 150)
        click_y = randint(350, 700)
        _curved_move_to(click_x, click_y)
        sleep(uniform(0.5, 1.0))
        pyautogui.click()

        # 9. Read the clicked page
        sleep(uniform(8.0, 18.0))
        if not running:
            keyboard.press_and_release('ctrl+w')
            searches_done += 1
            _last_search_time = time()
            return

        # Minor reading activity on the page
        for _ in range(randint(2, 5)):
            pyautogui.scroll(-randint(2, 6))
            sleep(uniform(2.0, 4.0))
            if random() < 0.4:
                _curved_move_to(sw // 2 + randint(-100, 100), randint(300, 600))
            if not running: break

    # 10. Close the tab we opened
    keyboard.press_and_release('ctrl+w')
    searches_done += 1
    _last_search_time = time()
    sleep(uniform(1.0, 2.0))

def _do_browser_interaction():
    if not _is_browser_active():
        return
    if random() < CFG['browser_search_chance']:
        _do_google_search()
    else:
        # Switch tab or go back
        action = choice(['ctrl+tab', 'ctrl+shift+tab', 'alt+left'])
        keyboard.press_and_release(action)
        sleep(uniform(0.5, 1.5))

# ── Mouse helpers ─────────────────────────────────────────────────────────────
def _jitter(x, y, amount=3):
    if CFG.get('micro_jitter'):
        return x + randint(-amount, amount), y + randint(-amount, amount)
    return x, y

def _bezier_move(x1, y1, x2, y2, steps=40):
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
        # Natural acceleration: slow start/end, fast middle
        speed_factor = 1.0 - abs(t - 0.5) * 0.6
        sleep(CFG['mouse_speed'] * 0.005 / max(speed_factor, 0.3))
        # Occasional micro-pause (hesitation)
        if CFG.get('stealth_mode') and random() < 0.03:
            sleep(uniform(0.05, 0.15))

def _curved_move_to(x, y):
    cx, cy = pyautogui.position()
    dist   = ((x - cx)**2 + (y - cy)**2)**0.5
    steps  = max(10, int(dist / 10))
    _bezier_move(cx, cy, x, y, steps)

# ── Action helpers ────────────────────────────────────────────────────────────
ARROW_KEYS = ['up', 'down', 'left', 'right']

def _do_scroll():
    direction = choice(['up', 'down'])
    bursts = randint(1, max(1, CFG['scroll_max_bursts']))
    for _ in range(bursts):
        clicks = randint(1, max(1, CFG['scroll_max_clicks']))
        pyautogui.scroll(clicks if direction == 'up' else -clicks)
        # Simulate reading between scroll bursts
        sleep(uniform(0.4, 1.2))

def _press_arrow_keys():
    for _ in range(randint(1, max(1, CFG['arrow_max_keys']))):
        keyboard.press_and_release(choice(ARROW_KEYS))
        sleep(random() * 0.3 + 0.05)

# ── Main loop ─────────────────────────────────────────────────────────────────
def click_loop():
    global exit_program, running
    sw, sh = pyautogui.size()
    m = 100
    x_lo, x_hi = m, sw - m
    y_lo, y_hi = m, sh - m

    while not exit_program:
        if not running:
            sleep(0.2)
            continue
        try:
            _check_break()

            # Stealth: randomize tick boundaries each cycle
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

            # Chrome-only tab switch (only when Chrome is active)
            if random() < CFG['chrome_tab_chance']:
                title = _get_foreground_title()
                if 'chrome' in title or 'chromium' in title:
                    keyboard.press_and_release('ctrl+tab')

            # Auto window switch (non-disruptive, uses pinned slots)
            if random() < CFG['auto_switch_chance']:
                active_slots = [i for i in range(NUM_SLOTS)
                                if window_slots[i]['title_fragment'].strip()]
                if active_slots:
                    switch_to_slot(choice(active_slots))
                    sleep(uniform(2.0, 5.0))  # Stay on switched window briefly

            sleep(uniform(t_min, t_max))

        except Exception as exc:
            print(f'[click_loop] {exc}')
            sleep(1.0)

# ── Settings window ───────────────────────────────────────────────────────────
def open_settings(icon=None, item=None):
    threading.Thread(target=_settings_thread, daemon=True).start()

def _settings_thread():
    # ── Modern Color Palette ──
    BG  = '#0d1117'; FG  = '#e6edf3'  # Sleek dark blue-grey background, crisp text
    ACC = '#58a6ff'; GRN = '#2ea043'  # Vibrant neon blue accent, emerald green
    DIM = '#8b949e'; RED = '#f85149'  # Subdued text, alert red
    PANEL = '#161b22'                 # Slightly lighter for panels

    root = tk.Tk()
    root.title('System Host Configuration - Clark Lindley D. Suan')
    root.resizable(False, False)
    root.configure(bg=BG)

    style = ttk.Style(root)
    style.theme_use('clam')
    for name, opts in [
        ('TFrame',     {'background': BG}),
        ('TLabel',     {'background': BG, 'foreground': FG, 'font': ('Segoe UI', 9)}),
        ('Head.TLabel',{'background': BG, 'foreground': ACC,'font': ('Segoe UI', 11, 'bold')}),
        ('Sub.TLabel', {'background': BG, 'foreground': DIM,'font': ('Segoe UI', 8)}),
        ('TScale',     {'background': BG, 'troughcolor': '#21262d', 'slidercolor': ACC}),
        ('TButton',    {'background': '#21262d', 'foreground': ACC,
                        'font': ('Segoe UI', 9, 'bold'), 'borderwidth': 0, 'focusthickness': 0}),
        ('TEntry',     {'fieldbackground': '#0d1117', 'foreground': FG,
                        'insertcolor': FG, 'borderwidth': 1, 'bordercolor': '#30363d'}),
    ]:
        style.configure(name, **opts)
    style.map('TButton', background=[('active', '#30363d')], foreground=[('active', '#79c0ff')])

    canvas    = tk.Canvas(root, bg=BG, highlightthickness=0)
    scrollbar = ttk.Scrollbar(root, orient='vertical', command=canvas.yview)

    # Use standard tk.Frame to easily set custom background
    f = tk.Frame(canvas, bg=BG)
    f.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.create_window((0, 0), window=f, anchor='nw')
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side='left', fill='both', expand=True)
    scrollbar.pack(side='right', fill='y')
    root.bind_all('<MouseWheel>', lambda e: canvas.yview_scroll((-1)*(e.delta//120), 'units'))

    row = [0]

    # ── User Branding / Modern Header ──
    brand_frame = tk.Frame(f, bg=PANEL, padx=20, pady=20)
    brand_frame.grid(row=row[0], columnspan=3, sticky='ew', padx=10, pady=(10, 15))
    row[0] += 1

    tk.Label(brand_frame, text='Clark Lindley D. Suan', font=('Segoe UI', 16, 'bold'), bg=PANEL, fg=FG).pack(anchor='w')
    tk.Label(brand_frame, text='clarklindleysuan@gmail.com  •  clarklindleysuan.com', font=('Segoe UI', 9), bg=PANEL, fg=ACC).pack(anchor='w', pady=(2,0))

    def section(text, sub=''):
        ttk.Label(f, text=text, style='Head.TLabel').grid(
            row=row[0], columnspan=3, sticky='w', padx=12, pady=(14, 0))
        row[0] += 1
        if sub:
            ttk.Label(f, text=sub, style='Sub.TLabel').grid(
                row=row[0], columnspan=3, sticky='w', padx=14, pady=(0, 4))
            row[0] += 1

    def slider(label, key, lo, hi, res=0.01, fmt='{:.2f}', is_int=False):
        r = row[0]; var = tk.DoubleVar(value=CFG[key])
        vl = ttk.Label(f, text=fmt.format(CFG[key]), width=8)
        def on(*_):
            v = var.get()
            if is_int: v = int(round(v)); var.set(v)
            CFG[key] = v; vl.config(text=fmt.format(v))
        ttk.Label(f, text=label, width=32).grid(row=r, column=0, sticky='w', padx=(12,4), pady=3)
        ttk.Scale(f, from_=lo, to=hi, variable=var, orient='horizontal',
                  length=210, command=on).grid(row=r, column=1, padx=4, pady=3)
        vl.grid(row=r, column=2, padx=(4,12), pady=3)
        row[0] += 1

    def toggle_row(label, key):
        r = row[0]; var = tk.BooleanVar(value=CFG[key])
        def on(): CFG[key] = var.get()
        ttk.Label(f, text=label, width=32).grid(row=r, column=0, sticky='w', padx=(12,4), pady=3)

        # Styled checkbutton for dark theme
        tk.Checkbutton(f, variable=var, command=on, bg=BG, fg=ACC,
                       selectcolor=PANEL, activebackground=BG,
                       relief='flat').grid(row=r, column=1, sticky='w', padx=4)
        row[0] += 1

    # ── Sections ─────────────────────────────────────────────────────────────

    section('⏱  Tick Interval')
    slider('Min delay between ticks', 'tick_min', 0.5, 10,  0.5, '{:.1f} s')
    slider('Max delay between ticks', 'tick_max', 1,   30,  0.5, '{:.1f} s')

    section('🖱  Mouse Movement')
    slider('Speed  (lower = faster)',  'mouse_speed',     0.1, 3.0, 0.05, '{:.2f}×')
    slider('Curve intensity  (px)',    'curve_intensity', 0,   400, 10,   '{:.0f} px', True)
    toggle_row('Micro-jitter  (humanizes path)', 'micro_jitter')

    section('🖱  Right-Click')
    slider('Chance per tick', 'rightclick_chance', 0, 1, 0.01, '{:.0%}')

    section('🖱  Scroll Wheel')
    slider('Chance per tick',      'scroll_chance',     0, 1, 0.01, '{:.0%}')
    slider('Max bursts per event', 'scroll_max_bursts', 1, 8, 1,    '{:.0f}', True)
    slider('Max clicks per burst', 'scroll_max_clicks', 1, 10, 1,   '{:.0f}', True)

    section('⌨  Arrow Keys')
    slider('Chance per tick',       'arrow_chance',   0, 1, 0.01, '{:.0%}')
    slider('Max presses per event', 'arrow_max_keys', 1, 8, 1,    '{:.0f}', True)

    section('🌐  Browser Interaction',
            'Opens a new tab, searches Google naturally, reads results, then closes. Chrome-only features stay in Chrome.')
    slider('Chance per tick',           'browser_chance',        0, 1, 0.01, '{:.0%}')
    slider('Search limit per session',  'browser_search_limit',  1, 10, 1,   '{:.0f}', True)
    slider('Min interval between searches', 'search_interval_min', 5, 60, 5, '{:.0f} min', True)
    slider('Search vs tab-switch ratio','browser_search_chance', 0, 1, 0.01, '{:.0%}')
    slider('Chrome Ctrl+Tab chance',    'chrome_tab_chance',     0, 1, 0.01, '{:.0%}')

    section('☕  Break Reminder',
            'Shows a corner notification after you\'ve been working for a set time.')
    toggle_row('Enable break reminders', 'break_enabled')
    slider('Remind every  (minutes)',    'break_interval', 5,  120, 5, '{:.0f} min', True)
    slider('Suggested break  (minutes)', 'break_duration', 1,  30,  1, '{:.0f} min', True)

    def _test_break():
        _show_break_popup()
    test_btn = ttk.Button(f, text='Preview notification', command=_test_break)
    test_btn.grid(row=row[0], column=1, sticky='ew', padx=4, pady=(2,0))
    row[0] += 1

    section('🕵  Stealth / Anti-Detection',
            'Randomizes timing patterns and adds natural hesitations to avoid detection.')
    toggle_row('Stealth mode  (natural hesitations)', 'stealth_mode')
    toggle_row('Randomize tick patterns',             'randomize_patterns')
    slider('Auto window-switch chance',  'auto_switch_chance', 0, 0.5, 0.01, '{:.0%}')

    # ── Window Switcher ───────────────────────────────────────────────────────
    section('🪟  Window Switcher  (Ctrl+Alt+1 … Ctrl+Alt+5)',
            'Type a word from any window title. Press the hotkey to jump there instantly. Also used for auto-switching.')

    slot_vars   = []
    status_lbls = []

    def _refresh_slot(idx, sv, lbl):
        frag = sv.get().strip()
        window_slots[idx]['title_fragment'] = frag
        if not frag:
            lbl.config(text='—', fg=DIM); return
        hwnd = _find_hwnd(frag)
        window_slots[idx]['hwnd'] = hwnd
        if hwnd:
            n = user32.GetWindowTextLengthW(hwnd)
            b = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, b, n + 1)
            s = b.value[:38] + ('…' if len(b.value) > 38 else '')
            lbl.config(text=f'✔ {s}', fg=GRN)
        else:
            lbl.config(text='✘ Not found', fg=RED)

    for i in range(NUM_SLOTS):
        r = row[0]
        sv = tk.StringVar(value=window_slots[i]['title_fragment'])
        slot_vars.append(sv)

        tk.Label(f, text=f'Ctrl+Alt+{i+1}', bg=PANEL, fg=ACC,
                 font=('Segoe UI', 8, 'bold'), padx=6, pady=2
                 ).grid(row=r, column=0, sticky='w', padx=(14,4), pady=3)

        ttk.Entry(f, textvariable=sv, width=22).grid(row=r, column=1, padx=4, pady=3, sticky='ew')

        lbl = tk.Label(f, text='—', bg=BG, fg=DIM,
                       font=('Segoe UI', 8), anchor='w', width=30)
        lbl.grid(row=r, column=2, padx=(4,12), pady=3, sticky='w')
        status_lbls.append(lbl)

        sv.trace_add('write', lambda *_, idx=i, s=sv, lb=lbl:
                     root.after(300, _refresh_slot, idx, s, lb))
        row[0] += 1

    def scan_all():
        for i in range(NUM_SLOTS):
            _refresh_slot(i, slot_vars[i], status_lbls[i])
        _register_window_hotkeys()

    ttk.Button(f, text='🔍  Scan & Apply', command=scan_all).grid(
        row=row[0], column=1, sticky='ew', padx=4, pady=(4,0))
    ttk.Label(f, text='Re-resolve all slots + re-register hotkeys',
              style='Sub.TLabel').grid(row=row[0], column=2, sticky='w', padx=(4,12))
    row[0] += 1

    root.after(400, scan_all)

    # ── Bottom bar ────────────────────────────────────────────────────────────
    bar = tk.Frame(f, bg=PANEL)
    bar.grid(row=row[0], columnspan=3, sticky='ew', padx=10, pady=(20, 10))

    sv2 = tk.StringVar()
    sl  = tk.Label(bar, textvariable=sv2, bg=PANEL, font=('Segoe UI', 9, 'bold'))
    sl.pack(side='left', padx=10, pady=10)

    def _refresh_status():
        sv2.set('● Running' if running else '○ Stopped')
        sl.config(fg=ACC if running else '#8b949e')
        root.after(400, _refresh_status)

    root.after(0, _refresh_status)
    ttk.Button(bar, text='Start / Stop', command=lambda: stop() if running else start()
               ).pack(side='right', padx=(6, 10), pady=10)
    ttk.Button(bar, text='Close', command=root.destroy).pack(side='right', pady=10)

    root.update_idletasks()
    win_w, win_h = 580, min(820, root.winfo_reqheight() + 30)
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f'{win_w}x{win_h}+{(sw-win_w)//2}+{(sh-win_h)//2}')
    root.mainloop()

# ── Tray ──────────────────────────────────────────────────────────────────────
def start(icon=None, item=None):
    global running, searches_done, _last_break, _last_search_time, _used_queries
    running = True
    searches_done = 0
    _last_break = time()        # Bug #6: reset so break doesn't fire immediately
    _last_search_time = 0.0     # Allow first search after cooldown
    _used_queries = set()       # Fresh phrase pool
    _rebuild_tray_menu()

def stop(icon=None, item=None):
    global running; running = False; _rebuild_tray_menu()

def quit_app(icon=None, item=None):
    global running, exit_program
    running = False; exit_program = True
    t = icon or tray_icon
    if t: t.stop()

def _create_tray_image():
    img = Image.new('RGB', (64, 64), (30, 30, 30))
    d = ImageDraw.Draw(img)
    d.ellipse((16, 16, 48, 48), fill=(74, 144, 217))
    return img

def _build_menu():
    lbl = 'Stop (F10)' if running else 'Start (F9)'
    act = stop if running else start
    return pystray.Menu(
        pystray.MenuItem(lbl, act),
        pystray.MenuItem('Settings…', open_settings),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('Quit (F11)', quit_app),
    )

def _rebuild_tray_menu():
    if tray_icon:
        tray_icon.menu = _build_menu()
        tray_icon.update_menu()

def tray_thread():
    global tray_icon
    tray_icon = pystray.Icon('SystemHost', _create_tray_image(),
                             'System Host Service', menu=_build_menu())
    tray_icon.run()

# ── Hotkeys ───────────────────────────────────────────────────────────────────
def hotkey_thread():
    keyboard.add_hotkey('f9',  start,    suppress=True)
    keyboard.add_hotkey('f10', stop,     suppress=True)
    keyboard.add_hotkey('f11', quit_app, suppress=True)
    _register_window_hotkeys()
    keyboard.wait()

# ── Entry ─────────────────────────────────────────────────────────────────────
def main():
    threading.Thread(target=click_loop,    daemon=True).start()
    threading.Thread(target=hotkey_thread, daemon=True).start()
    threading.Thread(target=tray_thread,   daemon=True).start()
    # open_settings() # Commented out for stealth startup (starts in tray only)
    while not exit_program:
        sleep(0.5)

if __name__ == '__main__':
    main()
