import os
import time
from supabase import create_client, Client
from moviepy.editor import ImageClip, AudioFileClip
from elevenlabs.client import ElevenLabs
from huggingface_hub import InferenceClient

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
HF_API_TOKEN = os.getenv("HF_API_TOKEN")  # Hugging Face free inference API token
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID")  # set this to Leo's chosen voice

REQUIRED_VARS = {
    "SUPABASE_URL": SUPABASE_URL,
    "SUPABASE_KEY": SUPABASE_KEY,
    "HF_API_TOKEN": HF_API_TOKEN,
    "ELEVENLABS_API_KEY": ELEVENLABS_API_KEY,
    "ELEVENLABS_VOICE_ID": ELEVENLABS_VOICE_ID,
}
missing = [k for k, v in REQUIRED_VARS.items() if not v]
if missing:
    raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
elevenlabs = ElevenLabs(api_key=ELEVENLABS_API_KEY)
hf_client = InferenceClient(
    provider="hf-inference",
    api_key=HF_API_TOKEN,
)


def generate_scene_image(prompt: str, out_path: str, max_retries: int = 5):
    """Generate a WonderPals scene image via Hugging Face's free hf-inference provider.

    Note: this does not use the trained Leo LoRA (that required fal.ai's paid
    LoRA endpoint). Character consistency relies on the locked style prompt text.
    Retries with backoff if the model is cold-starting (503/loading).
    """
    for attempt in range(max_retries):
        try:
            image = hf_client.text_to_image(
                prompt,
                model="black-forest-labs/FLUX.1-schnell",
            )
            image.save(out_path)
            return
        except Exception as e:
            msg = str(e)
            if "503" in msg or "loading" in msg.lower():
                wait_time = 20
                print(f"Model loading, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})...")
                time.sleep(wait_time)
                continue
            raise

    raise RuntimeError(f"HF inference did not return an image after {max_retries} attempts")


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
            res = (
                supabase.table("video_jobs")
                .select("*")
                .eq("status", "pending")
                .eq("task_type", "video_generation")
                .order("created_at")
                .limit(1)
                .execute()
            )
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
