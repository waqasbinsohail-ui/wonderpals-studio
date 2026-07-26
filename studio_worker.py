import os
import time
import requests
import fal_client
from supabase import create_client, Client
from moviepy.editor import ImageClip, AudioFileClip
from elevenlabs.client import ElevenLabs

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
FAL_KEY = os.getenv("FAL_KEY")  # fal_client reads this env var automatically
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID")  # set this to Leo's chosen voice

REQUIRED_VARS = {
    "SUPABASE_URL": SUPABASE_URL,
    "SUPABASE_KEY": SUPABASE_KEY,
    "FAL_KEY": FAL_KEY,
    "ELEVENLABS_API_KEY": ELEVENLABS_API_KEY,
    "ELEVENLABS_VOICE_ID": ELEVENLABS_VOICE_ID,
}
missing = [k for k, v in REQUIRED_VARS.items() if not v]
if missing:
    raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
elevenlabs = ElevenLabs(api_key=ELEVENLABS_API_KEY)


def generate_scene_image(prompt: str, out_path: str):
    """Generate a WonderPals scene image with fal.ai and download it locally."""
    result = fal_client.subscribe(
        "fal-ai/flux/dev",
        arguments={
            "prompt": prompt,
            "image_size": "landscape_16_9",
            "num_images": 1,
        },
    )
    image_url = result["images"][0]["url"]
    resp = requests.get(image_url, timeout=60)
    resp.raise_for_status()
    with open(out_path, "wb") as f:
        f.write(resp.content)


def generate_narration_audio(text: str, out_path: str):
    """Generate narration audio with ElevenLabs and save it locally."""
    audio_stream = elevenlabs.text_to_speech.convert(
        voice_id=ELEVENLABS_VOICE_ID,
        text=text,
        model_id="eleven_multilingual_v2",
    )
    with open(out_path, "wb") as f:
        for chunk in audio_stream:
            if chunk:
                f.write(chunk)


def render_scene_video(image_path: str, audio_path: str, output_path: str):
    """Combine the generated image + narration into a single scene video clip."""
    audio_clip = AudioFileClip(audio_path)
    image_clip = ImageClip(image_path).set_duration(audio_clip.duration).set_audio(audio_clip)
    image_clip.write_videofile(
        output_path,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        logger=None,
    )


def run_worker():
    print("Worker active - waiting for scene jobs...")
    while True:
        job_id = None
        try:
            res = supabase.table("video_jobs").select("*").eq("status", "pending").limit(1).execute()
            jobs = res.data

            if jobs:
                job = jobs[0]
                job_id = job["id"]
                visual_prompt = job.get("prompt", "")
                narration_text = job.get("narration", "") or visual_prompt
                print(f"Processing Job {job_id}")

                supabase.table("video_jobs").update({"status": "processing"}).eq("id", job_id).execute()

                image_path = f"job_{job_id}.png"
                audio_path = f"job_{job_id}.mp3"
                video_path = f"job_{job_id}.mp4"

                generate_scene_image(visual_prompt, image_path)
                generate_narration_audio(narration_text, audio_path)
                render_scene_video(image_path, audio_path, video_path)

                storage_path = f"outputs/{video_path}"
                with open(video_path, "rb") as f:
                    supabase.storage.from_("videos").upload(
                        path=storage_path,
                        file=f,
                        file_options={"content-type": "video/mp4"},
                    )
                public_url = supabase.storage.from_("videos").get_public_url(storage_path)

                supabase.table("video_jobs").update({
                    "status": "completed",
                    "output_url": public_url,
                }).eq("id", job_id).execute()

                for p in (image_path, audio_path, video_path):
                    if os.path.exists(p):
                        os.remove(p)

                print(f"Job {job_id} done! Output: {public_url}")

        except Exception as e:
            print(f"Error processing job: {e}")
            if job_id:
                supabase.table("video_jobs").update({
                    "status": "failed",
                    "error_message": str(e),
                }).eq("id", job_id).execute()

        time.sleep(5)


if __name__ == "__main__":
    run_worker()
