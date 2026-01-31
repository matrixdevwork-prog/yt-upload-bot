import os
import json
import io
import mimetypes

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import (
    MediaIoBaseDownload,
    MediaFileUpload
)

print("Bot started")

# ------------------------------------------------------------------
# ENV VARIABLES (GitHub Secrets se aati hain)
# ------------------------------------------------------------------
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

# ------------------------------------------------------------------
# STEP 1: PENDING folder se sirf 1 video uthao
# ------------------------------------------------------------------
response = drive.files().list(
    q=f"'{PENDING_FOLDER_ID}' in parents and trashed=false",
    fields="files(id, name, mimeType)",
    orderBy="createdTime"
).execute()

files = response.get("files", [])

if not files:
    print("No pending videos found")
    exit(0)

video = files[0]
file_id = video["id"]
file_name = video["name"]

print(f"Selected video: {file_name}")

# ------------------------------------------------------------------
# STEP 2: Drive se video download karo
# ------------------------------------------------------------------
local_path = f"/tmp/{file_name}"

request = drive.files().get_media(fileId=file_id)
fh = io.FileIO(local_path, "wb")
downloader = MediaIoBaseDownload(fh, request)

done = False
while not done:
    status, done = downloader.next_chunk()

print("Download completed")

# ------------------------------------------------------------------
# STEP 3: YouTube par PRIVATE upload
# ------------------------------------------------------------------
mime_type = mimetypes.guess_type(local_path)[0] or "video/mp4"

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
    mimetype=mime_type,
    resumable=True
)

request = youtube.videos().insert(
    part="snippet,status",
    body=body,
    media_body=media
)

response = request.execute()
video_id = response.get("id")

print(f"YouTube upload successful. Video ID: {video_id}")

# ------------------------------------------------------------------
# STEP 4: Upload ke baad Drive me move karo
# ------------------------------------------------------------------
drive.files().update(
    fileId=file_id,
    addParents=UPLOADED_FOLDER_ID,
    removeParents=PENDING_FOLDER_ID,
    fields="id, parents"
).execute()

print("Moved video to UPLOADED folder")

print("Bot finished successfully")
