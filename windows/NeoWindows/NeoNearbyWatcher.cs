using System;
using System.Collections.Generic;
using Windows.Devices.Bluetooth.Advertisement;

namespace NeoWindows;

/// <summary>A freshly received LE advertisement, not proof of an audio connection.</summary>
public sealed record NeoSighting(string Name, ulong Address, DateTimeOffset SeenAt);

/// <summary>
/// Watches for Neo LE advertisements. Address and advertised names are hints, not
/// authenticated identity. Some firmware may use a private LE address or omit a name.
/// The watcher never pairs or connects a device.
/// </summary>
public sealed class NeoNearbyWatcher : IDisposable
{
    private readonly BluetoothLEAdvertisementWatcher watcher = new()
    {
        ScanningMode = BluetoothLEScanningMode.Active,
    };
    private readonly object gate = new();
    private readonly Dictionary<ulong, string> knownNames = new();
    private readonly Dictionary<ulong, DateTimeOffset> lastEmitted = new();
    private bool disposed;

    /// <summary>Raised on a Bluetooth worker thread, at most once per address per five seconds.</summary>
    public event Action<NeoSighting>? Nearby;
    /// <summary>Raised on a Bluetooth worker thread if Windows stops scanning unexpectedly.</summary>
    public event Action<string>? ScanStopped;

    public NeoNearbyWatcher()
    {
        watcher.Received += OnReceived;
        watcher.Stopped += OnStopped;
    }

    /// <summary>Allows advertisements without a name to match an already paired classic address.
    /// A different or rotating LE address cannot be associated this way.</summary>
    public void SetPairedDevices(IEnumerable<NeoDevice> devices)
    {
        lock (gate)
        {
            knownNames.Clear();
            foreach (var device in devices)
                if (device.Address != 0)
                    knownNames[device.Address] = device.Name;
        }
    }

    public void Start()
    {
        ObjectDisposedException.ThrowIf(disposed, this);
        watcher.Start();
    }

    private void OnReceived(BluetoothLEAdvertisementWatcher sender,
        BluetoothLEAdvertisementReceivedEventArgs args)
    {
        string name = args.Advertisement.LocalName;
        var now = DateTimeOffset.UtcNow;
        lock (gate)
        {
            if (disposed || args.BluetoothAddress == 0)
                return;
            if (!NeoDiscovery.IsNeoName(name) && !knownNames.TryGetValue(args.BluetoothAddress, out name!))
                return;
            if (lastEmitted.TryGetValue(args.BluetoothAddress, out var last) && now - last < TimeSpan.FromSeconds(5))
                return;
            lastEmitted[args.BluetoothAddress] = now;
        }
        Nearby?.Invoke(new NeoSighting(name, args.BluetoothAddress, now));
    }

    private void OnStopped(BluetoothLEAdvertisementWatcher sender,
        BluetoothLEAdvertisementWatcherStoppedEventArgs args)
    {
        if (!disposed && args.Error != Windows.Devices.Bluetooth.BluetoothError.Success)
            ScanStopped?.Invoke("Bluetooth scanning stopped: " + args.Error);
    }

    public void Dispose()
    {
        lock (gate)
        {
            if (disposed)
                return;
            disposed = true;
        }
        watcher.Received -= OnReceived;
        watcher.Stopped -= OnStopped;
        watcher.Stop();
    }
}
