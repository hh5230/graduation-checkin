(() => {
  'use strict';

  function connect({ onParticipant, onStage, onStats, onConnect } = {}) {
    const indicator = UI.byId('conn-status');
    function mark(online) {
      if (!indicator) return;
      indicator.dataset.online = String(online);
      indicator.dataset.i18n = online ? 'connection.online' : 'connection.offline';
      indicator.textContent = I18N.t(indicator.dataset.i18n);
    }
    function attach() {
      if (!window.io) return;
      const socket = window.io({ autoConnect: false });
      if (onParticipant) socket.on('participant_updated', onParticipant);
      if (onStage) socket.on('stage_updated', onStage);
      if (onStats) socket.on('stats_updated', onStats);
      socket.on('connect', () => {
        mark(true);
        if (onConnect) onConnect();
      });
      socket.on('disconnect', () => mark(false));
      socket.on('connect_error', () => mark(false));
      socket.connect();
    }
    mark(false);
    if (window.io) attach();
    else {
      const script = UI.byId('socket-client');
      if (script) script.addEventListener('load', attach, { once: true });
    }
  }

  // A broadcast received during a REST read supersedes that read's snapshot.
  function snapshot(path, render) {
    let revision = 0;
    function accept(data) {
      ++revision;
      UI.notice('state-notice');
      render(data);
    }
    async function refresh() {
      const ticket = ++revision;
      try {
        const data = await API.get(path);
        if (ticket === revision) accept(data);
      } catch (error) {
        if (ticket === revision) UI.showError('state-notice', error);
      }
    }
    return { accept, refresh };
  }
  window.Realtime = { connect, snapshot };
})();
