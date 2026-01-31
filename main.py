import os
import json
import random
import datetime
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# =======================
# ENV VARIABLES
# =======================
TOKEN_JSON = os.getenv("GOOGLE_TOKEN_JSON")
PENDING_FOLDER_ID = os.getenv("PENDING_FOLDER_ID")
UPLOADED_FOLDER_ID = os.getenv("UPLOADED_FOLDER_ID")

if not TOKEN_JSON:
    raise Exception("GOOGLE_TOKEN_JSON missing")

# =======================
# LOAD GOOGLE CREDS
# =======================
creds = Credentials.from_authorized_user_info(json.loads(TOKEN_JSON))
drive = build("drive", "v3", credentials=creds)
youtube = build("youtube", "v3", credentials=creds)

print("✅ Environment variables loaded")

# =======================
# READ TITLE FROM FILE
# =======================
def get_title_from_file(path="titles.txt"):
    with open(path, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]

    if not lines:
        raise Exception("titles.txt empty")

    line = lines.pop(0)

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    title_part, tag_part = line.split("|")
    title = title_part.strip()
    tags = [t.strip() for t in tag_part.split(",")]

    return title, tags

# =======================
# GET VIDEO FROM DRIVE
# =======================
def get_video_file():
    res = drive.files().list(
        q=f"'{PENDING_FOLDER_ID}' in parents and mimeType contains 'video/'",
        fields="files(id,name)"
    ).execute()

    files = res.get("files", [])
    if not files:
        raise Exception("No video found")

    return random.choice(files)

# =======================
# DOWNLOAD VIDEO
# =======================
def download_file(file_id, name):
    request = drive.files().get_media(fileId=file_id)
    with open(name, "wb") as f:
        f.write(request.execute())

# =======================
# MOVE FILE AFTER UPLOAD
# =======================
def move_file(file_id):
    drive.files().update(
        fileId=file_id,
        addParents=UPLOADED_FOLDER_ID,
        removeParents=PENDING_FOLDER_ID
    ).execute()

# =======================
# SCHEDULE TIME (IST)
# =======================
def get_publish_time():
    ist = ZoneInfo("Asia/Kolkata")
    now = datetime.datetime.now(ist)

    if now.hour < 7:
        publish = now.replace(hour=8, minute=0)
    elif now.hour < 13:
        publish = now.replace(hour=14, minute=0)
    else:
        publish = (now + datetime.timedelta(days=1)).replace(hour=8, minute=0)

    return publish.astimezone(datetime.timezone.utc).isoformat()

# =======================
# UPLOAD TO YOUTUBE
# =======================
def upload_video(path, title, tags, publish_time):
    body = {
        "snippet": {
            "title": title,
            "description": "",
            "tags": tags,
            "categoryId": "24"  # Entertainment
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": publish_time,
            "selfDeclaredMadeForKids": False
        }
    }

    media = MediaFileUpload(path, chunksize=-1, resumable=True)

    req = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )

    res = req.execute()
    return res["id"]

# =======================
# MAIN
# =======================
def main():
    print("🚀 Bot started")

    title, tags = get_title_from_file()
    print("📌 Title:", title)
    print("🏷️ Tags:", tags)

    video = get_video_file()
    print("🎬 Selected:", video["name"])

    download_file(video["id"], video["name"])
    print("⬇️ Download completed")

    publish_time = get_publish_time()
    print("⏰ Scheduled (UTC):", publish_time)

    video_id = upload_video(video["name"], title, tags, publish_time)
    print("✅ Uploaded. Video ID:", video_id)

    move_file(video["id"])
    print("📁 Moved file to uploaded folder")

if __name__ == "__main__":
    main()
