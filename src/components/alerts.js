const SPIN_FRAMES = ['|', '/', '-', '\\'];
const TYPE_INTERVAL_MS = 24;
const SPIN_INTERVAL_MS = 90;
const BAR_WIDTH = 12;
const BAR_FILLED = '#';
const BAR_EMPTY = '-';
const EXIT_FALLBACK_MS = 600;
const NEXT_DELAY_MS = 150;

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
    this.reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.queue = [];
    this.activeCount = 0;
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
    const timers = [];

    const el = document.createElement('div');
    el.className = 'alert';

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

    el.append(title, body, progress);

    el.style.opacity = '0';
    this.container.prepend(el);

    el.style.height = 'auto';
    const targetHeight = el.offsetHeight;
    el.style.height = '0px';
    void el.offsetHeight;

    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        el.style.height = targetHeight + 'px';
        el.style.opacity = '1';
      });
    });

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
    el.style.height = '0px';
    el.style.opacity = '0';
    el.addEventListener('transitionend', () => el.remove(), { once: true });
    setTimeout(() => el.remove(), EXIT_FALLBACK_MS);
    this.activeCount -= 1;
    setTimeout(() => this.next(), NEXT_DELAY_MS);
  }
}