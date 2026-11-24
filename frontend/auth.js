/* Login / signup pages ke liye chhota shared code. */
(() => {
  'use strict';
  const CFG = window.MEDORA_CONFIG || {};
  const API = (CFG.API || 'http://127.0.0.1:8000').replace(/\/$/, '');
  let session = null;
  try { session = JSON.parse(sessionStorage.getItem('medora') || 'null'); } catch (e) { }
  const saveSession = s => { try { sessionStorage.setItem('medora', JSON.stringify(s)); } catch (e) { } };
  async function api(path, { method = 'GET', body } = {}) {
    let res;
    try { res = await fetch(API + path, { method, headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined }); }
    catch (e) { throw new Error('Cannot reach the server. Is the backend running at ' + API + '?'); }
    let data = null; try { data = await res.json(); } catch (e) { }
    if (!res.ok) {
      const d = data && data.detail;
      if (Array.isArray(d) && d[0] && d[0].msg) throw new Error(String(d[0].msg).replace(/^Value error, /, ''));
      throw new Error(typeof d === 'string' ? d : 'Error ' + res.status);
    }
    return data;
  }
  window.MedoraAuth = { API, api, session, saveSession, params: new URLSearchParams(location.search), home: role => { location.href = 'index.html#/' + role; } };
})();
