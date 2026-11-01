using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Windows.Devices.Bluetooth;
using Windows.Devices.Enumeration;

namespace NeoWindows;

public sealed record NeoDevice(string Name, ulong Address, bool Connected);

/// <summary>Finds Neo headphones already paired in Windows Bluetooth settings.</summary>
public static class NeoDiscovery
{
    private static readonly string[] Names =
    {
        "REDMI Headphones Neo",
        "REDMI 头戴降噪耳机",
        "REDMI 頭戴降噪耳機",
    };

    /// <summary>
    /// Returns a snapshot of paired devices. A paired entry does not establish
    /// that the headphones are nearby; Connected is the current Windows status.
    /// Pairing itself is performed by the user in Windows Bluetooth settings.
    /// </summary>
    public static async Task<IReadOnlyList<NeoDevice>> FindPairedAsync()
    {
        var selector = BluetoothDevice.GetDeviceSelectorFromPairingState(true);
        var devices = await DeviceInformation.FindAllAsync(selector);
        var found = new Dictionary<ulong, NeoDevice>();

        foreach (var info in devices)
        {
            if (!IsNeoName(info.Name))
                continue;

            try
            {
                using var device = await BluetoothDevice.FromIdAsync(info.Id);
                if (device == null || device.BluetoothAddress == 0)
                    continue;

                var neo = new NeoDevice(info.Name, device.BluetoothAddress,
                    device.ConnectionStatus == BluetoothConnectionStatus.Connected);
                // A Windows device can appear more than once; retain connected status.
                if (!found.TryGetValue(neo.Address, out var previous) || neo.Connected || !previous.Connected)
                    found[neo.Address] = neo;
            }
            catch (Exception ex) when (ex is System.Runtime.InteropServices.COMException ||
                                       ex is UnauthorizedAccessException ||
                                       ex is InvalidOperationException)
            {
                // An entry can disappear while Windows is enumerating it.
            }
        }

        return new List<NeoDevice>(found.Values);
    }

    private static bool IsNeoName(string name)
    {
        foreach (var candidate in Names)
            if (string.Equals(name?.Trim(), candidate, StringComparison.OrdinalIgnoreCase))
                return true;
        return false;
    }
}
