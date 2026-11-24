const notice = document.querySelector('#playout-notice');

function showNotice(message, bad) {
  if (!notice) return;
  notice.textContent = message;
  notice.classList.toggle('bad', Boolean(bad));
}

async function post(url, payload) {
  const response = await fetch(url, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.message || '请求失败');
  return result;
}

document.querySelector('#packets-form')?.addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button');
  button.disabled = true;
  showNotice('正在建立核对单…');
  try {
    await post(`/api/playout/${form.dataset.run}/packets`,
      Object.fromEntries(new FormData(form)));
    location.reload();
  } catch (error) {
    showNotice(error.message, true);
    button.disabled = false;
  }
});

document.querySelector('#receipt-form')?.addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button');
  button.disabled = true;
  showNotice('正在核对…');
  try {
    const result = await post(`/api/playout/${form.dataset.run}/receipts`,
      Object.fromEntries(new FormData(form)));
    showNotice(`采信 ${result.accepted} 条，重复去重 ${result.duplicate_receipts} 条；`
      + `确认没播 ${result.summary.missed_confirmed} · 回执未到 ${result.summary.pending_receipt} · `
      + `放错字幕 ${result.summary.wrong_caption} · 重放 ${result.summary.replayed_frames}`);
    setTimeout(() => location.reload(), 900);
  } catch (error) {
    showNotice(error.message, true);
    button.disabled = false;
  }
});

document.querySelector('#preview-form')?.addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button');
  button.disabled = true;
  showNotice('正在试算…');
  try {
    const result = await post('/api/playout/preview', Object.fromEntries(new FormData(form)));
    const s = result.summary;
    showNotice(`试算：签发 ${s.signed_frames} 帧，播对 ${s.by_status.PLAYED_OK} · 放错字幕 ${s.wrong_caption} `
      + `· 确认没播 ${s.missed_confirmed} · 回执未到 ${s.pending_receipt} · 重放 ${s.replayed_frames}`);
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    button.disabled = false;
  }
});
