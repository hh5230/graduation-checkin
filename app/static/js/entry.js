(() => {
  'use strict';

  const { byId, element, notice, showError, personList } = UI;
  const panel = byId('confirmation');
  const confirm = byId('confirm-checkin');
  const cancel = byId('cancel-checkin');
  const recentList = byId('recent-checkins');
  const storageKey = 'graduation.checkins.' + recentList.dataset.user;
  let recent = [];
  try {
    const saved = JSON.parse(sessionStorage.getItem(storageKey));
    if (Array.isArray(saved)) recent = saved.slice(0, 10);
  } catch (_) { /* In-memory history is sufficient when storage is unavailable. */ }

  let participant = null;
  let identity = null;
  let busy = false;
  const scanner = Scanner.bind(lookup);
  function vibrate(pattern) { if (navigator.vibrate) navigator.vibrate(pattern); }

  function render() {
    panel.hidden = !participant;
    byId('confirmation-actions').hidden = !participant;
    document.body.classList.toggle('reviewing', Boolean(participant));
    confirm.disabled = busy || !participant || participant.status !== 'registered';
    cancel.disabled = busy;
    if (participant) {
      const info = byId('entry-person');
      info.textContent = '';
      info.append(element('strong', 'feature-name', participant.name), UI.badge(participant.status));
      const fields = element('dl', 'details');
      for (const [key, value] of [['field.code', participant.participant_code], ['field.email', participant.email]]) {
        fields.append(element('dt', '', I18N.t(key)), element('dd', '', value));
      }
      info.append(fields);
    }
    personList(recentList, recent, 'checked_in_at', 'entry.noRecent');
  }

  function duplicate(at, operator) {
    notice('entry-notice', 'warning', () => I18N.t('entry.duplicate', {
      time: formatTime(at), operator: operator || '—'
    }));
  }
  async function lookup(source) {
    if (busy || participant) return false;
    busy = true;
    scanner.hold(true);
    notice('entry-notice');
    try {
      participant = await API.get('/api/lookup', source);
      identity = source;
      if (participant.status !== 'registered') {
        duplicate(participant.checked_in_at, participant.checked_in_by && participant.checked_in_by.name);
        vibrate([60, 50, 60]);
      }
      return true;
    } catch (error) {
      showError('entry-notice', error);
      vibrate([60, 50, 60]);
      return false;
    } finally {
      busy = false;
      scanner.hold(Boolean(participant));
      render();
      if (participant) {
        panel.scrollIntoView({ block: 'nearest' });
        (confirm.disabled ? cancel : confirm).focus({ preventScroll: true });
      }
    }
  }

  function remember(person) {
    const { id, name, participant_code, checked_in_at } = person;
    recent = [{ id, name, participant_code, checked_in_at }, ...recent.filter(item => item.id !== id)].slice(0, 10);
    try { sessionStorage.setItem(storageKey, JSON.stringify(recent)); } catch (_) { /* Keep the current list. */ }
  }
  cancel.addEventListener('click', () => {
    participant = identity = null;
    notice('entry-notice');
    scanner.hold(false);
    render();
    byId('manual-code').focus();
  });
  confirm.addEventListener('click', async () => {
    if (busy || !participant || participant.status !== 'registered') return;
    busy = true;
    render();
    try {
      const checked = await API.post('/api/checkin', identity);
      remember(checked);
      participant = identity = null;
      notice('entry-notice', 'success', () => I18N.t('entry.success', {
        name: checked.name, time: formatTime(checked.checked_in_at)
      }));
      vibrate(80);
    } catch (error) {
      if (error.code === 'ALREADY_CHECKED_IN') {
        const details = error.details;
        participant = details.participant || Object.assign({}, participant, { status: 'checked_in' });
        const operator = details.checked_in_by || participant.checked_in_by;
        duplicate(details.checked_in_at || participant.checked_in_at, (operator && operator.name) || details.checked_in_by_name);
      } else {
        if (['INVALID_QR', 'PARTICIPANT_NOT_FOUND'].includes(error.code)) participant = identity = null;
        showError('entry-notice', error);
      }
      vibrate([60, 50, 60]);
    } finally {
      busy = false;
      scanner.hold(Boolean(participant));
      render();
    }
  });
  window.addEventListener('langchange', render);
  render();
  const code = new URLSearchParams(location.search).get('code')?.trim();
  if (code) {
    byId('manual-code').value = code;
    lookup({ code });
  }
})();
