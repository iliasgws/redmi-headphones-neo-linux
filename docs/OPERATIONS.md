# Development and operations

Run `./install.sh --help` for installer options. `./install.sh` installs into
`~/.local/share/neo-popup`, creates `~/.config/autostart/neo-popup.desktop`
and `~/.local/share/applications/neo-popup.desktop`. It does not require root
unless `--install-deps` is selected. `./uninstall.sh` removes those paths.

For a foreground run in a graphical session:

```sh
python3 neo_popup.py
```

A second invocation with `--show` asks the existing instance to display a
known Neo. `python3 demo_failure.py` opens a separate visual mock without
sending Bluetooth commands. It does not represent the production error flow.
The app currently does not expose an in-app quit command; closing a window hides
it while discovery continues. End the process or log out to stop discovery.

The settings surface draws rounded corners itself. Hyprland can also draw its
own square border; on Hyprland 0.55+ an optional compositor rule removes that
border and rounds only the settings window:

```lua
hl.window_rule({ match = { class = "^dev[.]earbuds[.]NeoPopup$", title = "^Neo Headphones Settings$" }, rounding = 20, border_size = 0 })
```

Place the rule in your Hyprland configuration and reload it. Hyprland rule
syntax varies by version; consult the documentation for your installed version.

For a local user service started by an operator, use the operator's actual unit
name with `systemctl --user` / `journalctl --user`; the installer does not
create a systemd unit. Autostart relies on the desktop session. Avoid copying
logs, phone-specific Bluetooth traces, serial numbers or device addresses into
issues or commits.

## Verification record

- Omarchy: the popup and tray registration were observed; the user confirmed
  Off/ANC/Transparency and the ANC slider's release behavior with a Neo.
- BlueZ battery percentage was observed on the user's connected Neo. This is
  optional and does not establish availability on other Bluetooth stacks.
- Fedora GNOME, tray extension behavior, first pairing, and the latest animation
  sequence have not been verified on a separate machine. The failure demo is
  not a tested production failure UI.
