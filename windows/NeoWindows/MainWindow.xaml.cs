using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using Forms = System.Windows.Forms;

namespace NeoWindows;

public partial class MainWindow : Window
{
    private NeoProtocol? session;
    private NeoNearbyWatcher? watcher;
    private NeoDevice? paired;
    private bool busy, loading, exiting, polling, previousConnected;
    private DateTimeOffset lastPopup = DateTimeOffset.MinValue;
    private DateTimeOffset lastSeen = DateTimeOffset.MinValue;
    private readonly DispatcherTimer animationTimer = new() { Interval = TimeSpan.FromMilliseconds(32) };
    private readonly DispatcherTimer pollTimer = new() { Interval = TimeSpan.FromSeconds(8) };
    private int frame, endFrame;
    private readonly Forms.NotifyIcon tray;

    public MainWindow()
    {
        InitializeComponent();
        var iconPath = Path.Combine(AppContext.BaseDirectory, "Assets", "neo.ico");
        tray = new Forms.NotifyIcon { Text = "REDMI Headphones Neo", Icon = File.Exists(iconPath) ? new System.Drawing.Icon(iconPath) : System.Drawing.SystemIcons.Application, Visible = true };
        var menu = new Forms.ContextMenuStrip();
        menu.Items.Add("Open headphones", null, (_, _) => Dispatcher.Invoke(ShowWindow));
        menu.Items.Add("Exit", null, (_, _) => Dispatcher.Invoke(() => { exiting = true; Close(); }));
        tray.ContextMenuStrip = menu;
        tray.DoubleClick += (_, _) => Dispatcher.Invoke(ShowWindow);
        animationTimer.Tick += (_, _) => AdvanceAnimation();
        pollTimer.Tick += async (_, _) => await RefreshAsync();
        Loaded += async (_, _) => {
            if (Environment.GetCommandLineArgs().Contains("--background")) Hide();
            PlayAnimation(1000, 1059);
            try {
                watcher = new NeoNearbyWatcher();
                watcher.Nearby += sighting => Dispatcher.BeginInvoke(new Action(() => Nearby(sighting)));
                watcher.ScanStopped += message => Dispatcher.BeginInvoke(new Action(() => { if (!busy) Status.Text = message; }));
                watcher.Start();
            } catch { Status.Text = "Bluetooth discovery unavailable. Check Windows Bluetooth settings."; }
            await RefreshAsync(); pollTimer.Start();
        };
        Closing += (_, e) => {
            if (!exiting) { e.Cancel = true; Hide(); return; }
            pollTimer.Stop(); animationTimer.Stop(); watcher?.Dispose(); session?.Dispose(); tray.Visible = false; tray.Dispose();
        };
    }
    private void ShowWindow() { Show(); WindowState = WindowState.Normal; Activate(); }
    private void Close_Click(object sender, RoutedEventArgs e) { lastPopup = DateTimeOffset.UtcNow; Hide(); }
    private void Settings_Click(object sender, RoutedEventArgs e) { Controls.Visibility = Controls.Visibility == Visibility.Visible ? Visibility.Collapsed : Visibility.Visible; }
    private void PlayAnimation(int start, int end) { animationTimer.Stop(); frame = start; endFrame = end; AdvanceAnimation(); animationTimer.Start(); }
    private void AdvanceAnimation()
    {
        var file = Path.Combine(AppContext.BaseDirectory, "Frames", $"{frame}.png");
        if (File.Exists(file)) Animation.Source = new BitmapImage(new Uri(file));
        if (frame++ >= endFrame) animationTimer.Stop();
    }
    private void Nearby(NeoSighting sighting)
    {
        lastSeen = sighting.SeenAt;
        if (paired?.Connected == true || busy || IsVisible || DateTimeOffset.UtcNow - lastPopup < TimeSpan.FromMinutes(2)) return;
        lastPopup = DateTimeOffset.UtcNow;
        Status.Text = "Headphones detected nearby";
        BluetoothButton.Visibility = paired == null ? Visibility.Visible : Visibility.Collapsed;
        ConnectButton.Content = "Connect";
        PlayAnimation(1000, 1059); ShowWindow();
    }
    private async Task RefreshAsync()
    {
        if (polling || busy) return;
        polling = true;
        try
        {
            var devices = await NeoDiscovery.FindPairedAsync();
            watcher?.SetPairedDevices(devices);
            paired = devices.FirstOrDefault(d => d.Connected) ?? devices.FirstOrDefault();
            bool connected = paired?.Connected == true;
            if (!connected && previousConnected) {
                session?.Dispose(); session = null; BatteryRow.Visibility = Visibility.Collapsed;
                SettingsButton.Visibility = Visibility.Collapsed; Controls.Visibility = Visibility.Collapsed;
                ConnectButton.Content = "Connect";
            }
            if (connected && !previousConnected) {
                if (!IsVisible && DateTimeOffset.UtcNow - lastPopup >= TimeSpan.FromMinutes(2)) { lastPopup = DateTimeOffset.UtcNow; ShowWindow(); }
                if (!busy) _ = ConnectControlsAsync(false);
            }
            previousConnected = connected;
            if (!busy && session == null) {
                Status.Text = connected ? "Headphones connected" : paired == null ? "Pair your headphones in Windows to get started" : DateTimeOffset.UtcNow - lastSeen < TimeSpan.FromSeconds(20) ? "Headphones detected nearby" : "Waiting for your headphones";
                BluetoothButton.Visibility = paired == null ? Visibility.Visible : Visibility.Collapsed;
            }
        }
        catch { if (!busy) Status.Text = "Bluetooth unavailable. Check Windows settings."; }
        finally { polling = false; }
    }
    private async void Connect_Click(object sender, RoutedEventArgs e)
    {
        if (busy) return;
        if (session != null) { Settings_Click(sender, e); return; }
        await ConnectControlsAsync(true);
    }
    private async Task ConnectControlsAsync(bool userRequested)
    {
        if (busy || session != null) return;
        busy = true; ConnectButton.IsEnabled = false; Status.Text = "Connecting…"; PlayAnimation(1000, 1059);
        try
        {
            var devices = await NeoDiscovery.FindPairedAsync();
            paired = devices.FirstOrDefault(d => d.Connected) ?? devices.FirstOrDefault();
            if (paired == null) { Status.Text = "Pair the Neo in Windows Bluetooth settings first."; BluetoothButton.Visibility = Visibility.Visible; return; }
            bool wasConnected = paired.Connected;
            NeoAudioRequest? audioRequest = null;
            if (userRequested && !wasConnected) {
                Status.Text = "Connecting headphone audio…";
                audioRequest = await NeoAudioConnect.RequestReconnectAsync(paired.Address);
                if (audioRequest.Accepted) {
                    for (int i = 0; i < 5; i++) {
                        await Task.Delay(1000);
                        var refreshed = await NeoDiscovery.FindPairedAsync();
                        if (refreshed.Any(d => d.Address == paired.Address && d.Connected)) break;
                    }
                }
            }
            session = await NeoProtocol.ConnectAsync(paired.Address);
            var settings = await session.ReadSettingsAsync();
            ShowSettings(settings);
            BatteryRow.Visibility = session.BatteryPercent.HasValue ? Visibility.Visible : Visibility.Collapsed;
            if (session.BatteryPercent.HasValue) { Battery.Text = $"{session.BatteryPercent.Value}%"; BatteryFill.Width = 18 * session.BatteryPercent.Value / 100.0; }
            Status.Text = "Headphone controls connected";
            ConnectButton.Content = "Settings"; SettingsButton.Visibility = Visibility.Collapsed;
            PlayAnimation(2000, 2149);
            if (!wasConnected) {
                Status.Text = audioRequest?.Accepted == true ? "Controls connected. Audio connection requested; check your Windows audio output." : "Controls connected. Connect audio in Windows Bluetooth settings.";
                BluetoothButton.Visibility = Visibility.Visible;
                if (userRequested && audioRequest?.Accepted != true) BluetoothSettings_Click(this, new RoutedEventArgs());
            } else BluetoothButton.Visibility = Visibility.Collapsed;
        }
        catch (Exception ex) {
            session?.Dispose(); session = null; BatteryRow.Visibility = Visibility.Collapsed;
            Status.Text = "Could not connect. " + ex.Message;
            BluetoothButton.Visibility = Visibility.Visible;
            if (userRequested && paired?.Connected != true) BluetoothSettings_Click(this, new RoutedEventArgs());
        }
        finally { busy = false; ConnectButton.IsEnabled = true; }
    }
    private void ShowSettings(NeoSettings settings)
    {
        loading = true;
        ModeText.Text = settings.NoiseMode switch { 0 => "Off", 1 => "Noise cancellation", 2 => "Transparency", _ => "Unknown" };
        AncOptions.Visibility = settings.NoiseMode == 1 ? Visibility.Visible : Visibility.Collapsed;
        Adaptive.IsChecked = settings.AdaptiveAnc; Strength.IsEnabled = !settings.AdaptiveAnc; Strength.Value = settings.NoiseLevel;
        loading = false;
    }
    private async Task ChangeAsync(Func<NeoProtocol, Task> change)
    {
        if (session == null || busy || loading) return;
        busy = true; Controls.IsEnabled = false;
        try { await change(session); ShowSettings(await session.ReadSettingsAsync()); Status.Text = "Headphone controls connected"; }
        catch (Exception ex) { Status.Text = "Could not update controls: " + ex.Message; }
        finally { Controls.IsEnabled = session != null; busy = false; }
    }
    private async void Mode_Click(object sender, RoutedEventArgs e) { var value = int.Parse((string)((Button)sender).Tag); await ChangeAsync(s => s.SetModeAsync(value)); }
    private async void Adaptive_Click(object sender, RoutedEventArgs e) { var enabled = Adaptive.IsChecked == true; await ChangeAsync(s => s.SetAdaptiveAsync(enabled)); }
    private async void Strength_Released(object sender, MouseButtonEventArgs e) { await Dispatcher.InvokeAsync(async () => await ChangeAsync(s => s.SetLevelAsync((int)Strength.Value)), DispatcherPriority.Background); }
    private async void Strength_KeyUp(object sender, KeyEventArgs e) { if (e.Key is Key.Left or Key.Right or Key.Up or Key.Down or Key.Home or Key.End) await ChangeAsync(s => s.SetLevelAsync((int)Strength.Value)); }
    private void BluetoothSettings_Click(object sender, RoutedEventArgs e) { Process.Start(new ProcessStartInfo("ms-settings:bluetooth") { UseShellExecute = true }); }
}
