(() => {
  'use strict';

  const { byId, element } = UI;
  const name = byId('display-name');
  const code = byId('display-code');
  const queue = byId('display-queue');
  const tools = byId('display-tools');
  const fullscreen = byId('fullscreen');
  let state = null;
  let hideTimer;
  function render() {
    if (!state) return;
    name.removeAttribute('data-i18n');
    name.textContent = state.current ? state.current.name : I18N.t('display.idle');
    name.classList.toggle('is-idle', !state.current);
    code.textContent = state.current ? state.current.participant_code : '';
    queue.textContent = '';
    state.queue.slice(0, 3).forEach((person, index) => {
      const row = element('li', '');
      const identity = element('div', 'person-who');
      identity.append(element('strong', '', person.name), element('span', 'mono', person.participant_code));
      row.append(element('span', 'position', String(index + 1).padStart(2, '0')), identity);
      queue.append(row);
    });
    if (!queue.childElementCount) queue.append(element('li', 'empty', I18N.t('stage.emptyQueue')));
  }
  const feed = Realtime.snapshot('/api/stage/state', data => {
    const previous = state && state.current;
    const current = data.current;
    const changed = !state || (previous && previous.id) !== (current && current.id) ||
      (previous && current && (previous.name !== current.name || previous.participant_code !== current.participant_code));
    state = data;
    render();
    const person = byId('display-person');
    if (changed && person.animate && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
      person.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 360, easing: 'ease-out' });
    }
  });
  function showTools() {
    tools.classList.remove('is-hidden');
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => tools.classList.add('is-hidden'), 3500);
  }
  function fullscreenLabel() {
    fullscreen.dataset.i18n = document.fullscreenElement ? 'display.exitFullscreen' : 'display.fullscreen';
    fullscreen.textContent = I18N.t(fullscreen.dataset.i18n);
  }
  fullscreen.addEventListener('click', async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await document.documentElement.requestFullscreen();
      UI.notice('display-notice');
    } catch (_) { UI.notice('display-notice', 'warning', () => I18N.t('display.fullscreenError')); }
  });
  document.addEventListener('fullscreenchange', fullscreenLabel);
  ['pointermove', 'pointerdown', 'keydown', 'focusin'].forEach(event => document.addEventListener(event, showTools));
  window.addEventListener('langchange', render);
  showTools();
  feed.refresh();
  Realtime.connect({ onStage: feed.accept, onConnect: feed.refresh });
})();
