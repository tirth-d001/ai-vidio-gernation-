// Global State
let currentProjectId = null;
let currentScenes = [];
let selectedSceneIndexForMediaReplace = null;
let renderPollInterval = null;

// Initialize App
document.addEventListener('DOMContentLoaded', () => {
    // Initialize Lucide Icons
    try {
        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    } catch (err) {
        console.error("Lucide failed to load:", err);
    }
    
    // Tab switching listener
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const tabName = item.getAttribute('data-tab');
            switchTab(tabName);
        });
    });

    // Setup forms
    document.getElementById('btn-create-project').addEventListener('click', handleCreateProject);
    document.getElementById('btn-save-settings').addEventListener('click', handleSaveSettings);
    document.getElementById('btn-render-video').addEventListener('click', handleRenderVideo);
    document.getElementById('btn-modal-media-search').addEventListener('click', handleModalMediaSearch);
    document.getElementById('btn-clear-temp-clips').addEventListener('click', () => handleClearTempClips(currentProjectId));
    document.getElementById('btn-output-clear-temp-clips').addEventListener('click', () => handleClearTempClips(currentProjectId));
    
    // Media Search keyboard trigger
    document.getElementById('modal-media-search-input').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleModalMediaSearch();
    });

    // Load initial data
    loadConfig();
    loadProjects();
    updateVoiceOptions();
    initializeCustomSelects();
});

// Toast Notifications Helper
function showToast(message, type = 'success') {
    const toast = document.getElementById('notification-toast');
    const toastMsg = document.getElementById('toast-msg');
    const toastIcon = document.getElementById('toast-icon');
    
    toastMsg.textContent = message;
    
    if (type === 'success') {
        toast.style.borderColor = 'rgba(0, 255, 135, 0.25)';
        toastIcon.setAttribute('data-lucide', 'check-circle');
        toastIcon.style.color = 'var(--accent-success)';
    } else {
        toast.style.borderColor = 'rgba(255, 0, 127, 0.25)';
        toastIcon.setAttribute('data-lucide', 'alert-circle');
        toastIcon.style.color = 'var(--accent-magenta)';
    }
    
    try {
        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    } catch (err) {
        console.error("Lucide failed to load:", err);
    }
    toast.classList.remove('hidden');
    
    setTimeout(() => {
        toast.classList.add('hidden');
    }, 4000);
}

// Tab navigation manager
function switchTab(tabId) {
    // Deactivate all nav items
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
        if (item.getAttribute('data-tab') === tabId) {
            item.classList.add('active');
        }
    });

    // Deactivate all tab sections
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });

    // Activate specific tab section
    document.getElementById(`${tabId}-tab`).classList.add('active');
    
    // Custom triggers per tab
    if (tabId === 'dashboard') {
        loadProjects();
        // Clear any polling
        if (renderPollInterval) clearInterval(renderPollInterval);
    } else if (tabId === 'new-project') {
        resetSetupForm();
    }
}

// Load App Settings Config
async function loadConfig() {
    try {
        const response = await fetch('/api/config');
        const data = await response.json();
        
        const geminiInput = document.getElementById('settings-gemini-key');
        const pexelsInput = document.getElementById('settings-pexels-key');
        const cvoiceInput = document.getElementById('settings-cvoice-key');
        
        if (data.gemini_key) {
            geminiInput.value = data.gemini_key.substring(0, 6) + '••••••••••••••••';
            geminiInput.placeholder = 'Key configured (Saved)';
        } else {
            geminiInput.value = '';
            geminiInput.placeholder = 'Enter Gemini API key...';
        }
        
        if (data.pexels_key) {
            pexelsInput.value = data.pexels_key.substring(0, 6) + '••••••••••••••••';
            pexelsInput.placeholder = 'Key configured (Saved)';
        } else {
            pexelsInput.value = '';
            pexelsInput.placeholder = 'Enter Pexels API key...';
        }

        if (data.cvoice_key) {
            cvoiceInput.value = data.cvoice_key.substring(0, 6) + '••••••••••••••••';
            cvoiceInput.placeholder = 'Key configured (Saved)';
        } else {
            cvoiceInput.value = '';
            cvoiceInput.placeholder = 'Enter cvoice.ai API key...';
        }
    } catch (e) {
        console.error('Failed to load settings config', e);
    }
}

// Save App Settings Config
async function handleSaveSettings() {
    const geminiValue = document.getElementById('settings-gemini-key').value.trim();
    const pexelsValue = document.getElementById('settings-pexels-key').value.trim();
    const cvoiceValue = document.getElementById('settings-cvoice-key').value.trim();
    
    const bodyData = {};
    
    // Only send the key if the user has changed it (it does not contain the bullet characters)
    if (geminiValue && !geminiValue.includes('••••')) {
        bodyData.gemini_key = geminiValue;
    } else if (geminiValue === '') {
        bodyData.gemini_key = ''; // Explicitly clear it if empty
    }
    
    if (pexelsValue && !pexelsValue.includes('••••')) {
        bodyData.pexels_key = pexelsValue;
    } else if (pexelsValue === '') {
        bodyData.pexels_key = ''; // Explicitly clear it if empty
    }

    if (cvoiceValue && !cvoiceValue.includes('••••')) {
        bodyData.cvoice_key = cvoiceValue;
    } else if (cvoiceValue === '') {
        bodyData.cvoice_key = ''; // Explicitly clear it if empty
    }
    
    // If nothing changed, just show success toast and exit
    if (Object.keys(bodyData).length === 0) {
        showToast('Settings saved successfully!');
        return;
    }

    try {
        const response = await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(bodyData)
        });
        const result = await response.json();
        if (result.status === 'success') {
            showToast('Settings saved successfully!');
            loadConfig(); // Reload to refresh the masked values
        } else {
            showToast('Failed to save settings', 'error');
        }
    } catch (e) {
        showToast('Error saving settings', 'error');
    }
}

// Load all project history on Dashboard
async function loadProjects() {
    try {
        const response = await fetch('/api/projects');
        const projects = await response.json();
        
        const grid = document.getElementById('projects-grid');
        const emptyState = document.getElementById('empty-state');
        
        grid.innerHTML = '';
        
        if (projects.length === 0) {
            emptyState.classList.remove('hidden');
            grid.classList.add('hidden');
            return;
        }
        
        emptyState.classList.add('hidden');
        grid.classList.remove('hidden');
        
        projects.forEach(p => {
            const card = document.createElement('div');
            card.className = 'card glass-card project-card animate-slide-in';
            
            // Format status styling
            let statusClass = 'status-draft';
            if (p.status === 'Completed') statusClass = 'status-completed';
            else if (p.status === 'Rendering' || p.status === 'Generating Script') statusClass = 'status-rendering';
            else if (p.status === 'Failed') statusClass = 'status-failed';
            
            const ratioLabel = p.aspect_ratio === '9:16' ? 'Vertical 9:16' : 'Widescreen 16:9';
            
            card.innerHTML = `
                <div class="project-ratio-badge">${ratioLabel}</div>
                <div class="project-card-body" onclick="openProject(${p.id})">
                    <h3 class="project-title">${p.title}</h3>
                    <p class="project-prompt">${p.prompt || 'No details provided'}</p>
                    <div class="project-meta">
                        <span class="project-status ${statusClass}">
                            <span class="status-dot"></span>
                            ${p.status}
                        </span>
                        <div class="project-actions" onclick="event.stopPropagation();">
                            <button class="btn-card-action btn-delete" onclick="deleteProject(${p.id})" title="Delete Project">
                                <i data-lucide="trash-2"></i>
                            </button>
                        </div>
                    </div>
                </div>
            `;
            grid.appendChild(card);
        });
        
        try {
            if (typeof lucide !== 'undefined') {
                lucide.createIcons();
            }
        } catch (err) {
            console.error("Lucide failed to load:", err);
        }
    } catch (e) {
        console.error('Error loading projects list', e);
    }
}

function resetSetupForm() {
    document.getElementById('project-title').value = '';
    document.getElementById('project-prompt').value = '';
    document.getElementById('ratio-916').checked = true;
    
    // Reset video language
    const languageSelect = document.getElementById('language-select');
    if (languageSelect) {
        languageSelect.value = 'en';
        languageSelect.dispatchEvent(new Event('change'));
    }
    
    // Reset video length
    const durationSelect = document.getElementById('duration-select');
    if (durationSelect) {
        durationSelect.value = '60';
        durationSelect.dispatchEvent(new Event('change'));
    }
    const customWrapper = document.getElementById('custom-duration-wrapper');
    if (customWrapper) customWrapper.classList.add('hidden');
    const customInput = document.getElementById('custom-duration-input');
    if (customInput) customInput.value = '45';
    
    // Reset cvoice custom Voice ID
    const cvoiceInput = document.getElementById('cvoice-custom-voice-id');
    if (cvoiceInput) cvoiceInput.value = '';
    const cvoiceWrapper = document.getElementById('cvoice-custom-voice-wrapper');
    if (cvoiceWrapper) cvoiceWrapper.classList.add('hidden');
    
    const voiceSelect = document.getElementById('voice-select');
    if (voiceSelect) {
        voiceSelect.selectedIndex = 0;
        voiceSelect.dispatchEvent(new Event('change'));
    }
    const subtitleSelect = document.getElementById('subtitle-select');
    if (subtitleSelect) {
        subtitleSelect.selectedIndex = 0;
        subtitleSelect.dispatchEvent(new Event('change'));
    }
    const bgMusicSelect = document.getElementById('bg-music-select');
    if (bgMusicSelect) {
        bgMusicSelect.selectedIndex = 0;
        bgMusicSelect.dispatchEvent(new Event('change'));
    }
    const visualSourceSelect = document.getElementById('visual-source-select');
    if (visualSourceSelect) {
        visualSourceSelect.value = 'pexels';
        visualSourceSelect.dispatchEvent(new Event('change'));
    }
    
    document.getElementById('setup-form-container').classList.remove('hidden');
    document.getElementById('storyboard-container').classList.add('hidden');
    document.getElementById('rendering-container').classList.add('hidden');
    document.getElementById('output-container').classList.add('hidden');
}

function toggleCustomDuration() {
    const select = document.getElementById('duration-select');
    const wrapper = document.getElementById('custom-duration-wrapper');
    if (select.value === 'custom') {
        wrapper.classList.remove('hidden');
    } else {
        wrapper.classList.add('hidden');
    }
}

// Create project entry and invoke Gemini scriptwriter
async function handleCreateProject() {
    const title = document.getElementById('project-title').value.trim() || 'Untitled Video';
    const prompt = document.getElementById('project-prompt').value.trim();
    
    if (!prompt) {
        showToast('Please describe your video topic first.', 'error');
        return;
    }
    
    // Check if API keys are set
    const responseConfig = await fetch('/api/config');
    const configData = await responseConfig.json();
    if (!configData.gemini_key) {
        showToast('Please enter your Gemini API Key in settings first.', 'error');
        switchTab('settings');
        return;
    }

    const aspect_ratio = document.querySelector('input[name="aspect-ratio"]:checked') ? 
        document.querySelector('input[name="aspect-ratio"]:checked').value : '9:16';
        
    // Parse video duration selection
    let duration = document.getElementById('duration-select').value;
    if (duration === 'custom') {
        const customVal = parseInt(document.getElementById('custom-duration-input').value);
        if (isNaN(customVal) || customVal < 15 || customVal > 600) {
            showToast('Custom duration must be between 15 and 600 seconds.', 'error');
            return;
        }
        duration = String(customVal);
    }
    
    let voice = document.getElementById('voice-select').value;
    if (voice === 'cvoice_custom') {
        const customVoiceId = document.getElementById('cvoice-custom-voice-id').value.trim();
        if (!customVoiceId) {
            showToast('Please enter a custom cvoice.ai Voice ID first.', 'error');
            return;
        }
        
        // Also check if cvoice API key is set
        if (!configData.cvoice_key) {
            showToast('Please enter your cvoice.ai API Key in settings first.', 'error');
            switchTab('settings');
            return;
        }
        
        const lang = document.getElementById('language-select').value;
        voice = 'cvoice:' + customVoiceId + '_' + lang;
    }
    const subtitle_style = document.getElementById('subtitle-select').value;
    const bg_music = document.getElementById('bg-music-select').value;
    const visual_source = document.getElementById('visual-source-select').value;
    
    showToast('Creating project record...');
    
    try {
        // Step 1: Create local project DB entry
        const createRes = await fetch('/api/projects', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, prompt, aspect_ratio, duration, voice, subtitle_style, bg_music, visual_source })
        });
        const project = await createRes.json();
        currentProjectId = project.id;
        
        // Hide config and show render loader during AI script generation
        document.getElementById('setup-form-container').classList.add('hidden');
        document.getElementById('rendering-container').classList.remove('hidden');
        updateProgressUI(20, 'Generating Storyboard Script...', 'AI is writing script paragraphs and visual prompts...');
        
        // Step 2: Trigger Gemini Scriptwriter
        const scriptRes = await fetch(`/api/projects/${currentProjectId}/generate-script`, { method: 'POST' });
        const scriptResult = await scriptRes.json();
        
        if (scriptResult.error) {
            throw new Error(scriptResult.error);
        }
        
        showToast('Storyboard generated successfully!');
        
        // Load storyboard view
        openProject(currentProjectId);
        
    } catch (e) {
        showToast(e.message || 'Error creating project', 'error');
        resetSetupForm();
    }
}

// Open and load project storyboard
async function openProject(projectId) {
    if (renderPollInterval) clearInterval(renderPollInterval);
    
    try {
        const response = await fetch(`/api/projects/${projectId}`);
        if (!response.ok) throw new Error('Project details could not be retrieved');
        
        const data = await response.json();
        const project = data.project;
        currentProjectId = project.id;
        currentScenes = data.scenes;
        
        // Populate view parameters first
        document.getElementById('edit-project-title').textContent = `Storyboard: ${project.title}`;
        document.getElementById('preview-ratio').textContent = project.aspect_ratio;
        if (project.voice.startsWith('cvoice:')) {
            document.getElementById('preview-voice').textContent = 'cvoice.ai';
        } else {
            document.getElementById('preview-voice').textContent = project.voice.split('-')[2] || project.voice;
        }
        document.getElementById('preview-subtitles').textContent = project.subtitle_style;
        document.getElementById('preview-music').textContent = project.bg_music === 'none' ? 'None' : project.bg_music;
        document.getElementById('preview-source').textContent = project.visual_source === 'pexels' ? 'Pexels' : 'YouTube';
        
        document.getElementById('volume-voice').value = project.voice_volume;
        document.getElementById('volume-music').value = project.bg_music_volume;
        
        document.getElementById('scene-count-badge').textContent = `${currentScenes.length} Scenes`;
        
        // Adjust screens - Switch to the creation wizard view tab
        switchTab('new-project');
        
        // Hide all screens by default
        document.getElementById('setup-form-container').classList.add('hidden');
        document.getElementById('storyboard-container').classList.add('hidden');
        document.getElementById('rendering-container').classList.add('hidden');
        document.getElementById('output-container').classList.add('hidden');
        
        // Route to the correct screen based on project status
        if (project.status === 'Completed') {
            showFinalVideo(projectId);
        } else if (project.status === 'Rendering' || project.status === 'Generating Script') {
            document.getElementById('rendering-container').classList.remove('hidden');
            startRenderPolling(projectId);
        } else {
            // Draft, Script Generated, Failed
            document.getElementById('storyboard-container').classList.remove('hidden');
            renderSceneCards();
        }
        
    } catch (e) {
        showToast(e.message || 'Failed to open project', 'error');
        switchTab('dashboard');
    }
}

function renderSceneCards() {
    const list = document.getElementById('scenes-list');
    list.innerHTML = '';
    
    currentScenes.forEach((scene, index) => {
        const card = document.createElement('div');
        card.className = 'card glass-card scene-card';
        
        // Thumbnail image placeholder/loaded state
        const thumbnailSrc = scene.video_url ? 
            (scene.video_source === 'pexels' ? `https://images.pexels.com/videos/${scene.video_url.split('/videos/')[1]?.split('/')[0]}/pictures/medium-1.jpg` : '/static/img/video_placeholder.jpg') 
            : 'https://images.pexels.com/videos/3196614/pictures/medium-1.jpg'; // generic default placeholder
            
        card.innerHTML = `
            <div class="scene-sequence">${scene.sequence}</div>
            <div class="scene-text-inputs">
                <div class="form-group" style="margin-bottom: 0;">
                    <label>Speech Narration</label>
                    <textarea class="scene-text-input" data-index="${index}" rows="2">${scene.text}</textarea>
                </div>
                <div class="visual-query-row">
                    <label>Visual Search Keyword:</label>
                    <input type="text" class="scene-query-input" data-index="${index}" value="${scene.visual_query}">
                </div>
            </div>
            <div class="scene-visual-preview">
                <img src="${thumbnailSrc}" onerror="this.src='https://images.pexels.com/videos/3209663/pictures/medium-1.jpg'" class="scene-thumbnail">
                <div class="scene-visual-overlay">
                    <button class="btn btn-primary btn-media-replace" onclick="openMediaModal(${index})">Replace Visual</button>
                </div>
            </div>
        `;
        list.appendChild(card);
    });
}

function exitToSetup() {
    resetSetupForm();
}

async function deleteProject(projectId) {
    if (!confirm('Are you sure you want to delete this project? This will delete all temporary visual and video outputs.')) return;
    
    try {
        const response = await fetch(`/api/projects/${projectId}`, { method: 'DELETE' });
        const result = await response.json();
        if (result.status === 'success') {
            showToast('Project deleted successfully.');
            loadProjects();
        } else {
            showToast('Failed to delete project', 'error');
        }
    } catch (e) {
        showToast('Error deleting project', 'error');
    }
}

// Media Modal Operations
function openMediaModal(sceneIndex) {
    selectedSceneIndexForMediaReplace = sceneIndex;
    const scene = currentScenes[sceneIndex];
    
    document.getElementById('modal-media-search-input').value = scene.visual_query;
    document.getElementById('media-modal').classList.remove('hidden');
    
    // Trigger initial search automatically
    handleModalMediaSearch();
}

function closeMediaModal() {
    document.getElementById('media-modal').classList.add('hidden');
    selectedSceneIndexForMediaReplace = null;
}

async function handleModalMediaSearch() {
    const query = document.getElementById('modal-media-search-input').value.trim();
    if (!query) {
        showToast('Please type a search query first.', 'error');
        return;
    }
    
    const resultsGrid = document.getElementById('modal-media-results');
    resultsGrid.innerHTML = '<div class="text-center pad-2">Searching Pexels Library...</div>';
    
    try {
        const response = await fetch(`/api/projects/${currentProjectId}/search-media?query=${encodeURIComponent(query)}`);
        const videos = await response.json();
        
        resultsGrid.innerHTML = '';
        if (videos.length === 0) {
            resultsGrid.innerHTML = '<div class="text-center pad-2">No matching stock videos found. Try different keywords.</div>';
            return;
        }
        
        videos.forEach(v => {
            const item = document.createElement('div');
            item.className = 'media-item';
            
            // Hover logic to play preview or show static
            item.innerHTML = `
                <img src="${v.image}" title="Select video">
            `;
            
            item.addEventListener('click', () => {
                // Swap media in local memory
                currentScenes[selectedSceneIndexForMediaReplace].video_url = v.url;
                currentScenes[selectedSceneIndexForMediaReplace].video_source = 'pexels';
                currentScenes[selectedSceneIndexForMediaReplace].visual_query = query;
                
                // Refresh storyboard cards
                renderSceneCards();
                closeMediaModal();
                showToast('Video clip updated for scene.');
            });
            
            resultsGrid.appendChild(item);
        });
        
    } catch (e) {
        resultsGrid.innerHTML = '<div class="text-center pad-2 log-error">Error connecting to Pexels API. Ensure API key is configured.</div>';
    }
}

// Start rendering pipeline
async function handleRenderVideo() {
    showToast('Starting rendering pipeline...');
    
    // 1. Gather all scene inputs from textareas
    const sceneCards = document.querySelectorAll('.scene-card');
    sceneCards.forEach((card, index) => {
        const text = card.querySelector('.scene-text-input').value.trim();
        const visual_query = card.querySelector('.scene-query-input').value.trim();
        
        currentScenes[index].text = text;
        currentScenes[index].visual_query = visual_query;
    });
    
    // Gather volume sliders
    const voice_volume = parseFloat(document.getElementById('volume-voice').value);
    const bg_music_volume = parseFloat(document.getElementById('volume-music').value);
    
    try {
        // Save current timeline state to backend
        const updateRes = await fetch(`/api/projects/${currentProjectId}/update-scenes`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ scenes: currentScenes })
        });
        
        if (!updateRes.ok) throw new Error('Failed to update scene details');
        
        const settingsRes = await fetch(`/api/projects/${currentProjectId}/update-settings`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ voice_volume, bg_music_volume })
        });
        
        // Trigger Render Engine
        const renderRes = await fetch(`/api/projects/${currentProjectId}/render`, { method: 'POST' });
        const renderResult = await renderRes.json();
        
        if (renderResult.status === 'success') {
            // Shift UI to Rendering view
            document.getElementById('storyboard-container').classList.add('hidden');
            document.getElementById('rendering-container').classList.remove('hidden');
            
            // Start Polling Render Progress
            startRenderPolling(currentProjectId);
        } else {
            showToast('Failed to start rendering', 'error');
        }
    } catch (e) {
        showToast(e.message || 'Error during rendering initiation', 'error');
    }
}

// Poll Render Progress
function startRenderPolling(projectId) {
    if (renderPollInterval) clearInterval(renderPollInterval);
    
    const consoleLogs = document.getElementById('render-console-logs');
    consoleLogs.innerHTML = '<p class="log-info">Connecting to render logger...</p>';
    
    let previousMsg = "";
    
    renderPollInterval = setInterval(async () => {
        try {
            const res = await fetch(`/api/projects/${projectId}/status`);
            const data = await res.json();
            
            // Update status UI
            document.getElementById('render-status-msg').textContent = data.progress_message;
            
            // Map status to progress bar percentages
            let percent = 10;
            if (data.progress_message.includes('Voiceover')) percent = 25;
            else if (data.progress_message.includes('video')) percent = 50;
            else if (data.progress_message.includes('subtitles')) percent = 70;
            else if (data.progress_message.includes('Stitching')) percent = 85;
            else if (data.progress_message.includes('Burning')) percent = 95;
            else if (data.status === 'Completed') percent = 100;
            
            document.getElementById('render-progress-fill').style.width = `${percent}%`;
            
            // Add console log lines if message changes
            if (data.progress_message !== previousMsg && data.progress_message) {
                const logLine = document.createElement('p');
                logLine.className = 'log-info';
                
                if (data.status === 'Failed') {
                    logLine.className = 'log-error';
                    logLine.textContent = `[ERROR] ${data.progress_message}`;
                } else if (data.status === 'Completed') {
                    logLine.className = 'log-success';
                    logLine.textContent = `[SUCCESS] Video compilation finished!`;
                } else {
                    logLine.textContent = `[RENDER] ${data.progress_message}`;
                }
                
                consoleLogs.appendChild(logLine);
                consoleLogs.scrollTop = consoleLogs.scrollHeight;
                previousMsg = data.progress_message;
            }
            
            // Check terminal conditions
            if (data.status === 'Completed') {
                clearInterval(renderPollInterval);
                showToast('Video compiled successfully!');
                
                // Show final view
                setTimeout(() => {
                    showFinalVideo(projectId);
                }, 1000);
            } else if (data.status === 'Failed') {
                clearInterval(renderPollInterval);
                document.getElementById('render-status-heading').textContent = "Rendering Failed";
                showToast(data.error_message || 'Video compilation failed', 'error');
            }
            
        } catch (e) {
            console.error('Error polling render status', e);
        }
    }, 2000);
}

function showFinalVideo(projectId) {
    document.getElementById('rendering-container').classList.add('hidden');
    document.getElementById('output-container').classList.remove('hidden');
    
    // Set video src
    const videoPlayer = document.getElementById('final-video-player');
    videoPlayer.src = `/video/${projectId}`;
    videoPlayer.load();
    
    // Set aspect ratio wrappers
    const wrapper = document.getElementById('video-player-wrapper');
    const project = currentScenes[0]; // Fetch ratio details
    // Check global layout style
    const ratioText = document.getElementById('preview-ratio').textContent;
    if (ratioText === '16:9') {
        wrapper.className = 'video-wrapper aspect-horizontal';
    } else {
        wrapper.className = 'video-wrapper aspect-vertical';
    }
    
    // Set download button
    const downloadBtn = document.getElementById('btn-download-video');
    downloadBtn.href = `/video/${projectId}`;
}

function updateProgressUI(width, title, message) {
    document.getElementById('render-progress-fill').style.width = `${width}%`;
    document.getElementById('render-status-heading').textContent = title;
    document.getElementById('render-status-msg').textContent = message;
}

// Convert native <select> elements into themed custom dropdowns
function initializeCustomSelects() {
    const selects = document.querySelectorAll('select:not(.custom-select-hidden)');
    
    selects.forEach(select => {
        select.classList.add('custom-select-hidden');
        select.style.display = 'none'; // hide native select
        
        // Create custom outer wrapper
        const wrapper = document.createElement('div');
        wrapper.className = 'custom-select-wrapper';
        
        // Create trigger button
        const trigger = document.createElement('div');
        trigger.className = 'custom-select-trigger';
        
        const selectedText = select.options[select.selectedIndex]?.text || '';
        const triggerText = document.createElement('span');
        triggerText.textContent = selectedText;
        triggerText.className = 'custom-select-text';
        
        const caret = document.createElement('div');
        caret.className = 'custom-select-caret';
        
        trigger.appendChild(triggerText);
        trigger.appendChild(caret);
        wrapper.appendChild(trigger);
        
        // Create custom list dropdown
        const optionsContainer = document.createElement('div');
        optionsContainer.className = 'custom-select-options';
        
        // Build list items from options
        const rebuildOptions = () => {
            optionsContainer.innerHTML = '';
            Array.from(select.options).forEach((opt, idx) => {
                const optionDiv = document.createElement('div');
                optionDiv.className = 'custom-select-option';
                optionDiv.textContent = opt.text;
                optionDiv.setAttribute('data-value', opt.value);
                
                if (idx === select.selectedIndex) {
                    optionDiv.classList.add('selected');
                }
                
                optionDiv.addEventListener('click', (e) => {
                    e.stopPropagation();
                    select.selectedIndex = idx;
                    select.dispatchEvent(new Event('change', { bubbles: true }));
                    
                    triggerText.textContent = opt.text;
                    optionsContainer.querySelectorAll('.custom-select-option').forEach(el => {
                        el.classList.remove('selected');
                    });
                    optionDiv.classList.add('selected');
                    wrapper.classList.remove('open');
                });
                
                optionsContainer.appendChild(optionDiv);
            });
        };
        
        rebuildOptions();
        wrapper.appendChild(optionsContainer);
        
        // Insert custom wrapper right after the native select
        select.parentNode.insertBefore(wrapper, select.nextSibling);
        
        // Toggle open state on trigger click
        trigger.addEventListener('click', (e) => {
            e.stopPropagation();
            document.querySelectorAll('.custom-select-wrapper').forEach(w => {
                if (w !== wrapper) w.classList.remove('open');
            });
            wrapper.classList.toggle('open');
        });
        
        // Sync custom UI when the native select element updates (internally or externally)
        select.addEventListener('change', () => {
            const text = select.options[select.selectedIndex]?.text || '';
            triggerText.textContent = text;
            optionsContainer.querySelectorAll('.custom-select-option').forEach((el, idx) => {
                if (idx === select.selectedIndex) {
                    el.classList.add('selected');
                } else {
                    el.classList.remove('selected');
                }
            });
        });
        
        // Optional MutationObserver to watch for changes to <option> children (e.g. dynamically added options)
        const observer = new MutationObserver(() => {
            rebuildOptions();
            const text = select.options[select.selectedIndex]?.text || '';
            triggerText.textContent = text;
        });
        observer.observe(select, { childList: true });
    });
    
    // Close dropdowns when clicking anywhere outside
    document.addEventListener('click', () => {
        document.querySelectorAll('.custom-select-wrapper').forEach(w => {
            w.classList.remove('open');
        });
    });
}

// Dynamic voice options catalog
const voiceData = {
    en: [
        { value: "en-US-AndrewNeural", text: "English Male (US) - Andrew" },
        { value: "en-US-EmmaNeural", text: "English Female (US) - Emma" },
        { value: "en-US-BrianNeural", text: "English Male (US) - Brian" },
        { value: "en-US-JennyNeural", text: "English Female (US) - Jenny" },
        { value: "en-GB-SoniaNeural", text: "English Female (UK) - Sonia" },
        { value: "en-GB-RyanNeural", text: "English Male (UK) - Ryan" },
        { value: "en-IN-NeerjaNeural", text: "English Female (India) - Neerja" },
        { value: "en-IN-PrabhatNeural", text: "English Male (India) - Prabhat" },
        { value: "en-AU-NatashaNeural", text: "English Female (Australia) - Natasha" },
        { value: "en-CA-LiamNeural", text: "English Male (Canada) - Liam" },
        { value: "cvoice_custom", text: "Custom cvoice.ai Voice (Free)" }
    ],
    hi: [
        { value: "hi-IN-SwaraNeural", text: "Hindi Female (India) - Swara" },
        { value: "hi-IN-MadhurNeural", text: "Hindi Male (India) - Madhur" },
        { value: "cvoice_custom", text: "Custom cvoice.ai Voice (Free)" }
    ]
};

function updateVoiceOptions() {
    const langSelect = document.getElementById('language-select');
    const voiceSelect = document.getElementById('voice-select');
    if (!langSelect || !voiceSelect) return;
    
    const lang = langSelect.value;
    const voices = voiceData[lang] || [];
    
    voiceSelect.innerHTML = '';
    voices.forEach(voice => {
        const opt = document.createElement('option');
        opt.value = voice.value;
        opt.textContent = voice.text;
        voiceSelect.appendChild(opt);
    });
    
    voiceSelect.selectedIndex = 0;
    voiceSelect.dispatchEvent(new Event('change'));
}

function toggleCustomVoiceWrapper() {
    const select = document.getElementById('voice-select');
    const wrapper = document.getElementById('cvoice-custom-voice-wrapper');
    if (!select || !wrapper) return;
    
    if (select.value === 'cvoice_custom') {
        wrapper.classList.remove('hidden');
    } else {
        wrapper.classList.add('hidden');
    }
}

async function handleClearTempClips(projectId) {
    if (!projectId) return;
    const confirmClear = confirm("Are you sure you want to delete all downloaded raw videos and voiceover clips for this project? This will save storage space. The final output video will NOT be deleted.");
    if (!confirmClear) return;
    
    try {
        const response = await fetch(`/api/projects/${projectId}/clear-clips`, { method: 'POST' });
        const result = await response.json();
        if (result.status === 'success') {
            showToast(result.message);
            openProject(projectId);
        } else {
            showToast(result.error || 'Failed to clear clips', 'error');
        }
    } catch (e) {
        showToast('Error connecting to server', 'error');
    }
}

