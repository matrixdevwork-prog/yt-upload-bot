import os
import json
import random
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload


# ========= ENV =========
TOKEN_JSON = os.getenv("GOOGLE_TOKEN_JSON")

PENDING_FOLDER_0 = os.getenv("PENDING_FOLDER_ID_0")
PENDING_FOLDER_1 = os.getenv("PENDING_FOLDER_ID_1")

UPLOADED_FOLDER_ID = os.getenv("UPLOADED_FOLDER_ID")

if not all([TOKEN_JSON, PENDING_FOLDER_0, PENDING_FOLDER_1, UPLOADED_FOLDER_ID]):
    raise Exception("Missing environment variables")


# ========= AUTH =========
creds = Credentials.from_authorized_user_info(json.loads(TOKEN_JSON))

drive = build("drive", "v3", credentials=creds)
youtube = build("youtube", "v3", credentials=creds)


# ========= TITLE =========
def get_title_from_file(path="titles.txt"):
    with open(path, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    if not lines:
        raise Exception("titles.txt empty")

    title = lines[0]

    # remove used line
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines[1:]))

    # extract tags from hashtags
    tags = [w[1:] for w in title.split() if w.startswith("#")]

    return title, tags


# ========= DRIVE =========
def list_files(folder_id):
    res = drive.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        fields="files(id,name,mimeType,shortcutDetails)"
    ).execute()

    return res.get("files", [])


def pick_video():
    # 🔥 priority folder first
    files = list_files(PENDING_FOLDER_1)

    if files:
        print("📁 Using priority folder")
        return random.choice(files), PENDING_FOLDER_1

    print("📁 Using fallback folder")
    files = list_files(PENDING_FOLDER_0)

    if not files:
        raise Exception("No videos in both folders")

    return random.choice(files), PENDING_FOLDER_0


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


def move_file(file_id, from_folder):
    drive.files().update(
        fileId=file_id,
        addParents=UPLOADED_FOLDER_ID,
        removeParents=from_folder,
        fields="id, parents"
    ).execute()


# ========= SCHEDULE =========
def get_schedule_time():
    ist = ZoneInfo("Asia/Kolkata")
    now = datetime.now(ist)

    target = datetime.combine(now.date(), time(14, 0), ist)

    if now >= target - timedelta(hours=2):
        target = datetime.combine(now.date() + timedelta(days=1), time(14, 0), ist)

    return target


# ========= YOUTUBE =========
def upload(video_path, title, tags, publish_time):
    body = {
        "snippet": {
            "title": title,
            "description": "",
            "tags": tags,
            "categoryId": "24"
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": publish_time.astimezone(ZoneInfo("UTC")).isoformat(),
            "selfDeclaredMadeForKids": False
        }
    }

    media = MediaFileUpload(video_path, resumable=True)

    req = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )

    res = req.execute()
    return res["id"]


# ========= MAIN =========
def main():
    print("🚀 Bot started")

    title, tags = get_title_from_file()
    print("📝 Title:", title)

    file, source_folder = pick_video()
    file = resolve_shortcut(file)

    video_path = download_video(file)
    print("⬇️ Downloaded:", video_path)

    schedule_time = get_schedule_time()
    print("⏰ Scheduled IST:", schedule_time)

    video_id = upload(video_path, title, tags, schedule_time)
    print("✅ Uploaded:", video_id)

    move_file(file["id"], source_folder)
    print("📦 Moved to uploaded folder")


if __name__ == "__main__":
    main()
