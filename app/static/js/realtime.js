(() => {
  'use strict';

  // The shell and the current page subscribe to one authenticated, same-origin socket.
  let socket;
  function connect({ onParticipant, onStage, onStats, onConnect } = {}) {
    if (!window.io) return;
    if (!socket) {
      socket = io();
      const indicator = UI.byId('conn-status');
      function mark(online) {
        if (!indicator) return;
        indicator.dataset.online = String(online);
        if (indicator.classList.contains('offline-dot')) {
          indicator.hidden = online;
          return;
        }
        indicator.dataset.i18n = online ? 'connection.online' : 'connection.offline';
        indicator.textContent = I18N.t(indicator.dataset.i18n);
      }
      socket.on('connect', () => mark(true));
      socket.on('disconnect', () => mark(false));
      socket.on('connect_error', () => mark(false));
    }
    if (onParticipant) socket.on('participant_updated', onParticipant);
    if (onStage) socket.on('stage_updated', onStage);
    if (onStats) socket.on('stats_updated', onStats);
    if (onConnect) {
      socket.on('connect', onConnect);
      if (socket.connected) onConnect();
    }
  }

  // Discard an older HTTP snapshot when a newer read or broadcast has arrived.
  function snapshot(path, render, noticeId = 'state-notice') {
    let revision = 0;
    function accept(data) {
      ++revision;
      UI.notice(noticeId);
      render(data);
    }
    async function refresh() {
      const ticket = ++revision;
      try {
        const data = await API.get(path);
        if (ticket === revision) accept(data);
      } catch (error) {
        if (ticket === revision) UI.showError(noticeId, error);
      }
    }
    return { accept, refresh };
  }
  window.Realtime = { connect, snapshot };
})();
