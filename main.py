import os
import json
import io
import mimetypes

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from googleapiclient.errors import HttpError

print("Bot started")

# -------------------------------------------------
# ENV VARIABLES (GitHub Secrets)
# -------------------------------------------------
TOKEN_JSON = os.getenv("GOOGLE_TOKEN_JSON")
PENDING_FOLDER_ID = os.getenv("PENDING_FOLDER_ID")
UPLOADED_FOLDER_ID = os.getenv("UPLOADED_FOLDER_ID")

if not TOKEN_JSON:
    raise Exception("GOOGLE_TOKEN_JSON not found in environment")
if not PENDING_FOLDER_ID:
    raise Exception("PENDING_FOLDER_ID not found in environment")
if not UPLOADED_FOLDER_ID:
    raise Exception("UPLOADED_FOLDER_ID not found in environment")

token_info = json.loads(TOKEN_JSON)

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/youtube.upload"
]

creds = Credentials.from_authorized_user_info(token_info, SCOPES)

drive = build("drive", "v3", credentials=creds)
youtube = build("youtube", "v3", credentials=creds)

# -------------------------------------------------
# STEP 1: Get one file from PENDING
# -------------------------------------------------
res = drive.files().list(
    q=f"'{PENDING_FOLDER_ID}' in parents and trashed=false",
    fields="files(id, name, mimeType)",
    orderBy="createdTime"
).execute()

files = res.get("files", [])
if not files:
    print("No pending videos found")
    exit(0)

video = files[0]
file_id = video["id"]
file_name = video["name"]
mime_type = video["mimeType"]

print(f"Selected file: {file_name}")
print(f"MIME type: {mime_type}")

# -------------------------------------------------
# STEP 2: Handle Drive SHORTCUT
# -------------------------------------------------
if mime_type == "application/vnd.google-apps.shortcut":
    print("Shortcut detected. Resolving real file...")

    shortcut_info = drive.files().get(
        fileId=file_id,
        fields="shortcutDetails"
    ).execute()

    target_id = shortcut_info["shortcutDetails"]["targetId"]

    real_file = drive.files().get(
        fileId=target_id,
        fields="id, name, mimeType"
    ).execute()

    file_id = real_file["id"]
    file_name = real_file["name"]
    mime_type = real_file["mimeType"]

    print(f"Resolved to real file: {file_name}")
    print(f"Real MIME type: {mime_type}")

# -------------------------------------------------
# STEP 3: Validate real video file
# -------------------------------------------------
if not mime_type.startswith("video/"):
    raise Exception(f"Not a video file. MIME type = {mime_type}")

# -------------------------------------------------
# STEP 4: Download from Drive
# -------------------------------------------------
local_path = f"/tmp/{file_name}"

request = drive.files().get_media(fileId=file_id)
fh = io.FileIO(local_path, "wb")
downloader = MediaIoBaseDownload(fh, request)

done = False
while not done:
    status, done = downloader.next_chunk()

print("Download completed")

# -------------------------------------------------
# STEP 5: Upload to YouTube (PRIVATE)
# -------------------------------------------------
yt_mime = mimetypes.guess_type(local_path)[0] or "video/mp4"

body = {
    "snippet": {
        "title": file_name.rsplit(".", 1)[0],
        "description": "Auto uploaded by bot",
        "tags": ["automation"],
        "categoryId": "22"
    },
    "status": {
        "privacyStatus": "private"
    }
}

media = MediaFileUpload(
    local_path,
    mimetype=yt_mime,
    resumable=True
)

try:
    req = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )
    resp = req.execute()
    yt_video_id = resp.get("id")
    print(f"YouTube upload successful. Video ID: {yt_video_id}")

except HttpError as e:
    raise Exception(f"YouTube upload failed: {e}")

# -------------------------------------------------
# STEP 6: Move original Drive file to UPLOADED
# -------------------------------------------------
drive.files().update(
    fileId=file_id,
    addParents=UPLOADED_FOLDER_ID,
    removeParents=PENDING_FOLDER_ID,
    fields="id, parents"
).execute()

print("Moved video to UPLOADED folder")
print("Bot finished successfully")
