/**
 * SYSTEM Broadcast Templates — Twitch Panel Generator & Constructor
 * Pure Canvas 2D engine, multi-format cards & banners, dynamic block builder.
 */

(() => {
  'use strict';

  const STORAGE_KEY = 'system24_twitch_panels_v2';
  let globalMode = 'card'; // 'card' or 'banner'
  let panels = [];
  let nextId = 1;

  // ──────────────────────────────────────────────
  // Standard Templates with Pre-Configured Blocks
  // ──────────────────────────────────────────────
  const TEMPLATES = {
    about: () => ({
      title: 'ABOUT',
      tag: 'INFO',
      mode: 'card',
      bannerVariant: 'standard',
      blocks: [
        { type: 'text', content: 'VOKKIRY', style: 'lead' },
        { type: 'text', content: 'streamer · developer · creative', style: 'normal' },
        { type: 'text', content: 'variety gaming · tech & software engineering', style: 'normal' },
        { type: 'text', content: 'stream starts ~19:00 MSK', style: 'dim' },
        { type: 'divider', style: 'solid' },
        { type: 'tags', tags: ['ARCH LINUX', 'PYTHON', 'NEOVIM', '1080P60'] }
      ]
    }),

    schedule: () => ({
      title: 'SCHEDULE',
      tag: 'TIME',
      mode: 'card',
      bannerVariant: 'standard',
      blocks: [
        { type: 'kv', key: 'MON', value: '—', highlight: false },
        { type: 'kv', key: 'TUE', value: '—', highlight: false },
        { type: 'kv', key: 'WED', value: '19:00 MSK', highlight: true },
        { type: 'kv', key: 'THU', value: '—', highlight: false },
        { type: 'kv', key: 'FRI', value: '19:00 MSK', highlight: true },
        { type: 'kv', key: 'SAT', value: '16:00 MSK', highlight: true },
        { type: 'kv', key: 'SUN', value: '16:00 MSK', highlight: true }
      ]
    }),

    donate: () => ({
      title: 'DONATE',
      tag: 'SUPPORT',
      mode: 'card',
      bannerVariant: 'standard',
      blocks: [
        { type: 'text', content: 'Support the broadcast', style: 'lead' },
        { type: 'text', content: 'Все донаты идут на развитие стрима и покупку железа.', style: 'normal' },
        { type: 'divider', style: 'solid' },
        { type: 'link', label: 'DonationAlerts', url: 'https://www.donationalerts.com/r/vokkiry' }
      ]
    }),

    specs: () => ({
      title: 'PC SPECS',
      tag: 'HARDWARE',
      mode: 'card',
      bannerVariant: 'standard',
      blocks: [
        { type: 'kv', key: 'CPU', value: 'AMD Ryzen 7 5800X3D', highlight: false },
        { type: 'kv', key: 'GPU', value: 'RTX 4070 Ti SUPER', highlight: false },
        { type: 'kv', key: 'RAM', value: '32 GB DDR4 3600', highlight: false },
        { type: 'kv', key: 'OS', value: 'Arch Linux', highlight: false },
        { type: 'kv', key: 'MIC', value: 'FIFINE K688', highlight: false },
        { type: 'kv', key: 'MOUSE', value: 'Logitech G PRO X Superlight', highlight: false }
      ]
    }),

    faq: () => ({
      title: 'FAQ',
      tag: 'Q&A',
      mode: 'card',
      bannerVariant: 'standard',
      blocks: [
        { type: 'qa', q: 'Сколько тебе лет и откуда ты?', a: '24 года, вещаю из РФ.' },
        { type: 'qa', q: 'Во что играешь на стримах?', a: 'Variety: соулслайки, инди, шутеры и лайвкодинг.' },
        { type: 'qa', q: 'Какой стек разработки?', a: 'Python, TypeScript, Arch Linux + Neovim.' },
        { type: 'qa', q: 'Когда следующий стрим?', a: 'Смотри панель расписания выше или анонсы в ТГ.' }
      ]
    }),

    social: () => ({
      title: 'SOCIAL',
      tag: 'LINKS',
      mode: 'card',
      bannerVariant: 'standard',
      blocks: [
        { type: 'link', label: 'Discord', url: 'https://discord.gg/vokkiry' },
        { type: 'link', label: 'Telegram', url: 'https://t.me/vokkiry' },
        { type: 'link', label: 'GitHub', url: 'https://github.com/Vokiry' },
        { type: 'link', label: 'YouTube', url: 'https://youtube.com/@vokkiry' }
      ]
    }),

    rules: () => ({
      title: 'RULES',
      tag: 'NOTICE',
      mode: 'card',
      bannerVariant: 'standard',
      blocks: [
        {
          type: 'list',
          bullet: 'num',
          items: [
            'Будьте вежливы ко всем участникам чата',
            'Без спама, флуда и несогласованного пиара',
            'Без политики, оскорблений и провокаций',
            'Слушайте модераторов и стримера',
            'Приятного просмотра!'
          ]
        }
      ]
    }),

    commands: () => ({
      title: 'COMMANDS',
      tag: 'BOT',
      mode: 'card',
      bannerVariant: 'standard',
      blocks: [
        { type: 'kv', key: '!discord', value: 'Ссылка на наш Discord сервер', highlight: true },
        { type: 'kv', key: '!specs', value: 'Характеристики компьютера', highlight: true },
        { type: 'kv', key: '!donate', value: 'Ссылка на поддержку трансляции', highlight: true },
        { type: 'kv', key: '!tg', value: 'Телеграм-канал с анонсами', highlight: true }
      ]
    }),

    custom: () => ({
      title: 'CUSTOM',
      tag: 'MODULE',
      mode: 'card',
      bannerVariant: 'standard',
      blocks: [
        { type: 'text', content: 'Custom Section Header', style: 'lead' },
        { type: 'text', content: 'Добавь любые блоки через панель ниже.', style: 'normal' }
      ]
    })
  };

  // ──────────────────────────────────────────────
  // Expose Global Testing Hooks
  // ──────────────────────────────────────────────
  window.getPanels = () => panels;
  window.panelToCanvas = renderCardToCanvas;
  window.setGlobalMode = setGlobalMode;

  // ──────────────────────────────────────────────
  // Canvas 2D Engine (Pixel-Perfect 640px @ 2x)
  // ──────────────────────────────────────────────
  function renderCardToCanvas(panel, forceMode) {
    const mode = forceMode || panel.mode || globalMode;
    const scale = 2; // 2x Retina scale
    const width = 320;
    const font = '"IBM Plex Mono", "JetBrains Mono", monospace';
    const bg = '#151C24';
    const border = 'rgba(232, 238, 242, 0.35)';
    const accent = '#63E6BE';
    const text = '#E8EEF2';
    const muted = '#7E8B96';

    let height = 80;

    if (mode === 'banner') {
      const v = panel.bannerVariant || 'standard';
      if (v === 'mini') height = 50;
      else if (v === 'hero') height = 110;
      else height = 80;
    } else {
      // Calculate dynamic card height
      height = 42; // Header space
      for (const block of panel.blocks) {
        if (block.type === 'text') {
          const lines = (block.content || '').split('\n').filter(Boolean);
          height += Math.max(1, lines.length) * 22;
        } else if (block.type === 'kv') {
          height += 24;
        } else if (block.type === 'qa') {
          height += 46;
        } else if (block.type === 'list') {
          height += Math.max(1, (block.items || []).length) * 22;
        } else if (block.type === 'tags') {
          height += 30;
        } else if (block.type === 'link') {
          height += 26;
        } else if (block.type === 'divider') {
          height += 16;
        } else if (block.type === 'progress') {
          height += 48;
        }
      }
      height += 14; // Bottom padding
    }

    const canvas = document.createElement('canvas');
    canvas.width = width * scale;
    canvas.height = height * scale;
    const ctx = canvas.getContext('2d');
    ctx.scale(scale, scale);

    // 1. Background
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, width, height);

    // 2. Outer Border
    ctx.strokeStyle = border;
    ctx.lineWidth = 1;
    ctx.strokeRect(0.5, 0.5, width - 1, height - 1);

    const title = (panel.title || 'UNTITLED').toUpperCase();
    const tag = (panel.tag || 'SYS//24').toUpperCase();

    if (mode === 'banner') {
      const v = panel.bannerVariant || 'standard';

      if (v === 'mini') {
        // Mini Banner (320 × 50px)
        ctx.fillStyle = accent;
        ctx.fillRect(1, 1, 3, height - 2);

        ctx.font = `700 14px ${font}`;
        ctx.fillStyle = accent;
        ctx.textAlign = 'left';
        ctx.fillText(`[ ${title} ]`, 14, 30);

        ctx.font = `600 10px ${font}`;
        ctx.fillStyle = muted;
        ctx.textAlign = 'right';
        ctx.fillText(tag, width - 14, 30);

      } else if (v === 'hero') {
        // Hero Banner (320 × 110px)
        ctx.fillStyle = accent;
        ctx.fillRect(1, 1, width - 2, 3);

        ctx.font = `600 10px ${font}`;
        ctx.fillStyle = muted;
        ctx.textAlign = 'left';
        ctx.fillText(`// SYSTEM24 // ${tag}`, 14, 26);

        ctx.font = `700 22px ${font}`;
        ctx.fillStyle = accent;
        ctx.fillText(`[ ${title} ]`, 14, 62);

        ctx.font = `400 11px ${font}`;
        ctx.fillStyle = text;
        ctx.fillText('CHANNEL SPECIFICATION & INFO', 14, 88);

        ctx.fillStyle = muted;
        ctx.textAlign = 'right';
        ctx.fillText('■', width - 14, 62);

        ctx.fillStyle = accent;
        ctx.fillRect(1, height - 5, 5, 4);
        ctx.fillRect(width - 6, height - 5, 5, 4);

      } else {
        // Standard Banner (320 × 80px)
        ctx.fillStyle = accent;
        ctx.fillRect(1, 1, width - 2, 2);

        ctx.font = `600 10px ${font}`;
        ctx.fillStyle = muted;
        ctx.textAlign = 'left';
        ctx.fillText(`// SYSTEM24 // ${tag}`, 14, 25);

        ctx.font = `700 19px ${font}`;
        ctx.fillStyle = accent;
        ctx.fillText(`[ ${title} ]`, 14, 53);

        ctx.font = `600 11px ${font}`;
        ctx.fillStyle = muted;
        ctx.textAlign = 'right';
        ctx.fillText(tag, width - 14, 25);
        ctx.fillText('■', width - 14, 53);

        ctx.fillStyle = accent;
        ctx.fillRect(1, height - 4, 4, 3);
        ctx.fillRect(width - 5, height - 4, 4, 3);
      }

    } else {
      // Full Card Layout
      ctx.fillStyle = 'rgba(232, 238, 242, 0.03)';
      ctx.fillRect(1, 1, width - 2, 36);

      ctx.font = `700 13px ${font}`;
      ctx.fillStyle = accent;
      ctx.textAlign = 'left';
      ctx.fillText(`[ ${title} ]`, 14, 23);

      ctx.font = `600 10px ${font}`;
      ctx.fillStyle = muted;
      ctx.textAlign = 'right';
      ctx.fillText(tag, width - 14, 23);

      ctx.strokeStyle = 'rgba(232, 238, 242, 0.12)';
      ctx.beginPath();
      ctx.moveTo(1, 37.5);
      ctx.lineTo(width - 1, 37.5);
      ctx.stroke();

      let y = 58;
      ctx.textAlign = 'left';

      for (const block of panel.blocks) {
        if (block.type === 'text') {
          const lines = (block.content || '').split('\n').filter(Boolean);
          if (lines.length === 0) lines.push('');
          for (const line of lines) {
            if (block.style === 'lead') {
              ctx.font = `700 13px ${font}`;
              ctx.fillStyle = text;
            } else if (block.style === 'dim') {
              ctx.font = `400 11px ${font}`;
              ctx.fillStyle = '#55606A';
            } else {
              ctx.font = `400 12px ${font}`;
              ctx.fillStyle = muted;
            }
            ctx.fillText(line, 14, y);
            y += 22;
          }

        } else if (block.type === 'kv') {
          ctx.font = `500 12px ${font}`;
          ctx.fillStyle = muted;
          ctx.fillText(block.key || 'KEY', 14, y);

          ctx.textAlign = 'right';
          ctx.fillStyle = block.highlight ? accent : text;
          ctx.fillText(block.value || '—', width - 14, y);
          ctx.textAlign = 'left';
          y += 24;

        } else if (block.type === 'qa') {
          // Question
          ctx.font = `700 12px ${font}`;
          ctx.fillStyle = accent;
          ctx.fillText(`Q: ${block.q || 'Вопрос?'}`, 14, y);
          y += 20;

          // Answer
          ctx.font = `400 12px ${font}`;
          ctx.fillStyle = text;
          ctx.fillText(`   ${block.a || 'Ответ...'}`, 14, y);
          y += 26;

        } else if (block.type === 'list') {
          const items = block.items || [];
          items.forEach((item, idx) => {
            let prefix = '•';
            if (block.bullet === 'arrow') prefix = '→';
            else if (block.bullet === 'num') prefix = `${String(idx + 1).padStart(2, '0')}.`;
            else if (block.bullet === 'check') prefix = '[✓]';

            ctx.font = `700 12px ${font}`;
            ctx.fillStyle = accent;
            ctx.fillText(prefix, 14, y);

            ctx.font = `400 12px ${font}`;
            ctx.fillStyle = text;
            const indent = block.bullet === 'num' ? 44 : (block.bullet === 'check' ? 42 : 32);
            ctx.fillText(item, indent, y);
            y += 22;
          });

        } else if (block.type === 'tags') {
          let curX = 14;
          const tags = block.tags || [];
          for (const t of tags) {
            ctx.font = `700 10px ${font}`;
            const tw = ctx.measureText(t).width;
            const pw = tw + 12;

            if (curX + pw > width - 14) {
              curX = 14;
              y += 24;
            }

            ctx.strokeStyle = 'rgba(99, 230, 190, 0.4)';
            ctx.strokeRect(curX + 0.5, y - 11.5, pw, 16);

            ctx.fillStyle = accent;
            ctx.fillText(t, curX + 6, y);
            curX += pw + 6;
          }
          y += 22;

        } else if (block.type === 'link') {
          ctx.font = `700 12px ${font}`;
          ctx.fillStyle = accent;
          ctx.fillText('→', 14, y);

          ctx.font = `600 12px ${font}`;
          ctx.fillStyle = text;
          ctx.fillText(block.label || 'Link', 32, y);

          if (block.url) {
            ctx.textAlign = 'right';
            ctx.font = `400 11px ${font}`;
            ctx.fillStyle = accent;
            const cleanUrl = block.url.replace(/^https?:\/\//, '').slice(0, 24);
            ctx.fillText(cleanUrl, width - 14, y);
            ctx.textAlign = 'left';
          }
          y += 26;

        } else if (block.type === 'divider') {
          ctx.strokeStyle = 'rgba(232, 238, 242, 0.12)';
          ctx.beginPath();
          ctx.moveTo(14, y - 4);
          ctx.lineTo(width - 14, y - 4);
          ctx.stroke();
          y += 14;

        } else if (block.type === 'progress') {
          const cur = parseFloat(block.current || 0);
          const tgt = Math.max(0.01, parseFloat(block.target || 100));
          const pct = Math.min(100, Math.max(0, (cur / tgt) * 100));
          const unit = block.unit || '₽';

          ctx.font = `600 11px ${font}`;
          ctx.fillStyle = muted;
          ctx.fillText((block.label || 'PROGRESS').toUpperCase(), 14, y);

          ctx.textAlign = 'right';
          ctx.fillStyle = text;
          ctx.fillText(`${cur} / ${tgt} ${unit}`, width - 14, y);
          ctx.textAlign = 'left';
          y += 18;

          // ASCII progress bar [######------] 50%
          const barW = 20;
          const filled = Math.round((pct / 100) * barW);
          const empty = Math.max(0, barW - filled);
          const ascii = `[${'#'.repeat(filled)}${'-'.repeat(empty)}]`;

          ctx.font = `700 11px ${font}`;
          ctx.fillStyle = accent;
          ctx.fillText(ascii, 14, y);

          ctx.textAlign = 'right';
          ctx.fillText(`${pct.toFixed(0)}%`, width - 14, y);
          ctx.textAlign = 'left';
          y += 26;
        }
      }
    }

    return canvas;
  }

  // ──────────────────────────────────────────────
  // Markdown Generator
  // ──────────────────────────────────────────────
  function panelToMarkdown(panel) {
    const lines = [];
    lines.push(`### ${panel.title || 'UNTITLED'}`);

    for (const block of panel.blocks) {
      if (block.type === 'text') {
        if (block.style === 'lead') lines.push(`**${block.content || ''}**`);
        else if (block.style === 'dim') lines.push(`*${block.content || ''}*`);
        else lines.push(block.content || '');

      } else if (block.type === 'kv') {
        lines.push(`* **${block.key || 'KEY'}:** ${block.value || '—'}`);

      } else if (block.type === 'qa') {
        lines.push(`**Q: ${block.q || ''}**\n> A: ${block.a || ''}`);

      } else if (block.type === 'list') {
        const items = block.items || [];
        items.forEach((it, idx) => {
          if (block.bullet === 'num') lines.push(`${idx + 1}. ${it}`);
          else if (block.bullet === 'check') lines.push(`- [x] ${it}`);
          else lines.push(`* ${it}`);
        });

      } else if (block.type === 'tags') {
        const tags = (block.tags || []).map(t => `\`${t}\``).join(' ');
        lines.push(tags);

      } else if (block.type === 'link') {
        lines.push(`[${block.label || 'Link'}](${block.url || '#'})`);

      } else if (block.type === 'divider') {
        lines.push('---');

      } else if (block.type === 'progress') {
        lines.push(`**${block.label || 'Goal'}:** ${block.current || 0} / ${block.target || 100} ${block.unit || ''}`);
      }
    }

    return lines.join('\n\n');
  }

  function generateAllMarkdown() {
    const parts = [
      '# TWITCH CHANNEL PROFILE // SYSTEM24 PANELS',
      'Generated via SYSTEM OBS Templates twitch-panels module\n'
    ];

    panels.forEach((p, idx) => {
      parts.push(`<!-- PANEL 0${idx + 1}: ${p.title} -->`);
      parts.push(panelToMarkdown(p));
      parts.push('\n---\n');
    });

    return parts.join('\n');
  }

  // ──────────────────────────────────────────────
  // State & LocalStorage Management
  // ──────────────────────────────────────────────
  function saveState() {
    try {
      const serialized = JSON.stringify({ globalMode, panels, nextId });
      localStorage.setItem(STORAGE_KEY, serialized);
    } catch (e) {}
  }

  function loadState() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed.panels) && parsed.panels.length > 0) {
          panels = parsed.panels;
          nextId = parsed.nextId || (panels.length + 1);
          if (parsed.globalMode) globalMode = parsed.globalMode;
          return true;
        }
      }
    } catch (e) {}
    return false;
  }

  // ──────────────────────────────────────────────
  // Global Actions
  // ──────────────────────────────────────────────
  function setGlobalMode(mode) {
    globalMode = mode;
    document.getElementById('global-mode-card').className = mode === 'card' ? 'toolbar__btn toolbar__btn--accent' : 'toolbar__btn';
    document.getElementById('global-mode-banner').className = mode === 'banner' ? 'toolbar__btn toolbar__btn--accent' : 'toolbar__btn';
    renderAll();
    saveState();
  }

  window.addPanel = function(type) {
    const factory = TEMPLATES[type];
    if (!factory) return;
    const data = factory();
    data.id = nextId++;
    panels.push(data);
    renderAll();
    saveState();
    showToast(`+ Added ${data.title} panel`);
  };

  window.removePanel = function(id) {
    panels = panels.filter(p => p.id !== id);
    renderAll();
    saveState();
    showToast('Panel removed');
  };

  window.movePanel = function(id, dir) {
    const idx = panels.findIndex(p => p.id === id);
    const newIdx = idx + dir;
    if (newIdx < 0 || newIdx >= panels.length) return;
    [panels[idx], panels[newIdx]] = [panels[newIdx], panels[idx]];
    renderAll();
    saveState();
  };

  window.updatePanelMeta = function(id, field, value) {
    const panel = panels.find(p => p.id === id);
    if (!panel) return;
    panel[field] = value;
    renderPreview(panel);
    saveState();
  };

  window.togglePanelMode = function(id) {
    const panel = panels.find(p => p.id === id);
    if (!panel) return;
    const cur = panel.mode || globalMode;
    panel.mode = cur === 'card' ? 'banner' : 'card';
    renderAll();
    saveState();
  };

  // ──────────────────────────────────────────────
  // Block Item Manipulation
  // ──────────────────────────────────────────────
  window.addBlock = function(panelId, blockType) {
    const panel = panels.find(p => p.id === panelId);
    if (!panel) return;

    let newBlock = { type: blockType };
    if (blockType === 'text') newBlock = { type: 'text', content: 'New text content', style: 'normal' };
    else if (blockType === 'kv') newBlock = { type: 'kv', key: 'KEY', value: 'Value', highlight: false };
    else if (blockType === 'qa') newBlock = { type: 'qa', q: 'Новый вопрос?', a: 'Ответ на вопрос...' };
    else if (blockType === 'list') newBlock = { type: 'list', bullet: 'num', items: ['Пункт списка 1', 'Пункт списка 2'] };
    else if (blockType === 'tags') newBlock = { type: 'tags', tags: ['TAG1', 'TAG2'] };
    else if (blockType === 'link') newBlock = { type: 'link', label: 'Ссылка', url: 'https://' };
    else if (blockType === 'divider') newBlock = { type: 'divider', style: 'solid' };
    else if (blockType === 'progress') newBlock = { type: 'progress', label: 'Сбор', current: 500, target: 5000, unit: '₽' };

    panel.blocks.push(newBlock);
    renderAll();
    saveState();
    showToast(`+ Added ${blockType.toUpperCase()} block`);
  };

  window.removeBlock = function(panelId, blockIdx) {
    const panel = panels.find(p => p.id === panelId);
    if (!panel) return;
    panel.blocks.splice(blockIdx, 1);
    renderAll();
    saveState();
  };

  window.moveBlock = function(panelId, blockIdx, dir) {
    const panel = panels.find(p => p.id === panelId);
    if (!panel) return;
    const newIdx = blockIdx + dir;
    if (newIdx < 0 || newIdx >= panel.blocks.length) return;
    [panel.blocks[blockIdx], panel.blocks[newIdx]] = [panel.blocks[newIdx], panel.blocks[blockIdx]];
    renderAll();
    saveState();
  };

  window.updateBlockProp = function(panelId, blockIdx, prop, value) {
    const panel = panels.find(p => p.id === panelId);
    if (!panel || !panel.blocks[blockIdx]) return;
    panel.blocks[blockIdx][prop] = value;
    renderPreview(panel);
    saveState();
  };

  // ──────────────────────────────────────────────
  // Markdown Actions
  // ──────────────────────────────────────────────
  window.copySingleMarkdown = function(panelId) {
    const panel = panels.find(p => p.id === panelId);
    if (!panel) return;
    const md = panelToMarkdown(panel);
    navigator.clipboard.writeText(md).then(() => {
      showToast(`✓ Copied Markdown: ${panel.title}`);
    }).catch(() => showToast('✗ Clipboard error'));
  };

  window.openMarkdownModal = function() {
    const modal = document.getElementById('markdown-modal');
    const textarea = document.getElementById('markdown-bundle-text');
    textarea.value = generateAllMarkdown();
    modal.classList.add('is-active');
  };

  window.closeMarkdownModal = function() {
    document.getElementById('markdown-modal').classList.remove('is-active');
  };

  window.copyMarkdownBundle = function() {
    const textarea = document.getElementById('markdown-bundle-text');
    navigator.clipboard.writeText(textarea.value).then(() => {
      showToast('✓ All Markdown copied to clipboard!');
    }).catch(() => showToast('✗ Clipboard error'));
  };

  window.downloadMarkdownFile = function() {
    const md = generateAllMarkdown();
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
    downloadBlob(blob, 'twitch-channel-panels.md');
    showToast('✓ Saved twitch-channel-panels.md');
  };

  // ──────────────────────────────────────────────
  // JSON Import / Export
  // ──────────────────────────────────────────────
  window.exportConfigJson = function() {
    const data = { version: '2.0', globalMode, panels };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    downloadBlob(blob, 'system24-twitch-panels-config.json');
    showToast('✓ Exported panels config JSON');
  };

  window.importConfigJson = function(e) {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        const parsed = JSON.parse(ev.target.result);
        if (Array.isArray(parsed.panels)) {
          panels = parsed.panels;
          nextId = panels.reduce((max, p) => Math.max(max, p.id || 0), 0) + 1;
          if (parsed.globalMode) globalMode = parsed.globalMode;
          renderAll();
          saveState();
          showToast(`✓ Imported ${panels.length} panels from JSON!`);
        }
      } catch (err) {
        showToast('✗ Invalid JSON config file');
      }
    };
    reader.readAsText(file);
    e.target.value = '';
  };

  window.resetToDefaults = function() {
    panels = [];
    nextId = 1;
    const order = ['about', 'schedule', 'donate', 'specs', 'faq', 'social', 'rules', 'commands'];
    order.forEach(t => {
      const item = TEMPLATES[t]();
      item.id = nextId++;
      panels.push(item);
    });
    renderAll();
    saveState();
    showToast('✓ Restored all standard templates');
  };

  // ──────────────────────────────────────────────
  // PNG Download
  // ──────────────────────────────────────────────
  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  window.downloadPanel = function(id) {
    const panel = panels.find(p => p.id === id);
    if (!panel) return;
    const canvas = renderCardToCanvas(panel);
    const mode = panel.mode || globalMode;
    const slug = (panel.title || 'panel').toLowerCase().replace(/[^a-z0-9]+/g, '-');
    const filename = `twitch-panel-${slug}-${mode}.png`;

    canvas.toBlob(blob => {
      if (!blob) {
        showToast('✗ Export error');
        return;
      }
      downloadBlob(blob, filename);
      showToast(`✓ Downloaded ${filename}`);
    }, 'image/png');
  };

  window.downloadAll = async function() {
    if (panels.length === 0) return;
    for (let i = 0; i < panels.length; i++) {
      const panel = panels[i];
      const canvas = renderCardToCanvas(panel);
      const mode = panel.mode || globalMode;
      const slug = (panel.title || 'panel').toLowerCase().replace(/[^a-z0-9]+/g, '-');
      const filename = `twitch-panel-${String(i + 1).padStart(2, '0')}-${slug}-${mode}.png`;

      await new Promise(resolve => {
        canvas.toBlob(blob => {
          if (blob) downloadBlob(blob, filename);
          resolve();
        }, 'image/png');
      });
      await new Promise(r => setTimeout(r, 220));
    }
    showToast(`✓ Downloaded all ${panels.length} PNGs!`);
  };

  // ──────────────────────────────────────────────
  // Rendering Workflow
  // ──────────────────────────────────────────────
  function renderAll() {
    const editorList = document.getElementById('editor-list');
    const previewList = document.getElementById('preview-list');
    editorList.innerHTML = '';
    previewList.innerHTML = '';

    document.getElementById('dock-panel-count').textContent = panels.length;

    if (panels.length === 0) {
      editorList.innerHTML = `<div style="color:#7E8B96; font-size:12px; padding:32px 0;">
        No panels configured. Click one of the buttons above to add a panel or restore standard templates.
      </div>`;
    }

    panels.forEach(panel => {
      editorList.appendChild(createPanelEditor(panel));

      const previewContainer = document.createElement('div');
      previewContainer.className = 'panel-preview';
      previewContainer.id = `preview-${panel.id}`;
      previewList.appendChild(previewContainer);

      renderPreview(panel);
    });
  }

  function renderPreview(panel) {
    const container = document.getElementById(`preview-${panel.id}`);
    if (!container) return;
    container.innerHTML = '';

    const canvas = renderCardToCanvas(panel);
    canvas.style.width = '320px';
    canvas.style.height = (canvas.height / 2) + 'px';
    canvas.style.display = 'block';
    canvas.title = `Click to download PNG: ${panel.title}`;
    canvas.style.cursor = 'pointer';
    canvas.onclick = () => window.downloadPanel(panel.id);

    container.appendChild(canvas);
  }

  function createPanelEditor(panel) {
    const div = document.createElement('div');
    div.className = 'panel-editor';
    div.id = `editor-${panel.id}`;

    const activeMode = panel.mode || globalMode;
    const isCard = activeMode === 'card';

    // Header Bar
    let html = `<div class="panel-editor__header">
      <div class="panel-editor__title-wrap">
        <span class="panel-editor__title">${esc(panel.title)}</span>
        <span style="font-size:10px; color:#7E8B96;">#${panel.id}</span>
      </div>
      <div class="panel-editor__actions">
        <button class="panel-editor__btn ${isCard ? 'panel-editor__btn--active' : ''}" onclick="togglePanelMode(${panel.id})">${isCard ? 'CARD' : 'BANNER'}</button>
        <button class="panel-editor__btn" onclick="copySingleMarkdown(${panel.id})" title="Copy Markdown for Twitch">MD ⎘</button>
        <button class="panel-editor__btn" onclick="movePanel(${panel.id}, -1)" title="Move Up">↑</button>
        <button class="panel-editor__btn" onclick="movePanel(${panel.id}, 1)" title="Move Down">↓</button>
        <button class="panel-editor__btn panel-editor__btn--download" onclick="downloadPanel(${panel.id})" title="Download PNG">↓ PNG</button>
        <button class="panel-editor__btn panel-editor__btn--danger" onclick="removePanel(${panel.id})" title="Remove">✕</button>
      </div>
    </div>`;

    // Metadata (Title, Tag)
    html += `<div class="panel-editor__meta">
      <div>
        <label class="field__label">Header Title</label>
        <input class="field__input" type="text" value="${esc(panel.title)}"
          oninput="updatePanelMeta(${panel.id}, 'title', this.value)">
      </div>
      <div>
        <label class="field__label">Tag / Category</label>
        <input class="field__input" type="text" value="${esc(panel.tag)}"
          oninput="updatePanelMeta(${panel.id}, 'tag', this.value)">
      </div>
    </div>`;

    // Banner Variant Strip (if Banner mode)
    if (!isCard) {
      const curV = panel.bannerVariant || 'standard';
      html += `<div class="panel-editor__mode-strip">
        <span class="panel-editor__mode-label">Banner Height:</span>
        <button class="panel-editor__btn ${curV === 'mini' ? 'panel-editor__btn--active' : ''}" onclick="updatePanelMeta(${panel.id}, 'bannerVariant', 'mini'); renderAll();">MINI (50px)</button>
        <button class="panel-editor__btn ${curV === 'standard' ? 'panel-editor__btn--active' : ''}" onclick="updatePanelMeta(${panel.id}, 'bannerVariant', 'standard'); renderAll();">STANDARD (80px)</button>
        <button class="panel-editor__btn ${curV === 'hero' ? 'panel-editor__btn--active' : ''}" onclick="updatePanelMeta(${panel.id}, 'bannerVariant', 'hero'); renderAll();">HERO (110px)</button>
      </div>`;
    }

    // Dynamic Blocks List
    html += `<div class="blocks-list">`;
    panel.blocks.forEach((block, bIdx) => {
      html += createBlockEditorHtml(panel.id, block, bIdx);
    });
    html += `</div>`;

    // Add Block Bar
    html += `<div class="add-block-bar">
      <span class="add-block-bar__label">+ ADD BLOCK:</span>
      <button class="add-block-bar__btn" onclick="addBlock(${panel.id}, 'text')">TEXT</button>
      <button class="add-block-bar__btn" onclick="addBlock(${panel.id}, 'kv')">KEY-VAL</button>
      <button class="add-block-bar__btn" onclick="addBlock(${panel.id}, 'qa')">Q&amp;A</button>
      <button class="add-block-bar__btn" onclick="addBlock(${panel.id}, 'list')">LIST</button>
      <button class="add-block-bar__btn" onclick="addBlock(${panel.id}, 'tags')">TAGS</button>
      <button class="add-block-bar__btn" onclick="addBlock(${panel.id}, 'link')">LINK</button>
      <button class="add-block-bar__btn" onclick="addBlock(${panel.id}, 'divider')">DIVIDER</button>
      <button class="add-block-bar__btn" onclick="addBlock(${panel.id}, 'progress')">PROGRESS</button>
    </div>`;

    div.innerHTML = html;
    return div;
  }

  function createBlockEditorHtml(panelId, block, bIdx) {
    let bHtml = `<div class="block-item">
      <div class="block-item__header">
        <span class="block-item__tag">[ ${block.type.toUpperCase()} ]</span>
        <div class="block-item__actions">
          <button class="block-item__btn" onclick="moveBlock(${panelId}, ${bIdx}, -1)" title="Move Block Up">↑</button>
          <button class="block-item__btn" onclick="moveBlock(${panelId}, ${bIdx}, 1)" title="Move Block Down">↓</button>
          <button class="block-item__btn block-item__btn--del" onclick="removeBlock(${panelId}, ${bIdx})" title="Delete Block">✕</button>
        </div>
      </div>`;

    if (block.type === 'text') {
      bHtml += `<div class="block-item__grid-2" style="margin-bottom:6px;">
        <div>
          <label class="field__label">Style</label>
          <select class="field__select" onchange="updateBlockProp(${panelId}, ${bIdx}, 'style', this.value)">
            <option value="normal" ${block.style === 'normal' ? 'selected' : ''}>Normal Text</option>
            <option value="lead" ${block.style === 'lead' ? 'selected' : ''}>Bold / Accent Header</option>
            <option value="dim" ${block.style === 'dim' ? 'selected' : ''}>Muted / Dim</option>
          </select>
        </div>
      </div>
      <textarea class="field__textarea" placeholder="Text paragraph..."
        oninput="updateBlockProp(${panelId}, ${bIdx}, 'content', this.value)">${esc(block.content || '')}</textarea>`;

    } else if (block.type === 'kv') {
      bHtml += `<div class="block-item__grid-2">
        <div>
          <label class="field__label">Key (Label)</label>
          <input class="field__input" type="text" value="${esc(block.key || '')}" placeholder="CPU / MON / COMMAND"
            oninput="updateBlockProp(${panelId}, ${bIdx}, 'key', this.value)">
        </div>
        <div>
          <label class="field__label">Value</label>
          <input class="field__input" type="text" value="${esc(block.value || '')}" placeholder="Ryzen 7 / 19:00 MSK"
            oninput="updateBlockProp(${panelId}, ${bIdx}, 'value', this.value)">
        </div>
      </div>`;

    } else if (block.type === 'qa') {
      bHtml += `<div style="margin-bottom:6px;">
        <label class="field__label">Question (Q)</label>
        <input class="field__input" type="text" value="${esc(block.q || '')}" placeholder="Вопрос..."
          oninput="updateBlockProp(${panelId}, ${bIdx}, 'q', this.value)">
      </div>
      <div>
        <label class="field__label">Answer (A)</label>
        <input class="field__input" type="text" value="${esc(block.a || '')}" placeholder="Ответ..."
          oninput="updateBlockProp(${panelId}, ${bIdx}, 'a', this.value)">
      </div>`;

    } else if (block.type === 'list') {
      const rawItems = (block.items || []).join('\n');
      bHtml += `<div class="block-item__grid-2" style="margin-bottom:6px;">
        <div>
          <label class="field__label">Bullet Type</label>
          <select class="field__select" onchange="updateBlockProp(${panelId}, ${bIdx}, 'bullet', this.value)">
            <option value="num" ${block.bullet === 'num' ? 'selected' : ''}>Numbered (01, 02)</option>
            <option value="arrow" ${block.bullet === 'arrow' ? 'selected' : ''}>Arrow (→)</option>
            <option value="dot" ${block.bullet === 'dot' ? 'selected' : ''}>Bullet (•)</option>
            <option value="check" ${block.bullet === 'check' ? 'selected' : ''}>Checkmark [✓]</option>
          </select>
        </div>
      </div>
      <div>
        <label class="field__label">Items (1 per line)</label>
        <textarea class="field__textarea" placeholder="Item 1&#10;Item 2"
          oninput="updateBlockProp(${panelId}, ${bIdx}, 'items', this.value.split('\\n').filter(Boolean))">${esc(rawItems)}</textarea>
      </div>`;

    } else if (block.type === 'tags') {
      const rawTags = (block.tags || []).join(', ');
      bHtml += `<div>
        <label class="field__label">Tags (comma-separated)</label>
        <input class="field__input" type="text" value="${esc(rawTags)}" placeholder="ARCH LINUX, PYTHON, 1080P60"
          oninput="updateBlockProp(${panelId}, ${bIdx}, 'tags', this.value.split(',').map(s => s.trim()).filter(Boolean))">
      </div>`;

    } else if (block.type === 'link') {
      bHtml += `<div class="block-item__grid-2">
        <div>
          <label class="field__label">Link Label</label>
          <input class="field__input" type="text" value="${esc(block.label || '')}" placeholder="Discord / DonationAlerts"
            oninput="updateBlockProp(${panelId}, ${bIdx}, 'label', this.value)">
        </div>
        <div>
          <label class="field__label">Target URL</label>
          <input class="field__input" type="text" value="${esc(block.url || '')}" placeholder="https://..."
            oninput="updateBlockProp(${panelId}, ${bIdx}, 'url', this.value)">
        </div>
      </div>`;

    } else if (block.type === 'divider') {
      bHtml += `<div style="font-size:10px; color:#7E8B96; padding:4px 0;">Solid TUI Separator Line (1px)</div>`;

    } else if (block.type === 'progress') {
      bHtml += `<div class="block-item__grid-2" style="margin-bottom:6px;">
        <div>
          <label class="field__label">Goal Title</label>
          <input class="field__input" type="text" value="${esc(block.label || '')}" placeholder="Сбор на микрофон"
            oninput="updateBlockProp(${panelId}, ${bIdx}, 'label', this.value)">
        </div>
        <div>
          <label class="field__label">Currency / Unit</label>
          <input class="field__input" type="text" value="${esc(block.unit || '')}" placeholder="₽ / $ / subs"
            oninput="updateBlockProp(${panelId}, ${bIdx}, 'unit', this.value)">
        </div>
      </div>
      <div class="block-item__grid-2">
        <div>
          <label class="field__label">Current Progress</label>
          <input class="field__input" type="number" value="${esc(block.current || 0)}"
            oninput="updateBlockProp(${panelId}, ${bIdx}, 'current', parseFloat(this.value) || 0)">
        </div>
        <div>
          <label class="field__label">Target Amount</label>
          <input class="field__input" type="number" value="${esc(block.target || 1000)}"
            oninput="updateBlockProp(${panelId}, ${bIdx}, 'target', parseFloat(this.value) || 1)">
        </div>
      </div>`;
    }

    bHtml += `</div>`;
    return bHtml;
  }

  // ──────────────────────────────────────────────
  // Helper Utilities
  // ──────────────────────────────────────────────
  function esc(str) {
    if (!str) return '';
    const d = document.createElement('div');
    d.textContent = String(str);
    return d.innerHTML;
  }

  function showToast(msg) {
    const el = document.getElementById('toast');
    el.textContent = msg;
    el.classList.add('is-visible');
    clearTimeout(el._timer);
    el._timer = setTimeout(() => el.classList.remove('is-visible'), 2400);
  }

  // ──────────────────────────────────────────────
  // Initialization
  // ──────────────────────────────────────────────
  const restored = loadState();
  if (!restored) {
    resetToDefaults();
  } else {
    renderAll();
  }
})();
