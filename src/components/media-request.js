/**
 * SYSTEM Broadcast Templates — Media Request / YouTube Overlay
 * Handles YouTube Iframe API playback, synchronized queue with DonateX,
 * skip, pause/resume, and postMessage fallback listeners.
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

  let socketRef = null;
  let trackQueue = [];
  let currentTrack = null;
  let isPlaying = false;
  let endCheckTimer = null;

  if (params.get('width')) {
    card.style.width = params.get('width') + 'px';
  }

  function updateQueueBadge() {
    if (!queueBadgeEl) return;
    if (trackQueue.length > 0) {
      queueBadgeEl.textContent = `queue [ ${trackQueue.length} ]`;
      queueBadgeEl.style.display = 'inline-block';
    } else {
      queueBadgeEl.style.display = 'none';
    }
  }

  function updateTrackDisplay(track) {
    donorEl.textContent = `${track.user || 'viewer'}${track.amount ? ' · ' + track.amount : ''}`;
    titleEl.textContent = track.title || 'YouTube Track';
    statusEl.textContent = 'PLAYING';

    if (track.message) {
      messageEl.textContent = track.message;
      messageEl.style.display = 'block';
    } else {
      messageEl.style.display = 'none';
    }
  }

  function enqueueTrack(item) {
    if (!item || !item.youtubeId) return;

    // 1. If same track is already playing, enrich metadata if previous was generic
    if (currentTrack && currentTrack.youtubeId === item.youtubeId) {
      if (item.title && item.title !== 'YouTube Track') currentTrack.title = item.title;
      if (item.amount) currentTrack.amount = item.amount;
      if (item.message) currentTrack.message = item.message;
      updateTrackDisplay(currentTrack);
      return;
    }

    // 2. If same track is already in queue, enrich metadata
    const existing = trackQueue.find(t => t.youtubeId === item.youtubeId);
    if (existing) {
      if (item.title && item.title !== 'YouTube Track') existing.title = item.title;
      if (item.amount) existing.amount = item.amount;
      if (item.message) existing.message = item.message;
      return;
    }

    trackQueue.push(item);
    updateQueueBadge();

    if (!isPlaying) {
      playNextTrack();
    }
  }

  function playNextTrack() {
    if (endCheckTimer) {
      clearInterval(endCheckTimer);
      endCheckTimer = null;
    }

    if (trackQueue.length === 0) {
      currentTrack = null;
      isPlaying = false;
      stopPlayback();
      return;
    }

    currentTrack = trackQueue.shift();
    isPlaying = true;
    updateQueueBadge();
    updateTrackDisplay(currentTrack);

    card.classList.add('is-active');

    // Direct clean iframe embed: zero external script dependencies, robust on VPN/CEF
    container.innerHTML = `
      <iframe
        id="yt-iframe"
        src="https://www.youtube-nocookie.com/embed/${encodeURIComponent(currentTrack.youtubeId)}?autoplay=1&enablejsapi=1&controls=1&playsinline=1"
        style="width: 100%; height: 100%; border: 0; display: block;"
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
        referrerpolicy="strict-origin-when-cross-origin"
        allowfullscreen>
      </iframe>
    `;
  }

  function onTrackEnded() {
    if (!isPlaying) return;
    statusEl.textContent = 'FINISHED';
    isPlaying = false;

    const endedTrack = currentTrack;
    currentTrack = null;

    // Notify bridge to skip DonateX track if it came from DonateX
    if (endedTrack && endedTrack.source === 'donatex' && socketRef && socketRef.readyState === WebSocket.OPEN) {
      try {
        socketRef.send(JSON.stringify({
          type: 'media_finished',
          source: 'donatex',
          youtubeId: endedTrack.youtubeId
        }));
      } catch (e) {}
    }

    // If we have more tracks in local queue:
    if (trackQueue.length > 0) {
      setTimeout(playNextTrack, 600);
    } else {
      setTimeout(() => {
        if (!isPlaying && trackQueue.length === 0) {
          stopPlayback();
        }
      }, 1800);
    }
  }

  function skipTrack(origin) {
    if (!isPlaying && !currentTrack) return;
    const iframe = container.querySelector('iframe');
    if (iframe && iframe.contentWindow) {
      try {
        iframe.contentWindow.postMessage(JSON.stringify({ event: 'command', func: 'stopVideo', args: '' }), '*');
      } catch (e) {}
    }

    const skippedTrack = currentTrack;
    isPlaying = false;
    currentTrack = null;

    if (origin !== 'donatex_server' && skippedTrack && skippedTrack.source === 'donatex' && socketRef && socketRef.readyState === WebSocket.OPEN) {
      try {
        socketRef.send(JSON.stringify({
          type: 'media_finished',
          source: 'donatex',
          youtubeId: skippedTrack.youtubeId
        }));
      } catch (e) {}
    }

    if (trackQueue.length > 0) {
      setTimeout(playNextTrack, 400);
    } else {
      setTimeout(() => {
        if (!isPlaying && trackQueue.length === 0) {
          stopPlayback();
        }
      }, 1800);
    }
  }

  let isPaused = false;
  function togglePause(forcedAction) {
    if (!isPlaying) return;
    if (forcedAction === 'pause') isPaused = true;
    else if (forcedAction === 'resume' || forcedAction === 'play') isPaused = false;
    else isPaused = !isPaused;

    const iframe = container.querySelector('iframe');
    if (iframe && iframe.contentWindow) {
      const cmd = isPaused ? 'pauseVideo' : 'playVideo';
      iframe.contentWindow.postMessage(JSON.stringify({ event: 'command', func: cmd, args: '' }), '*');
      statusEl.textContent = isPaused ? 'PAUSED' : 'PLAYING';
    }
  }

  function stopPlayback() {
    card.classList.remove('is-active');
    isPaused = false;
    if (socketRef && socketRef.readyState === WebSocket.OPEN) {
      try {
        socketRef.send(JSON.stringify({ type: 'media_request_ended' }));
      } catch (e) {}
    }
    setTimeout(() => {
      if (!isPlaying) {
        container.innerHTML = '';
      }
    }, 350);
  }

  // Listen for YouTube iframe postMessage events (works even without iframe_api)
  window.addEventListener('message', (event) => {
    if (!event.data) return;
    let data = event.data;
    if (typeof data === 'string') {
      try { data = JSON.parse(data); } catch (e) { return; }
    }
    if (data && data.event === 'onStateChange' && data.info === 0) {
      onTrackEnded();
    }
  });

  if (params.has('yt')) {
    enqueueTrack({
      youtubeId: params.get('yt'),
      user: params.get('donor') || 'TestDonor',
      amount: params.get('amount') || '$10.00',
      message: params.get('msg') || 'Track request test!',
      title: params.get('title') || 'YouTube Track'
    });
  }

  const wsParam = params.get('ws');
  if (wsParam !== 'off') {
    const wsUrl = wsParam || `ws://${location.host || '127.0.0.1:8787'}/events`;
    let retryDelay = 1000;
    const connect = () => {
      const socket = new WebSocket(wsUrl);
      socketRef = socket;
      socket.onopen = () => { retryDelay = 1000; };
      socket.onmessage = (msg) => {
        try {
          const data = JSON.parse(msg.data);
          if (data.type === 'media_request' && data.youtubeId) {
            enqueueTrack(data);
          } else if (data.type === 'media_control') {
            if (data.action === 'skip') {
              skipTrack(data.origin);
            } else if (data.action === 'toggle_pause' || data.action === 'pause' || data.action === 'resume') {
              togglePause(data.action);
            } else if (data.action === 'stop') {
              trackQueue = [];
              updateQueueBadge();
              stopPlayback();
            }
          }
        } catch (e) {}
      };
      socket.onclose = () => {
        socketRef = null;
        setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 2, 10000);
      };
      socket.onerror = () => socket.close();
    };
    connect();
  }
})();
