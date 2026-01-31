import os
import io
import json
import datetime

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload


# ==================================================
# ENV VARIABLES
# ==================================================
TOKEN_JSON = os.getenv("GOOGLE_TOKEN_JSON")
PENDING_FOLDER_ID = os.getenv("PENDING_FOLDER_ID")
UPLOADED_FOLDER_ID = os.getenv("UPLOADED_FOLDER_ID")

if not TOKEN_JSON:
    raise Exception("GOOGLE_TOKEN_JSON missing")
if not PENDING_FOLDER_ID:
    raise Exception("PENDING_FOLDER_ID missing")
if not UPLOADED_FOLDER_ID:
    raise Exception("UPLOADED_FOLDER_ID missing")

print("✅ Environment variables loaded")


# ==================================================
# AUTH
# ==================================================
creds = Credentials.from_authorized_user_info(json.loads(TOKEN_JSON))
drive = build("drive", "v3", credentials=creds)
youtube = build("youtube", "v3", credentials=creds)

print("🚀 Bot started")


# ==================================================
# TITLE + TAGS FROM TXT
# ==================================================
def get_title_from_file(path="titles.txt"):
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for i, line in enumerate(lines):
        if "|" not in line:
            continue

        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 3:
            continue

        status, title, tags = parts

        if status == "0":
            # mark as used
            lines[i] = f"1 | {title} | {tags}\n"

            with open(path, "w", encoding="utf-8") as f:
                f.writelines(lines)

            tag_list = tags.replace("#", "").split()
            return title, tag_list, tags

    raise Exception("❌ No unused titles left in titles.txt")


# ==================================================
# SCHEDULE TIME (IST → UTC)
# ==================================================
now_utc = datetime.datetime.utcnow()
now_ist = now_utc + datetime.timedelta(hours=5, minutes=30)

if now_ist.hour < 12:
    publish_ist = now_ist.replace(hour=8, minute=0, second=0, microsecond=0)
else:
    publish_ist = now_ist.replace(hour=14, minute=0, second=0, microsecond=0)

if publish_ist <= now_ist:
    publish_ist += datetime.timedelta(days=1)

publish_utc = publish_ist - datetime.timedelta(hours=5, minutes=30)
publish_at = publish_utc.isoformat() + "Z"

print("📅 Scheduled publish (IST):", publish_ist.strftime("%Y-%m-%d %H:%M"))


# ==================================================
# PICK ONE FILE FROM PENDING
# ==================================================
res = drive.files().list(
    q=f"'{PENDING_FOLDER_ID}' in parents and trashed=false",
    fields="files(id,name,mimeType,shortcutDetails)",
    pageSize=1
).execute()

files = res.get("files", [])
if not files:
    raise Exception("No video found in PENDING folder")

file = files[0]
file_id = file["id"]
file_name = file["name"]

print("🎬 Selected file:", file_name)


# ==================================================
# SHORTCUT RESOLVE
# ==================================================
real_file_id = file_id

if file["mimeType"] == "application/vnd.google-apps.shortcut":
    print("🔗 Shortcut detected, resolving real file...")
    shortcut = drive.files().get(
        fileId=file_id,
        fields="shortcutDetails"
    ).execute()

    real_file_id = shortcut["shortcutDetails"]["targetId"]

    real_meta = drive.files().get(
        fileId=real_file_id,
        fields="name"
    ).execute()

    file_name = real_meta["name"]
    print("Resolved to:", file_name)


# ==================================================
# DOWNLOAD VIDEO
# ==================================================
request = drive.files().get_media(fileId=real_file_id)
fh = io.FileIO("video.mp4", "wb")
downloader = MediaIoBaseDownload(fh, request)

done = False
while not done:
    _, done = downloader.next_chunk()

print("⬇️ Download completed")


# ==================================================
# GET TITLE + TAGS
# ==================================================
TITLE, TAG_LIST, TAG_TEXT = get_title_from_file("titles.txt")

print("📝 Title:", TITLE)
print("🏷️ Tags:", TAG_LIST)


# ==================================================
# YOUTUBE UPLOAD (SCHEDULED)
# ==================================================
body = {
    "snippet": {
        "title": TITLE,
        "description": f"{TAG_TEXT}\n\nAI generated Hulk meme",
        "categoryId": "24",          # Entertainment
        "tags": TAG_LIST
    },
    "status": {
        "privacyStatus": "private",
        "publishAt": publish_at,
        "selfDeclaredMadeForKids": False
    },
    "contentDetails": {
        "hasAlteredContent": True
    }
}

media = MediaFileUpload("video.mp4", resumable=True)

response = youtube.videos().insert(
    part="snippet,status,contentDetails",
    body=body,
    media_body=media
).execute()

print("📤 YouTube upload successful:", response["id"])


# ==================================================
# MOVE ONLY SHORTCUT (SAFE)
# ==================================================
meta = drive.files().get(
    fileId=file_id,
    fields="parents"
).execute()

previous_parents = ",".join(meta.get("parents", []))

drive.files().update(
    fileId=file_id,
    addParents=UPLOADED_FOLDER_ID,
    removeParents=previous_parents,
    fields="id, parents"
).execute()

print("📁 Shortcut moved to UPLOADED folder")
print("✅ Bot finished successfully")
