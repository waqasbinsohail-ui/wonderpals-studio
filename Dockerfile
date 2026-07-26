FROM python:3.10-slim

# 1. Install FFmpeg (the video rendering engine) on the cloud server
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. Install all required Python packages
RUN pip install --no-cache-dir supabase moviepy pillow python-dotenv

# 3. Copy your project code to the server
COPY . .

# 4. Run your worker script automatically
CMD ["python", "studio_worker.py"]