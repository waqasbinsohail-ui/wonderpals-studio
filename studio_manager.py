import os
import json
from supabase import create_client, Client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_KEY or not SUPABASE_URL:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY environment variables are required!")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Master Locked Rules for Leo
LEO_LOCKED_STYLE = (
    "Leo, the approved WonderPals lion cub. Soft 3D cartoon style, soft golden-yellow fur, "
    "rounded fluffy orange mane, brown eyes, blue short-sleeve T-shirt with a large yellow star badge "
    "on upper-left chest, red shorts, yellow sneakers. Child-friendly rounded proportions."
)

# Episode 001 Configuration
EPISODE_001_DATA = {
    "episode_number": "EP001",
    "title": "Leo Learns to Share",
    "lesson": "Sharing toys brings joy to everyone",
    "location": "Giggle Forest Playground",
    "scenes": [
        {
            "scene_num": 1,
            "title": "Opening Hook & Playground Arrival",
            "narrator_text": "Welcome to Sunshine Valley! Today, Leo is playing at Giggle Forest.",
            "prompt": f"Show {LEO_LOCKED_STYLE} walking happily into Giggle Forest playground carrying a bright red toy truck."
        },
        {
            "scene_num": 2,
            "title": "The Everyday Problem",
            "narrator_text": "Leo has a fun red truck, but his friend wants to try it too.",
            "prompt": f"Show {LEO_LOCKED_STYLE} sitting on grass holding his red toy truck close to his chest with a thoughtful expression."
        },
        {
            "scene_num": 3,
            "title": "Learning Moment & Catchphrase",
            "narrator_text": "Leo remembers: sharing makes playing even more fun! Let's find out together!",
            "prompt": f"Show {LEO_LOCKED_STYLE} standing up with a huge warm smile, pointing forward with right arm in his signature catchphrase pose."
        },
        {
            "scene_num": 4,
            "title": "Spark Appears & Happy Ending",
            "narrator_text": "Leo shares his truck! Spark glows brightly because sharing is caring.",
            "prompt": f"Show {LEO_LOCKED_STYLE} handing the red toy truck to a friend, with Spark the tiny golden star glowing warmly overhead."
        }
    ]
}

def queue_episode_jobs(episode_data):
    print(f"--- Launching Production for {episode_data['episode_number']}: {episode_data['title']} ---")
    
    for scene in episode_data["scenes"]:
        job_payload = {
            "prompt": scene["prompt"],
            "narration": scene["narrator_text"],
            "task_type": "video_generation",
            "status": "pending",
            "metadata": json.dumps({
                "episode": episode_data["episode_number"],
                "scene": scene["scene_num"],
                "title": scene["title"],
                "location": episode_data["location"]
            })
        }
        
        # Insert job directly into Supabase job queue
        res = supabase.table("video_jobs").insert(job_payload).execute()
        print(f"Queued Scene {scene['scene_num']}: '{scene['title']}' -> Job ID: {res.data[0]['id']}")

if __name__ == "__main__":
    queue_episode_jobs(EPISODE_001_DATA)
