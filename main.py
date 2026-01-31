import os
import io
import json
import datetime
import requests

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload


# ================= ENV =================
TOKEN_JSON = os.getenv("GOOGLE_TOKEN_JSON")
PENDING_FOLDER_ID = os.getenv("PENDING_FOLDER_ID")
UPLOADED_FOLDER_ID = os.getenv("UPLOADED_FOLDER_ID")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not all([TOKEN_JSON, PENDING_FOLDER_ID, UPLOADED_FOLDER_ID, OPENROUTER_API_KEY]):
    raise Exception("Missing required environment variables")

print("✅ All environment variables loaded")


# ================= AUTH =================
creds = Credentials.from_authorized_user_info(json.loads(TOKEN_JSON))
drive = build("drive", "v3", credentials=creds)
youtube = build("youtube", "v3", credentials=creds)

print("🚀 Bot started")


# ================= TIME LOGIC (IST) =================
now_utc = datetime.datetime.utcnow()
now_ist = now_utc + datetime.timedelta(hours=5, minutes=30)

if now_ist.hour < 12:
    # Morning slot → publish 8:00 AM IST
    publish_ist = now_ist.replace(hour=8, minute=0, second=0, microsecond=0)
else:
    # Afternoon slot → publish 2:00 PM IST
    publish_ist = now_ist.replace(hour=14, minute=0, second=0, microsecond=0)

publish_utc = publish_ist - datetime.timedelta(hours=5, minutes=30)
publish_at = publish_utc.isoformat() + "Z"

print("📅 Scheduled publish time (IST):", publish_ist.strftime("%Y-%m-%d %H:%M"))


# ================= AI TITLE + TAGS =================
def generate_ai_text():
    prompt = (
        "Generate a viral YouTube Shorts title (max 5 words) "
        "and exactly 3 viral hashtags for Hulk-style funny AI content. "
        "Respond ONLY in valid JSON like:\n"
        '{ "title": "text", "tags": ["#tag1", "#tag2", "#tag3"] }'
    )

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "openai/gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )

    data = response.json()

    if "choices" not in data:
        print("⚠️ OpenRouter raw response:", data)
        raise Exception("OpenRouter did not return choices")

    content = data["choices"][0]["message"]["content"]

    try:
        parsed = json.loads(content)
        return parsed
    except Exception:
        print("⚠️ AI returned invalid JSON:", content)
        raise Exception("Invalid AI JSON output")


ai = generate_ai_text()
TITLE = ai["title"]
TAGS = ai["tags"]

print("🧠 AI Title:", TITLE)
print("🏷️ AI Tags:", TAGS)


# ================= GET VIDEO =================
results = drive.files().list(
    q=f"'{PENDING_FOLDER_ID}' in parents",
    fields="files(id,name,mimeType,shortcutDetails)"
).execute()

if not results.get("files"):
    raise Exception("No video found in PENDING folder")

file = results["files"][0]
file_id = file["id"]

print("🎬 Selected:", file["name"])

# Resolve shortcut
if file["mimeType"] == "application/vnd.google-apps.shortcut":
    file_id = file["shortcutDetails"]["targetId"]
    file = drive.files().get(
        fileId=file_id,
        fields="id,name,mimeType"
    ).execute()
    print("🔗 Shortcut resolved:", file["name"])


# ================= DOWNLOAD =================
request = drive.files().get_media(fileId=file_id)
fh = io.FileIO("video.mp4", "wb")
downloader = MediaIoBaseDownload(fh, request)

done = False
while not done:
    status, done = downloader.next_chunk()

print("⬇️ Download completed")


# ================= YOUTUBE UPLOAD =================
body = {
    "snippet": {
        "title": TITLE,
        "description": "😂 AI generated Hulk-style viral short",
        "tags": TAGS,
        "categoryId": "24",  # Entertainment
    },
    "status": {
        "privacyStatus": "private",
        "publishAt": publish_at,
        "selfDeclaredMadeForKids": False,
    }
}

media = MediaFileUpload("video.mp4", resumable=True)

request = youtube.videos().insert(
    part="snippet,status",
    body=body,
    media_body=media
)

response = request.execute()
video_id = response["id"]

print("📤 YouTube upload successful. Video ID:", video_id)


# ================= MOVE FILE =================
drive.files().update(
    fileId=file_id,
    addParents=UPLOADED_FOLDER_ID,
    removeParents=PENDING_FOLDER_ID,
).execute()

print("📁 Moved video to UPLOADED folder")
print("✅ Automation completed successfully")
