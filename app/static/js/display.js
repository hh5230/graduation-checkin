(() => {
  'use strict';

  const { byId } = UI;
  let state;
  function render() {
    if (!state) return;
    const current = state.current;
    const next = 'next' in state ? state.next : state.queue[0];
    const name = byId('display-name');
    name.removeAttribute('data-i18n');
    name.textContent = current ? current.name : I18N.t('display.idle');
    UI.sizeName(name);
    name.classList.toggle('is-idle', !current);
    byId('display-label').hidden = !current;
    byId('display-code').textContent = current?.participant_code || '';
    byId('display-next').textContent = next?.name || '—';
    UI.sizeName(byId('display-next'));
  }
  function animate(id) {
    if (!matchMedia('(prefers-reduced-motion: reduce)').matches) {
      byId(id).animate?.([{ opacity: 0, transform: 'translateY(var(--sp-3))' }, { opacity: 1, transform: 'translateY(0)' }],
        { duration: 360, easing: 'ease-out' });
    }
  }
  const feed = Realtime.snapshot('/api/stage/state', data => {
    const previous = state?.current;
    const nextName = byId('display-next').textContent;
    state = data;
    render();
    if (previous?.id !== data.current?.id || previous?.name !== data.current?.name ||
      previous?.participant_code !== data.current?.participant_code) animate('display-person');
    if (nextName !== byId('display-next').textContent) animate('display-next');
  });
  async function fullscreen() {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await document.documentElement.requestFullscreen();
      UI.notice('display-notice');
    } catch (_) { UI.notice('display-notice', 'warning', () => I18N.t('display.fullscreenError')); }
  }
  const back = byId('display-back');
  let hideTimer;
  function goBack() {
    if (document.referrer && new URL(document.referrer).origin === location.origin) history.back();
    else location.assign('/');
  }
  function revealBack() {
    back.hidden = false;
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => { back.hidden = true; }, 3000);
  }
  document.addEventListener('pointermove', revealBack);
  document.addEventListener('pointerdown', revealBack);
  back.addEventListener('click', goBack);
  document.addEventListener('dblclick', fullscreen);
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && !e.repeat) goBack();
    if (e.key.toLowerCase() === 'f' && !e.repeat && !e.ctrlKey && !e.altKey && !e.metaKey) fullscreen();
  });
  window.addEventListener('langchange', render);
  feed.refresh();
  Realtime.connect({ onStage: feed.accept, onConnect: feed.refresh });
})();
