(() => {
  const params = new URLSearchParams(location.search);
  const minutes = parseFloat(params.get('minutes')) || 10;
  const el = document.querySelector('.countdown__value');
  if (!el) return;

  let left = Math.max(0, Math.round(minutes * 60));
  let initialLeft = left;
  let isPaused = false;

  function render() {
    const m = String(Math.floor(left / 60)).padStart(2, '0');
    const s = String(left % 60).padStart(2, '0');
    el.textContent = m + ':' + s;
  }

  render();

  setInterval(() => {
    if (isPaused || left <= 0) return;
    left -= 1;
    if (left <= 0) {
      left = 0;
      el.textContent = '00:00';
      return;
    }
    render();
  }, 1000);

  const wsParam = params.get('ws');
  if (wsParam !== 'off') {
    const wsUrl = wsParam || `ws://${location.host || '127.0.0.1:8787'}/events`;
    let retryDelay = 1000;
    const connect = () => {
      const socket = new WebSocket(wsUrl);
      socket.onopen = () => { retryDelay = 1000; };
      socket.onmessage = (msg) => {
        try {
          const data = JSON.parse(msg.data);
          if (data.type === 'countdown_control') {
            if (data.action === 'set' && typeof data.minutes === 'number') {
              left = Math.max(0, Math.round(data.minutes * 60));
              initialLeft = left;
              isPaused = false;
              render();
            } else if (data.action === 'reset') {
              left = initialLeft;
              isPaused = false;
              render();
            } else if (data.action === 'pause') {
              isPaused = true;
            } else if (data.action === 'resume') {
              isPaused = false;
            } else if (data.action === 'toggle_pause') {
              isPaused = !isPaused;
            } else if (data.action === 'adjust') {
              left = Math.max(0, left + (data.deltaSeconds || 0));
              render();
            }
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
  }
})();