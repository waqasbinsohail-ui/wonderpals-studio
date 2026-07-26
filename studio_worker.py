import os
import requests

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

def send_discord_notification(message):
    if not DISCORD_WEBHOOK_URL:
        print("No DISCORD_WEBHOOK_URL found in environment variables.")
        return
    
    payload = {"content": message}
    response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
    if response.status_code in [200, 204]:
        print("Successfully sent message to Discord!")
    else:
        print(f"Failed to send to Discord: {response.status_code}")

if __name__ == "__main__":
    send_discord_notification("🚀 WonderPals Studio backend worker is online and connected!")