using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
using Windows.Devices.Bluetooth;
using Windows.Devices.Enumeration;

namespace NeoWindows;

/// <summary>Result indicates whether Windows accepted a request, not whether audio connected.</summary>
public sealed record NeoAudioRequest(bool Accepted, string Message);

/// <summary>
/// Sends the Bluetooth audio driver's one-shot reconnect property to audio filters
/// belonging to the selected paired device. This is Windows implementation-specific;
/// it may fail on future Windows versions or on some hardware/drivers.
/// </summary>
public static class NeoAudioConnect
{
    private const string ContainerProperty = "System.Devices.Aep.ContainerId";

    public static async Task<NeoAudioRequest> RequestReconnectAsync(ulong address)
    {
        try
        {
            var devices = await DeviceInformation.FindAllAsync(
                BluetoothDevice.GetDeviceSelectorFromPairingState(true),
                new[] { ContainerProperty }, DeviceInformationKind.AssociationEndpoint);
            Guid? container = null;
            foreach (var info in devices)
            {
                if (!NeoDiscovery.IsNeoName(info.Name)) continue;
                using var device = await BluetoothDevice.FromIdAsync(info.Id);
                if (device?.BluetoothAddress == address &&
                    info.Properties.TryGetValue(ContainerProperty, out var value) && value is Guid id)
                {
                    container = id;
                    break;
                }
            }
            if (container == null)
                return new(false, "Windows could not find a matching paired Neo audio device.");
            return await Task.Run(() => SendReconnect(container.Value));
        }
        catch (Exception ex) when (ex is COMException || ex is UnauthorizedAccessException ||
                                   ex is InvalidOperationException)
        {
            return new(false, "Windows could not request an audio connection. Use Bluetooth settings to connect.");
        }
    }

    private static NeoAudioRequest SendReconnect(Guid container)
    {
        try
        {
            var type = Type.GetTypeFromCLSID(ComIds.MMDeviceEnumeratorClsid, true)!;
            var enumerator = (IMMDeviceEnumerator)Activator.CreateInstance(type)!;
            enumerator.EnumAudioEndpoints(EDataFlow.All, DeviceState.Active | DeviceState.Unplugged,
                out var endpoints);
            endpoints.GetCount(out var count);
            var filters = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            for (uint i = 0; i < count; i++)
            {
                try
                {
                    endpoints.Item(i, out var endpoint);
                    endpoint.OpenPropertyStore(ComIds.StgmRead, out var store);
                    var key = PropertyKeys.DeviceContainerId;
                    store.GetValue(ref key, out var value);
                    Guid? endpointContainer;
                    try { endpointContainer = value.AsGuid(); }
                    finally { NativeMethods.PropVariantClear(ref value); }
                    if (endpointContainer != container) continue;
                    var topologyIid = ComIds.DeviceTopologyIid;
                    endpoint.Activate(ref topologyIid, ComIds.ClsCtxAll, IntPtr.Zero, out var topologyObject);
                    ((IDeviceTopology)topologyObject).GetConnector(0, out var connector);
                    connector.GetDeviceIdConnectedTo(out var filterId);
                    if (!string.IsNullOrEmpty(filterId)) filters.Add(filterId);
                }
                catch (COMException) { /* A disappearing endpoint is not fatal. */ }
            }
            var accepted = 0;
            foreach (var filterId in filters)
            {
                try
                {
                    enumerator.GetDevice(filterId, out var filter);
                    var controlIid = ComIds.KsControlIid;
                    filter.Activate(ref controlIid, ComIds.ClsCtxAll, IntPtr.Zero, out var control);
                    var property = new KsProperty { Set = KsBluetoothAudio.PropertySet,
                        Id = KsBluetoothAudio.OneShotReconnect, Flags = KsBluetoothAudio.KsPropertyTypeGet };
                    if (((IKsControl)control).KsProperty(ref property, (uint)Marshal.SizeOf<KsProperty>(),
                        IntPtr.Zero, 0, out _) >= 0) accepted++;
                }
                catch (COMException) { /* Other matching filters can still accept the request. */ }
            }
            return accepted > 0
                ? new(true, "Connection requested. Waiting for Windows to connect the headphones…")
                : new(false, "Windows did not accept the audio connection request. Use Bluetooth settings to connect.");
        }
        catch (Exception ex) when (ex is COMException || ex is InvalidOperationException || ex is InvalidCastException)
        {
            return new(false, "Windows could not request an audio connection. Use Bluetooth settings to connect.");
        }
    }
}
