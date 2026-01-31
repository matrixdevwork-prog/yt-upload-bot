import os
import json

print("Bot started")

oauth_json = os.getenv("GOOGLE_OAUTH_JSON")
if not oauth_json:
    raise Exception("OAuth secret not found")

creds = json.loads(oauth_json)
print("OAuth credentials loaded")
print("Client ID:", creds.get("client_id", "ok"))

print("Dry run successful")


