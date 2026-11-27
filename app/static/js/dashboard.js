(() => {
  'use strict';

  const { byId, element, personList } = UI;
  const admin = document.body.dataset.role === 'admin';
  const hasStage = Boolean(byId('dash-current'));
  let timeline = null;
  let stage = null;
  let recent = [];
  let timelineVersion = 0;
  let rosterVersion = 0;
  let timer;

  function renderChart() {
    if (!timeline) return;
    const buckets = timeline.buckets;
    const total = buckets.reduce((sum, b) => sum + b.count, 0);
    byId('chart-total').textContent = total.toLocaleString(I18N.getLang());
    const max = Math.max(2, ...buckets.map(b => b.count));
    const step = Math.ceil(max / 2);
    const clock = new Intl.DateTimeFormat(I18N.getLang(), { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
    const chart = byId('timeline');
    const axis = element('div', 'chart-axis');
    const plot = element('div', 'chart-plot');
    const labels = element('div', 'chart-labels');
    for (const n of [step * 2, step, 0]) axis.append(element('span', '', n));
    for (const b of buckets) {
      const start = clock.format(new Date(b.start));
      const end = clock.format(new Date(b.end));
      const tip = I18N.t('dashboard.bucket', { start, end, count: b.count });
      const slot = element('div', 'chart-slot');
      slot.tabIndex = 0;
      slot.setAttribute('aria-label', tip);
      slot.title = tip;
      const bar = element('div', 'chart-bar' + (b.current ? ' current' : ''));
      bar.style.height = (100 * b.count / (2 * step)) + '%';
      const tooltip = element('span', 'chart-tooltip', tip);
      tooltip.setAttribute('aria-hidden', 'true');
      slot.append(bar, tooltip);
      plot.append(slot);
      labels.append(element('span', '', start));
    }
    if (!total) {
      const empty = element('div', 'chart-empty');
      empty.append(element('span', '', I18N.t('dashboard.emptyChart')));
      plot.append(empty);
    }
    chart.replaceChildren(axis, plot, labels);
  }
  async function fetchChart() {
    clearTimeout(timer);
    const version = ++timelineVersion;
    try {
      const data = await API.get('/api/stats/timeline', { bucket_minutes: 10, buckets: 12 });
      if (version !== timelineVersion) return;
      timeline = data;
      UI.notice('timeline-notice');
      renderChart();
    } catch (error) {
      if (version === timelineVersion) UI.showError('timeline-notice', error);
    }
  }

  function renderRecent() {
    personList(byId('dash-recent'), recent, 'checked_in_at', 'dashboard.emptyRecent');
  }
  // Keep the latest five check-ins and accept profile/status changes only from newer snapshots.
  function remember(people) {
    const byPerson = new Map(recent.map(person => [person.id, person]));
    for (const person of people) {
      if (!person) continue;
      if (!person.checked_in_at) {
        const previous = byPerson.get(person.id);
        if (previous && previous.updated_at <= person.updated_at) byPerson.delete(person.id);
        continue;
      }
      const previous = byPerson.get(person.id);
      if (!previous || previous.updated_at <= person.updated_at) byPerson.set(person.id, person);
    }
    recent = [...byPerson.values()].sort((a, b) =>
      b.checked_in_at.localeCompare(a.checked_in_at) || b.id - a.id).slice(0, 5);
    renderRecent();
  }

  function renderStage() {
    if (!stage) return;
    personList(byId('dash-current'), stage.current ? [stage.current] : [], 'called_at', 'stage.idle');
    personList(byId('dash-queue'), stage.queue.slice(0, 5), null, 'stage.emptyQueue', true);
  }
  const stageFeed = Realtime.snapshot('/api/stage/state', data => {
    stage = data;
    remember([data.current, ...data.queue, ...data.recent_completed]);
    renderStage();
  });
  async function loadRoster() {
    if (!admin) return;
    const version = ++rosterVersion;
    try {
      // The roster is ordered by ID. A late check-in may be on any page.
      let page = 1;
      while (true) {
        const data = await API.get('/api/participants', { page, per_page: 100 });
        if (version !== rosterVersion) return;
        remember(data.items);
        if (page * data.per_page >= data.total) break;
        page++;
      }
      UI.notice('recent-notice');
    } catch (error) {
      if (version === rosterVersion) UI.showError('recent-notice', error);
    }
  }
  function refresh() { if (hasStage) stageFeed.refresh(); fetchChart(); loadRoster(); }
  window.addEventListener('langchange', () => { renderChart(); renderStage(); renderRecent(); });
  setInterval(fetchChart, 60000);
  Realtime.connect({
    onStage: hasStage ? stageFeed.accept : undefined, onConnect: refresh,
    onStats: () => { clearTimeout(timer); timer = setTimeout(fetchChart, 300); },
    onParticipant: ({ action, participant }) => {
      if (action === 'check_in' || recent.some(p => p.id === participant.id)) remember([participant]);
    }
  });
  refresh();
})();
