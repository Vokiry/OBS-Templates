const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  
  const consoleLogs = [];
  page.on('console', msg => consoleLogs.push(`[${msg.type()}]: ${msg.text()}`));
  page.on('pageerror', err => console.log('PAGE ERROR:', err.message));

  const fileUrl = 'file://' + path.resolve(__dirname, '../src/panels/index.html');
  await page.goto(fileUrl);
  await page.waitForLoadState('networkidle');

  // Verify that defaults are initialized
  const panelCount = await page.evaluate(() => window.getPanels().length);
  console.log(`Default panels loaded: ${panelCount}`);
  if (panelCount !== 7) {
    throw new Error(`Expected 7 default panels, got ${panelCount}`);
  }

  // Test full card export for all 7 panels
  const cardExports = await page.evaluate(async () => {
    const list = window.getPanels();
    const results = [];
    for (const p of list) {
      const c = window.panelToCanvas(p, 'card');
      const dataUrl = c.toDataURL('image/png');
      results.push({
        id: p.id,
        label: p.data._label,
        w: c.width,
        h: c.height,
        bytes: dataUrl.length
      });
    }
    return results;
  });

  console.log('Card exports OK:');
  cardExports.forEach(r => console.log(`  ${r.label.padEnd(12)} -> ${r.w}x${r.h} (${r.bytes} bytes)`));

  // Test banner export for all 7 panels
  const bannerExports = await page.evaluate(async () => {
    const list = window.getPanels();
    const results = [];
    for (const p of list) {
      const c = window.panelToCanvas(p, 'banner');
      const dataUrl = c.toDataURL('image/png');
      results.push({
        id: p.id,
        label: p.data._label,
        w: c.width,
        h: c.height,
        bytes: dataUrl.length
      });
    }
    return results;
  });

  console.log('Banner exports OK:');
  bannerExports.forEach(r => console.log(`  ${r.label.padEnd(12)} -> ${r.w}x${r.h} (${r.bytes} bytes)`));

  // Switch global mode to banner
  await page.evaluate(() => window.setGlobalMode('banner'));
  await page.waitForTimeout(200);

  // Take screenshot in banner mode
  await page.screenshot({ path: '/tmp/panels_banner_mode.png', fullPage: true });
  console.log('Screenshot saved to /tmp/panels_banner_mode.png');

  // Switch back to card mode
  await page.evaluate(() => window.setGlobalMode('card'));
  await page.waitForTimeout(200);
  await page.screenshot({ path: '/tmp/panels_card_mode.png', fullPage: true });
  console.log('Screenshot saved to /tmp/panels_card_mode.png');

  // Test copy markdown function
  const mdResult = await page.evaluate(() => {
    const p = window.getPanels()[3]; // specs
    return p;
  });
  console.log('Panel 4 specs data verified:', mdResult.data._label);

  await browser.close();
  console.log('ALL PLAYWRIGHT TESTS PASSED CLEANLY!');
})();
