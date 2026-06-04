import os
import requests
import json
import asyncio
import edge_tts
import whisper
import google.generativeai as genai
from dotenv import load_dotenv

# Load env variables from .env if present
load_dotenv()

# Setup Gemini
genai_api_key = os.getenv("GEMINI_API_KEY")
if genai_api_key:
    genai.configure(api_key=genai_api_key)

# Whisper Model (Lazy loaded when needed to save memory)
_whisper_model = None

def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        # Load tiny model for speed and low CPU usage
        _whisper_model = whisper.load_model("tiny")
    return _whisper_model

# 1. Gemini Script Generator
def generate_script_and_keywords(topic, duration="Short", tone="Informative", language="English"):
    """
    Returns a list of dictionaries: [{'text': '...', 'visual_query': '...'}]
    """
    if not os.getenv("GEMINI_API_KEY"):
        raise ValueError("GEMINI_API_KEY is not set. Please add it to your configuration.")
    
    # Define lengths (mapping seconds to words based on average narration rate of 2.2 words/sec)
    if duration == "Short":
        words_limit = 130
    elif duration == "Long":
        words_limit = 400
    else:
        try:
            seconds = int(duration)
            # Enforce limits (Min: 15s, Max: 600s) on backend
            seconds = max(15, min(600, seconds))
            words_limit = int(seconds * 2.2)
        except ValueError:
            words_limit = 130  # fallback
    
    prompt = f"""
    Write a viral video script about the topic: "{topic}".
    Tone: {tone}
    Language: {language}
    Approximate length: {words_limit} words.
    
    Structure the script into a chronological sequence of short scenes (1-2 sentences per scene).
    For each scene, provide:
    1. The narration text (what the voiceover says, translated to {language}).
    2. A highly descriptive visual search query (in English) suitable for fetching stock video footage (e.g., "slow motion galaxy space", "hands typing on keyboard"). Do NOT include movie titles or abstract concepts, use realistic visual descriptions.
    
    Return ONLY a valid JSON array of objects, with no markdown formatting wrappers, like this:
    [
      {{
        "text": "scene narration text...",
        "visual_query": "visual search query..."
      }},
      ...
    ]
    """
    
    model = genai.GenerativeModel('gemini-2.5-flash')
    response = model.generate_content(prompt)
    
    # Clean output in case markdown code blocks are wrapped around the JSON
    text = response.text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    
    try:
        scenes = json.loads(text)
        return scenes
    except json.JSONDecodeError as e:
        # Fallback formatting parser if JSON parse fails
        print("Failed to parse JSON from Gemini response, raw response:", text)
        raise ValueError("AI returned invalid structure. Please try again.") from e

# 2. Edge-TTS Audio Generation
def generate_voiceover_sync(text, voice, output_path):
    """
    Synchronous wrapper to run Edge-TTS async code.
    """
    async def _async_gen():
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_path)
        
    asyncio.run(_async_gen())

# 3. Whisper Local Transcription with Word Timestamps
def transcribe_audio_to_words(audio_path):
    """
    Transcribes audio and returns a list of word segments with start/end times.
    Format: [{'word': 'hello', 'start': 0.1, 'end': 0.5}, ...]
    """
    model = get_whisper_model()
    result = model.transcribe(audio_path, word_timestamps=True)
    
    words_list = []
    for segment in result.get('segments', []):
        for word_info in segment.get('words', []):
            words_list.append({
                'word': word_info['word'].strip(),
                'start': word_info['start'],
                'end': word_info['end']
            })
    return words_list

# 4. Pexels API Stock Video Fetcher
def search_pexels_videos(query, api_key=None, orientation=None):
    """
    Searches Pexels for videos and returns list of video objects.
    Optionally filters by orientation ('portrait' or 'landscape').
    If orientation search returns no results, falls back to general search.
    """
    key = api_key or os.getenv("PEXELS_API_KEY")
    if not key:
        return []
    
    headers = {"Authorization": key}
    
    def run_query(target_orientation):
        url = f"https://api.pexels.com/videos/search?query={query}&per_page=5"
        if target_orientation:
            url += f"&orientation={target_orientation}"
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                videos = []
                for item in data.get('videos', []):
                    video_files = item.get('video_files', [])
                    video_url = None
                    for vf in video_files:
                        if vf.get('file_type') == 'video/mp4':
                            video_url = vf.get('link')
                            break
                    if video_url:
                        videos.append({
                            'id': item.get('id'),
                            'image': item.get('image'), # thumbnail
                            'duration': item.get('duration'),
                            'url': video_url,
                            'width': item.get('width'),
                            'height': item.get('height')
                        })
                return videos
        except Exception as e:
            print(f"Error fetching Pexels videos with orientation '{target_orientation}' for query '{query}':", e)
        return []

    # First attempt with requested orientation
    results = run_query(orientation)
    if results:
        return results
        
    # Fallback to general search if orientation filter was specified but returned no results
    if orientation:
        print(f"Pexels orientation search for '{orientation}' returned 0 results for '{query}'. Running fallback query...")
        return run_query(None)
        
    return []

def download_video_clip(url, dest_path):
    """
    Downloads a video clip from URL and saves to destination.
    """
    try:
        response = requests.get(url, stream=True, timeout=30)
        if response.status_code == 200:
            with open(dest_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=1024*1024):
                    if chunk:
                        f.write(chunk)
            return True
    except Exception as e:
        print(f"Failed to download video from {url}:", e)
    return False
