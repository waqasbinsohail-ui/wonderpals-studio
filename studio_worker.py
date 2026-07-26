import os
import time
import base64
import requests
from supabase import create_client, Client
from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip
from elevenlabs.client import ElevenLabs

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID")  # set this to Leo's chosen voice

REQUIRED_VARS = {
    "SUPABASE_URL": SUPABASE_URL,
    "SUPABASE_KEY": SUPABASE_KEY,
    "CLOUDFLARE_ACCOUNT_ID": CLOUDFLARE_ACCOUNT_ID,
    "CLOUDFLARE_API_TOKEN": CLOUDFLARE_API_TOKEN,
    "ELEVENLABS_API_KEY": ELEVENLABS_API_KEY,
    "ELEVENLABS_VOICE_ID": ELEVENLABS_VOICE_ID,
}
missing = [k for k, v in REQUIRED_VARS.items() if not v]
if missing:
    raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
elevenlabs = ElevenLabs(api_key=ELEVENLABS_API_KEY)

CF_MODEL_URL = (
    f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}"
    f"/ai/run/@cf/black-forest-labs/flux-1-schnell"
)


def generate_scene_image(prompt: str, out_path: str, max_retries: int = 3):
    """Generate a WonderPals scene image via Cloudflare Workers AI's free tier.

    Note: this does not use the trained Leo LoRA (that required fal.ai's paid
    LoRA endpoint). Character consistency relies on the locked style prompt text.
    Retries on rate limiting (Cloudflare's free tier has daily/rate caps).
    """
    headers = {"Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"}
    payload = {"prompt": prompt}

    for attempt in range(max_retries):
        resp = requests.post(CF_MODEL_URL, headers=headers, json=payload, timeout=60)

        if resp.status_code == 200:
            data = resp.json()
            if not data.get("success", True) and "result" not in data:
                raise RuntimeError(f"Cloudflare Workers AI error: {data.get('errors')}")
            image_b64 = data["result"]["image"]
            with open(out_path, "wb") as f:
                f.write(base64.b64decode(image_b64))
            return

        if resp.status_code == 429:
            wait_time = 10
            print(f"Rate limited, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})...")
            time.sleep(wait_time)
            continue

        print(f"Cloudflare error response: {resp.text}")
        resp.raise_for_status()

    raise RuntimeError(f"Cloudflare Workers AI did not return an image after {max_retries} attempts")


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


def render_scene_video(image_path: str, audio_path: str, output_path: str, zoom_factor: float = 1.15):
    """Combine the generated image + narration into a scene video clip,
    with a slow Ken Burns zoom effect for a sense of motion."""
    audio_clip = AudioFileClip(audio_path)
    duration = audio_clip.duration

    def zoom(t):
        return 1 + (zoom_factor - 1) * (t / duration)

    image_clip = (
        ImageClip(image_path)
        .resize(zoom)
        .set_duration(duration)
        .set_position("center")
    )

    video = (
        CompositeVideoClip([image_clip])
        .set_duration(duration)
        .set_audio(audio_clip)
    )

    video.write_videofile(
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
