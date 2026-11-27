(() => {
  'use strict';

  const { byId, element, notice, personList } = UI;
  const call = byId('call-next');
  const complete = byId('complete');
  const advance = byId('complete-next');
  let state = null;
  let busy = false;
  const scanner = Scanner.bind(source => operate('/api/stage/queue', source, 'stage.enqueued'));

  function controls() {
    const current = state && state.current;
    const waiting = state && state.queue.length;
    call.disabled = busy || !waiting || Boolean(current);
    complete.disabled = busy || !current;
    advance.disabled = busy || !current || !waiting;
  }
  function render() {
    controls();
    const card = byId('stage-current');
    card.textContent = '';
    if (!state) {
      card.append(element('p', 'empty', I18N.t('common.loading')));
      return;
    }
    if (state.current) {
      card.append(element('strong', 'feature-name', state.current.name),
        element('span', 'mono feature-code', state.current.participant_code));
    } else card.append(element('p', 'empty', I18N.t('stage.idle')));
    personList(byId('stage-queue'), state.queue, 'queued_at', 'stage.emptyQueue', true);
    personList(byId('stage-recent'), state.recent_completed, 'completed_at', 'stage.emptyRecent');
  }
  const feed = Realtime.snapshot('/api/stage/state', data => { state = data; render(); });

  async function operate(path, body, messageKey) {
    if (busy) return false;
    busy = true;
    scanner.hold(true);
    controls();
    notice('stage-notice');
    try {
      const result = await API.post(path, body);
      const person = result.participant || result.current || result.completed;
      notice('stage-notice', 'success', () => I18N.t(messageKey, { name: person.name, position: result.position }));
      return true;
    } catch (error) {
      notice('stage-notice', error.code === 'ALREADY_QUEUED' ? 'warning' : 'error', () => {
        const message = UI.errorText(error);
        if (error.code === 'ALREADY_QUEUED' && error.details.position) {
          return message + ' ' + I18N.t('stage.position', { position: error.details.position });
        }
        return message;
      });
      return false;
    } finally {
      await feed.refresh();
      busy = false;
      scanner.hold(false);
      controls();
    }
  }
  call.addEventListener('click', () => operate('/api/stage/call-next', {}, 'stage.called'));
  complete.addEventListener('click', () => {
    if (state && state.current) operate('/api/stage/complete', { participant_id: state.current.id }, 'stage.finished');
  });
  advance.addEventListener('click', () => operate('/api/stage/call-next', { complete_current: true }, 'stage.called'));
  window.addEventListener('langchange', render);
  render();
  feed.refresh();
  Realtime.connect({ onStage: feed.accept, onConnect: feed.refresh });
})();
