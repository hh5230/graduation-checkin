(() => {
  'use strict';

  function supported(value) {
    const base = String(value || '').toLowerCase().split(/[-_]/)[0];
    return ['zh', 'en'].includes(base) ? base : null;
  }

  let stored;
  try { stored = localStorage.getItem('lang'); } catch (_) { /* Storage may be disabled. */ }
  const cookie = document.cookie.match(/(?:^|;\s*)lang=([^;]*)/);
  let language = supported(stored) || supported(cookie && cookie[1]) || supported(navigator.language) || 'zh';
  let dictionary = Object.create(null);
  const cache = new Map();
  let revision = 0;

  function t(key, params = {}) {
    if (!Object.prototype.hasOwnProperty.call(dictionary, key)) return key;
    return dictionary[key].replace(/\{(\w+)\}/g, (match, name) =>
      Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : match);
  }

  function apply(root = document) {
    const attrs = [
      ['data-i18n', 'textContent'], ['data-i18n-placeholder', 'placeholder'],
      ['data-i18n-title', 'title'], ['data-i18n-alt', 'alt'], ['data-i18n-aria', 'aria-label']
    ];
    for (const [attr, target] of attrs) {
      const selector = '[' + attr + ']';
      const nodes = Array.from(root.querySelectorAll(selector));
      if (root.matches && root.matches(selector)) nodes.unshift(root);
      for (const node of nodes) {
        const key = node.getAttribute(attr);
        if (!Object.prototype.hasOwnProperty.call(dictionary, key)) continue;
        if (target === 'textContent') node.textContent = t(key);
        else node.setAttribute(target, t(key));
      }
    }
    document.documentElement.lang = language;
    document.querySelectorAll('[data-lang]').forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.lang === language));
    });
  }

  async function select(value, persist) {
    const requested = supported(value);
    if (!requested) return;
    const ticket = ++revision;
    if (!cache.has(requested)) {
      cache.set(requested, fetch('/static/i18n/' + requested + '.json', { credentials: 'same-origin' })
        .then(response => {
          if (!response.ok) throw new Error('Locale ' + response.status);
          return response.json();
        }).catch(error => { cache.delete(requested); throw error; }));
    }
    const messages = await cache.get(requested);
    if (ticket !== revision) return;
    dictionary = messages;
    language = requested;
    if (persist) {
      try { localStorage.setItem('lang', language); } catch (_) { /* The cookie still persists. */ }
      document.cookie = 'lang=' + language + '; Path=/; Max-Age=31536000; SameSite=Lax';
    }
    apply();
    document.dispatchEvent(new CustomEvent('langchange', { bubbles: true, detail: { lang: language } }));
  }

  window.I18N = { t, apply, getLang: () => language, setLang: value => select(value, true) };
  function reportLoadError() {
    const notice = document.getElementById('global-notice') || document.getElementById('display-notice');
    if (notice) {
      const fallback = language === 'en'
        ? 'Language file unavailable. Try switching the language again.'
        : '无法加载语言文件，请再次选择语言。';
      const key = 'lang.unavailable';
      notice.textContent = t(key) === key ? fallback : t(key);
      notice.dataset.tone = 'error';
      notice.dataset.localeError = 'true';
      notice.hidden = false;
    }
  }
  window.addEventListener('langchange', () => {
    document.querySelectorAll('[data-locale-error]').forEach(node => {
      node.hidden = true;
      delete node.dataset.localeError;
    });
  });
  document.querySelectorAll('[data-lang]').forEach(button => {
    button.addEventListener('click', () => I18N.setLang(button.dataset.lang).catch(reportLoadError));
  });
  select(language, false).catch(reportLoadError);
})();
