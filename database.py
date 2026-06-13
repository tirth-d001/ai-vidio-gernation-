import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'generator.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Projects table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            prompt TEXT,
            aspect_ratio TEXT DEFAULT '9:16',
            duration TEXT DEFAULT 'Short',
            voice TEXT DEFAULT 'en-US-AndrewNeural',
            subtitle_style TEXT DEFAULT 'MrBeast',
            bg_music TEXT DEFAULT 'none',
            bg_music_volume REAL DEFAULT 0.1,
            voice_volume REAL DEFAULT 1.0,
            visual_source TEXT DEFAULT 'pexels',
            status TEXT DEFAULT 'Draft',
            error_message TEXT,
            video_path TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    ''')
    
    # Try adding visual_source column to projects if it doesn't exist (migration)
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN visual_source TEXT DEFAULT 'pexels'")
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    # Scenes table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scenes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            sequence INTEGER,
            text TEXT,
            voiceover_path TEXT,
            visual_query TEXT,
            video_source TEXT,
            video_url TEXT,
            video_path TEXT,
            start_time REAL DEFAULT 0.0,
            duration REAL DEFAULT 0.0,
            FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
        )
    ''')
    
    conn.commit()
    conn.close()

def create_project(title, prompt, aspect_ratio, duration, voice, subtitle_style, bg_music, visual_source='pexels'):
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute('''
        INSERT INTO projects (title, prompt, aspect_ratio, duration, voice, subtitle_style, bg_music, visual_source, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (title, prompt, aspect_ratio, duration, voice, subtitle_style, bg_music, visual_source, now, now))
    project_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return project_id

def get_project(project_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    project = cursor.execute('SELECT * FROM projects WHERE id = ?', (project_id,)).fetchone()
    conn.close()
    return dict(project) if project else None

def get_all_projects():
    conn = get_db_connection()
    cursor = conn.cursor()
    projects = cursor.execute('SELECT * FROM projects ORDER BY created_at DESC').fetchall()
    conn.close()
    return [dict(p) for p in projects]

def update_project(project_id, **kwargs):
    conn = get_db_connection()
    cursor = conn.cursor()
    kwargs['updated_at'] = datetime.now().isoformat()
    
    fields = []
    values = []
    for key, val in kwargs.items():
        fields.append(f"{key} = ?")
        values.append(val)
    values.append(project_id)
    
    query = f"UPDATE projects SET {', '.join(fields)} WHERE id = ?"
    cursor.execute(query, values)
    conn.commit()
    conn.close()

def delete_project(project_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM projects WHERE id = ?', (project_id,))
    cursor.execute('DELETE FROM scenes WHERE project_id = ?', (project_id,))
    conn.commit()
    conn.close()

def add_scene(project_id, sequence, text, visual_query):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO scenes (project_id, sequence, text, visual_query)
        VALUES (?, ?, ?, ?)
    ''', (project_id, sequence, text, visual_query))
    scene_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return scene_id

def get_scenes(project_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    scenes = cursor.execute('SELECT * FROM scenes WHERE project_id = ? ORDER BY sequence ASC', (project_id,)).fetchall()
    conn.close()
    return [dict(s) for s in scenes]

def update_scene(scene_id, **kwargs):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    fields = []
    values = []
    for key, val in kwargs.items():
        fields.append(f"{key} = ?")
        values.append(val)
    values.append(scene_id)
    
    query = f"UPDATE scenes SET {', '.join(fields)} WHERE id = ?"
    cursor.execute(query, values)
    conn.commit()
    conn.close()

# Initialize on import
if not os.path.exists(DB_PATH):
    init_db()
