#!/usr/bin/env bash
set -eu
src=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
dest="$HOME/.local/share/neo-popup"

case "${1:-}" in
  --install-deps)
    if command -v dnf >/dev/null 2>&1; then
      sudo dnf install -y bluez bluez-libs python3-gobject python3-cairo gtk4 librsvg2
    elif command -v pacman >/dev/null 2>&1; then
      sudo pacman -S --needed bluez bluez-utils python-gobject python-cairo gtk4 librsvg
    else
      printf '%s\n' 'Unsupported package manager. Install BlueZ, Python GI, Cairo, GTK 4, and SVG/WebP loaders manually.' >&2
      exit 1
    fi
    ;;
  --help|-h)
    printf '%s\n' 'Usage: ./install.sh [--install-deps]' 'Install the app for the current user. --install-deps installs Fedora or Arch dependencies first.'
    exit 0
    ;;
  '') ;;
  *) printf 'Unknown option: %s\n' "$1" >&2; exit 2 ;;
esac
python3 -c 'import gi; gi.require_version("Gtk", "4.0"); gi.require_foreign("cairo"); from gi.repository import Gtk, Gio, GdkPixbuf; assert "webp" in [x for f in GdkPixbuf.Pixbuf.get_formats() for x in f.get_extensions()]; assert "svg" in [x for f in GdkPixbuf.Pixbuf.get_formats() for x in f.get_extensions()]' || {
    printf '%s\n' 'Missing GTK 4, Python GObject, Cairo, or WebP/SVG support.' 'Run ./install.sh --install-deps on Fedora or Arch/Omarchy, or install these dependencies manually.' >&2
    exit 1
}
command -v bluetoothctl >/dev/null || { printf '%s\n' 'BlueZ tools are required. Run ./install.sh --install-deps.' >&2; exit 1; }
mkdir -p "$dest/assets" "$HOME/.local/share/applications" "$HOME/.config/autostart"
cp "$src"/*.py "$dest/"
cp "$src"/assets/*.webp "$dest/assets/"
cp "$src"/assets/*.svg "$dest/assets/"
extension_dir="$HOME/.local/share/gnome-shell/extensions/neo-controls@earbuds.dev"
mkdir -p "$extension_dir"
cp "$src"/gnome-extension/neo-controls@earbuds.dev/extension.js "$src"/gnome-extension/neo-controls@earbuds.dev/metadata.json "$extension_dir/"
if [[ "${XDG_CURRENT_DESKTOP:-}" == *GNOME* ]] && command -v gnome-extensions >/dev/null 2>&1; then
    gnome-extensions enable neo-controls@earbuds.dev 2>/dev/null || printf '%s\n' 'Enable REDMI Headphones Neo Controls in the GNOME Extensions app after logging in again.'
fi
repo_root=$(git -C "$src" rev-parse --show-toplevel 2>/dev/null || :)
if [ "$repo_root" = "$src" ]; then
    printf '%s\n' "$src" > "$dest/source-path"
fi
cat > "$HOME/.config/autostart/neo-popup.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Headphones Neo discovery
Exec=python3 "$dest/neo_popup.py"
Terminal=false
X-GNOME-Autostart-enabled=true
EOF
cat > "$HOME/.local/share/applications/neo-popup.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=REDMI Headphones Neo
Comment=Find and connect your headphones
Exec=python3 "$dest/neo_popup.py" --show
Icon=audio-headphones
Terminal=false
Categories=AudioVideo;Audio;
EOF
printf 'Installed to %s and enabled desktop autostart.\n' "$dest"
if [ "$repo_root" = "$src" ]; then
    git -C "$src" rev-parse HEAD > "$dest/installed-revision"
fi
if [ "${NEO_NO_START:-0}" != 1 ] && [ -n "${WAYLAND_DISPLAY:-}${DISPLAY:-}" ]; then
    nohup python3 "$dest/neo_popup.py" >/dev/null 2>&1 </dev/null &
    printf '%s\n' 'Starting the companion in this desktop session.'
fi
printf '%s\n' 'Open settings from the app menu: REDMI Headphones Neo.' 'After an update, quit the previous instance or log out and back in to load the new version.'
