// GAS 網頁應用程式 /exec 網址
const API = 'https://script.google.com/macros/s/AKfycbxjR_bN94mGeo5jQmIBK6oXIAIiPnSneslshRbqBgSCyUwLOF-phYs2GVtuyYXUJhiaOQ/exec';

let collections = [];
let articles = [];
let currentCid = '';
let openPmid = null;

const STATUS_LABEL = {
  candidate: '待篩選', kept: '待摘要', summarized: '可閱讀',
  read: '已讀', dropped: '不看', no_abstract: '無摘要',
};
const JOB_LABEL = {
  pending: '等待中', running: '執行中', done: '完成', error: '失敗',
};

// 通關碼存在 localStorage，由頁面內輸入框設定（不用瀏覽器原生 prompt）
function getToken() { return localStorage.getItem('mjr_token') || ''; }

function showGate(msg) {
  document.getElementById('token-msg').textContent = msg || '';
  document.getElementById('token-gate').classList.remove('hidden');
  document.getElementById('token-input').focus();
}
function hideGate() { document.getElementById('token-gate').classList.add('hidden'); }

async function getJSON(params) {
  // 加時間戳 + no-store，避免瀏覽器快取 GAS 回應導致重新整理拿到舊資料
  const r = await fetch(
    API + '?' + new URLSearchParams({ ...params, token: getToken(), _: Date.now() }),
    { cache: 'no-store' }
  );
  const data = await r.json();
  if (data.error === 'unauthorized') {
    localStorage.removeItem('mjr_token');
    showGate('通關碼錯誤，請重新輸入');
    throw new Error('unauthorized');
  }
  return data;
}

// 不設 header，維持 text/plain 避免 GAS 的 CORS preflight（與小說站同款）。
// GAS 對 POST 不回 CORS 標頭，瀏覽器讀不到回應 → 一律當「送出即可」：
// 請求其實已送達並執行（寫入會成功），讀不到回應屬正常，不讓它丟錯卡住流程。
async function post(body) {
  try {
    const r = await fetch(API, {
      method: 'POST', body: JSON.stringify({ ...body, token: getToken() }),
    });
    return await r.json();
  } catch (e) {
    return { _unreadable: true };  // 跨來源讀不到回應，但工作已送達 GAS
  }
}

function toast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.remove('hidden');
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.add('hidden'), 2200);
}

function currentCollection() {
  return collections.find(c => String(c.collection_id) === String(currentCid));
}

// 集合狀態：空白視為 active（相容舊資料）
function colStatus(c) { return (c && c.status) ? String(c.status) : 'active'; }

async function loadCollections() {
  const data = await getJSON({ action: 'collections' });
  collections = data.collections || [];
  const sel = document.getElementById('collection-select');
  sel.innerHTML = '';
  [...collections].reverse().forEach(c => {
    const o = document.createElement('option');
    o.value = c.collection_id;
    const draft = colStatus(c) === 'draft' ? '（草稿）' : '';
    const tag = c.type === 'topic' ? '🔍 ' : '📖 ';
    o.textContent = tag + (c.name || c.collection_id) + draft;
    sel.appendChild(o);
  });
  if (sel.value) { currentCid = sel.value; await refreshCurrent(); }
}

// 依目前選到的集合，決定要顯示「文章清單」還是「草稿確認面板」
async function refreshCurrent() {
  const c = currentCollection();
  const draftPanel = document.getElementById('draft');
  if (c && c.type === 'topic' && colStatus(c) === 'draft') {
    document.getElementById('list').innerHTML = '';
    showDraftPanel(c);
  } else {
    draftPanel.classList.add('hidden');
    await loadArticles(currentCid);
  }
  // 主題集合才需要產摘要鈕？其實期別也要，保留全部可用
  document.getElementById('btn-summarize').classList.toggle(
    'hidden', !!(c && c.type === 'topic' && colStatus(c) === 'draft'));
  updateWatchToggle(c);
}

// 訂閱開關只對「已啟用的主題集合」有意義（期別不重掃、draft 還沒成形）
function updateWatchToggle(c) {
  const label = document.getElementById('watch-label');
  const box = document.getElementById('watch-check');
  const eligible = !!(c && c.type === 'topic' && colStatus(c) === 'active');
  label.classList.toggle('hidden', !eligible);
  if (eligible) box.checked = String(c.watch || '').toLowerCase() === 'on';
}

function showDraftPanel(c) {
  const panel = document.getElementById('draft');
  document.getElementById('draft-name').textContent = c.name || c.collection_id;
  const ta = document.getElementById('draft-query');
  ta.value = c.query || '';
  ta.placeholder = '（尚未起草。請先跑 python producer.py run-jobs，再回來重新整理）';
  panel.classList.remove('hidden');
  panel.dataset.cid = c.collection_id;
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

  let shown = articles.filter(a => !(hideDropped && a.status === 'dropped'));
  // 主題模式：有語意排序分數時，相關度高的排前面
  if (shown.some(a => a.relevance_score !== '' && a.relevance_score != null)) {
    shown = [...shown].sort((x, y) => (Number(y.relevance_score) || 0) - (Number(x.relevance_score) || 0));
  }
  if (!shown.length) {
    list.innerHTML = '<div class="empty">這個集合還沒有文章，或都被隱藏了。</div>';
    return;
  }

  shown.forEach(a => {
    const card = document.createElement('div');
    card.className = 'card' + (a.status === 'dropped' ? ' dropped' : '');
    const score = (a.relevance_score !== '' && a.relevance_score != null)
      ? `<span class="score" title="AI 語意相關度">★ ${a.relevance_score}</span>` : '';
    card.innerHTML = `
      <div class="zh">${esc(a.title_zh || a.title_en)}</div>
      <div class="en">${esc(a.title_en)}</div>
      <div class="meta">${esc(a.journal)} · ${esc(a.pub_date)} · ${esc(a.authors)}</div>
      <div>
        <span class="badge b-${a.status}">${STATUS_LABEL[a.status] || a.status}</span>
        ${score}
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
  } else if (a.status === 'dropped') {
    btns.push(`<button data-act="restore">↩ 還原</button>`);
  }
  return btns.join('');
}

async function onAction(a, act) {
  if (act === 'keep') return setStatus(a, 'kept');
  if (act === 'drop') return setStatus(a, 'dropped');
  if (act === 'restore') return setStatus(a, 'candidate');
  if (act === 'read') return openReader(a);
}

async function setStatus(a, status) {
  a.status = status;
  renderList();
  await post({ action: 'update', collection_id: a.collection_id, pmid: a.pmid, fields: { status } });
  toast('已更新');
}

// 容錯渲染：相容不同版本的 marked，載入失敗時退回純文字
function renderMarkdown(md) {
  try {
    if (typeof marked !== 'undefined') {
      if (typeof marked.parse === 'function') return marked.parse(md);
      if (typeof marked === 'function') return marked(md);
    }
  } catch (e) { /* 落到下面的純文字退路 */ }
  return esc(md).replace(/\n/g, '<br>');
}

function openReader(a) {
  openPmid = a.pmid;
  const reader = document.getElementById('reader');
  reader.classList.remove('hidden');
  const body = document.getElementById('reader-body');
  const summary = a.summary || '*（這篇尚未產生摘要，請先標 kept 再產摘要）*';
  const link = `\n\n[🔗 在 PubMed 開啟原文](${a.url})`;
  body.innerHTML = renderMarkdown(summary + link);
  document.getElementById('note-input').value = a.note || '';
  reader.scrollTop = 0;
  // 手機單欄時面板在頁尾，捲過去才看得到
  reader.scrollIntoView({ behavior: 'smooth', block: 'start' });
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

// 下載單篇摘要為 Markdown 檔（摘要本身已含標題與文獻資訊，只補原文連結）
function downloadSummary() {
  const a = articles.find(x => x.pmid === openPmid);
  if (!a || !a.summary) { toast('這篇還沒有摘要'); return; }
  const md = `${a.summary}\n\n🔗 PubMed 原文：${a.url}\n`;
  const safe = String(a.title_zh || a.title_en || a.pmid)
    .replace(/[\\/:*?"<>|]/g, '').slice(0, 40).trim();
  const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${a.pmid}_${safe}.md`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  toast('已下載摘要');
}

// 列印只印閱讀面板的摘要（靠 @media print 隱藏其他區塊），可在對話框存成 PDF
function printSummary() {
  const a = articles.find(x => x.pmid === openPmid);
  if (!a || !a.summary) { toast('這篇還沒有摘要'); return; }
  window.print();
}

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// --- M3：從網頁發起工作（寫進 Jobs 佇列，由本機 worker 推進）---

// 只開指定面板、關掉其他
function openOnly(id) {
  ['form-issue', 'form-topic', 'jobs-panel'].forEach(p => {
    document.getElementById(p).classList.toggle('hidden', p !== id);
  });
}
function closePanels() {
  ['form-issue', 'form-topic', 'jobs-panel'].forEach(
    p => document.getElementById(p).classList.add('hidden'));
}

async function submitIssue(e) {
  e.preventDefault();
  const journal = document.getElementById('issue-journal').value.trim();
  const year = parseInt(document.getElementById('issue-year').value, 10);
  const month = parseInt(document.getElementById('issue-month').value, 10);
  const max = parseInt(document.getElementById('issue-max').value, 10) || 50;
  if (!journal || !year || !month) { toast('請填期刊、年、月'); return; }
  await post({ action: 'enqueue', type: 'ingest_issue', params: { journal, year, month, max } });
  closePanels();
  toast('已排入佇列，請到本機跑 run-jobs');
}

async function submitTopic(e) {
  e.preventDefault();
  const name = document.getElementById('topic-name').value.trim();
  const topic = document.getElementById('topic-desc').value.trim();
  if (!topic) { toast('請描述主題'); return; }
  await post({ action: 'new_topic', name: name || topic, topic });
  document.getElementById('topic-name').value = '';
  document.getElementById('topic-desc').value = '';
  closePanels();
  toast('已建立草稿並排入起草工作，跑完 run-jobs 後重新整理');
}

async function confirmTopic() {
  const panel = document.getElementById('draft');
  const cid = panel.dataset.cid;
  const query = document.getElementById('draft-query').value.trim();
  const max = parseInt(document.getElementById('draft-max').value, 10) || 80;
  if (!cid || !query) { toast('檢索式不可為空'); return; }
  await post({ action: 'confirm_topic', collection_id: cid, query, max });
  toast('已確認，請跑 run-jobs 抓取');
  panel.classList.add('hidden');
}

async function summarizeCurrent() {
  if (!currentCid) return;
  await post({ action: 'enqueue', type: 'summarize', params: { collection: currentCid } });
  toast('已排入產摘要工作，跑 run-jobs 後重新整理');
}

// 切換目前主題集合的訂閱狀態（排程會重掃 watch=on 的集合補新文章）
async function toggleWatch(e) {
  const c = currentCollection();
  if (!c) return;
  const on = e.target.checked;
  c.watch = on ? 'on' : 'off';
  await post({ action: 'set_watch', collection_id: c.collection_id, watch: on });
  toast(on ? '已訂閱，排程會自動補新文章' : '已取消訂閱');
}

// 立即執行（雲端）：請 GAS 用 PAT 觸發 GitHub Actions 跑掉佇列裡的工作
async function runNow(e) {
  const btn = e.currentTarget;
  const old = btn.textContent;
  btn.disabled = true;
  btn.textContent = '⚡ 觸發中…';
  try {
    const res = await post({ action: 'run_now' });
    // 讀得到回應且明確報錯（如 GH_PAT 未設）才顯示失敗；
    // 讀不到回應（CORS）時請求其實已送達，樂觀視為已觸發。
    if (res && res.error) toast('觸發失敗：' + res.error);
    else toast('已觸發雲端執行，約一兩分鐘後到「工作狀態」或按「重新整理」看結果');
  } finally {
    btn.textContent = old;
    btn.disabled = false;
  }
}

async function loadJobs() {
  const data = await getJSON({ action: 'jobs' });
  const box = document.getElementById('jobs-list');
  const jobs = data.jobs || [];
  if (!jobs.length) { box.innerHTML = '<div class="empty">目前沒有工作。</div>'; return; }
  box.innerHTML = jobs.map(j => `
    <div class="job j-${j.status}">
      <span class="job-type">${esc(j.type)}</span>
      <span class="job-status">${JOB_LABEL[j.status] || j.status}</span>
      <span class="job-time">${esc(j.created_at)}</span>
      ${j.message ? `<div class="job-msg">${esc(j.message)}</div>` : ''}
    </div>`).join('');
}

// --- 事件綁定 ---

document.getElementById('collection-select').addEventListener('change', e => {
  currentCid = e.target.value;
  refreshCurrent();
});
document.getElementById('hide-dropped').addEventListener('change', renderList);
document.getElementById('btn-refresh').addEventListener('click', async (e) => {
  const btn = e.currentTarget;
  const old = btn.textContent;
  btn.disabled = true;
  btn.textContent = '↻ 更新中…';
  await loadCollections();
  btn.textContent = old;
  btn.disabled = false;
  toast('已重新整理');
});
document.getElementById('reader-close').addEventListener('click', () => {
  document.getElementById('reader').classList.add('hidden');
});
document.getElementById('btn-save-note').addEventListener('click', saveNote);
document.getElementById('btn-mark-read').addEventListener('click', markRead);
document.getElementById('btn-download').addEventListener('click', downloadSummary);
document.getElementById('btn-print').addEventListener('click', printSummary);

document.getElementById('btn-new-issue').addEventListener('click', () => openOnly('form-issue'));
document.getElementById('btn-new-topic').addEventListener('click', () => openOnly('form-topic'));
document.getElementById('btn-jobs').addEventListener('click', async () => {
  openOnly('jobs-panel');
  await loadJobs();
});
document.getElementById('btn-summarize').addEventListener('click', summarizeCurrent);
document.getElementById('btn-run-now').addEventListener('click', runNow);
document.getElementById('watch-check').addEventListener('change', toggleWatch);
document.getElementById('form-issue').addEventListener('submit', submitIssue);
document.getElementById('form-topic').addEventListener('submit', submitTopic);
document.getElementById('btn-confirm-topic').addEventListener('click', confirmTopic);
document.querySelectorAll('[data-close]').forEach(btn => {
  btn.addEventListener('click', () => document.getElementById(btn.dataset.close).classList.add('hidden'));
});

function submitToken() {
  const t = document.getElementById('token-input').value.trim();
  if (!t) return;
  localStorage.setItem('mjr_token', t);
  document.getElementById('token-input').value = '';
  hideGate();
  startApp();
}
document.getElementById('token-submit').addEventListener('click', submitToken);
document.getElementById('token-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') submitToken();
});

async function startApp() {
  try { await loadCollections(); }
  catch (e) { /* unauthorized 時已顯示通關碼輸入框 */ }
}

if (getToken()) startApp();
else showGate();
