import os
import io
import json
import tempfile
import requests
from datetime import datetime, timedelta, timezone

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

# ==================================================
# ENV VARIABLES
# ==================================================
TOKEN_JSON = os.getenv("GOOGLE_TOKEN_JSON")
PENDING_FOLDER_ID = os.getenv("PENDING_FOLDER_ID")
UPLOADED_FOLDER_ID = os.getenv("UPLOADED_FOLDER_ID")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not TOKEN_JSON:
    raise Exception("GOOGLE_TOKEN_JSON missing")
if not PENDING_FOLDER_ID:
    raise Exception("PENDING_FOLDER_ID missing")
if not UPLOADED_FOLDER_ID:
    raise Exception("UPLOADED_FOLDER_ID missing")
if not OPENROUTER_API_KEY:
    raise Exception("OPENROUTER_API_KEY missing")

print("Bot started")

# ==================================================
# AUTH
# ==================================================
creds = Credentials.from_authorized_user_info(
    json.loads(TOKEN_JSON),
    scopes=[
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/youtube.upload"
    ]
)

drive = build("drive", "v3", credentials=creds)
youtube = build("youtube", "v3", credentials=creds)

# ==================================================
# AI TITLE + TAGS (OPENROUTER)
# ==================================================
def generate_ai_title_and_tags(filename):
    prompt = f"""
You generate VIRAL Hinglish meme titles for AI-generated Hulk videos.

Rules:
- EXACTLY 5 words title
- Hinglish, loud, funny
- Words like: aree, ree, bhai, kya
- No emojis
- No quotes
- No hashtags in title

Generate:
1. ONE title
2. THREE hashtags

STRICT FORMAT:
TITLE: <title>
TAGS: #tag1 #tag2 #tag3

Filename: {filename}
"""

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com",
            "X-Title": "Hulk Meme Automation"
        },
        json={
            "model": "openai/gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 1.1
        },
        timeout=20
    )

    data = response.json()
    text = data["choices"][0]["message"]["content"]

    title = ""
    tags = ""

    for line in text.splitlines():
        if line.startswith("TITLE:"):
            title = line.replace("TITLE:", "").strip()
        if line.startswith("TAGS:"):
            tags = line.replace("TAGS:", "").strip()

    if not title or len(title.split()) != 5:
        title = "Aree Hulk Ye Kya"
    if not tags:
        tags = "#HulkMeme #AIVideo #ViralShorts"

    tag_list = [t.replace("#", "") for t in tags.split()[:3]]

    return title, tag_list, tags

# ==================================================
# PICK ONE FILE FROM PENDING
# ==================================================
res = drive.files().list(
    q=f"'{PENDING_FOLDER_ID}' in parents and trashed=false",
    fields="files(id, name, mimeType)",
    pageSize=1
).execute()

files = res.get("files", [])
if not files:
    print("No videos in PENDING folder")
    exit(0)

file = files[0]
file_id = file["id"]
file_name = file["name"]
mime_type = file["mimeType"]

print(f"Selected file: {file_name}")

# ==================================================
# SHORTCUT RESOLVE
# ==================================================
real_file_id = file_id

if mime_type == "application/vnd.google-apps.shortcut":
    print("Shortcut detected, resolving real file...")
    shortcut = drive.files().get(
        fileId=file_id,
        fields="shortcutDetails"
    ).execute()

    real_file_id = shortcut["shortcutDetails"]["targetId"]

    meta = drive.files().get(
        fileId=real_file_id,
        fields="name"
    ).execute()

    file_name = meta["name"]

# ==================================================
# DOWNLOAD VIDEO
# ==================================================
request = drive.files().get_media(fileId=real_file_id)
fh = io.BytesIO()
downloader = MediaIoBaseDownload(fh, request)

done = False
while not done:
    _, done = downloader.next_chunk()

fh.seek(0)

tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
tmp.write(fh.read())
tmp.close()

print("Download completed")

# ==================================================
# SCHEDULE TIME (IST → UTC)
# ==================================================
now_ist = datetime.utcnow() + timedelta(hours=5, minutes=30)

publish_hour = 8
if now_ist.hour >= 9:
    publish_hour = 14

publish_ist = now_ist.replace(
    hour=publish_hour,
    minute=0,
    second=0,
    microsecond=0
)

if publish_ist <= now_ist:
    publish_ist += timedelta(days=1)

publish_utc = (publish_ist - timedelta(hours=5, minutes=30)).replace(tzinfo=timezone.utc)

print("Scheduled publish (UTC):", publish_utc.isoformat())

# ==================================================
# AI TITLE + TAGS
# ==================================================
title, tag_list, tag_text = generate_ai_title_and_tags(file_name)

# ==================================================
# YOUTUBE UPLOAD (FINAL FIXED)
# ==================================================
body = {
    "snippet": {
        "title": title,
        "description": f"{tag_text}\n\nAI generated Hulk meme",
        "categoryId": "24",          # Entertainment
        "tags": tag_list             # exactly 3 tags
    },
    "status": {
        "privacyStatus": "private",
        "publishAt": publish_utc.isoformat(),
        "selfDeclaredMadeForKids": False
    },
    "contentDetails": {
        "hasAlteredContent": True
    }
}

media = MediaFileUpload(tmp.name, resumable=True)

response = youtube.videos().insert(
    part="snippet,status,contentDetails",
    body=body,
    media_body=media
).execute()

print("YouTube upload successful:", response["id"])

# ==================================================
# MOVE ONLY SHORTCUT (NO PARENT ERROR)
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

print("Shortcut moved to UPLOADED folder")
print("Bot finished successfully")
