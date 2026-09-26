function render(id, text, ok) {
  const element = document.getElementById(id);
  element.textContent = text;
  element.className = `value ${ok ? 'ok' : 'bad'}`;
}

async function refresh() {
  const status = await chrome.runtime.sendMessage({ type: 'get_status' });
  render('agent', status?.state === 'connected' ? 'Connected' : 'Disconnected', status?.state === 'connected');
  render('tab', status?.tabOpen ? 'Open' : 'Not open', status?.tabOpen);
  document.getElementById('error').textContent = status?.lastError || '';
}

document.getElementById('open').addEventListener('click', () => {
  chrome.runtime.sendMessage({ type: 'open_flowmusic' });
});
document.getElementById('retry').addEventListener('click', () => {
  chrome.runtime.sendMessage({ type: 'reconnect' });
  setTimeout(refresh, 500);
});
refresh();

