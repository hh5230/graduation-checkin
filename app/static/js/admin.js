(() => {
  'use strict';

  const { byId, notice, showError, element } = UI;
  const search = byId('search');
  const filter = byId('status-filter');
  let selectedStatus = '';
  search.value = new URLSearchParams(location.search).get('q') || '';
  const rows = byId('participant-rows');
  const editor = byId('editor');
  const form = byId('editor-form');
  const qr = byId('qr-dialog');
  const image = byId('qr-image');
  const previous = byId('prev-page');
  const next = byId('next-page');
  let list = null;
  let page = 1;
  let version = 0;
  let timer;
  let loading = true;
  let editorPerson = null;
  let qrPerson = null;
  let saving = false;
  let regenerating = false;

  function rowFor(person) {
    return UI.personRow(person, { email: true, timeField: 'checked_in_at',
      actions: [['admin.edit', 'edit', openEditor], ['admin.qr', 'qr', openQr],
        ['admin.timeline', 'clock', openTimeline], ['admin.undo', 'undo', openUndo]] });
  }
  function render() {
    rows.textContent = '';
    if (list) list.items.forEach(person => rows.append(rowFor(person)));
    const pages = list ? Math.max(1, Math.ceil(list.total / list.per_page)) : 1;
    const empty = byId('list-empty');
    empty.hidden = Boolean(list && list.items.length) || (!list && !loading);
    empty.dataset.i18n = loading ? 'common.loading' : 'admin.empty';
    empty.textContent = I18N.t(empty.dataset.i18n);
    byId('page-info').textContent = list ? I18N.t('admin.pageInfo', { page: list.page, pages, total: list.total }) : '';
    previous.disabled = loading || !list || page <= 1;
    next.disabled = loading || !list || page >= pages;
  }
  async function loadList() {
    clearTimeout(timer);
    const ticket = ++version;
    loading = true;
    previous.disabled = next.disabled = true;
    try {
      const result = await API.get('/api/participants', {
        q: search.value.trim(), status: selectedStatus, page, per_page: 20
      });
      if (ticket !== version) return;
      const last = Math.max(1, Math.ceil(result.total / result.per_page));
      if (page > last) {
        page = last;
        return loadList();
      }
      list = result;
      notice('list-notice');
    } catch (error) {
      if (ticket === version) {
        if (list) page = list.page;
        showError('list-notice', error);
      }
    } finally {
      if (ticket === version) { loading = false; render(); }
    }
  }
  function schedule(delay) {
    clearTimeout(timer);
    ++version;
    loading = true;
    previous.disabled = next.disabled = true;
    timer = setTimeout(loadList, delay);
  }
  function updateSheetLink() {
    byId('print-sheet').href = '/admin/qr-sheet?' + new URLSearchParams({ status: selectedStatus, q: search.value.trim() });
  }
  updateSheetLink();
  function refilter(delay) {
    updateSheetLink();
    list = null;
    page = 1;
    schedule(delay);
    render();
  }
  search.addEventListener('input', () => refilter(250));
  filter.addEventListener('click', event => {
    const selected = event.target.closest('[data-status]');
    if (!selected || selectedStatus === selected.dataset.status) return;
    selectedStatus = selected.dataset.status;
    filter.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(b === selected)));
    refilter(0);
  });
  previous.addEventListener('click', () => { --page; loadList(); });
  next.addEventListener('click', () => { ++page; loadList(); });

  function openEditor(person) {
    editorPerson = person;
    form.reset();
    if (person) for (const key of ['participant_code', 'name', 'email']) form.elements[key].value = person[key];
    const title = byId('editor-title');
    title.dataset.i18n = person ? 'admin.editTitle' : 'admin.create';
    title.textContent = I18N.t(title.dataset.i18n);
    notice('editor-notice');
    editor.showModal();
    form.elements.participant_code.focus();
  }
  byId('create-person').addEventListener('click', () => openEditor(null));
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (saving) return;
    const body = {};
    for (const key of ['participant_code', 'name', 'email']) body[key] = form.elements[key].value.trim();
    saving = true;
    Array.from(form.elements).forEach(field => { field.disabled = true; });
    notice('editor-notice');
    try {
      const person = editorPerson ? await API.patch('/api/participants/' + editorPerson.id, body)
        : await API.post('/api/participants', body);
      const key = editorPerson ? 'admin.saved' : 'admin.created';
      notice('admin-notice', 'success', () => I18N.t(key, { name: person.name }));
      editor.close();
      await loadList();
    } catch (error) { showError('editor-notice', error); }
    finally {
      saving = false;
      Array.from(form.elements).forEach(field => { field.disabled = false; });
    }
  });

  function setPass(person, revision) {
    qrPerson = person;
    byId('qr-name').textContent = person.name;
    byId('qr-code').textContent = person.participant_code;
    const url = '/api/participants/' + person.id + '/qr.png?v=' + encodeURIComponent(revision || person.updated_at || person.id);
    byId('print-qr').disabled = true;
    image.src = url;
    const download = byId('download-qr');
    download.href = url;
    download.download = person.participant_code + '.png';
  }
  image.addEventListener('load', () => { byId('print-qr').disabled = false; });
  image.addEventListener('error', () => notice('qr-notice', 'error', () => I18N.t('admin.qrFailed')));
  function confirmation(open) {
    byId('qr-confirm').hidden = !open;
    byId('qr-actions').hidden = open;
    if (qr.open) byId(open ? 'keep-qr' : 'ask-regenerate').focus();
  }
  function openQr(person) {
    notice('qr-notice');
    confirmation(false);
    setPass(person);
    qr.showModal();
  }
  byId('ask-regenerate').addEventListener('click', () => confirmation(true));
  byId('keep-qr').addEventListener('click', () => confirmation(false));
  byId('regenerate').addEventListener('click', async () => {
    if (regenerating) return;
    regenerating = true;
    byId('keep-qr').disabled = byId('regenerate').disabled = true;
    notice('qr-notice');
    try {
      const person = await API.post('/api/participants/' + qrPerson.id + '/regenerate-qr', {});
      setPass(person, Date.now());
      confirmation(false);
      notice('qr-notice', 'success', () => I18N.t('admin.regenerated'));
      await loadList();
    } catch (error) { showError('qr-notice', error); }
    finally {
      regenerating = false;
      byId('keep-qr').disabled = byId('regenerate').disabled = false;
    }
  });
  byId('print-qr').addEventListener('click', () => window.print());
  const auditDialog = byId('participant-detail');
  let auditPerson = null;
  let auditEvents = [];
  let auditVersion = 0;
  const fieldKeys = { participant_code: 'field.code', name: 'field.name', email: 'field.email',
    entrance: 'entry.entrance', reason: 'field.reason', from: 'audit.from', to: 'audit.to',
    changed_fields: 'audit.fields', requeue_count: 'audit.requeues', line: 'admin.line', position: 'audit.position' };

  function detailValue(key, value) {
    if (key === 'from' || key === 'to') return I18N.t('status.' + value);
    if (key === 'changed_fields' && Array.isArray(value)) {
      return value.map(field => fieldKeys[field] ? I18N.t(fieldKeys[field]) : field).join(' · ');
    }
    return typeof value === 'object' ? JSON.stringify(value) : String(value);
  }
  const actionIcons = { create: 'add', update: 'edit', check_in: 'check', enqueue: 'move', call: 'move',
    complete: 'check', regenerate_qr: 'qr', requeue: 'undo', undo: 'undo', import: 'add' };
  function renderAudit() {
    const list = byId('audit-list');
    list.replaceChildren();
    for (const item of auditEvents) {
      const row = element('li');
      const mark = element('span', 'audit-mark');
      mark.append(UI.icon(actionIcons[item.action] || 'clock'));
      const summary = element('div', 'audit-entry');
      const time = element('time', 'secondary', formatTime(item.at));
      time.dateTime = item.at;
      summary.append(element('strong', '', I18N.t('action.' + item.action)), time);
      if (item.operator) summary.append(element('span', '', item.operator.name));
      for (const [key, value] of Object.entries(item.details || {})) {
        if (value == null) continue;
        const label = fieldKeys[key] ? I18N.t(fieldKeys[key]) : key;
        summary.append(element('span', 'secondary', label + ' · ' + detailValue(key, value)));
      }
      row.append(mark, summary);
      list.append(row);
    }
  }
  async function loadAudit() {
    const revision = ++auditVersion;
    const person = auditPerson;
    if (!person || !auditDialog.open) return;
    try {
      const events = await API.get('/api/participants/' + person.id + '/timeline');
      if (revision !== auditVersion || !auditDialog.open) return;
      auditEvents = events;
      notice('audit-notice', 'info', events.length ? null : () => I18N.t('audit.empty'));
      renderAudit();
    } catch (error) { if (revision === auditVersion) showError('audit-notice', error); }
  }
  function openTimeline(person) {
    auditPerson = person;
    auditEvents = [];
    renderAudit();
    UI.showDetails(person);
    notice('audit-notice', 'info', () => I18N.t('common.loading'));
    loadAudit();
  }
  auditDialog.addEventListener('close', () => { ++auditVersion; auditPerson = null; });

  const upload = byId('import-dialog');
  const importForm = byId('import-form');
  let importing = false;
  let report = null;
  byId('csv-template').href = 'data:text/csv;charset=utf-8,' + encodeURIComponent('participant_code,name,email\r\n');
  function renderImport() {
    byId('import-result').hidden = !report;
    if (!report) return;
    byId('import-created').textContent = report.created;
    byId('import-skipped').textContent = report.skipped_existing;
    const table = byId('import-errors');
    table.hidden = !report.errors.length;
    const body = table.tBodies[0];
    body.replaceChildren();
    for (const error of report.errors) {
      const message = UI.errorText(error);
      const cell = element('td');
      cell.append(element('strong', '', message));
      if (error.message && error.message !== message) cell.append(element('p', '', error.message));
      cell.append(element('small', '', error.code));
      const row = element('tr');
      row.append(element('td', '', error.line), element('td', 'mono', error.participant_code || '—'), cell);
      body.append(row);
    }
  }
  byId('open-import').addEventListener('click', () => {
    report = null;
    importForm.reset();
    notice('import-notice');
    renderImport();
    upload.showModal();
  });
  importForm.addEventListener('submit', async event => {
    event.preventDefault();
    if (importing) return;
    const data = new FormData(importForm);
    importing = true;
    upload.querySelectorAll('input,button').forEach(control => { control.disabled = true; });
    notice('import-notice', 'info', () => I18N.t('common.loading'));
    report = null;
    renderImport();
    try {
      report = await API.upload('/api/participants/import', data);
      notice('import-notice');
      renderImport();
      await loadList();
    } catch (error) { showError('import-notice', error); }
    finally {
      importing = false;
      upload.querySelectorAll('input,button').forEach(control => { control.disabled = false; });
    }
  });
  upload.addEventListener('cancel', event => { if (importing) event.preventDefault(); });

  const undo = byId('undo-dialog');
  const undoForm = byId('undo-form');
  let undoPerson;
  let undoing = false;
  let toastTimer;
  function openUndo(person) {
    undoPerson = person;
    undoForm.reset();
    byId('undo-person').textContent = person.name + ' · ' + person.participant_code;
    notice('undo-notice');
    undo.showModal();
    undoForm.elements.reason.focus();
  }
  undoForm.addEventListener('submit', async event => {
    event.preventDefault();
    if (undoing) return;
    const input = undoForm.elements.reason;
    const reason = input.value.trim();
    if (!reason) { input.value = ''; input.reportValidity(); return; }
    undoing = true;
    for (const control of undoForm.elements) control.disabled = true;
    notice('undo-notice');
    try {
      await API.post('/api/participants/' + undoPerson.id + '/undo', { reason });
      const name = undoPerson.name;
      undo.close();
      clearTimeout(toastTimer);
      notice('undo-toast', 'success', () => I18N.t('admin.undone', { name }));
      toastTimer = setTimeout(() => notice('undo-toast'), 4000);
      await loadList();
    } catch (error) { showError('undo-notice', error); }
    finally {
      undoing = false;
      for (const control of undoForm.elements) control.disabled = false;
    }
  });
  undo.addEventListener('cancel', event => { if (undoing) event.preventDefault(); });
  document.querySelectorAll('[data-close]').forEach(button => {
    button.addEventListener('click', () => button.closest('dialog').close());
  });
  editor.addEventListener('cancel', event => { if (saving) event.preventDefault(); });
  qr.addEventListener('cancel', event => { if (regenerating) event.preventDefault(); });
  window.addEventListener('langchange', () => { render(); renderImport(); renderAudit(); });
  loadList();
  Realtime.connect({
    onConnect: () => { loadList(); loadAudit(); },
    onStats: () => schedule(180),
    onParticipant: ({ action, participant }) => {
      if (qr.open && qrPerson.id === participant.id && ['update', 'regenerate_qr'].includes(action)) {
        setPass(participant);
      }
      if (auditDialog.open && auditPerson?.id === participant.id) {
        auditPerson = participant;
        UI.showDetails(participant);
        loadAudit();
      }
      schedule(180);
    }
  });
})();
