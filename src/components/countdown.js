(() => {
  const params = new URLSearchParams(location.search);
  const minutes = parseFloat(params.get('minutes')) || 10;
  const el = document.querySelector('.countdown__value');
  if (el) {
    let left = Math.max(0, Math.round(minutes * 60));

    function render() {
      const m = String(Math.floor(left / 60)).padStart(2, '0');
      const s = String(left % 60).padStart(2, '0');
      el.textContent = m + ':' + s;
    }

    render();
    const timer = setInterval(() => {
      left -= 1;
      if (left <= 0) {
        clearInterval(timer);
        left = 0;
        el.textContent = '00:00';
        return;
      }
      render();
    }, 1000);
  }
})();