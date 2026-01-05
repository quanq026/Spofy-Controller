const API_URL = "";
const API_KEY_PARAM = "";

let isPlaying = false;
let currentTrackId = null;
let isActionInProgress = false;
let isDeviceOffline = false;
let consecutiveFailures = 0;

// DOM Elements Reference
const els = {
    player: document.getElementById("player-view"),
    loading: document.getElementById("loading-state"),
    offline: document.getElementById("offline-state"),
    art: document.getElementById("track-art"),
    title: document.getElementById("track-name"),
    artist: document.getElementById("artist-name"),
    progressFill: document.getElementById("progress-fill"),
    progressBar: null,
    currTime: document.getElementById("current-time"),
    totTime: document.getElementById("total-time"),
    playIcon: document.getElementById("icon-play"),
    pauseIcon: document.getElementById("icon-pause"),
    likeBtn: document.getElementById("btn-like"),
    shuffleBtn: document.getElementById("btn-shuffle"),
    queueList: document.getElementById("queue-list")
};

async function fetchState() {
    try {
        const res = await fetch(`${API_URL}/current${API_KEY_PARAM ? '?key=' + API_KEY_PARAM : ''}`);

        if (!res.ok) {
            handleFetchError(res.status);
            return;
        }

        const data = await res.json();

        if (!data.is_playing && data.message === "No active playback") {
            showOfflineState();
            return;
        }

        // Validate required data fields - if missing, show offline
        if (!data.track || !data.track_id || !data.progress) {
            showOfflineState();
            isDeviceOffline = true;
            return;
        }

        // Success - reset failure counter and show player
        consecutiveFailures = 0;
        isDeviceOffline = false;
        updateUI(data);
        el_showPlayer();

        if (Math.random() < 0.2) fetchQueue();

    } catch (e) {
        console.error("Poll error", e);
        handleFetchError(null);
    }
}

function handleFetchError(status) {
    consecutiveFailures++;

    if (status === 401) {
        showToast('Authentication failed', 'error');
        showOfflineState();
        isDeviceOffline = true;
    } else if (status === 404 || status === 403) {
        // Device offline or not available - show immediately
        showOfflineState();
        isDeviceOffline = true;
    } else if (status >= 500 || status === null) {
        showToast('Connection error, retrying...', 'error');
    }
}

// Initialize State based on HTML attributes
const appContainer = document.querySelector('.app-container');

// Force initial state if missing (handles stale HTML + New JS case)
if (appContainer && !appContainer.hasAttribute('data-state')) {
    console.log("Forcing initial loading state");
    appContainer.setAttribute('data-state', 'loading');
}

function setAppState(state) {
    if (!appContainer) return;
    appContainer.setAttribute('data-state', state);

    // Manage controls based on state
    if (state === 'player') {
        enableAllControls();
    } else {
        disableAllControls();
    }
}

function showOfflineState() {
    setAppState('offline');
}

function el_showPlayer() {
    setAppState('player');
}

function disableAllControls() {
    document.querySelectorAll('button.btn-icon, button.btn-play').forEach(btn => {
        btn.disabled = true;
        btn.style.opacity = '0.5';
        btn.style.cursor = 'not-allowed';
    });
}

function enableAllControls() {
    document.querySelectorAll('button.btn-icon, button.btn-play').forEach(btn => {
        btn.disabled = false;
        btn.style.opacity = '1';
        btn.style.cursor = 'pointer';
    });
}

function updateUI(data) {
    if (!data) return;

    // Track Info
    if (currentTrackId !== data.track_id) {
        currentTrackId = data.track_id;
        els.title.innerText = data.track;
        els.artist.innerText = data.artist;
        els.art.src = data.thumbnail;
        els.art.alt = `Album art for ${data.track} by ${data.artist}`;
        fetchQueue(); // Update queue when song changes
    }

    // Playback Status
    isPlaying = data.is_playing;
    togglePlayIcon(isPlaying);

    // Playback Status (Progress, Time, Duration)
    if (data.progress_percent !== undefined) {
        els.progressFill.style.width = data.progress_percent + "%";
    }
    if (data.progress) {
        const [curr, tot] = data.progress.split(" / ");
        els.currTime.innerText = curr;
        els.totTime.innerText = tot;
    }

    // Like Status
    const heartIcon = els.likeBtn.querySelector('svg');
    if (data.is_liked) {
        els.likeBtn.classList.add("active");
        if (heartIcon) heartIcon.style.fill = "#1ed760";
    } else {
        els.likeBtn.classList.remove("active");
        if (heartIcon) heartIcon.style.fill = "none";
    }

    // Shuffle
    if (data.shuffle_state) els.shuffleBtn.classList.add("active");
    else els.shuffleBtn.classList.remove("active");
}

async function fetchQueue() {
    try {
        const res = await fetch(`${API_URL}/queue${API_KEY_PARAM ? '?key=' + API_KEY_PARAM : ''}`);
        if (!res.ok) return;

        const data = await res.json();
        if (data.success && data.up_next) {
            renderQueue(data.up_next);
        } else if (data.up_next && data.up_next.length === 0) {
            els.queueList.innerHTML = '<div style="color:var(--text-sec); text-align:center; padding:20px;">Queue is empty</div>';
        }
    } catch (e) {
        console.error('Queue fetch error:', e);
    }
}

function renderQueue(items) {
    els.queueList.innerHTML = '';
    items.forEach(item => {
        const queueItem = document.createElement('div');
        queueItem.className = 'queue-item';
        queueItem.setAttribute('role', 'button');
        queueItem.setAttribute('tabindex', '0');
        queueItem.setAttribute('aria-label', `Play ${item.track} by ${item.artist}`);
        queueItem.onclick = () => playQueue(item.index);
        queueItem.onkeydown = (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                playQueue(item.index);
            }
        };

        const qThumb = document.createElement('div');
        qThumb.className = 'q-thumb';
        const qImg = document.createElement('img');
        qImg.src = item.thumbnail || 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40"><rect fill="%23333" width="40" height="40"/><text x="50%" y="50%" fill="%23666" font-size="12" text-anchor="middle" dy=".3em">♪</text></svg>';
        qImg.alt = `${item.track} thumbnail`;
        qThumb.appendChild(qImg);

        const qNum = document.createElement('span');
        qNum.className = 'q-num';
        qNum.textContent = item.index;

        const qInfo = document.createElement('div');
        qInfo.className = 'q-info';

        const qTitle = document.createElement('div');
        qTitle.className = 'q-title';
        qTitle.textContent = item.track;
        qTitle.title = item.track;

        const qArtist = document.createElement('div');
        qArtist.className = 'q-artist';
        qArtist.textContent = item.artist;
        qArtist.title = item.artist;

        qInfo.appendChild(qTitle);
        qInfo.appendChild(qArtist);
        queueItem.appendChild(qThumb);
        queueItem.appendChild(qInfo);
        els.queueList.appendChild(queueItem);
    });
}

async function control(action) {
    if (isActionInProgress || isDeviceOffline) {
        if (isDeviceOffline) {
            showToast('Device is offline', 'error');
        }
        return;
    }
    isActionInProgress = true;

    try {
        const res = await fetch(`${API_URL}/${action}${API_KEY_PARAM ? '?key=' + API_KEY_PARAM : ''}`);
        if (!res.ok) {
            if (res.status === 404 || res.status === 403) {
                showOfflineState();
                isDeviceOffline = true;
                showToast('Device is offline', 'error');
            } else {
                showToast(`Failed to ${action}`, 'error');
            }
            return;
        }
        consecutiveFailures = 0;
        setTimeout(fetchState, 200);
    } catch (e) {
        console.error(`Control error (${action}):`, e);
        showToast('Network error', 'error');
    } finally {
        setTimeout(() => { isActionInProgress = false; }, 500);
    }
}

function togglePlay() {
    control(isPlaying ? "pause" : "play");
}

async function toggleShuffle() {
    try {
        const isShuffle = els.shuffleBtn.classList.contains("active");
        const res = await fetch(`${API_URL}/shuffle/${!isShuffle}${API_KEY_PARAM ? '?key=' + API_KEY_PARAM : ''}`);
        if (!res.ok) {
            showToast('Failed to toggle shuffle', 'error');
            return;
        }
        setTimeout(fetchState, 200);
    } catch (e) {
        console.error('Shuffle error:', e);
        showToast('Network error', 'error');
    }
}

function toggleLike() {
    const isLiked = els.likeBtn.classList.contains("active");
    control(isLiked ? "dislike" : "like");
}

async function playQueue(index) {
    if (isDeviceOffline) {
        showToast('Device is offline', 'error');
        return;
    }
    try {
        const res = await fetch(`${API_URL}/queue/${index}${API_KEY_PARAM ? '?key=' + API_KEY_PARAM : ''}`);
        if (!res.ok) {
            if (res.status === 404 || res.status === 403) {
                showOfflineState();
                isDeviceOffline = true;
                showToast('Device is offline', 'error');
            } else {
                showToast('Failed to play track', 'error');
            }
            return;
        }
        consecutiveFailures = 0;
        setTimeout(fetchState, 500);
    } catch (e) {
        console.error('Queue play error:', e);
        showToast('Network error', 'error');
    }
}

function togglePlayIcon(playing) {
    if (playing) {
        els.playIcon.classList.add("hidden");
        els.pauseIcon.classList.remove("hidden");
    } else {
        els.playIcon.classList.remove("hidden");
        els.pauseIcon.classList.add("hidden");
    }
}



function showToast(message, type = 'info') {
    const existingToast = document.querySelector('.toast');
    if (existingToast) existingToast.remove();

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => toast.classList.add('show'), 10);
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

document.addEventListener('DOMContentLoaded', () => {
    // Set up progress bar click handler for seeking
    const progressBar = document.querySelector('.progress-bar');
    els.progressBar = progressBar;

    if (progressBar) {
        progressBar.style.cursor = 'pointer';
        progressBar.addEventListener('click', async (e) => {
            if (isDeviceOffline) {
                showToast('Device is offline', 'error');
                return;
            }
            const rect = progressBar.getBoundingClientRect();
            const percent = ((e.clientX - rect.left) / rect.width) * 100;

            try {
                const res = await fetch(`${API_URL}/seek/${Math.round(percent)}${API_KEY_PARAM ? '?key=' + API_KEY_PARAM : ''}`);
                if (!res.ok) {
                    if (res.status === 404 || res.status === 403) {
                        showOfflineState();
                        isDeviceOffline = true;
                        showToast('Device is offline', 'error');
                    } else {
                        showToast('Seek failed', 'error');
                    }
                } else {
                    consecutiveFailures = 0;
                    setTimeout(fetchState, 100);
                }
            } catch (e) {
                console.error('Seek error:', e);
                showToast('Network error', 'error');
            }
        });
    }

    // ======================
    // SETTINGS MODAL LOGIC
    // ======================
    const modal = document.getElementById('settings-modal');
    const btnSettings = document.getElementById('btn-settings');
    const btnCloseSettings = document.getElementById('btn-close-settings');
    const btnSaveSettings = document.getElementById('btn-save-settings');

    // Inputs
    const inputs = {
        clientId: document.getElementById('env-client-id'),
        clientSecret: document.getElementById('env-client-secret'),
        gistId: document.getElementById('env-gist-id'),
        githubToken: document.getElementById('env-github-token'),
        gistFilename: document.getElementById('env-gist-filename')
    };

    // Load from LocalStorage
    function loadSettings() {
        inputs.clientId.value = localStorage.getItem('env_CLIENT_ID') || '';
        inputs.clientSecret.value = localStorage.getItem('env_CLIENT_SECRET') || '';
        inputs.gistId.value = localStorage.getItem('env_GITHUB_GIST_ID') || '';
        inputs.githubToken.value = localStorage.getItem('env_GITHUB_TOKEN') || '';
        inputs.gistFilename.value = localStorage.getItem('env_GIST_FILENAME') || '';
    }

    // Save to LocalStorage & Cookies
    // Save to LocalStorage & Cookies
    function syncSettingsToCookies() {
        const setCookie = (name, val) => {
            document.cookie = `${name}=${encodeURIComponent(val)}; max-age=31536000; path=/`;
        };

        localStorage.setItem('env_CLIENT_ID', inputs.clientId.value);
        setCookie('CLIENT_ID', inputs.clientId.value);

        localStorage.setItem('env_CLIENT_SECRET', inputs.clientSecret.value);
        setCookie('CLIENT_SECRET', inputs.clientSecret.value);

        localStorage.setItem('env_GITHUB_GIST_ID', inputs.gistId.value);
        setCookie('GITHUB_GIST_ID', inputs.gistId.value);

        localStorage.setItem('env_GITHUB_TOKEN', inputs.githubToken.value);
        setCookie('GITHUB_TOKEN', inputs.githubToken.value);

        localStorage.setItem('env_GIST_FILENAME', inputs.gistFilename.value);
        setCookie('GIST_FILENAME', inputs.gistFilename.value);
    }

    function saveSettingsAndReload() {
        syncSettingsToCookies();
        showToast('Settings saved! Reloading...', 'success');
        setTimeout(() => window.location.reload(), 1000);
    }

    if (btnSettings) {
        btnSettings.addEventListener('click', () => {
            loadSettings();
            modal.classList.remove('hidden');
        });
    }

    if (btnCloseSettings) {
        btnCloseSettings.addEventListener('click', () => {
            modal.classList.add('hidden');
        });
    }

    if (btnSaveSettings) {
        btnSaveSettings.addEventListener('click', saveSettingsAndReload);
    }

    // Close on click outside
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.classList.add('hidden');
        }
    });

    // Initial Load of Cookies on Page Load (sync JS to Cookies just in case)
    loadSettings();
    syncSettingsToCookies(); // Ensure cookies are set if they exist in localStorage but not cookies
});

setInterval(fetchState, 1000);
fetchState();