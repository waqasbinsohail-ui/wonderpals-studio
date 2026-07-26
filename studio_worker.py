import os
import time
from supabase import create_client, Client
from moviepy.editor import TextClip, ColorClip, CompositeVideoClip

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_KEY or not SUPABASE_URL:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY environment variables are required!")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def render_video_with_moviepy(prompt: str, output_path: str, duration: int = 5):
    """Renders a clean 1080p video with text overlay using MoviePy."""
    # 1. Dark background (1920x1080)
    bg = ColorClip(size=(1920, 1080), color=(18, 24, 38), duration=duration)

    # 2. Text overlay displaying the prompt
    # Wrap prompt text if long
    formatted_prompt = prompt if len(prompt) < 60 else prompt[:57] + "..."
    txt_clip = TextClip(
        formatted_prompt, 
        fontsize=50, 
        color='white', 
        font='Arial', 
        size=(1600, None), 
        method='caption'
    ).set_duration(duration).set_position('center')

    # 3. Composite and write to mp4
    final_video = CompositeVideoClip([bg, txt_clip])
    final_video.write_videofile(
        output_path, 
        fps=24, 
        codec='libx264', 
        audio=False, 
        logger=None # Suppress verbose logs
    )

def run_worker():
    print("Worker active — waiting for video commands...")
    while True:
        try:
            # 1. Check for pending jobs
            res = supabase.table("video_jobs").select("*").eq("status", "pending").limit(1).execute()
            jobs = res.data

            if jobs:
                job = jobs[0]
                job_id = job["id"]
                prompt = job.get("prompt", "Corporate Video")
                print(f"Processing Job {job_id}: '{prompt}'")

                # Mark as processing
                supabase.table("video_jobs").update({"status": "processing"}).eq("id", job_id).execute()

                # 2. Render local video file
                local_filename = f"job_{job_id}.mp4"
                render_video_with_moviepy(prompt, local_filename, duration=5)

                # 3. Upload to Supabase Storage ('videos' bucket)
                storage_path = f"outputs/{local_filename}"
                with open(local_filename, "rb") as f:
                    supabase.storage.from_("videos").upload(
                        path=storage_path, 
                        file=f, 
                        file_options={"content-type": "video/mp4"}
                    )

                # 4. Generate public download URL
                public_url = supabase.storage.from_("videos").get_public_url(storage_path)

                # 5. Mark completed in DB
                supabase.table("video_jobs").update({
                    "status": "completed",
                    "output_url": public_url
                }).eq("id", job_id).execute()

                # Clean up local file after upload
                if os.path.exists(local_filename):
                    os.remove(local_filename)

                print(f"Job {job_id} done! Output: {public_url}")

        except Exception as e:
            print(f"Error processing job: {e}")
            if 'job_id' in locals():
                supabase.table("video_jobs").update({
                    "status": "failed",
                    "error_message": str(e)
                }).eq("id", job_id).execute()

        time.sleep(5)

if __name__ == "__main__":
    run_worker()
