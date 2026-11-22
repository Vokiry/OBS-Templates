/**
 * SYSTEM Broadcast Templates — Media Request / YouTube Overlay
 * FIFO playback, DonateX synchronization, safe timers, and YouTube postMessage handling.
 */

(() => {
  const params = new URLSearchParams(location.search);
  const card = document.getElementById('media-card');
  const donorEl = document.getElementById('media-donor');
  const queueBadgeEl = document.getElementById('media-queue');
  const messageEl = document.getElementById('media-message');
  const titleEl = document.getElementById('media-track-title');
  const statusEl = document.getElementById('media-duration');
  const container = document.getElementById('yt-player-container');

  const allowedDomains = ['youtube.com', 'youtube-nocookie.com'];
  let youtubeDomain = allowedDomains.includes(params.get('domain')) ? params.get('domain') : 'youtube-nocookie.com';
  const mediaConfigReady = (async () => {
    if (params.get('ws') === 'off') return;
    try {
      const response = await SystemAPI.fetch('/api/media/config');
      if (!response.ok) return;
      const config = await response.json();
      // An explicit server setting is authoritative; the URL is a fallback for standalone previews.
      if (config.configured && allowedDomains.includes(config.youtubeDomain)) {
        youtubeDomain = config.youtubeDomain;
      }
    } catch (e) {}
  })();

  let socketRef = null;
  let ytPlayer = null;
  let ytApiReady = Boolean(window.YT && window.YT.Player);
  let trackQueue = [];
  let currentTrack = null;
  let isPlaying = false;
  let isPaused = false;
  let advancing = false;
  let endCheckTimer = null;
  let activePlayerDomain = youtubeDomain;
  let playbackGeneration = 0;
  let lastReportedTime = 0;
  let lastReportedDuration = 0;
  const pendingTimers = new Set();

  window.onYouTubeIframeAPIReady = () => {
    ytApiReady = true;
  };

  if (params.get('width')) card.style.width = `${parseInt(params.get('width'), 10) || 480}px`;

  function schedule(callback, delay) {
    const generation = playbackGeneration;
    const timer = setTimeout(() => {
      pendingTimers.delete(timer);
      if (generation === playbackGeneration) callback();
    }, delay);
    pendingTimers.add(timer);
    return timer;
  }

  function clearPlaybackTimers() {
    if (endCheckTimer) {
      clearInterval(endCheckTimer);
      endCheckTimer = null;
    }
    pendingTimers.forEach(timer => clearTimeout(timer));
    pendingTimers.clear();
  }

  function invalidatePlayback() {
    playbackGeneration += 1;
    clearPlaybackTimers();
  }

  function updateQueueBadge() {
    if (!queueBadgeEl) return;
    queueBadgeEl.textContent = `queue [ ${trackQueue.length} ]`;
    queueBadgeEl.style.display = trackQueue.length > 0 ? 'inline-block' : 'none';
  }

  function updateTrackDisplay(track) {
    const rawUser = track.user || track.donor || '';
    const cleanUser = rawUser && rawUser !== 'Заказ трека' && rawUser !== 'Добавление трека в очередь'
      ? rawUser
      : 'viewer';
    donorEl.textContent = `${cleanUser}${track.amount ? ` · ${track.amount}` : ''}`;
    titleEl.textContent = track.title || 'YouTube Track';
    statusEl.textContent = 'PLAYING';
    statusEl.style.color = '';
    messageEl.style.color = '';
    messageEl.textContent = track.message || '';
    messageEl.style.display = track.message ? 'block' : 'none';
  }

  function enrichTrack(target, item) {
    if (item.title && item.title !== 'YouTube Track') target.title = item.title;
    if (item.amount) target.amount = item.amount;
    if (item.message) target.message = item.message;
    if (item.source) target.source = item.source;
  }

  function enqueueTrack(item) {
    if (!item || !/^[A-Za-z0-9_-]{11}$/.test(item.youtubeId || '')) return;
    item = { ...item, requestId: String(item.requestId || item.donationId || `video-${item.youtubeId}`) };
    if (currentTrack && currentTrack.requestId === item.requestId) {
      enrichTrack(currentTrack, item);
      updateTrackDisplay(currentTrack);
      return;
    }
    const existing = trackQueue.find(track => track.requestId === item.requestId);
    if (existing) {
      enrichTrack(existing, item);
      return;
    }

    trackQueue.push({ ...item });
    updateQueueBadge();
    if (!isPlaying && !currentTrack && !advancing) playNextTrack();
  }

  function syncMediaMode(data) {
    if (data.mode === 'local') {
      trackQueue = [];
      updateQueueBadge();
      stopPlayback();
      return;
    }
    if (data.mode !== 'request' || !Array.isArray(data.queue) || data.queue.length === 0) return;
    const requests = data.queue.map(item => ({
      ...item,
      requestId: String(item.requestId || item.donationId || `video-${item.youtubeId}`),
    }));
    const active = requests[0];
    if (currentTrack && currentTrack.requestId === active.requestId) {
      enrichTrack(currentTrack, active);
      trackQueue = requests.slice(1);
      updateQueueBadge();
      updateTrackDisplay(currentTrack);
      if (isPaused) statusEl.textContent = 'PAUSED';
      return;
    }

    // Reconnect or stale playback: adopt the server's authoritative active request.
    invalidatePlayback();
    destroyPlayer();
    currentTrack = null;
    isPlaying = false;
    advancing = false;
    trackQueue = requests;
    playNextTrack();
  }

  function destroyPlayer() {
    const previousPlayer = ytPlayer;
    ytPlayer = null;
    if (previousPlayer && typeof previousPlayer.destroy === 'function') {
      try { previousPlayer.destroy(); } catch (e) {}
    }
    container.innerHTML = '';
  }

  function showPlaybackError(statusText, messageText) {
    statusEl.textContent = statusText;
    statusEl.style.color = 'var(--color-danger)';
    messageEl.textContent = messageText;
    messageEl.style.display = 'block';
    messageEl.style.color = 'var(--color-danger)';
  }

  function handlePlaybackError(errorCode, track = currentTrack) {
    if (!track || track !== currentTrack) return;
    console.warn('YouTube playback error code:', errorCode);
    if (errorCode === 101 || errorCode === 150) {
      showPlaybackError('RESTRICTED // SKIPPING...', '[ ВОСПРОИЗВЕДЕНИЕ ЗАПРЕЩЕНО ПРАВООБЛАДАТЕЛЕМ ]');
      schedule(() => skipTrack('blocked_by_owner'), 3500);
    } else if (errorCode === 100) {
      showPlaybackError('VIDEO NOT FOUND // SKIPPING...', '[ ВИДЕО НЕ НАЙДЕНО, УДАЛЕНО ИЛИ ПРИВАТНОЕ ]');
      schedule(() => skipTrack('not_found'), 3000);
    } else if (errorCode === 2) {
      showPlaybackError('INVALID VIDEO ID', '[ НЕКОРРЕКТНЫЙ ID ВИДЕО ]');
      schedule(() => skipTrack('invalid_param'), 3000);
    } else if ((errorCode === 153 || errorCode === 5) && activePlayerDomain !== 'youtube-nocookie.com') {
      renderPlayer(track, 'youtube-nocookie.com');
    } else {
      schedule(() => onTrackEnded(track), 2500);
    }
  }

  async function renderPlayer(track, forcedDomain = null) {
    if (!track || track !== currentTrack) return;
    clearPlaybackTimers();
    const generation = playbackGeneration;
    await mediaConfigReady;
    if (generation !== playbackGeneration || track !== currentTrack) return;

    destroyPlayer();
    lastReportedTime = 0;
    lastReportedDuration = 0;
    const domain = forcedDomain || youtubeDomain;
    activePlayerDomain = domain;
    const embedDomain = domain === 'youtube.com' ? 'www.youtube.com' : 'www.youtube-nocookie.com';
    const apiHost = `https://${embedDomain}`;

    if (ytApiReady && window.YT && window.YT.Player) {
      try {
        container.innerHTML = '<div id="yt-player-target"></div>';
        const player = new YT.Player('yt-player-target', {
          host: apiHost,
          width: '100%',
          height: '100%',
          videoId: track.youtubeId,
          playerVars: {
            autoplay: 1,
            controls: 1,
            rel: 0,
            enablejsapi: 1,
            playsinline: 1,
            origin: window.location.origin,
          },
          events: {
            onReady: event => {
              if (generation !== playbackGeneration || track !== currentTrack || ytPlayer !== player) return;
              try {
                event.target.unMute();
                event.target.setVolume(100);
                event.target.playVideo();
              } catch (e) {}
              startEndCheckTimer();
            },
            onStateChange: event => {
              if (generation === playbackGeneration && ytPlayer === player && event.data === 0) onTrackEnded(track);
            },
            onError: event => {
              if (generation === playbackGeneration && ytPlayer === player) handlePlaybackError(event.data, track);
            },
          },
        });
        ytPlayer = player;
        return;
      } catch (e) {
        console.warn('YT.Player init failed, falling back to standard iframe:', e);
      }
    }

    container.innerHTML = `
      <iframe
        id="yt-iframe"
        src="${apiHost}/embed/${encodeURIComponent(track.youtubeId)}?autoplay=1&enablejsapi=1&controls=1&playsinline=1&origin=${encodeURIComponent(window.location.origin)}"
        style="width: 100%; height: 100%; border: 0; display: block;"
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
        referrerpolicy="strict-origin-when-cross-origin"
        allowfullscreen>
      </iframe>`;
    setupDirectIframeHandlers();
    startEndCheckTimer();
  }

  function playNextTrack() {
    advancing = false;
    invalidatePlayback();
    isPaused = false;
    if (trackQueue.length === 0) {
      stopPlayback();
      return;
    }

    currentTrack = trackQueue.shift();
    isPlaying = true;
    updateQueueBadge();
    updateTrackDisplay(currentTrack);
    card.classList.add('is-active');
    renderPlayer(currentTrack);
  }

  function setupDirectIframeHandlers() {
    const iframe = container.querySelector('iframe');
    if (!iframe) return;
    iframe.addEventListener('load', () => {
      if (!iframe.isConnected) return;
      try {
        iframe.contentWindow.postMessage(JSON.stringify({ event: 'listening', id: 1, channel: 'widget' }), '*');
        for (const [id, eventName] of [[1, 'onStateChange'], [2, 'onError']]) {
          iframe.contentWindow.postMessage(JSON.stringify({
            event: 'command', func: 'addEventListener', args: [eventName], id, channel: 'widget',
          }), '*');
        }
      } catch (e) {}
    });
  }

  function startEndCheckTimer() {
    if (endCheckTimer) clearInterval(endCheckTimer);
    endCheckTimer = setInterval(() => {
      if (!isPlaying || !currentTrack) {
        clearPlaybackTimers();
        return;
      }
      if (isPaused) return;
      if (ytPlayer && typeof ytPlayer.getCurrentTime === 'function' && typeof ytPlayer.getDuration === 'function') {
        try {
          const current = ytPlayer.getCurrentTime();
          const duration = ytPlayer.getDuration();
          if (duration > 0 && current >= duration - 0.8) {
            onTrackEnded(currentTrack);
            return;
          }
        } catch (e) {}
      }
      const iframe = container.querySelector('iframe');
      if (iframe && iframe.contentWindow) {
        try {
          for (const func of ['getCurrentTime', 'getDuration']) {
            iframe.contentWindow.postMessage(JSON.stringify({ event: 'command', func, args: '' }), '*');
          }
        } catch (e) {}
      }
    }, 1000);
  }

  function notifyBridge(payload) {
    SystemAPI.fetch('/notify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(response => {
      if (!response.ok) throw new Error(`notify HTTP ${response.status}`);
    }).catch(() => {
      if (socketRef && socketRef.readyState === WebSocket.OPEN) {
        try { socketRef.send(JSON.stringify(payload)); } catch (e) {}
      }
    });
  }

  function onTrackEnded(track = currentTrack) {
    if (!isPlaying || !track || track !== currentTrack) return;
    invalidatePlayback();
    statusEl.textContent = 'FINISHED';
    isPlaying = false;
    currentTrack = null;
    notifyBridge({
      type: 'media_finished',
      source: track.source || 'donatex',
      youtubeId: track.youtubeId,
      requestId: track.requestId,
      donationId: track.donationId || '',
    });
    advanceQueue(600);
  }

  function skipTrack(origin, expectedRequestId = null, expectedDonationId = null) {
    if (!currentTrack) return;
    if (expectedRequestId && currentTrack.requestId !== expectedRequestId) return;
    if (expectedDonationId && currentTrack.donationId !== expectedDonationId) return;
    const skippedTrack = currentTrack;
    invalidatePlayback();
    isPlaying = false;
    currentTrack = null;
    destroyPlayer();

    // Server-originated skips have already completed the DonateX/coordinator operation.
    if (['blocked_by_owner', 'not_found', 'invalid_param'].includes(origin)) {
      notifyBridge({
        type: 'media_finished',
        source: skippedTrack.source || 'donatex',
        youtubeId: skippedTrack.youtubeId,
        requestId: skippedTrack.requestId,
        donationId: skippedTrack.donationId || '',
      });
    }
    advanceQueue(400);
  }

  function advanceQueue(delay) {
    if (trackQueue.length > 0) {
      advancing = true;
      schedule(playNextTrack, delay);
    } else {
      advancing = true;
      schedule(() => stopPlayback(), 1200);
    }
  }

  function togglePause(forcedAction) {
    if (!isPlaying) return;
    if (forcedAction === 'pause') isPaused = true;
    else if (['resume', 'play'].includes(forcedAction)) isPaused = false;
    else isPaused = !isPaused;

    if (ytPlayer && typeof ytPlayer.pauseVideo === 'function') {
      try {
        if (isPaused) ytPlayer.pauseVideo();
        else ytPlayer.playVideo();
        statusEl.textContent = isPaused ? 'PAUSED' : 'PLAYING';
        return;
      } catch (e) {}
    }
    const iframe = container.querySelector('iframe');
    if (iframe && iframe.contentWindow) {
      iframe.contentWindow.postMessage(JSON.stringify({
        event: 'command', func: isPaused ? 'pauseVideo' : 'playVideo', args: '',
      }), '*');
      statusEl.textContent = isPaused ? 'PAUSED' : 'PLAYING';
    }
  }

  function stopPlayback() {
    invalidatePlayback();
    advancing = false;
    card.classList.remove('is-active');
    isPaused = false;
    isPlaying = false;
    currentTrack = null;
    destroyPlayer();
  }

  window.addEventListener('message', event => {
    if (!['https://www.youtube.com', 'https://www.youtube-nocookie.com'].includes(event.origin)) return;
    const iframe = container.querySelector('iframe');
    if (!iframe || event.source !== iframe.contentWindow || !event.data) return;
    let data = event.data;
    if (typeof data === 'string') {
      try { data = JSON.parse(data); } catch (e) { return; }
    }
    if (!data || typeof data !== 'object') return;
    if (data.event === 'onStateChange' && data.info === 0) onTrackEnded(currentTrack);
    else if (data.event === 'onError') handlePlaybackError(data.info, currentTrack);
    else if (data.info && typeof data.info === 'object') {
      lastReportedTime = Number(data.info.currentTime) || lastReportedTime;
      lastReportedDuration = Number(data.info.duration) || lastReportedDuration;
      if (!isPaused && lastReportedDuration > 0 && lastReportedTime >= lastReportedDuration - 0.8) {
        onTrackEnded(currentTrack);
      }
    }
  });

  if (params.has('yt')) {
    enqueueTrack({
      youtubeId: params.get('yt'),
      user: params.get('donor') || 'TestDonor',
      amount: params.get('amount') || '$10.00',
      message: params.get('msg') || 'Track request test!',
      title: params.get('title') || 'YouTube Track',
    });
  }

  const wsParam = params.get('ws');
  if (wsParam !== 'off') {
    const wsUrl = SystemAPI.withKey(wsParam || `ws://${location.host || '127.0.0.1:8787'}/events`);
    let retryDelay = 1000;
    const connect = () => {
      const socket = new WebSocket(wsUrl);
      socketRef = socket;
      socket.onopen = () => { retryDelay = 1000; };
      socket.onmessage = message => {
        try {
          const data = JSON.parse(message.data);
          if (data.type === 'media_request') enqueueTrack(data);
          else if (data.type === 'media_config' && allowedDomains.includes(data.youtubeDomain)) {
            youtubeDomain = data.youtubeDomain;
          } else if (data.type === 'media_mode') syncMediaMode(data);
          else if (data.type === 'media_control') {
            if (data.action === 'skip') skipTrack(data.origin, data.requestId, data.donationId);
            else if (['toggle_pause', 'pause', 'resume'].includes(data.action)) togglePause(data.action);
            else if (data.action === 'stop') {
              trackQueue = [];
              updateQueueBadge();
              stopPlayback();
            }
          }
        } catch (e) {
          console.warn('Media request event failed:', e);
        }
      };
      socket.onclose = () => {
        if (socketRef === socket) socketRef = null;
        setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 2, 10000);
      };
      socket.onerror = () => socket.close();
    };
    connect();
  }
})();
