(() => {
  'use strict';

  let reader = null;
  let running = false;
  let held = false;
  let paused = false;
  let startup = null;
  let shutdown = null;
  const seen = new Map();

  function cameraError(cause) {
    const description = String(cause && (cause.name || '')) + ' ' + String(cause);
    let code = 'CAMERA_FAILED';
    if (/NotAllowed|PermissionDenied|permission denied|permission dismissed|SecurityError/i.test(description)) {
      code = 'CAMERA_DENIED';
    } else if (/NotFound|DevicesNotFound|Overconstrained|no camera|device not found/i.test(description)) {
      code = 'CAMERA_MISSING';
    }
    return new ApiError(code, '', 0);
  }

  function syncPause() {
    if (!reader || !running || held === paused) return;
    if (held) reader.pause(false);
    else reader.resume();
    paused = held;
  }
  function pause() { held = true; syncPause(); }
  function resume() { held = false; syncPause(); }

  async function open(elementId, onDecoded) {
    if (!window.isSecureContext) throw new ApiError('CAMERA_INSECURE', '', 0);
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) throw new ApiError('CAMERA_MISSING', '', 0);
    if (!window.Html5Qrcode) throw new ApiError('CAMERA_LIBRARY', '', 0);
    reader = new Html5Qrcode(elementId, { verbose: false });
    try {
      await reader.start({ facingMode: 'environment' }, { fps: 10 }, raw => {
        if (held || shutdown) return;
        const token = raw.startsWith('GRAD:') ? raw.slice(5) : raw;
        const now = Date.now();
        for (const [key, stamp] of seen) if (now - stamp >= 3000) seen.delete(key);
        if (seen.has(token)) return;
        seen.set(token, now);
        onDecoded(token);
      });
      running = true;
      // The pinned reader inserts its own English pause label in the video surface.
      const overlay = Array.from(document.getElementById(elementId).children)
        .find(child => child.textContent.trim() === 'Scanner paused');
      if (overlay) {
        overlay.dataset.i18n = 'scan.paused';
        I18N.apply(overlay);
      }
      syncPause();
    } catch (cause) {
      if (running) await reader.stop();
      reader.clear();
      reader = null;
      running = paused = false;
      throw cameraError(cause);
    }
  }
  async function start(elementId, onDecoded) {
    if (shutdown) await shutdown;
    if (running) return;
    if (!startup) startup = open(elementId, onDecoded).finally(() => { startup = null; });
    await startup;
  }
  async function stop() {
    if (shutdown) return shutdown;
    shutdown = (async () => {
      if (startup) {
        try { await startup; } catch (_) { return; }
      }
      if (!reader) return;
      if (running) await reader.stop();
      reader.clear();
      running = paused = false;
      reader = null;
    })().finally(() => { shutdown = null; });
    return shutdown;
  }

  function bind(onIdentify) {
    const toggle = UI.byId('camera-toggle');
    const frame = UI.byId('camera-frame');
    const form = UI.byId('manual-form');
    const input = UI.byId('manual-code');
    let changing = false;
    function update() {
      toggle.disabled = changing || held;
      toggle.dataset.i18n = running ? 'scan.stop' : 'scan.start';
      toggle.textContent = I18N.t(toggle.dataset.i18n);
      frame.classList.toggle('is-running', running);
      for (const field of form.elements) field.disabled = held;
    }
    toggle.addEventListener('click', async () => {
      changing = true;
      update();
      UI.notice('camera-notice');
      try {
        if (running) await stop();
        else await start('reader', token => onIdentify({ token }));
      } catch (error) {
        UI.showError('camera-notice', error.code ? error : cameraError(error));
      } finally { changing = false; update(); }
    });
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (held) return;
      const code = input.value.trim();
      if (!code) {
        UI.notice('camera-notice', 'error', () => I18N.t('scan.needCode'));
        input.focus();
        return;
      }
      UI.notice('camera-notice');
      if (await onIdentify({ code })) input.value = '';
    });
    window.addEventListener('pagehide', () => { stop().then(update).catch(() => {}); });
    return {
      hold(value) {
        if (value) pause();
        else resume();
        update();
      }
    };
  }
  window.Scanner = { start, stop, pause, resume, bind };
})();
