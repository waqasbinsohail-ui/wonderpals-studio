import os
import time
import requests
from supabase import create_client, Client
from moviepy.editor import (
    ImageClip,
    VideoFileClip,
    AudioFileClip,
    TextClip,
    CompositeVideoClip,
    concatenate_videoclips,
)

# ----------------------------------------------------
# 1. Supabase & Storage Configuration
# ----------------------------------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

BUCKET_NAME = "wonderpals-outputs"


# ----------------------------------------------------
# 2. Video Stitcher Logic
# ----------------------------------------------------
def create_scene_clip(visual_path: str, audio_path: str, caption_text: str):
    """Combines a single visual asset, voiceover audio, and styled captions."""
    audio = AudioFileClip(audio_path)
    scene_duration = audio.duration

    if visual_path.endswith((".mp4", ".mov", ".webm")):
        visual_clip = VideoFileClip(visual_path)
        if visual_clip.duration < scene_duration:
            visual_clip = visual_clip.loop(duration=scene_duration)
        else:
            visual_clip = visual_clip.subclip(0, scene_duration)
    else:
        visual_clip = ImageClip(visual_path).set_duration(scene_duration)

    visual_clip = visual_clip.resize(newsize=(1920, 1080))

    try:
        subtitle = TextClip(
            caption_text,
            fontsize=60,
            color="yellow",
            font="Arial-Bold",
            stroke_color="black",
            stroke_width=3,
            method="caption",
            size=(1600, None),
        ).set_duration(scene_duration).set_position(("center", 900))
        
        scene_clip = CompositeVideoClip([visual_clip, subtitle])
    except Exception as e:
        print(f"⚠️ Subtitle rendering skipped: {e}")
        scene_clip = visual_clip

    scene_clip = scene_clip.set_audio(audio)
    return scene_clip


def assemble_full_episode(scenes: list, output_filepath: str) -> str:
    """Stitches multiple scene clips sequentially into a full MP4 episode."""
    print(f"✂️ Stitching {len(scenes)} scenes into final video...")
    rendered_clips = []

    for idx, scene in enumerate(scenes, start=1):
        print(f"   └─ Processing Scene {idx}/{len(scenes)}...")
        clip = create_scene_clip(
            visual_path=scene["visual"],
            audio_path=scene["audio"],
            caption_text=scene["caption"]
        )
        rendered_clips.append(clip)

    final_video = concatenate_videoclips(rendered_clips, method="compose")

    print("🎥 Rendering final MP4 file...")
    final_video.write_videofile(
        output_filepath,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        threads=4,
        preset="fast"
    )

    final_video.close()
    for clip in rendered_clips:
        clip.close()

    print(f"🎉 Episode rendered: {output_filepath}")
    return output_filepath


# ----------------------------------------------------
# 3. Helper Functions
# ----------------------------------------------------
def download_file(url: str, local_path: str) -> str:
    """Downloads remote asset URLs locally for processing."""
    response = requests.get(url, stream=True)
    response.raise_for_status()
    with open(local_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    return local_path


def upload_to_supabase_storage(local_filepath: str, destination_name: str) -> str:
    """Uploads rendered video to Supabase Storage."""
    print(f"☁️ Uploading to Supabase Storage bucket '{BUCKET_NAME}'...")
    with open(local_filepath, "rb") as f:
        supabase.storage.from_(BUCKET_NAME).upload(
            file=f,
            path=destination_name,
            file_options={"content-type": "video/mp4", "upsert": "true"}
        )
    return supabase.storage.from_(BUCKET_NAME).get_public_url(destination_name)


# ----------------------------------------------------
# 4. Worker Queue Handler
# ----------------------------------------------------
def process_leo_phase_1_batch(job_id: str, payload: dict):
    scenes_data = payload.get("scenes", [])
    if not scenes_data:
        raise ValueError("Job payload missing 'scenes' array.")

    local_scenes = []
    temp_files = []

    try:
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

        output_filename = f"leo_episode_{job_id[:8]}.mp4"
        local_output_path = f"/tmp/{output_filename}"

        assemble_full_episode(local_scenes, output_filepath=local_output_path)
        temp_files.append(local_output_path)

        public_video_url = upload_to_supabase_storage(local_output_path, f"episodes/{output_filename}")

        supabase.table("jobs").update({
            "status": "completed",
            "result_url": public_video_url,
            "error_message": None
        }).eq("id", job_id).execute()

        print(f"✨ Job {job_id} finished! Output: {public_video_url}")

    finally:
        for file_path in temp_files:
            if os.path.exists(file_path):
                os.remove(file_path)


# ----------------------------------------------------
# 5. Main Execution Loop
# ----------------------------------------------------
if __name__ == "__main__":
    print("🚀 WonderPals Studio Worker listening for jobs...")
    while True:
        res = supabase.table("jobs").select("*").eq("status", "pending").limit(1).execute()
        jobs = res.data

        if jobs:
            job = jobs[0]
            job_id = job["id"]
            task_type = job.get("task_type")
            payload = job.get("payload", {})

            print(f"⚡ Job Picked Up: Processing {task_type} ({job_id})")
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
