import os
import discord
from discord import app_commands
from studio_manager import queue_episode_jobs, EPISODE_001_DATA, supabase

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not DISCORD_BOT_TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN environment variable is required!")

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


@client.event
async def on_ready():
    await tree.sync()
    print(f"Discord bot online as {client.user}")


@tree.command(name="produce_episode", description="Queue WonderPals Episode 001 for production")
async def produce_episode(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    try:
        queue_episode_jobs(EPISODE_001_DATA)
        await interaction.followup.send(
            f"Queued **{EPISODE_001_DATA['episode_number']}: {EPISODE_001_DATA['title']}** "
            f"({len(EPISODE_001_DATA['scenes'])} scenes). The worker will start producing shortly. "
            f"Use `/status` to check progress."
        )
    except Exception as e:
        await interaction.followup.send(f"Failed to queue episode: {e}")


@tree.command(name="status", description="Check WonderPals production job status")
async def status(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    res = supabase.table("video_jobs").select("id,status,output_url").order("id", desc=True).limit(10).execute()
    if not res.data:
        await interaction.followup.send("No jobs found yet. Try `/produce_episode` first.")
        return
    lines = []
    for j in res.data:
        line = f"#{j['id']} - {j['status']}"
        if j.get("output_url"):
            line += f" - {j['output_url']}"
        lines.append(line)
    await interaction.followup.send("\n".join(lines))


client.run(DISCORD_BOT_TOKEN)
