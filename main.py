import os
import json
import random
from datetime import datetime, time
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

# ================= ENV =================
DRIVE_TOKEN = os.getenv("DRIVE_TOKEN_JSON_A")
YOUTUBE_TOKEN = os.getenv("YOUTUBE_TOKEN_JSON_B")
PENDING_FOLDER_ID = os.getenv("PENDING_FOLDER_ID")
UPLOADED_FOLDER_ID = os.getenv("UPLOADED_FOLDER_ID")

if not all([DRIVE_TOKEN, YOUTUBE_TOKEN, PENDING_FOLDER_ID, UPLOADED_FOLDER_ID]):
    raise Exception("Missing environment variables")

# ================= AUTH =================
drive_creds = Credentials.from_authorized_user_info(json.loads(DRIVE_TOKEN))
youtube_creds = Credentials.from_authorized_user_info(json.loads(YOUTUBE_TOKEN))

drive = build("drive", "v3", credentials=drive_creds)
youtube = build("youtube", "v3", credentials=youtube_creds)

# ================= TITLES =================
def get_title_from_file(path="titles.txt"):
    with open(path, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]

    if not lines:
        raise Exception("titles.txt empty")

    line = lines[0]

    if "|" not in line:
        raise Exception("Invalid format: Title | #tag #tag")

    title_part, hashtag_part = line.split("|", 1)
    title = title_part.strip()
    hashtags = " ".join(
        h for h in hashtag_part.strip().split() if h.startswith("#")
    )

    final_title = f"{title} {hashtags}".strip()

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines[1:]))

    return final_title

# ================= DRIVE =================
def get_video_file():
    res = drive.files().list(
        q=f"'{PENDING_FOLDER_ID}' in parents and trashed=false",
        fields="files(id,name,mimeType,shortcutDetails)"
    ).execute()

    files = res.get("files", [])
    if not files:
        raise Exception("No video found")

    return random.choice(files)

def resolve_shortcut(file):
    if file["mimeType"] == "application/vnd.google-apps.shortcut":
        return drive.files().get(
            fileId=file["shortcutDetails"]["targetId"],
            fields="id,name,mimeType"
        ).execute()
    return file

def download_video(file):
    request = drive.files().get_media(fileId=file["id"])
    filename = file["name"]

    with open(filename, "wb") as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

    return filename

def move_file(file_id):
    drive.files().update(
        fileId=file_id,
        addParents=UPLOADED_FOLDER_ID,
        removeParents=PENDING_FOLDER_ID,
        fields="id"
    ).execute()

# ================= SCHEDULE =================
def get_publish_time():
    ist = ZoneInfo("Asia/Kolkata")
    now = datetime.now(ist)
    publish_time = datetime.combine(now.date(), time(14, 0), ist)
    return publish_time

# ================= YOUTUBE =================
def upload_to_youtube(video_path, title, publish_time):
    body = {
        "snippet": {
            "title": title,
            "description": "",
            "categoryId": "24"
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": publish_time.astimezone(
                ZoneInfo("UTC")
            ).isoformat(),
            "selfDeclaredMadeForKids": False
        }
    }

    media = MediaFileUpload(video_path, resumable=True)

    res = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    ).execute()

    return res["id"]

# ================= MAIN =================
def main():
    print("🚀 Dual-account automation started")

    title = get_title_from_file()
    print("📝 Title:", title)

    file = get_video_file()
    file = resolve_shortcut(file)

    video_path = download_video(file)
    print("⬇ Downloaded from Drive A:", video_path)

    publish_time = get_publish_time()
    video_id = upload_to_youtube(video_path, title, publish_time)

    print("✅ Uploaded to Channel B:", video_id)

    move_file(file["id"])
    print("📁 Moved file in Drive A")

if __name__ == "__main__":
    main()
