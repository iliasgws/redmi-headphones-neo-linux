#!/usr/bin/env python3
"""Local BlueZ discovery popup for the REDMI Headphones Neo."""
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gio, GLib, Gtk, Gdk
from neo_tray import NeoTray
from neo_settings import NeoSettings

BLUEZ = 'org.bluez'
ROOT = '/'
OBJECT_MANAGER = 'org.freedesktop.DBus.ObjectManager'
PROPERTIES = 'org.freedesktop.DBus.Properties'
DEVICE = 'org.bluez.Device1'
ADAPTER = 'org.bluez.Adapter1'
BATTERY = 'org.bluez.Battery1'
ASSETS = Path(__file__).resolve().parent / 'assets'
NAMES = ('redmi headphones neo', 'redmi 头戴降噪耳机', 'redmi 頭戴降噪耳機')

class NeoPopup(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='dev.earbuds.NeoPopup', flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.bus = None
        self.objects = {}
        self.adapters = set()
        self.current = None
        self.last_shown = {}
        self.closed_at = {}
        self.last_connected = {}
        self.animation_id = 0
        self.animation_key = None
        self.chain_connecting = False
        self.pairing = False
        self.preview = '--preview' in sys.argv
        self.tray = None
        self.settings = None
        self.controls = None
        self.controls_path = None
        self.controls_snapshot = None
        self.controls_busy = False
        self.control_generation = 0
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix='neo-controls')

    def do_command_line(self, command_line):
        self.activate()
        if '--show' in command_line.get_arguments():
            if self.current:
                connected = self.objects.get(self.current, {}).get(DEVICE, {}).get('Connected')
                self.show_device(self.current, 'connected' if connected else 'find')
            else:
                candidate = next((path for path in self.objects if self.is_neo(path)), None)
                if candidate:
                    connected = self.objects[candidate][DEVICE].get('Connected')
                    self.show_device(candidate, 'connected' if connected else 'find')
                else:
                    self.status.set_text('Turn on the headphones and put them in pairing mode to find them.')
                    self.subtitle.set_text('Looking for headphones')
                    self.button.set_sensitive(False)
                    self.window.present()
        return 0

    def do_activate(self):
        if self.bus is not None:
            if self.window.get_visible(): self.window.present()
            return
        self.hold()
        self.build_window()
        self.tray = NeoTray(self.open_settings)
        if self.preview:
            self.current = '/preview'
            self.objects[self.current] = {DEVICE: {'Name': 'REDMI Headphones Neo', 'Connected': False, 'Paired': True}, BATTERY: {'Percentage': 85}}
            self.show_device(self.current, 'find')
            return
        try:
            self.bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            self.bus.signal_subscribe(BLUEZ, OBJECT_MANAGER, None, None, None, Gio.DBusSignalFlags.NONE, self.object_signal)
            self.bus.signal_subscribe(BLUEZ, PROPERTIES, 'PropertiesChanged', None, None, Gio.DBusSignalFlags.NONE, self.property_signal)
            result = self.bus.call_sync(BLUEZ, ROOT, OBJECT_MANAGER, 'GetManagedObjects', None, GLib.VariantType.new('(a{oa{sa{sv}}})'), Gio.DBusCallFlags.NONE, 5000, None)
            self.objects = result.unpack()[0]
            for path, interfaces in self.objects.items():
                if ADAPTER in interfaces: self.start_discovery(path)
                if DEVICE in interfaces: self.last_connected[path] = bool(interfaces[DEVICE].get('Connected'))
        except GLib.Error as exc:
            self.status.set_text('Bluetooth service unavailable. Open Bluetooth settings and try again.')
            self.window.present()
            print('Neo popup: Bluetooth service unavailable:', exc.message, file=sys.stderr)

    def build_window(self):
        self.window = Gtk.ApplicationWindow(application=self, title='REDMI Headphones Neo')
        self.window.set_default_size(400, 480)
        self.window.set_resizable(False)
        self.window.set_decorated(False)
        self.window.add_css_class('neo-window')
        self.window.connect('close-request', self.dismiss)
        css = Gtk.CssProvider()
        css.load_from_data(b'''
            window.neo-window { background: transparent; }
            .neo-card { background: #fff; color: #181818; border-radius: 34px; }
            .neo-title { color: #101010; font-size: 20px; font-weight: 600; }
            .neo-close { min-width: 30px; min-height: 30px; padding: 0; border-radius: 99px; background: #f1f1f1; color: #8b8b8b; box-shadow: none; border: none; font-size: 22px; }
            .neo-status { color: #242424; font-size: 14px; }
            .neo-button { min-height: 52px; border-radius: 16px; border: none; box-shadow: none; background: #ededed; color: #2d2d2d; font-size: 18px; }
            .neo-button:hover { background: #e1e1e1; }
            .battery-body { border: 2px solid #292929; border-radius: 4px; padding: 2px; min-width: 22px; min-height: 8px; }
            .battery-fill { background: #37ce78; border-radius: 1px; min-height: 6px; }
            .battery-cap { background: #292929; border-radius: 0 2px 2px 0; min-width: 2px; min-height: 5px; }
        ''')
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer.add_css_class('neo-card')
        outer.set_margin_top(4); outer.set_margin_bottom(4); outer.set_margin_start(4); outer.set_margin_end(4)
        self.window.set_child(outer)
        header = Gtk.CenterBox()
        header.set_margin_top(22); header.set_margin_start(20); header.set_margin_end(20)
        outer.append(header)
        spacer = Gtk.Box(); spacer.set_size_request(32, 32)
        header.set_start_widget(spacer)
        title = Gtk.Label(label='REDMI Headphones Neo')
        title.add_css_class('neo-title')
        header.set_center_widget(title)
        close = Gtk.Button(label='×'); close.add_css_class('neo-close')
        close.set_tooltip_text('Close')
        close.connect('clicked', lambda *_: self.dismiss(self.window))
        header.set_end_widget(close)
        self.subtitle = Gtk.Label(label='Headphones nearby')
        self.subtitle.add_css_class('neo-status')
        self.subtitle.set_visible(False)
        outer.append(self.subtitle)
        self.picture = Gtk.Picture()
        self.picture.set_size_request(300, 275)
        self.picture.set_vexpand(True)
        self.picture.set_can_shrink(True)
        self.picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        outer.append(self.picture)
        self.battery_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.battery_row.set_halign(Gtk.Align.CENTER)
        self.battery_row.set_valign(Gtk.Align.CENTER)
        self.battery_row.set_margin_bottom(20)
        outer.append(self.battery_row)
        battery_label = Gtk.Label(label='Battery'); battery_label.add_css_class('neo-status')
        self.battery_row.append(battery_label)
        icon = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        icon.set_valign(Gtk.Align.CENTER)
        self.battery_row.append(icon)
        body = Gtk.Box(); body.add_css_class('battery-body')
        self.battery_fill = Gtk.Box(); self.battery_fill.add_css_class('battery-fill')
        self.battery_fill.set_halign(Gtk.Align.START)
        body.append(self.battery_fill); icon.append(body)
        cap = Gtk.Box(); cap.add_css_class('battery-cap'); cap.set_valign(Gtk.Align.CENTER); icon.append(cap)
        self.battery_percent = Gtk.Label(); self.battery_percent.add_css_class('neo-status')
        self.battery_row.append(self.battery_percent)
        self.status = Gtk.Label(label='')
        self.status.add_css_class('neo-status')
        self.status.set_wrap(True)
        self.status.set_justify(Gtk.Justification.CENTER)
        self.status.set_margin_top(16)
        self.status.set_margin_bottom(20)
        outer.append(self.status)
        self.button = Gtk.Button(label='Connect')
        self.button.add_css_class('neo-button')
        self.button.set_margin_start(32); self.button.set_margin_end(32); self.button.set_margin_bottom(30)
        self.button.connect('clicked', self.on_connect)
        outer.append(self.button)

    def dismiss(self, *_):
        if self.current: self.closed_at[self.current] = time.monotonic()
        self.stop_animation()
        self.window.set_visible(False)
        return True

    def start_discovery(self, path):
        if path in self.adapters: return
        self.adapters.add(path)
        # A discovery filter disables BlueZ's default RSSI change threshold,
        # allowing known headphones to be reported promptly when seen again.
        options = {'DuplicateData': GLib.Variant('b', True)}
        self.bus.call(BLUEZ, path, ADAPTER, 'SetDiscoveryFilter',
                      GLib.Variant('(a{sv})', (options,)), None,
                      Gio.DBusCallFlags.NONE, 10000, None, self.filter_done, path)

    def filter_done(self, bus, result, path):
        try: bus.call_finish(result)
        except GLib.Error as exc:
            print('Neo popup: using default discovery:', exc.message, file=sys.stderr)
        self.bus.call(BLUEZ, path, ADAPTER, 'StartDiscovery', None, None, Gio.DBusCallFlags.NONE, 10000, None, self.discovery_done, path)

    def discovery_done(self, bus, result, path):
        try: bus.call_finish(result)
        except GLib.Error as exc:
            self.adapters.discard(path)
            print('Neo popup: discovery unavailable:', exc.message, file=sys.stderr)

    def object_signal(self, bus, sender, path, interface, signal, parameters):
        args = parameters.unpack()
        if signal == 'InterfacesAdded':
            object_path, interfaces = args
            self.objects.setdefault(object_path, {}).update(interfaces)
            if ADAPTER in interfaces: self.start_discovery(object_path)
            if DEVICE in interfaces: self.consider(object_path, discovered=True)
            if object_path == self.current: self.refresh()
        elif signal == 'InterfacesRemoved':
            object_path, interfaces = args
            if object_path in self.objects:
                for name in interfaces: self.objects[object_path].pop(name, None)
            if ADAPTER in interfaces: self.adapters.discard(object_path)

    def property_signal(self, bus, sender, path, interface, signal, parameters):
        iface, changed, invalidated = parameters.unpack()
        if iface not in (DEVICE, ADAPTER, BATTERY): return
        props = self.objects.setdefault(path, {}).setdefault(iface, {})
        props.update(changed)
        for key in invalidated: props.pop(key, None)
        if iface == ADAPTER and 'Powered' in changed:
            if changed['Powered']: self.start_discovery(path)
            else: self.adapters.discard(path)
        if iface == DEVICE:
            if 'Connected' in changed:
                connected = bool(changed['Connected'])
                was = self.last_connected.get(path, False)
                self.last_connected[path] = connected
                if connected and not was and self.is_neo(path): self.show_device(path, 'connected')
                elif not connected and was and self.current == path:
                    self.controls_snapshot = None
                    if self.window.get_visible(): self.refresh()
                    self.update_settings()
            seen = any(key in changed for key in ('RSSI', 'ManufacturerData', 'ServiceData'))
            if seen or 'Name' in changed:
                self.consider(path, discovered=seen or ('Name' in changed and 'RSSI' in props))
        if path == self.current:
            if self.window.get_visible(): self.refresh()
            self.update_settings()

    def is_neo(self, path):
        props = self.objects.get(path, {}).get(DEVICE, {})
        names = [str(props.get('Name', '')).casefold(), str(props.get('Alias', '')).casefold()]
        return any(name in text for text in names for name in NAMES)

    def consider(self, path, discovered=False):
        if not discovered or not self.is_neo(path): return
        props = self.objects[path][DEVICE]
        if props.get('Connected') or self.window.get_visible(): return
        now = time.monotonic()
        if now - self.last_shown.get(path, 0) < 15 or now - self.closed_at.get(path, 0) < 15: return
        self.show_device(path, 'find')

    def show_device(self, path, animation):
        continuing_find = self.current == path and self.animation_key == 'find' and self.animation_id != 0
        self.current = path
        self.last_shown[path] = time.monotonic()
        self.refresh()
        self.window.present()
        if animation == 'connected':
            if not continuing_find:
                self.stop_animation()
                self.animate('find')
            self.queue_connected_animation()
        else:
            self.chain_connecting = False
            self.animate('find')

    def queue_connected_animation(self):
        if not self.current or not self.objects.get(self.current, {}).get(DEVICE, {}).get('Connected'):
            return
        if self.animation_key == 'connecting': return
        if self.animation_key == 'find' and self.animation_id:
            self.chain_connecting = True
        else:
            self.chain_connecting = False
            self.animate('connecting')

    def refresh(self):
        if not self.current: return
        interfaces = self.objects.get(self.current, {})
        device = interfaces.get(DEVICE, {})
        battery = interfaces.get(BATTERY, {}).get('Percentage')
        connected = bool(device.get('Connected'))
        paired = bool(device.get('Paired'))
        self.subtitle.set_text('Connected' if connected else 'Headphones nearby')
        self.battery_row.set_visible(paired and connected and battery is not None)
        self.status.set_visible(not connected)
        self.status.set_text('Ready to connect' if not connected else '')
        if battery is not None:
            self.battery_percent.set_text(f'{battery}%')
            self.battery_fill.set_size_request(round(20 * max(0, min(100, battery)) / 100), 6)
        self.button.set_label('Settings' if connected else 'Connect')
        self.button.set_sensitive(not self.pairing)
        if self.settings is not None and self.settings.window.get_visible():
            self.settings.refresh(self.controls_snapshot,battery,connected,self.controls_busy)

    def on_connect(self, *_):
        if not self.current or self.pairing: return
        if self.objects.get(self.current, {}).get(DEVICE, {}).get('Connected'):
            self.open_settings()
            return
        if self.preview:
            self.status.set_text('Preview mode')
            return
        device = self.objects.get(self.current, {}).get(DEVICE, {})
        self.pairing = True
        self.button.set_sensitive(False)
        self.status.set_text('Connecting…')
        self.chain_connecting = False
        self.stop_animation()
        self.animate('find')
        if not device.get('Paired'):
            self.status.set_text('Pairing… Confirm any Bluetooth pairing request.')
            self.call_device('Pair', self.pair_done)
        else: self.call_device('Connect', self.connect_done)

    def open_settings(self):
        candidates = [p for p in self.objects if self.is_neo(p)]
        connected = next((p for p in candidates if self.objects[p][DEVICE].get('Connected')), None)
        if connected: self.current = connected
        elif not self.current: self.current = next(iter(candidates), None)
        if self.settings is None: self.settings = NeoSettings(self, self.control_action)
        self.window.set_visible(False)
        self.stop_animation()
        self.settings.present()
        self.update_settings()
        if self.current and self.objects.get(self.current, {}).get(DEVICE, {}).get('Connected'):
            self.load_controls()

    def update_settings(self, error=None):
        if self.settings is None: return
        interfaces = self.objects.get(self.current, {}) if self.current else {}
        connected = bool(interfaces.get(DEVICE, {}).get('Connected'))
        battery = interfaces.get(BATTERY, {}).get('Percentage')
        self.settings.refresh(self.controls_snapshot, battery, connected, self.controls_busy, error)

    def load_controls(self):
        self.run_control('read', None)

    def control_action(self, action, value):
        if action in ('mode', 'level', 'adaptive'):
            self.run_control(action, value)
        elif action == 'back':
            if self.settings: self.settings.hide()
            if self.current:
                connected = self.objects.get(self.current, {}).get(DEVICE, {}).get('Connected')
                self.show_device(self.current, 'connected' if connected else 'find')
            else: self.window.present()
        elif action == 'disconnect' and self.current and not self.controls_busy:
            self.bus.call(BLUEZ, self.current, DEVICE, 'Disconnect', None, None,
                          Gio.DBusCallFlags.NONE, 10000, None, self.disconnect_done, self.current)

    def disconnect_done(self, bus, result, path):
        try: bus.call_finish(result)
        except GLib.Error:
            if path == self.current: self.update_settings('Could not disconnect. Try Bluetooth settings.')

    def run_control(self, action, value):
        if self.controls_busy or not self.current: return
        device = self.objects.get(self.current, {}).get(DEVICE, {})
        address = device.get('Address')
        if not address or not device.get('Connected'):
            self.update_settings('Connect the headphones to use these controls.')
            return
        path = self.current
        self.controls_busy = True
        self.update_settings()
        def work():
            from neo_protocol import NeoProtocol
            with NeoProtocol.connect(address) as session:
                if action == 'mode': session.set_noise_mode(value)
                elif action == 'level': session.set_noise_level(value)
                elif action == 'adaptive': session.set_adaptive_anc(value)
                result = session.read_settings()
                return {'mode': result.noise_mode, 'level': result.noise_level, 'adaptive': result.adaptive_anc}
        future = self.worker.submit(work)
        def completed(done):
            try:
                result, error = done.result(), None
            except Exception as exc:
                result, error = None, type(exc).__name__
            GLib.idle_add(self.control_finished, path, result, error)
        future.add_done_callback(completed)

    def control_finished(self, path, result, error):
        self.controls_busy = False
        if path != self.current: return GLib.SOURCE_REMOVE
        if result is not None: self.controls_snapshot = result
        if error:
            self.controls_snapshot = None
            self.update_settings('Could not access Neo controls. Close other headphone control apps and reopen Settings.')
            print('Neo popup: control session failed:', error, file=sys.stderr)
        else: self.update_settings()
        return GLib.SOURCE_REMOVE

    def call_device(self, method, callback):
        self.bus.call(BLUEZ, self.current, DEVICE, method, None, None, Gio.DBusCallFlags.NONE, 45000, None, callback, self.current)

    def pair_done(self, bus, result, path):
        try: bus.call_finish(result)
        except GLib.Error as exc:
            self.failed(exc); return
        if path != self.current: self.pairing = False; return
        self.call_device('Connect', self.connect_done)

    def connect_done(self, bus, result, path):
        self.pairing = False
        try:
            bus.call_finish(result)
            if path == self.current:
                self.status.set_text('Connected')
                self.queue_connected_animation()
        except GLib.Error as exc:
            if 'AlreadyConnected' in exc.message: self.refresh(); return
            self.failed(exc)

    def failed(self, exc):
        self.pairing = False
        self.button.set_sensitive(True)
        self.status.set_text('Could not connect. Check Bluetooth settings and try again.')
        self.chain_connecting = False
        self.animate('find')
        print('Neo popup: connection failed:', exc.message, file=sys.stderr)

    def stop_animation(self):
        if self.animation_id:
            GLib.source_remove(self.animation_id)
            self.animation_id = 0
        self.animation_key = None

    def animate(self, name):
        if self.animation_key == name: return
        self.stop_animation()
        self.animation_key = name
        start, count, delay = {'find': (1000, 60, 32), 'connecting': (2000, 150, 32), 'connected': (3000, 150, 30)}[name]
        index = [0]
        def frame():
            if not self.window.get_visible() and index[0] > 0:
                self.animation_id = 0
                return GLib.SOURCE_REMOVE
            try:
                self.picture.set_paintable(Gdk.Texture.new_from_filename(str(ASSETS / f'fc_01013D05_{start + index[0]}.webp')))
            except GLib.Error:
                self.animation_id = 0
                return GLib.SOURCE_REMOVE
            index[0] += 1
            if index[0] >= count:
                self.animation_id = 0
                if name == 'find' and self.chain_connecting:
                    self.chain_connecting = False
                    GLib.idle_add(self.queue_connected_animation)
                return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE
        frame()
        self.animation_id = GLib.timeout_add(delay, frame)

    def do_shutdown(self):
        self.stop_animation()
        if self.tray: self.tray.close()
        self.worker.shutdown(wait=False, cancel_futures=True)
        if self.bus:
            for path in list(self.adapters):
                self.bus.call(BLUEZ, path, ADAPTER, 'StopDiscovery', None, None, Gio.DBusCallFlags.NONE, 5000, None, None, None)
        Gtk.Application.do_shutdown(self)

if __name__ == '__main__':
    raise SystemExit(NeoPopup().run(sys.argv))
