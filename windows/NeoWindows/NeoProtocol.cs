using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Threading;
using System.Threading.Tasks;
using Windows.Devices.Bluetooth;
using Windows.Devices.Bluetooth.Rfcomm;
using Windows.Networking.Sockets;
using Windows.Storage.Streams;

namespace NeoWindows;

public sealed record NeoSettings(int NoiseMode, int NoiseLevel, bool AdaptiveAnc);

/// <summary>Authenticated RCSP session for the REDMI Headphones Neo. Pair in Windows first.</summary>
public sealed class NeoProtocol : IDisposable
{
    private static readonly Guid ServiceUuid = new("0000fd2d-0000-1000-8000-00805f9b34fb");
    private static readonly byte[] Magic = { 0xfe, 0xdc, 0xba };
    private static readonly byte[] Seed = { 0x11, 0x22, 0x33, 0x33, 0x22, 0x11 };
    private static readonly int[][] Layers = {
        new[] {0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15},
        new[] {0,7,2,1,4,3,6,5,8,11,10,9,12,15,14,13},
        new[] {10,13,0,3,6,1,14,9,4,7,8,5,2,15,12,11},
        new[] {14,7,0,13,8,15,6,11,4,9,2,5,10,1,12,3}
    };
    private static readonly int[] Gather = {14,7,8,15,0,13,6,11,4,9,2,5,10,1,12,3};
    private static readonly byte[] Exp = BuildExp();
    private static readonly byte[] Log = BuildLog();
    private readonly BluetoothDevice device;
    private readonly RfcommDeviceService service;
    private readonly StreamSocket socket;
    private readonly Stream input, output;
    private readonly SemaphoreSlim gate = new(1, 1);
    private readonly List<byte> buffer = new();
    private byte sequence;
    private bool authenticated, peerChallenge, peerVerified, closed;
    public ushort Vid { get; private set; }
    public ushort Pid { get; private set; }
    public string? Firmware { get; private set; }
    public int? BatteryPercent { get; private set; }
    public bool? BatteryCharging { get; private set; }

    private NeoProtocol(BluetoothDevice device, RfcommDeviceService service, StreamSocket socket)
    {
        this.device = device; this.service = service; this.socket = socket;
        input = socket.InputStream.AsStreamForRead(); output = socket.OutputStream.AsStreamForWrite();
    }

    public static async Task<NeoProtocol> ConnectAsync(ulong address)
    {
        var device = await BluetoothDevice.FromBluetoothAddressAsync(address).AsTask().WaitAsync(TimeSpan.FromSeconds(15))
            ?? throw new IOException("Windows could not find the Bluetooth device. Pair it first.");
        RfcommDeviceService? service = null;
        StreamSocket? socket = null;
        NeoProtocol? session = null;
        try
        {
            var services = await device.GetRfcommServicesForIdAsync(RfcommServiceId.FromUuid(ServiceUuid), BluetoothCacheMode.Uncached)
                .AsTask().WaitAsync(TimeSpan.FromSeconds(15));
            if (services.Error != BluetoothError.Success || services.Services.Count == 0)
                throw new IOException("The Neo RCSP Bluetooth service is unavailable.");
            service = services.Services[0];
            socket = new StreamSocket();
            await socket.ConnectAsync(service.ConnectionHostName, service.ConnectionServiceName, SocketProtectionLevel.BluetoothEncryptionAllowNullAuthentication)
                .AsTask().WaitAsync(TimeSpan.FromSeconds(15));
            session = new NeoProtocol(device, service, socket);
            await session.AuthenticateAsync();
            return session;
        }
        catch
        {
            if (session != null) session.Dispose();
            else { socket?.Dispose(); service?.Dispose(); device.Dispose(); }
            throw;
        }
    }

    private async Task AuthenticateAsync()
    {
        try
        {
            var factor = RandomNumberGenerator.GetBytes(16);
            var answer = await RequestAsync(0x50, new byte[] {1}.Concat(factor).ToArray());
            if (!answer.SequenceEqual(new byte[] {1}.Concat(AuthResponse(factor))))
                throw new IOException("Headphone authentication response did not match.");
            if (!(await RequestAsync(0x51, new byte[] {1, 0})).SequenceEqual(new byte[] {1}))
                throw new IOException("Invalid authentication acknowledgment.");
            while (!peerVerified)
            {
                var packet = await NextPacketAsync();
                if ((packet.Flags & 0x80) != 0) await IncomingAsync(packet);
            }
            authenticated = true;
            ParseTargetInfo(await RequestAsync(0x02, new byte[] {255,255,255,255}));
            if (Vid != 0x2717 || (Pid != 0x50f0 && Pid != 0x50fb))
                throw new IOException($"Unsupported device identity {Vid:X4}:{Pid:X4}.");
        }
        catch { Dispose(); throw; }
    }

    public async Task<NeoSettings> ReadSettingsAsync()
    {
        await gate.WaitAsync();
        try
        {
            EnsureReady();
            var configs = ParseConfigs(await RequestAsync(0xf3, new byte[] {0,11,0,37}));
            if (!configs.TryGetValue(11, out var noise) || noise.Length != 2 || noise[0] > 2 || noise[1] > 2 ||
                !configs.TryGetValue(37, out var adaptive) || adaptive.Length != 1)
                throw new IOException("Invalid or missing Neo settings.");
            return new NeoSettings(noise[0], noise[1], adaptive[0] != 0);
        }
        finally { gate.Release(); }
    }
    public Task SetModeAsync(int mode) => SetAsync(0x08, mode, new byte[] {2,4,(byte)mode});
    public Task SetLevelAsync(int level) => SetAsync(0xf2, level, new byte[] {4,0,11,1,(byte)level});
    public async Task SetAdaptiveAsync(bool enabled)
    {
        await gate.WaitAsync();
        try { EnsureReady(); await RequestAsync(0xf2, new byte[] {3,0,37, enabled ? (byte)1 : (byte)0}); }
        finally { gate.Release(); }
    }
    private async Task SetAsync(byte opcode, int value, byte[] payload)
    {
        if (value < 0 || value > 2) throw new ArgumentOutOfRangeException(nameof(value));
        await gate.WaitAsync();
        try { EnsureReady(); await RequestAsync(opcode, payload); }
        finally { gate.Release(); }
    }
    private void EnsureReady()
    {
        if (closed || !authenticated || Vid != 0x2717 || (Pid != 0x50f0 && Pid != 0x50fb))
            throw new IOException("Connect to a REDMI Headphones Neo first.");
    }

    private sealed record Packet(byte Flags, byte Opcode, byte Sequence, byte Status, byte[] Payload);
    private async Task SendAsync(byte flags, byte opcode, byte[] body)
    {
        if (closed || body.Length > 4096) throw new IOException("Session closed or packet too large.");
        var packet = new byte[body.Length + 8];
        Array.Copy(Magic, packet, 3); packet[3] = flags; packet[4] = opcode;
        packet[5] = (byte)(body.Length >> 8); packet[6] = (byte)body.Length;
        Array.Copy(body, 0, packet, 7, body.Length); packet[^1] = 0xef;
        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(8));
        await output.WriteAsync(packet, cts.Token); await output.FlushAsync(cts.Token);
    }
    private async Task<Packet> NextPacketAsync()
    {
        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(8));
        while (true)
        {
            while (buffer.Count >= 3 && !(buffer[0] == 0xfe && buffer[1] == 0xdc && buffer[2] == 0xba)) buffer.RemoveAt(0);
            if (buffer.Count >= 7)
            {
                int length = (buffer[5] << 8) | buffer[6];
                if (length > 4096) { buffer.RemoveAt(0); continue; }
                if (buffer.Count >= length + 8)
                {
                    if (buffer[length + 7] != 0xef) { buffer.RemoveAt(0); continue; }
                    byte flags = buffer[3], opcode = buffer[4];
                    bool request = (flags & 0x80) != 0;
                    int minimum = !request || opcode == 1 ? 2 : 1;
                    if (length < minimum) { buffer.RemoveAt(0); continue; }
                    byte status = request ? (byte)0 : buffer[7];
                    byte seq = buffer[request ? 7 : 8];
                    int payloadStart = request ? (opcode == 1 ? 9 : 8) : 9;
                    var payload = buffer.GetRange(payloadStart, length + 7 - payloadStart).ToArray();
                    buffer.RemoveRange(0, length + 8);
                    return new Packet(flags, opcode, seq, status, payload);
                }
            }
            var chunk = new byte[4096];
            int read = await input.ReadAsync(chunk, cts.Token);
            if (read == 0) throw new IOException("Headphones closed the Bluetooth connection.");
            buffer.AddRange(chunk.AsSpan(0, read).ToArray());
        }
    }
    private Task ReplyAsync(byte opcode, byte seq, byte[] payload, byte status = 0) =>
        SendAsync(0x04, opcode, new byte[] {status, seq}.Concat(payload).ToArray());
    private async Task IncomingAsync(Packet packet)
    {
        if (packet.Opcode == 0x50)
        {
            if (authenticated || packet.Payload.Length != 17 || packet.Payload[0] != 1)
                throw new IOException("Invalid peer authentication challenge.");
            await ReplyAsync(packet.Opcode, packet.Sequence, new byte[] {1}.Concat(AuthResponse(packet.Payload[1..])).ToArray());
            peerChallenge = true;
        }
        else if (packet.Opcode == 0x51)
        {
            await ReplyAsync(packet.Opcode, packet.Sequence, new byte[] {1});
            if (!peerChallenge || !packet.Payload.SequenceEqual(new byte[] {1,0}))
                throw new IOException("Headphones rejected authentication.");
            peerVerified = true;
        }
        else if (!authenticated) throw new IOException("Unexpected pre-authentication request.");
        else if (packet.Opcode == 0x0e || (packet.Flags & 0x40) != 0)
            await ReplyAsync(packet.Opcode, packet.Sequence, Array.Empty<byte>(), packet.Opcode == 0xf4 ? (byte)0 : (byte)2);
    }
    private async Task<byte[]> RequestAsync(byte opcode, byte[] payload)
    {
        byte seq = sequence++;
        try
        {
            await SendAsync(0xc4, opcode, new byte[] {seq}.Concat(payload).ToArray());
            while (true)
            {
                var packet = await NextPacketAsync();
                if ((packet.Flags & 0x80) != 0) await IncomingAsync(packet);
                else if (packet.Opcode == opcode && packet.Sequence == seq)
                {
                    if (packet.Status != 0) throw new DeviceException(opcode, packet.Status);
                    return packet.Payload;
                }
            }
        }
        catch (DeviceException) { throw; }
        catch { Dispose(); throw; }
    }
    public sealed class DeviceException : IOException
    {
        public DeviceException(byte opcode, byte status) : base($"Headphones rejected command {opcode:X2} (status {status}).") { }
    }
    private void ParseTargetInfo(byte[] data)
    {
        var attrs = new Dictionary<int, byte[]>();
        for (int offset = 0; offset < data.Length;)
        {
            int length = data[offset], end = offset + 1 + length;
            if (length < 1 || end > data.Length) throw new IOException("Truncated target info.");
            attrs[data[offset + 1]] = data[(offset + 2)..end]; offset = end;
        }
        if (!attrs.TryGetValue(3, out var id) || id.Length != 4 || !attrs.TryGetValue(1, out var version) || version.Length < 2 ||
            version.Take(2).Any(b => (b >> 4) > 9 || (b & 15) > 9)) throw new IOException("Invalid Neo identity or firmware.");
        Vid = (ushort)((id[0] << 8) | id[1]); Pid = (ushort)((id[2] << 8) | id[3]);
        Firmware = $"{version[0] >> 4}.{version[0] & 15}.{version[1] >> 4}.{version[1] & 15}";
        if (attrs.TryGetValue(7, out var battery) && battery.Length > 0 && battery[0] != 255 && (battery[0] & 127) <= 100)
        { BatteryPercent = battery[0] & 127; BatteryCharging = (battery[0] & 128) != 0; }
    }
    private static Dictionary<int, byte[]> ParseConfigs(byte[] data)
    {
        var result = new Dictionary<int, byte[]>();
        for (int offset = 0; offset < data.Length;)
        {
            int length = data[offset], end = offset + 1 + length;
            if (length < 2 || end > data.Length) throw new IOException("Invalid configuration record.");
            int id = (data[offset + 1] << 8) | data[offset + 2];
            var value = data[(offset + 3)..end];
            if (result.TryGetValue(id, out var existing) && !existing.SequenceEqual(value)) throw new IOException("Conflicting configuration records.");
            result[id] = value; offset = end;
        }
        return result;
    }
    private static byte[] BuildExp() { var a = new byte[256]; int v = 1; for (int i=0;i<256;i++) { a[i]=(byte)v; v=v*45%257; } return a; }
    private static byte[] BuildLog() { var a = new byte[256]; for (int i=0;i<256;i++) a[Exp[i]]=(byte)i; return a; }
    private static byte[] AuthResponse(byte[] challenge)
    {
        if (challenge.Length != 16) throw new IOException("Invalid authentication factor.");
        var key = challenge.ToArray(); key[15] ^= 6;
        var ring = new byte[17]; Array.Copy(key, ring, 16); foreach (byte b in key) ring[16] ^= b;
        var schedule = new byte[272]; Array.Copy(key, schedule, 16);
        for (int s=1;s<=16;s++)
        {
            for (int j=0;j<17;j++) ring[j]=(byte)((ring[j]<<3)|(ring[j]>>5));
            for (int i=0;i<16;i++) schedule[16*s+i]=(byte)(ring[(s+i)%17]+Exp[Exp[(17*(s+1)+i+1)%256]]);
        }
        var original = Enumerable.Range(0,16).Select(i => Seed[i%Seed.Length]).ToArray();
        var state = original.ToArray();
        for (int round=0;round<8;round++)
        {
            if (round == 2) for (int i=0;i<16;i++) state[i] = (byte)(((0x9999>>i)&1)!=0 ? state[i]^original[i] : state[i]+original[i]);
            for (int i=0;i<16;i++)
            {
                bool x = ((0x9999>>i)&1)!=0;
                int n = x ? state[i]^schedule[32*round+i] : (state[i]+schedule[32*round+i])&255;
                n = x ? Exp[n] : Log[n];
                state[i] = (byte)(x ? n+schedule[32*round+16+i] : n^schedule[32*round+16+i]);
            }
            foreach (var layer in Layers) for (int p=0;p<16;p+=2)
            {
                int i=layer[p], j=layer[p+1], a=state[i], b=state[j]; state[i]=(byte)(2*a+b); state[j]=(byte)(a+b);
            }
            state = Gather.Select(i => state[i]).ToArray();
        }
        for (int i=0;i<16;i++) state[i]=(byte)(((0x9999>>i)&1)!=0 ? state[i]^schedule[256+i] : state[i]+schedule[256+i]);
        return state;
    }
    public void Dispose()
    {
        if (closed) return;
        closed = true; authenticated = false;
        input.Dispose(); output.Dispose(); socket.Dispose(); service.Dispose(); device.Dispose();
    }
}
