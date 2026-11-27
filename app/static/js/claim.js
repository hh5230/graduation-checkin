(() => {
  'use strict';

  const { byId } = UI;
  const form = byId('claim-form');
  const entry = byId('claim-entry');
  const result = byId('claim-result');
  const image = byId('claim-image');
  const download = byId('claim-download');
  const submit = form.querySelector('button[type=submit]');
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (submit.disabled) return;
    submit.disabled = true;
    UI.notice('claim-notice');
    try {
      const data = await API.post('/api/public/claim', {
        participant_code: form.elements.participant_code.value.trim().toUpperCase(),
        email: form.elements.email.value.trim().toLowerCase()
      });
      byId('claim-name').textContent = data.participant.name;
      byId('claim-code').textContent = data.participant.participant_code;
      byId('claim-status').replaceChildren(UI.badge(data.participant.status));
      image.src = 'data:image/png;base64,' + data.qr_png_base64;
      download.href = image.src;
      download.download = data.qr_filename;
      entry.hidden = true;
      result.hidden = false;
      byId('claim-name').focus();
    } catch (error) {
      UI.notice('claim-notice', 'error', () => {
        const seconds = error.details?.retry_after;
        return error.code === 'RATE_LIMITED' && Number.isFinite(seconds)
          ? I18N.t('claim.retry', { seconds }) : UI.errorText(error);
      });
    } finally { submit.disabled = false; }
  });
  byId('claim-again').addEventListener('click', () => {
    result.hidden = true;
    entry.hidden = false;
    image.removeAttribute('src');
    download.removeAttribute('href');
    form.reset();
    form.elements.participant_code.focus();
  });
})();
