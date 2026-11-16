import json
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

CONFIG_PATH = Path.home() / ".config" / "lyrics-pip" / "config.json"
DEFAULT_CONFIG = {"x": None, "y": None, "w": 380, "h": 300, "opacity": 0.92}
EDGE = 8

CSS = b"""
window.lyrics { background-color: rgb(18, 18, 22); border-radius: 10px; }
.title { color: #9aa0aa; font-size: 10pt; }
.status { color: #c9ced6; font-size: 12pt; }
.line { color: #6f7682; font-size: 12pt; }
.line.active { color: #ffffff; font-size: 15pt; font-weight: bold; }
button.close { color: #9aa0aa; background: none; border: none; box-shadow: none;
               padding: 0 6px; min-height: 0; min-width: 0; }
button.close:hover { color: #ff6b6b; }
"""


def load_config(path=CONFIG_PATH) -> dict:
    cfg = dict(DEFAULT_CONFIG)
    try:
        cfg.update(json.loads(Path(path).read_text()))
    except (OSError, ValueError):
        pass
    cfg["opacity"] = min(1.0, max(0.3, float(cfg.get("opacity") or 0.92)))
    return cfg


def save_config(cfg: dict, path=CONFIG_PATH) -> None:
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(cfg))
    except OSError:
        pass


def is_visible_position(x, y, w, h, monitors) -> bool:
    """True if enough of the window would land on one of the monitors."""
    if not monitors:
        return True
    for mx, my, mw, mh in monitors:
        ow = min(x + w, mx + mw) - max(x, mx)
        oh = min(y + h, my + mh) - max(y, my)
        if ow >= 80 and oh >= 40:
            return True
    return False


def _label(text, css_class, selectable=False):
    lab = Gtk.Label(label=text)
    lab.set_line_wrap(True)
    lab.set_justify(Gtk.Justification.CENTER)
    lab.set_xalign(0.5)
    lab.get_style_context().add_class(css_class)
    return lab


class LyricsWindow(Gtk.Window):
    def __init__(self, config_path=CONFIG_PATH):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self._config_path = config_path
        self._cfg = load_config(config_path)
        self._labels: list = []
        self._synced = False
        self._active = -1
        self._scroll_target = None
        self._scroll_timer = 0
        self.on_edit = None
        self.on_reload = None

        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.stick()  # visible on every workspace
        self.set_accept_focus(False)  # never steal keyboard focus from the user's work
        self.set_title("Lyrics PiP")
        self.set_resizable(True)
        self.set_default_size(self._cfg["w"], self._cfg["h"])
        self.set_opacity(self._cfg["opacity"])
        visual = self.get_screen().get_rgba_visual()
        if visual is not None:
            self.set_visual(visual)
        self.get_style_context().add_class("lyrics")

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            self.get_screen(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.set_margin_start(10)
        outer.set_margin_end(10)
        outer.set_margin_top(6)
        outer.set_margin_bottom(8)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._title = Gtk.Label(label="")
        self._title.set_xalign(0)
        self._title.set_ellipsize(3)  # Pango.EllipsizeMode.END
        self._title.get_style_context().add_class("title")
        header.pack_start(self._title, True, True, 0)
        close = Gtk.Button(label="×")
        close.get_style_context().add_class("close")
        close.set_relief(Gtk.ReliefStyle.NONE)
        close.set_can_focus(False)
        close.connect("clicked", lambda *_: self.close())
        header.pack_end(close, False, False, 0)
        self._edit_btn = self._header_button("✎", "Ubah lirik", lambda: self.on_edit)
        header.pack_end(self._edit_btn, False, False, 0)
        self._reload_btn = self._header_button("⟳", "Muat ulang lirik", lambda: self.on_reload)
        header.pack_end(self._reload_btn, False, False, 0)
        outer.pack_start(header, False, False, 0)

        self._scroller = Gtk.ScrolledWindow()
        self._scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.EXTERNAL)
        self._box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self._scroller.add(self._box)
        outer.pack_start(self._scroller, True, True, 0)
        self.add(outer)

        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.SCROLL_MASK
        )
        self.connect("button-press-event", self._on_press)
        self.connect("motion-notify-event", self._on_motion)
        self.connect("scroll-event", self._on_scroll)
        # The ScrolledWindow would otherwise swallow Ctrl+scroll over the lyrics.
        self._scroller.connect("scroll-event", self._on_scroll)
        self.connect("delete-event", self._on_delete)

        if self._cfg["x"] is not None and self._cfg["y"] is not None:
            x, y = int(self._cfg["x"]), int(self._cfg["y"])
            display = self.get_display()
            monitors = []
            for i in range(display.get_n_monitors()):
                g = display.get_monitor(i).get_geometry()
                monitors.append((g.x, g.y, g.width, g.height))
            if is_visible_position(x, y, self._cfg["w"], self._cfg["h"], monitors):
                self.move(x, y)

    # ---- content -------------------------------------------------------
    def _clear(self):
        for child in self._box.get_children():
            self._box.remove(child)
        self._labels = []
        self._active = -1
        self._synced = False

    def _header_button(self, label, tooltip, get_callback):
        btn = Gtk.Button(label=label)
        btn.get_style_context().add_class("close")
        btn.set_relief(Gtk.ReliefStyle.NONE)
        btn.set_can_focus(False)
        btn.set_tooltip_text(tooltip)
        btn.set_no_show_all(True)  # hidden until set_song_controls(True)

        def clicked(*_):
            cb = get_callback()
            if cb is not None:
                cb()

        btn.connect("clicked", clicked)
        return btn

    def set_song_controls(self, visible: bool) -> None:
        for btn in (self._edit_btn, self._reload_btn):
            if visible:
                btn.show()
            else:
                btn.hide()

    def set_status(self, text: str, action=None) -> None:
        self._clear()
        self._title.set_text("")
        self._box.set_margin_top(0)
        self._box.set_margin_bottom(0)
        self._box.set_valign(Gtk.Align.CENTER)
        self._box.pack_start(_label(text, "status"), False, False, 0)
        if action is not None:
            label, callback = action
            btn = Gtk.Button(label=label)
            btn.set_can_focus(False)
            btn.set_halign(Gtk.Align.CENTER)
            btn.connect("clicked", lambda *_: callback())
            self._box.pack_start(btn, False, False, 0)
        self._box.show_all()

    def set_lyrics(self, lyrics, title: str, artist: str) -> None:
        self._clear()
        self._title.set_text(f"{title} — {artist}" if artist else title)
        self._synced = bool(lyrics.synced)
        self._box.set_valign(Gtk.Align.START)
        pad = 110 if self._synced else 4
        self._box.set_margin_top(pad)
        self._box.set_margin_bottom(pad)
        for _, text in lyrics.lines:
            lab = _label(text or "♪", "line")
            self._labels.append(lab)
            self._box.pack_start(lab, False, False, 0)
        self._box.show_all()
        self._scroller.get_vadjustment().set_value(0)

    def set_active(self, index: int) -> None:
        if not self._synced or index == self._active:
            return
        if 0 <= self._active < len(self._labels):
            self._labels[self._active].get_style_context().remove_class("active")
        self._active = index
        if not (0 <= index < len(self._labels)):
            return
        self._labels[index].get_style_context().add_class("active")
        GLib.idle_add(self._scroll_to_active)

    def _scroll_to_active(self):
        if not (0 <= self._active < len(self._labels)):
            return False
        lab = self._labels[self._active]
        coords = lab.translate_coordinates(self._box, 0, 0)
        if coords is None:
            return False
        y = coords[1] + self._box.get_margin_top() + lab.get_allocated_height() / 2
        adj = self._scroller.get_vadjustment()
        self._scroll_target = max(0, y - adj.get_page_size() / 2)
        if not self._scroll_timer:
            self._scroll_timer = GLib.timeout_add(16, self._scroll_step)
        return False

    def _scroll_step(self):
        adj = self._scroller.get_vadjustment()
        diff = self._scroll_target - adj.get_value()
        if abs(diff) < 1:
            adj.set_value(self._scroll_target)
            self._scroll_timer = 0
            return False
        adj.set_value(adj.get_value() + diff * 0.25)
        return True

    # ---- window behaviour ---------------------------------------------
    def _edge_at(self, x, y):
        w, h = self.get_size()
        left, right = x < EDGE, x > w - EDGE
        top, bottom = y < EDGE, y > h - EDGE
        E = Gdk.WindowEdge
        if top and left:
            return E.NORTH_WEST
        if top and right:
            return E.NORTH_EAST
        if bottom and left:
            return E.SOUTH_WEST
        if bottom and right:
            return E.SOUTH_EAST
        if left:
            return E.WEST
        if right:
            return E.EAST
        if top:
            return E.NORTH
        if bottom:
            return E.SOUTH
        return None

    def _on_press(self, _w, ev):
        if ev.button != 1:
            return False
        edge = self._edge_at(ev.x, ev.y)
        if edge is not None:
            self.begin_resize_drag(edge, ev.button, int(ev.x_root), int(ev.y_root), ev.time)
        else:
            self.begin_move_drag(ev.button, int(ev.x_root), int(ev.y_root), ev.time)
        return True

    def _on_motion(self, _w, ev):
        edge = self._edge_at(ev.x, ev.y)
        win = self.get_window()
        if win is None:
            return False
        if edge is None:
            win.set_cursor(None)
        else:
            name = {
                Gdk.WindowEdge.NORTH: "n-resize", Gdk.WindowEdge.SOUTH: "s-resize",
                Gdk.WindowEdge.EAST: "e-resize", Gdk.WindowEdge.WEST: "w-resize",
                Gdk.WindowEdge.NORTH_WEST: "nw-resize", Gdk.WindowEdge.NORTH_EAST: "ne-resize",
                Gdk.WindowEdge.SOUTH_WEST: "sw-resize", Gdk.WindowEdge.SOUTH_EAST: "se-resize",
            }[edge]
            win.set_cursor(Gdk.Cursor.new_from_name(self.get_display(), name))
        return False

    def _on_scroll(self, _w, ev):
        if not (ev.state & Gdk.ModifierType.CONTROL_MASK):
            return False
        step = 0.05 if ev.direction == Gdk.ScrollDirection.UP else -0.05
        if ev.direction == Gdk.ScrollDirection.SMOOTH:
            step = -0.05 * ev.delta_y
        self._cfg["opacity"] = min(1.0, max(0.3, self._cfg["opacity"] + step))
        self.set_opacity(self._cfg["opacity"])
        return True

    def _on_delete(self, *_):
        x, y = self.get_position()
        w, h = self.get_size()
        self._cfg.update({"x": x, "y": y, "w": w, "h": h})
        save_config(self._cfg, self._config_path)
        return False


class LyricsPasteDialog(Gtk.Dialog):
    """Paste box for custom lyrics (plain text or LRC)."""

    def __init__(self, parent, heading: str, initial: str = ""):
        super().__init__(title="Ubah lirik", transient_for=parent, modal=True)
        self.set_keep_above(True)  # the lyrics window is always on top; so are we
        self.set_default_size(440, 380)
        self.add_button("Batal", Gtk.ResponseType.CANCEL)
        self.add_button("Simpan", Gtk.ResponseType.OK)
        area = self.get_content_area()
        area.set_spacing(6)
        area.set_border_width(8)
        area.pack_start(Gtk.Label(label=heading, xalign=0), False, False, 0)
        area.pack_start(
            Gtk.Label(label="Tempel lirik biasa, atau format LRC ([mm:ss.xx] teks) agar tersorot.",
                      xalign=0), False, False, 0)
        self._view = Gtk.TextView()
        self._view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        scroller = Gtk.ScrolledWindow()
        scroller.add(self._view)
        area.pack_start(scroller, True, True, 0)
        self.set_text(initial)
        area.show_all()

    def set_text(self, text: str) -> None:
        self._view.get_buffer().set_text(text)

    def get_text(self) -> str:
        buf = self._view.get_buffer()
        return buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)


def ask_lyrics_text(parent, heading: str, initial: str):
    """Show the paste dialog. Returns the text on Simpan (may be empty), None on cancel."""
    dialog = LyricsPasteDialog(parent, heading, initial)
    try:
        response = dialog.run()
        return dialog.get_text() if response == Gtk.ResponseType.OK else None
    finally:
        dialog.destroy()
