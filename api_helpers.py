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
    
    try:
        seconds = int(duration)
    except ValueError:
        if duration == "Short":
            seconds = 30
        elif duration == "Long":
            seconds = 120
        else:
            seconds = 60  # fallback
            
    # Enforce limits (Min: 15s, Max: 600s) on backend
    seconds = max(15, min(600, seconds))
    
    # Calculate word limit and scenes
    # Average narration speed is ~2.25 words per second
    total_words = int(seconds * 2.25)
    # Target average scene duration is 7.5 seconds
    num_scenes = max(3, round(seconds / 7.5))
    words_per_scene = int(total_words / num_scenes)
    
    prompt = f"""
    Write a viral video script about the topic: "{topic}".
    Tone: {tone}
    Language: {language}
    
    CRITICAL STRUCTURE RULES:
    - You MUST generate EXACTLY {num_scenes} scenes. No more, no less.
    - Each scene's narration text must contain approximately {words_per_scene} words (between {words_per_scene - 3} and {words_per_scene + 3} words).
    - The total script across all scenes should sum up to approximately {total_words} words.
    - Structure the script into a chronological sequence of scenes.
    
    For each scene, provide:
    1. The narration text (what the voiceover says, translated to {language}).
    2. A short, punchy visual search query (in English, maximum 3-5 words) suitable for finding stock videos or YouTube videos (e.g., "slow motion space", "hands typing keyboard").
    
    CRITICAL VISUAL SEARCH QUERY RULES:
    - ALWAYS request real-world, authentic footage (no animations, cartoons, drawings, or vector graphics).
    - Keep the query extremely short and focused (maximum 3 to 5 words). Long sentences confuse search engines.
    - Include key subject terms related to the script topic (e.g., if the topic is Spider-Man, include "spider man" in the queries like "spider man cosplay", "spider man web shooter", "spider man parkour").
    - For fictional, comic, or movie-related topics, use descriptors like "cosplay", "real life", "props", or "diy build" to help locate real-world representations rather than cartoons or 3D animations.
    - The visual query must describe real-world objects, people, scenes, or actions. Avoid abstract concepts or abstract loop backgrounds.
    
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
    response = model.generate_content(prompt, request_options={"timeout": 60})
    
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

# 2. Edge-TTS & cvoice.ai Audio Generation
def generate_cvoice_voiceover(text, voice_id, api_key, output_path):
    """
    Calls the cvoice.ai REST API to generate and download speech audio.
    """
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json"
    }
    data = {
        "text": text,
        "voice_id": voice_id
    }
    url = "https://cvoice.ai/api/tts"
    try:
        # Increase timeout to 120s to allow the server to process voice generation under heavy load
        response = requests.post(url, headers=headers, json=data, timeout=120)
        if response.status_code == 200:
            res_data = response.json()
            audio_url = res_data.get("url")
            if audio_url:
                # Download audio file with 60s timeout
                r = requests.get(audio_url, timeout=60)
                if r.status_code == 200:
                    with open(output_path, "wb") as f:
                        f.write(r.content)
                    return True
                else:
                    raise ValueError(f"Failed to download audio from URL: {audio_url}")
            raise ValueError(f"No audio URL returned from cvoice.ai: {res_data}")
        else:
            raise ValueError(f"cvoice.ai API returned error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"Error generating cvoice.ai voiceover for voice_id '{voice_id}':", e)
        raise e

def trim_audio_silence(file_path):
    """
    Trims silence from the beginning and end of an audio file using FFmpeg.
    """
    import subprocess
    import shutil
    
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        return
        
    # We write to a temporary path, then move it back
    temp_path = file_path + ".trimmed.mp3"
    
    # Check if ffmpeg is available
    if not shutil.which("ffmpeg"):
        print("Warning: FFmpeg not found, skipping silence trimming.")
        return
        
    cmd = [
        "ffmpeg", "-y",
        "-i", file_path,
        "-af", "silenceremove=start_periods=1:start_threshold=-50dB:stop_periods=-1:stop_threshold=-50dB",
        temp_path
    ]
    
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0 and os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
            shutil.move(temp_path, file_path)
            print(f"Successfully trimmed silence from audio file: {file_path}")
        else:
            print(f"Warning: FFmpeg silence trimming failed for {file_path}. Error: {result.stderr}")
            if os.path.exists(temp_path):
                os.remove(temp_path)
    except Exception as e:
        print(f"Error trimming silence from {file_path}: {e}")
        if os.path.exists(temp_path):
            os.remove(temp_path)

def generate_voiceover_sync(text, voice, output_path):
    """
    Generates a voiceover audio file. If the voice is a cvoice voice ID
    and the API key is configured, uses cvoice.ai. Otherwise falls back to Edge-TTS.
    """
    if voice.startswith("cvoice:"):
        api_key = os.getenv("CVOICE_API_KEY")
        if api_key:
            # Parse voice_id (strip prefix and any language suffix, e.g. cvoice:guid_hi -> guid)
            raw_id = voice.replace("cvoice:", "")
            if raw_id.endswith("_hi"):
                voice_id = raw_id[:-3]
                fallback_voice = "hi-IN-SwaraNeural"
            elif raw_id.endswith("_en"):
                voice_id = raw_id[:-3]
                fallback_voice = "en-US-AndrewNeural"
            else:
                voice_id = raw_id
                fallback_voice = "en-US-AndrewNeural"
                
            print(f"Generating cvoice.ai voiceover for ID: {voice_id}...")
            try:
                generate_cvoice_voiceover(text, voice_id, api_key, output_path)
                trim_audio_silence(output_path)
                return
            except Exception as e:
                print(f"cvoice.ai generation failed ({e}). Falling back to Edge-TTS default voice: {fallback_voice}...")
                voice = fallback_voice
        else:
            print("cvoice.ai voice selected but CVOICE_API_KEY is not set. Falling back to Edge-TTS default...")
            # Detect language suffix to select a default voice
            voice = "hi-IN-SwaraNeural" if voice.endswith("_hi") else "en-US-AndrewNeural"

    async def _async_gen():
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_path)
        
    asyncio.run(_async_gen())
    trim_audio_silence(output_path)

# 3. Whisper Local Transcription with Word Timestamps
def transcribe_audio_to_words(audio_path, language=None):
    """
    Transcribes audio and returns a list of word segments with start/end times.
    Format: [{'word': 'hello', 'start': 0.1, 'end': 0.5}, ...]
    """
    model = get_whisper_model()
    result = model.transcribe(audio_path, word_timestamps=True, language=language)
    
    words_list = []
    for segment in result.get('segments', []):
        for word_info in segment.get('words', []):
            words_list.append({
                'word': word_info['word'].strip(),
                'start': word_info['start'],
                'end': word_info['end']
            })
    return words_list

def transliterate_words_to_hinglish(words):
    """
    Transliterates a list of Devanagari Hindi words into their Hinglish equivalents using Gemini.
    """
    if not words:
        return []
    
    # Extract word strings
    word_strs = [w['word'] for w in words]
    
    # Call Gemini in a single prompt to transliterate
    prompt = f"""
    You are a precise transliterator from Hindi Devanagari to Romanized Hindi (Hinglish).
    Transliterate the following list of Hindi words into their phonetic Hinglish equivalents (using English/Latin characters, informal conversational spelling). 
    Preserve the exact order and length.
    Return ONLY a valid JSON array of strings matching the inputs.

    Input:
    {json.dumps(word_strs, ensure_ascii=False)}
    """
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt, request_options={"timeout": 30})
        
        # Clean response markdown wrappers if any
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        
        transliterated_strs = json.loads(text)
        if len(transliterated_strs) == len(words):
            # Update the original dicts
            for i, tw in enumerate(transliterated_strs):
                words[i]['word'] = tw
            print("Successfully transliterated Devanagari words to Hinglish!")
        else:
            print(f"Warning: Transliteration length mismatch ({len(transliterated_strs)} vs {len(words)}). Using original words.")
    except Exception as e:
        print("Failed to transliterate words to Hinglish:", e)
        
    return words

def clean_search_query(query):
    """
    Cleans and simplifies long descriptive search queries (e.g. from Gemini)
    into a shorter focused phrase suitable for Pexels and YouTube searches.
    """
    if not query:
        return ""
    if query.startswith("http://") or query.startswith("https://"):
        return query
        
    import re
    # Split by comma, semicolon, or period to isolate the main clause
    parts = re.split(r'[,;.]', query)
    short_query = parts[0].strip()
    
    # Split into words and limit to maximum 10 words to keep it highly focused
    words = short_query.split()
    if len(words) > 10:
        short_query = " ".join(words[:10])
        
    return short_query.strip()

# 4. Pexels API Stock Video Fetcher
def search_pexels_videos(query, api_key=None, orientation=None):
    """
    Searches Pexels for videos and returns list of video objects.
    Optionally filters by orientation ('portrait' or 'landscape').
    If orientation search returns no results, falls back to general search.
    """
    cleaned_query = clean_search_query(query)
    key = api_key or os.getenv("PEXELS_API_KEY")
    if not key:
        return []
    
    headers = {"Authorization": key}
    
    def run_query(target_orientation):
        url = f"https://api.pexels.com/videos/search?query={cleaned_query}&per_page=5"
        if target_orientation:
            url += f"&orientation={target_orientation}"
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                videos = []
                for item in data.get('videos', []):
                    video_files = item.get('video_files', [])
                    
                    # Select the highest quality video link (HD/1080p preferred)
                    mp4_files = [vf for vf in video_files if vf.get('file_type') == 'video/mp4' and vf.get('link')]
                    if mp4_files:
                        def score_file(vf):
                            w = vf.get('width') or 0
                            h = vf.get('height') or 0
                            if (w == 1920 and h == 1080) or (w == 1080 and h == 1920):
                                return 100
                            if w >= 2000 or h >= 2000:
                                return 90
                            if w >= 1280 or h >= 1280:
                                return 80
                            return 10
                        
                        sorted_files = sorted(mp4_files, key=lambda x: (score_file(x), x.get('width') or 0), reverse=True)
                        video_url = sorted_files[0].get('link')
                    else:
                        video_url = None
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
            print(f"Error fetching Pexels videos with orientation '{target_orientation}' for query '{cleaned_query}':", e)
        return []

    # First attempt with requested orientation
    results = run_query(orientation)
    if results:
        return results
        
    # Fallback to general search if orientation filter was specified but returned no results
    if orientation:
        print(f"Pexels orientation search for '{orientation}' returned 0 results for '{cleaned_query}'. Running fallback query...")
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

def calculate_youtube_video_penalty(meta):
    """
    Computes a penalty score for a YouTube video metadata dictionary.
    Higher penalty indicates lower quality, watermarked, or branded content (news, gameplay, compilation).
    """
    penalty = 0
    
    title = (meta.get('title') or '').lower()
    channel = (meta.get('channel') or meta.get('uploader') or '').lower()
    description = (meta.get('description') or '').lower()
    tags = [t.lower() for t in (meta.get('tags') or [])]
    
    # 1. News, Broadcast & TV Station terms (highly branded, overlays, banners)
    news_terms = ['news', 'breaking', 'tv', 'television', 'broadcast', 'live', 'reporter', 'report', 'journal', 'interview', 'press', 'feed']
    # 2. Compilation, Social media re-edits & reaction clips (watermarks, text overlays)
    compilation_terms = ['compilation', 'tiktok', 'instagram', 'reels', 'funny', 'meme', 'memes', 'status', 'whatsapp', 'reaction', 'react', 'recap', 'best of']
    # 3. Gaming & Gameplay clips (HUD elements, game logs/watermarks)
    gaming_terms = ['gameplay', 'lets play', 'playthrough', 'walkthrough', 'gaming', 'twitch', 'livestream', 'roblox', 'minecraft', 'fortnite', 'gta', 'modded', 'mod']
    # 4. Intro/Outro/Promos & Text Overlay terms
    overlay_terms = ['logo', 'watermark', 'intro', 'outro', 'subscribe', 'promo', 'promotional', 'lyrics', 'subtitles', 'captions', 'with subtitles', 'trailer', 'teaser']

    # Check Channel / Uploader name (high penalty if channel is news, funny, compilation or gaming focused)
    for term in news_terms + compilation_terms + gaming_terms:
        if term in channel:
            penalty += 15
            break
            
    # Check Title (strong penalty if title explicitly says compilation, gaming, or news)
    for term in news_terms + compilation_terms + gaming_terms:
        if term in title:
            penalty += 10
            
    for term in overlay_terms:
        if term in title:
            penalty += 8

    # Check Tags
    for term in news_terms + compilation_terms + gaming_terms + overlay_terms:
        if any(term in tag for tag in tags):
            penalty += 3
            break
            
    # Check Description (lower penalty since B-rolls might have standard promos in description)
    for term in compilation_terms + gaming_terms + overlay_terms:
        if term in description:
            penalty += 2
            
    return penalty

def download_youtube_clip_sync(query, dest_path, aspect_ratio="9:16"):
    """
    Searches YouTube for query and downloads the first video result under 10 minutes
    that matches the desired aspect ratio (if possible).
    Restricts resolution to <=720p for speed.
    Returns the YouTube watch URL of the downloaded video.
    """
    import yt_dlp
    
    # We remove the target file if it already exists to avoid conflict
    if os.path.exists(dest_path):
        try: os.remove(dest_path)
        except: pass
        
    is_direct_url = query.startswith("http://") or query.startswith("https://")
    
    if is_direct_url:
        print(f"yt-dlp downloading direct URL: {query}...")
        ydl_opts = {
            'format': 'bestvideo[height<=720][ext=mp4]/best[height<=720]/best',
            'outtmpl': dest_path,
            'quiet': True,
            'noplaylist': True,
            'source_address': '0.0.0.0',  # force IPv4 to bypass bot detection blocks
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(query, download=True)
                watch_url = info.get('webpage_url') or query
                print(f"Successfully downloaded YouTube video from direct URL: {watch_url}")
                return watch_url
            except Exception as e:
                print(f"yt-dlp direct download failed for '{query}': {e}")
                raise e
    else:
        # Search query
        cleaned_query = clean_search_query(query)
        
        # Append aspect-ratio specific terms to push YouTube to return vertical vs widescreen B-roll
        if aspect_ratio == "9:16":
            search_query_term = f"{cleaned_query} cinematic vertical B-roll footage no watermark"
        else:
            search_query_term = f"{cleaned_query} cinematic raw B-roll footage no logo"
            
        print(f"yt-dlp searching for query: {search_query_term} (original: {query}, ratio: {aspect_ratio})...")
        search_query = f"ytsearch10:{search_query_term}"
        
        # Step 1: Flat search to get video IDs and durations without triggering blocks or downloading pages
        flat_opts = {
            'default_search': 'ytsearch10',
            'quiet': True,
            'extract_flat': True,
            'source_address': '0.0.0.0',
        }
        
        candidates = []
        with yt_dlp.YoutubeDL(flat_opts) as ydl:
            try:
                info = ydl.extract_info(search_query, download=False)
                if info and 'entries' in info:
                    for entry in info['entries']:
                        if entry:
                            video_id = entry.get('id')
                            duration = entry.get('duration')
                            if video_id:
                                # Prioritize filtering by duration if present (between 5s and 600s)
                                if duration is None or (5 <= duration <= 600):
                                    candidates.append(entry)
            except Exception as e:
                print(f"yt-dlp flat search failed: {e}")
                raise e
                
        if not candidates:
            raise ValueError(f"No search result matching duration <= 10m found on YouTube for: {query}")
            
        # Step 2: Select and download the best candidate that fits the target orientation and has the lowest logo/quality penalty.
        # Check top 5 candidates for orientation match and clean B-roll score.
        download_opts = {
            'format': 'bestvideo[height<=720][ext=mp4]/best[height<=720]/best',
            'outtmpl': dest_path,
            'quiet': True,
            'noplaylist': True,
            'source_address': '0.0.0.0',
        }
        
        matching_ratio_candidates = []
        other_ratio_candidates = []
        
        print("Analyzing search candidate orientations and logo/quality penalties...")
        for candidate in candidates[:5]:
            video_id = candidate.get('id')
            watch_url = f"https://www.youtube.com/watch?v={video_id}"
            
            with yt_dlp.YoutubeDL({'quiet': True, 'source_address': '0.0.0.0'}) as ydl:
                try:
                    meta = ydl.extract_info(watch_url, download=False)
                    width = meta.get('width') or 0
                    height = meta.get('height') or 0
                    
                    is_vertical = height > width
                    is_widescreen = width > height
                    
                    # Compute penalty score
                    penalty = calculate_youtube_video_penalty(meta)
                    
                    safe_title = meta.get('title', '').encode('ascii', 'ignore').decode('ascii')
                    safe_channel = (meta.get('channel') or meta.get('uploader') or '').encode('ascii', 'ignore').decode('ascii')
                    print(f"  Candidate {video_id}: {width}x{height} | Penalty: {penalty} | Channel: '{safe_channel}' | Title: '{safe_title[:50]}'")
                    
                    is_match = (aspect_ratio == "9:16" and is_vertical) or (aspect_ratio == "16:9" and is_widescreen)
                    
                    if is_match:
                        matching_ratio_candidates.append((penalty, watch_url))
                    else:
                        other_ratio_candidates.append((penalty, watch_url))
                except Exception as e:
                    print(f"  Failed to extract metadata for {video_id}: {e}")
                    # Default high penalty for failed metadata fetch
                    other_ratio_candidates.append((50, watch_url))
                    
        # Sort both lists by penalty (ascending, lowest penalty first)
        matching_ratio_candidates.sort(key=lambda x: x[0])
        other_ratio_candidates.sort(key=lambda x: x[0])
        
        # Combine lists: prioritize matching orientation, then fallback orientation
        urls_to_try = [url for penalty, url in matching_ratio_candidates]
        urls_to_try.extend([url for penalty, url in other_ratio_candidates])
        
        # Add rest of the unchecked candidates from the top 10 as absolute fallback
        for candidate in candidates[5:]:
            urls_to_try.append(f"https://www.youtube.com/watch?v={candidate.get('id')}")
            
        # Try downloading in order
        last_err = None
        for watch_url in urls_to_try:
            print(f"Attempting to download video: {watch_url}...")
            if os.path.exists(dest_path):
                try: os.remove(dest_path)
                except: pass
                
            with yt_dlp.YoutubeDL(download_opts) as ydl:
                try:
                    ydl.extract_info(watch_url, download=True)
                    print(f"Successfully downloaded YouTube video: {watch_url}")
                    return watch_url
                except Exception as e:
                    print(f"yt-dlp download failed for video {watch_url}: {e}")
                    last_err = e
                    continue
        
        if last_err:
            raise last_err
        raise ValueError(f"No search result matching duration <= 10m found on YouTube for: {query}")
