const CONFIG = {
    API_URL: "",
    API_KEY: "",
    POLL_INTERVAL: 1000,
    SEEK_DEBOUNCE: 150,
    ACTION_COOLDOWN: 500,
    TOAST_DURATION: 3000,
    QUEUE_FETCH_CHANCE: 0.2
};

const state = {
    isPlaying: false,
    currentTrackId: null,
    isActionInProgress: false,
    isDeviceOffline: false,
    consecutiveFailures: 0,
    isSeeking: false,
    lastSeekPercent: 0,
    currentTimeMs: 0,
    totalTimeMs: 0,
    lastSyncTime: 0,
    progressPercent: 0,
};

const els = {
    appContainer: null,
    player: null,
    loading: null,
    offline: null,
    art: null,
    title: null,
    artist: null,
    progressFill: null,
    progressBar: null,
    currTime: null,
    totTime: null,
    playIcon: null,
    pauseIcon: null,
    likeBtn: null,
    shuffleBtn: null,
    queueList: null,
};

function initElements() {
    els.appContainer = document.querySelector('.app-container');
    els.player = document.getElementById("player-view");
    els.loading = document.getElementById("loading-state");
    els.offline = document.getElementById("offline-state");
    els.art = document.getElementById("track-art");
    els.title = document.getElementById("track-name");
    els.artist = document.getElementById("artist-name");
    els.progressFill = document.getElementById("progress-fill");
    els.progressBar = document.querySelector('.progress-bar');
    els.currTime = document.getElementById("current-time");
    els.totTime = document.getElementById("total-time");
    els.playIcon = document.getElementById("icon-play");
    els.pauseIcon = document.getElementById("icon-pause");
    els.likeBtn = document.getElementById("btn-like");
    els.shuffleBtn = document.getElementById("btn-shuffle");
    els.queueList = document.getElementById("queue-list");
}

function getHeaders() {
    const headers = {};
    if (CONFIG.API_KEY) headers['X-API-Key'] = CONFIG.API_KEY;
    return headers;
}

async function apiRequest(endpoint, options = {}) {
    const url = `${CONFIG.API_URL}/${endpoint}`;
    const response = await fetch(url, {
        ...options,
        headers: { ...getHeaders(), ...options.headers }
    });
    return response;
}

async function fetchState() {
    try {
        const res = await apiRequest('current');

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
            state.isDeviceOffline = true;
            return;
        }

        state.consecutiveFailures = 0;
        state.isDeviceOffline = false;
        updateUI(data);
        el_showPlayer();

        if (Math.random() < CONFIG.QUEUE_FETCH_CHANCE) fetchQueue();

    } catch (e) {
        console.error("Poll error", e);
        handleFetchError(null);
    }
}

function handleFetchError(status) {
    state.consecutiveFailures++;

    if (status === 401) {
        showToast('Authentication failed', 'error');
        showOfflineState();
        state.isDeviceOffline = true;
    } else if (status === 404 || status === 403) {
        showOfflineState();
        state.isDeviceOffline = true;
    } else if (status >= 500 || status === null) {
        showToast('Connection error, retrying...', 'error');
    }
}

function setAppState(appState) {
    if (!els.appContainer) return;
    els.appContainer.setAttribute('data-state', appState);
    if (appState === 'player') {
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

    if (state.currentTrackId !== data.track_id) {
        state.currentTrackId = data.track_id;
        els.title.innerText = data.track;
        els.artist.innerText = data.artist;
        els.art.src = data.thumbnail;
        els.art.alt = `Album art for ${data.track} by ${data.artist}`;
        fetchQueue();
    }

    state.isPlaying = data.is_playing;
    togglePlayIcon(state.isPlaying);

    if (data.progress) {
        const [currStr, totStr] = data.progress.split(" / ");
        const currMs = parseTimeToMs(currStr);
        const totMs = parseTimeToMs(totStr);

        state.currentTimeMs = currMs;
        state.totalTimeMs = totMs;
        state.lastSyncTime = performance.now();

        if (totMs > 0) {
            state.progressPercent = (currMs / totMs) * 100;
        }
    }

    const heartIcon = els.likeBtn?.querySelector('svg');
    if (data.is_liked) {
        els.likeBtn?.classList.add("active");
        if (heartIcon) heartIcon.style.fill = "var(--primary)";
    } else {
        els.likeBtn?.classList.remove("active");
        if (heartIcon) heartIcon.style.fill = "none";
    }

    if (data.shuffle_state) els.shuffleBtn?.classList.add("active");
    else els.shuffleBtn?.classList.remove("active");
}

function parseTimeToMs(timeStr) {
    if (!timeStr) return 0;
    const parts = timeStr.split(':').map(Number);
    if (parts.length === 2) {
        // M:SS format
        return (parts[0] * 60 + parts[1]) * 1000;
    } else if (parts.length === 3) {
        // H:MM:SS format
        return (parts[0] * 3600 + parts[1] * 60 + parts[2]) * 1000;
    }
    return 0;
}

function formatMsToTime(ms) {
    if (ms < 0) ms = 0;
    const totalSeconds = Math.floor(ms / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes}:${seconds.toString().padStart(2, '0')}`;
}

let progressAnimationId = null;

function updateProgressDisplay() {
    if (state.isSeeking) {
        progressAnimationId = requestAnimationFrame(updateProgressDisplay);
        return;
    }

    let displayTimeMs = state.currentTimeMs;

    if (state.isPlaying && state.lastSyncTime > 0) {
        const elapsed = performance.now() - state.lastSyncTime;
        displayTimeMs = state.currentTimeMs + elapsed;

        if (displayTimeMs > state.totalTimeMs) {
            displayTimeMs = state.totalTimeMs;
        }
    }

    let progressPercent = 0;
    if (state.totalTimeMs > 0) {
        progressPercent = (displayTimeMs / state.totalTimeMs) * 100;
    }

    if (els.currTime) {
        els.currTime.innerText = formatMsToTime(displayTimeMs);
    }
    if (els.totTime) {
        els.totTime.innerText = formatMsToTime(state.totalTimeMs);
    }
    if (els.progressFill) {
        els.progressFill.style.width = progressPercent + "%";
    }
    if (els.progressBar) {
        els.progressBar.setAttribute('aria-valuenow', Math.round(progressPercent));
        els.progressBar.setAttribute('aria-valuetext',
            `${formatMsToTime(displayTimeMs)} of ${formatMsToTime(state.totalTimeMs)}`);
    }

    progressAnimationId = requestAnimationFrame(updateProgressDisplay);
}

function startProgressAnimation() {
    if (progressAnimationId) return;
    progressAnimationId = requestAnimationFrame(updateProgressDisplay);
}

function stopProgressAnimation() {
    if (progressAnimationId) {
        cancelAnimationFrame(progressAnimationId);
        progressAnimationId = null;
    }
}

function togglePlayIcon(playing) {
    if (playing) {
        els.playIcon?.classList.add("hidden");
        els.pauseIcon?.classList.remove("hidden");
    } else {
        els.playIcon?.classList.remove("hidden");
        els.pauseIcon?.classList.add("hidden");
    }
}

async function fetchQueue() {
    try {
        const res = await apiRequest('queue');
        if (!res.ok) return;

        const data = await res.json();
        if (data.success && data.up_next) {
            renderQueue(data.up_next);
        } else if (data.up_next && data.up_next.length === 0) {
            els.queueList.innerHTML = '<div class="queue-empty">Queue is empty</div>';
        }
    } catch (e) {
        console.error('Queue fetch error:', e);
    }
}

function renderQueue(items) {
    if (!els.queueList) return;
    els.queueList.innerHTML = '';

    items.forEach(item => {
        const queueItem = createQueueItem(item);
        els.queueList.appendChild(queueItem);
    });
}

function createQueueItem(item) {
    const queueItem = document.createElement('div');
    queueItem.className = 'queue-item';
    queueItem.setAttribute('role', 'button');
    queueItem.setAttribute('tabindex', '0');
    queueItem.setAttribute('aria-label', `Play ${item.track} by ${item.artist}`);
    queueItem.dataset.index = item.index;

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
    qImg.src = item.thumbnail || getPlaceholderImage();
    qImg.alt = `${item.track} thumbnail`;
    qImg.loading = 'lazy';
    qThumb.appendChild(qImg);

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

    return queueItem;
}

function getPlaceholderImage() {
    return 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40"><rect fill="%23333" width="40" height="40"/><text x="50%" y="50%" fill="%23666" font-size="12" text-anchor="middle" dy=".3em">♪</text></svg>';
}

async function control(action) {
    if (state.isActionInProgress || state.isDeviceOffline) {
        if (state.isDeviceOffline) {
            showToast('Device is offline', 'error');
        }
        return;
    }
    state.isActionInProgress = true;

    try {
        const res = await apiRequest(action);
        if (!res.ok) {
            if (res.status === 404 || res.status === 403) {
                showOfflineState();
                state.isDeviceOffline = true;
                showToast('Device is offline', 'error');
            } else {
                showToast(`Failed to ${action}`, 'error');
            }
            return;
        }
        state.consecutiveFailures = 0;
        setTimeout(fetchState, 200);
    } catch (e) {
        console.error(`Control error (${action}):`, e);
        showToast('Network error', 'error');
    } finally {
        setTimeout(() => { state.isActionInProgress = false; }, CONFIG.ACTION_COOLDOWN);
    }
}

function togglePlay() {
    control(state.isPlaying ? "pause" : "play");
}

async function toggleShuffle() {
    try {
        const isShuffle = els.shuffleBtn?.classList.contains("active");
        const res = await apiRequest(`shuffle/${!isShuffle}`);
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
    const isLiked = els.likeBtn?.classList.contains("active");
    control(isLiked ? "dislike" : "like");
}

async function playQueue(index) {
    if (state.isDeviceOffline) {
        showToast('Device is offline', 'error');
        return;
    }
    try {
        const res = await apiRequest(`queue/${index}`);
        if (!res.ok) {
            if (res.status === 404 || res.status === 403) {
                showOfflineState();
                state.isDeviceOffline = true;
                showToast('Device is offline', 'error');
            } else {
                showToast('Failed to play track', 'error');
            }
            return;
        }
        state.consecutiveFailures = 0;
        setTimeout(fetchState, 500);
    } catch (e) {
        console.error('Queue play error:', e);
        showToast('Network error', 'error');
    }
}

function showToast(message, type = 'info') {
    const existingToast = document.querySelector('.toast');
    if (existingToast) existingToast.remove();

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'polite');
    document.body.appendChild(toast);

    requestAnimationFrame(() => {
        toast.classList.add('show');
    });

    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, CONFIG.TOAST_DURATION);
}

function initProgressBar() {
    const progressBar = els.progressBar;
    if (!progressBar) return;

    let seekDebounceTimer = null;

    const debouncedSeek = (percent) => {
        if (seekDebounceTimer) {
            clearTimeout(seekDebounceTimer);
        }
        state.lastSeekPercent = percent;
        seekDebounceTimer = setTimeout(async () => {
            await performSeek(Math.round(state.lastSeekPercent));
        }, CONFIG.SEEK_DEBOUNCE);
    };

    async function performSeek(percent) {
        if (state.isDeviceOffline) {
            showToast('Device is offline', 'error');
            return;
        }
        try {
            if (state.totalTimeMs > 0) {
                state.currentTimeMs = (percent / 100) * state.totalTimeMs;
                state.lastSyncTime = performance.now();
                state.progressPercent = percent;
            }

            const res = await apiRequest(`seek/${percent}`);
            if (!res.ok) {
                if (res.status === 404 || res.status === 403) {
                    showOfflineState();
                    state.isDeviceOffline = true;
                    showToast('Device is offline', 'error');
                } else {
                    showToast('Seek failed', 'error');
                }
            } else {
                state.consecutiveFailures = 0;
                setTimeout(fetchState, 100);
            }
        } catch (e) {
            console.error('Seek error:', e);
            showToast('Network error', 'error');
        }
    }

    function getSeekPercent(e, rect) {
        const clientX = e.touches ? e.touches[0].clientX : e.clientX;
        return Math.max(0, Math.min(100, ((clientX - rect.left) / rect.width) * 100));
    }

    function updateProgressVisual(percent) {
        if (els.progressFill) {
            els.progressFill.style.width = percent + '%';
        }
        progressBar.setAttribute('aria-valuenow', Math.round(percent));
    }

    function handleSeekStart(e) {
        if (state.isDeviceOffline) {
            showToast('Device is offline', 'error');
            return;
        }
        state.isSeeking = true;
        progressBar.classList.add('seeking');
        const rect = progressBar.getBoundingClientRect();
        const percent = getSeekPercent(e, rect);
        updateProgressVisual(percent);
        state.lastSeekPercent = percent;

        if (e.type === 'mousedown') {
            e.preventDefault();
        }
    }

    function handleSeekMove(e) {
        if (!state.isSeeking) return;
        e.preventDefault();
        const rect = progressBar.getBoundingClientRect();
        const percent = getSeekPercent(e, rect);
        updateProgressVisual(percent);
        state.lastSeekPercent = percent;
    }

    function handleSeekEnd(e) {
        if (!state.isSeeking) return;
        state.isSeeking = false;
        progressBar.classList.remove('seeking');
        debouncedSeek(state.lastSeekPercent);
    }

    progressBar.addEventListener('mousedown', handleSeekStart);
    document.addEventListener('mousemove', handleSeekMove);
    document.addEventListener('mouseup', handleSeekEnd);

    progressBar.addEventListener('touchstart', handleSeekStart, { passive: false });
    progressBar.addEventListener('touchmove', handleSeekMove, { passive: false });
    progressBar.addEventListener('touchend', handleSeekEnd);
    progressBar.addEventListener('touchcancel', handleSeekEnd);

    progressBar.addEventListener('click', (e) => {
        if (state.isSeeking) return;
        const rect = progressBar.getBoundingClientRect();
        const percent = getSeekPercent(e, rect);
        updateProgressVisual(percent);
        debouncedSeek(percent);
    });

    progressBar.addEventListener('keydown', (e) => {
        if (state.isDeviceOffline) return;

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

let pollInterval = null;

function startPolling() {
    if (pollInterval) return;
    pollInterval = setInterval(fetchState, CONFIG.POLL_INTERVAL);
    fetchState();
    startProgressAnimation();
}

function stopPolling() {
    if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
    }
    stopProgressAnimation();
}

function init() {
    initElements();

    if (els.appContainer && !els.appContainer.hasAttribute('data-state')) {
        els.appContainer.setAttribute('data-state', 'loading');
    }

    initProgressBar();

    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            stopPolling();
        } else {
            startPolling();
        }
    });

    startPolling();
}

document.addEventListener('DOMContentLoaded', init);

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebar-overlay');

    if (sidebar && overlay) {
        sidebar.classList.toggle('open');
        overlay.classList.toggle('open');

        if (sidebar.classList.contains('open')) {
            loadSidebarData();
        }
    }
}

async function loadSidebarData() {
    try {
        const userRes = await fetch('/api/auth/me');
        if (userRes.ok) {
            const user = await userRes.json();
            const usernameEl = document.getElementById('sidebar-username');
            const avatarEl = document.getElementById('user-avatar');
            if (usernameEl) usernameEl.textContent = user.username;
            if (avatarEl) avatarEl.textContent = user.username.charAt(0).toUpperCase();
        }

        const configRes = await fetch('/api/config');
        if (configRes.ok) {
            const config = await configRes.json();
            document.getElementById('config-client-id').textContent = config.client_id || '-';
            document.getElementById('config-client-secret').textContent = config.client_secret || '-';
            document.getElementById('config-gist-id').textContent = config.gist_id || '-';
            document.getElementById('config-github-token').textContent = config.github_token || '-';
            document.getElementById('config-gist-filename').textContent = config.gist_filename || '-';
        }

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

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const sidebar = document.getElementById('sidebar');
        if (sidebar && sidebar.classList.contains('open')) {
            toggleSidebar();
        }
    }
});