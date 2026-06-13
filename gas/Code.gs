/**
 * 喵醫師的醫學期刊助理 — GAS 後端
 * 部署：Apps Script 編輯器 → 部署 → 新增部署作業 → 類型「網頁應用程式」
 *   執行身分：我；存取權：任何人 → 取得 /exec 網址貼進前端 app.js 的 API。
 */

const SHEET_ID = '1rHmu5k42PvHTF9GavqdCj5Gtr4lBfiuutIhSzBVh8_k';

function getSheet_(name) {
  return SpreadsheetApp.openById(SHEET_ID).getSheetByName(name);
}

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

function doGet(e) {
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
  return json_({ error: 'unknown action: ' + action });
}

function doPost(e) {
  const body = JSON.parse(e.postData.contents);
  if (body.action === 'update') {
    updateArticle_(body.collection_id, body.pmid, body.fields || {});
    return json_({ ok: true });
  }
  return json_({ error: 'unknown action' });
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
