FROM python:3.10-slim

# Install FFmpeg
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Pin moviepy to 1.0.3 so moviepy.editor works
RUN pip install --no-cache-dir supabase moviepy==1.0.3 pillow python-dotenv

# Copy code and run worker
COPY . .

CMD ["python", "studio_worker.py"]
