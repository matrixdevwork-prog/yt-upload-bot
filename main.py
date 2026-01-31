import os
import json
import io
from datetime import datetime, timedelta
import pytz

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
    raise Exception("GOOGLE_TOKEN_JSON missing")

# =========================
# AUTH
# =========================
creds = Credentials.from_authorized_user_info(json.loads(TOKEN_JSON))
drive = build("drive", "v3", credentials=creds)
youtube = build("youtube", "v3", credentials=creds)

print("✅ Environment variables loaded")

# =========================
# TITLE + TAG PICKER
# =========================
def get_title_from_file(path="titles.txt"):
    if not os.path.exists(path):
        raise Exception("titles.txt not found in repo root")

    with open(path, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]

    if not lines:
        raise Exception("titles.txt is empty")

    first = lines[0]
    remaining = lines[1:]

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(remaining))

    title, tags = first.split("|")
    tag_list = [t.strip() for t in tags.split(",")]

    return title.strip(), tag_list

# =========================
# DESCRIPTION BUILDER
# =========================
def build_description(title, tags):
    hashtags = " ".join([f"#{t}" for t in tags])

    return f"""
{title}

🔥 Hulk AI Viral Short
😂 Funny AI Generated Content
🤖 Altered / AI Based Video

{hashtags}
""".strip()

# =========================
# SCHEDULE LOGIC (IST)
# =========================
def get_publish_time():
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)

    if now.hour < 7:
        publish = now.replace(hour=8, minute=0, second=0)
    elif now.hour < 13:
        publish = now.replace(hour=14, minute=0, second=0)
    else:
        publish = (now + timedelta(days=1)).replace(hour=8, minute=0, second=0)

    print("📅 Scheduled publish (IST):", publish.strftime("%Y-%m-%d %H:%M"))
    return publish.astimezone(pytz.utc).isoformat()

# =========================
# GET NEXT VIDEO
# =========================
def get_next_video():
    results = drive.files().list(
        q=f"'{PENDING_FOLDER_ID}' in parents and trashed=false",
        fields="files(id,name,mimeType,shortcutDetails)"
    ).execute()

    files = results.get("files", [])
    if not files:
        raise Exception("No videos in pending folder")

    f = files[0]

    # Handle shortcut
    if f["mimeType"] == "application/vnd.google-apps.shortcut":
        real_id = f["shortcutDetails"]["targetId"]
        real = drive.files().get(fileId=real_id, fields="id,name").execute()
        return real["id"], real["name"], f["id"]

    return f["id"], f["name"], None

# =========================
# DOWNLOAD VIDEO
# =========================
def download_video(file_id, name):
    request = drive.files().get_media(fileId=file_id)
    fh = io.FileIO(name, "wb")
    downloader = MediaIoBaseDownload(fh, request)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    print("⬇️ Download completed")
    return name

# =========================
# UPLOAD TO YOUTUBE
# =========================
def upload_to_youtube(path, title, description, tags, publish_time):
    body = {
        "snippet": {
            "title": title[:95],
            "description": description,
            "tags": tags,
            "categoryId": "24"
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": publish_time,
            "selfDeclaredMadeForKids": False
        }
    }

    media = MediaFileUpload(path, resumable=True)

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )

    response = request.execute()
    print("✅ YouTube upload successful:", response["id"])

# =========================
# MOVE FILE AFTER UPLOAD
# =========================
def move_file(file_id):
    drive.files().update(
        fileId=file_id,
        addParents=UPLOADED_FOLDER_ID,
        removeParents=PENDING_FOLDER_ID
    ).execute()

# =========================
# MAIN
# =========================
def main():
    print("🚀 Bot started")

    title, tags = get_title_from_file()
    description = build_description(title, tags)
    publish_time = get_publish_time()

    file_id, name, shortcut_id = get_next_video()
    path = download_video(file_id, name)

    upload_to_youtube(path, title, description, tags, publish_time)

    move_file(shortcut_id or file_id)

    print("🎉 DONE")

if __name__ == "__main__":
    main()
