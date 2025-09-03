# UWW-Net Configuration

This file contains all customizable settings for the UltraWideWallpapers network fetcher.

## Settings

### destination_folder
- **Type**: string
- **Default**: "C:\\media\\wallpapers"
- **Description**: The folder where downloaded wallpapers will be stored.

### verbose_logging
- **Type**: boolean
- **Default**: true
- **Description**: Enable/disable detailed logging output.

### interval_seconds
- **Type**: integer
- **Default**: 600
- **Description**: Time interval between wallpaper fetch cycles in seconds (10 minutes by default).

### aspect_ratio
- **Type**: object
- **Default**: {"width": 16, "height": 9}
- **Description**: The aspect ratio to crop wallpapers to. Used for monitor compatibility.

### temp_dir_prefix
- **Type**: string
- **Default**: "uww_dl_"
- **Description**: Prefix for temporary directories created during downloads.

### history_file
- **Type**: string
- **Default**: "download_history.txt"
- **Description**: Filename for storing download history to avoid duplicates.

### wallpaper_source
- **Type**: object
- **Description**: Settings related to the wallpaper source website.

#### wallpaper_source.url
- **Type**: string
- **Default**: "https://ultrawidewallpapers.net/gallery"
- **Description**: The URL of the wallpaper gallery to scrape.

#### wallpaper_source.max_shuffles
- **Type**: integer
- **Default**: 25
- **Description**: Maximum number of shuffle attempts to find unique wallpapers.

#### wallpaper_source.webdriver_timeout
- **Type**: integer
- **Default**: 10
- **Description**: Timeout in seconds for WebDriver operations.

#### wallpaper_source.shuffle_timeout
- **Type**: integer
- **Default**: 5
- **Description**: Timeout in seconds for shuffle button operations.

#### wallpaper_source.window_size
- **Type**: string
- **Default**: "1920,1080"
- **Description**: Browser window size for headless Chrome operations.
