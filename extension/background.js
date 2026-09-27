const AGENT_WS_URL = 'ws://127.0.0.1:8123/ws/extension';
const FLOWMUSIC_URL = 'https://www.flowmusic.app/';
const FLOWMUSIC_MATCH = ['https://www.flowmusic.app/*'];

let socket = null;
let reconnectTimer = null;
let state = 'disconnected';
let lastError = null;

function setState(next, error = null) {
  state = next;
  lastError = error;
  chrome.storage.local.set({ bridgeState: state, bridgeLastError: lastError });
}

async function flowMusicTabOpen() {
  return (await chrome.tabs.query({ url: FLOWMUSIC_MATCH })).length > 0;
}

async function sendHello() {
  if (socket?.readyState !== WebSocket.OPEN) return;
  socket.send(JSON.stringify({
    type: 'hello',
    version: chrome.runtime.getManifest().version,
    flowmusicTabOpen: await flowMusicTabOpen(),
  }));
}

function scheduleReconnect() {
  clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(connect, 3000);
}

function connect() {
  if (socket?.readyState === WebSocket.OPEN || socket?.readyState === WebSocket.CONNECTING) return;
  setState('connecting');
  try {
    socket = new WebSocket(AGENT_WS_URL);
  } catch (error) {
    socket = null;
    setState('error', error?.message || 'Cannot create local WebSocket');
    scheduleReconnect();
    return;
  }
  socket.onopen = async () => {
    setState('connected');
    await sendHello();
  };
  socket.onmessage = async (event) => {
    let message;
    try { message = JSON.parse(event.data); } catch { return; }
    if (message.type !== 'request' || message.action !== 'flowmusic_fetch') return;
    const response = await handleFlowMusicFetch(message.payload || {});
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'response', id: message.id, ...response }));
    }
  };
  socket.onerror = () => setState('error', 'Cannot connect to the local API');
  socket.onclose = () => {
    socket = null;
    setState('disconnected');
    scheduleReconnect();
  };
}

const allowedPaths = [
  /^\/__api\/projects$/,
  /^\/__api\/projects\/[^/?]+\/clips\/ids$/,
  /^\/__api\/projects\/[^/?]+\/conversations\/ids$/,
  /^\/__api\/conversations\/[^/?]+\/transcript$/,
  /^\/__api\/conversation$/,
  /^\/__api\/messages\/[^/?]+\/stream\?last_id=\d+$/,
  /^\/__api\/audio-create-song-status\/[^/?]+$/,
  /^\/__api\/download\/audio\/[^/?]+\?format=(m4a|wav)$/,
];

async function getFlowMusicTab() {
  const tabs = await chrome.tabs.query({ url: FLOWMUSIC_MATCH });
  let tab = tabs.find((item) => !item.discarded) || tabs[0];
  if (!tab) {
    tab = await chrome.tabs.create({ url: FLOWMUSIC_URL, active: false });
    await new Promise((resolve) => setTimeout(resolve, 3500));
  }
  if (tab?.discarded) {
    tab = await chrome.tabs.update(tab.id, { active: false });
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
  return tab;
}

async function reloadFlowMusicTab(tabId, timeoutMs = 15000) {
  return new Promise((resolve) => {
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      chrome.tabs.onUpdated.removeListener(onUpdated);
      resolve();
    };
    const onUpdated = (updatedTabId, changeInfo) => {
      if (updatedTabId === tabId && changeInfo.status === 'complete') finish();
    };
    const timer = setTimeout(finish, timeoutMs);
    chrome.tabs.onUpdated.addListener(onUpdated);
    chrome.tabs.reload(tabId).then(async () => {
      const tab = await chrome.tabs.get(tabId).catch(() => null);
      if (tab?.status === 'complete') finish();
    }).catch(finish);
  });
}

async function handleFlowMusicFetch(payload) {
  const {
    path,
    method = 'GET',
    body = null,
    responseMode = 'json',
    expectedOperations = 2,
  } = payload;
  if (typeof path !== 'string' || !allowedPaths.some((pattern) => pattern.test(path))) {
    return { status: 400, error: 'UNSUPPORTED_FLOWMUSIC_PATH' };
  }
  if (!['GET', 'POST'].includes(method) || !['json', 'text', 'sse', 'base64'].includes(responseMode)) {
    return { status: 400, error: 'INVALID_REQUEST_OPTIONS' };
  }
  try {
    const tab = await getFlowMusicTab();
    if (!tab?.id) return { status: 503, error: 'NO_FLOWMUSIC_TAB' };
    const executeRequest = async () => {
      const [execution] = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        world: 'MAIN',
        args: [path, method, body, responseMode, expectedOperations],
        func: async (requestPath, requestMethod, requestBody, mode, operationTarget) => {
        const parseSession = (raw) => {
          if (!raw || typeof raw !== 'string') return null;
          const candidates = [raw, raw.replace(/^base64-/, '')];
          try {
            const decodedUri = decodeURIComponent(raw);
            if (decodedUri !== raw) candidates.push(decodedUri, decodedUri.replace(/^base64-/, ''));
          } catch {}
          for (let index = 0; index < candidates.length && index < 4; index += 1) {
            const candidate = candidates[index];
            try {
              const value = JSON.parse(candidate);
              if (value?.access_token) return value;
              if (value?.currentSession?.access_token) return value.currentSession;
            } catch {}
            try {
              const normalized = candidate.replace(/-/g, '+').replace(/_/g, '/');
              const decoded = atob(normalized);
              if (decoded && decoded !== candidate) candidates.push(decoded);
            } catch {}
          }
          return null;
        };

        const tokenExpiry = (token) => {
          try {
            const payload = token.split('.')[1];
            const normalized = payload.replace(/-/g, '+').replace(/_/g, '/');
            const decoded = JSON.parse(atob(normalized));
            return Number(decoded.exp) || 0;
          } catch {
            return 0;
          }
        };

        const sessions = [];
        try {
          for (const key of Object.keys(localStorage)) {
            if (!key.includes('sb-') || !key.includes('auth-token')) continue;
            const session = parseSession(localStorage.getItem(key));
            if (session?.access_token) sessions.push(session);
          }
        } catch {}

        try {
          const groups = new Map();
          for (const entry of document.cookie.split(';').map((value) => value.trim())) {
            const separator = entry.indexOf('=');
            if (separator < 0) continue;
            const name = entry.slice(0, separator);
            if (!name.includes('sb-') || !name.includes('auth-token')) continue;
            const base = name.replace(/\.\d+$/, '');
            const parts = groups.get(base) || [];
            const chunkMatch = name.match(/\.(\d+)$/);
            parts.push({
              index: chunkMatch ? Number(chunkMatch[1]) : -1,
              value: entry.slice(separator + 1),
            });
            groups.set(base, parts);
          }
          for (const parts of groups.values()) {
            parts.sort((a, b) => a.index - b.index);
            const session = parseSession(parts.map((part) => part.value).join(''));
            if (session?.access_token) sessions.push(session);
          }
        } catch {}

        const now = Math.floor(Date.now() / 1000);
        sessions.sort((a, b) => tokenExpiry(b.access_token) - tokenExpiry(a.access_token));
        const session = sessions.find((item) => tokenExpiry(item.access_token) > now + 15)
          || sessions[0];
        const accessToken = session?.access_token || null;

        const headers = {
          accept: ['text', 'sse'].includes(mode)
            ? 'text/event-stream'
            : mode === 'base64'
              ? 'audio/*'
              : 'application/json',
        };
        if (accessToken) headers.authorization = `Bearer ${accessToken}`;
        if (requestBody !== null && requestMethod !== 'GET') {
          headers['content-type'] = 'application/json';
        }
        const response = await fetch(requestPath, {
          method: requestMethod,
          headers,
          credentials: 'include',
          body: requestBody !== null && requestMethod !== 'GET'
            ? JSON.stringify(requestBody)
            : undefined,
        });
        if (mode === 'base64') {
          const bytes = new Uint8Array(await response.arrayBuffer());
          let binary = '';
          for (let index = 0; index < bytes.length; index += 0x8000) {
            binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
          }
          return {
            status: response.status,
            data: {
              base64: btoa(binary),
              contentType: response.headers.get('content-type') || 'application/octet-stream',
            },
          };
        }
        if (mode === 'sse' && response.body) {
          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let snapshot = '';
          const deadline = Date.now() + 30000;
          const readWithTimeout = (timeoutMs) => new Promise((resolve, reject) => {
            const timer = setTimeout(() => resolve({ timedOut: true }), timeoutMs);
            reader.read().then(
              (result) => {
                clearTimeout(timer);
                resolve({ timedOut: false, result });
              },
              (error) => {
                clearTimeout(timer);
                reject(error);
              },
            );
          });
          try {
            while (Date.now() < deadline) {
              const next = await readWithTimeout(Math.min(5000, deadline - Date.now()));
              if (next.timedOut) break;
              const { done, value } = next.result;
              if (value) snapshot += decoder.decode(value, { stream: !done });
              if (done && !/event:\s*(?:complete|final)\b/.test(snapshot)) {
                snapshot += '\n\nevent: final\ndata: {}\n\n';
              }

              const operationIds = new Set();
              const operationPattern = /"operation_id(?:_b)?"\s*:\s*"([^"]+)"/g;
              for (const match of snapshot.matchAll(operationPattern)) operationIds.add(match[1]);
              if (
                operationIds.size >= Math.max(1, Number(operationTarget) || 2)
                || /event:\s*(?:complete|final|error)\b/.test(snapshot)
                || snapshot.includes('Stream not found')
                || done
              ) break;
            }
          } finally {
            reader.cancel().catch(() => {});
          }
          return { status: response.status, data: snapshot };
        }
        const text = await response.text();
        if (mode === 'text') return { status: response.status, data: text };
        try { return { status: response.status, data: JSON.parse(text) }; }
        catch { return { status: response.status, data: text }; }
        },
      });
      return execution?.result || { status: 502, error: 'NO_BROWSER_RESULT' };
    };

    let result = await executeRequest();
    if ([401, 403].includes(Number(result?.status))) {
      // Loading the first-party app invokes Supabase getSession(), which
      // refreshes an expired access token using the browser's refresh token.
      await reloadFlowMusicTab(tab.id);
      result = await executeRequest();
    }
    return result;
  } catch (error) {
    return { status: 502, error: error?.message || 'FLOWMUSIC_BROWSER_REQUEST_FAILED' };
  }
}

chrome.runtime.onMessage.addListener((message, _, sendResponse) => {
  if (message?.type === 'get_status') {
    flowMusicTabOpen().then((tabOpen) => sendResponse({ state, lastError, tabOpen }));
    return true;
  }
  if (message?.type === 'open_flowmusic') {
    chrome.tabs.create({ url: FLOWMUSIC_URL, active: true });
  }
  if (message?.type === 'reconnect') connect();
  return false;
});

chrome.alarms.create('keepalive', { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener(() => {
  if (socket?.readyState !== WebSocket.OPEN) connect();
  else sendHello();
});
chrome.runtime.onInstalled.addListener(connect);
chrome.runtime.onStartup.addListener(connect);
connect();
