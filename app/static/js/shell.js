(() => {
  'use strict';

  const { byId, element } = UI;
  const body = document.body;
  const drawer = byId('sidebar');
  const menu = byId('hamburger');
  const scrim = byId('scrim');
  const mobile = matchMedia('(max-width: 768px)');
  const form = byId('global-search');
  const search = form.querySelector('input');
  const searchToggle = byId('search-toggle');
  const bell = byId('bell');
  const storageKey = 'graduation.notifications.' + body.dataset.user;
  const dot = byId('bell-dot');
  let updates = [];
  try {
    const saved = JSON.parse(sessionStorage.getItem(storageKey));
    if (Array.isArray(saved?.items)) {
      updates = saved.items.slice(0, 8);
      dot.hidden = !saved.unread;
    }
  } catch (_) { /* The current page also works without session storage. */ }
  function saveUpdates() {
    try { sessionStorage.setItem(storageKey, JSON.stringify({ items: updates, unread: !dot.hidden })); }
    catch (_) { /* Keep the in-memory notifications. */ }
  }
  let stats = null;
  let statsAt;

  function setDrawer(open) {
    body.classList.toggle('drawer-open', open);
    drawer.inert = mobile.matches && !open;
    scrim.hidden = !open;
    menu.setAttribute('aria-expanded', String(open));
    if (open) byId('close-drawer').focus();
  }
  function closeDrawer() {
    setDrawer(false);
    menu.focus();
  }
  menu.addEventListener('click', () => setDrawer(true));
  byId('close-drawer').addEventListener('click', closeDrawer);
  scrim.addEventListener('click', closeDrawer);
  mobile.addEventListener('change', () => { setDrawer(false); setSearch(false); });
  setDrawer(false);

  function setSearch(open) {
    form.classList.toggle('expanded', open);
    searchToggle.setAttribute('aria-expanded', String(open));
    if (open) search.focus();
  }
  searchToggle.addEventListener('click', () => setSearch(true));
  form.addEventListener('focusout', event => {
    if (!form.contains(event.relatedTarget)) setSearch(false);
  });
  byId('shortcut').textContent = /mac|iphone|ipad/i.test(navigator.platform) ? '⌘K' : 'Ctrl K';
  document.addEventListener('keydown', event => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      if (!document.querySelector('dialog[open]')) setSearch(true);
    }
    if (event.key === 'Escape') {
      if (body.classList.contains('drawer-open')) closeDrawer();
      if (mobile.matches && form.classList.contains('expanded')) {
        setSearch(false);
        searchToggle.focus();
      }
      if (!byId('notifications').hidden) { setBell(false); bell.focus(); }
    }
    if (event.key === 'Tab' && body.classList.contains('drawer-open')) {
      const links = drawer.querySelectorAll('a, button');
      const first = links[0], last = links[links.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  });

  function setBell(open) {
    byId('notifications').hidden = !open;
    bell.setAttribute('aria-expanded', String(open));
  }
  function renderUpdates() {
    const list = byId('updates');
    list.replaceChildren();
    if (!updates.length) list.append(element('li', 'empty', I18N.t('shell.noUpdates')));
    updates.forEach(({ name, action }) => {
      const row = element('li', 'notification-row');
      row.append(element('strong', '', name), element('span', '', I18N.t('action.' + action)));
      list.append(row);
    });
  }
  bell.addEventListener('click', () => {
    setBell(byId('notifications').hidden);
    dot.hidden = true;
    saveUpdates();
  });
  document.addEventListener('click', event => {
    if (!event.target.closest('.notification')) setBell(false);
  });
  byId('account-avatar').textContent = UI.initials(body.dataset.name);

  function renderHeader() {
    const now = new Date();
    const date = byId('today');
    if (date) {
      date.dateTime = now.toISOString();
      date.textContent = new Intl.DateTimeFormat(I18N.getLang(), {
        weekday: 'short', month: 'short', day: 'numeric', year: 'numeric'
      }).format(now);
    }
    const greeting = byId('greeting');
    if (greeting) {
      const hour = now.getHours();
      const period = hour < 12 ? 'morning' : hour < 18 ? 'afternoon' : 'evening';
      greeting.textContent = I18N.t('dashboard.' + period, { name: body.dataset.name });
    }
  }
  function renderStats() {
    if (!stats) return;
    const numbers = { ...stats, checked_only: stats.checked_in - stats.waiting - stats.on_stage - stats.completed };
    document.querySelectorAll('[data-stat]').forEach(node => {
      node.textContent = numbers[node.dataset.stat].toLocaleString(I18N.getLang());
    });
    document.querySelectorAll('[data-rate]').forEach(node => {
      node.textContent = new Intl.NumberFormat(I18N.getLang(), { style: 'percent', maximumFractionDigits: 1 })
        .format(stats.total ? stats.checked_in / stats.total : 0);
    });
    const stamp = byId('stats-time');
    if (stamp) { stamp.dateTime = statsAt; stamp.textContent = formatTime(statsAt); }
  }
  const counts = Realtime.snapshot('/api/stats', data => {
    stats = data;
    statsAt = new Date().toISOString();
    renderStats();
  }, 'global-notice');
  window.addEventListener('langchange', () => { renderHeader(); renderUpdates(); renderStats(); });
  renderHeader();
  renderUpdates();
  setInterval(renderHeader, 60000);
  counts.refresh();
  Realtime.connect({
    onStats: counts.accept, onConnect: counts.refresh,
    onParticipant: ({ participant, action }) => {
      updates.unshift({ name: participant.name, action });
      updates.splice(8);
      dot.hidden = false;
      saveUpdates();
      renderUpdates();
    }
  });
})();
