(() => {
  'use strict';

  let reader = null;
  let running = false;
  let held = false;
  let paused = false;
  let startup = null;
  let shutdown = null;
  const seen = new Map();

  function unavailable() {
    if (!window.isSecureContext) return 'CAMERA_INSECURE';
    if (!navigator.mediaDevices?.getUserMedia) return 'CAMERA_MISSING';
    if (!window.Html5Qrcode) return 'CAMERA_LIBRARY';
    return null;
  }
  function qrToken(raw) {
    return raw.trim().replace(/^GRAD:/, '').trim();
  }

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
    const reason = unavailable();
    if (reason) throw new ApiError(reason, '', 0);
    reader = new Html5Qrcode(elementId, { verbose: false });
    try {
      await reader.start({ facingMode: 'environment' }, { fps: 10 }, raw => {
        if (held || shutdown) return;
        const token = qrToken(raw);
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
    const photo = UI.byId('scan-photo');
    const photoButton = UI.byId('photo-button');
    const toggleText = toggle.querySelector('[data-i18n]');
    let changing = false;
    let readingPhoto = false;
    let fallback = unavailable();
    let fileReader;

    function update() {
      toggle.disabled = changing || held || readingPhoto || Boolean(unavailable());
      toggleText.dataset.i18n = running ? 'scan.stop' : 'scan.start';
      toggleText.textContent = I18N.t(toggleText.dataset.i18n);
      frame.classList.toggle('is-running', running);
      frame.hidden = Boolean(fallback);
      toggle.classList.toggle('primary', !fallback);
      photoButton.classList.toggle('primary', Boolean(fallback));
      photo.disabled = held || readingPhoto || !window.Html5Qrcode;
      for (const field of form.elements) field.disabled = held || readingPhoto;
    }
    async function changeCamera() {
      changing = true;
      // The live reader needs a measurable container, including when retrying.
      fallback = null;
      update();
      UI.notice('camera-notice');
      try {
        if (running) await stop();
        else await start('reader', token => {
          if (!readingPhoto) onIdentify({ token });
        });
      } catch (error) {
        const failure = error.code ? error : cameraError(error);
        fallback = failure.code;
        UI.showError('camera-notice', failure);
      } finally { changing = false; update(); }
    }
    toggle.addEventListener('click', changeCamera);
    photo.addEventListener('change', async () => {
      const file = photo.files[0];
      photo.value = '';
      if (!file || held || readingPhoto) return;
      readingPhoto = true;
      update();
      UI.notice('photo-notice');
      try {
        fileReader ??= new Html5Qrcode('photo-reader', { verbose: false });
        const raw = await fileReader.scanFile(file, false);
        await onIdentify({ token: qrToken(raw) });
      } catch (_) {
        UI.notice('photo-notice', 'warning', () => I18N.t('scan.noPhotoQR'));
      } finally {
        fileReader?.clear();
        readingPhoto = false;
        update();
      }
    });
    if (fallback) UI.showError('camera-notice', new ApiError(fallback, '', 0));
    update();
    if (!fallback && !new URLSearchParams(location.search).has('code')) changeCamera();
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (held) return;
      const code = input.value.trim();
      if (!code) {
        UI.notice('camera-notice', 'error', () => I18N.t('scan.needCode'));
        input.focus();
        return;
      }
      UI.notice('photo-notice');
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
