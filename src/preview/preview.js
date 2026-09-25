const STATES = {
  offline: 'SYSTEM OFFLINE',
  starting: 'STARTING SOON',
  intro: 'INTRO / NOW PLAYING',
  main: 'LIVE / MAIN',
  chatting: 'LIVE / CHAT',
  focus: 'LIVE / FOCUS',
  brb: 'PAUSED / BRB',
  ending: 'ENDING',
};

const STATE_CYCLE = ['starting', 'intro', 'main', 'chatting', 'focus', 'brb', 'ending', 'offline'];
const ALERT_DEMO = [
  { title: 'NEW SUB', body: 'username · tier 1' },
  { title: 'RESUB', body: 'username · 12 months' },
  { title: 'GIFT SUB', body: 'username × 5' },
  { title: 'RAID', body: 'username · 42 viewers' },
  { title: 'CHEER', body: 'username · 500' },
  { title: 'DONATION', body: 'username · 5.00' },
];
const FEED_POOL = [
  ['DONATE', 'username — 5.00'],
  ['SUB', 'username — tier 3'],
  ['RAID', 'username — 21 viewers'],
  ['DONATE', 'username — 12.50'],
  ['SUB', 'username — tier 1'],
];
const CHAT_POOL = [
  ['alice', 'lets goooo'],
  ['bob', 'this track slaps'],
  ['carol', 'how long until start?'],
  ['dave', 'hi from germany'],
  ['erin', 'audio sounds great today'],
];

function mountAlertLoop(container, delay) {
  const queue = new AlertQueue(container, { maxVisible: 2 });
  let index = 0;
  const fire = () => {
    const event = ALERT_DEMO[index % ALERT_DEMO.length];
    index += 1;
    queue.enqueue(event);
  };
  fire();
  setInterval(fire, delay);
}

function cycleStates(el, delay) {
  let i = STATE_CYCLE.indexOf(el.dataset.state);
  if (i < 0) i = 0;
  setInterval(() => {
    i = (i + 1) % STATE_CYCLE.length;
    const state = STATE_CYCLE[i];
    el.dataset.state = state;
    el.querySelector('.scene-indicator__value').textContent = STATES[state];
  }, delay);
}

const liveAlerts = document.getElementById('live-alerts');
if (liveAlerts && typeof AlertQueue !== 'undefined') mountAlertLoop(liveAlerts, 4800);

const liveIndicator = document.getElementById('live-indicator');
if (liveIndicator) cycleStates(liveIndicator, 3000);

const mock = document.querySelector('.mock');
const mockIndicator = mock?.querySelector('.scene-indicator');
if (mockIndicator) cycleStates(mockIndicator, 4200);

const mockAlerts = mock?.querySelector('.alerts');
if (mockAlerts && typeof AlertQueue !== 'undefined') mountAlertLoop(mockAlerts, 5200);

function retireOldest(list, oldestAtStart) {
  const oldest = oldestAtStart ? list.firstElementChild : list.lastElementChild;
  if (!oldest || oldest.classList.contains('is-exiting')) return false;
  elCollapseOut(oldest);
  return true;
}

function elCollapseOut(el) {
  el.style.height = el.offsetHeight + 'px';
  void el.offsetHeight;
  el.classList.add('is-exiting');
  requestAnimationFrame(() => {
    el.style.height = '0px';
  });
  setTimeout(() => el.remove(), 260);
}

function trimList(list, cap, oldestAtStart) {
  while (list.children.length > cap) {
    if (!retireOldest(list, oldestAtStart)) break;
  }
}

let feedIndex = 0;
setInterval(() => {
  document.querySelectorAll('.activity-feed__list').forEach((list) => {
    const [tag, text] = FEED_POOL[feedIndex % FEED_POOL.length];
    const item = document.createElement('div');
    item.className = 'activity-feed__item is-entering';
    const tagEl = document.createElement('span');
    tagEl.className = 'activity-feed__tag';
    tagEl.textContent = tag;
    const textEl = document.createElement('span');
    textEl.className = 'activity-feed__text';
    textEl.textContent = text;
    item.append(tagEl, textEl);
    list.prepend(item);
    trimList(list, 5, false);
  });
  feedIndex += 1;
}, 6400);

const liveChatBody = document.querySelector('#live-chat .chat__body');

function appendChatMessage(user, text) {
  if (!liveChatBody) return;
  const msg = document.createElement('div');
  msg.className = 'chat__msg is-entering';
  const userEl = document.createElement('span');
  userEl.className = 'chat__user';
  userEl.textContent = user;
  const textEl = document.createElement('span');
  textEl.className = 'chat__text';
  textEl.textContent = text;
  msg.append(userEl, textEl);
  liveChatBody.append(msg);
  trimList(liveChatBody, 6, true);
}

if (liveChatBody) {
  CHAT_POOL.slice(0, 3).forEach(([user, text]) => appendChatMessage(user, text));
  let chatIndex = 3;
  setInterval(() => {
    const [user, text] = CHAT_POOL[chatIndex % CHAT_POOL.length];
    chatIndex += 1;
    appendChatMessage(user, text);
  }, 3600);
}

const countdownValue = document.querySelector('#live-countdown .countdown__value');
let countdownLeft = 900;
if (countdownValue) {
  const renderCountdown = () => {
    const m = String(Math.floor(countdownLeft / 60)).padStart(2, '0');
    const s = String(countdownLeft % 60).padStart(2, '0');
    countdownValue.textContent = m + ':' + s;
  };
  renderCountdown();
  setInterval(() => {
    countdownLeft = countdownLeft > 0 ? countdownLeft - 1 : 900;
    renderCountdown();
  }, 1000);
}

let trackProgress = 21;
setInterval(() => {
  trackProgress = (trackProgress + 0.4) % 100;
  document.querySelectorAll('.now-playing__progress-bar').forEach((bar) => {
    bar.style.width = trackProgress + '%';
  });
}, 140);

// Connect live preview to WebSocket events so dock controls update preview in real time
(() => {
  const wsUrl = `ws://${location.host || '127.0.0.1:8787'}/events`;
  let retryDelay = 1000;

  const liveMediaCard = document.getElementById('live-media-card');
  const liveMediaDonor = document.getElementById('live-media-donor');
  const liveMediaMsg = document.getElementById('live-media-msg');
  const liveMediaTitle = document.getElementById('live-media-title');
  const liveYtContainer = document.getElementById('live-yt-container');

  const connect = () => {
    const socket = new WebSocket(wsUrl);
    socket.onopen = () => { retryDelay = 1000; };
    socket.onmessage = (msg) => {
      try {
        const data = JSON.parse(msg.data);

        // 1. Media Request
        if (data.type === 'media_request' && data.youtubeId && liveMediaCard) {
          liveMediaDonor.textContent = `${data.user || 'viewer'}${data.amount ? ' · ' + data.amount : ''}`;
          liveMediaTitle.textContent = data.title || 'YouTube Track';
          if (data.message) {
            liveMediaMsg.textContent = data.message;
            liveMediaMsg.style.display = 'block';
          } else {
            liveMediaMsg.style.display = 'none';
          }
          liveYtContainer.innerHTML = `
            <iframe
              src="https://www.youtube.com/embed/${encodeURIComponent(data.youtubeId)}?autoplay=1&enablejsapi=1&controls=1"
              allow="autoplay; encrypted-media"
              allowfullscreen>
            </iframe>
          `;
          liveMediaCard.classList.add('is-active');
        } else if (data.type === 'media_control' && liveMediaCard) {
          if (data.action === 'skip' || data.action === 'stop') {
            liveMediaCard.classList.remove('is-active');
            setTimeout(() => { liveYtContainer.innerHTML = ''; }, 300);
          }
        }

        // 2. Countdown Control
        else if (data.type === 'countdown_control' && countdownValue) {
          if (data.action === 'set' && typeof data.minutes === 'number') {
            countdownLeft = Math.round(data.minutes * 60);
          } else if (data.action === 'adjust') {
            countdownLeft = Math.max(0, countdownLeft + (data.deltaSeconds || 0));
          } else if (data.action === 'reset') {
            countdownLeft = 900;
          }
          const m = String(Math.floor(countdownLeft / 60)).padStart(2, '0');
          const s = String(countdownLeft % 60).padStart(2, '0');
          countdownValue.textContent = m + ':' + s;
        }

        // 3. Status Switcher
        else if (data.type === 'status' && data.state && liveIndicator) {
          const s = data.state.toLowerCase();
          liveIndicator.dataset.state = s;
          liveIndicator.querySelector('.scene-indicator__value').textContent = STATES[s] || s.toUpperCase();
        }

        // 4. Alert Broadcast
        else if (data.type === 'alert' && data.title && typeof AlertQueue !== 'undefined') {
          // Trigger alert in live simulation if AlertQueue instance exists
        }
      } catch (e) {}
    };
    socket.onclose = () => {
      setTimeout(connect, retryDelay);
      retryDelay = Math.min(retryDelay * 2, 10000);
    };
    socket.onerror = () => socket.close();
  };
  connect();
})();