"""Neo settings window for the Linux companion."""
from pathlib import Path
import gi
import cairo
gi.require_foreign('cairo')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib
from neo_image import set_animation_frame

ASSETS = Path(__file__).resolve().parent / 'assets'

class NeoLevelSlider(Gtk.DrawingArea):
    """Three-stop slider; device writes occur only after a drag ends."""
    def __init__(self, on_commit):
        super().__init__()
        self.value = 0
        self.initial = 0
        self.start_x = 0.0
        self.dragging = False
        self.on_commit = on_commit
        self.set_content_height(40)
        self.set_hexpand(True)
        self.set_focusable(True)
        self.set_tooltip_text('ANC strength: Light, Balanced, or Deep')
        self.set_draw_func(self.draw_slider)
        drag = Gtk.GestureDrag.new()
        drag.set_button(1)
        drag.connect('drag-begin', self.drag_begin)
        drag.connect('drag-update', self.drag_update)
        drag.connect('drag-end', self.drag_end)
        self.add_controller(drag)
        keys = Gtk.EventControllerKey.new()
        keys.connect('key-pressed', self.key_pressed)
        self.add_controller(keys)

    def set_value(self, value):
        if not self.dragging:
            self.value = max(0, min(2, int(value)))
            self.queue_draw()

    def get_value(self): return self.value

    def choose(self, x):
        span = max(1, self.get_width() - 28)
        self.value = max(0, min(2, round((x - 14) / span * 2)))
        self.queue_draw()

    def drag_begin(self, gesture, x, y):
        if not self.is_sensitive(): return
        self.grab_focus()
        self.dragging = True
        self.initial = self.value
        self.start_x = x
        self.choose(x)

    def drag_update(self, gesture, dx, dy):
        if self.dragging: self.choose(self.start_x + dx)

    def drag_end(self, gesture, dx, dy):
        if not self.dragging: return
        self.choose(self.start_x + dx)
        self.dragging = False
        if self.value != self.initial: self.on_commit(self.value)

    def key_pressed(self, controller, keyval, keycode, state):
        if keyval not in (Gdk.KEY_Left, Gdk.KEY_Right, Gdk.KEY_Down, Gdk.KEY_Up): return False
        change = -1 if keyval in (Gdk.KEY_Left, Gdk.KEY_Down) else 1
        value = max(0, min(2, self.value + change))
        if value != self.value:
            self.value = value
            self.queue_draw()
            self.on_commit(value)
        return True

    def draw_slider(self, widget, cr, width, height):
        cr.set_antialias(cairo.ANTIALIAS_BEST)
        start, end, y = 14, max(15, width - 14), height / 2
        active = self.is_sensitive()
        cr.set_line_cap(1)
        cr.set_line_width(10)
        cr.set_source_rgb(.88, .88, .89); cr.move_to(start, y); cr.line_to(end, y); cr.stroke()
        x = start + (end-start) * self.value / 2
        cr.set_source_rgb(.10, .50, .98) if active else cr.set_source_rgb(.70, .74, .81)
        cr.move_to(start, y); cr.line_to(x, y); cr.stroke()
        for index in range(3):
            px = start + (end-start) * index / 2
            cr.set_source_rgb(.98, .98, .99); cr.arc(px, y, 2.2, 0, 6.283); cr.fill()
        cr.set_source_rgb(.10, .50, .98) if active else cr.set_source_rgb(.65, .69, .76)
        cr.arc(x, y, 10, 0, 6.283); cr.fill()
        cr.set_source_rgb(1, 1, 1); cr.arc(x, y, 4, 0, 6.283); cr.fill()

class NeoSettings:
    def __init__(self, app, action):
        self.action = action
        self.syncing = False
        self.mode = None
        self.adaptive = False
        self.window = Gtk.ApplicationWindow(application=app, title='REDMI Headphones Neo')
        self.window.set_default_size(420, 700)
        self.window.set_resizable(False)
        self.window.set_decorated(False)
        self.window.connect('close-request', self.hide)
        self.window.add_css_class('neo-settings-window')
        css = Gtk.CssProvider()
        css.load_from_data(b'''
          window.neo-settings-window { background: #f2f2f4; color: #121212; }
          .settings-title { color:#111; font-size:25px; font-weight:600; }
          .settings-card { background:white; color:#161616; border-radius:24px; padding:20px; }
          .settings-battery { background:#fafafa; border-radius:30px; padding:10px 22px; color:#333; font-size:18px; }
          .settings-battery-body { border:2px solid #60636b; border-radius:4px; padding:2px; min-width:23px; min-height:9px; }
          .settings-battery-fill { background:#60636b; border-radius:1px; min-height:7px; }
          .settings-battery-cap { background:#60636b; border-radius:0 2px 2px 0; min-width:2px; min-height:5px; }
          .mode-button { min-width:64px; min-height:64px; border-radius:20px; background:#eeeeef; color:#444; box-shadow:none; border:0; }
          .mode-button.active { background:#1684ff; color:#fff; }
          .mode-button label { font-size:12px; }
          .settings-status { color:#5b6372; font-size:12px; }
          .settings-row { color:#222; font-size:16px; padding:12px 2px; }
          .settings-back { min-width:40px; min-height:40px; padding:0; margin:0; border-radius:99px; background:#fff; border:none; box-shadow:none; }
          .settings-disconnect { min-height:48px; border-radius:18px; background:#fff; color:#e04848; border:none; box-shadow:none; font-size:15px; font-weight:500; }
          .settings-disconnect:hover { background:#fbeeee; }
          .settings-disconnect:disabled { color:#b0a0a0; }
        ''')
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        scroller = Gtk.ScrolledWindow(); scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.window.set_child(scroller)
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        page.set_margin_top(22); page.set_margin_bottom(24); page.set_margin_start(20); page.set_margin_end(20)
        scroller.set_child(page)
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        page.append(header)
        back = Gtk.Button(); back.add_css_class('settings-back'); back.set_tooltip_text('Back to popup')
        back_pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(ASSETS / 'back.svg'), 14, 14, True)
        back_icon = Gtk.Image.new_from_pixbuf(back_pixbuf)
        back_icon.set_halign(Gtk.Align.CENTER); back_icon.set_valign(Gtk.Align.CENTER)
        back.set_child(back_icon)
        back.connect('clicked', lambda *_: self.action('back', None))
        header.append(back)
        title = Gtk.Label(label='REDMI Headphones Neo'); title.add_css_class('settings-title'); title.set_wrap(True); title.set_xalign(0)
        header.append(title)
        self.picture = Gtk.Picture()
        set_animation_frame(self.picture, ASSETS / 'fc_01013D05_3149.webp')
        self.picture.set_can_shrink(True)
        self.picture.set_content_fit(Gtk.ContentFit.CONTAIN); self.picture.set_size_request(280, 220); page.append(self.picture)
        self.animation_timer = 0
        self.battery = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.battery.add_css_class('settings-battery'); self.battery.set_halign(Gtk.Align.CENTER)
        battery_icon = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        battery_icon.set_valign(Gtk.Align.CENTER)
        body = Gtk.Box(); body.add_css_class('settings-battery-body')
        self.battery_fill = Gtk.Box(); self.battery_fill.add_css_class('settings-battery-fill')
        self.battery_fill.set_halign(Gtk.Align.START); body.append(self.battery_fill)
        battery_icon.append(body)
        cap = Gtk.Box(); cap.add_css_class('settings-battery-cap'); cap.set_valign(Gtk.Align.CENTER)
        battery_icon.append(cap); self.battery.append(battery_icon)
        self.battery_text = Gtk.Label(); self.battery.append(self.battery_text)
        page.append(self.battery)
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16); card.add_css_class('settings-card'); page.append(card)
        modes = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8); modes.set_homogeneous(True); card.append(modes)
        self.buttons = {}
        self.mode_icons = {}
        for code, icon_name, label in [(2,'transparency','Transparency'), (1,'anc','Noise\ncancellation'), (0,'off','Off')]:
            button=Gtk.Button(); button.add_css_class('mode-button')
            content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            content.set_halign(Gtk.Align.CENTER)
            content.set_valign(Gtk.Align.CENTER)
            icon=Gtk.Picture(); icon.set_can_shrink(True); icon.set_size_request(30,30)
            icon.set_halign(Gtk.Align.CENTER)
            icon.set_valign(Gtk.Align.CENTER)
            icon.set_margin_top(8)
            icon.set_content_fit(Gtk.ContentFit.CONTAIN)
            icon.set_paintable(Gdk.Texture.new_for_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(str(ASSETS / f'mode-{icon_name}-normal.svg'), 128, 128, True)))
            content.append(icon)
            button.set_child(content)
            button.set_tooltip_text(label.replace('\n',' '))
            button.update_property([Gtk.AccessibleProperty.LABEL], [label.replace('\n',' ')])
            button.connect('clicked', lambda _, c=code: self.action('mode', c))
            modes.append(button); self.buttons[code]=button
            self.mode_icons[code]=(icon,icon_name)
        self.anc_controls=Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.append(self.anc_controls)
        row=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10); self.anc_controls.append(row)
        text=Gtk.Label(label='Adaptive ANC'); text.set_hexpand(True); text.set_xalign(0); text.add_css_class('settings-row'); row.append(text)
        self.adaptive_switch=Gtk.Switch(); self.adaptive_switch.set_valign(Gtk.Align.CENTER)
        self.adaptive_switch.connect('notify::active', self.change_adaptive); row.append(self.adaptive_switch)
        self.scale=NeoLevelSlider(lambda value: self.action('level', value))
        self.anc_controls.append(self.scale)
        marks=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL); marks.set_homogeneous(True); self.anc_controls.append(marks)
        for caption in ('Light','Balanced','Deep'):
            label=Gtk.Label(label=caption); label.add_css_class('settings-status'); marks.append(label)
        self.status=Gtk.Label(label=''); self.status.set_wrap(True); self.status.add_css_class('settings-status'); card.append(self.status)
        extra=Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0); extra.add_css_class('settings-card'); page.append(extra)
        for name in ('Dimensional audio','Audio','Gestures','Additional settings'):
            item=Gtk.Label(label=name+'   ·   Not available yet'); item.set_xalign(0); item.add_css_class('settings-row'); item.set_opacity(0.55); extra.append(item)
        self.disconnect=Gtk.Button(label='Disconnect')
        self.disconnect.add_css_class('settings-disconnect')
        self.disconnect.connect('clicked', lambda *_: self.action('disconnect', None))
        page.append(self.disconnect)
        self.refresh(None,None,False,False)

    def hide(self, *_):
        if self.animation_timer:
            GLib.source_remove(self.animation_timer)
            self.animation_timer = 0
        self.scale.dragging = False
        self.window.set_visible(False)
        return True

    def present(self):
        self.window.present()
        if self.animation_timer: GLib.source_remove(self.animation_timer)
        index = [0]
        def frame():
            try:
                set_animation_frame(self.picture, ASSETS / f'fc_01013D05_{3000 + index[0]}.webp')
            except GLib.Error:
                self.animation_timer = 0
                return GLib.SOURCE_REMOVE
            index[0] += 1
            if index[0] >= 150 or not self.window.get_visible():
                self.animation_timer = 0
                return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE
        frame()
        self.animation_timer = GLib.timeout_add(30, frame)

    def change_adaptive(self, widget, *_):
        if not self.syncing: self.action('adaptive', widget.get_active())

    def refresh(self, snapshot, battery, connected, busy, error=None):
        self.syncing=True
        self.battery.set_visible(battery is not None and connected)
        if battery is not None:
            self.battery_text.set_text(f'{battery}%')
            self.battery_fill.set_size_request(round(20 * max(0, min(100, battery)) / 100), 7)
        enabled=connected and snapshot is not None and not busy
        if snapshot is not None:
            self.mode=snapshot['mode']; self.adaptive=snapshot['adaptive']
            for code,button in self.buttons.items():
                if code==self.mode: button.add_css_class('active')
                else: button.remove_css_class('active')
                icon,icon_name=self.mode_icons[code]
                variant='selected' if code==self.mode else 'normal'
                icon.set_paintable(Gdk.Texture.new_for_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(str(ASSETS / f'mode-{icon_name}-{variant}.svg'), 128, 128, True)))
            self.adaptive_switch.set_active(self.adaptive)
            self.scale.set_value(snapshot['level'])
        for button in self.buttons.values(): button.set_sensitive(enabled)
        self.anc_controls.set_visible(self.mode==1)
        self.disconnect.set_sensitive(connected and not busy)
        self.adaptive_switch.set_sensitive(enabled and self.mode==1)
        self.scale.set_sensitive(enabled and self.mode==1 and not self.adaptive)
        message = error or ('Connecting to headphone controls…' if connected and snapshot is None else ('Connect headphones to use controls' if not connected else ''))
        self.status.set_text(message)
        self.status.set_visible(bool(message))
        self.syncing=False
