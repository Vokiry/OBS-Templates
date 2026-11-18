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
  let ytPlayer = null;
  let ytApiReady = false;
  let trackQueue = [];
  let currentTrack = null;
  let isPlaying = false;
  let endCheckTimer = null;

  if (window.YT && window.YT.Player) {
    ytApiReady = true;
  }
  window.onYouTubeIframeAPIReady = () => {
    ytApiReady = true;
  };

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

    if (ytApiReady && window.YT && window.YT.Player) {
      try {
        if (!ytPlayer) {
          container.innerHTML = '<div id="yt-player-target"></div>';
          ytPlayer = new YT.Player('yt-player-target', {
            host: 'https://www.youtube-nocookie.com',
            width: '100%',
            height: '100%',
            videoId: currentTrack.youtubeId,
            playerVars: {
              autoplay: 1,
              controls: 1,
              rel: 0,
              enablejsapi: 1,
              playsinline: 1
            },
            events: {
              onReady: (e) => {
                try {
                  e.target.unMute();
                  e.target.setVolume(100);
                  e.target.playVideo();
                } catch (err) {}
                startEndCheckTimer();
              },
              onStateChange: (e) => {
                if (e.data === 0) { // 0 === YT.PlayerState.ENDED
                  onTrackEnded();
                }
              },
              onError: (e) => {
                handlePlaybackError(e.data);
              }
            }
          });
        } else {
          ytPlayer.loadVideoById(currentTrack.youtubeId);
          startEndCheckTimer();
        }
        return;
      } catch (e) {
        console.warn('YT.Player init failed, falling back to standard iframe:', e);
      }
    }

    fallbackDirectIframe(currentTrack.youtubeId);
    startEndCheckTimer();
  }

  function startEndCheckTimer() {
    if (endCheckTimer) clearInterval(endCheckTimer);

    endCheckTimer = setInterval(() => {
      if (!isPlaying || !currentTrack) {
        clearInterval(endCheckTimer);
        endCheckTimer = null;
        return;
      }

      // Check via YT.Player API if active
      if (ytPlayer && typeof ytPlayer.getCurrentTime === 'function' && typeof ytPlayer.getDuration === 'function') {
        try {
          const cur = ytPlayer.getCurrentTime();
          const dur = ytPlayer.getDuration();
          if (dur > 0 && cur >= dur - 0.8) {
            clearInterval(endCheckTimer);
            endCheckTimer = null;
            onTrackEnded();
            return;
          }
        } catch (e) {}
      }

      // Query via iframe postMessage if direct iframe
      const iframe = container.querySelector('iframe');
      if (iframe && iframe.contentWindow) {
        try {
          iframe.contentWindow.postMessage(JSON.stringify({ event: 'command', func: 'getCurrentTime', args: '' }), '*');
          iframe.contentWindow.postMessage(JSON.stringify({ event: 'command', func: 'getDuration', args: '' }), '*');
        } catch (e) {}
      }
    }, 1000);
  }

  function handlePlaybackError(errorCode) {
    console.warn('YouTube playback error code:', errorCode);
    if (errorCode === 101 || errorCode === 150) {
      statusEl.textContent = 'RESTRICTED // SKIPPING...';
      statusEl.style.color = 'var(--color-danger)';
      if (messageEl) {
        messageEl.textContent = '[ ВОСПРОИЗВЕДЕНИЕ ЗАПРЕЩЕНО ПРАВООБЛАДАТЕЛЕМ НА СТОРОННИХ САЙТАХ ]';
        messageEl.style.display = 'block';
        messageEl.style.color = 'var(--color-danger)';
      }
      setTimeout(() => {
        skipTrack('blocked_by_owner');
      }, 3500);
    } else if (errorCode === 100) {
      statusEl.textContent = 'VIDEO NOT FOUND // SKIPPING...';
      setTimeout(() => {
        skipTrack('not_found');
      }, 3000);
    } else {
      fallbackDirectIframe(currentTrack ? currentTrack.youtubeId : '');
      startEndCheckTimer();
    }
  }

  function fallbackDirectIframe(videoId) {
    if (!videoId) return;
    container.innerHTML = `
      <iframe
        id="yt-iframe"
        src="https://www.youtube-nocookie.com/embed/${encodeURIComponent(videoId)}?autoplay=1&enablejsapi=1&controls=1&playsinline=1"
        style="width: 100%; height: 100%; border: 0; display: block;"
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
        referrerpolicy="strict-origin-when-cross-origin"
        allowfullscreen>
      </iframe>
    `;

    const iframe = container.querySelector('iframe');
    if (iframe) {
      iframe.addEventListener('load', () => {
        try {
          iframe.contentWindow.postMessage(JSON.stringify({
            event: 'listening',
            id: 1,
            channel: 'widget'
          }), '*');
          iframe.contentWindow.postMessage(JSON.stringify({
            event: 'command',
            func: 'addEventListener',
            args: ['onStateChange'],
            id: 1,
            channel: 'widget'
          }), '*');
        } catch (e) {}
      });
    }
  }

  function onTrackEnded() {
    if (!isPlaying) return;
    if (endCheckTimer) {
      clearInterval(endCheckTimer);
      endCheckTimer = null;
    }
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
      }, 1500);
    }
  }

  function skipTrack(origin) {
    if (!isPlaying && !currentTrack) return;
    if (ytPlayer && typeof ytPlayer.stopVideo === 'function') {
      try { ytPlayer.stopVideo(); } catch (e) {}
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

    if (ytPlayer && typeof ytPlayer.pauseVideo === 'function') {
      try {
        if (isPaused) {
          ytPlayer.pauseVideo();
          statusEl.textContent = 'PAUSED';
        } else {
          ytPlayer.playVideo();
          statusEl.textContent = 'PLAYING';
        }
        return;
      } catch (e) {}
    }

    const iframe = container.querySelector('iframe');
    if (iframe && iframe.contentWindow) {
      const cmd = isPaused ? 'pauseVideo' : 'playVideo';
      iframe.contentWindow.postMessage(JSON.stringify({ event: 'command', func: cmd, args: '' }), '*');
      statusEl.textContent = isPaused ? 'PAUSED' : 'PLAYING';
    }
  }

  function stopPlayback() {
    if (endCheckTimer) {
      clearInterval(endCheckTimer);
      endCheckTimer = null;
    }
    card.classList.remove('is-active');
    isPaused = false;
    isPlaying = false;
    currentTrack = null;

    if (socketRef && socketRef.readyState === WebSocket.OPEN) {
      try {
        socketRef.send(JSON.stringify({ type: 'media_request_ended' }));
      } catch (e) {}
    }

    setTimeout(() => {
      if (!isPlaying) {
        container.innerHTML = '';
        ytPlayer = null;
      }
    }, 350);
  }

  let lastReportedTime = 0;
  let lastReportedDuration = 0;

  // Listen for YouTube iframe postMessage events (works even without iframe_api)
  window.addEventListener('message', (event) => {
    if (!event.data) return;
    let data = event.data;
    if (typeof data === 'string') {
      try { data = JSON.parse(data); } catch (e) { return; }
    }
    if (data && data.event === 'onStateChange') {
      if (data.info === 0) { // 0 === ENDED
        onTrackEnded();
      }
    } else if (data && data.event === 'onError') {
      handlePlaybackError(data.info);
    } else if (data && data.info !== undefined && typeof data.info === 'number') {
      if (data.info > 100) {
        lastReportedDuration = data.info;
      } else if (data.info > 0) {
        lastReportedTime = data.info;
      }
      if (lastReportedDuration > 0 && lastReportedTime >= lastReportedDuration - 0.8) {
        onTrackEnded();
      }
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
