/**
 * 喵醫師的醫學期刊助理 — GAS 後端
 * 部署：Apps Script 編輯器 → 部署 → 新增部署作業 → 類型「網頁應用程式」
 *   執行身分：我；存取權：任何人 → 取得 /exec 網址貼進前端 app.js 的 API。
 */

const SHEET_ID = '1rHmu5k42PvHTF9GavqdCj5Gtr4lBfiuutIhSzBVh8_k';

function getSheet_(name) {
  return SpreadsheetApp.openById(SHEET_ID).getSheetByName(name);
}

// 確保分頁存在、且包含所有需要的欄位（缺的補在尾端，與 Python 端 schema 一致）
function ensureSheet_(name, headers) {
  const ss = SpreadsheetApp.openById(SHEET_ID);
  let sh = ss.getSheetByName(name);
  if (!sh) {
    sh = ss.insertSheet(name);
    sh.getRange(1, 1, 1, headers.length).setValues([headers]);
    return sh;
  }
  const existing = sh.getRange(1, 1, 1, Math.max(1, sh.getLastColumn())).getValues()[0];
  const missing = headers.filter(h => existing.indexOf(h) === -1);
  if (missing.length) {
    sh.getRange(1, existing.length + 1, 1, missing.length).setValues([missing]);
  }
  return sh;
}

const COLLECTIONS_HEADERS = ['collection_id', 'type', 'name', 'query',
  'created_at', 'last_synced_at', 'note', 'status'];
const JOBS_HEADERS = ['job_id', 'type', 'params', 'status',
  'created_at', 'finished_at', 'message'];

function readRecords_(name) {
  const sh = getSheet_(name);
  const values = sh.getDataRange().getValues();
  const headers = values.shift();
  const idKey = headers[0]; // 第一欄當主鍵，過濾空白列
  return values
    .filter(row => String(row[0]).trim() !== '')
    .map(row => {
      const obj = {};
      headers.forEach((h, i) => (obj[h] = row[i]));
      return obj;
    });
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

// 通關碼存在「專案設定 → 指令碼屬性」的 API_TOKEN，不寫進公開的程式碼
function checkToken_(token) {
  const secret = PropertiesService.getScriptProperties().getProperty('API_TOKEN');
  return !!secret && String(token) === secret;
}

function doGet(e) {
  if (!checkToken_(e.parameter.token)) return json_({ error: 'unauthorized' });
  const action = (e.parameter.action || '').toLowerCase();
  if (action === 'collections') {
    return json_({ collections: readRecords_('Collections') });
  }
  if (action === 'articles') {
    const cid = String(e.parameter.collection || '');
    const arts = readRecords_('Articles')
      .filter(a => String(a.collection_id) === cid);
    return json_({ articles: arts });
  }
  if (action === 'jobs') {
    ensureSheet_('Jobs', JOBS_HEADERS);  // 還沒有 Jobs 分頁時先建好，避免讀取報錯
    // 只回最近 20 件，給前端顯示工作進度
    const jobs = readRecords_('Jobs').slice(-20).reverse();
    return json_({ jobs: jobs });
  }
  return json_({ error: 'unknown action: ' + action });
}

function doPost(e) {
  const body = JSON.parse(e.postData.contents);
  if (!checkToken_(body.token)) return json_({ error: 'unauthorized' });

  if (body.action === 'update') {
    updateArticle_(body.collection_id, body.pmid, body.fields || {});
    return json_({ ok: true });
  }
  // 通用：把一件工作排進 Jobs 佇列（期別抓取、產摘要…）
  if (body.action === 'enqueue') {
    const jid = enqueueJob_(body.type, body.params || {});
    return json_({ ok: true, job_id: jid });
  }
  // 主題模式：建立一個 draft 集合 + 排 draft_topic 工作（worker 會起草 query）
  if (body.action === 'new_topic') {
    const cid = 'topic-' + nowStamp_();
    addCollection_(cid, 'topic', body.name || body.topic, '', body.topic || '', 'draft');
    const jid = enqueueJob_('draft_topic', { collection_id: cid });
    return json_({ ok: true, collection_id: cid, job_id: jid });
  }
  // 主題模式：使用者確認/微調 query 後，啟用集合 + 排 ingest_topic 工作
  if (body.action === 'confirm_topic') {
    updateCollection_(body.collection_id, { query: body.query, status: 'active' });
    const jid = enqueueJob_('ingest_topic',
      { collection_id: body.collection_id, max: body.max || 50 });
    return json_({ ok: true, job_id: jid });
  }
  return json_({ error: 'unknown action' });
}

function nowStamp_() {
  return Utilities.formatDate(new Date(), 'Asia/Taipei', 'yyyyMMddHHmmss');
}

function nowStr_() {
  return Utilities.formatDate(new Date(), 'Asia/Taipei', 'yyyy-MM-dd HH:mm:ss');
}

// Jobs 表頭：job_id, type, params, status, created_at, finished_at, message
function enqueueJob_(type, params) {
  const sh = ensureSheet_('Jobs', JOBS_HEADERS);
  const jid = 'job-' + nowStamp_() + '-' + Math.floor(Math.random() * 1000);
  sh.appendRow([jid, type, JSON.stringify(params), 'pending', nowStr_(), '', '']);
  return jid;
}

// Collections 表頭：collection_id, type, name, query, created_at, last_synced_at, note, status
function addCollection_(cid, type, name, query, note, status) {
  const sh = ensureSheet_('Collections', COLLECTIONS_HEADERS);
  sh.appendRow([cid, type, name, query, nowStr_(), '', note, status]);
}

function updateCollection_(cid, fields) {
  const sh = ensureSheet_('Collections', COLLECTIONS_HEADERS);
  const values = sh.getDataRange().getValues();
  const headers = values[0];
  const colId = headers.indexOf('collection_id');
  for (let r = 1; r < values.length; r++) {
    if (String(values[r][colId]) === String(cid)) {
      Object.keys(fields).forEach(key => {
        const c = headers.indexOf(key);
        if (c >= 0) sh.getRange(r + 1, c + 1).setValue(fields[key]);
      });
      return;
    }
  }
}

function updateArticle_(collectionId, pmid, fields) {
  const sh = getSheet_('Articles');
  const values = sh.getDataRange().getValues();
  const headers = values[0];
  const colId = headers.indexOf('collection_id');
  const colPmid = headers.indexOf('pmid');
  for (let r = 1; r < values.length; r++) {
    if (String(values[r][colId]) === String(collectionId) &&
        String(values[r][colPmid]) === String(pmid)) {
      Object.keys(fields).forEach(key => {
        const c = headers.indexOf(key);
        if (c >= 0) sh.getRange(r + 1, c + 1).setValue(fields[key]);
      });
      return;
    }
  }
}
