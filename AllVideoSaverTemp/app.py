from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import os
import uuid
import tempfile
import logging
import threading
import time

# ---------------------------
# Logging
# ---------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Enable CORS

# ---------------------------
# Configuration
# ---------------------------
DOWNLOAD_FOLDER = r"D:\AllVideoSaverTemp"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

FFMPEG_PATH = r"D:\ffmpeg-8.0"
  # <-- Set path to your ffmpeg folder

# ---------------------------
# Helper Functions
# ---------------------------
def sanitize_filename(filename):
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    return filename[:100]

def format_duration(seconds):
    if not seconds:
        return "Unknown"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"

def detect_platform(extractor):
    extractor_lower = extractor.lower()
    if 'tiktok' in extractor_lower:
        return 'tiktok'
    elif 'youtube' in extractor_lower:
        return 'youtube'
    elif 'facebook' in extractor_lower:
        return 'facebook'
    elif 'instagram' in extractor_lower:
        return 'instagram'
    elif 'twitter' in extractor_lower:
        return 'twitter'
    return extractor_lower

def get_available_formats(info):
    formats = []
    if 'formats' in info:
        for fmt in info['formats']:
            if fmt.get('height'):
                formats.append({
                    'quality': f"{fmt['height']}p",
                    'format_note': fmt.get('format_note', ''),
                    'ext': fmt.get('ext', ''),
                    'filesize': fmt.get('filesize')
                })
    seen = set()
    unique_formats = []
    for fmt in formats:
        if fmt['quality'] not in seen:
            seen.add(fmt['quality'])
            unique_formats.append(fmt)
    return sorted(unique_formats, key=lambda x: int(x['quality'].replace('p', '')), reverse=True)

def get_format_selector(quality):
    if quality == 'audio':
        return 'bestaudio/best'
    elif quality == '360':
        return 'best[height<=360]/best'
    elif quality == '720':
        return 'best[height<=720]/best'
    elif quality == '1080':
        return 'best[height<=1080]/best'
    return 'bestvideo+bestaudio/best'

def delayed_cleanup(path, delay=60):
    """Delete file after delay to prevent WinError 32"""
    def _cleanup():
        time.sleep(delay)
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            logger.warning(f"Could not delete file {path}: {str(e)}")
    threading.Thread(target=_cleanup).start()

# ---------------------------
# Routes
# ---------------------------
@app.route('/')
def index():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>AllVideoSaver</title>
        <meta http-equiv="refresh" content="0; url=/static/index.html">
    </head>
    <body>
        <p>Redirecting to <a href="/static/index.html">AllVideoSaver</a>...</p>
    </body>
    </html>
    """

@app.route('/api/fetch-info', methods=['POST'])
def fetch_video_info():
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({'error': 'No URL provided'}), 400
    url = data['url'].strip()
    if not url:
        return jsonify({'error': 'Empty URL provided'}), 400

    ydl_opts = {'quiet': True, 'no_warnings': False, 'extract_flat': False, 'ffmpeg_location': FFMPEG_PATH}

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_info = {
                'title': info.get('title', 'Unknown Title'),
                'duration': format_duration(info.get('duration', 0)),
                'thumbnail': info.get('thumbnail', ''),
                'platform': detect_platform(info.get('extractor', '')),
                'formats': get_available_formats(info)
            }
            logger.info(f"Fetched info: {video_info['title']}")
            return jsonify(video_info)
    except Exception as e:
        logger.error(f"Error fetching info: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/download', methods=['POST'])
def download_video():
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({'error': 'No URL provided'}), 400
    url = data['url'].strip()
    quality = data.get('quality', '720')
    if not url:
        return jsonify({'error': 'Empty URL provided'}), 400

    filename = f"allvideosaver_{uuid.uuid4().hex}"
    filepath = os.path.join(DOWNLOAD_FOLDER, filename)

    ydl_opts = {
        'outtmpl': filepath + '.%(ext)s',
        'format': get_format_selector(quality),
        'ffmpeg_location': FFMPEG_PATH
    }

    if quality == 'audio':
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            downloaded_file = ydl.prepare_filename(info)
            if quality == 'audio':
                downloaded_file = downloaded_file.rsplit('.', 1)[0] + '.mp3'
                download_name = f"{sanitize_filename(info['title'])}.mp3"
            else:
                download_name = f"{sanitize_filename(info['title'])}_{quality}p.mp4"

            logger.info(f"Downloaded: {info['title']}")
            # Delayed cleanup to avoid WinError 32
            delayed_cleanup(downloaded_file, delay=60)

            return send_file(
                downloaded_file,
                as_attachment=True,
                download_name=download_name,
                mimetype='video/mp4' if quality != 'audio' else 'audio/mpeg'
            )
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ---------------------------
# Run App
# ---------------------------
if __name__ == '__main__':
    if not os.path.exists('static'):
        os.makedirs('static')
    print("Starting AllVideoSaver Server...")
    print("Dependencies: pip install flask flask-cors yt-dlp")
    print("Server running at http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
