(() => {
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
})();