using System;
using System.Diagnostics;
using System.IO;
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
    private bool busy, loading;
    private readonly DispatcherTimer animationTimer = new() { Interval = TimeSpan.FromMilliseconds(32) };
    private int frame, endFrame;
    private readonly Forms.NotifyIcon tray;

    public MainWindow()
    {
        InitializeComponent();
        tray = new Forms.NotifyIcon { Text = "REDMI Headphones Neo", Icon = System.Drawing.SystemIcons.Application, Visible = true };
        var menu = new Forms.ContextMenuStrip();
        menu.Items.Add("Open", null, (_, _) => Dispatcher.Invoke(ShowWindow));
        menu.Items.Add("Exit", null, (_, _) => Dispatcher.Invoke(Close));
        tray.ContextMenuStrip = menu;
        tray.DoubleClick += (_, _) => Dispatcher.Invoke(ShowWindow);
        animationTimer.Tick += (_, _) => AdvanceAnimation();
        Loaded += (_, _) => { PlayAnimation(1000, 1059); _ = RefreshAsync(); };
        Closing += (_, _) => { animationTimer.Stop(); session?.Dispose(); tray.Visible = false; tray.Dispose(); };
    }
    private void ShowWindow() { Show(); WindowState = WindowState.Normal; Activate(); }
    private void PlayAnimation(int start, int end) { animationTimer.Stop(); frame = start; endFrame = end; AdvanceAnimation(); animationTimer.Start(); }
    private void AdvanceAnimation()
    {
        var file = Path.Combine(AppContext.BaseDirectory, "Frames", $"{frame}.png");
        if (File.Exists(file)) Animation.Source = new BitmapImage(new Uri(file));
        if (frame++ >= endFrame) animationTimer.Stop();
    }
    private async Task RefreshAsync()
    {
        try
        {
            var devices = await NeoDiscovery.FindPairedAsync();
            Status.Text = devices.Count == 0 ? "Pair the Neo in Windows Bluetooth settings first." :
                devices[0].Connected ? "Neo connected to Windows. Connect controls below." : "Neo paired. Connect it in Windows Bluetooth settings, then try controls.";
        }
        catch { Status.Text = "Bluetooth is unavailable. Check Windows Bluetooth settings."; }
    }
    private async void Connect_Click(object sender, RoutedEventArgs e)
    {
        if (busy) return;
        if (session != null) { session.Dispose(); session = null; Controls.IsEnabled = false; Battery.Visibility = Visibility.Collapsed; ConnectButton.Content = "Connect controls"; await RefreshAsync(); return; }
        busy = true; ConnectButton.IsEnabled = false; Status.Text = "Connecting controls…"; PlayAnimation(1000, 1059);
        try
        {
            var devices = await NeoDiscovery.FindPairedAsync();
            if (devices.Count == 0) throw new InvalidOperationException("Pair the Neo in Windows Bluetooth settings first.");
            var device = devices[0];
            session = await NeoProtocol.ConnectAsync(device.Address);
            var settings = await session.ReadSettingsAsync();
            ShowSettings(settings);
            Battery.Visibility = session.BatteryPercent.HasValue ? Visibility.Visible : Visibility.Collapsed;
            if (session.BatteryPercent.HasValue) Battery.Text = $"Battery  {session.BatteryPercent.Value}%";
            Status.Text = "Controls connected"; ConnectButton.Content = "Disconnect controls"; Controls.IsEnabled = true; PlayAnimation(2000, 2149);
        }
        catch (Exception ex) { session?.Dispose(); session = null; Controls.IsEnabled = false; Status.Text = "Couldn't connect controls: " + ex.Message; }
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
        try { await change(session); ShowSettings(await session.ReadSettingsAsync()); Status.Text = "Controls connected"; }
        catch (Exception ex) { Status.Text = "Couldn't update controls: " + ex.Message; }
        finally { Controls.IsEnabled = session != null; busy = false; }
    }
    private async void Mode_Click(object sender, RoutedEventArgs e) { var value = int.Parse((string)((Button)sender).Tag); await ChangeAsync(s => s.SetModeAsync(value)); }
    private async void Adaptive_Click(object sender, RoutedEventArgs e) { var enabled = Adaptive.IsChecked == true; await ChangeAsync(s => s.SetAdaptiveAsync(enabled)); }
    private async void Strength_Released(object sender, MouseButtonEventArgs e) { await Dispatcher.InvokeAsync(async () => await ChangeAsync(s => s.SetLevelAsync((int)Strength.Value)), DispatcherPriority.Background); }
    private async void Strength_KeyUp(object sender, KeyEventArgs e) { if (e.Key is Key.Left or Key.Right or Key.Up or Key.Down or Key.Home or Key.End) await ChangeAsync(s => s.SetLevelAsync((int)Strength.Value)); }
    private void BluetoothSettings_Click(object sender, RoutedEventArgs e) { Process.Start(new ProcessStartInfo("ms-settings:bluetooth") { UseShellExecute = true }); }
}
