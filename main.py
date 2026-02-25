import os
import json
import random
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload


# ================= ENV =================
TOKEN_JSON = os.getenv("GOOGLE_TOKEN_JSON")

PENDING_FOLDER_ID_0 = os.getenv("PENDING_FOLDER_ID_0")
PENDING_FOLDER_ID_1 = os.getenv("PENDING_FOLDER_ID_1")

UPLOADED_FOLDER_ID = os.getenv("UPLOADED_FOLDER_ID")

if not all([TOKEN_JSON, PENDING_FOLDER_ID_0, PENDING_FOLDER_ID_1, UPLOADED_FOLDER_ID]):
    raise Exception("Missing environment variables")


# ================= AUTH =================
creds = Credentials.from_authorized_user_info(json.loads(TOKEN_JSON))

drive = build("drive", "v3", credentials=creds)
youtube = build("youtube", "v3", credentials=creds)


# ================= TITLE =================
def get_title_from_file(path="titles.txt"):
    with open(path, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    if not lines:
        raise Exception("titles.txt empty")

    line = lines[0]

    if "|" in line:
        title_part, tag_part = line.split("|", 1)
        title = title_part.strip()
        tags = [t.strip() for t in tag_part.split(",") if t.strip()]
    else:
        title = line
        tags = [w[1:] for w in title.split() if w.startswith("#")]

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines[1:]))

    return title, tags


# ================= DRIVE =================
def list_folder(folder_id):
    res = drive.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        fields="files(id,name,mimeType,shortcutDetails)"
    ).execute()

    return res.get("files", [])


def pick_video():
    files_priority = list_folder(PENDING_FOLDER_ID_1)

    if files_priority:
        print("Using PRIORITY folder")
        return random.choice(files_priority), PENDING_FOLDER_ID_1

    files_fallback = list_folder(PENDING_FOLDER_ID_0)

    if files_fallback:
        print("Using FALLBACK folder")
        return random.choice(files_fallback), PENDING_FOLDER_ID_0

    raise Exception("No video in any pending folder")


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


# ================= SCHEDULE =================
def get_schedule_time():
    ist = ZoneInfo("Asia/Kolkata")
    now = datetime.now(ist)

    target = datetime.combine(now.date(), time(14, 0), ist)

    if now >= target:
        target = target + timedelta(days=1)

    return target


# ================= UPLOAD =================
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


# ================= MAIN =================
def main():
    print("Bot started")

    title, tags = get_title_from_file()
    print("Title:", title)
    print("Tags:", tags)

    file, source_folder = pick_video()
    file = resolve_shortcut(file)

    video_path = download_video(file)
    print("Downloaded:", video_path)

    publish_time = get_schedule_time()
    print("Scheduled IST:", publish_time)

    vid = upload(video_path, title, tags, publish_time)
    print("Uploaded:", vid)

    move_file(file["id"], source_folder)
    print("Moved to uploaded folder")


if __name__ == "__main__":
    main()
