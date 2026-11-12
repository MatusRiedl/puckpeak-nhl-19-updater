"""NHL 19's icon on the shadPS4 window (gameicon): read from the player's own game, put on once per window."""
from types import SimpleNamespace

from overtime_roster.app import gameicon

PNG = b'\x89PNG\r\n\x1a\n' + b'\0' * 64


class FakeUser32:
    def __init__(self):
        self.icons = {}         # (hwnd, kind) -> handle
        self.made = 0

    def CreateIconFromResourceEx(self, buf, size, icon, ver, cx, cy, flags):
        self.made += 1
        return 100 + cx

    def SendMessageTimeoutW(self, hwnd, msg, wparam, lparam, flags, timeout, out):
        if msg == gameicon.WM_SETICON:
            self.icons[(hwnd, wparam)] = lparam
        elif msg == gameicon.WM_GETICON:
            out._obj.value = self.icons.get((hwnd, wparam), 0)
        return 1


def game(tmp_path, data=PNG):
    (tmp_path / 'sce_sys').mkdir()
    (tmp_path / 'sce_sys' / 'icon0.png').write_bytes(data)
    return str(tmp_path)


def test_the_icon_goes_on_each_window_once(tmp_path):
    u = FakeUser32()
    icon = gameicon.GameIcon(game(tmp_path), user32=u, windows=SimpleNamespace(visible_of=lambda pids: [7, 8]))
    assert icon.apply(42) == 2
    assert u.icons == {(7, 1): 356, (7, 0): 132, (8, 1): 356, (8, 0): 132}
    assert icon.apply(42) == 0


def test_no_icon_without_the_games_png(tmp_path):
    u = FakeUser32()
    assert not gameicon.GameIcon(str(tmp_path), user32=u).handles
    assert not gameicon.GameIcon(game(tmp_path, b'not a png'), user32=u).handles
    assert u.made == 0 and gameicon.watch(SimpleNamespace(), '', icon=SimpleNamespace(handles={})) is None


def test_watch_stops_when_the_game_exits(tmp_path):
    runs = []
    proc = SimpleNamespace(pid=5, poll=lambda: None if len(runs) < 3 else 0)
    icon = SimpleNamespace(handles={1: 1}, apply=runs.append)
    gameicon.watch(proc, '', icon=icon, sleep=lambda s: None).join(2)
    assert runs == [5, 5, 5]
