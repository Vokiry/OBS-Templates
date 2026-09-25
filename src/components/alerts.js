const SPIN_FRAMES = ['|', '/', '-', '\\'];
const TYPE_INTERVAL_MS = 24;
const SPIN_INTERVAL_MS = 90;
const BAR_WIDTH = 12;
const BAR_FILLED = '#';
const BAR_EMPTY = '-';
const EXIT_FALLBACK_MS = 600;
const NEXT_DELAY_MS = 150;

const DEFAULT_SOUNDS = {
  donate: { file: '../sounds/donate.wav', volume: 0.8 },
  sub: { file: '../sounds/sub.wav', volume: 0.7 },
  resub: { file: '../sounds/sub.wav', volume: 0.7 },
  gift: { file: '../sounds/sub.wav', volume: 0.7 },
  raid: { file: '../sounds/raid.wav', volume: 0.9 },
  cheer: { file: '../sounds/cheer.wav', volume: 0.6 },
  follow: { file: '../sounds/follow.wav', volume: 0.5 },
  default: { file: '../sounds/default.wav', volume: 0.7 },
};

function readHoldMs() {
  const raw = getComputedStyle(document.documentElement).getPropertyValue('--alert-duration');
  const parsed = parseFloat(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 4200;
}

class AlertQueue {
  constructor(container, opts = {}) {
    this.container = container;
    this.maxVisible = opts.maxVisible ?? 3;
    this.holdMs = opts.holdMs ?? readHoldMs();
    this.sfx = opts.sfx ?? true;
    this.masterVolume = typeof opts.volume === 'number' ? Math.max(0, Math.min(1, opts.volume)) : 0.7;
    this.soundMap = { ...DEFAULT_SOUNDS, ...(opts.sounds || {}) };
    this.reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.queue = [];
    this.activeCount = 0;
    this.loadSoundConfig();
  }

  async loadSoundConfig() {
    try {
      const resp = await fetch('../sounds/sounds.json');
      if (resp.ok) {
        const data = await resp.json();
        if (typeof data.masterVolume === 'number' && this.masterVolume === 0.7) {
          this.masterVolume = data.masterVolume;
        }
        if (data.sounds) {
          this.soundMap = { ...this.soundMap, ...data.sounds };
        }
      }
    } catch (e) {}
  }

  resolveKind(event) {
    if (event.kind) return event.kind.toLowerCase();
    const t = (event.title || '').toLowerCase();
    if (t.includes('resub')) return 'resub';
    if (t.includes('gift')) return 'gift';
    if (t.includes('sub')) return 'sub';
    if (t.includes('raid')) return 'raid';
    if (t.includes('cheer') || t.includes('bit')) return 'cheer';
    if (t.includes('donat')) return 'donate';
    if (t.includes('follow')) return 'follow';
    return 'default';
  }

  playSound(kind) {
    if (!this.sfx || this.masterVolume <= 0) return;
    const soundConfig = this.soundMap[kind] || this.soundMap.default;
    if (!soundConfig || !soundConfig.file) return;
    try {
      const audio = new Audio(soundConfig.file);
      const vol = (soundConfig.volume ?? 0.7) * this.masterVolume;
      audio.volume = Math.max(0, Math.min(1, vol));
      audio.play().catch(() => {});
    } catch (e) {}
  }

  enqueue(event) {
    this.queue.push(event);
    this.next();
  }

  next() {
    if (!this.queue.length || this.activeCount >= this.maxVisible) return;
    this.show(this.queue.shift());
  }

  show(event) {
    this.activeCount += 1;
    const kind = this.resolveKind(event);
    this.playSound(kind);
    const timers = [];

    const el = document.createElement('div');
    el.className = 'alert';
    if (kind === 'donate') {
      el.classList.add('alert--donation');
    }

    const title = document.createElement('span');
    title.className = 'alert__title';
    const spinner = document.createElement('span');
    spinner.className = 'alert__spinner';
    const titleText = document.createElement('span');
    titleText.textContent = ' ';
    const cursor = document.createElement('span');
    cursor.className = 'alert__cursor';
    cursor.textContent = '_';
    title.append(spinner, titleText, cursor);

    const body = document.createElement('span');
    body.className = 'alert__body';
    body.textContent = event.body;

    const progress = document.createElement('span');
    progress.className = 'alert__progress';

    if (event.message) {
      const msgEl = document.createElement('div');
      msgEl.className = 'alert__message';
      msgEl.textContent = event.message;
      el.append(title, body, msgEl, progress);
    } else {
      el.append(title, body, progress);
    }

    // Pre-populate text to measure accurate targetHeight including progress bar and title
    titleText.textContent = ' ' + (event.title || '');
    progress.textContent = this.bar(1);

    el.style.opacity = '0';
    this.container.prepend(el);

    el.style.height = 'auto';
    const targetHeight = el.offsetHeight;
    el.style.height = '0px';
    void el.offsetHeight;

    // Reset for typewriter animation
    titleText.textContent = ' ';

    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        el.style.height = targetHeight + 'px';
        el.style.opacity = '1';
      });
    });

    // Once opened, release fixed height to auto so text is never cut off
    setTimeout(() => {
      if (el.style.height !== '0px') {
        el.style.height = 'auto';
      }
    }, 320);

    if (this.reducedMotion) {
      spinner.replaceWith(this.doneMark());
      cursor.remove();
      titleText.textContent = ' ' + event.title;
    } else {
      let frame = 0;
      let typed = 0;
      timers.push(setInterval(() => {
        frame = (frame + 1) % SPIN_FRAMES.length;
        spinner.textContent = SPIN_FRAMES[frame];
      }, SPIN_INTERVAL_MS));

      timers.push(setInterval(() => {
        typed += 1;
        titleText.textContent = ' ' + event.title.slice(0, typed);
        if (typed >= event.title.length) {
          clearInterval(timers[0]);
          clearInterval(timers[1]);
          spinner.replaceWith(this.doneMark());
          cursor.remove();
        }
      }, TYPE_INTERVAL_MS));
    }

    if (this.reducedMotion) {
      progress.textContent = this.bar(0);
    } else {
      const start = performance.now();
      timers.push(setInterval(() => {
        const left = Math.max(0, 1 - (performance.now() - start) / this.holdMs);
        progress.textContent = this.bar(left);
      }, 100));
    }

    timers.push(setTimeout(() => this.dismiss(el, timers), this.holdMs));
  }

  doneMark() {
    const mark = document.createElement('span');
    mark.className = 'alert__done';
    mark.textContent = '>';
    return mark;
  }

  bar(fractionLeft) {
    const filled = Math.round(BAR_WIDTH * fractionLeft);
    return '[' + BAR_FILLED.repeat(filled) + BAR_EMPTY.repeat(BAR_WIDTH - filled) + ']';
  }

  dismiss(el, timers) {
    timers.forEach(clearInterval);
    el.style.height = el.offsetHeight + 'px';
    void el.offsetHeight;
    requestAnimationFrame(() => {
      el.style.height = '0px';
      el.style.opacity = '0';
    });
    el.addEventListener('transitionend', () => el.remove(), { once: true });
    setTimeout(() => el.remove(), EXIT_FALLBACK_MS);
    this.activeCount -= 1;
    setTimeout(() => this.next(), NEXT_DELAY_MS);
  }
}