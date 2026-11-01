# Windows 11 preview

Run the installer and follow the prompts. The optional startup entry keeps the
headphones icon in the notification area and listens for Neo advertisements.
Click the icon to open the popup. Pair the headphones once in Windows Bluetooth
settings. A fresh, named Neo advertisement can show the popup automatically;
Bluetooth discovery depends on the headphone's advertisements and Windows
adapter, and may not work with hidden or changing Bluetooth addresses.

**Connect** requests a Windows audio reconnect and opens the Neo's authenticated
control channel. If the driver does not accept the reconnect request, the app
opens Windows Bluetooth settings as a fallback. Driver acceptance does not prove
that audio connected. Windows' Bluetooth connection status does not prove
that the audio profile is connected. The app displays battery only if the Neo
returns a valid value. Controls and battery reporting require verification on a
real Windows PC with the Neo.

The top-right close button hides the app; use **Exit** in its tray icon menu to
stop background discovery. To uninstall, use Windows Installed apps.

Build on Windows with the .NET 8 SDK:

```powershell
dotnet publish windows/NeoWindows/NeoWindows.csproj -c Release -r win-x64 --self-contained true
```

The included animation shows the black Neo and derives from the Xiaomi WebP
assets; see the root ASSETS.md for provenance and rights. A white Neo animation
has not been found in the extracted resources.
