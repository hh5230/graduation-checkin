(() => {
  'use strict';

  const { byId, element, badge, personAvatar, notice } = UI;
  const picker = byId('entrance-dialog');
  const custom = byId('custom-entrance');
  const searchPanel = byId('no-qr');
  const search = byId('entry-search');
  const params = new URLSearchParams(location.search);
  const recentKey = 'graduation.checkins.' + document.body.dataset.user;
  const entranceKey = 'graduation.entrance';
  let recent = [];
  let entrance = '';
  try {
    entrance = (localStorage.getItem(entranceKey) || '').trim().slice(0, 64);
    const saved = JSON.parse(sessionStorage.getItem(recentKey));
    if (Array.isArray(saved)) recent = saved.slice(0, 10);
  } catch (_) { /* Device storage is optional. */ }

  let participant = null;
  let identity = null;
  let busy = false;
  let timer;
  let searchRevision = 0;
  let matches = [];
  const scanner = Scanner.bind(lookup, { autoStart: false });

  function sync() {
    const review = Boolean(participant);
    const hold = busy || review || !entrance || picker.open || searchPanel.open;
    byId('entry-workspace').hidden = review;
    byId('confirmation').hidden = !review;
    scanner.hold(hold);
    if (!hold) scanner.startCamera();
    byId('change-entrance').disabled = search.disabled = busy;
    byId('confirm-checkin').disabled = byId('cancel-checkin').disabled = busy;
    byId('entrance-name').textContent = entrance;
    if (review) byId('entry-person').replaceChildren(UI.sizeName(element('strong', 'hero-name', participant.name)),
      element('span', 'feature-code', participant.participant_code), badge(participant.status),
      element('span', 'secondary', participant.email));
  }

  function select(person, source) {
    participant = person;
    identity = source;
    sync();
    byId('confirm-checkin').focus({ preventScroll: true });
  }
  function reset() {
    participant = identity = null;
    searchPanel.open = false;
    search.value = byId('manual-code').value = '';
    clearSearch();
    busy = false;
    sync();
    window.scrollTo(0, 0);
  }
  function openPicker() {
    custom.value = entrance;
    byId('cancel-entrance').hidden = !entrance;
    picker.showModal();
    sync();
  }
  function choose(value) {
    entrance = value;
    try { localStorage.setItem(entranceKey, entrance); } catch (_) { /* Keep it for this session. */ }
    picker.close();
  }
  picker.querySelectorAll('[data-entrance]').forEach(button =>
    button.addEventListener('click', () => choose(button.dataset.entrance)));
  picker.addEventListener('cancel', event => { if (!entrance) event.preventDefault(); });
  byId('cancel-entrance').addEventListener('click', () => picker.close());
  byId('change-entrance').addEventListener('click', openPicker);
  byId('entrance-form').addEventListener('submit', event => {
    event.preventDefault();
    const value = custom.value.trim();
    if (value) choose(value);
    else { custom.value = ''; custom.reportValidity(); }
  });

  async function lookup(source) {
    if (busy || participant || !entrance || picker.open) return false;
    busy = true;
    sync();
    try {
      const person = await API.get('/api/lookup', source);
      busy = false;
      select(person, source);
      return true;
    } catch (error) {
      await Scanner.flash('error', () => UI.errorText(error));
      reset();
      return false;
    }
  }
  byId('cancel-checkin').addEventListener('click', reset);
  byId('confirm-checkin').addEventListener('click', async () => {
    if (busy || !identity || !entrance) return;
    busy = true;
    sync();
    try {
      const person = await API.post('/api/checkin', { ...identity, entrance });
      const { id, name, participant_code, checked_in_at, status } = person;
      recent = [{ id, name, participant_code, checked_in_at, status }, ...recent.filter(p => p.id !== id)].slice(0, 10);
      try { sessionStorage.setItem(recentKey, JSON.stringify(recent)); } catch (_) { /* In-memory history remains available. */ }
      renderRecent();
      await Scanner.flash('success', () => I18N.t('entry.success', { name, time: formatTime(checked_in_at) }));
    } catch (error) {
      await Scanner.flash(error.code === 'ALREADY_CHECKED_IN' ? 'warning' : 'error', () => UI.errorText(error));
    } finally { reset(); }
  });

  function renderMatches() {
    const list = byId('search-results');
    list.replaceChildren();
    for (const person of matches) {
      const row = element('li');
      const button = element('button', 'search-result');
      const who = element('span', 'person-who');
      who.append(element('strong', '', person.name), element('span', 'secondary', [person.participant_code, person.email].join(' · ')));
      button.append(personAvatar(person), who, badge(person.status));
      button.addEventListener('click', () => {
        if (!busy) select(person, { code: person.participant_code });
      });
      row.append(button);
      list.append(row);
    }
  }
  function clearSearch() {
    clearTimeout(timer);
    ++searchRevision;
    matches = [];
    renderMatches();
    notice('search-notice');
  }
  function searchPeople() {
    clearSearch();
    const q = search.value.trim();
    if (!q) return;
    const revision = searchRevision;
    timer = setTimeout(async () => {
      try {
        const result = await API.get('/api/checkin/search', { q });
        if (revision !== searchRevision) return;
        matches = result;
        renderMatches();
        if (!matches.length) notice('search-notice', 'info', () => I18N.t('admin.empty'));
      } catch (error) {
        if (revision === searchRevision) UI.showError('search-notice', error);
      }
    }, 250);
  }
  search.addEventListener('input', searchPeople);
  searchPanel.addEventListener('toggle', () => {
    sync();
    if (searchPanel.open) { search.focus(); searchPeople(); }
    else clearSearch();
  });
  function renderRecent() { UI.personList(byId('recent-checkins'), recent, 'checked_in_at', 'entry.noRecent'); }
  function initialIntent() {
    const q = params.get('q')?.trim();
    const code = params.get('code')?.trim();
    params.delete('q');
    params.delete('code');
    if (q) { search.value = q; searchPanel.open = true; }
    else if (code) lookup({ code });
    sync();
  }
  picker.addEventListener('close', initialIntent);
  window.addEventListener('langchange', () => { renderRecent(); renderMatches(); });
  renderRecent();
  if (entrance) initialIntent();
  else openPicker();
})();
