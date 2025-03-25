from __future__ import print_function
import os
import time
import json
import io
from datetime import datetime
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google.oauth2 import service_account

# === Configuration for Website Backup ===
BASE_URL = "https://www.chords-and-tabs.net"
MY_SONGS_URL = BASE_URL + "/mysongs/"
COOKIES_FILE = 'cookies.json'

# === Configuration for Google Drive Backup ===
PARENT_FOLDER_ID = "1HxvwceupKtXUymKNAtMQCdK7qHHiXKeh"  # Your Drive backup folder ID
SERVICE_ACCOUNT_FILE = "automatic-backup-church-songs-741cba4a6eed.json"
SCOPES = ["https://www.googleapis.com/auth/drive"]

# === Google Drive Authentication ===
# When running on GitHub Actions, you can store your credentials JSON as a secret and write it to a file.
if os.environ.get("GITHUB_ACTIONS"):
    # Write the service account JSON from the secret to a file
    with open(SERVICE_ACCOUNT_FILE, "w") as f:
        f.write(os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"))
credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES)
drive_service = build("drive", "v3", credentials=credentials)

# === Undetected Chrome Setup ===
options = uc.ChromeOptions()
options.add_argument("--start-maximized")
# When running on GitHub Actions, run headless
if os.environ.get("GITHUB_ACTIONS"):
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

driver = uc.Chrome(options=options)

def load_cookies():
    if os.environ.get("GITHUB_ACTIONS"):
        print("Running on GitHub Actions. Loading cookies from secret.")
        cookie_str = os.environ.get("CHORDS_AND_TABS_COOKIES", "[]")
        try:
            cookies = json.loads(cookie_str)
        except Exception as e:
            print("Error parsing cookies from secret:", e)
            cookies = []
        driver.get(MY_SONGS_URL)
        for cookie in cookies:
            # Remove attributes that might cause errors
            cookie.pop("sameSite", None)
            driver.add_cookie(cookie)
        driver.refresh()
        print("Cookies loaded from secret.")
    else:
        if os.path.exists(COOKIES_FILE):
            print("Loading cookies from file.")
            driver.get(MY_SONGS_URL)
            with open(COOKIES_FILE, "r") as f:
                cookies = json.load(f)
            for cookie in cookies:
                cookie.pop("sameSite", None)
                driver.add_cookie(cookie)
            driver.refresh()
            print("Cookies loaded from file.")
        else:
            print("No cookies file found. Please log in manually.")
            driver.get(MY_SONGS_URL)
            input("After signing in, press ENTER to continue...")
            cookies = driver.get_cookies()
            with open(COOKIES_FILE, "w") as f:
                json.dump(cookies, f)
            print("Cookies saved.")

load_cookies()
driver.get(MY_SONGS_URL)
time.sleep(5)

def create_timestamped_folder(service, parent_folder_id):
    now = datetime.now().strftime("Backup %Y-%m-%d %H-%M-%S")
    metadata = {
        "name": now,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_folder_id]
    }
    folder = service.files().create(body=metadata, fields="id, name").execute()
    print(f"Created Drive folder: {folder['name']} (ID: {folder['id']})")
    return folder["id"]

def upload_in_memory_file(service, folder_id, file_name, file_data, mimetype):
    file_metadata = {"name": file_name, "parents": [folder_id]}
    media = MediaIoBaseUpload(file_data, mimetype=mimetype, resumable=True)
    file = service.files().create(body=file_metadata, media_body=media, fields="id").execute()
    print(f"Uploaded {file_name} to Drive (ID: {file.get('id')})")
    return file.get("id")

def main():
    try:
        folder_id = create_timestamped_folder(drive_service, PARENT_FOLDER_ID)
        song_elements = driver.find_elements(By.XPATH, "//a[starts-with(@href, '/song/my/')]")
        song_links = [elem.get_attribute("href") for elem in song_elements]
        print(f"Found {len(song_links)} songs.")

        if not song_links:
            print("No songs found. Verify you're logged in and on the 'My Songs' page.")
            driver.quit()
            return

        for link in song_links:
            unique_id = link.split("/")[-1]
            edit_url = BASE_URL + "/mysong/edit/" + unique_id
            driver.get(edit_url)
            time.sleep(2)

            try:
                song_name = driver.find_element(By.ID, "frm-createNewSongForm-song").get_attribute("value").strip()
            except:
                song_name = f"Song_{unique_id}"
            try:
                song_text = driver.find_element(By.ID, "frm-createNewSongForm-text").get_attribute("value")
            except Exception as e:
                print(f"Could not extract text for {song_name}: {e}")
                continue

            safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in song_name)
            file_name = f"{safe_name}.txt"
            text_bytes = song_text.encode("utf-8")
            text_file = io.BytesIO(text_bytes)
            text_file.seek(0)
            upload_in_memory_file(drive_service, folder_id, file_name, text_file, "text/plain")
            time.sleep(1)
        driver.quit()
        print("Backup complete!")
    except KeyboardInterrupt:
        print("Backup interrupted by user.")
        driver.quit()
    except Exception as err:
        print(f"Backup failed: {err}")
        driver.quit()

if __name__ == '__main__':
    main()
