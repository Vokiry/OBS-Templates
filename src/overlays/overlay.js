(() => {
  // 1. Positioning logic based on ?pos= URL parameter
  const params = new URLSearchParams(location.search);
  const pos = params.get('pos');
  const overlay = document.querySelector('.overlay');
  if (overlay) {
    if (pos) {
      overlay.className = overlay.className.replace(/\boverlay--\S+/g, '').trim();
      overlay.classList.add('overlay--' + pos);
    } else if (!overlay.className.includes('overlay--')) {
      overlay.classList.add('overlay--top-left');
    }
  }

  // 2. Anti-Freeze Repaint Trigger for OBS Browser (CEF OSR)
  // On Linux with software rendering, OBS CEF destroys GPU textures when an overlay is hidden.
  // To recreate the texture when returning to the scene, Chromium MUST generate a paint event.
  let canvas = null;
  let ctx = null;
  let toggle = false;

  function ensureCanvas() {
    if (!canvas && document.body) {
      canvas = document.createElement('canvas');
      canvas.width = 1;
      canvas.height = 1;
      canvas.style.cssText = 'position:fixed;top:0;left:0;width:1px;height:1px;opacity:0.01;pointer-events:none;z-index:-999;';
      canvas.setAttribute('aria-hidden', 'true');
      document.body.appendChild(canvas);
      ctx = canvas.getContext('2d');
    }
  }

  function touchCompositor() {
    ensureCanvas();
    if (ctx) {
      toggle = !toggle;
      ctx.clearRect(0, 0, 1, 1);
      ctx.fillStyle = toggle ? 'rgba(255,255,255,0.01)' : 'rgba(0,0,0,0.01)';
      ctx.fillRect(0, 0, 1, 1);
      if (canvas) {
        canvas.style.opacity = toggle ? '0.01' : '0.02';
      }
    }
    if (document.body) {
      document.body.style.transform = toggle ? 'translateZ(0)' : 'translateZ(0.01px)';
    }
  }

  function triggerWakeup() {
    touchCompositor();
    let frame = 0;
    const burst = () => {
      touchCompositor();
      frame++;
      if (frame < 3) {
        requestAnimationFrame(burst);
      }
    };
    requestAnimationFrame(burst);
  }

  window.systemWakeup = triggerWakeup;

  // OBS Studio native callback (called directly by obs-browser C++ layer)
  function attachObsCallbacks() {
    if (window.obsstudio) {
      window.obsstudio.onVisibilityChange = function(visible) {
        if (visible) triggerWakeup();
      };
      window.obsstudio.onActiveChange = function(active) {
        if (active) triggerWakeup();
      };
    }
  }

  attachObsCallbacks();

  // In case window.obsstudio is defined asynchronously by CEF
  let _obs = window.obsstudio;
  try {
    Object.defineProperty(window, 'obsstudio', {
      configurable: true,
      enumerable: true,
      get() { return _obs; },
      set(val) {
        _obs = val;
        attachObsCallbacks();
      }
    });
  } catch (e) {}

  // Native OBS Browser events
  window.addEventListener('obsSourceVisibleChanged', (e) => {
    if (e && e.detail && e.detail.visible) {
      triggerWakeup();
    }
  });

  window.addEventListener('obsSourceActiveChanged', (e) => {
    if (e && e.detail && e.detail.active) {
      triggerWakeup();
    }
  });

  window.addEventListener('obsSceneChanged', () => {
    triggerWakeup();
  });

  // Standard web visibility events
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {
      triggerWakeup();
    }
  });

  window.addEventListener('pageshow', triggerWakeup);
  window.addEventListener('focus', triggerWakeup);

  // Keep-alive pulse (1 tick every 1.5s) prevents Chromium OSR from deep-sleeping
  setInterval(touchCompositor, 1500);

  // Initial wake-up on load
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', triggerWakeup);
  } else {
    triggerWakeup();
  }
})();
