import os
import time
import requests
import uuid
from supabase import create_client, Client
from video_stitcher import assemble_full_episode  # Import our stitcher script

# Supabase Setup
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

BUCKET_NAME = "wonderpals-outputs"


def download_file(url: str, local_path: str) -> str:
    """Helper to download remote URLs (S3/Supabase assets) to local disk for FFmpeg."""
    response = requests.get(url, stream=True)
    response.raise_for_status()
    with open(local_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    return local_path


def upload_to_supabase_storage(local_filepath: str, destination_name: str) -> str:
    """Uploads rendered MP4 to Supabase Storage and returns the public CDN URL."""
    print(f"☁️ Uploading {destination_name} to Supabase Storage bucket '{BUCKET_NAME}'...")
    
    with open(local_filepath, "rb") as f:
        supabase.storage.from_(BUCKET_NAME).upload(
            file=f,
            path=destination_name,
            file_options={"content-type": "video/mp4", "upsert": "true"}
        )

    # Get Public URL
    public_url = supabase.storage.from_(BUCKET_NAME).get_public_url(destination_name)
    return public_url


def process_leo_phase_1_batch(job_id: str, payload: dict):
    """
    Handles 'generate_leo_phase_1_batch' jobs:
    Payload structure expected:
    {
      "scenes": [
        {"visual": "https://...", "audio": "https://...", "caption": "Hi I'm Leo!"},
        ...
      ]
    }
    """
    print(f"🎬 Processing Leo Phase 1 Batch for Job ID: {job_id}...")
    scenes_data = payload.get("scenes", [])

    if not scenes_data:
        raise ValueError("Job payload is missing the 'scenes' list.")

    local_scenes = []
    temp_files = []

    try:
        # Step 1: Download raw assets to local temporary files
        for i, scene in enumerate(scenes_data):
            vis_ext = ".mp4" if ".mp4" in scene["visual"].lower() else ".png"
            local_vis = f"/tmp/scene_{i}_vis_{job_id[:8]}{vis_ext}"
            local_aud = f"/tmp/scene_{i}_aud_{job_id[:8]}.mp3"

            print(f"   └─ Downloading assets for Scene {i+1}...")
            download_file(scene["visual"], local_vis)
            download_file(scene["audio"], local_aud)

            temp_files.extend([local_vis, local_aud])

            local_scenes.append({
                "visual": local_vis,
                "audio": local_aud,
                "caption": scene.get("caption", "")
            })

        # Step 2: Render full MP4 locally
        output_filename = f"leo_episode_{job_id[:8]}.mp4"
        local_output_path = f"/tmp/{output_filename}"
        
        assemble_full_episode(local_scenes, output_filepath=local_output_path)
        temp_files.append(local_output_path)

        # Step 3: Upload output MP4 to Supabase Storage
        public_video_url = upload_to_supabase_storage(local_output_path, f"episodes/{output_filename}")

        # Step 4: Mark Job as completed in Supabase
        supabase.table("jobs").update({
            "status": "completed",
            "result_url": public_video_url,
            "error_message": None
        }).eq("id", job_id).execute()

        print(f"✨ Job {job_id} finished! Output: {public_video_url}")

    finally:
        # Step 5: Clean up temporary files on local disk
        for file_path in temp_files:
            if os.path.exists(file_path):
                os.remove(file_path)


def poll_worker_loop():
    """Main worker loop looking for pending tasks."""
    print("🚀 WonderPals Studio Worker listening for jobs...")
    
    while True:
        # Fetch pending job
        res = supabase.table("jobs").select("*").eq("status", "pending").limit(1).execute()
        jobs = res.data

        if jobs:
            job = jobs[0]
            job_id = job["id"]
            task_type = job.get("task_type")
            payload = job.get("payload", {})

            print(f"⚡ Job Picked Up: Processing {task_type} ({job_id})")

            # Update status to processing
            supabase.table("jobs").update({"status": "processing"}).eq("id", job_id).execute()

            try:
                if task_type == "generate_leo_phase_1_batch":
                    process_leo_phase_1_batch(job_id, payload)
                else:
                    print(f"Unknown task type: {task_type}")
                    
            except Exception as e:
                print(f"❌ Error processing job {job_id}: {e}")
                supabase.table("jobs").update({
                    "status": "failed",
                    "error_message": str(e)
                }).eq("id", job_id).execute()
        else:
            time.sleep(5)


if __name__ == "__main__":
    poll_worker_loop()
