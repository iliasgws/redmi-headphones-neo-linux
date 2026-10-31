# Architecture and protocol map

## Runtime

The XDG autostart entry starts `neo_popup.py` in the graphical user session.
GTK's application ID provides a single instance. BlueZ objects and property
changes are observed over the system D-Bus; the app uses a shared discovery
session and recognizes Neo Bluetooth names. Discovery is best-effort and is
not an authenticated identity check. It never initiates a connection merely
because a device is seen. A user request calls `Device1.Pair` if needed and
then `Device1.Connect`. Battery comes only from BlueZ `Battery1.Percentage`.

The popup plays the original frame sequences from `assets/`: 1000–1059 at
32 ms per frame while finding/connecting, then 2000–2149 at 32 ms per frame
only after BlueZ says the device is connected. The sequence stops at the last
frame. The settings screen has its own once-only 3000–3149 animation.

`neo_tray.py` exposes a StatusNotifierItem over the user D-Bus. It relies on a
running tray watcher; stock GNOME may require an extension. Activation opens
settings. The app-menu launcher is independent of tray support.

The settings update button uses a separate worker and `neo_updater.py` to
check the checkout recorded by the installer. It validates the origin, refuses
local changes, pulls fast-forward only, and reinstalls if the installed revision
differs. A helper restarts the installed app after the old process exits. Update
status is returned to the GTK thread; Bluetooth controls have their own worker.

The optional GNOME Shell extension in `gnome-extension/` uses the session D-Bus
interface `dev.earbuds.NeoControls` at `/dev/earbuds/NeoControls`. `GetState`
and `StateChanged` report BlueZ connection/battery and the most recent control
snapshot; `Action` dispatches to the same serialized control worker as GTK.
Opening the menu requests a fresh snapshot. The bridge rejects invalid writes
and does not expose device addresses or initiate a connection.

## Controls

`neo_settings.py` uses GTK 4 and a Cairo slider. Pointer/touch dragging changes
only the local position; a device command is submitted after release. Keyboard
changes are explicit actions. Adaptive ANC disables manual strength.

Actions go to one `ThreadPoolExecutor` worker in `neo_popup.py`. Each action
opens an authenticated RFCOMM session, sends its command, reads the resulting
settings and closes the session. This avoids keeping the proprietary channel
open indefinitely, but another phone or app can still occupy it. UI callbacks
are returned to the GTK thread through `GLib.idle_add`.

`neo_protocol.py` resolves the FD2D service through libbluetooth SDP (with
optional `sdptool` fallback), performs RCSP mutual authentication, validates
VID `2717` and Neo PID `50F0` or `50FB`, and serializes request/reply frames.
The methods implemented for the Neo are:

| Function | RCSP command |
| --- | --- |
| Read settings | `F3`: config IDs `000B`, `0025` |
| Off / ANC / Transparency | `08`: `02 04` followed by `00` / `01` / `02` |
| ANC strength | `F2`: config `000B`, bytes `01 00` / `01 01` / `01 02` |
| Adaptive ANC | `F2`: config `0025`, one byte `00` / `01` |

These commands come from a capture of Xiaomi's app and have been exercised on
a China-firmware Neo. Other features are deliberately not implemented.

## Boundaries

Pairing and SDP depend on desktop Bluetooth services and a system pairing
agent. Audio connection does not prove that the separate control socket is
available. Errors can also result from proximity, radio state, another host,
or missing access to BlueZ. Full behavior has not been verified on Fedora
GNOME or with every Neo variant. Never generalize a protocol write to another
model based only on a similar UI.
