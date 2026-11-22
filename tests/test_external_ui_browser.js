const { chromium } = require('playwright');
const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const root = path.resolve(__dirname, '..');
const port = 20000 + Math.floor(Math.random() * 1000);
const base = `http://127.0.0.1:${port}`;
const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'system-external-ui-test-'));
const configPath = path.join(tempDir, 'config.toml');
fs.writeFileSync(configPath, `[server]\nhost = "0.0.0.0"\nport = ${port}\n[appearance]\ntheme = "mocha-harmony"\n`);
const server = spawn(path.join(root, 'bridge/.venv/bin/python'), [
  'bridge/alerts_bridge.py', '--config', configPath, '--settings',
], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
let serverLog = '';
server.stdout.on('data', data => { serverLog += data; });
server.stderr.on('data', data => { serverLog += data; });

async function waitForServer() {
  for (let i = 0; i < 80; i++) {
    try { if ((await fetch(`${base}/health`)).ok && serverLog.includes('API key required')) return; } catch (e) {}
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`External bridge did not start:\n${serverLog}`);
}

(async () => {
  let browser;
  try {
    await waitForServer();
    const key = serverLog.match(/API key required for external access:\s*(\S+)/)?.[1];
    if (!key) throw new Error('Session key was not announced');
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext();
    await context.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (['http:', 'https:'].includes(url.protocol) && !['127.0.0.1', 'localhost'].includes(url.hostname)) {
        return route.abort();
      }
      return route.continue();
    });

    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`${base}/settings?key=${encodeURIComponent(key)}`);
    await page.waitForFunction(() => document.getElementById('appearance-theme').value === 'mocha-harmony');
    const backupHref = await page.locator('a[href*="/api/backup/export"]').getAttribute('href');
    if (!backupHref.includes('key=')) throw new Error('Backup link lost external authorization');
    await page.locator('.save-btn').click();
    await page.waitForFunction(() => document.getElementById('save-status').textContent.includes('СОХРАНЕНЫ'));

    const dockPage = await context.newPage();
    dockPage.on('pageerror', error => errors.push(error.message));
    await dockPage.goto(`${base}/dock?key=${encodeURIComponent(key)}`);
    await dockPage.locator('#btn-dnd').click();
    await dockPage.waitForFunction(() => document.getElementById('btn-dnd').textContent === 'DND: ON');
    const health = await (await context.request.get(`${base}/health`)).json();
    if (!health.dnd_active) throw new Error('External Dock command did not reach the backend');

    await page.addInitScript(() => {
      window.__players = [];
      window.YT = { Player: class {
        constructor(target, options) { this.options = options; window.__players.push(this); }
        destroy() {} playVideo() {} pauseVideo() {} stopVideo() {} unMute() {} setVolume() {}
        getCurrentTime() { return 0; } getDuration() { return 100; }
      } };
    });
    await page.goto(`${base}/src/overlays/media-request.html?key=${encodeURIComponent(key)}`);
    await page.evaluate(() => {
      window.SystemAPI.fetch('/notify', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: 'media_request', requestId: 'external', youtubeId: 'dQw4w9WgXcQ' }),
      });
    });
    await page.waitForFunction(() => window.__players.length === 1);
    await page.evaluate(() => window.__players[0].options.events.onStateChange({ data: 0 }));
    await page.waitForFunction(async () => {
      const response = await fetch('/api/media/status');
      return response.ok && (await response.json()).mode === 'local';
    });
    if (errors.length) throw new Error(errors.join('\n'));
    console.log('External Settings, backup link, Dock DND, and media completion authorization passed.');
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
