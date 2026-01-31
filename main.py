import os, json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

print("Bot started")

token_json = os.getenv("GOOGLE_TOKEN_JSON")
if not token_json:
    raise Exception("Token secret not found")

token_info = json.loads(token_json)

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/youtube.upload"
]

creds = Credentials.from_authorized_user_info(token_info, SCOPES)

drive = build("drive", "v3", credentials=creds)

# 🔴 PENDING folder ID yahan paste karo
PENDING_FOLDER_ID = "17fDjO4OLjVCKrvp80GFeyRq7RJqVViAz"

results = drive.files().list(
    q=f"'{PENDING_FOLDER_ID}' in parents and trashed=false",
    fields="files(id, name)"
).execute()

files = results.get("files", [])

if not files:
    print("No pending videos found")
else:
    print("Found pending videos:")
    for f in files:
        print("-", f["name"])

