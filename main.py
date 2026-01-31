import os
import io
import json
import tempfile

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
    raise Exception("GOOGLE_TOKEN_JSON not found in environment")
if not PENDING_FOLDER_ID:
    raise Exception("PENDING_FOLDER_ID not found in environment")
if not UPLOADED_FOLDER_ID:
    raise Exception("UPLOADED_FOLDER_ID not found in environment")

print("Bot started")

# =========================
# AUTH
# =========================
creds = Credentials.from_authorized_user_info(
    json.loads(TOKEN_JSON),
    scopes=[
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/youtube.upload",
    ],
)

drive = build("drive", "v3", credentials=creds)
youtube = build("youtube", "v3", credentials=creds)

# =========================
# GET ONE FILE FROM PENDING
# =========================
results = drive.files().list(
    q=f"'{PENDING_FOLDER_ID}' in parents and trashed = false",
    fields="files(id, name, mimeType)",
    pageSize=1
).execute()

files = results.get("files", [])
if not files:
    print("No files found in PENDING folder")
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
    shortcut_meta = drive.files().get(
        fileId=file_id,
        fields="shortcutDetails"
    ).execute()

    real_file_id = shortcut_meta["shortcutDetails"]["targetId"]

    real_meta = drive.files().get(
        fileId=real_file_id,
        fields="name, mimeType"
    ).execute()

    file_name = real_meta["name"]
    mime_type = real_meta["mimeType"]

    print(f"Resolved to real file: {file_name}")
    print(f"Real MIME type: {mime_type}")

# =========================
# DOWNLOAD FILE
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
# YOUTUBE UPLOAD
# =========================
body = {
    "snippet": {
        "title": file_name.replace(".mp4", ""),
        "description": "Automated upload",
        "categoryId": "22"
    },
    "status": {
        "privacyStatus": "public"
    }
}

media = MediaFileUpload(tmp.name, resumable=True)

upload_request = youtube.videos().insert(
    part="snippet,status",
    body=body,
    media_body=media
)

response = upload_request.execute()
video_id = response["id"]

print(f"YouTube upload successful. Video ID: {video_id}")

# =========================
# MOVE FILE (REPLACE PARENT)
# =========================
meta = drive.files().get(
    fileId=real_file_id,
    fields="parents"
).execute()

previous_parents = ",".join(meta.get("parents", []))

drive.files().update(
    fileId=real_file_id,
    addParents=UPLOADED_FOLDER_ID,
    removeParents=previous_parents,
    fields="id, parents"
).execute()

print("File moved to UPLOADED folder successfully")
print("Bot finished successfully")
