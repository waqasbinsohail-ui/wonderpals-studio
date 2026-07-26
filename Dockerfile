FROM python:3.10-slim

# Install FFmpeg
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy code and run worker
COPY . .

# Default: run the worker. In Railway, override the Start Command to
# `python discord_bot.py` on the second service to run the bot instead.
CMD ["python", "studio_worker.py"]
