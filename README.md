# REDMI Headphones Neo for Linux

A desktop companion for REDMI Headphones Neo. It discovers nearby headphones,
shows Xiaomi's extracted popup animation, and offers Connect, battery status,
and a compact settings popup. It uses BlueZ and GTK 4 on Omarchy and GNOME.

## Features

- A discovery popup and Connect button for a nearby Neo; animations play once.
- On connection, the finding animation is followed by the connecting animation.
- A status-bar icon and settings popup with Off, Transparency, ANC, three ANC
  strengths and Adaptive ANC. The slider sends a change when released.
- A battery percentage when BlueZ reports one, plus Disconnect.
- Per-user installation and automatic start at login.
- An optional GNOME Quick Settings panel for connection, battery and Neo
  noise controls, plus settings and disconnect.

**Device coverage:** a China-firmware Neo was used on Omarchy; the user
confirmed noise modes and the slider. Fedora GNOME has not been tested. A
GNOME StatusNotifierItem/AppIndicator extension is needed for the tray icon;
the application launcher works without one. Linux Bluetooth discovery may
be slower than a phone and depends on the headset advertising nearby.

## Install

Clone the repository, enter it, and run:

```sh
git clone https://github.com/iliasgws/redmi-headphones-neo-linux.git
cd redmi-headphones-neo-linux
./install.sh --install-deps
```

The last command uses `sudo` to install dependencies on Fedora or
Arch/Omarchy, then installs the app for your user. If dependencies are already
installed, use `./install.sh` without the flag. Open **REDMI Headphones Neo**
from the application menu, or log out and back in to start discovery
implicitly at login.

### GNOME Quick Settings

The installer also copies the **REDMI Headphones Neo Controls** extension for
GNOME Shell 45–48. In GNOME, enable it in the Extensions app or run
`gnome-extensions enable neo-controls@earbuds.dev`. A logout and login may be
needed after installation or an update. The companion must be running; open
its application launcher if Quick Settings reports that the app is unavailable.
Open the Neo menu to refresh the controls. Battery is shown only when BlueZ
reports it. This extension has not yet been verified in a GNOME session.

### Manual dependencies

- Fedora: `bluez bluez-libs python3-gobject python3-cairo gtk4 librsvg2`
- Arch/Omarchy: `bluez bluez-utils python-gobject python-cairo gtk4 librsvg`
- A powered Bluetooth adapter, active BlueZ service, and a Wayland or X11 session.

The installer checks GTK, Python GI, Cairo, and the WebP/SVG image loaders.

## Update and remove

Open the Neo settings window and click **Update app**. The app checks its
installed Git checkout, downloads a fast-forward update, installs it, and
restarts. This needs Git and network access. It stops if the checkout has
local or untracked changes; commit or remove those changes first. If the
checkout was moved, reinstall from its new location to reconnect the button.

To update manually instead:

```sh
git pull
./install.sh
```

An already-running process continues using its loaded code; log out and back
in, or stop the old instance and open **REDMI Headphones Neo** again.
To uninstall, run `./uninstall.sh`. It removes this app's user files and
startup entry; stop any running instance separately or log out.

## Troubleshooting

- **No discovery popup:** check that Bluetooth is on, the Neo is awake and
  nearby, and the headphones are in pairing mode for first use. Existing
  paired-device entries alone do not prove presence. Open the launcher to
  access an already known Neo.
- **Can't connect or control settings:** pair through desktop Bluetooth
  settings if needed. A phone or another app can occupy the Neo's separate
  control channel; close it or disconnect the phone, then reopen Settings.
- **No tray icon:** the desktop needs a StatusNotifierItem watcher (GNOME
  requires a compatible extension). The launcher is an alternative.
- **No battery:** the app only displays a percentage when BlueZ supplies it.
- **Bluetooth changes:** the app does not connect automatically; Connect is
  user initiated. System pairing may still prompt for confirmation.

The unsupported sections in Settings are placeholders. The failure popup is a
standalone visual demo (`python3 demo_failure.py`), not the real failure flow.

## For contributors and coding agents

Start with [AGENTS.md](AGENTS.md), then [architecture](docs/ARCHITECTURE.md)
and [operations](docs/OPERATIONS.md). The [asset notice](ASSETS.md) describes
the source and redistribution limitations of the included artwork.

This project is not affiliated with Xiaomi or Apple. No code license is
specified; see [ASSETS.md](ASSETS.md) before sharing any artwork.
