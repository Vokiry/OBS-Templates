const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  
  const consoleLogs = [];
  page.on('console', msg => consoleLogs.push(`[${msg.type()}]: ${msg.text()}`));
  page.on('pageerror', err => console.error('PAGE ERROR:', err.message));

  const fileUrl = 'file://' + path.resolve(__dirname, '../src/panels/index.html');
  await page.goto(fileUrl);
  await page.waitForLoadState('networkidle');

  // 1. Verify standard templates
  const panels = await page.evaluate(() => window.getPanels());
  console.log(`Initialized with ${panels.length} standard panels:`, panels.map(p => p.title).join(', '));
  if (panels.length !== 8) {
    throw new Error(`Expected 8 standard panels, got ${panels.length}`);
  }

  // 2. Verify FAQ card exists and contains Q&A blocks
  const faqPanel = panels.find(p => p.title === 'FAQ');
  if (!faqPanel) throw new Error('FAQ panel not found!');
  const qaBlocks = faqPanel.blocks.filter(b => b.type === 'qa');
  console.log(`FAQ panel verified with ${qaBlocks.length} Q&A blocks`);
  if (qaBlocks.length !== 4) throw new Error(`Expected 4 Q&A blocks, got ${qaBlocks.length}`);

  // 3. Test Canvas export for all standard panels in Card mode
  const cardExports = await page.evaluate(async () => {
    const list = window.getPanels();
    const results = [];
    for (const p of list) {
      const c = window.panelToCanvas(p, 'card');
      const dataUrl = c.toDataURL('image/png');
      results.push({ title: p.title, w: c.width, h: c.height, bytes: dataUrl.length });
    }
    return results;
  });
  console.log('Card exports OK:');
  cardExports.forEach(r => console.log(`  ${r.title.padEnd(12)} -> ${r.w}x${r.h} (${r.bytes} bytes)`));

  // 4. Test Banner modes: Mini (50px -> 100px @ 2x), Standard (80px -> 160px @ 2x), Hero (110px -> 220px @ 2x)
  const bannerTests = await page.evaluate(async () => {
    const p = window.getPanels()[0]; // About panel
    const miniCanvas = window.panelToCanvas({ ...p, bannerVariant: 'mini' }, 'banner');
    const stdCanvas = window.panelToCanvas({ ...p, bannerVariant: 'standard' }, 'banner');
    const heroCanvas = window.panelToCanvas({ ...p, bannerVariant: 'hero' }, 'banner');
    return {
      mini: { w: miniCanvas.width, h: miniCanvas.height },
      std: { w: stdCanvas.width, h: stdCanvas.height },
      hero: { w: heroCanvas.width, h: heroCanvas.height }
    };
  });
  console.log('Banner variant heights verified:', bannerTests);
  if (bannerTests.mini.h !== 100 || bannerTests.std.h !== 160 || bannerTests.hero.h !== 220) {
    throw new Error(`Banner heights mismatch: ${JSON.stringify(bannerTests)}`);
  }

  // 5. Test adding a Custom panel and adding all block types
  await page.evaluate(() => {
    window.addPanel('custom');
    const list = window.getPanels();
    const last = list[list.length - 1];
    window.addBlock(last.id, 'text');
    window.addBlock(last.id, 'kv');
    window.addBlock(last.id, 'qa');
    window.addBlock(last.id, 'list');
    window.addBlock(last.id, 'tags');
    window.addBlock(last.id, 'link');
    window.addBlock(last.id, 'divider');
    window.addBlock(last.id, 'progress');
  });

  const updatedPanels = await page.evaluate(() => window.getPanels());
  const customPanel = updatedPanels[updatedPanels.length - 1];
  console.log(`Custom panel blocks count: ${customPanel.blocks.length}`);
  if (customPanel.blocks.length < 10) {
    throw new Error(`Expected at least 10 blocks in custom panel, got ${customPanel.blocks.length}`);
  }

  // Render canvas for the custom panel with all blocks
  const customCanvas = await page.evaluate(() => {
    const list = window.getPanels();
    const last = list[list.length - 1];
    const c = window.panelToCanvas(last, 'card');
    return { w: c.width, h: c.height, url: c.toDataURL('image/png') };
  });
  console.log(`Custom panel with all block types rendered: ${customCanvas.w}x${customCanvas.h}`);

  // Save base64 sample of custom panel
  const customB64 = customCanvas.url.replace(/^data:image\/png;base64,/, '');
  fs.writeFileSync('/tmp/sample_custom_all_blocks.png', customB64, 'base64');

  // 6. Test Markdown Modal and bundle generation
  await page.evaluate(() => window.openMarkdownModal());
  await page.waitForTimeout(100);
  const mdContent = await page.evaluate(() => document.getElementById('markdown-bundle-text').value);
  console.log(`Generated Markdown bundle length: ${mdContent.length} chars`);
  if (!mdContent.includes('### FAQ') || !mdContent.includes('### PC SPECS')) {
    throw new Error('Markdown bundle missing expected panel sections!');
  }
  await page.evaluate(() => window.closeMarkdownModal());

  // 7. Test LocalStorage Persistence
  await page.reload();
  await page.waitForLoadState('networkidle');
  const reloadedPanels = await page.evaluate(() => window.getPanels());
  console.log(`After page reload, restored ${reloadedPanels.length} panels from LocalStorage`);
  if (reloadedPanels.length !== 9) { // 8 standard + 1 custom
    throw new Error(`Expected 9 restored panels, got ${reloadedPanels.length}`);
  }

  // 8. Screenshot full constructor UI
  await page.screenshot({ path: '/tmp/constructor_full_ui.png', fullPage: true });
  console.log('Saved /tmp/constructor_full_ui.png');

  // Clean up: reset defaults
  await page.evaluate(() => window.resetToDefaults());

  await browser.close();
  console.log('ALL PLAYWRIGHT TESTS FOR CONSTRUCTOR PASSED CLEANLY (100%)!');
})();
