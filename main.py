import os
import json
import io
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from googleapiclient.errors import HttpError

# ---------------- CONFIG ----------------
IST = ZoneInfo("Asia/Kolkata")

GOOGLE_TOKEN_JSON = os.getenv("GOOGLE_TOKEN_JSON")
PENDING_FOLDER_ID = os.getenv("PENDING_FOLDER_ID")
UPLOADED_FOLDER_ID = os.getenv("UPLOADED_FOLDER_ID")

if not all([GOOGLE_TOKEN_JSON, PENDING_FOLDER_ID, UPLOADED_FOLDER_ID]):
    raise Exception("Missing required environment variables")

# ---------------- AUTH ----------------
creds = Credentials.from_authorized_user_info(
    json.loads(GOOGLE_TOKEN_JSON),
    scopes=[
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/youtube.upload",
    ],
)

drive = build("drive", "v3", credentials=creds)
youtube = build("youtube", "v3", credentials=creds)

# ---------------- TITLE HANDLER ----------------
def get_title_from_file(path="titles.txt"):
    with open(path, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]

    if not lines:
        raise Exception("titles.txt empty")

    first = lines[0]
    rest = lines[1:]

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(rest))

    title, tags = first.split("|")
    tags = [t.strip() for t in tags.split(",")]

    return title.strip(), tags

# ---------------- DRIVE ----------------
def resolve_shortcut(file):
    if file["mimeType"] == "application/vnd.google-apps.shortcut":
        target_id = file["shortcutDetails"]["targetId"]
        return drive.files().get(fileId=target_id, fields="id,name,mimeType").execute()
    return file

def download_video(file):
    request = drive.files().get_media(fileId=file["id"])
    fh = io.FileIO("video.mp4", "wb")
    downloader = MediaIoBaseDownload(fh, request)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    fh.close()

# ---------------- SCHEDULE LOGIC ----------------
def get_next_schedule():
    now = datetime.now(IST)

    today_8 = now.replace(hour=8, minute=0, second=0, microsecond=0)
    today_14 = now.replace(hour=14, minute=0, second=0, microsecond=0)

    if now < today_8:
        return today_8
    elif now < today_14:
        return today_14
    else:
        return (now + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)

# ---------------- MAIN ----------------
def main():
    print("🚀 Bot started")

    title, tags = get_title_from_file()
    print("📝 Title:", title)
    print("🏷️ Tags:", tags)

    results = drive.files().list(
        q=f"'{PENDING_FOLDER_ID}' in parents",
        fields="files(id,name,mimeType,shortcutDetails)",
        pageSize=1,
    ).execute()

    if not results["files"]:
        print("No pending videos")
        return

    file = resolve_shortcut(results["files"][0])
    print("📥 Downloading:", file["name"])
    download_video(file)

    schedule_time = get_next_schedule()
    print("⏰ Scheduled (IST):", schedule_time)

    body = {
        "snippet": {
            "title": title[:100],
            "description": f"{title}\n\n#shorts",
            "tags": tags[:15],
            "categoryId": "24",  # Entertainment
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": schedule_time.isoformat(),
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload("video.mp4", chunksize=-1, resumable=True)

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()

    video_id = response["id"]
    print("✅ Uploaded:", video_id)

    # Move file in Drive
    drive.files().update(
        fileId=file["id"],
        addParents=UPLOADED_FOLDER_ID,
        removeParents=PENDING_FOLDER_ID,
    ).execute()

    print("📁 Moved to uploaded folder")

# ---------------- RUN ----------------
if __name__ == "__main__":
    main()
