(() => {
  'use strict';

  const { byId } = UI;
  let stats = null;
  let updated = null;
  function render() {
    if (!stats) return;
    const locale = I18N.getLang();
    const count = new Intl.NumberFormat(locale);
    for (const field of ['total', 'checked_in', 'not_checked_in', 'waiting', 'on_stage', 'completed']) {
      byId('stat-' + field).textContent = count.format(stats[field]);
    }
    const fraction = stats.total ? stats.checked_in / stats.total : 0;
    const percentage = new Intl.NumberFormat(locale, { style: 'percent', maximumFractionDigits: 1 }).format(fraction);
    byId('rate-value').textContent = percentage;
    byId('rate-bar').value = fraction * 100;
    byId('stats-time').dateTime = updated;
    byId('stats-time').textContent = formatTime(updated);
  }
  const feed = Realtime.snapshot('/api/stats', data => {
    stats = data;
    updated = new Date().toISOString();
    render();
  });
  window.addEventListener('langchange', render);
  feed.refresh();
  Realtime.connect({ onStats: feed.accept, onConnect: feed.refresh });
})();
