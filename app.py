import os
import threading
import traceback
import requests
from flask import Flask, render_template, request, jsonify, send_from_directory, url_for
from werkzeug.utils import secure_filename

import database as db
import api_helpers as api
import video_engine as engine

app = Flask(__name__)

# Directory Configurations
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'projects_data')
BG_MUSIC_DIR = os.path.join(BASE_DIR, 'static', 'bg_music')

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(BG_MUSIC_DIR, exist_ok=True)

# Global dictionary to track rendering progress messages
render_progress = {}

def get_project_dir(project_id):
    p_dir = os.path.join(DATA_DIR, f'project_{project_id}')
    os.makedirs(p_dir, exist_ok=True)
    os.makedirs(os.path.join(p_dir, 'voiceovers'), exist_ok=True)
    os.makedirs(os.path.join(p_dir, 'clips'), exist_ok=True)
    return p_dir

# Download default royalty-free tracks on startup
def download_default_bgm():
    tracks = {
        'tense_suspense.mp3': 'https://upload.wikimedia.org/wikipedia/commons/2/23/Epic_Suspense_Music_by_FesliyanStudios.mp3',
        'chill_lofi.mp3': 'https://upload.wikimedia.org/wikipedia/commons/d/df/Morning_Routine_Lofi.mp3',
        'inspiring_epic.mp3': 'https://upload.wikimedia.org/wikipedia/commons/e/ec/Epic_Inspirational_Cinematic_by_FesliyanStudios.mp3'
    }
    
    for filename, url in tracks.items():
        dest = os.path.join(BG_MUSIC_DIR, filename)
        if not os.path.exists(dest):
            print(f"Downloading default BGM track {filename}...")
            try:
                r = requests.get(url, timeout=20)
                if r.status_code == 200:
                    with open(dest, 'wb') as f:
                        f.write(r.content)
            except Exception as e:
                print(f"Failed to download default BGM {filename}:", e)

@app.route('/')
def index():
    return render_template('index.html')

# --- CONFIG API ---
@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    if request.method == 'POST':
        data = request.json or {}
        existing_gemini = os.getenv('GEMINI_API_KEY', '')
        existing_pexels = os.getenv('PEXELS_API_KEY', '')
        
        gemini_key = data.get('gemini_key', existing_gemini) if 'gemini_key' in data else existing_gemini
        pexels_key = data.get('pexels_key', existing_pexels) if 'pexels_key' in data else existing_pexels
        
        # Write to .env file
        env_lines = []
        if os.path.exists('.env'):
            with open('.env', 'r') as f:
                env_lines = f.readlines()
                
        new_lines = []
        gemini_written = False
        pexels_written = False
        
        for line in env_lines:
            if line.startswith('GEMINI_API_KEY='):
                new_lines.append(f'GEMINI_API_KEY={gemini_key}\n')
                gemini_written = True
            elif line.startswith('PEXELS_API_KEY='):
                new_lines.append(f'PEXELS_API_KEY={pexels_key}\n')
                pexels_written = True
            else:
                new_lines.append(line)
                
        if not gemini_written:
            new_lines.append(f'GEMINI_API_KEY={gemini_key}\n')
        if not pexels_written:
            new_lines.append(f'PEXELS_API_KEY={pexels_key}\n')
            
        with open('.env', 'w') as f:
            f.writelines(new_lines)
            
        # Re-apply env config
        os.environ['GEMINI_API_KEY'] = gemini_key
        os.environ['PEXELS_API_KEY'] = pexels_key
        api.genai.configure(api_key=gemini_key)
        
        return jsonify({'status': 'success', 'message': 'Configuration updated successfully'})
    
    return jsonify({
        'gemini_key': os.getenv('GEMINI_API_KEY', ''),
        'pexels_key': os.getenv('PEXELS_API_KEY', '')
    })

# --- PROJECTS CRUD API ---
@app.route('/api/projects', methods=['GET'])
def get_projects():
    projects = db.get_all_projects()
    # Format dates
    return jsonify(projects)

@app.route('/api/projects', methods=['POST'])
def create_project():
    data = request.json or {}
    title = data.get('title', 'Untitled Project')
    prompt = data.get('prompt', '')
    aspect_ratio = data.get('aspect_ratio', '9:16')
    duration = data.get('duration', 'Short')
    voice = data.get('voice', 'en-US-AndrewNeural')
    subtitle_style = data.get('subtitle_style', 'MrBeast')
    bg_music = data.get('bg_music', 'none')
    
    project_id = db.create_project(
        title=title,
        prompt=prompt,
        aspect_ratio=aspect_ratio,
        duration=duration,
        voice=voice,
        subtitle_style=subtitle_style,
        bg_music=bg_music
    )
    
    # Initialize directory structure
    get_project_dir(project_id)
    
    project = db.get_project(project_id)
    return jsonify(project)

@app.route('/api/projects/<int:project_id>', methods=['GET'])
def get_project_details(project_id):
    project = db.get_project(project_id)
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    scenes = db.get_scenes(project_id)
    return jsonify({
        'project': project,
        'scenes': scenes
    })

@app.route('/api/projects/<int:project_id>', methods=['DELETE'])
def delete_project(project_id):
    project = db.get_project(project_id)
    if not project:
         return jsonify({'error': 'Project not found'}), 404
         
    # Delete folder (with fallback error handling for Windows file locks)
    p_dir = os.path.join(DATA_DIR, f'project_{project_id}')
    if os.path.exists(p_dir):
        try:
            shutil.rmtree(p_dir)
        except Exception as e:
            print(f"Warning: could not delete directory {p_dir} immediately: {e}")
            # Try to delete individual unlocked files inside
            for root, dirs, files in os.walk(p_dir, topdown=False):
                for name in files:
                    try: os.remove(os.path.join(root, name))
                    except: pass
                for name in dirs:
                    try: os.rmdir(os.path.join(root, name))
                    except: pass
            # Attempt to delete directory one last time (ignoring remaining locked files)
            try:
                shutil.rmtree(p_dir, ignore_errors=True)
            except:
                pass
        
    db.delete_project(project_id)
    return jsonify({'status': 'success', 'message': 'Project deleted'})

# --- SCRIPT GENERATION ---
@app.route('/api/projects/<int:project_id>/generate-script', methods=['POST'])
def generate_script(project_id):
    project = db.get_project(project_id)
    if not project:
        return jsonify({'error': 'Project not found'}), 404
        
    db.update_project(project_id, status='Generating Script')
    
    try:
        # Determine language/tone defaults
        # We can extract from metadata or support extra fields
        tone = "Dramatic" if "mystery" in project['prompt'].lower() or "scary" in project['prompt'].lower() else "Informative"
        
        # Call Gemini AI
        scenes_data = api.generate_script_and_keywords(
            topic=project['prompt'],
            duration=project['duration'],
            tone=tone,
            language="English"
        )
        
        # Clear existing scenes if any
        existing_scenes = db.get_scenes(project_id)
        for s in existing_scenes:
            # delete existing voiceover file if exists
            if s.get('voiceover_path') and os.path.exists(s['voiceover_path']):
                try: os.remove(s['voiceover_path'])
                except: pass
            if s.get('video_path') and os.path.exists(s['video_path']):
                try: os.remove(s['video_path'])
                except: pass
                
        # Connect to db, insert scenes
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM scenes WHERE project_id = ?', (project_id,))
        conn.commit()
        conn.close()
        
        # Insert new scenes
        for idx, scene in enumerate(scenes_data):
            db.add_scene(
                project_id=project_id,
                sequence=idx + 1,
                text=scene.get('text', ''),
                visual_query=scene.get('visual_query', '')
            )
            
        db.update_project(project_id, status='Script Generated')
        
        scenes = db.get_scenes(project_id)
        return jsonify({'status': 'success', 'scenes': scenes})
        
    except Exception as e:
        db.update_project(project_id, status='Failed', error_message=str(e))
        return jsonify({'error': str(e)}), 500

# --- UPDATE SCENES ---
@app.route('/api/projects/<int:project_id>/update-scenes', methods=['POST'])
def update_scenes(project_id):
    data = request.json or {}
    scenes_data = data.get('scenes', [])
    
    for s in scenes_data:
        db.update_scene(
            scene_id=s['id'],
            text=s.get('text', ''),
            visual_query=s.get('visual_query', ''),
            video_url=s.get('video_url', ''),
            video_source=s.get('video_source', '')
        )
    return jsonify({'status': 'success', 'message': 'Scenes updated'})

# --- STOCK MEDIA SEARCH ---
@app.route('/api/projects/<int:project_id>/search-media', methods=['GET'])
def search_media(project_id):
    query = request.args.get('query', '')
    if not query:
        return jsonify([])
        
    project = db.get_project(project_id)
    orientation = "portrait" if project and project.get('aspect_ratio') == "9:16" else "landscape"
    videos = api.search_pexels_videos(query, orientation=orientation)
    return jsonify(videos)

# --- BACKGROUND RENDER PROCESS ---
def render_project_worker(project_id):
    global render_progress
    p_dir = get_project_dir(project_id)
    project = db.get_project(project_id)
    scenes = db.get_scenes(project_id)
    
    render_progress[project_id] = "Setting up assets..."
    db.update_project(project_id, status='Rendering')
    
    try:
        # Step 1: Generate speech voiceovers
        render_progress[project_id] = "Generating AI Voiceovers..."
        for scene in scenes:
            vo_path = os.path.join(p_dir, 'voiceovers', f'scene_{scene["sequence"]}.mp3')
            api.generate_voiceover_sync(scene['text'], project['voice'], vo_path)
            db.update_scene(scene['id'], voiceover_path=vo_path)
            
        # Refresh scenes list to get voiceover paths
        scenes = db.get_scenes(project_id)
        
        # Step 2: Fetch and Download visual clips
        render_progress[project_id] = "Downloading Scene Videos..."
        orientation = "portrait" if project and project.get('aspect_ratio') == "9:16" else "landscape"
        for idx, scene in enumerate(scenes):
            clip_path = os.path.join(p_dir, 'clips', f'scene_{scene["sequence"]}.mp4')
            
            # If user hasn't selected a specific video_url, search and auto-download first result
            video_url = scene.get('video_url')
            if not video_url:
                # Search Pexels automatically with orientation filter
                results = api.search_pexels_videos(scene['visual_query'], orientation=orientation)
                if results:
                    video_url = results[0]['url']
                    db.update_scene(scene['id'], video_url=video_url, video_source='pexels')
                    
            if video_url:
                render_progress[project_id] = f"Downloading video for Scene {scene['sequence']}..."
                api.download_video_clip(video_url, clip_path)
                db.update_scene(scene['id'], video_path=clip_path)
            else:
                # Fallback empty canvas if video cannot be found
                # To wow the user, let's download a generic fallback video or raise error
                fallback_results = api.search_pexels_videos("abstract motion background", orientation=orientation)
                if fallback_results:
                    video_url = fallback_results[0]['url']
                    api.download_video_clip(video_url, clip_path)
                    db.update_scene(scene['id'], video_url=video_url, video_path=clip_path, video_source='pexels')
                else:
                    raise ValueError(f"No video clip found for scene {scene['sequence']} ('{scene['visual_query']}')")
                    
        # Refresh scenes
        scenes = db.get_scenes(project_id)
        
        # Step 3: Get audio word timestamps for captions
        render_progress[project_id] = "Analyzing speech timestamps..."
        all_words = []
        elapsed_audio_time = 0.0
        
        for scene in scenes:
            words = api.transcribe_audio_to_words(scene['voiceover_path'])
            # Adjust word timestamps to fit the global timeline
            for w in words:
                w['start'] += elapsed_audio_time
                w['end'] += elapsed_audio_time
                all_words.append(w)
                
            # Get duration of this scene audio
            # Using MoviePy to read duration
            from moviepy.editor import AudioFileClip
            audio = AudioFileClip(scene['voiceover_path'])
            elapsed_audio_time += audio.duration
            audio.close()
            
        # Write ASS Subtitle File
        render_progress[project_id] = "Generating styled subtitles..."
        ass_content = engine.generate_ass_subtitles(all_words, project['subtitle_style'], project['aspect_ratio'])
        ass_path = os.path.join(p_dir, 'subtitles.ass')
        with open(ass_path, 'w', encoding='utf-8') as f:
            f.write(ass_content)
            
        # Step 4: Stitch video clips and mix audio
        render_progress[project_id] = "Stitching clips and mixing audio..."
        bg_music_path = None
        if project['bg_music'] != 'none':
            bg_music_path = os.path.join(BG_MUSIC_DIR, project['bg_music'])
            
        temp_video_path = os.path.join(p_dir, 'temp_video.mp4')
        final_temp_path = engine.assemble_video_pipeline(
            project_id=project_id,
            scenes=scenes,
            bg_music_path=bg_music_path,
            bg_music_volume=project['bg_music_volume'],
            aspect_ratio=project['aspect_ratio'],
            dest_output_path=temp_video_path
        )
        
        # Step 5: Burn subtitles using FFmpeg
        render_progress[project_id] = "Burning subtitles onto final video..."
        final_video_path = os.path.join(p_dir, 'final_video.mp4')
        
        engine.burn_subtitles(final_temp_path, ass_path, final_video_path)
        
        # Cleanup intermediate temp files
        try: os.remove(final_temp_path)
        except: pass
        
        # Update database status
        db.update_project(project_id, status='Completed', video_path=final_video_path)
        render_progress[project_id] = "Done!"
        
    except Exception as e:
        print("Rendering failed:")
        traceback.print_exc()
        db.update_project(project_id, status='Failed', error_message=str(e))
        render_progress[project_id] = f"Failed: {str(e)}"

@app.route('/api/projects/<int:project_id>/update-settings', methods=['POST'])
def update_project_settings(project_id):
    data = request.json or {}
    voice_volume = data.get('voice_volume', 1.0)
    bg_music_volume = data.get('bg_music_volume', 0.1)
    
    db.update_project(
        project_id,
        voice_volume=voice_volume,
        bg_music_volume=bg_music_volume
    )
    return jsonify({'status': 'success', 'message': 'Settings updated'})

@app.route('/api/projects/<int:project_id>/render', methods=['POST'])
def render_video(project_id):
    project = db.get_project(project_id)
    if not project:
        return jsonify({'error': 'Project not found'}), 404
        
    # Start rendering thread
    t = threading.Thread(target=render_project_worker, args=(project_id,))
    t.daemon = True
    t.start()
    
    return jsonify({'status': 'success', 'message': 'Rendering started'})

@app.route('/api/projects/<int:project_id>/status', methods=['GET'])
def get_render_status(project_id):
    project = db.get_project(project_id)
    progress_msg = render_progress.get(project_id, "Idle")
    return jsonify({
        'status': project['status'] if project else 'Idle',
        'progress_message': progress_msg,
        'error_message': project.get('error_message') if project else None
    })

# --- STATIC CONTENT ROUTING ---
@app.route('/video/<int:project_id>')
def serve_video(project_id):
    project = db.get_project(project_id)
    if not project or not project.get('video_path'):
        return "Video not found", 404
        
    directory = os.path.dirname(project['video_path'])
    filename = os.path.basename(project['video_path'])
    return send_from_directory(directory, filename)

@app.route('/audio/voiceover/<int:scene_id>')
def serve_voiceover(scene_id):
    # Fetch scene voiceover
    conn = db.get_db_connection()
    scene = conn.execute('SELECT * FROM scenes WHERE id = ?', (scene_id,)).fetchone()
    conn.close()
    
    if not scene or not scene['voiceover_path']:
        return "Voiceover not found", 404
        
    directory = os.path.dirname(scene['voiceover_path'])
    filename = os.path.basename(scene['voiceover_path'])
    return send_from_directory(directory, filename)

# Run BGM Downloader on startup
download_default_bgm()

if __name__ == '__main__':
    # Server runs locally on port 5000
    app.run(debug=True, port=5000)
