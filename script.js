const API_URL = "http://localhost:8000";
// Open Mode: No key needed by default. If you set a key, add ?key=YOUR_KEY here manually or in a settings UI.
const API_KEY_PARAM = "";

let isPlaying = false;
let currentTrackId = null;

// UI Elements
const els = {
    player: document.getElementById("player-view"),
    loading: document.getElementById("loading-state"),
    art: document.getElementById("track-art"),
    title: document.getElementById("track-name"),
    artist: document.getElementById("artist-name"),
    progressFill: document.getElementById("progress-fill"),
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
    if (data.is_liked) {
        els.likeBtn.classList.add("active");
        els.likeBtn.style.fill = "#1ed760"; // Green fill
    } else {
        els.likeBtn.classList.remove("active");
        els.likeBtn.style.fill = "none";
    }

    // Shuffle
    if (data.shuffle_state) els.shuffleBtn.classList.add("active");
    else els.shuffleBtn.classList.remove("active");
}

async function fetchQueue() {
    try {
        const res = await fetch(`${API_URL}/queue${API_KEY_PARAM ? '?key=' + API_KEY_PARAM : ''}`);
        const data = await res.json();
        if (data.success && data.up_next) {
            renderQueue(data.up_next);
        }
    } catch (e) { console.error(e); }
}

function renderQueue(items) {
    els.queueList.innerHTML = items.map(item => `
        <div class="queue-item" onclick="playQueue(${item.index - 1})">
            <span class="q-num" style="color:var(--text-sec); font-size:12px; width:20px;">${item.index}</span>
            <div class="q-info">
                <div class="q-title">${item.track}</div>
                <div class="q-artist">${item.artist}</div>
            </div>
        </div>
    `).join("");
}

// Controls
async function control(action) {
    await fetch(`${API_URL}/${action}${API_KEY_PARAM ? '?key=' + API_KEY_PARAM : ''}`);
    setTimeout(fetchState, 200); // Quick refresh
}

function togglePlay() {
    control(isPlaying ? "pause" : "play");
}

function toggleShuffle() {
    const isShuffle = els.shuffleBtn.classList.contains("active");
    // API expects /shuffle/true or /shuffle/false
    fetch(`${API_URL}/shuffle/${!isShuffle}${API_KEY_PARAM ? '?key=' + API_KEY_PARAM : ''}`);
    setTimeout(fetchState, 200);
}

function toggleLike() {
    const isLiked = els.likeBtn.classList.contains("active");
    control(isLiked ? "dislike" : "like");
}

async function playQueue(index) {
    // Note: The API queue endpoint uses a specific index logic, need to ensure backend supports this 
    // The previous backend code had /queue/{index}.
    await fetch(`${API_URL}/queue/${index}${API_KEY_PARAM ? '?key=' + API_KEY_PARAM : ''}`);
    setTimeout(fetchState, 500);
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

// Init
setInterval(fetchState, 1000);
fetchState();
