import os
import io
import json
import tempfile
from datetime import datetime, timedelta, timezone

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

# =========================
# ENV VARIABLES
# =========================
TOKEN_JSON = os.getenv("GOOGLE_TOKEN_JSON")
PENDING_FOLDER_ID = os.getenv("PENDING_FOLDER_ID")
UPLOADED_FOLDER_ID = os.getenv("UPLOADED_FOLDER_ID")

if not TOKEN_JSON:
    raise Exception("GOOGLE_TOKEN_JSON not found")
if not PENDING_FOLDER_ID:
    raise Exception("PENDING_FOLDER_ID not found")
if not UPLOADED_FOLDER_ID:
    raise Exception("UPLOADED_FOLDER_ID not found")

print("Bot started")

# =========================
# AUTH
# =========================
creds = Credentials.from_authorized_user_info(
    json.loads(TOKEN_JSON),
    scopes=[
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/youtube.upload"
    ]
)

drive = build("drive", "v3", credentials=creds)
youtube = build("youtube", "v3", credentials=creds)

# =========================
# PICK ONE FILE FROM PENDING
# =========================
results = drive.files().list(
    q=f"'{PENDING_FOLDER_ID}' in parents and trashed=false",
    fields="files(id, name, mimeType)",
    pageSize=1
).execute()

files = results.get("files", [])
if not files:
    print("No videos in PENDING folder")
    exit(0)

file = files[0]
file_id = file["id"]
file_name = file["name"]
mime_type = file["mimeType"]

print(f"Selected file: {file_name}")
print(f"MIME type: {mime_type}")

# =========================
# SHORTCUT RESOLVE
# =========================
real_file_id = file_id

if mime_type == "application/vnd.google-apps.shortcut":
    print("Shortcut detected. Resolving real file...")
    shortcut = drive.files().get(
        fileId=file_id,
        fields="shortcutDetails"
    ).execute()

    real_file_id = shortcut["shortcutDetails"]["targetId"]

    real_meta = drive.files().get(
        fileId=real_file_id,
        fields="name, mimeType"
    ).execute()

    file_name = real_meta["name"]
    mime_type = real_meta["mimeType"]

    print(f"Resolved to real file: {file_name}")

# =========================
# DOWNLOAD VIDEO
# =========================
request = drive.files().get_media(fileId=real_file_id)
fh = io.BytesIO()
downloader = MediaIoBaseDownload(fh, request)

done = False
while not done:
    status, done = downloader.next_chunk()

fh.seek(0)

tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
tmp.write(fh.read())
tmp.close()

print("Download completed")

# =========================
# DECIDE SCHEDULE TIME (IST)
# =========================
now_ist = datetime.now() + timedelta(hours=5, minutes=30)

# Default: morning slot
publish_hour = 8

# If already past 9 AM IST → afternoon slot
if now_ist.hour >= 9:
    publish_hour = 14  # 2 PM

publish_ist = now_ist.replace(
    hour=publish_hour,
    minute=0,
    second=0,
    microsecond=0
)

# If time already crossed today, schedule next day
if publish_ist <= now_ist:
    publish_ist += timedelta(days=1)

# Convert IST → UTC
publish_utc = publish_ist - timedelta(hours=5, minutes=30)
publish_utc = publish_utc.replace(tzinfo=timezone.utc)

print("Scheduled publish time (UTC):", publish_utc.isoformat())

# =========================
# YOUTUBE UPLOAD (SCHEDULED)
# =========================
body = {
    "snippet": {
        "title": file_name.replace(".mp4", ""),
        "description": "Automated scheduled upload",
        "categoryId": "22"
    },
    "status": {
        "privacyStatus": "private",
        "publishAt": publish_utc.isoformat()
    }
}

media = MediaFileUpload(tmp.name, resumable=True)

request = youtube.videos().insert(
    part="snippet,status",
    body=body,
    media_body=media
)

response = request.execute()
video_id = response["id"]

print(f"YouTube upload successful. Video ID: {video_id}")
print(f"Video scheduled for {publish_hour}:00 IST")

# =========================
# MOVE SHORTCUT ONLY
# =========================
meta = drive.files().get(
    fileId=file_id,
    fields="parents"
).execute()

previous_parents = ",".join(meta.get("parents", []))

drive.files().update(
    fileId=file_id,  # move shortcut, not real file
    addParents=UPLOADED_FOLDER_ID,
    removeParents=previous_parents,
    fields="id, parents"
).execute()

print("Shortcut moved to UPLOADED folder")
print("Bot finished successfully")
