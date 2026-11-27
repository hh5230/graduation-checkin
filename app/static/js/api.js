(() => {
  'use strict';

  const byId = id => document.getElementById(id);

  class ApiError extends Error {
    constructor(code, serverMessage, status, details) {
      const key = 'error.' + code;
      const translated = I18N.t(key);
      super(translated === key ? serverMessage || code : translated);
      this.name = 'ApiError';
      this.code = code;
      this.status = status;
      this.details = details || {};
    }
  }

  async function request(method, path, params, body) {
    const url = new URL(path, location.origin);
    if (params) Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) url.searchParams.set(key, value);
    });
    const options = {
      method, credentials: 'same-origin',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-Lang': I18N.getLang() }
    };
    if (method !== 'GET') options.body = JSON.stringify(body || {});
    let response;
    try { response = await fetch(url, options); }
    catch (_) { throw new ApiError('NETWORK_ERROR', '', 0); }

    if (response.status === 401 && location.pathname !== '/login' && url.pathname !== '/api/auth/login') {
      location.assign('/login?next=' + encodeURIComponent(location.pathname + location.search + location.hash));
    }
    let result;
    try { result = await response.json(); }
    catch (_) { throw new ApiError('INTERNAL_ERROR', '', response.status); }
    if (response.ok && result && result.ok === true) return result.data;
    const error = (result && result.error) || {};
    throw new ApiError(error.code || 'INTERNAL_ERROR', error.message, response.status, error.details);
  }

  function formatTime(iso) {
    if (!iso) return '—';
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return '—';
    const pad = value => String(value).padStart(2, '0');
    return [date.getFullYear(), pad(date.getMonth() + 1), pad(date.getDate())].join('-') +
      ' ' + [date.getHours(), date.getMinutes(), date.getSeconds()].map(pad).join(':');
  }

  const escapes = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  const escapeHtml = value => String(value == null ? '' : value).replace(/[&<>"']/g, ch => escapes[ch]);
  window.API = {
    get: (path, params) => request('GET', path, params),
    post: (path, body) => request('POST', path, null, body),
    patch: (path, body) => request('PATCH', path, null, body)
  };
  Object.assign(window, { ApiError, formatTime, escapeHtml });

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function badge(status) {
    return element('span', 'badge badge-' + status, I18N.t('status.' + status));
  }

  const notices = new Map();
  function notice(id, tone, message) {
    const node = byId(id);
    if (!message) {
      notices.delete(id);
      node.hidden = true;
      node.textContent = '';
      return;
    }
    notices.set(id, message);
    node.dataset.tone = tone;
    node.textContent = message();
    node.hidden = false;
  }
  window.addEventListener('langchange', () => {
    notices.forEach((message, id) => { byId(id).textContent = message(); });
  });
  function errorText(error) {
    const key = 'error.' + error.code;
    const value = I18N.t(key);
    return value === key ? error.message : value;
  }
  function showError(id, error) { notice(id, 'error', () => errorText(error)); }

  // Queue and history panels share the participant identity and a local timestamp.
  function personList(node, items, timeField, emptyKey, numbered = false) {
    node.textContent = '';
    if (!items.length) {
      node.append(element('li', 'empty', I18N.t(emptyKey)));
      return;
    }
    items.forEach((person, index) => {
      const row = element('li', 'person-row');
      if (numbered) row.append(element('span', 'position', String(index + 1).padStart(2, '0')));
      const who = element('div', 'person-who');
      who.append(element('strong', '', person.name), element('span', 'mono', person.participant_code));
      const time = element('time', 'row-time', formatTime(person[timeField]));
      if (person[timeField]) time.dateTime = person[timeField];
      row.append(who, time);
      node.append(row);
    });
  }
  window.UI = { byId, element, badge, notice, showError, errorText, personList };

  const logout = byId('logout');
  if (logout) logout.addEventListener('click', async () => {
    logout.disabled = true;
    try {
      await API.post('/api/auth/logout', {});
      try {
        Object.keys(sessionStorage).filter(key => key.startsWith('graduation.checkins.'))
          .forEach(key => sessionStorage.removeItem(key));
      } catch (_) { /* Storage can be disabled. */ }
      location.assign('/login');
    } catch (error) {
      showError('global-notice', error);
      logout.disabled = false;
    }
  });

  const login = byId('login-form');
  if (login) login.addEventListener('submit', async event => {
    event.preventDefault();
    const submit = login.querySelector('button[type=submit], button:not([type])');
    if (submit.disabled) return;
    submit.disabled = true;
    notice('login-notice');
    try {
      await API.post('/api/auth/login', {
        username: login.elements.username.value.trim(), password: login.elements.password.value
      });
      const next = new URLSearchParams(location.search).get('next') || '/';
      let destination = new URL('/', location.origin);
      if (/^\/(?!\/)/.test(next) && !/[\\\u0000-\u001f\u007f]/.test(next)) {
        const candidate = new URL(next, location.origin);
        if (candidate.origin === location.origin) destination = candidate;
      }
      location.assign(destination.href);
    } catch (error) {
      showError('login-notice', error);
      submit.disabled = false;
    }
  });
})();
