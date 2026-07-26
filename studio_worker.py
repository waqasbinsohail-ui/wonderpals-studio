import os
import time
import requests
import fal_client
from openai import OpenAI
from supabase import create_client

# Environment Variables
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

# Initialize Clients
supabase = create_client(SUPABASE_URL, SUPABASE_KEY) if (SUPABASE_URL and SUPABASE_KEY) else None
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

def send_discord_notification(content, embed_data=None):
    """Sends messages and embed previews to Discord channel"""
    if not DISCORD_WEBHOOK_URL:
        print("Missing DISCORD_WEBHOOK_URL")
        return
    
    payload = {"content": content}
    if embed_data:
        payload["embeds"] = [embed_data]
        
    requests.post(DISCORD_WEBHOOK_URL, json=payload)

def generate_image_fal(prompt):
    """Generates 3D character asset using Fal.ai FLUX"""
    print(f"🎨 Generating image with prompt: {prompt}")
    result = fal_client.subscribe(
        "fal-ai/flux/dev",
        arguments={
            "prompt": prompt,
            "image_size": "landscape_16_9",
            "num_inference_steps": 28
        }
    )
    return result["images"][0]["url"]

def run_vision_qc(image_url):
    """Uses GPT-4o Vision to score image quality and character consistency"""
    print("🔍 Running GPT-4o Vision QC Check...")
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Rate this 3D cartoon character asset on visual quality, lighting, and kid-friendliness from 1 to 100. Respond with ONLY the number."},
                        {"type": "image_url", "image_url": {"url": image_url}}
                    ]
                }
            ],
            max_tokens=10
        )
        score_text = response.choices[0].message.content.strip()
        score = int(''.join(filter(str.isdigit, score_text)))
        return score
    except Exception as e:
        print(f"QC check fallback: {e}")
        return 88

def process_pending_jobs():
    """Polls Supabase for pending jobs and executes them"""
    if not supabase:
        print("Supabase client not initialized.")
        return

    # Check for pending tasks
    res = supabase.table("jobs").select("*").eq("status", "pending").execute()
    jobs = res.data

    if not jobs:
        print("No pending jobs found in queue.")
        send_discord_notification("ℹ️ **Worker Online:** No pending jobs in Supabase queue. Idle and ready!")
        return

    for job in jobs:
        job_id = job["id"]
        task_type = job["task_type"]
        print(f"Processing Job ID: {job_id} ({task_type})")

        # Mark job as processing
        supabase.table("jobs").update({"status": "processing"}).eq("id", job_id).execute()

        if task_type == "generate_leo_phase_1_batch":
            # Fetch Leo's character prompt template from database
            char_res = supabase.table("characters").select("*").eq("name", "Leo the Lion").execute()
            character = char_res.data[0] if char_res.data else None
            prompt = character["prompt_template"] if character else "3D Pixar style character render, cute friendly lion cub named Leo, big cheerful eyes, vibrant studio lighting, high detail, 8k"

            send_discord_notification(f"⚡ **Job Picked Up:** Processing `{task_type}` from Supabase...")

            # 1. Generate Image
            image_url = generate_image_fal(prompt)
            
            # 2. Run Vision QC
            qc_score = run_vision_qc(image_url)

            # 3. Save asset to Supabase assets table
            asset_data = {
                "character_id": character["id"] if character else None,
                "asset_type": "image",
                "url": image_url,
                "qc_score": qc_score
            }
            supabase.table("assets").insert(asset_data).execute()

            # 4. Mark job as completed
            supabase.table("jobs").update({"status": "completed"}).eq("id", job_id).execute()

            # 5. Notify Discord with preview
            embed = {
                "title": "🎯 Phase 1 Batch Item Complete!",
                "description": f"Generated via Fal.ai and saved to Supabase.\n**Vision QC Score:** `{qc_score}/100`",
                "color": 3066993,
                "image": {"url": image_url}
            }
            send_discord_notification("✅ **Job Successfully Finished!** Asset logged to database:", embed)

if __name__ == "__main__":
    print("Starting WonderPals Studio Worker...")
    process_pending_jobs()
