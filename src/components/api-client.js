/** Optional session-key support for explicitly exposed/non-loopback deployments. */
(() => {
  const params = new URLSearchParams(location.search);
  const suppliedKey = params.get('key') || '';
  let apiKey = suppliedKey;
  try {
    if (suppliedKey) sessionStorage.setItem('system_api_key', suppliedKey);
    else apiKey = sessionStorage.getItem('system_api_key') || '';
  } catch (e) {}

  if (suppliedKey) {
    params.delete('key');
    const query = params.toString();
    history.replaceState(null, '', `${location.pathname}${query ? `?${query}` : ''}${location.hash}`);
  }

  function withKey(url) {
    if (!apiKey) return url;
    const target = new URL(url, location.href);
    target.searchParams.set('key', apiKey);
    return target.toString();
  }

  window.SystemAPI = {
    key: apiKey,
    withKey,
    async fetch(input, init = {}) {
      const headers = new Headers(init.headers || {});
      if (apiKey) headers.set('Authorization', `Bearer ${apiKey}`);
      return fetch(input, { ...init, headers });
    },
  };

  if (apiKey) {
    document.querySelectorAll('a[href]').forEach(link => {
      const href = link.getAttribute('href');
      if (href && href.startsWith('/') && !href.startsWith('//')) link.href = withKey(href);
    });
  }
})();
