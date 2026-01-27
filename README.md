# UWW-Net - UltraWideWallpapers Network Fetcher

A Python application that automatically downloads wallpapers from ultrawidewallpapers.net and sets them as your system wallpaper.

## Features

- **Automatic Wallpaper Downloads**: Fetches wallpapers from ultrawidewallpapers.net
- **Multi-Monitor Support**: Detects and handles multiple monitors
- **Wallpaper Stitching**: Option to stitch multiple wallpapers into a single large image spanning all monitors
- **Brightness Filtering**: Automatically skips overly bright images that might be uncomfortable for light-sensitive eyes
- **System Tray Integration**: Runs in the background with a system tray icon
- **Duplicate Prevention**: Tracks downloaded wallpapers to avoid duplicates
- **Aspect Ratio Cropping**: Crops wallpapers to match monitor aspect ratios

## Installation

1. Install required dependencies:

   ```bash
   pip install requests Pillow pystray screeninfo selenium
   ```

2. For Chrome WebDriver (required for scraping):
   - Download ChromeDriver from https://chromedriver.chromium.org/
   - Place it in your system PATH

## Configuration

Edit `config.json` to customize settings:

- `stitch_wallpapers`: Set to `true` to enable wallpaper stitching, `false` for individual wallpapers
- `destination_folder`: Folder where wallpapers are stored
- `interval_seconds`: Time between automatic downloads
- `verbose_logging`: Enable detailed logging
- `brightness_threshold`: Maximum average brightness (0-255) allowed for wallpapers. Images with average brightness >= this value are silently discarded and replaced. Default is 200.0. Lower values are stricter (e.g., 150 for darker wallpapers, 220 for brighter ones).

## Usage

### Command Line

```bash
# Run once and exit
python uww-net-main.pyw --once

# Run with custom interval
python uww-net-main.pyw --interval 1800

# Run without clearing console
python uww-net-main.pyw --no-clear
```

### System Tray

When running normally, the application runs in the background with a system tray icon. Right-click the icon for options:

- **Run Now**: Download wallpapers immediately
- **Toggle Console**: Show/hide the console window
- **Toggle Logging**: Enable/disable verbose logging
- **Toggle Wallpaper Stitching**: Switch between stitched and individual wallpapers
- **Restart**: Restart the application
- **Exit**: Close the application

## Wallpaper Stitching

When `stitch_wallpapers` is enabled:

1. Downloads one wallpaper per monitor
2. Creates a single large image that spans all monitors
3. Sets the stitched image as the system wallpaper

When disabled (default):

1. Downloads wallpapers for each monitor
2. Sets the first downloaded wallpaper as the system wallpaper

## Monitor Detection

The application automatically detects your monitor setup using:

1. `screeninfo` library (recommended)
2. Windows ctypes API
3. Tkinter fallback

## Files

- `uww-net-main.pyw`: Main application
- `wallpaper_scraper.py`: Web scraping functionality
- `image_utils.py`: Image processing and wallpaper setting
- `monitors.py`: Monitor detection
- `download_history.txt`: Tracks downloaded wallpapers
- `config.json`: Configuration settings

## Troubleshooting

- Ensure ChromeDriver is installed and in PATH
- Check that destination folder exists and is writable
- Verify monitor detection works (run with verbose logging)
- For stitching issues, ensure you have one wallpaper per monitor
