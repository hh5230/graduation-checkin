(() => {
  'use strict';

  const { byId, notice, showError } = UI;
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
      actions: [['admin.edit', 'edit', openEditor], ['admin.qr', 'qr', openQr]] });
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
  function refilter(delay) {
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
  document.querySelectorAll('[data-close]').forEach(button => {
    button.addEventListener('click', () => button.closest('dialog').close());
  });
  editor.addEventListener('cancel', event => { if (saving) event.preventDefault(); });
  qr.addEventListener('cancel', event => { if (regenerating) event.preventDefault(); });
  window.addEventListener('langchange', render);
  loadList();
  Realtime.connect({
    onConnect: loadList,
    onParticipant: ({ action, participant }) => {
      if (qr.open && qrPerson.id === participant.id && ['update', 'regenerate_qr'].includes(action)) {
        setPass(participant);
      }
      schedule(180);
    }
  });
})();
