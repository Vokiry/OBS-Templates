const pos = new URLSearchParams(location.search).get('pos') || 'top-left';
const overlay = document.querySelector('.overlay');
if (overlay) overlay.classList.add('overlay--' + pos);