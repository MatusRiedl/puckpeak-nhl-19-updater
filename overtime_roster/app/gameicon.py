"""NHL 19's own icon on the shadPS4 window (owner 2026-11-12, 0.91.0: the taskbar showed shadPS4's PS4 icon).

The icon is the player's own game's `sce_sys\\icon0.png`, read at run time (game data is never shipped). Windows makes
an icon straight from PNG bytes (CreateIconFromResourceEx), and WM_SETICON puts it on the emulator's top-level windows
(title bar, taskbar, Alt+Tab). The emulator's exe is never touched. The handles live as long as this app; shadPS4 falls
back to its own icon when the app closes first.
"""
import logging
import os
import sys
import threading
import time

log = logging.getLogger(__name__)

WM_SETICON, WM_GETICON = 0x0080, 0x007F
ICON_SMALL, ICON_BIG = 0, 1
SMTO_ABORTIFHUNG = 0x0002
MAX_PNG = 4 * 1024 * 1024
SIZES = {ICON_BIG: 256, ICON_SMALL: 32}


def icon_path(game_dir):
    """The game's icon0.png, or None."""
    path = os.path.join(game_dir or '', 'sce_sys', 'icon0.png')
    return path if game_dir and os.path.isfile(path) else None


def read_png(game_dir):
    """The PNG bytes of the game's icon, or None (no file, too big, not a PNG)."""
    path = icon_path(game_dir)
    if not path:
        return None
    try:
        if os.path.getsize(path) > MAX_PNG:
            return None
        with open(path, 'rb') as f:
            data = f.read()
    except OSError:
        return None
    return data if data.startswith(b'\x89PNG\r\n\x1a\n') else None


class GameIcon:
    """The game's icon as Windows icon handles, put on a process's windows by apply(pid)."""

    def __init__(self, game_dir, user32=None, windows=None):
        self.handles = {}
        if sys.platform != 'win32' and user32 is None:
            return
        data = read_png(game_dir)
        if data is None:
            return
        self.user32 = user32 if user32 is not None else self._load()
        from . import launch
        self.windows = windows if windows is not None else launch.Windows()
        import ctypes
        buf = ctypes.create_string_buffer(data, len(data))
        for kind, size in SIZES.items():
            h = self.user32.CreateIconFromResourceEx(buf, len(data), True, 0x00030000, size, size, 0)
            if h:
                self.handles[kind] = h
        if not self.handles:
            log.info('game icon: Windows made no icon from %s', icon_path(game_dir))

    @staticmethod
    def _load():
        import ctypes
        from ctypes import wintypes as wt
        u = ctypes.WinDLL('user32', use_last_error=True)
        u.CreateIconFromResourceEx.argtypes = [ctypes.c_char_p, wt.DWORD, wt.BOOL, wt.DWORD, ctypes.c_int,
                                               ctypes.c_int, wt.UINT]
        u.CreateIconFromResourceEx.restype = wt.HICON
        u.SendMessageTimeoutW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM, wt.UINT, wt.UINT,
                                          ctypes.POINTER(ctypes.c_size_t)]
        u.SendMessageTimeoutW.restype = ctypes.c_ssize_t
        return u

    def _send(self, hwnd, msg, wparam, lparam):
        import ctypes
        out = ctypes.c_size_t(0)
        ok = self.user32.SendMessageTimeoutW(hwnd, msg, wparam, lparam, SMTO_ABORTIFHUNG, 500, ctypes.byref(out))
        return out.value if ok else None

    def apply(self, pid):
        """Put the icon on pid's visible top-level windows that do not show it yet; the number of windows changed."""
        if not self.handles:
            return 0
        changed = 0
        try:
            hwnds = self.windows.visible_of([pid])
        except Exception:       # noqa: BLE001 (a cosmetic step: never in the way of the game)
            return 0
        for hwnd in hwnds:
            big = self.handles.get(ICON_BIG)
            if big and self._send(hwnd, WM_GETICON, ICON_BIG, 0) == big:
                continue
            for kind, h in self.handles.items():
                self._send(hwnd, WM_SETICON, kind, h)
            changed += 1
        if changed:
            log.info('game icon: on %d window(s) of process %s', changed, pid)
        return changed


FAST, SLOW, FAST_FOR = 1, 10, 90    # seconds: look often while the window appears, then now and then (a new window)


def watch(proc, game_dir, icon=None, sleep=time.sleep, clock=time.monotonic):
    """A daemon thread that keeps the game's icon on proc's windows until it exits. -> the thread, or None (no icon)."""
    icon = icon if icon is not None else GameIcon(game_dir)
    if not icon.handles:
        return None

    def run():
        start = clock()
        while proc.poll() is None:
            icon.apply(proc.pid)
            sleep(FAST if clock() - start < FAST_FOR else SLOW)

    t = threading.Thread(target=run, daemon=True, name='game-icon')
    t.start()
    return t
