// GAS 網頁應用程式 /exec 網址
const API = 'https://script.google.com/macros/s/AKfycbxjR_bN94mGeo5jQmIBK6oXIAIiPnSneslshRbqBgSCyUwLOF-phYs2GVtuyYXUJhiaOQ/exec';

let articles = [];
let currentCid = '';
let openPmid = null;

const STATUS_LABEL = {
  candidate: '待篩選', kept: '待摘要', summarized: '可閱讀',
  read: '已讀', dropped: '不看', no_abstract: '無摘要',
};

async function getJSON(params) {
  // 加時間戳 + no-store，避免瀏覽器快取 GAS 回應導致重新整理拿到舊資料
  const r = await fetch(
    API + '?' + new URLSearchParams({ ...params, _: Date.now() }),
    { cache: 'no-store' }
  );
  return r.json();
}

// 不設 header，維持 text/plain 避免 GAS 的 CORS preflight（與小說站同款）
async function post(body) {
  await fetch(API, { method: 'POST', body: JSON.stringify(body) });
}

function toast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.remove('hidden');
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.add('hidden'), 1800);
}

async function loadCollections() {
  const data = await getJSON({ action: 'collections' });
  const sel = document.getElementById('collection-select');
  sel.innerHTML = '';
  (data.collections || []).reverse().forEach(c => {
    const o = document.createElement('option');
    o.value = c.collection_id;
    o.textContent = c.name || c.collection_id;
    sel.appendChild(o);
  });
  if (sel.value) { currentCid = sel.value; await loadArticles(currentCid); }
}

async function loadArticles(cid) {
  const data = await getJSON({ action: 'articles', collection: cid });
  articles = data.articles || [];
  renderList();
}

function renderList() {
  const hideDropped = document.getElementById('hide-dropped').checked;
  const list = document.getElementById('list');
  list.innerHTML = '';

  const shown = articles.filter(a => !(hideDropped && a.status === 'dropped'));
  if (!shown.length) {
    list.innerHTML = '<div class="empty">這個集合還沒有文章，或都被隱藏了。</div>';
    return;
  }

  shown.forEach(a => {
    const card = document.createElement('div');
    card.className = 'card' + (a.status === 'dropped' ? ' dropped' : '');
    card.innerHTML = `
      <div class="zh">${esc(a.title_zh || a.title_en)}</div>
      <div class="en">${esc(a.title_en)}</div>
      <div class="meta">${esc(a.journal)} · ${esc(a.pub_date)} · ${esc(a.authors)}</div>
      <div>
        <span class="badge b-${a.status}">${STATUS_LABEL[a.status] || a.status}</span>
      </div>
      <div class="actions">${actionsFor(a)}</div>
    `;
    card.querySelectorAll('button[data-act]').forEach(btn => {
      btn.addEventListener('click', () => onAction(a, btn.dataset.act));
    });
    list.appendChild(card);
  });
}

function actionsFor(a) {
  const btns = [];
  if (a.status === 'candidate' || a.status === 'no_abstract') {
    btns.push(`<button data-act="keep" class="primary">✓ 留著</button>`);
    btns.push(`<button data-act="drop">✗ 不看</button>`);
  } else if (a.status === 'kept') {
    btns.push(`<button data-act="drop">✗ 不看</button>`);
    btns.push(`<span class="meta">（等下次產摘要）</span>`);
  } else if (a.status === 'summarized' || a.status === 'read') {
    btns.push(`<button data-act="read" class="primary">📖 閱讀</button>`);
  }
  return btns.join('');
}

async function onAction(a, act) {
  if (act === 'keep') return setStatus(a, 'kept');
  if (act === 'drop') return setStatus(a, 'dropped');
  if (act === 'read') return openReader(a);
}

async function setStatus(a, status) {
  a.status = status;
  renderList();
  await post({ action: 'update', collection_id: a.collection_id, pmid: a.pmid, fields: { status } });
  toast('已更新');
}

function openReader(a) {
  openPmid = a.pmid;
  const reader = document.getElementById('reader');
  reader.classList.remove('hidden');
  const body = document.getElementById('reader-body');
  const summary = a.summary || '*（尚無摘要）*';
  const link = `\n\n[🔗 在 PubMed 開啟原文](${a.url})`;
  body.innerHTML = marked.parse(summary + link);
  document.getElementById('note-input').value = a.note || '';
  reader.scrollTop = 0;
}

async function saveNote() {
  const a = articles.find(x => x.pmid === openPmid);
  if (!a) return;
  a.note = document.getElementById('note-input').value;
  await post({ action: 'update', collection_id: a.collection_id, pmid: a.pmid, fields: { note: a.note } });
  toast('註記已儲存');
}

async function markRead() {
  const a = articles.find(x => x.pmid === openPmid);
  if (!a) return;
  a.status = 'read';
  renderList();
  await post({ action: 'update', collection_id: a.collection_id, pmid: a.pmid, fields: { status: 'read' } });
  toast('已標為已讀');
}

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

document.getElementById('collection-select').addEventListener('change', e => {
  currentCid = e.target.value;
  loadArticles(currentCid);
});
document.getElementById('hide-dropped').addEventListener('change', renderList);
document.getElementById('btn-refresh').addEventListener('click', async (e) => {
  const btn = e.currentTarget;
  const old = btn.textContent;
  btn.disabled = true;
  btn.textContent = '↻ 更新中…';
  await loadArticles(currentCid);
  btn.textContent = old;
  btn.disabled = false;
  toast('已重新整理');
});
document.getElementById('reader-close').addEventListener('click', () => {
  document.getElementById('reader').classList.add('hidden');
});
document.getElementById('btn-save-note').addEventListener('click', saveNote);
document.getElementById('btn-mark-read').addEventListener('click', markRead);

loadCollections();
