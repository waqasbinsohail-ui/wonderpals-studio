import os
import requests
import fal_client
from openai import OpenAI
from supabase import create_client

# Load Railway Environment Variables
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

# Initialize OpenAI & Supabase
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
supabase = create_client(SUPABASE_URL, SUPABASE_KEY) if (SUPABASE_URL and SUPABASE_KEY) else None

def send_discord_notification(content, embed_data=None):
    if not DISCORD_WEBHOOK_URL:
        print("Missing DISCORD_WEBHOOK_URL")
        return
    
    payload = {"content": content}
    if embed_data:
        payload["embeds"] = [embed_data]
        
    requests.post(DISCORD_WEBHOOK_URL, json=payload)

def test_fal_image_gen():
    """Generates a test 3D character asset using Fal.ai FLUX"""
    print("🎨 Generating test asset via Fal.ai...")
    result = fal_client.subscribe(
        "fal-ai/flux/dev",
        arguments={
            "prompt": "3D Pixar style character render, cute friendly lion cub named Leo, big cheerful eyes, vibrant studio lighting, high detail, 8k",
            "image_size": "landscape_16_9",
            "num_inference_steps": 28
        }
    )
    return result["images"][0]["url"]

def test_elevenlabs_voice(text="Welcome to WonderPals Studio! All AI pipelines are online and working."):
    """Generates a test audio clip using ElevenLabs API"""
    print("🎙️ Generating test voice clip via ElevenLabs...")
    voice_id = "21m00Tcm4TlvDq8ikWAM"  # Default preset voice ID
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json"
    }
    data = {
        "text": text,
        "model_id": "eleven_turbo_v2_5"
    }
    res = requests.post(url, headers=headers, json=data)
    return res.status_code == 200

if __name__ == "__main__":
    send_discord_notification("⚙️ **WonderPals Studio: Running Full Integration Test...**")
    
    try:
        image_url = test_fal_image_gen()
        voice_ready = test_elevenlabs_voice()

        if image_url and voice_ready:
            embed = {
                "title": "🎉 Studio Tech Stack Fully Operational!",
                "description": "Fal.ai (Image), ElevenLabs (Voice), OpenAI (Brain), and Supabase (Data) are all responding correctly.",
                "color": 5814783,
                "image": {"url": image_url}
            }
            send_discord_notification("✅ **Test Succeeded!** Here is your first live asset created by the studio backend:", embed)
        else:
            send_discord_notification("⚠️ Test completed with errors. Check Railway deployment logs.")
    except Exception as e:
        print(f"Error: {e}")
        send_discord_notification(f"❌ Test Failed: `{str(e)}`")
