const API_URL = "/api";
// Open Mode: No key needed by default. If you set a key, add ?key=YOUR_KEY query param (requires updating this script) 
// or mostly, just use Headers. But for UI, we assume Open Mode or Same-Origin.
const API_KEY_PARAM = "";

let isPlaying = false;
let currentTrackId = null;
let isActionInProgress = false;

// UI Elements
const els = {
    player: document.getElementById("player-view"),
    loading: document.getElementById("loading-state"),
    art: document.getElementById("track-art"),
    title: document.getElementById("track-name"),
    artist: document.getElementById("artist-name"),
    progressFill: document.getElementById("progress-fill"),
    progressBar: null, // Will be set after DOM load
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
            if (res.status === 401) {
                showToast('Authentication failed', 'error');
            } else if (res.status >= 500) {
                showToast('Server error, retrying...', 'error');
            }
            return;
        }

        const data = await res.json();

        if (!data.is_playing && data.message === "No active playback") {
            // Show "Nothing Playing" state if needed, or just stay as is
            // For now we just keep polling
            return;
        }

        updateUI(data);
        el_showPlayer();

        // Also update queue occasionally (or every time? Queue is heavy? Let's do it 10%)
        if (Math.random() < 0.2) fetchQueue();

    } catch (e) {
        console.error("Poll error", e);
        showToast('Connection error', 'error');
    }
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

    // Progress
    els.progressFill.style.width = data.progress_percent + "%";
    const [curr, tot] = data.progress.split(" / ");
    els.currTime.innerText = curr;
    els.totTime.innerText = tot;

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

        const qNum = document.createElement('span');
        qNum.className = 'q-num';
        qNum.style.cssText = 'color:var(--text-sec); font-size:12px; width:20px;';
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
        queueItem.appendChild(qNum);
        queueItem.appendChild(qInfo);
        els.queueList.appendChild(queueItem);
    });
}

// Controls
async function control(action) {
    if (isActionInProgress) return;
    isActionInProgress = true;

    try {
        const res = await fetch(`${API_URL}/${action}${API_KEY_PARAM ? '?key=' + API_KEY_PARAM : ''}`);
        if (!res.ok) {
            showToast(`Failed to ${action}`, 'error');
            return;
        }
        setTimeout(fetchState, 200); // Quick refresh
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
    try {
        const res = await fetch(`${API_URL}/queue/${index}${API_KEY_PARAM ? '?key=' + API_KEY_PARAM : ''}`);
        if (!res.ok) {
            showToast('Failed to play track', 'error');
            return;
        }
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

function el_showPlayer() {
    els.loading.classList.add("hidden");
    els.player.classList.remove("hidden");
}

// Toast notification system
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

// Initialize after DOM is fully loaded
document.addEventListener('DOMContentLoaded', () => {
    // Set up progress bar click handler for seeking
    const progressBar = document.querySelector('.progress-bar');
    els.progressBar = progressBar;

    if (progressBar) {
        progressBar.style.cursor = 'pointer';
        progressBar.addEventListener('click', async (e) => {
            const rect = progressBar.getBoundingClientRect();
            const percent = ((e.clientX - rect.left) / rect.width) * 100;

            try {
                const res = await fetch(`${API_URL}/seek/${Math.round(percent)}${API_KEY_PARAM ? '?key=' + API_KEY_PARAM : ''}`);
                if (!res.ok) {
                    showToast('Seek failed', 'error');
                } else {
                    setTimeout(fetchState, 100);
                }
            } catch (e) {
                console.error('Seek error:', e);
                showToast('Network error', 'error');
            }
        });
    }
});

// Init
setInterval(fetchState, 1000);
fetchState();