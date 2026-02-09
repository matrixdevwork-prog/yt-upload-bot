import os
import json
import random
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload


# ================== ENV ==================
TOKEN_JSON = os.getenv("GOOGLE_TOKEN_JSON")
PENDING_FOLDER_ID = os.getenv("PENDING_FOLDER_ID")
UPLOADED_FOLDER_ID = os.getenv("UPLOADED_FOLDER_ID")

if not all([TOKEN_JSON, PENDING_FOLDER_ID, UPLOADED_FOLDER_ID]):
    raise Exception("❌ Missing environment variables")


# ================== AUTH ==================
creds = Credentials.from_authorized_user_info(json.loads(TOKEN_JSON))
drive = build("drive", "v3", credentials=creds)
youtube = build("youtube", "v3", credentials=creds)


# ================== TITLES ==================
# Format:
# Aree Hulk Gussa 😂 #hulkai #funny #viralshorts | hulkai,funny,viralshorts

def get_title_from_file(path="titles.txt"):
    with open(path, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]

    if not lines:
        raise Exception("❌ titles.txt empty")

    line = lines[0]

    if "|" not in line:
        raise Exception("❌ Invalid title format")

    title_part, tag_part = line.split("|", 1)
    title = title_part.strip()
    tags = [t.strip() for t in tag_part.split(",") if t.strip()]

    # remove used title
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines[1:]))

    return title, tags


# ================== DRIVE ==================
def get_video_file():
    res = drive.files().list(
        q=f"'{PENDING_FOLDER_ID}' in parents and trashed=false",
        fields="files(id,name,mimeType,shortcutDetails)"
    ).execute()

    files = res.get("files", [])
    if not files:
        raise Exception("❌ No video found in pending folder")

    return random.choice(files)


def resolve_shortcut(file):
    if file["mimeType"] == "application/vnd.google-apps.shortcut":
        target_id = file["shortcutDetails"]["targetId"]
        return drive.files().get(
            fileId=target_id,
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


# ================== SCHEDULE ==================
def get_schedule_time():
    ist = ZoneInfo("Asia/Kolkata")
    now = datetime.now(ist)

    target = datetime.combine(now.date(), time(14, 0), ist)

    # agar 1 ghanta pehle nahi chala to next day
    if now > target - timedelta(hours=1):
        target = datetime.combine(now.date() + timedelta(days=1), time(14, 0), ist)

    return target


# ================== YOUTUBE ==================
def upload_to_youtube(video_path, title, tags, publish_time):
    body = {
        "snippet": {
            "title": title,
            "description": "",
            "tags": tags,
            "categoryId": "24"  # Entertainment
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": publish_time.astimezone(ZoneInfo("UTC")).isoformat(),
            "selfDeclaredMadeForKids": False
        }
    }

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )

    response = request.execute()
    return response["id"]


# ================== MAIN ==================
def main():
    print("🚀 Bot started")

    title, tags = get_title_from_file()
    print("📝 Title:", title)
    print("🏷️ Tags:", tags)

    file = get_video_file()
    file = resolve_shortcut(file)

    video_path = download_video(file)
    print("⬇️ Downloaded:", video_path)

    publish_time = get_schedule_time()
    print("⏰ Scheduled (IST):", publish_time)

    video_id = upload_to_youtube(video_path, title, tags, publish_time)
    print("✅ Uploaded:", video_id)

    move_file(file["id"])
    print("📁 Moved video to uploaded folder")


if __name__ == "__main__":
    main()
