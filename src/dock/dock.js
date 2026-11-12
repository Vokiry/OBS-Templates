/**
 * SYSTEM Broadcast Templates — OBS Custom Dock Control Panel
 * State switching, countdown timer controls, media queue, alert management, and diagnostics.
 */

try {
  const cachedTheme = localStorage.getItem('system_theme');
  if (cachedTheme) document.documentElement.dataset.theme = cachedTheme;
} catch (e) {}

const API_BASE = window.location.origin;

async function sendNotify(payload) {
  try {
    const res = await fetch(`${API_BASE}/notify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    showToast(res.ok ? 'OK' : 'ERR');
  } catch (err) {
    showToast('OFFLINE');
  }
}

function showToast(text) {
  const el = document.getElementById('toast');
  el.textContent = `[ ${text} ]`;
  setTimeout(() => { if (el.textContent === `[ ${text} ]`) el.textContent = ''; }, 1800);
}

function setState(state) {
  document.querySelectorAll('.dock__grid--3 .dock__btn').forEach(b => {
    b.classList.toggle('dock__btn--active', b.textContent.toLowerCase().includes(state));
  });
  sendNotify({ type: 'status', state });
}

function setTimer(minutes) {
  sendNotify({ type: 'countdown_control', action: 'set', minutes: Number(minutes) });
}

function adjustTimer(deltaSeconds) {
  sendNotify({ type: 'countdown_control', action: 'adjust', deltaSeconds });
}

let isTimerPaused = false;
function toggleTimerPause() {
  isTimerPaused = !isTimerPaused;
  const btn = document.getElementById('btn-timer-pause');
  if (btn) btn.textContent = isTimerPaused ? 'RESUME' : 'PAUSE';
  sendNotify({ type: 'countdown_control', action: isTimerPaused ? 'pause' : 'resume' });
}

function resetTimer() {
  isTimerPaused = false;
  const btn = document.getElementById('btn-timer-pause');
  if (btn) btn.textContent = 'PAUSE';
  sendNotify({ type: 'countdown_control', action: 'reset' });
}

let isMediaPaused = false;
function toggleMediaPause() {
  isMediaPaused = !isMediaPaused;
  const btn = document.getElementById('btn-media-pause');
  if (btn) btn.textContent = isMediaPaused ? 'RESUME' : 'PAUSE';
  sendNotify({ type: 'media_control', action: isMediaPaused ? 'pause' : 'resume' });
}

async function skipMedia() {
  try {
    const res = await fetch(`${API_BASE}/api/media/skip`, { method: 'POST' });
    showToast(res.ok ? 'TRACK SKIPPED' : 'ERR');
  } catch (e) {
    sendNotify({ type: 'media_control', action: 'skip' });
  }
}

async function skipAlert() {
  try {
    const res = await fetch(`${API_BASE}/api/donations/skip`, { method: 'POST' });
    showToast(res.ok ? 'ALERT SKIPPED' : 'ERR');
  } catch (e) {
    sendNotify({ type: 'alert_skip' });
  }
}

function clearChat() {
  sendNotify({ type: 'chat_clear' });
}

function replayAlert() {
  sendNotify({ type: 'alert_replay' });
  showToast('REPLAY SENT');
}

let isDndActive = false;
function toggleDND() {
  isDndActive = !isDndActive;
  const btn = document.getElementById('btn-dnd');
  if (btn) {
    btn.textContent = isDndActive ? 'DND: ON' : 'DND: OFF';
    btn.classList.toggle('dock__btn--active', isDndActive);
    btn.style.color = isDndActive ? '#E9B13C' : '';
  }
  sendNotify({ type: 'dnd_control', active: isDndActive });
  showToast(isDndActive ? 'DND: SILENT' : 'DND: NORMAL');
}

async function stopTTS() {
  try {
    const res = await fetch(`${API_BASE}/api/tts/stop`, { method: 'POST' });
    showToast(res.ok ? 'TTS STOPPED' : 'ERR');
  } catch (e) {
    sendNotify({ type: 'tts_stop' });
  }
}

// Dev Simulation Triggers
function sendAlert(kind, user, message) {
  sendNotify({ kind, user, message });
}

function sendYouTubeTest() {
  sendNotify({
    type: 'media_request',
    user: 'MusicFan',
    amount: '250 ₽',
    message: 'Track request test',
    youtubeId: 'jfKfPfyJRdk',
    title: 'Lofi Hip Hop Radio — Beats to Relax'
  });
}

function sendChat(user, text, color) {
  sendNotify({ type: 'chat', user, text, color });
}

function sendAnnouncement(user, text, color = 'PRIMARY') {
  sendNotify({
    type: 'chat',
    subtype: 'announcement',
    user: user,
    text: text,
    announcementColor: color
  });
}

let testPollState = 0;
let testPollAutoTimer = null;
function sendTestPoll() {
  testPollState = (testPollState + 1) % 3;
  if (testPollAutoTimer) { clearTimeout(testPollAutoTimer); testPollAutoTimer = null; }

  if (testPollState === 1) {
    // Quick 12-second test countdown so test poll auto-resolves and dismisses
    const ends = new Date(Date.now() + 12000).toISOString();
    sendNotify({
      type: 'poll',
      action: 'begin',
      id: 'test_poll_1',
      title: 'Играем сегодня в хоррор?',
      choices: [
        { id: '1', title: 'Да, обязательно!', votes: 14, percent: 70 },
        { id: '2', title: 'Нет, давай чилл', votes: 6, percent: 30 }
      ],
      totalVotes: 20,
      status: 'active',
      endsAt: ends
    });
    showToast('POLL STARTED');

    // Auto-progress at 5s to show live voting animation
    testPollAutoTimer = setTimeout(() => {
      if (testPollState === 1) sendTestPoll();
    }, 5000);

  } else if (testPollState === 2) {
    sendNotify({
      type: 'poll',
      action: 'progress',
      id: 'test_poll_1',
      title: 'Играем сегодня в хоррор?',
      choices: [
        { id: '1', title: 'Да, обязательно!', votes: 32, percent: 80 },
        { id: '2', title: 'Нет, давай чилл', votes: 8, percent: 20 }
      ],
      totalVotes: 40,
      status: 'active',
      endsAt: new Date(Date.now() + 7000).toISOString()
    });
    showToast('POLL UPDATED');
  } else {
    sendNotify({
      type: 'poll',
      action: 'end',
      id: 'test_poll_1',
      title: 'Играем сегодня в хоррор?',
      choices: [
        { id: '1', title: 'Да, обязательно!', votes: 45, percent: 82 },
        { id: '2', title: 'Нет, давай чилл', votes: 10, percent: 18 }
      ],
      totalVotes: 55,
      status: 'completed'
    });
    showToast('POLL ENDED');
  }
}

let testPredState = 0;
let testPredAutoTimer = null;
function sendTestPrediction() {
  testPredState = (testPredState + 1) % 3;
  if (testPredAutoTimer) { clearTimeout(testPredAutoTimer); testPredAutoTimer = null; }

  if (testPredState === 1) {
    sendNotify({
      type: 'prediction',
      action: 'begin',
      id: 'test_pred_1',
      title: 'Выиграем следующую катку?',
      status: 'ACTIVE',
      outcomes: [
        { id: '1', title: 'Победа', color: 'blue', points: 34200, percent: 65, users: 48 },
        { id: '2', title: 'Поражение', color: 'pink', points: 18400, percent: 35, users: 24 }
      ],
      totalPoints: 52600
    });
    showToast('PRED STARTED');

    // Auto-progress test simulation so it doesn't stay stuck forever if clicked once
    testPredAutoTimer = setTimeout(() => {
      if (testPredState === 1) {
        sendTestPrediction(); // advances to lock
        testPredAutoTimer = setTimeout(() => {
          if (testPredState === 2) sendTestPrediction(); // advances to resolved/end
        }, 5000);
      }
    }, 6000);

  } else if (testPredState === 2) {
    sendNotify({
      type: 'prediction',
      action: 'lock',
      id: 'test_pred_1',
      title: 'Выиграем следующую катку?',
      status: 'LOCKED',
      outcomes: [
        { id: '1', title: 'Победа', color: 'blue', points: 51200, percent: 68, users: 70 },
        { id: '2', title: 'Поражение', color: 'pink', points: 24100, percent: 32, users: 35 }
      ],
      totalPoints: 75300
    });
    showToast('PRED LOCKED');
  } else {
    if (testPredAutoTimer) { clearTimeout(testPredAutoTimer); testPredAutoTimer = null; }
    sendNotify({
      type: 'prediction',
      action: 'end',
      id: 'test_pred_1',
      title: 'Выиграем следующую катку?',
      status: 'RESOLVED',
      winningOutcomeId: '1',
      outcomes: [
        { id: '1', title: 'Победа', color: 'blue', points: 51200, percent: 68, users: 70, isWinner: true },
        { id: '2', title: 'Поражение', color: 'pink', points: 24100, percent: 32, users: 35 }
      ],
      totalPoints: 75300
    });
    showToast('PRED RESOLVED');
  }
}

function sendTestReward() {
  sendNotify({
    type: 'chat',
    subtype: 'reward',
    user: 'LoyalViewer',
    rewardTitle: 'Попить воды',
    rewardCost: 350,
    text: 'Держи водный баланс на стриме!'
  });
  showToast('REWARD SENT');
}

function sendTestTTS() {
  sendNotify({
    type: 'tts_test',
    user: 'Tester',
    text: 'Привет, стрим! Проверка озвучки сообщений.'
  });
  showToast('TTS SENT');
}

let currentStreamStats = null;

function formatUptime(startedAt) {
  if (!startedAt) return '00:00:00';
  const startMs = Date.parse(startedAt);
  if (isNaN(startMs)) return '00:00:00';
  const diffSec = Math.max(0, Math.floor((Date.now() - startMs) / 1000));
  const h = String(Math.floor(diffSec / 3600)).padStart(2, '0');
  const m = String(Math.floor((diffSec % 3600) / 60)).padStart(2, '0');
  const s = String(diffSec % 60).padStart(2, '0');
  return `${h}:${m}:${s}`;
}

function updateStatsDisplay() {
  const el = document.getElementById('stream-stats');
  if (!el) return;
  if (!currentStreamStats || !currentStreamStats.live) {
    el.textContent = '[ OFFLINE ]';
    el.classList.remove('is-live');
    return;
  }
  const v = currentStreamStats.viewers ?? 0;
  const c = currentStreamStats.chatters;
  const audience = (c !== null && c !== undefined) ? `${v} [${c}]` : `${v}`;
  const uptime = formatUptime(currentStreamStats.started_at);
  el.textContent = `[ LIVE // ${audience} // ${uptime} ]`;
  el.classList.add('is-live');
}

async function pollHealth() {
  try {
    const res = await fetch(`${API_BASE}/health`);
    if (res.ok) {
      const data = await res.json();
      const ovl = document.getElementById('tag-ovl');
      if (ovl) ovl.textContent = `${data.overlays ?? 0} OVL`;

      const setTag = (id, label, active) => {
        const el = document.getElementById(id);
        if (!el) return;
        el.textContent = (active ? '● ' : '○ ') + label;
        el.classList.toggle('is-off', !active);
        el.classList.toggle('is-ok', !!active);
        el.style.color = active ? '#63E6BE' : '#E5484D';
      };

      setTag('tag-tw', 'TW', data.adapters?.twitch);
      setTag('tag-chat', 'CHAT', data.adapters?.twitch_chat);
      setTag('tag-da', 'DA', data.adapters?.donationalerts);
      setTag('tag-dx', 'DX', data.adapters?.donatex);

      const cfgBtn = document.getElementById('dock-config-btn');
      const panelsBtn = document.getElementById('dock-panels-btn');
      if (cfgBtn) {
        cfgBtn.style.display = data.settings_enabled ? 'inline-block' : 'none';
      }
      if (panelsBtn) {
        panelsBtn.style.display = data.settings_enabled ? 'inline-block' : 'none';
      }

      const badge = document.getElementById('bridge-status');
      badge.textContent = '● ONLINE';
      badge.classList.remove('is-off');
      badge.classList.add('is-ok');
      badge.style.color = '#63E6BE';

      if (data.theme && document.documentElement.dataset.theme !== data.theme) {
        document.documentElement.dataset.theme = data.theme;
        if (document.body) document.body.dataset.theme = data.theme;
      }

      if (data.stream_stats !== undefined) {
        currentStreamStats = data.stream_stats;
        updateStatsDisplay();
      }
    }
  } catch (e) {
    currentStreamStats = null;
    updateStatsDisplay();
    const badge = document.getElementById('bridge-status');
    badge.textContent = '○ OFFLINE';
    badge.classList.add('is-off');
    badge.classList.remove('is-ok');
    badge.style.color = '#E5484D';
  }
}

pollHealth();
setInterval(pollHealth, 3000);
setInterval(updateStatsDisplay, 1000);
