(() => {
  'use strict';

  const { byId, element, notice, personList } = UI;
  const sheet = byId('requeue-sheet');
  let state = null;
  let busy = false;
  let absent = null;
  const scanner = Scanner.bind(source => operate('/api/stage/queue', source, 'stage.enqueued'));

  function controls() {
    const locked = busy || sheet.open;
    const waiting = state?.queue_length ?? state?.queue.length;
    byId('call-next').disabled = locked || !waiting || Boolean(state?.current);
    byId('complete').disabled = byId('requeue').disabled = locked || !state?.current;
    scanner.hold(locked);
  }
  function hero(id, person, empty) {
    const card = byId(id);
    card.replaceChildren(element('strong', person ? 'hero-name' : 'hero-idle',
      person ? person.name : I18N.t(state ? empty : 'common.loading')));
    if (person) UI.sizeName(card.firstElementChild);
    if (person) card.append(element('span', 'feature-code', person.participant_code));
  }
  function render() {
    controls();
    hero('stage-current', state?.current, 'stage.idle');
    hero('stage-next', state && ('next' in state ? state.next : state.queue[0]), 'stage.emptyQueue');
    if (absent) byId('requeue-question').textContent = I18N.t('stage.requeueQuestion', { name: absent.name });
    if (!state) return;
    byId('stage-length').textContent = I18N.t('stage.length', { count: state.queue_length ?? state.queue.length });
    const roster = byId('stage-queue');
    roster.replaceChildren();
    if (!state.queue.length) roster.append(element('li', 'empty', I18N.t('stage.emptyQueue')));
    state.queue.forEach((person, index) => {
      const row = UI.personRow(person, { position: index + 1, actions: [] });
      const who = row.querySelector('.person-who');
      const time = element('time', 'secondary', formatTime(person.queued_at));
      time.dateTime = person.queued_at;
      who.append(time);
      if (person.requeue_count > 0) who.append(element('span', 'requeue-count',
        I18N.t('stage.requeueCount', { count: person.requeue_count })));
      roster.append(row);
    });
    personList(byId('stage-recent'), state.recent_completed, 'completed_at', 'stage.emptyRecent');
  }
  const feed = Realtime.snapshot('/api/stage/state', data => { state = data; render(); });
  async function operate(path, body, key, target) {
    if (busy || sheet.open) return false;
    const hadQueue = (state?.queue_length ?? state?.queue.length ?? 0) > 0;
    busy = true;
    controls();
    let success = false;
    let tone, message;
    try {
      const result = await API.post(path, body);
      const person = result.participant || result.current || result.completed || target;
      message = () => I18N.t(key, { name: person.name, position: result.position });
      tone = 'success';
      success = true;
    } catch (error) {
      tone = ['ALREADY_QUEUED', 'STAGE_BUSY', 'NOTHING_ON_STAGE', 'QUEUE_EMPTY'].includes(error.code) ? 'warning' : 'error';
      message = () => error.code === 'QUEUE_EMPTY' && hadQueue
        ? UI.errorText(error) + '\n' + I18N.t('feedback.colleague') : UI.errorText(error);
    }
    try {
      notice('stage-notice', tone, message);
      await Promise.all([Scanner.flash(tone, message), feed.refresh()]);
    } finally { busy = false; controls(); }
    return success;
  }
  byId('call-next').addEventListener('click', () => operate('/api/stage/call-next', {}, 'stage.called'));
  byId('complete').addEventListener('click', () => {
    if (state?.current) operate('/api/stage/complete', { participant_id: state.current.id }, 'stage.finished');
  });
  byId('requeue').addEventListener('click', () => {
    absent = state.current;
    sheet.returnValue = '';
    sheet.showModal();
    render();
  });
  sheet.addEventListener('close', () => {
    const target = absent;
    absent = null;
    if (sheet.returnValue === 'move') operate('/api/stage/requeue', { participant_id: target.id }, 'stage.requeued', target);
    else controls();
  });
  window.addEventListener('langchange', render);
  render();
  feed.refresh();
  Realtime.connect({ onStage: feed.accept, onConnect: feed.refresh });
})();
