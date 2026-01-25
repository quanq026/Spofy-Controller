const API_URL = "";
const API_KEY = "";

function getHeaders() {
    const headers = {};
    if (API_KEY) headers['X-API-Key'] = API_KEY;
    return headers;
}

let isPlaying = false;
let currentTrackId = null;
let isActionInProgress = false;
let isDeviceOffline = false;
let consecutiveFailures = 0;

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
        const res = await fetch(`${API_URL}/current`, { headers: getHeaders() });

        if (!res.ok) {
            handleFetchError(res.status);
            return;
        }

        const data = await res.json();

        if (!data.is_playing && data.message === "No active playback") {
            showOfflineState();
            return;
        }

        if (!data.track || !data.track_id || !data.progress) {
            showOfflineState();
            isDeviceOffline = true;
            return;
        }

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
        showOfflineState();
        isDeviceOffline = true;
    } else if (status >= 500 || status === null) {
        showToast('Connection error, retrying...', 'error');
    }
}

const appContainer = document.querySelector('.app-container');

if (appContainer && !appContainer.hasAttribute('data-state')) {
    appContainer.setAttribute('data-state', 'loading');
}

function setAppState(state) {
    if (!appContainer) return;
    appContainer.setAttribute('data-state', state);
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

    if (currentTrackId !== data.track_id) {
        currentTrackId = data.track_id;
        els.title.innerText = data.track;
        els.artist.innerText = data.artist;
        els.art.src = data.thumbnail;
        els.art.alt = `Album art for ${data.track} by ${data.artist}`;
        fetchQueue();
    }

    isPlaying = data.is_playing;
    togglePlayIcon(isPlaying);

    if (data.progress_percent !== undefined) {
        els.progressFill.style.width = data.progress_percent + "%";
        // Update ARIA attributes for accessibility
        if (els.progressBar) {
            els.progressBar.setAttribute('aria-valuenow', Math.round(data.progress_percent));
        }
    }
    if (data.progress) {
        const [curr, tot] = data.progress.split(" / ");
        els.currTime.innerText = curr;
        els.totTime.innerText = tot;
        // Update ARIA valuetext for screen readers
        if (els.progressBar) {
            els.progressBar.setAttribute('aria-valuetext', `${curr} of ${tot}`);
        }
    }

    const heartIcon = els.likeBtn.querySelector('svg');
    if (data.is_liked) {
        els.likeBtn.classList.add("active");
        if (heartIcon) heartIcon.style.fill = "#1ed760";
    } else {
        els.likeBtn.classList.remove("active");
        if (heartIcon) heartIcon.style.fill = "none";
    }

    if (data.shuffle_state) els.shuffleBtn.classList.add("active");
    else els.shuffleBtn.classList.remove("active");
}

async function fetchQueue() {
    try {
        const res = await fetch(`${API_URL}/queue`, { headers: getHeaders() });
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
        const res = await fetch(`${API_URL}/${action}`, { headers: getHeaders() });
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
        const res = await fetch(`${API_URL}/shuffle/${!isShuffle}`, { headers: getHeaders() });
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
        const res = await fetch(`${API_URL}/queue/${index}`, { headers: getHeaders() });
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
    const progressBar = document.querySelector('.progress-bar');
    els.progressBar = progressBar;

    if (progressBar) {
        let isSeeking = false;
        let seekDebounceTimer = null;
        let lastSeekPercent = 0;

        // Debounced seek function to prevent API spam
        const debouncedSeek = (percent) => {
            if (seekDebounceTimer) {
                clearTimeout(seekDebounceTimer);
            }
            lastSeekPercent = percent;
            seekDebounceTimer = setTimeout(async () => {
                await performSeek(Math.round(lastSeekPercent));
            }, 150);
        };

        // Actual seek API call
        async function performSeek(percent) {
            if (isDeviceOffline) {
                showToast('Device is offline', 'error');
                return;
            }
            try {
                const res = await fetch(`${API_URL}/seek/${percent}`, { headers: getHeaders() });
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
        }

        // Calculate seek percent from event
        function getSeekPercent(e, rect) {
            const clientX = e.touches ? e.touches[0].clientX : e.clientX;
            const percent = Math.max(0, Math.min(100, ((clientX - rect.left) / rect.width) * 100));
            return percent;
        }

        // Update progress fill visually during seeking
        function updateProgressVisual(percent) {
            if (els.progressFill) {
                els.progressFill.style.width = percent + '%';
            }
            // Update ARIA value
            progressBar.setAttribute('aria-valuenow', Math.round(percent));
        }

        // Mouse/Touch start
        function handleSeekStart(e) {
            if (isDeviceOffline) {
                showToast('Device is offline', 'error');
                return;
            }
            isSeeking = true;
            progressBar.classList.add('seeking');
            const rect = progressBar.getBoundingClientRect();
            const percent = getSeekPercent(e, rect);
            updateProgressVisual(percent);
            lastSeekPercent = percent;

            if (e.type === 'mousedown') {
                e.preventDefault();
            }
        }

        // Mouse/Touch move
        function handleSeekMove(e) {
            if (!isSeeking) return;
            e.preventDefault();
            const rect = progressBar.getBoundingClientRect();
            const percent = getSeekPercent(e, rect);
            updateProgressVisual(percent);
            lastSeekPercent = percent;
        }

        // Mouse/Touch end
        function handleSeekEnd(e) {
            if (!isSeeking) return;
            isSeeking = false;
            progressBar.classList.remove('seeking');
            debouncedSeek(lastSeekPercent);
        }

        // Mouse events
        progressBar.addEventListener('mousedown', handleSeekStart);
        document.addEventListener('mousemove', handleSeekMove);
        document.addEventListener('mouseup', handleSeekEnd);

        // Touch events for mobile
        progressBar.addEventListener('touchstart', handleSeekStart, { passive: false });
        progressBar.addEventListener('touchmove', handleSeekMove, { passive: false });
        progressBar.addEventListener('touchend', handleSeekEnd);
        progressBar.addEventListener('touchcancel', handleSeekEnd);

        // Click fallback for simple taps
        progressBar.addEventListener('click', (e) => {
            if (isSeeking) return; // Ignore if already handled by drag
            const rect = progressBar.getBoundingClientRect();
            const percent = getSeekPercent(e, rect);
            updateProgressVisual(percent);
            debouncedSeek(percent);
        });

        // Keyboard accessibility for progress bar
        progressBar.addEventListener('keydown', (e) => {
            if (isDeviceOffline) return;

            const currentPercent = parseFloat(els.progressFill?.style.width) || 0;
            let newPercent = currentPercent;

            switch (e.key) {
                case 'ArrowRight':
                case 'ArrowUp':
                    newPercent = Math.min(100, currentPercent + 5);
                    break;
                case 'ArrowLeft':
                case 'ArrowDown':
                    newPercent = Math.max(0, currentPercent - 5);
                    break;
                case 'Home':
                    newPercent = 0;
                    break;
                case 'End':
                    newPercent = 100;
                    break;
                default:
                    return;
            }

            e.preventDefault();
            updateProgressVisual(newPercent);
            debouncedSeek(newPercent);
        });
    }
});

// Page Visibility API - pause polling when tab is hidden
let pollInterval = null;

function startPolling() {
    if (pollInterval) return;
    pollInterval = setInterval(fetchState, 1000);
    fetchState();
}

function stopPolling() {
    if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
    }
}

// Handle visibility change
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        stopPolling();
    } else {
        startPolling();
    }
});

// Start polling initially
startPolling();

// ======================= Sidebar Functions =======================
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebar-overlay');

    if (sidebar && overlay) {
        sidebar.classList.toggle('open');
        overlay.classList.toggle('open');

        // Load user info when opening
        if (sidebar.classList.contains('open')) {
            loadSidebarData();
        }
    }
}

async function loadSidebarData() {
    try {
        // Load user info
        const userRes = await fetch('/api/auth/me');
        if (userRes.ok) {
            const user = await userRes.json();
            const usernameEl = document.getElementById('sidebar-username');
            const avatarEl = document.getElementById('user-avatar');
            if (usernameEl) usernameEl.textContent = user.username;
            if (avatarEl) avatarEl.textContent = user.username.charAt(0).toUpperCase();
        }

        // Load config
        const configRes = await fetch('/api/config');
        if (configRes.ok) {
            const config = await configRes.json();
            document.getElementById('config-client-id').textContent = config.client_id || '-';
            document.getElementById('config-client-secret').textContent = config.client_secret || '-';
            document.getElementById('config-gist-id').textContent = config.gist_id || '-';
            document.getElementById('config-github-token').textContent = config.github_token || '-';
            document.getElementById('config-gist-filename').textContent = config.gist_filename || '-';
        }

        // Load API key
        const apiKeyRes = await fetch('/api/my-api-key');
        if (apiKeyRes.ok) {
            const data = await apiKeyRes.json();
            const apiKeyEl = document.getElementById('config-api-key');
            if (apiKeyEl) {
                apiKeyEl.textContent = data.api_key || 'Not generated';
                apiKeyEl.title = data.api_key || '';
            }
        }
    } catch (err) {
        console.error('Error loading sidebar data:', err);
    }
}

async function generateApiKey() {
    const btn = document.getElementById('btn-generate-api');
    const textEl = document.getElementById('btn-generate-text');

    if (!btn || btn.disabled) return;

    btn.disabled = true;
    textEl.textContent = 'Đang tạo...';

    try {
        const res = await fetch('/api/generate-api-key', { method: 'POST' });
        const data = await res.json();

        if (data.success) {
            const apiKeyEl = document.getElementById('config-api-key');
            if (apiKeyEl) {
                apiKeyEl.textContent = data.api_key;
                apiKeyEl.title = data.api_key;
            }
            textEl.textContent = 'Đã tạo!';
            setTimeout(() => {
                textEl.textContent = 'Tạo API Key mới';
            }, 2000);
        } else {
            textEl.textContent = 'Lỗi!';
        }
    } catch (err) {
        console.error('Error generating API key:', err);
        textEl.textContent = 'Lỗi!';
    } finally {
        btn.disabled = false;
        setTimeout(() => {
            textEl.textContent = 'Tạo API Key mới';
        }, 2000);
    }
}

async function copyApiKey() {
    const apiKeyEl = document.getElementById('config-api-key');
    const copyBtn = document.getElementById('btn-copy-api');

    if (!apiKeyEl || !apiKeyEl.title) return;

    try {
        await navigator.clipboard.writeText(apiKeyEl.title);
        copyBtn.classList.add('copied');
        setTimeout(() => {
            copyBtn.classList.remove('copied');
        }, 2000);
    } catch (err) {
        console.error('Copy failed:', err);
    }
}

function goToSetup() {
    window.location.href = '/setup';
}

async function logout() {
    try {
        await fetch('/api/auth/logout', { method: 'POST' });
        window.location.href = '/welcome';
    } catch (err) {
        console.error('Logout error:', err);
        window.location.href = '/welcome';
    }
}

// Close sidebar with Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const sidebar = document.getElementById('sidebar');
        if (sidebar && sidebar.classList.contains('open')) {
            toggleSidebar();
        }
    }
});