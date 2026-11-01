# Windows 11 preview

Pair and connect the REDMI Headphones Neo in Windows Bluetooth settings, then
run REDMI-Neo.exe. Choose **Connect controls** to authenticate to the Neo's
separate control channel. ANC, transparency, Adaptive ANC and strength use the
same Neo commands as the Linux app. The battery appears only if the headset
returns a usable value. The Windows build is experimental and has not yet been
verified against a real device. Windows manages audio pairing and connection.

Build on Windows with .NET 8 SDK:

```powershell
dotnet publish windows/NeoWindows/NeoWindows.csproj -c Release -r win-x64 --self-contained true
```

The PNG animation frames are derived from the Xiaomi WebP assets; see the root
ASSETS.md for provenance and rights.
