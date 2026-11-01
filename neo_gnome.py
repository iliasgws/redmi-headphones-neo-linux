"""Session D-Bus bridge for the optional GNOME Quick Settings extension."""
from gi.repository import Gio, GLib

NAME = 'dev.earbuds.NeoControls'
PATH = '/dev/earbuds/NeoControls'
XML = '''<node><interface name="dev.earbuds.NeoControls">
<method name="GetState"><arg type="a{sv}" direction="out"/></method>
<method name="Action"><arg type="s" direction="in"/><arg type="v" direction="in"/></method>
<signal name="StateChanged"><arg type="a{sv}"/></signal>
</interface></node>'''

class NeoGnomeBridge:
    def __init__(self, app):
        self.app = app
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.node = Gio.DBusNodeInfo.new_for_xml(XML)
        self.registration = self.bus.register_object(PATH, self.node.interfaces[0], self.method, None, None)
        self.owner = Gio.bus_own_name_on_connection(self.bus, NAME, Gio.BusNameOwnerFlags.NONE, None, None)

    def state(self):
        app = self.app
        # Prefer an active Neo over a stale discovery selection.
        connected_path = next((p for p, obj in app.objects.items()
                               if app.is_neo(p) and obj.get('org.bluez.Device1', {}).get('Connected')), None)
        path = connected_path or app.current
        interfaces = app.objects.get(path, {}) if path else {}
        connected = bool(interfaces.get('org.bluez.Device1', {}).get('Connected'))
        battery = interfaces.get('org.bluez.Battery1', {}).get('Percentage')
        snapshot = app.controls_snapshot if connected and path == app.current else None
        fields = {
            'connected': ('b', connected), 'battery': ('i', int(battery) if battery is not None else -1),
            'mode': ('i', snapshot['mode'] if snapshot else -1),
            'level': ('i', snapshot['level'] if snapshot else -1),
            'adaptive': ('b', snapshot['adaptive'] if snapshot else False),
            'available': ('b', bool(snapshot)), 'busy': ('b', app.controls_busy),
            'error': ('s', app.controls_error or ''),
        }
        return {key: GLib.Variant(kind, value) for key, (kind, value) in fields.items()}

    def emit(self):
        self.bus.emit_signal(None, PATH, NAME, 'StateChanged', GLib.Variant('(a{sv})', (self.state(),)))

    def method(self, bus, sender, path, iface, method, parameters, invocation):
        if method == 'GetState':
            invocation.return_value(GLib.Variant('(a{sv})', (self.state(),)))
            return
        if method != 'Action':
            invocation.return_dbus_error(NAME + '.InvalidAction', 'Unknown method')
            return
        action, value = parameters.unpack()
        if action in ('mode', 'level') and (type(value) is not int or value not in (0, 1, 2)):
            invocation.return_dbus_error(NAME + '.InvalidAction', 'Invalid value')
            return
        if action == 'adaptive' and type(value) is not bool:
            invocation.return_dbus_error(NAME + '.InvalidAction', 'Invalid value')
            return
        if action not in ('refresh', 'settings', 'disconnect', 'mode', 'level', 'adaptive'):
            invocation.return_dbus_error(NAME + '.InvalidAction', 'Unknown action')
            return
        app = self.app
        connected_path = next((p for p, obj in app.objects.items()
                               if app.is_neo(p) and obj.get('org.bluez.Device1', {}).get('Connected')), None)
        if connected_path and connected_path != app.current:
            app.current = connected_path
            app.controls_snapshot = None
        if action in ('mode', 'level', 'adaptive', 'disconnect'):
            if not connected_path:
                invocation.return_dbus_error(NAME + '.Disconnected', 'The headphones are disconnected.')
                return
            if app.controls_busy:
                invocation.return_dbus_error(NAME + '.Busy', 'Headphone controls are busy.')
                return
            if action != 'disconnect' and not app.controls_snapshot:
                invocation.return_dbus_error(NAME + '.Unavailable', 'Headphone controls have not been read yet.')
                return
        if action == 'settings': app.open_settings()
        elif action == 'refresh':
            if connected_path: app.load_controls()
            else: self.emit()
        elif action in ('mode', 'level', 'adaptive'):
            app.run_control(action, value)
        elif action == 'disconnect' and connected_path:
            app.control_action(action, None)
        invocation.return_value(None)

    def close(self):
        Gio.bus_unown_name(self.owner)
        self.bus.unregister_object(self.registration)
