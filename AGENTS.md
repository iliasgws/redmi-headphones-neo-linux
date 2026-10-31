# Guidance for coding agents

## Project and scope

This is a Linux GTK 4 / PyGObject companion for REDMI Headphones Neo, not the
Android application or a general Xiaomi device driver. Read README.md and
`docs/ARCHITECTURE.md` before changing behavior. The settings popup, automatic
discovery, and tray icon share one long-running user-session process.

## Map

- `neo_popup.py`: app lifecycle, BlueZ discovery, pairing/connect, popup,
  animation sequencing, worker coordination, and settings actions.
- `neo_settings.py`: GTK settings UI and the release-to-commit ANC slider.
- `neo_protocol.py`: serialized RFCOMM framing, authentication, SDP, and Neo
  control commands. Device identities are checked before settings commands.
- `neo_tray.py`: StatusNotifierItem registration and activation.
- `demo_failure.py`: standalone mock; never sends Bluetooth commands.
- `assets/`: Xiaomi-derived frame sequences and separately authored UI icons.
- `install.sh` and `uninstall.sh`: per-user installation and removal.

## Critical behavior

- Preserve identity checks, packet framing, authentication and serialized
  requests. Do not infer support on other Xiaomi models.
- Do not send pairing, connection, setting, reset or firmware commands while
  investigating unless the user requested or authorized the operation.
- A reported BlueZ battery is optional. Do not invent battery values.
- During discovery and while connecting play the finding sequence once; only
  play the connecting sequence after BlueZ reports `Connected=true`.
- Slider changes must be sent once after pointer/touch release, not during drag.
- Another host may hold the control channel even when audio is connected.
- Do not claim Fedora GNOME or real-device behavior was verified from a build or
  static analysis. State what was actually observed.
- Avoid printing device addresses, serial numbers, raw packet captures, tokens,
  or personal user paths in committed files and logs.
- Xiaomi artwork has no redistribution permission established; see ASSETS.md.
  Do not relicense it on the assumption that it is open source.
- Keep the real connection-failure handling separate from the demo unless
  explicitly asked to integrate it.

## Working conventions

Keep changes focused; preserve existing local user work. Describe any platform
or device verification boundary. Do not run tests unless requested by the user
or governing instructions. For installation, use `./install.sh`; dependency
installation is opt-in via `--install-deps` and may invoke `sudo`.
