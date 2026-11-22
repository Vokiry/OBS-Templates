const { chromium } = require('playwright');
const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const root = path.resolve(__dirname, '..');
const port = 19000 + Math.floor(Math.random() * 1000);
const base = `http://127.0.0.1:${port}`;
const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'system-media-test-'));
const configPath = path.join(tempDir, 'config.toml');
fs.writeFileSync(configPath, `[server]\nhost = "127.0.0.1"\nport = ${port}\n`);
const server = spawn(path.join(root, 'bridge/.venv/bin/python'), [
  'bridge/alerts_bridge.py', '--config', configPath, '--settings',
], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
let serverLog = '';
server.stdout.on('data', data => { serverLog += data; });
server.stderr.on('data', data => { serverLog += data; });

async function waitForServer() {
  for (let i = 0; i < 60; i++) {
    try {
      const response = await fetch(`${base}/health`);
      if (response.ok) return;
    } catch (e) {}
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`Bridge did not start:\n${serverLog}`);
}

(async () => {
  let browser;
  try {
    await waitForServer();
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext();
    await context.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (['http:', 'https:'].includes(url.protocol) && !['127.0.0.1', 'localhost'].includes(url.hostname)) {
        return route.abort();
      }
      return route.continue();
    });

    async function open(pathname, fakeWebSocket = false) {
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => {
        errors.push(error.message);
        console.error('Browser pageerror:', error.message);
      });
      if (fakeWebSocket) await page.addInitScript(() => {
        window.WebSocket = class {
          static OPEN = 1;
          constructor() { this.readyState = 1; window.__fakeWs = this; }
          send() {} close() {}
          addEventListener(type, callback) { if (type === 'message') this.onmessage = callback; }
        };
      });
      await page.addInitScript(() => {
        window.__players = [];
        window.YT = { Player: class {
          constructor(target, options) {
            this.options = options; this.currentTime = 0; this.duration = 100; window.__players.push(this);
          }
          destroy() {} playVideo() {} pauseVideo() {} stopVideo() {} unMute() {} setVolume() {}
          getCurrentTime() { return this.currentTime; } getDuration() { return this.duration; }
        } };
      });
      await page.goto(base + pathname, { waitUntil: 'domcontentloaded' });
      return { page, errors };
    }

    async function post(payload, pathname = '/notify') {
      const response = await context.request.post(base + pathname, {
        data: payload,
        headers: { Referer: `${base}/dock` },
      });
      if (!response.ok()) throw new Error(`${pathname}: HTTP ${response.status()} ${await response.text()}`);
    }

    let test = await open('/src/overlays/media-request.html?ws=off&yt=dQw4w9WgXcQ');
    await test.page.waitForFunction(() => window.__players.length === 1);
    if (!await test.page.locator('#media-card').evaluate(element => element.classList.contains('is-active'))) {
      throw new Error('Query media request did not open the player');
    }
    if (test.errors.length) throw new Error(test.errors.join('\n'));
    await test.page.close();

    test = await open('/src/overlays/media-request.html');
    const page = test.page;
    await post({ type: 'media_request', youtubeId: 'dQw4w9WgXcQ', title: 'FIRST TRACK', donationId: 'first' });
    await page.waitForFunction(() => window.__players.length === 1);
    await post({ type: 'media_request', youtubeId: 'jfKfPfyJRdk', title: 'SECOND TRACK', donationId: 'second' });
    await page.waitForFunction(() => document.getElementById('media-queue').textContent.includes('1'));

    // An error on track 1 schedules a delayed skip. A manual skip advances first;
    // the stale timeout must not skip track 2 when it fires three seconds later.
    await page.evaluate(() => window.__players[0].options.events.onError({ data: 100 }));
    await page.waitForTimeout(300);
    await post({}, '/api/media/skip');
    await page.waitForFunction(() => (
      window.__players.length === 2 && document.getElementById('media-track-title').textContent === 'SECOND TRACK'
    ));
    await page.waitForTimeout(3500);
    const state = await page.evaluate(() => ({
      players: window.__players.length,
      title: document.getElementById('media-track-title').textContent,
      active: document.getElementById('media-card').classList.contains('is-active'),
    }));
    if (state.players !== 2 || state.title !== 'SECOND TRACK' || !state.active) {
      throw new Error(`Stale playback callback regressed: ${JSON.stringify(state)}`);
    }
    if (test.errors.length) throw new Error(test.errors.join('\n'));

    // The same video from another donation is a distinct request. A newly attached
    // overlay must restore both the active request and the complete pending queue.
    await post({
      type: 'media_request', requestId: 'third', donationId: 'third',
      youtubeId: 'jfKfPfyJRdk', title: 'THIRD SAME VIDEO',
    });
    await page.waitForFunction(() => document.getElementById('media-queue').textContent.includes('1'));
    const reconnect = await open('/src/overlays/media-request.html');
    await reconnect.page.waitForFunction(() => window.__players.length === 1);
    const restored = await reconnect.page.evaluate(() => ({
      title: document.getElementById('media-track-title').textContent,
      queue: document.getElementById('media-queue').textContent,
    }));
    if (restored.title !== 'SECOND TRACK' || !restored.queue.includes('1')) {
      throw new Error(`Queue snapshot was not restored: ${JSON.stringify(restored)}`);
    }
    await page.close();
    await post({}, '/api/media/skip');
    await reconnect.page.waitForFunction(() => (
      window.__players.length === 2 && document.getElementById('media-track-title').textContent === 'THIRD SAME VIDEO'
    ));
    if (reconnect.errors.length) throw new Error(reconnect.errors.join('\n'));
    await reconnect.page.close();
    await post({ type: 'media_control', action: 'stop' });
    await new Promise(resolve => setTimeout(resolve, 150));

    // youtube.com -> nocookie is a single fallback, not an infinite recreation loop.
    await post({ media: { enabled: false, youtube_domain: 'youtube.com' } }, '/api/config');
    test = await open('/src/overlays/media-request.html');
    await post({ type: 'media_request', requestId: 'fallback', youtubeId: 'dQw4w9WgXcQ', title: 'FALLBACK' });
    await test.page.waitForFunction(() => window.__players.length === 1);
    await test.page.evaluate(() => window.__players[0].options.events.onError({ data: 153 }));
    await test.page.waitForFunction(() => window.__players.length === 2);
    const hosts = await test.page.evaluate(() => window.__players.map(player => player.options.host));
    if (hosts[0] !== 'https://www.youtube.com' || hosts[1] !== 'https://www.youtube-nocookie.com') {
      throw new Error(`Incorrect fallback hosts: ${JSON.stringify(hosts)}`);
    }
    await test.page.evaluate(() => window.__players[1].options.events.onError({ data: 153 }));
    await test.page.waitForTimeout(4000);
    const fallbackState = await test.page.evaluate(() => ({
      players: window.__players.length,
      active: document.getElementById('media-card').classList.contains('is-active'),
    }));
    if (fallbackState.players !== 2 || fallbackState.active) {
      throw new Error(`Fallback did not finish the failed track: ${JSON.stringify(fallbackState)}`);
    }
    await test.page.close();
    await post({ type: 'media_control', action: 'stop' });
    await new Promise(resolve => setTimeout(resolve, 150));

    // End polling must respect pause even when the playhead is inside the final second.
    test = await open('/src/overlays/media-request.html');
    await post({ type: 'media_request', requestId: 'paused', youtubeId: 'dQw4w9WgXcQ', title: 'PAUSED END' });
    await test.page.waitForFunction(() => window.__players.length === 1);
    await test.page.evaluate(() => { window.__players[0].currentTime = 99.5; });
    await post({ type: 'media_control', action: 'pause' });
    await test.page.waitForTimeout(1400);
    const pausedState = await test.page.evaluate(() => ({
      players: window.__players.length,
      active: document.getElementById('media-card').classList.contains('is-active'),
      status: document.getElementById('media-duration').textContent,
    }));
    if (pausedState.players !== 1 || !pausedState.active || pausedState.status !== 'PAUSED') {
      throw new Error(`Paused track advanced unexpectedly: ${JSON.stringify(pausedState)}`);
    }
    if (test.errors.length) throw new Error(test.errors.join('\n'));

    // A live domain setting update must affect the next track on an attached overlay.
    await post({ media: { enabled: false, youtube_domain: 'youtube-nocookie.com' } }, '/api/config');
    await post({ type: 'media_request', requestId: 'after-live-config', youtubeId: 'jfKfPfyJRdk', title: 'LIVE CONFIG' });
    await post({}, '/api/media/skip');
    await test.page.waitForFunction(() => window.__players.length === 2);
    const liveHost = await test.page.evaluate(() => window.__players[1].options.host);
    if (liveHost !== 'https://www.youtube-nocookie.com') {
      throw new Error(`Live media config was not applied: ${liveHost}`);
    }
    await test.page.close();

    // A delayed skip for A must be ignored after the overlay advanced to B.
    test = await open('/src/overlays/media-request.html', true);
    await test.page.waitForFunction(() => typeof window.__fakeWs?.onmessage === 'function');
    const emit = async payload => {
      await test.page.evaluate(data => window.__fakeWs.onmessage({ data: JSON.stringify(data) }), payload);
    };
    await emit({ type: 'media_request', requestId: 'a', youtubeId: 'dQw4w9WgXcQ', title: 'A' });
    await test.page.waitForFunction(() => window.__players.length === 1);
    await emit({ type: 'media_request', requestId: 'b', youtubeId: 'jfKfPfyJRdk', title: 'B' });
    await emit({ type: 'media_control', action: 'skip', requestId: 'a' });
    await test.page.waitForFunction(() => window.__players.length === 2);
    await emit({ type: 'media_control', action: 'skip', requestId: 'a' });
    await test.page.waitForTimeout(600);
    const staleSkipState = await test.page.evaluate(() => ({
      players: window.__players.length,
      title: document.getElementById('media-track-title').textContent,
      active: document.getElementById('media-card').classList.contains('is-active'),
    }));
    if (staleSkipState.players !== 2 || staleSkipState.title !== 'B' || !staleSkipState.active) {
      throw new Error(`Stale skip advanced the overlay: ${JSON.stringify(staleSkipState)}`);
    }
    if (test.errors.length) throw new Error(test.errors.join('\n'));
    await test.page.close();

    console.log('Media playback, FIFO, reconnect, stale timer/skip, fallback, pause, and live config tests passed.');
    await context.close();
  } finally {
    if (browser) await browser.close();
    server.kill('SIGTERM');
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
