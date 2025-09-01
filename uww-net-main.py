from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import os

def get_one_wallpaper_after_shuffle():
    # Initialize the WebDriver (e.g., Chrome)
    # Ensure ChromeDriver is set up correctly (see previous instructions).
    driver = webdriver.Chrome()
    # For headless mode (no browser window visible):
    # from selenium.webdriver.chrome.options import Options
    # options = Options()
    # options.add_argument('--headless')
    # driver = webdriver.Chrome(options=options)


    try:
        # 1. Navigate to the gallery page
        driver.get("https://ultrawidewallpapers.net/gallery")
        print("Navigated to gallery page.")

        # 2. Locate and click the "Shuffle" button
        try:
            # IMPORTANT: Replace this with the actual selector for the shuffle button
            # Based on inspection, a common pattern for sort/filter links is used here.
            shuffle_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "#shuffleButton"))
            )
            print("Found shuffle button.")
            shuffle_button.click()
            print("Shuffle button clicked. Waiting for content to reload...")

            # Wait for the content to reload after clicking shuffle.
            # A simple time.sleep is used for demonstration, but a more robust wait condition
            # (like waiting for staleness of old elements or disappearance of a loading spinner)
            # would be better in a production scenario.
            time.sleep(3) # Give time for new content to load
            print("Content likely reloaded after shuffle.")

        except Exception as e:
            print(f"Could not find or click the shuffle button: {e}")
            return None # Exit if shuffle fails

        # 3. Extract data from the first newly loaded wallpaper
        try:
            # Find all wallpaper elements
            wallpaper_elements = driver.find_elements(By.CSS_SELECTOR, "#galleryContainer .image-link")

            if not wallpaper_elements:
                print("No wallpapers found after shuffle.")
                return None

            # Get the first wallpaper element
            first_wallpaper_element = wallpaper_elements[0]
            print("Found the first wallpaper element.")

            # Extract details from the first wallpaper
            image_url = first_wallpaper_element.get_attribute("href")

            # You might need to inspect the HTML to find a title, categories, etc.
            # Example (adjust selectors based on actual HTML):
            # title_element = first_wallpaper_element.find_element(By.CLASS_NAME, "wallpaper-title")
            # title = title_element.text if title_element else "N/A"

            wallpaper_info = {
                "image_url": image_url,
                # "title": title, # Uncomment and adjust if a title exists
                # ... add other relevant data here
            }

            return wallpaper_info

        except Exception as e:
            print(f"Error extracting data from the first wallpaper: {e}")
            return None

    finally:
        driver.quit() # Close the browser

# To run the program:
if __name__ == "__main__":
    wallpaper_data = get_one_wallpaper_after_shuffle()
    if wallpaper_data:
        print("\nSuccessfully extracted data for one wallpaper after shuffle:")
        print(wallpaper_data)
    else:
        print("\nFailed to extract wallpaper data.")