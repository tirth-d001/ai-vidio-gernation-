import os
import subprocess
import shutil
import math
import PIL.Image
# Monkey-patch PIL.Image.ANTIALIAS for compatibility with newer Pillow versions
if not hasattr(PIL.Image, "ANTIALIAS"):
    PIL.Image.ANTIALIAS = PIL.Image.Resampling.LANCZOS

from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_videoclips, CompositeAudioClip
from moviepy.video.fx.all import mirror_x, resize
from PIL import Image

def detect_ffmpeg():
    """
    Checks if ffmpeg is available on the system path.
    """
    return shutil.which("ffmpeg") is not None

def crop_to_aspect_ratio(clip, target_ratio="9:16"):
    """
    Crops a video clip to 9:16 (vertical) or 16:9 (widescreen).
    """
    w, h = clip.size
    
    if target_ratio == "9:16":
        # Target aspect ratio is 9/16 = 0.5625
        target_w = int(h * 9 / 16)
        if target_w <= w:
            # Crop sides
            x1 = (w - target_w) // 2
            x2 = x1 + target_w
            cropped = clip.crop(x1=x1, y1=0, x2=x2, y2=h)
        else:
            # Scale and crop top/bottom
            target_h = int(w * 16 / 9)
            y1 = (h - target_h) // 2
            y2 = y1 + target_h
            cropped = clip.crop(x1=0, y1=y1, x2=w, y2=y2)
        # Resize to standard mobile Full HD (1080x1920)
        return cropped.resize(newsize=(1080, 1920))
        
    else:  # "16:9"
        # Target aspect ratio is 16/9 = 1.777
        target_h = int(w * 9 / 16)
        if target_h <= h:
            # Crop top/bottom
            y1 = (h - target_h) // 2
            y2 = y1 + target_h
            cropped = clip.crop(x1=0, y1=y1, x2=w, y2=y2)
        else:
            # Crop sides
            target_w = int(h * 16 / 9)
            x1 = (w - target_w) // 2
            x2 = x1 + target_w
            cropped = clip.crop(x1=x1, y1=0, x2=x2, y2=h)
        # Resize to standard widescreen Full HD (1920x1080)
        return cropped.resize(newsize=(1920, 1080))

def generate_ass_subtitles(words, subtitle_style="MrBeast", aspect_ratio="9:16"):
    """
    Generates an Advanced SubStation Alpha (.ass) subtitle file.
    ASS subtitles support rich styling, margins, and center alignment.
    """
    font_name = "Arial Black" if subtitle_style == "MrBeast" else "Arial"
    
    # Scale canvas size and styles based on target aspect ratio (1080p canvas)
    if aspect_ratio == "9:16":
        play_res_x = 1080
        play_res_y = 1920
        font_size = 56 if subtitle_style == "MrBeast" else (44 if subtitle_style == "TikTok" else 36)
        margin_v = "120"
        outline_thickness = "6" if subtitle_style == "MrBeast" else "2"
    else:  # "16:9"
        play_res_x = 1920
        play_res_y = 1080
        font_size = 56 if subtitle_style == "MrBeast" else (44 if subtitle_style == "TikTok" else 36)
        margin_v = "100"
        outline_thickness = "6" if subtitle_style == "MrBeast" else "2"
    
    # Colors in Hex ABGR format (Alpha Blue Green Red)
    primary_color = "&H0000FFFF" if subtitle_style == "MrBeast" else "&H00FFFFFF"  # Yellow vs White
    outline_color = "&H00000000"  # Black
    back_color = "&H80000000" if subtitle_style == "TikTok" else "&H00000000"  # Translucent black capsule vs none
    
    border_style = "3" if subtitle_style == "TikTok" else "1"  # 3 = opaque box, 1 = outline + shadow
    
    # Screen alignment: 2 = Centered Bottom (standard subtitle position)
    alignment = "2"
    
    ass_template = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {play_res_x}
PlayResY: {play_res_y}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{primary_color},&H00FFFFFF,{outline_color},{back_color},-1,0,0,0,100,100,0,0,{border_style},{outline_thickness},0,{alignment},10,10,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    # Generate dialogue lines
    # For high engagement shorts, we group words into very small phrases (1-2 words at a time)
    dialogue_lines = []
    
    # Group words by duration (e.g. max 2-3 words per subtitle block, or group by 0.8s intervals)
    current_phrase = []
    phrase_start = None
    
    for i, word_info in enumerate(words):
        word = word_info['word']
        start = word_info['start']
        end = word_info['end']
        
        if phrase_start is None:
            phrase_start = start
            
        # Clean word from punctuation for comparison if needed
        clean_word = word.upper() if subtitle_style == "MrBeast" else word
        current_phrase.append(clean_word)
        
        # Trigger point to render phrase:
        # Group size of 2 words, or if there's a pause > 0.4s
        is_last = (i == len(words) - 1)
        next_start = words[i+1]['start'] if not is_last else None
        
        if len(current_phrase) >= 2 or is_last or (next_start and (next_start - end) > 0.4):
            # Convert float seconds to ASS timestamp format: H:MM:SS.CS (Centiseconds)
            def format_time(sec):
                h = int(sec // 3600)
                m = int((sec % 3600) // 60)
                s = int(sec % 60)
                cs = int(round((sec - int(sec)) * 100))
                if cs >= 100:
                    cs = 99
                return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
                
            start_str = format_time(phrase_start)
            end_str = format_time(end)
            
            phrase_text = " ".join(current_phrase)
                
            dialogue_lines.append(
                f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{phrase_text}"
            )
            
            # Reset
            current_phrase = []
            phrase_start = next_start
            
    return ass_template + "\n".join(dialogue_lines)

def assemble_video_pipeline(project_id, scenes, bg_music_path, bg_music_volume, aspect_ratio, dest_output_path):
    """
    Stitches scenes together, matches voiceover audio, performs cropping/filters,
    adds background music with ducking, and burns in subtitles.
    """
    video_clips = []
    audio_clips = []
    
    current_time = 0.0
    scene_clips_to_close = []
    
    try:
        # 1. Process each scene
        for scene in scenes:
            video_path = scene['video_path']
            voiceover_path = scene['voiceover_path']
            
            if not video_path or not os.path.exists(video_path):
                print(f"Skipping scene {scene['sequence']} - video clip missing.")
                continue
            if not voiceover_path or not os.path.exists(voiceover_path):
                print(f"Skipping scene {scene['sequence']} - voiceover audio missing.")
                continue
                
            # Load voiceover and video
            voice_audio = AudioFileClip(voiceover_path)
            duration = voice_audio.duration
            
            # Load video clip
            vid_clip = VideoFileClip(video_path)
            
            # Adjust video clip duration
            if vid_clip.duration < duration:
                # If too short, loop it
                n_loops = math.ceil(duration / vid_clip.duration)
                # Simple loop concatenation
                vid_clip = concatenate_videoclips([vid_clip] * n_loops).subclip(0, duration)
            else:
                # Trim to match voiceover
                vid_clip = vid_clip.subclip(0, duration)
                
            # Apply crop and aspect ratio resize
            vid_clip = crop_to_aspect_ratio(vid_clip, aspect_ratio)
            
            # Mirror the video to help avoid copyright matches
            vid_clip = mirror_x(vid_clip)
            
            # Mute the original video clip audio completely
            vid_clip = vid_clip.set_audio(None)
            
            # Position voiceover audio at the scene timeline start
            voice_audio = voice_audio.set_start(current_time)
            
            video_clips.append(vid_clip)
            audio_clips.append(voice_audio)
            
            # Track current timeline head
            current_time += duration
            
        if not video_clips:
            raise ValueError("No valid video scenes to assemble.")
            
        # 2. Stitch video tracks
        final_video = concatenate_videoclips(video_clips, method="compose")
        total_duration = final_video.duration
        
        # 3. Add Background Music with smart audio ducking
        narration_audio = CompositeAudioClip(audio_clips)
        
        final_audio_tracks = [narration_audio]
        
        if bg_music_path and os.path.exists(bg_music_path):
            bg_music = AudioFileClip(bg_music_path)
            # Loop bg music if it's shorter than the video
            if bg_music.duration < total_duration:
                n_loops = math.ceil(total_duration / bg_music.duration)
                bg_music = concatenate_videoclips([bg_music] * n_loops).subclip(0, total_duration)
            else:
                bg_music = bg_music.subclip(0, total_duration)
                
            # Apply smart audio ducking (lower bg volume when narration is active)
            # Simple ducking implementation: set constant soft background volume
            bg_music = bg_music.volumex(bg_music_volume)
            final_audio_tracks.append(bg_music)
            
        final_audio = CompositeAudioClip(final_audio_tracks)
        final_video = final_video.set_audio(final_audio)
        
        # 4. Render intermediate video (without subtitles)
        temp_rendered_path = dest_output_path.replace(".mp4", "_temp.mp4")
        
        # Render settings optimized for high-quality Full HD output
        final_video.write_videofile(
            temp_rendered_path,
            fps=24,
            codec='libx264',
            audio_codec='aac',
            bitrate='8000k',
            remove_temp=True,
            preset='fast',  # fast encoding for better H.264 compression/quality balance
            threads=4
        )
        
        # Explicitly close MoviePy resources to avoid file lock issues on Windows
        for clip in video_clips:
            clip.close()
        for clip in audio_clips:
            clip.close()
        final_video.close()
        narration_audio.close()
        final_audio.close()
        
        return temp_rendered_path
        
    except Exception as e:
        print("Error during video assembly pipeline:", e)
        # Cleanup clips in case of crash
        for clip in video_clips:
            try: clip.close()
            except: pass
        for clip in audio_clips:
            try: clip.close()
            except: pass
        raise e

def burn_subtitles(video_path, ass_path, output_path):
    """
    Uses FFmpeg CLI to burn Advanced SubStation Alpha (.ass) subtitles onto the video.
    This method avoids ImageMagick and runs extremely fast.
    """
    if not detect_ffmpeg():
        raise RuntimeError("FFmpeg was not found on your system path. Please configure FFmpeg.")
        
    # On Windows, FFmpeg requires escaping the path for the subtitle filter.
    # We replace backslashes with forward slashes and escape colon for Windows paths.
    escaped_ass_path = ass_path.replace("\\", "/").replace(":", "\\:")
    
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"ass='{escaped_ass_path}'",
        "-c:a", "copy",  # Keep audio codec
        "-preset", "ultrafast",
        output_path
    ]
    
    print("Running FFmpeg burn command:", " ".join(cmd))
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    if result.returncode != 0:
        print("FFmpeg Error details:", result.stderr)
        raise RuntimeError(f"FFmpeg subtitle burning failed: {result.stderr}")
        
    return output_path
