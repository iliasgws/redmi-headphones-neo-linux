"""StatusNotifierItem for desktops with a system tray."""
from gi.repository import Gio, GLib

XML = '''<node><interface name="org.kde.StatusNotifierItem">
<method name="Activate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="SecondaryActivate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="ContextMenu"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="Scroll"><arg type="i" direction="in"/><arg type="s" direction="in"/></method>
<property name="Category" type="s" access="read"/><property name="Id" type="s" access="read"/>
<property name="Title" type="s" access="read"/><property name="Status" type="s" access="read"/>
<property name="IconName" type="s" access="read"/><property name="ItemIsMenu" type="b" access="read"/>
<signal name="NewStatus"><arg type="s"/></signal><signal name="NewIcon"/>
</interface></node>'''

class NeoTray:
    def __init__(self, activate):
        self.activate = activate
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.node = Gio.DBusNodeInfo.new_for_xml(XML)
        self.registration = self.bus.register_object('/StatusNotifierItem', self.node.interfaces[0], self.method, self.get_property, None)
        self.watch = Gio.bus_watch_name_on_connection(self.bus, 'org.kde.StatusNotifierWatcher', Gio.BusNameWatcherFlags.NONE, self.watcher_appeared, None)

    def watcher_appeared(self, bus, name, owner):
        bus.call('org.kde.StatusNotifierWatcher', '/StatusNotifierWatcher', 'org.kde.StatusNotifierWatcher',
                 'RegisterStatusNotifierItem', GLib.Variant('(s)', (self.bus.get_unique_name(),)),
                 None, Gio.DBusCallFlags.NONE, 5000, None, None, None)

    def method(self, bus, sender, path, iface, method, parameters, invocation):
        if method in ('Activate', 'SecondaryActivate', 'ContextMenu'):
            self.activate()
        invocation.return_value(None)

    def get_property(self, bus, sender, path, iface, name):
        values = {'Category': 'Hardware', 'Id': 'neo-headphones', 'Title': 'REDMI Headphones Neo',
                  'Status': 'Active', 'IconName': 'audio-headphones-symbolic'}
        if name == 'ItemIsMenu': return GLib.Variant('b', False)
        return GLib.Variant('s', values.get(name, ''))

    def close(self):
        Gio.bus_unwatch_name(self.watch)
        self.bus.unregister_object(self.registration)
