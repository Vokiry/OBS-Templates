const pos = new URLSearchParams(location.search).get('pos') || 'top-left';
document.querySelector('.overlay').classList.add('overlay--' + pos);