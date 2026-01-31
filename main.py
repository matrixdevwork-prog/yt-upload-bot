import os
import json
import io
import random
import datetime
import requests

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

# ================== ENV ==================
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

print("✅ All environment variables loaded")

# ================== AUTH ==================
creds = Credentials.from_authorized_user_info(json.loads(TOKEN_JSON))
drive = build("drive", "v3", credentials=creds)
youtube = build("youtube", "v3", credentials=creds)

# ================== AI TITLE + TAGS ==================
def generate_ai_text():
    prompt = (
        "Generate a viral YouTube Shorts title (max 5 words) "
        "for funny Hulk AI meme content like 'areee ye kya hogya ree'. "
        "Also generate exactly 3 viral hashtags. "
        "Return JSON: {title:'', tags:[]}"
    )

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "openai/gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.9
        }
    )

    data = response.json()
    text = data["choices"][0]["message"]["content"]
    return json.loads(text)

# ================== DRIVE ==================
def list_pending_files():
    q = f"'{PENDING_FOLDER_ID}' in parents and trashed=false"
    res = drive.files().list(
        q=q,
        fields="files(id,name,mimeType,shortcutDetails)"
    ).execute()
    return res["files"]

def resolve_shortcut(file):
    if file["mimeType"] == "application/vnd.google-apps.shortcut":
        target_id = file["shortcutDetails"]["targetId"]
        real = drive.files().get(
            fileId=target_id,
            fields="id,name,mimeType"
        ).execute()
        print("🔁 Shortcut resolved:", real["name"])
        return real
    return file

def download_file(file):
    request = drive.files().get_media(fileId=file["id"])
    fh = io.FileIO(file["name"], "wb")
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return file["name"]

def move_file(file_id):
    drive.files().update(
        fileId=file_id,
        addParents=UPLOADED_FOLDER_ID,
        removeParents=PENDING_FOLDER_ID
    ).execute()

# ================== YOUTUBE ==================
def get_schedule_time():
    now = datetime.datetime.utcnow()
    today_ist = now + datetime.timedelta(hours=5, minutes=30)

    if today_ist.hour < 8:
        target = today_ist.replace(hour=8, minute=0, second=0)
    else:
        target = today_ist.replace(hour=14, minute=0, second=0)

    return (target - datetime.timedelta(hours=1)).isoformat() + "Z"

def upload_to_youtube(video_path, title, tags):
    body = {
        "snippet": {
            "title": title,
            "description": "AI Hulk funny short 😂",
            "tags": tags,
            "categoryId": "24"  # Entertainment
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": get_schedule_time(),
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
    print("✅ YouTube Uploaded:", res["id"])

# ================== MAIN ==================
def main():
    print("🚀 Bot started")

    files = list_pending_files()
    if not files:
        print("📭 No pending videos")
        return

    file = random.choice(files)
    print("🎯 Selected:", file["name"])

    file = resolve_shortcut(file)
    video_path = download_file(file)

    ai = generate_ai_text()
    print("🤖 AI Title:", ai["title"])
    print("🏷 Tags:", ai["tags"])

    upload_to_youtube(video_path, ai["title"], ai["tags"])
    move_file(file["id"])

    print("🎉 Done successfully")

if __name__ == "__main__":
    main()
