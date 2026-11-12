/**
 * SYSTEM Broadcast Templates — Web Settings & Configuration Controller
 * Handles 2-column widescreen TUI modules: Twitch Chat, EventSub, DonationAlerts,
 * DonateX, Yandex TTS (Alice), System Doctor, Backups, and live Theme Presets.
 */

const API_BASE = window.location.origin;
let configData = {};
let availableSoundFiles = [];
let currentPreviewAudio = null;
let maskedSecrets = {};

const DEFAULT_TTS_VOICES = {
  "shitova.us": "Алиса (Татьяна Шитова)",
  "jane": "Джейн",
  "oksana": "Оксана",
  "alyss": "Алисса",
  "omazh": "Омаж",
  "ermil": "Ермил",
  "zahar": "Захар",
  "kolya": "Коля",
  "kostya": "Костя",
  "valtz": "Вальц",
  "sasha": "Саша",
  "krosh": "Крош (Смешарики)",
  "robot": "Робот"
};
let ttsVoicesMap = DEFAULT_TTS_VOICES;

// Module toggles
const modules = {
  chat: true,
  twitch: true,
  da: true,
  dx: true,
  goal: true,
  tts: false
};

const THEME_PREVIEWS = {
  'mocha-teal': { base: '#11111b', surface: '#181825', accent: '#94e2d5', secondary: '#89dceb', label: 'MOCHA-TEAL' },
  'mocha-harmony': { base: '#11111b', surface: '#181825', accent: '#cba6f7', secondary: '#94e2d5', label: 'MOCHA-HARMONY' },
  'mocha-mauve': { base: '#11111b', surface: '#181825', accent: '#cba6f7', secondary: '#b4befe', label: 'MOCHA-MAUVE' },
  'mocha-sky': { base: '#11111b', surface: '#181825', accent: '#89dceb', secondary: '#74c7ec', label: 'MOCHA-SKY' },
  'classic': { base: '#0B0F14', surface: '#151C24', accent: '#63E6BE', secondary: '#38bdf8', label: 'SYSTEM-CLASSIC' }
};

function applyThemeUI(themeKey) {
  const info = THEME_PREVIEWS[themeKey] || THEME_PREVIEWS['mocha-teal'];
  document.documentElement.dataset.theme = themeKey;
  if (document.body) document.body.dataset.theme = themeKey;
  const tag = document.getElementById('theme-active-tag');
  if (tag) tag.textContent = '● ' + info.label;
  const sBase = document.getElementById('swatch-base');
  const sSurf = document.getElementById('swatch-surface');
  const sAcc = document.getElementById('swatch-accent');
  const sSec = document.getElementById('swatch-secondary');
  if (sBase) sBase.style.backgroundColor = info.base;
  if (sSurf) sSurf.style.backgroundColor = info.surface;
  if (sAcc) sAcc.style.backgroundColor = info.accent;
  if (sSec) sSec.style.backgroundColor = info.secondary;
}

function setToggleState(id, isActive) {
  const btn = document.getElementById(id);
  if (!btn) return;
  btn.textContent = isActive ? 'ON' : 'OFF';
  btn.classList.toggle('is-active', !!isActive);
}

function toggleModule(mod) {
  modules[mod] = !modules[mod];
  const map = {
    chat: 'btn-chat-toggle',
    twitch: 'btn-twitch-toggle',
    da: 'btn-da-toggle',
    dx: 'btn-dx-toggle',
    goal: 'btn-goal-toggle',
    tts: 'btn-tts-toggle'
  };
  setToggleState(map[mod], modules[mod]);
  if (mod === 'tts') {
    const modeSel = document.getElementById('tts-mode');
    if (modules.tts) {
      if (modeSel.value === 'off') modeSel.value = 'all';
    } else {
      modeSel.value = 'off';
    }
  }
}

function onTtsModeChange() {
  const modeSel = document.getElementById('tts-mode');
  modules.tts = modeSel.value !== 'off';
  setToggleState('btn-tts-toggle', modules.tts);
}

function populateTtsSelect(selectEl, selectedVal) {
  if (!selectEl) return;
  selectEl.innerHTML = '';
  for (const [id, label] of Object.entries(ttsVoicesMap)) {
    const opt = document.createElement('option');
    opt.value = id;
    opt.textContent = `${label} [${id}]`;
    if (id === selectedVal) opt.selected = true;
    selectEl.appendChild(opt);
  }
}

function addVipVoiceRow(username = '', voice = 'krosh') {
  const container = document.getElementById('vip-voices-container');
  if (!container) return;
  if (container.children.length >= 10) {
    showStatus('[ Максимум 10 закрепленных голосов ]');
    return;
  }
  const row = document.createElement('div');
  row.className = 'vip-voice-row';

  const nickInput = document.createElement('input');
  nickInput.type = 'text';
  nickInput.className = 'form-input vip-nick-input';
  nickInput.placeholder = 'Ник чаттера';
  nickInput.value = username;

  const voiceSelect = document.createElement('select');
  voiceSelect.className = 'form-select vip-voice-select';
  populateTtsSelect(voiceSelect, voice);

  const delBtn = document.createElement('button');
  delBtn.type = 'button';
  delBtn.className = 'vip-voice-del-btn';
  delBtn.textContent = 'УДАЛИТЬ';
  delBtn.onclick = () => row.remove();

  row.appendChild(nickInput);
  row.appendChild(voiceSelect);
  row.appendChild(delBtn);
  container.appendChild(row);
}

function togglePeek(inputId) {
  const el = document.getElementById(inputId);
  if (!el) return;
  const isPwd = el.type === 'password';
  el.type = isPwd ? 'text' : 'password';
  const btn = el.parentElement ? el.parentElement.querySelector('.peek-btn') : null;
  if (btn) btn.textContent = isPwd ? 'HIDE' : 'SHOW';
}

function populateSelect(selectId, files, selectedVal) {
  const el = document.getElementById(selectId);
  if (!el) return;
  el.innerHTML = '';
  files.forEach(f => {
    const opt = document.createElement('option');
    opt.value = f;
    opt.textContent = f;
    if (f === selectedVal) opt.selected = true;
    el.appendChild(opt);
  });
}

function testSound(selectId) {
  const el = document.getElementById(selectId);
  if (!el || !el.value) return;
  if (currentPreviewAudio) {
    currentPreviewAudio.pause();
    currentPreviewAudio.currentTime = 0;
  }
  currentPreviewAudio = new Audio(`../sounds/${encodeURIComponent(el.value)}`);
  currentPreviewAudio.play().catch(e => console.warn('Preview error:', e));
}

async function handleSoundUpload(input) {
  if (!input.files || input.files.length === 0) return;
  const file = input.files[0];
  const formData = new FormData();
  formData.append('file', file);

  showStatus(`Загрузка ${file.name}...`);
  try {
    const res = await fetch(`${API_BASE}/api/sounds/upload`, {
      method: 'POST',
      body: formData
    });
    const data = await res.json();
    if (res.ok && data.filename) {
      showStatus(`[ Файл ${data.filename} успешно добавлен! ]`);
      if (!availableSoundFiles.includes(data.filename)) {
        availableSoundFiles.push(data.filename);
        availableSoundFiles.sort();
      }
      // Refresh all selects
      const soundTypes = ['donate', 'sub', 'resub', 'gift', 'raid', 'cheer', 'follow', 'default'];
      soundTypes.forEach(t => {
        const sel = document.getElementById(`snd-${t}`);
        const curVal = sel ? sel.value : null;
        populateSelect(`snd-${t}`, availableSoundFiles, curVal);
      });
    } else {
      showStatus(`[ Ошибка загрузки: ${data.error || 'неизвестно'} ]`);
    }
  } catch (e) {
    showStatus('[ Ошибка сети при загрузке файла ]');
  }
  input.value = '';
}

async function connectDonationAlerts() {
  try {
    const res = await fetch(`${API_BASE}/api/da/auth-url`);
    if (res.ok) {
      const data = await res.json();
      if (data.url) {
        window.open(data.url, '_blank');
      }
    }
  } catch (e) {
    showStatus('[ Ошибка получения ссылки DonationAlerts ]');
  }
}

function showStatus(text) {
  const el = document.getElementById('save-status');
  if (!el) return;
  el.textContent = text;
  el.style.opacity = '1';
  setTimeout(() => {
    if (el.textContent === text) {
      el.style.opacity = '0';
    }
  }, 3500);
}

const TEST_ALERT_PAYLOADS = {
  donate: { type: 'alert', kind: 'donate', user: 'system_dev', amount: '500 ₽', message: 'Тестовый донат из панели настроек' },
  sub: { type: 'alert', kind: 'sub', user: 'subscriber_test', body: 'subscriber_test · tier 1' },
  resub: { type: 'alert', kind: 'resub', user: 'veteran_viewer', body: 'veteran_viewer · 12 months' },
  gift: { type: 'alert', kind: 'gift', user: 'generous_gifter', body: 'generous_gifter × 5' },
  raid: { type: 'alert', kind: 'raid', user: 'streamer_friend', body: 'streamer_friend · 84 viewers' },
  cheer: { type: 'alert', kind: 'cheer', user: 'bits_hero', body: 'bits_hero · 500 bits' },
  follow: { type: 'alert', kind: 'follow', user: 'new_follower', body: 'new_follower' }
};

let testAlertDebounce = false;

async function fireTestAlert(kind) {
  if (testAlertDebounce) return;
  const payload = TEST_ALERT_PAYLOADS[kind];
  if (!payload) return;

  testAlertDebounce = true;
  setTimeout(() => { testAlertDebounce = false; }, 800);

  const statusEl = document.getElementById('test-alert-status');
  try {
    if (statusEl) {
      statusEl.textContent = `[ ОТПРАВКА: ${kind.toUpperCase()}... ]`;
      statusEl.className = 'test-status-line is-pending';
    }
    const res = await fetch(`${API_BASE}/notify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      if (statusEl) {
        statusEl.textContent = `[ ✓ АЛЕРТ ${kind.toUpperCase()} ОТПРАВЛЕН В OBS ]`;
        statusEl.className = 'test-status-line is-success';
        setTimeout(() => {
          if (statusEl.textContent.includes('✓')) statusEl.textContent = '';
        }, 3500);
      }
    } else {
      throw new Error(`HTTP ${res.status}`);
    }
  } catch (err) {
    if (statusEl) {
      statusEl.textContent = `[ ✗ ОШИБКА ОТПРАВКИ: ${err.message} ]`;
      statusEl.className = 'test-status-line is-error';
    }
  }
}

async function testTtsVoice() {
  const textInput = document.getElementById('tts-test-input');
  const text = textInput ? textInput.value.trim() : '';
  if (!text) return;
  const voice = document.getElementById('tts-voice')?.value || 'shitova.us';
  const speed = document.getElementById('tts-speed')?.value || '1.0';
  const emotion = document.getElementById('tts-emotion')?.value || 'neutral';
  const statusEl = document.getElementById('tts-test-status');
  try {
    if (statusEl) {
      statusEl.textContent = '[ ОТПРАВКА ОЗВУЧКИ... ]';
      statusEl.className = 'test-status-line is-pending';
    }
    const res = await fetch(`${API_BASE}/notify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        type: 'tts_test',
        user: 'Streamer',
        text: text,
        voice: voice,
        speed: speed,
        emotion: emotion
      })
    });
    if (res.ok) {
      if (statusEl) {
        statusEl.textContent = `[ ✓ ОЗВУЧКА (${voice}) ОТПРАВЛЕНА В OBS ]`;
        statusEl.className = 'test-status-line is-success';
        setTimeout(() => { if (statusEl.textContent.includes('✓')) statusEl.textContent = ''; }, 3500);
      }
    } else {
      throw new Error(`HTTP ${res.status}`);
    }
  } catch (err) {
    if (statusEl) {
      statusEl.textContent = `[ ✗ ОШИБКА: ${err.message} ]`;
      statusEl.className = 'test-status-line is-error';
    }
  }
}

function copyDockUrl() {
  const url = `${API_BASE}/dock`;
  if (navigator.clipboard) {
    navigator.clipboard.writeText(url).then(() => showStatus('[ ✓ URL ДОКА СКОПИРОВАН В БУФЕР: ' + url + ' ]'));
  } else {
    prompt('Скопируйте URL дока:', url);
  }
}

async function sendTestChatMessage() {
  const input = document.getElementById('chat-test-input');
  const text = input ? input.value.trim() : '';
  if (!text) return;
  const statusEl = document.getElementById('chat-test-status');
  try {
    if (statusEl) {
      statusEl.textContent = '[ ОТПРАВКА... ]';
      statusEl.className = 'test-status-line is-pending';
    }
    const userNick = document.getElementById('chat-channel')?.value.trim() || 'Streamer';
    const res = await fetch(`${API_BASE}/notify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        type: 'chat',
        subtype: 'message',
        user: userNick,
        text: text,
        color: '#63E6BE'
      })
    });
    if (res.ok) {
      if (statusEl) {
        statusEl.textContent = '[ ✓ ОТПРАВЛЕНО В ЧАТ ]';
        statusEl.className = 'test-status-line is-success';
        setTimeout(() => { if (statusEl.textContent.includes('✓')) statusEl.textContent = ''; }, 3000);
      }
    }
  } catch (e) {
    if (statusEl) {
      statusEl.textContent = '[ ✗ ОШИБКА ОТПРАВКИ ]';
      statusEl.className = 'test-status-line is-error';
    }
  }
}

async function handleBackupRestore(input) {
  if (!input.files || input.files.length === 0) return;
  const file = input.files[0];
  if (!confirm(`Восстановить конфигурацию, звуки и сцены из бэкапа "${file.name}"?`)) {
    input.value = '';
    return;
  }
  showStatus(`Восстановление из ${file.name}...`);
  const formData = new FormData();
  formData.append('file', file);
  try {
    const res = await fetch(`${API_BASE}/api/backup/import`, {
      method: 'POST',
      body: formData
    });
    const data = await res.json();
    if (res.ok && data.ok) {
      showStatus('[ ✓ БЭКАП УСПЕШНО ВОССТАНОВЛЕН И ПРИМЕНЕН ]');
      loadConfig();
    } else {
      showStatus(`[ Ошибка восстановления: ${data.error || 'неизвестно'} ]`);
    }
  } catch (e) {
    showStatus('[ Ошибка сети при загрузке бэкапа ]');
  }
  input.value = '';
}

async function runSystemDoctor() {
  try {
    const res = await fetch(`${API_BASE}/api/doctor`);
    if (!res.ok) return;
    const d = await res.json();

    // 1. Server
    const srvEl = document.getElementById('doc-server');
    if (srvEl) {
      srvEl.textContent = `● Сервер: ${d.server?.host}:${d.server?.port} [ OK ]`;
      srvEl.className = 'doctor-badge is-ok';
    }

    // 2. Overlays
    const ovlEl = document.getElementById('doc-overlays');
    if (ovlEl) {
      const cnt = d.overlays?.count || 0;
      ovlEl.textContent = `● Оверлеи OBS: ${cnt} подключено`;
      ovlEl.className = cnt > 0 ? 'doctor-badge is-ok' : 'doctor-badge is-warn';
    }

    // 3. Twitch Chat
    const chatEl = document.getElementById('doc-chat');
    if (chatEl) {
      const tc = d.twitch_chat || {};
      if (tc.channel) {
        chatEl.textContent = `● Чат: #${tc.channel} (${tc.emotes_count} 7TV) [ OK ]`;
        chatEl.className = 'doctor-badge is-ok';
      } else {
        chatEl.textContent = '○ Чат: Не указан канал';
        chatEl.className = 'doctor-badge is-off';
      }
    }

    // 4. Twitch Events
    const twEl = document.getElementById('doc-twitch');
    if (twEl) {
      const tw = d.twitch || {};
      if (tw.authenticated) {
        twEl.textContent = '● Twitch Events: Авторизован [ OK ]';
        twEl.className = 'doctor-badge is-ok';
      } else if (tw.configured) {
        twEl.textContent = '○ Twitch Events: Требуется вход';
        twEl.className = 'doctor-badge is-warn';
      } else {
        twEl.textContent = '○ Twitch Events: Не настроен';
        twEl.className = 'doctor-badge is-off';
      }
    }

    // 5. DonationAlerts
    const daEl = document.getElementById('doc-da');
    if (daEl) {
      const da = d.donationalerts || {};
      if (da.authenticated) {
        daEl.textContent = '● DonationAlerts: Подключен [ OK ]';
        daEl.className = 'doctor-badge is-ok';
      } else if (da.configured) {
        daEl.textContent = '○ DA: Нажмите Подключить';
        daEl.className = 'doctor-badge is-warn';
      } else {
        daEl.textContent = '○ DonationAlerts: Не настроен';
        daEl.className = 'doctor-badge is-off';
      }
    }

    // 6. DonateX
    const dxEl = document.getElementById('doc-dx');
    if (dxEl) {
      const dx = d.donatex || {};
      if (dx.connected) {
        dxEl.textContent = '● DonateX: Подключен [ OK ]';
        dxEl.className = 'doctor-badge is-ok';
      } else if (dx.configured) {
        dxEl.textContent = '○ DonateX: Подключение...';
        dxEl.className = 'doctor-badge is-warn';
      } else {
        dxEl.textContent = '○ DonateX: Не настроен';
        dxEl.className = 'doctor-badge is-off';
      }
    }

    // 7. Sounds
    const sndEl = document.getElementById('doc-sounds');
    if (sndEl) {
      const snd = d.sounds || {};
      const volPct = Math.round((snd.master_volume || 0.7) * 100);
      sndEl.textContent = `● Звуки: ${snd.count} шт. [ ${volPct}% ]`;
      sndEl.className = 'doctor-badge is-ok';
    }

    // 8. TTS
    const ttsEl = document.getElementById('doc-tts');
    if (ttsEl) {
      const tts = d.tts || {};
      if (tts.mode !== 'off') {
        ttsEl.textContent = `● TTS: [ ${tts.mode.toUpperCase()} ] (${tts.voice})`;
        ttsEl.className = 'doctor-badge is-ok';
      } else {
        ttsEl.textContent = '○ TTS: Выключен';
        ttsEl.className = 'doctor-badge is-off';
      }
    }
  } catch (e) {
    console.warn('System doctor error:', e);
  }
}

async function loadConfig() {
  try {
    const res = await fetch(`${API_BASE}/api/config`);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    configData = data.config || {};
    const sounds = data.sounds || {};
    availableSoundFiles = sounds.available_files || [];
    const mapping = sounds.mapping || {};

    // 0. Appearance & Theme
    const appCfg = configData.appearance || {};
    const curTheme = appCfg.theme || 'mocha-teal';
    const themeSel = document.getElementById('appearance-theme');
    if (themeSel) {
      themeSel.value = curTheme;
    }
    applyThemeUI(curTheme);

    // 1. Chat
    const tc = configData.twitch_chat || {};
    modules.chat = tc.enabled !== false;
    setToggleState('btn-chat-toggle', modules.chat);
    document.getElementById('chat-channel').value = tc.channel || '';
    document.getElementById('chat-7tv-source').value = tc.seven_tv_source || 'direct';
    document.getElementById('chat-7tv-mirror').value = tc.seven_tv_mirror || 'https://enhanced.jeetbot.cc';
    const fadeSecVal = tc.fade_seconds !== undefined ? String(tc.fade_seconds) : '45';
    const fadeSel = document.getElementById('chat-fade-seconds');
    if (fadeSel) fadeSel.value = fadeSecVal;
    runSystemDoctor();

    // 2. Twitch Events
    const tw = configData.twitch || {};
    modules.twitch = tw.enabled !== false;
    setToggleState('btn-twitch-toggle', modules.twitch);
    document.getElementById('twitch-client-id').value = tw.client_id || '';
    document.getElementById('twitch-client-secret').value = tw.client_secret || '';
    document.getElementById('twitch-follows').checked = !!tw.include_follows;

    const twAuthStatus = document.getElementById('twitch-auth-status');
    if (data.auth?.twitch) {
      twAuthStatus.textContent = '[ АВТОРИЗОВАН ]';
      twAuthStatus.classList.add('btn-auth-ok');
    } else {
      twAuthStatus.textContent = '[ ТРЕБУЕТСЯ АВТОРИЗАЦИЯ ]';
      twAuthStatus.classList.remove('btn-auth-ok');
    }

    // 3. DonationAlerts
    const da = configData.donationalerts || {};
    modules.da = da.enabled !== false;
    setToggleState('btn-da-toggle', modules.da);
    document.getElementById('da-client-id').value = da.client_id || '';
    document.getElementById('da-client-secret').value = da.client_secret || '';
    maskedSecrets['da-client-secret'] = da.client_secret || '';
    document.getElementById('da-access-token').value = da.access_token || '';
    maskedSecrets['da-access-token'] = da.access_token || '';

    // 4. DonateX
    const dx = configData.donatex || {};
    modules.dx = dx.enabled !== false;
    setToggleState('btn-dx-toggle', modules.dx);
    document.getElementById('dx-token').value = dx.token || '';
    maskedSecrets['dx-token'] = dx.token || '';

    // 5. Goal
    const goal = configData.goal || {};
    modules.goal = goal.enabled !== false;
    setToggleState('btn-goal-toggle', modules.goal);
    document.getElementById('goal-title').value = goal.title || 'Сбор на цель';
    document.getElementById('goal-currency').value = goal.currency || 'RUB';
    document.getElementById('goal-current').value = goal.current !== undefined ? goal.current : 0;
    document.getElementById('goal-target').value = goal.target !== undefined ? goal.target : 10000;

    // 6. Sounds Mapping
    const soundTypes = ['donate', 'sub', 'resub', 'gift', 'raid', 'cheer', 'follow', 'default'];
    soundTypes.forEach(t => {
      populateSelect(`snd-${t}`, availableSoundFiles, mapping[t]);
    });
    const masterVol = typeof sounds.masterVolume === 'number' ? Math.round(sounds.masterVolume * 100) : 70;
    document.getElementById('alerts-volume').value = masterVol;
    document.getElementById('alerts-volume-val').textContent = masterVol + '%';

    // 7. TTS (Yandex Alice)
    if (data.tts_voices) {
      ttsVoicesMap = data.tts_voices;
    }
    populateTtsSelect(document.getElementById('tts-voice'), 'shitova.us');

    const tts = configData.tts || {};
    const ttsMode = tts.mode || 'off';
    modules.tts = ttsMode !== 'off';
    setToggleState('btn-tts-toggle', modules.tts);
    document.getElementById('tts-mode').value = ttsMode;
    document.getElementById('tts-reward-name').value = tts.reward_name || 'TTS';
    if (tts.voice) document.getElementById('tts-voice').value = tts.voice;
    const spVal = tts.speed ? (String(tts.speed) === '1' ? '1.0' : String(tts.speed)) : '1.1';
    document.getElementById('tts-speed').value = spVal;
    document.getElementById('tts-emotion').value = tts.emotion || 'neutral';
    const ttsVol = typeof tts.volume === 'number' ? Math.round(tts.volume * 100) : 80;
    document.getElementById('tts-volume').value = ttsVol;
    document.getElementById('tts-volume-val').textContent = ttsVol + '%';
    document.getElementById('tts-max-length').value = tts.max_length !== undefined ? tts.max_length : 200;
    const blInput = document.getElementById('tts-blacklist');
    if (blInput) {
      blInput.value = Array.isArray(tts.blacklist) ? tts.blacklist.join(', ') : '';
    }

    const vipContainer = document.getElementById('vip-voices-container');
    if (vipContainer) {
      vipContainer.innerHTML = '';
      const vip = tts.vip_voices || {};
      for (const [nick, voice] of Object.entries(vip)) {
        addVipVoiceRow(nick, voice);
      }
    }

  } catch (e) {
    showStatus('[ Ошибка загрузки конфигурации ]');
    console.error('Config load failed:', e);
  }
}

// Return the field value only if the user actually changed it from the masked version.
// If unchanged, return undefined so the server preserves the original secret.
function getSecretValue(inputId) {
  const el = document.getElementById(inputId);
  if (!el) return undefined;
  const val = el.value.trim();
  if (val === maskedSecrets[inputId]) return undefined;  // still masked — skip
  return val;
}

async function saveConfiguration() {
  showStatus('Сохранение настроек...');
  const soundTypes = ['donate', 'sub', 'resub', 'gift', 'raid', 'cheer', 'follow', 'default'];
  const soundMapping = {};
  soundTypes.forEach(t => {
    const sel = document.getElementById(`snd-${t}`);
    if (sel && sel.value) soundMapping[t] = sel.value;
  });

  const payload = {
    server: {
      host: configData.server?.host || '127.0.0.1',
      port: configData.server?.port || 8787
    },
    twitch_chat: {
      enabled: modules.chat,
      channel: document.getElementById('chat-channel').value.trim(),
      seven_tv_source: document.getElementById('chat-7tv-source').value,
      seven_tv_mirror: document.getElementById('chat-7tv-mirror').value.trim(),
      fade_seconds: parseInt(document.getElementById('chat-fade-seconds')?.value, 10) || 45
    },
    twitch: {
      enabled: modules.twitch,
      client_id: document.getElementById('twitch-client-id').value.trim(),
      include_follows: document.getElementById('twitch-follows').checked,
      redirect_url: configData.twitch?.redirect_url || 'http://localhost:3000'
    },
    donationalerts: {
      enabled: modules.da,
      client_id: document.getElementById('da-client-id').value.trim(),
    },
    donatex: {
      enabled: modules.dx,
    },
    goal: {
      enabled: modules.goal,
      title: document.getElementById('goal-title').value.trim() || 'Сбор на цель',
      currency: document.getElementById('goal-currency').value.trim() || 'RUB',
      current: parseFloat(document.getElementById('goal-current').value || 0),
      target: Math.max(0.01, parseFloat(document.getElementById('goal-target').value || 10000))
    },
    sounds: {
      mapping: soundMapping,
      masterVolume: (parseInt(document.getElementById('alerts-volume').value, 10) || 70) / 100
    },
    appearance: {
      theme: document.getElementById('appearance-theme')?.value || 'mocha-teal'
    }
  };

  // Collect VIP voices
  const vipVoices = {};
  document.querySelectorAll('#vip-voices-container .vip-voice-row').forEach(row => {
    const nick = row.querySelector('.vip-nick-input')?.value.trim();
    const voice = row.querySelector('.vip-voice-select')?.value;
    if (nick && voice) {
      vipVoices[nick] = voice;
    }
  });

  payload.tts = {
    mode: modules.tts ? document.getElementById('tts-mode').value : 'off',
    voice: document.getElementById('tts-voice').value,
    speed: document.getElementById('tts-speed').value,
    emotion: document.getElementById('tts-emotion').value,
    volume: (parseInt(document.getElementById('tts-volume').value, 10) || 80) / 100,
    max_length: parseInt(document.getElementById('tts-max-length').value, 10) || 200,
    reward_name: document.getElementById('tts-reward-name').value.trim() || 'TTS',
    vip_voices: vipVoices,
    blacklist: (document.getElementById('tts-blacklist')?.value || '').split(',').map(s => s.trim()).filter(Boolean),
  };
  if (configData.tts?.auth_token) payload.tts.auth_token = configData.tts.auth_token;
  if (configData.tts?.random_pool) payload.tts.random_pool = configData.tts.random_pool;

  // Only include secrets that were actually changed by the user
  const twSecret = getSecretValue('twitch-client-secret');
  if (twSecret !== undefined) payload.twitch.client_secret = twSecret;

  const daSecret = getSecretValue('da-client-secret');
  if (daSecret !== undefined) payload.donationalerts.client_secret = daSecret;

  const daToken = getSecretValue('da-access-token');
  if (daToken !== undefined) payload.donationalerts.access_token = daToken;

  const dxToken = getSecretValue('dx-token');
  if (dxToken !== undefined) payload.donatex.token = dxToken;

  try {
    const res = await fetch(`${API_BASE}/api/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok && data.ok) {
      showStatus('[ ✓ НАСТРОЙКИ СОХРАНЕНЫ И ПРИМЕНЕНЫ НА ЛЕТУ ]');
    } else {
      showStatus(`[ Ошибка сохранения: ${data.error || 'неизвестно'} ]`);
    }
  } catch (e) {
    showStatus('[ Ошибка сети при сохранении ]');
    console.error('Save failed:', e);
  }
}

document.getElementById('appearance-theme')?.addEventListener('change', (e) => {
  applyThemeUI(e.target.value);
});

loadConfig();
