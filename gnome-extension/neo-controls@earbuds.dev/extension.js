import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const BUS = 'dev.earbuds.NeoControls';
const PATH = '/dev/earbuds/NeoControls';
const IFACE = 'dev.earbuds.NeoControls';

const NeoIndicator = GObject.registerClass(class NeoIndicator extends PanelMenu.Button {
    _init() {
        super._init(0.0, 'REDMI Headphones Neo');
        this._state = {available: false, connected: false, battery: -1, mode: -1,
            level: -1, adaptive: false, busy: false, error: ''};
        this._icon = new St.Icon({icon_name: 'audio-headphones-symbolic',
            style_class: 'system-status-icon'});
        this.add_child(this._icon);
        this._title = new PopupMenu.PopupMenuItem('REDMI Headphones Neo', {reactive: false});
        this.menu.addMenuItem(this._title);
        this._status = new PopupMenu.PopupMenuItem('Unavailable', {reactive: false});
        this.menu.addMenuItem(this._status);
        this._modes = [];
        for (const [name, value] of [['Off', 0], ['Noise cancellation', 1], ['Transparency', 2]]) {
            const item = new PopupMenu.PopupMenuItem(name);
            item.connect('activate', () => this._action('mode', new GLib.Variant('i', value)));
            this.menu.addMenuItem(item);
            this._modes.push(item);
        }
        this._adaptive = new PopupMenu.PopupSwitchMenuItem('Adaptive ANC', false);
        this._adaptive.connect('toggled', (_item, enabled) =>
            this._action('adaptive', new GLib.Variant('b', enabled)));
        this.menu.addMenuItem(this._adaptive);
        this._levels = [];
        for (const [name, value] of [['Light', 0], ['Balanced', 1], ['Deep', 2]]) {
            const item = new PopupMenu.PopupMenuItem(name);
            item.connect('activate', () => this._action('level', new GLib.Variant('i', value)));
            this.menu.addMenuItem(item);
            this._levels.push(item);
        }
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        this._settings = new PopupMenu.PopupMenuItem('Open settings');
        this._settings.connect('activate', () => this._action('settings'));
        this.menu.addMenuItem(this._settings);
        this._disconnect = new PopupMenu.PopupMenuItem('Disconnect');
        this._disconnect.connect('activate', () => this._action('disconnect'));
        this.menu.addMenuItem(this._disconnect);
        this.menu.connect('open-state-changed', (_menu, open) => {
            if (open) {
                this._action('refresh');
                this._refresh();
            }
        });
        this._render();
        Gio.DBusProxy.new_for_bus(Gio.BusType.SESSION, Gio.DBusProxyFlags.DO_NOT_AUTO_START,
            null, BUS, PATH, IFACE, null, (_source, result) => {
                if (this._destroyed)
                    return;
                try {
                    this._proxy = Gio.DBusProxy.new_for_bus_finish(result);
                    this._signalId = this._proxy.connect('g-signal', (_proxy, _sender, signal, params) => {
                        if (signal === 'StateChanged')
                            this._setState(params.deep_unpack()[0]);
                    });
                    this._ownerId = this._proxy.connect('notify::g-name-owner', () => {
                        if (this._proxy.g_name_owner)
                            this._refresh();
                        else {
                            this._state = {...this._state, available: false, connected: false};
                            this._render();
                        }
                    });
                    this._refresh();
                } catch (e) {
                    console.error(`Neo controls: ${e.message}`);
                }
            });
    }

    _setState(state) {
        for (const [key, value] of Object.entries(state))
            this._state[key] = value instanceof GLib.Variant ? value.deep_unpack() : value;
        this._render();
    }

    _call(method, parameters, callback = null) {
        if (!this._proxy?.g_name_owner)
            return;
        this._proxy.call(method, parameters, Gio.DBusCallFlags.NONE, 15000, null,
            (proxy, result) => {
                if (this._destroyed)
                    return;
                try {
                    const response = proxy.call_finish(result);
                    callback?.(response);
                } catch (e) {
                    if (method === 'Action') {
                        this._refresh(() => {
                            this._state.error = 'Could not apply the change; try again';
                            this._render();
                        });
                    } else {
                        this._state.error = 'Could not contact the Neo app';
                        this._render();
                    }
                    console.error(`Neo controls: ${e.message}`);
                }
            });
    }

    _action(name, value = new GLib.Variant('s', '')) {
        this._call('Action', new GLib.Variant('(sv)', [name, value]));
    }

    _refresh(after = null) {
        this._call('GetState', null, response => {
            this._setState(response.deep_unpack()[0]);
            after?.();
        });
    }

    _render() {
        const s = this._state;
        const connected = s.connected;
        const enabled = connected && s.available && !s.busy;
        const status = !this._proxy?.g_name_owner ? 'App unavailable' : !connected ? 'Disconnected' :
            s.battery >= 0 ? `${s.battery}%` : 'Connected';
        this._status.label.text = s.error || (s.busy ? 'Working…' : status);
        this._modes.forEach((item, value) => {
            item.visible = connected;
            item.setSensitive(enabled);
            item.setOrnament(s.mode === value ? PopupMenu.Ornament.DOT : PopupMenu.Ornament.NONE);
        });
        this._adaptive.visible = connected && s.mode === 1;
        this._adaptive.setSensitive(enabled);
        this._adaptive.setToggleState(!!s.adaptive);
        this._levels.forEach((item, value) => {
            item.visible = connected && s.mode === 1;
            item.setSensitive(enabled && !s.adaptive);
            item.setOrnament(s.level === value ? PopupMenu.Ornament.DOT : PopupMenu.Ornament.NONE);
        });
        this._settings.setSensitive(!!this._proxy?.g_name_owner);
        this._disconnect.visible = connected;
        this._disconnect.setSensitive(connected && !s.busy);
    }

    destroy() {
        this._destroyed = true;
        if (this._proxy) {
            if (this._signalId) this._proxy.disconnect(this._signalId);
            if (this._ownerId) this._proxy.disconnect(this._ownerId);
        }
        super.destroy();
    }
});

export default class NeoControlsExtension extends Extension {
    enable() {
        this._indicator = new NeoIndicator();
        Main.panel.addToStatusArea('neo-headphones', this._indicator);
    }

    disable() {
        this._indicator?.destroy();
        this._indicator = null;
    }
}
