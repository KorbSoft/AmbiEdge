# AmbiEdge

**Screen-reactive bias lighting for LED strips connected to your PC.**

AmbiEdge watches the edges of your screen and lights an LED strip behind your monitor or TV
with matching colors, the "ambilight" effect. It works with several kinds of controllers:
USB, serial (Arduino / ESP), Wi-Fi (WLED) and anything OpenRGB can drive.

It's **free and open source** ([GPL-3.0](#license)), made as a hobby project. It was built with
the help of AI; see [How it was made](#how-it-was-made).

**Features**

- Screen sync with smoothing, black-bar detection and a "vivid colors" mode that keeps small
  saturated details (a red logo on gray) from turning muddy.
- **Profiles** (Desktop, Movie, Game, or your own) that switch automatically by the app in front.
- **Mood light**: a plain color, slow breathing, color cycle or rainbow when you're not syncing.
- Lights **fade out when the display sleeps, the PC locks or goes to sleep**, and come back by
  themselves. An optional **daily schedule** keeps them off outside the hours you choose.
- A **tray icon** (Windows) or **menu bar icon** (macOS) with on/off, mood light, brightness and
  profile controls.
- A live preview of the layout, a test pattern for checking it, and **Fit to LED count** to split
  a strip over the screen edges automatically.

> [!CAUTION]
> **Use at your own risk.** AmbiEdge is provided "as is", without warranty of any kind. The
> authors aren't responsible for damage to your LED strip, controller, power supply, USB port,
> computer or anything else, or for any other harm that comes from using it. Read
> [Safety](#safety) before you start.

---

## Contents

- [What you need](#what-you-need)
- [Supported controllers](#supported-controllers)
- [Will my strip work?](#will-my-strip-work)
- [Install](#install)
- [First-time setup](#first-time-setup)
- [Settings](#settings)
- [Tray icon](#tray-icon)
- [Safety](#safety)
- [Things worth knowing](#things-worth-knowing)
- [Troubleshooting](#troubleshooting)
- [Command line](#command-line)
- [Privacy](#privacy)
- [Adding a controller](#adding-a-controller)
- [How it was made](#how-it-was-made)
- [License](#license)

## What you need

- A PC running **Windows 10 or 11**, or a Mac running **macOS 11 (Big Sur) or newer**. Linux may
  work but isn't tested (see [Other platforms](#other-platforms)).
- An **addressable** LED strip (WS2812B, SK6812, WS2815 and similar, where each LED can show
  its own color) with a **controller the PC can talk to**: plugged into the PC over USB, or on
  your network running WLED, or connected to a motherboard ARGB header that OpenRGB supports.

## Supported controllers

| Controller | How it connects | Notes |
|---|---|---|
| **Robobloq SyncLight** | USB (HID, ID `1A86:FE07`) | Replaces Robobloq's SyncLight app for screen sync. Reports its LED count. |
| **Adalight** devices | USB serial / COM port | Arduino or ESP boards running Adalight-compatible firmware, Prismatik/Lightpack-style DIY builds, and ready-made kits that use the Adalight protocol. |
| **WLED** | Wi-Fi or Ethernet (UDP) | Any ESP8266/ESP32 running [WLED](https://kno.wled.ge). Reports its LED count. |
| **OpenRGB** | OpenRGB SDK server (TCP) | Motherboard ARGB headers, RGB controllers and many branded products that [OpenRGB](https://openrgb.org) supports. *Experimental.* |
| **None (preview only)** | n/a | No hardware. Shows the effect in the window, for trying the app or planning a layout. |

Layouts can be any mix of left, top, right and bottom edges, start at any corner, run either
direction, and skip a gap for a monitor stand, so most physical setups can be described.

## Will my strip work?

**Probably yes** if:

- Its controller box plugs into the PC with a USB cable *and* the strip's own software does
  screen sync. Look in **Device Manager**: if the controller appears under **Ports (COM & LPT)**
  (often as "USB-SERIAL CH340", "CP210x" or "Arduino"), try the **Adalight** driver. On a Mac,
  a serial controller shows up as a port like `/dev/cu.usbserial-1420` or `/dev/cu.usbmodem…`
  (run `ls /dev/cu.*` in Terminal before and after plugging it in). If it's a
  Robobloq kit, use the **Robobloq** driver. **Find devices** in the app lists what it can see.
- It's an ESP-based controller that runs (or can be flashed with) **WLED**.
- It's plugged into a motherboard **ARGB header** that OpenRGB can control.

**Probably not** if:

- It's controlled only by a **phone app over Bluetooth or Wi-Fi** (most Govee, "Magic Home",
  Tuya / Smart Life, Philips Hue, Nanoleaf and similar), unless you replace the controller.
- It uses an **IR remote** only, or it's a plain 12 V **RGB** strip (4 wires, the whole strip is
  one color). These aren't addressable, so they can't show different colors per LED.
- It's a **camera-based** or **HDMI sync box** kit. Those work without a PC and use their own
  protocols.
- It's a USB kit whose controller uses its own undocumented protocol. You can
  [add a driver](#adding-a-controller) if you can work out the protocol.

When in doubt, check that the strip's manufacturer offers PC screen sync software. If they do,
the controller talks to the PC, and it may be Adalight-compatible.

## Install

### Option A: download the app (easiest)

**Windows**

1. Download `AmbiEdge.exe` from the [Releases page](https://github.com/KorbSoft/AmbiEdge/releases).
2. Double-click it. No installation needed.

Windows SmartScreen will probably warn that the app is from an "unknown publisher", because the
file isn't code-signed (signing certificates cost money and this is a free project). Click
**More info → Run anyway** if you trust the download. Some antivirus programs also flag
PyInstaller-built apps by mistake. If you'd rather not run a prebuilt file, use option B: the
source is all here to read.

**macOS** (Apple Silicon; on an Intel Mac, use option B)

1. Download `AmbiEdge-macOS.zip` from the [Releases page](https://github.com/KorbSoft/AmbiEdge/releases),
   double-click it to unzip, and drag **AmbiEdge** into **Applications**.
2. Open it. Because the app isn't notarized by Apple (that needs a paid developer account), macOS
   will refuse the first time. Go to **System Settings → Privacy & Security**, scroll down and
   click **Open Anyway** next to the message about AmbiEdge, then confirm.
3. The first time you click **Start sync**, macOS asks for **Screen Recording** permission.
   Allow it in **System Settings → Privacy & Security → Screen Recording** (called **Screen &
   System Audio Recording** on macOS 15 and later), then quit AmbiEdge and open it again. macOS
   only applies the permission after a restart of the app. Each new release is a new app to
   macOS, so you may have to turn the permission off and on again after updating.

### Option B: run from source

**Windows**

1. Install **Python 3.9 or newer** from [python.org](https://www.python.org/downloads/). Tick
   **Add python.exe to PATH** during setup.
2. Download this repository (**Code → Download ZIP**, then extract it) or `git clone` it.
3. Double-click **`setup.bat`** once. It creates a `.venv` folder and installs the dependencies.
4. Double-click **`start.bat`** to run AmbiEdge.

Or by hand:

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m ambiedge
```

**macOS**

1. Install **Python 3.9 or newer** from [python.org](https://www.python.org/downloads/macos/). Its
   installer includes Tk, which the window needs. (With Homebrew Python, also run
   `brew install python-tk`.)
2. Download this repository (**Code → Download ZIP**) or `git clone` it.
3. Double-click **`setup.command`** once. The first time, macOS may block it: right-click it,
   choose **Open**, and confirm (or allow it under **System Settings → Privacy & Security**).
4. Double-click **`start.command`** to run AmbiEdge.

Or by hand:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m ambiedge
```

When run from source, macOS asks for Screen Recording permission for the app that started
Python, usually **Terminal**. Turn it on for that app, then start AmbiEdge again.

`pip install .` also installs `ambiedge` (console) and `ambiedge-gui` (no console) commands.

## First-time setup

1. **Close your strip's own app** (SyncLight, Prismatik, the vendor's sync tool and so on), or
   the two will fight over the lights.
2. **Device tab:** pick your controller, or click **Find devices...** and choose from the list.
   - Adalight: choose the COM port (on a Mac, the `/dev/cu.…` port) and the baud rate your firmware uses.
   - WLED: enter the device's IP address (shown in the WLED app).
   - OpenRGB: start OpenRGB, open its **SDK Server** tab, click **Start Server**, then pick the device number.
3. **Layout tab:** enter how many LEDs are on each edge, as seen from the **front** of the
   screen, plus the corner LED 1 sits at and which way the strip runs. Or click **Fit to LED
   count...**: enter the strip's total (pre-filled when the controller reports it) and AmbiEdge
   splits it over the edges to match the screen's shape. Fine-tune after testing.
4. Click **Test layout**. Left should be **red**, top **green**, right **blue** and bottom
   **yellow**. The first LED of each edge (going clockwise) is white and **LED 1 blinks**.
   - Colors change before or after the corners: adjust the edge counts.
   - Everything is mirrored: change the direction or the starting corner.
   - LED 1 isn't exactly at a corner: use **Shift start by**.
   - Red shows as green (or similar): change **Color order** (many WS2812B strips are GRB).
5. Click **Start sync**, or **Mood light** for a plain color or slow effect.

The preview at the top of the window shows the layout and the live colors, with LED 1 and the
last LED numbered. Settings save automatically.

## Settings

**Layout**

- **Left / Top / Right / Bottom**: LEDs on each edge. Use 0 for edges without LEDs.
- **Bottom gap**: how many LEDs would fit in a gap in the middle of the bottom edge (for a stand).
- **LED 1 is at / Going**: the corner the strip starts at and the direction it runs, seen from the front.
- **Shift start by**: moves LED 1 along the strip when it doesn't start exactly at a corner.
- **Color order**: the order your strip expects red, green and blue in.
- **Fit to LED count**: fills in the edge counts from the strip's total LED count.

**Look** (saved per profile)

- **Profile**: which profile you're editing.
- **Brightness**: overall brightness.
- **Color boost**: increases saturation, since edge averages often look washed out.
- **Vivid colors**: gives bright, saturated pixels more weight than gray ones when averaging, so
  small colorful details still show. 0 is a plain average.
- **Smoothing**: higher fades more slowly and flickers less.
- **Edge depth**: how far into the screen each LED looks (a fraction of the screen).
- **Gamma**: values above 1 deepen dim colors; often looks more natural on WS2812 strips.
- **Ignore black bars**: samples inside letterboxed video instead of the black bars.

**Profiles**

- Each profile has its own Look settings. AmbiEdge comes with **Desktop**, **Movie** (smoother,
  with common video players already listed) and **Game** (faster).
- **Use this profile while these apps are in front**: program file names such as `vlc.exe`
  on Windows, or app names such as `iina` or `quicktime player` on macOS, separated by commas. **Choose...** lists the programs that have a window open.
- **Switch profiles automatically by the app in front**: when none of the listed apps is in
  front, the profile selected on the Look tab is used.

**Mood**

- **Color**, with quick presets, and an **Effect**: solid, breathe (a slow pulse), color cycle or
  rainbow. All effects change slowly on purpose. **Brightness** is separate from screen sync.

**Schedule**

- **Turn the lights off while the display sleeps, the PC is locked or the PC is asleep**: the
  lights fade out and come back when you return. On by default. (Windows and macOS.)
- **Only turn the lights on between ... and ...**: a daily schedule, 24-hour times. An off time
  earlier than the on time spans midnight (for example 18:00 to 01:00).
- **When AmbiEdge opens**: do nothing, start screen sync, or turn on the mood light.
- **Start AmbiEdge when I sign in to Windows** / **when I log in to this Mac**: it starts hidden in
  the tray or menu bar. On macOS this adds a login item (a LaunchAgent in
  `~/Library/LaunchAgents`), which macOS lists under **System Settings → General → Login Items**.
- **Closing the window keeps AmbiEdge running in the tray** (or menu bar): on by default.

**Advanced**

- **FPS**: updates per second. 30 is plenty; higher uses more CPU and bandwidth.
- **Monitor #**: which screen to follow. 0 is usually the main one.
- **Capture**: Automatic uses DXGI on Windows and falls back to GDI. macOS always uses mss
  (CoreGraphics).
- **LEDs per zone**: values above 1 average neighboring LEDs into larger zones.
- **Max power**: limits R+G+B per LED (0 to 765). See [Safety](#safety).
- **White balance**: scales red, green and blue if white looks tinted.

## Tray icon

**Windows**

On Windows, AmbiEdge puts an icon in the notification area (next to the clock). It's colorful
while the lights are on and gray while they're off or paused. Hover it to see what it's doing.

- **Click** it to open the window.
- **Right-click** it for **Screen sync**, **Mood light**, **Off**, **Brightness** (sets the
  brightness of the profile in use, or of the mood light), **Profile**, and **Quit**.

Closing the window hides it to the tray; use **Quit** in the tray menu to exit. If you can't see
the icon, click the arrow next to the clock, and drag the icon out to keep it visible.

**macOS**

AmbiEdge puts an icon in the menu bar, colorful while the lights are on and gray while they're
off. **Click** it for the same menu, including **Open AmbiEdge**. Closing the window keeps
AmbiEdge running there; clicking its Dock icon also brings the window back. **Quit** in the menu,
or Cmd+Q, turns the lights off and exits. If the menu bar is full, the icon can be hidden behind
the notch on MacBooks: quit a few other menu bar apps, or use a menu bar manager.

## Safety

- **Photosensitive epilepsy:** fast-changing, flashing light can trigger seizures in people with
  photosensitive epilepsy, and fast flicker is unpleasant for many others. Games and videos can
  flash quickly. Raise **Smoothing**, lower **Brightness**, or don't use screen sync if this
  could affect you or anyone in the room.
- **Power:** each WS2812-type LED can draw about 60 mA at full white (5 V strips). 60 LEDs at
  full white is about 3.6 A, far more than a USB port supplies (0.5 to 3 A). The default **Max
  power** of 255 per LED keeps most USB-powered strips within safe limits. Raise it only if the
  strip has a separate power supply rated for the current, and keep in mind that brightness can
  spike suddenly, for example on a white loading screen.
- **Heat and wiring:** don't cover strips or controllers, don't run a strip from a supply that
  gets hot, and use wiring rated for the current. Turn the lights off when you're away.
- **Firmware and hardware:** AmbiEdge only sends color data. It never flashes firmware or
  changes controller settings. Even so, sending data to the wrong device or with wrong settings
  is at your own risk.

## Things worth knowing

- **Streaming services can show black.** Netflix, Disney+ and other DRM-protected video in a
  browser or app is usually blocked from screen capture, so the LEDs stay dark. Turning off
  hardware acceleration in the browser sometimes helps; it's a limitation of the platform, not
  this app.
- **HDR:** with Windows HDR turned on (or on an HDR / XDR Mac display showing HDR video),
  captured colors can look washed out or dim. Try raising
  Color boost or Gamma, or turn HDR off while syncing.
- **Games:** borderless/windowed fullscreen works best. Some games in exclusive fullscreen
  can't be captured.
- **The taskbar** sits on the bottom edge when you're not in fullscreen, so bottom LEDs show
  its color. On a Mac the menu bar (top) and the Dock do the same.
- **Lock screen, display sleep and PC sleep** turn the lights off (fading over a second) and
  back on when you return, unless you untick that option on the Schedule tab. UAC prompts and
  resolution changes pause capture briefly; AmbiEdge resumes by itself.
- **WLED and paused lights:** while paused, AmbiEdge keeps sending "off" so WLED doesn't switch
  back to its own effect. Quitting AmbiEdge hands the strip back to WLED.
- **Unplugging the controller** is fine: AmbiEdge keeps retrying and reconnects when it's back.
- **Only one copy runs at a time**, so two copies can't fight over the lights.
- **Serial speed limits FPS:** 115200 baud carries about 120 LEDs at 30 fps. For longer strips,
  use a higher baud rate in both the firmware and the app. Many Arduino boards reset when the
  port opens, so the first frame takes about two seconds.
- **WLED** goes back to its normal effect two seconds after AmbiEdge stops sending. WLED's own
  LED count, color order and current limiter still apply, so leave Color order at RGB here.
- **OpenRGB** switches the device to its direct/custom mode while syncing.
- **CPU use** is low: frames are downscaled before sampling, and unchanged colors are only resent
  once a second.
- Settings are in `%APPDATA%\AmbiEdge\config.json` on Windows and
  `~/Library/Application Support/AmbiEdge/config.json` on macOS, with a log in `ambiedge.log`
  next to it. Delete the config file to reset everything.
- **macOS specifics:** capture needs the Screen Recording permission (see [Install](#install)).
  macOS 15 and later may ask you every so often to confirm that AmbiEdge can keep recording the
  screen; that's macOS, not AmbiEdge. Sleep is detected only while the window app is running
  (not with `--headless`); display sleep and the lock screen are detected in both. Retina screens
  are captured at full resolution, so CPU use is a bit higher than on Windows; lower **FPS** if
  it matters.

### Other platforms

Windows and macOS have full support. On Linux, capture uses `mss`, which needs an X11 session
(Wayland isn't supported), and USB devices may need a udev rule for access. The tray icon,
automatic profile switching and turning off with the display aren't available on Linux yet; the
schedule works everywhere. Reports from people who try it are welcome.

## Troubleshooting

| Problem | Try |
|---|---|
| "No Robobloq controller found" | Check the cable and USB port. Close SyncLight. |
| "Can't open COM3" | Another app (Arduino IDE serial monitor, Prismatik, the vendor app) has the port open. Close it. |
| Serial device connects but LEDs stay dark | Wrong baud rate or the firmware doesn't speak Adalight. Check the firmware's settings. |
| WLED doesn't react | Check the IP address, that the PC and WLED are on the same network, and that the firewall allows outgoing UDP. In WLED, make sure "Receive UDP realtime" is on. |
| "Can't reach the OpenRGB SDK server" | Start OpenRGB and click **Start Server** on its SDK Server tab. |
| Wrong colors | Change Color order. |
| Colors shifted around the screen | Recheck the edge counts, the starting corner and the direction with Test layout. |
| Wrong screen | Change Monitor #. |
| LEDs flicker | Raise Smoothing. Check the strip's power supply and data wiring. |
| Some LEDs stay off at the end | The layout has fewer LEDs than the strip. The status line says how many the device reports, when it can tell. Try Fit to LED count. |
| Lights turn off by themselves | The display went to sleep, the PC locked, or it's outside the schedule. The status line says which. Change it on the Schedule tab. |
| Wrong profile is used | Check the Profiles tab: "In use now" shows which profile is active and why. |
| No tray icon | Click the arrow next to the clock. Windows may hide new icons there. |
| Mac: LEDs only follow the wallpaper, or "AmbiEdge needs permission to see the screen" | Turn on Screen Recording for AmbiEdge (or for Terminal, when run from source) in System Settings → Privacy & Security, then quit and reopen AmbiEdge. |
| Mac: "AmbiEdge can't be opened" / "Apple could not verify…" | System Settings → Privacy & Security → **Open Anyway**. See [Install](#install). |
| Mac: no serial port listed | Use the `/dev/cu.…` port, not `/dev/tty.…`. Some CH340 boards on older macOS need the maker's driver. |

If something else goes wrong, open an [issue](https://github.com/KorbSoft/AmbiEdge/issues) with
your controller model and the contents of `%APPDATA%\AmbiEdge\ambiedge.log` (macOS:
`~/Library/Application Support/AmbiEdge/ambiedge.log`; run with `--debug` for more detail).

## Command line

```text
ambiedge                 open the window
ambiedge --minimized     start hidden in the tray / menu bar
ambiedge --headless      sync with the saved settings, no window (Ctrl+C stops)
ambiedge --headless --mood
ambiedge --headless --test-pattern
ambiedge --list-devices  list detected controllers
ambiedge --config PATH   use a different settings file
ambiedge --debug         verbose logging
```

From source, use `python -m ambiedge` with the same options.

## Privacy

AmbiEdge runs entirely on your PC. Screen images are processed in memory to work out the edge
colors and are never saved or sent anywhere. There's no telemetry, no account and no internet
connection. The only network traffic is to a WLED device or OpenRGB server **you** configure.

## Adding a controller

Drivers live in [`ambiedge/drivers/`](ambiedge/drivers). Each one is a small class:

```python
from .base import DeviceNotFound, Driver

class MyDriver(Driver):
    key = "mydriver"                  # stored in the config
    label = "My controller (USB)"     # shown in the UI
    option_keys = ("my_port",)        # settings it reads; add defaults in config.py

    def open(self):                   # raise DeviceNotFound if it isn't there
        ...
    def send(self, colors):           # (n, 3) uint8 array, LED 1 first
        ...
    def close(self):
        ...
```

Register it in `DRIVERS` in `ambiedge/drivers/__init__.py`, add an `_options_<key>` method in
`gui.py` for its settings, and add tests for its packet format in `tests/`. Run the tests with:

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

Pull requests are welcome, especially drivers for more controllers and reports of hardware that
works.

## How it was made

AmbiEdge was made with the help of AI. Most of the code and documentation were written with
Claude, Anthropic's AI assistant, directed by the project's author. Commits made this way are
marked with a `Co-Authored-By: Claude` line, so you can see exactly which parts.

It has been tested on real hardware with a Robobloq SyncLight strip on Windows 11. The Adalight,
WLED and OpenRGB drivers have so far only been tested against simulated devices, so reports from
people with that hardware (working or not) are especially welcome. Please
[open an issue](https://github.com/KorbSoft/AmbiEdge/issues/new/choose).

## Disclaimer

AmbiEdge is an independent project. It is **not affiliated with, endorsed by or supported by**
Robobloq, WLED, OpenRGB, Adafruit or any LED or hardware manufacturer. Product names are
trademarks of their owners and are used only to describe compatibility. The Robobloq protocol
was worked out independently, for interoperability with hardware the user owns.

## License

AmbiEdge is free and open-source software, released under the
[GNU General Public License v3.0 or later](LICENSE). Copyright (C) 2026 KorbSoft.

You can use it for anything, study and change the code, and share it, including your changed
versions. If you distribute a modified version or something built on AmbiEdge, it has to be
released under the same license, with its source code. See [LICENSE](LICENSE) for the exact
terms.

The software is provided without any warranty, as described in the license. Use it at your own
risk.
