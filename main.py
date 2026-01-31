import os
import json
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

print("Bot started")

# Load OAuth JSON from GitHub Secret
oauth_json = os.getenv("GOOGLE_OAUTH_JSON")
if not oauth_json:
    raise Exception("OAuth secret not found")

client_config = json.loads(oauth_json)

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

flow = InstalledAppFlow.from_client_config(
    client_config,
    scopes=SCOPES
)

creds = flow.run_console()

drive = build("drive", "v3", credentials=creds)

# 🔴 YAHAN APNA PENDING FOLDER ID DALO
PENDING_FOLDER_ID = "17fDjO4OLjVCKrvp80GFeyRq7RJqVViAz"

results = drive.files().list(
    q=f"'{PENDING_FOLDER_ID}' in parents and trashed = false",
    fields="files(id, name)"
).execute()

files = results.get("files", [])

if not files:
    print("No pending videos found")
else:
    print("Found pending videos:")
    for f in files:
        print("-", f["name"])
