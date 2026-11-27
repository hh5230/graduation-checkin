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
    const chip = element('span', 'badge badge-' + status, I18N.t('status.' + status));
    chip.dataset.i18n = 'status.' + status;
    return chip;
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

  const iconPaths = {
    more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5m0-8h.01"/>',
    edit: '<path d="m15 5 4 4M4 20l4-1L21 6l-4-4L4 15z"/>',
    qr: '<path d="M3 3h6v6H3zm12 0h6v6h-6zM3 15h6v6H3zm12 0h2v3h4v3h-6z"/>'
  };
  function icon(key) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    for (const [attr, value] of Object.entries({ class: 'icon', viewBox: '0 0 24 24', fill: 'none',
      stroke: 'currentColor', 'stroke-width': '1.8', 'stroke-linecap': 'round',
      'stroke-linejoin': 'round', 'aria-hidden': 'true' })) svg.setAttribute(attr, value);
    svg.innerHTML = iconPaths[key];
    return svg;
  }

  function initials(name) {
    const words = String(name || '').trim().split(/\s+/);
    return (words.length > 1 ? words[0][0] + words[words.length - 1][0] : [...words[0]].slice(0, 2).join('')).toLocaleUpperCase();
  }

  function showDetails(person) {
    const body = byId('detail-person');
    const label = element('strong', 'feature-name', person.name);
    const fields = element('dl', 'details');
    const add = (key, value) => {
      const term = element('dt', '', I18N.t(key));
      term.dataset.i18n = key;
      fields.append(term, element('dd', '', value));
    };
    add('field.code', person.participant_code);
    if (person.email) add('field.email', person.email);
    for (const [prefix, key] of [['checked_in','checkin'], ['queued','queued'], ['called','called'], ['completed','completed']]) {
      if (!(prefix + '_at' in person)) continue;
      const operator = person[prefix + '_by']?.name;
      add('field.' + key, [formatTime(person[prefix + '_at']), operator].filter(Boolean).join(' · '));
    }
    body.replaceChildren(label, badge(person.status || 'checked_in'), fields);
    byId('participant-detail').showModal();
  }

  function personRow(person, { timeField, position, actions = [], email = false } = {}) {
    const row = element('li', 'person-row');
    if (person.status === 'on_stage') row.classList.add('highlight');
    if (position) row.append(element('span', 'position', String(position).padStart(2, '0')));
    row.append(element('span', 'avatar', initials(person.name)));
    const who = element('div', 'person-who');
    who.append(element('strong', '', person.name), element('span', 'secondary',
      email ? [person.participant_code, person.email].join(' · ') : person.participant_code));
    row.append(who);
    if (timeField && person[timeField]) {
      const time = element('time', 'row-time', formatTime(person[timeField]));
      time.dateTime = person[timeField];
      row.append(time);
    }
    row.append(badge(person.status || 'checked_in'));
    const menu = element('details', 'row-menu');
    const trigger = element('summary', 'icon-button');
    trigger.setAttribute('aria-label', I18N.t('common.actions') + ' · ' + person.name);
    trigger.append(icon('more'));
    const pop = element('div', 'pop-panel');
    for (const [key, glyph, handler] of [['common.details', 'info', showDetails], ...actions]) {
      const button = element('button', 'menu-action');
      button.type = 'button';
      button.append(icon(glyph), document.createTextNode(I18N.t(key)));
      button.addEventListener('click', () => { menu.open = false; handler(person); });
      pop.append(button);
    }
    menu.append(trigger, pop);
    row.append(menu);
    return row;
  }

  document.addEventListener('click', event => {
    for (const menu of document.querySelectorAll('.row-menu[open]')) {
      if (!menu.contains(event.target)) menu.open = false;
    }
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') document.querySelectorAll('.row-menu[open]').forEach(menu => {
      menu.open = false;
      menu.querySelector('summary').focus();
    });
  });

  function personList(node, items, timeField, emptyKey, numbered = false) {
    node.replaceChildren();
    if (!items.length) node.append(element('li', 'empty', I18N.t(emptyKey)));
    items.forEach((person, index) => node.append(personRow(person, { timeField, position: numbered && index + 1 })));
  }
  window.UI = { byId, element, badge, notice, showError, errorText, initials, personList, personRow };

  const logout = byId('logout');
  if (logout) logout.addEventListener('click', async () => {
    logout.disabled = true;
    try {
      await API.post('/api/auth/logout', {});
      try {
        Object.keys(sessionStorage).filter(key =>
          key.startsWith('graduation.checkins.') || key.startsWith('graduation.notifications.'))
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
