(() => {
'use strict';
const CFG = window.MEDORA_CONFIG || {};
const API = (CFG.API || 'http://127.0.0.1:8000').replace(/\/$/, '');
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const SPOTS = [
  ['Rajpur Road, Dehradun', 30.3350, 78.0600],
  ['Clock Tower, Dehradun', 30.3244, 78.0419],
  ['Jolly Grant Airport', 30.1897, 78.1803],
  ['Har Ki Pauri, Haridwar', 29.9567, 78.1693],
  ['Laxman Jhula, Rishikesh', 30.1260, 78.3280],
  ['IIT Roorkee', 29.8649, 77.8966],
];
const RES_LABEL = { ER_BED: 'Emergency beds', ICU_BED: 'ICU beds', VENTILATOR: 'Ventilators', OT: 'Operation theatres' };
const NEED_LABEL = { ER_BED: 'Emergency bed', ICU_BED: 'ICU bed', VENTILATOR: 'Ventilator', OT: 'Operation theatre' };
const SEV_LABEL = { CRITICAL: 'Critical', MODERATE: 'Moderate', LOW: 'Low' };

/* ---------- session + api ---------- */
let session = null;
try { session = JSON.parse(sessionStorage.getItem('medora') || 'null'); } catch (e) { }
function saveSession(s) { session = s; try { s ? sessionStorage.setItem('medora', JSON.stringify(s)) : sessionStorage.removeItem('medora'); } catch (e) { } }

async function api(path, { method = 'GET', body, auth = true } = {}) {
  const headers = {};
  if (body) headers['Content-Type'] = 'application/json';
  if (auth && session) headers.Authorization = 'Bearer ' + session.token;
  let res;
  try { res = await fetch(API + path, { method, headers, body: body ? JSON.stringify(body) : undefined }); }
  catch (e) { throw new Error('Cannot reach the server. Is the backend running at ' + API + '?'); }
  let data = null; try { data = await res.json(); } catch (e) { }
  if (res.status === 401 && auth && session) { logout(true); throw new Error('Signed out. Please sign in again.'); }
  if (!res.ok) {
    const d = data && data.detail;
    throw new Error(typeof d === 'string' ? d : d ? 'Please check the details and try again.' : 'Error ' + res.status);
  }
  return data;
}

let toastT;
function toast(msg, ms = 4200) {
  const t = $('#toast'); t.textContent = msg; t.hidden = false;
  clearTimeout(toastT); toastT = setTimeout(() => { t.hidden = true; }, ms);
}

/* ---------- geo ---------- */
function hav(a, b, c, d) {
  const r = Math.PI / 180, dp = (c - a) * r, dl = (d - b) * r;
  const x = Math.sin(dp / 2) ** 2 + Math.cos(a * r) * Math.cos(c * r) * Math.sin(dl / 2) ** 2;
  return 12742 * Math.asin(Math.sqrt(x));
}
const etaMin = km => Math.max(1, Math.round(km * 1.35 / 40 * 60));

/* ---------- road routes (OSRM, in-page) ---------- */
const routeCache = new Map();
async function fetchRoute(from, to) {
  const key = [from.lat, from.lon, to.lat, to.lon].map(v => (+v).toFixed(4)).join();
  if (routeCache.has(key)) return routeCache.get(key);
  try {
    const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), 7000);
    const r = await fetch(`https://router.project-osrm.org/route/v1/driving/${from.lon},${from.lat};${to.lon},${to.lat}?overview=full&geometries=geojson`, { signal: ctl.signal });
    clearTimeout(t);
    const rt = ((await r.json()).routes || [])[0]; if (!rt) throw new Error('no route');
    const out = { coords: rt.geometry.coordinates.map(([lo, la]) => [la, lo]), km: rt.distance / 1000, min: rt.duration / 60, approx: false };
    routeCache.set(key, out); return out;
  } catch (e) {                                   // routing service nahi mili: seedhi line (sirf fallback)
    const km = hav(from.lat, from.lon, to.lat, to.lon) * 1.35;
    return { coords: [[from.lat, from.lon], [to.lat, to.lon]], km, min: etaMin(km / 1.35), approx: true };
  }
}
function buildPath(coords) {
  const cum = [0];
  for (let i = 1; i < coords.length; i++) cum.push(cum[i - 1] + hav(coords[i - 1][0], coords[i - 1][1], coords[i][0], coords[i][1]));
  return { coords, cum, total: cum[cum.length - 1] || 0 };
}
function pointAt(path, d) {                       // route par d km aage ki jagah
  const { coords, cum, total } = path;
  if (d <= 0 || coords.length < 2) return { lat: coords[0][0], lon: coords[0][1] };
  if (d >= total) { const l = coords[coords.length - 1]; return { lat: l[0], lon: l[1] }; }
  let lo = 0, hi = cum.length - 1;
  while (hi - lo > 1) { const m = (lo + hi) >> 1; cum[m] <= d ? lo = m : hi = m; }
  const seg = cum[hi] - cum[lo] || 1e-9, f = (d - cum[lo]) / seg;
  return { lat: coords[lo][0] + (coords[hi][0] - coords[lo][0]) * f, lon: coords[lo][1] + (coords[hi][1] - coords[lo][1]) * f };
}
function drawRoute(map, store, route) {
  if (store.route) { store.route.remove(); store.route = null; }
  if (!map || !route) return;
  const opt = route.approx ? { dashArray: '8 8' } : {};
  store.route = L.layerGroup([
    L.polyline(route.coords, { color: '#fff', weight: 9, opacity: .9, ...opt }),
    L.polyline(route.coords, { color: '#0B5C7A', weight: 5, opacity: .95, ...opt }),
  ]).addTo(map);
}
function glide(marker, to, ms = 900) {            // marker ko naye point tak smooth sarkao
  if (!marker) return;
  cancelAnimationFrame(marker._g);
  const from = marker.getLatLng(), t0 = performance.now();
  const step = now => {
    const k = Math.min(1, (now - t0) / ms);
    marker.setLatLng([from.lat + (to[0] - from.lat) * k, from.lng + (to[1] - from.lng) * k]);
    if (k < 1) marker._g = requestAnimationFrame(step);
  };
  marker._g = requestAnimationFrame(step);
}

async function geocode(q) {
  const url = 'https://nominatim.openstreetmap.org/search?format=json&limit=1&countrycodes=in&viewbox=77.6,30.6,78.6,29.6&q=' + encodeURIComponent(q + ', Uttarakhand');
  const r = await fetch(url, { headers: { 'Accept-Language': 'en' } });
  const j = await r.json();
  if (!j.length) return null;
  return { lat: +j[0].lat, lon: +j[0].lon, label: j[0].display_name.split(',').slice(0, 3).join(',') };
}

/* ---------- maps (Leaflet + OpenStreetMap) ---------- */
function makeMap(el, center = [30.1, 78.1], zoom = 9) {
  if (typeof L === 'undefined') { el.innerHTML = '<p class="nomap">The map could not load. Check your internet connection. Everything else still works.</p>'; return null; }
  const m = L.map(el).setView(center, zoom);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; OpenStreetMap' }).addTo(m);
  return m;
}
const pin = (cls, label) => L.divIcon({ className: '', html: `<div class="pin ${cls}" title="${esc(label || '')}"></div>`, iconSize: [26, 26], iconAnchor: [13, 26] });
function setMarker(map, store, key, latlng, cls, label) {
  if (!map) return;
  if (store[key]) { cancelAnimationFrame(store[key]._g); store[key].setLatLng(latlng); }
  else { store[key] = L.marker(latlng, { icon: pin(cls, label), title: label }).addTo(map); }
}
function dropMarker(store, key) { if (store[key]) { cancelAnimationFrame(store[key]._g); store[key].remove(); delete store[key]; } }
function fit(map, pts, maxZoom = 14) {
  if (!map || !pts.length) return;
  if (pts.length === 1) { map.setView(pts[0], 14); return; }
  map.fitBounds(L.latLngBounds(pts), { padding: [40, 40], maxZoom });
}
let allHospitals = null;
async function loadHospitals() { if (!allHospitals) { try { allHospitals = await api('/hospitals', { auth: false }); } catch (e) { allHospitals = []; } } return allHospitals; }

/* ---------- live push (WebSocket, no polling) ---------- */
let view = null;
const WS = { sock: null, tries: 0, timer: null, ping: null, want: false, opened: false };
function setLive(state) {
  const el = $('#live'); if (!el) return; el.hidden = !session || !WS.want;
  el.className = 'live ' + state;
  el.lastElementChild.textContent = { on: 'Live', off: 'Offline, reconnecting', wait: 'Connecting' }[state];
}
function openWS() {
  if (!session) return; WS.want = true;
  if (WS.sock && WS.sock.readyState <= 1) return;
  setLive('wait');
  let s; try { s = new WebSocket(API.replace(/^http/, 'ws') + '/ws'); } catch (e) { return; }
  WS.sock = s; let opened = false;
  s.onopen = () => {
    opened = true; WS.tries = 0; setLive('on');
    s.send(JSON.stringify({ token: session.token }));          // token URL mein nahi, pehle message mein
    clearInterval(WS.ping); WS.ping = setInterval(() => { if (s.readyState === 1) s.send('ping'); }, 25000);
    if (WS.opened) onPush({ type: 'refresh' });         // reconnect: jo miss hua wo ek baar mangwa lo
    WS.opened = true;
  };
  s.onmessage = e => { if (e.data === 'pong') return; try { onPush(JSON.parse(e.data)); } catch (_) { } };
  s.onclose = ev => {
    clearInterval(WS.ping); if (WS.sock === s) WS.sock = null;
    if (!WS.want || !session) return;
    if (ev && ev.code === 4401) { setLive('off'); api('/me').catch(() => { }); return; }     // token galat/expire: dobara reconnect nahi
    setLive('off');
    if (!opened) api('/me').catch(() => { });           // token expire hua ho to 401 se sign out ho jayega
    WS.timer = setTimeout(openWS, Math.min(5000, 500 * 2 ** WS.tries++));
  };
}
function closeWS() {
  WS.want = false; WS.opened = false; clearTimeout(WS.timer); clearInterval(WS.ping);
  if (WS.sock) { const s = WS.sock; WS.sock = null; s.onclose = null; s.close(); }
  const el = $('#live'); if (el) el.hidden = true;
}
let refreshT;
function onPush(m) {
  if (m.type === 'refresh') {
    clearTimeout(refreshT);
    refreshT = setTimeout(() => {                                  // 60 ms mein aaye kai events ek hi fetch
      if (view === 'ambulance') ambRefresh().catch(e => console.warn(e.message));
      if (view === 'hospital') hospRefresh().catch(e => console.warn(e.message));
    }, 60);
  } else if (m.type === 'location') { if (view === 'hospital') hospLive(m); }
  else if (m.type === 'alert') { if (view === 'hospital') hospAlert(m); }
  else if (m.type === 'notice') { toast(m.text, 8000); if (view === 'ambulance') beep(); }
}
document.addEventListener('visibilitychange', () => { if (!document.hidden && session && view && view !== 'landing') onPush({ type: 'refresh' }); });

function route() {
  const h = location.hash;
  const want = h === '#/ambulance' ? 'ambulance' : h === '#/hospital' ? 'hospital' : 'landing';
  if (want !== 'landing' && (!session || session.role !== want)) {
    if (session) { location.hash = '#/' + session.role; return; }
    location.replace('login.html?role=' + want); return;
  }
  if (want === view) return;
  view = want; stopDrive(); stopGps(); clearInterval(Hh.tick);
  ['landing', 'ambulance', 'hospital'].forEach(v => { $('#view-' + v).hidden = v !== want; });
  updateNav();
  window.scrollTo(0, 0);
  want === 'landing' ? closeWS() : openWS();
  if (want === 'ambulance') ambulanceStart();
  if (want === 'hospital') hospitalStart();
  if (want === 'landing') landingShown();
}
function updateNav() {
  const inApp = view && view !== 'landing';
  $$('.nav-landing').forEach(a => a.hidden = inApp);
  $('#who').hidden = !session; $('#who').textContent = session ? session.username : '';
  $('#nav-dash').hidden = !session || view === session.role;
  if (session) $('#nav-dash').href = '#/' + session.role;
  $('#btn-logout').hidden = !session;
  $('#btn-login-amb').hidden = !!session; $('#btn-login-hosp').hidden = !!session; $('#btn-signup').hidden = !!session;
}
function logout(silent) {
  saveSession(null); view = null; closeWS(); stopDrive(); stopGps(); clearInterval(Hh.tick); if (cdlg.open) cdlg.close();
  A.map = null; Hh.map = null; A.markers = {}; Hh.markers = {}; Hh.bg = {}; allBases = null; A.key = ''; A.opts = null; A.routeKey = ''; A.route = null; A.target = null;
  location.hash = '#/'; route(); updateNav();
  if (!silent) toast('Signed out.');
}

/* ---------- login / signup: alag pages ---------- */
const goLogin = role => { location.href = 'login.html?role=' + role; };
const goSignup = role => { location.href = 'signup.html?role=' + role; };
$('#btn-login-amb').onclick = () => goLogin('ambulance');
$('#btn-login-hosp').onclick = () => goLogin('hospital');
$('#btn-signup').onclick = () => goSignup('ambulance');
$$('[data-signup]').forEach(b => b.onclick = () => goSignup(b.dataset.signup));
$$('[data-login]').forEach(b => b.onclick = () => goLogin(b.dataset.login));
$('#btn-logout').onclick = () => logout();
window.addEventListener('hashchange', route);

/* ================= LANDING ================= */
let landingInit = false, R = { pick: null, map: null, markers: {} };
function landingShown() {
  if (landingInit) return; landingInit = true;
  $('#r-spots').innerHTML = SPOTS.map(([n, la, lo], i) => `<button class="spot" data-i="${i}">${esc(n)}</button>`).join('');
  $$('#r-spots .spot').forEach(b => b.onclick = () => { const [n, la, lo] = SPOTS[+b.dataset.i]; setPick({ lat: la, lon: lo, label: n }, true); });
  R.map = makeMap($('#r-map'), [30.2, 78.1], 9);
  if (R.map) R.map.on('click', e => setPick({ lat: e.latlng.lat, lon: e.latlng.lng, label: 'Place chosen on map' }, false));
  $('#r-gps').onclick = () => {
    if (!navigator.geolocation) return toast('This browser cannot share location. Pick a place instead.');
    navigator.geolocation.getCurrentPosition(p => setPick({ lat: p.coords.latitude, lon: p.coords.longitude, label: 'Your location' }, true),
      () => toast('Location is blocked. Allow it in the browser, or pick a place instead.'), { enableHighAccuracy: true, timeout: 8000 });
  };
  const search = async () => {
    const q = $('#r-q').value.trim(); if (!q) return;
    try { const g = await geocode(q); g ? setPick(g, true) : toast('Could not find that place. Try a nearby landmark.'); }
    catch (e) { toast('Place search is not reachable. Pick a quick place or tap the map.'); }
  };
  $('#r-search').onclick = search; $('#r-q').onkeydown = e => { if (e.key === 'Enter') search(); };
  $('#r-send').onclick = sendPublicReport;
  loadHospitals().then(hs => { $('#f-h').textContent = hs.length || 22; });
}
function setPick(p, pan) {
  R.pick = p; $('#r-picked').textContent = 'Selected: ' + p.label; $('#r-send').disabled = false;
  setMarker(R.map, R.markers, 'p', [p.lat, p.lon], 'scene', p.label);
  if (R.map && pan) R.map.setView([p.lat, p.lon], 14);
}
async function sendPublicReport() {
  if (!R.pick) return;
  const btn = $('#r-send'), out = $('#r-result'); btn.disabled = true;
  try {
    const r = await api('/incidents', { method: 'POST', auth: false, body: { lat: R.pick.lat, lon: R.pick.lon, location_text: R.pick.label } });
    out.className = 'result'; out.hidden = false;
    out.innerHTML = `<b>Alert sent.</b> Ambulance ${esc(r.ambulance_code || 'AMB-' + String(r.ambulance_id).padStart(2, '0'))} is on the way, about ${Math.round(r.eta_to_scene_min)} min. ${r.hospitals_notified} hospitals have been told to get ready.`;
  } catch (e) { out.className = 'result bad'; out.hidden = false; out.textContent = e.message; }
  finally { btn.disabled = false; }
}

/* ================= AMBULANCE ================= */
const A = { map: null, markers: {}, key: '', data: null, opts: null, pending: null, pTimer: null, rec: null, drive: null, gps: null, pos: null,
  fitted: false, route: null, routeKey: '', target: null, routeSeq: 0, speed: 10 };
function ambulanceStart() {
  $('#a-spots').innerHTML = SPOTS.map(([n], i) => `<button class="spot" data-i="${i}">${esc(n)}</button>`).join('');
  $$('#a-spots .spot').forEach(b => b.onclick = () => { const [n, la, lo] = SPOTS[+b.dataset.i]; queueReport({ lat: la, lon: lo, label: n, spoken: n }); });
  if (!A.map) { A.map = makeMap($('#a-map')); A.markers = {}; A.fitted = false; }
  setTimeout(() => A.map && A.map.invalidateSize(), 50);
  drawBackground(A.map, A.markers);
  startGps();
  ambRefresh().catch(e => toast(e.message));
}
async function ambRefresh() {
  const d = await api('/ambulance/active'); A.data = d; renderAmb(d); loadPrevAmb();
}
function setInfo(el, text, warn) { el.textContent = text; el.classList.toggle('warn', !!warn); }
function renderAmb(d) {
  const a = d.ambulance, inc = d.incident;
  $('#a-code').textContent = a.code; $('#a-base').textContent = a.base_name + ', ' + a.city;
  const st = $('#a-status');
  st.textContent = { AVAILABLE: 'Available', DISPATCHED: 'On the way', TRANSPORTING: 'Taking patient to hospital', OFFLINE: 'Offline' }[a.status] || a.status;
  st.className = 'badge ' + a.status.toLowerCase();
  if (!A.drive) A.pos = { lat: a.lat, lon: a.lon };            // drive chal rahi ho to position hamari apni hai, server ki purani nahi
  const key = inc ? inc.id + ':' + (inc.status === 'RESERVED' ? 'R' : 'C') : 'idle';
  if (key !== A.key) {
    A.key = key; A.fitted = false;
    $('#a-idle').hidden = key !== 'idle';
    $('#a-case').hidden = !inc || inc.status === 'RESERVED';
    $('#a-booked').hidden = !inc || inc.status !== 'RESERVED';
    if (inc && inc.status === 'RESERVED') { $('#a-opts').hidden = true; A.opts = null; }
    if (key === 'idle') { stopDrive(); A.opts = null; $('#a-opts').hidden = true; }
    if (inc && inc.status !== 'RESERVED') { $('#a-form').reset(); $('#p-n').textContent = '1'; $('#a-err').hidden = true; $('#a-opts').hidden = true; A.opts = null; }
  }
  const reserved = !!inc && inc.status === 'RESERVED';          // booking ke baad bhi form rahega: details baad mein bharo
  $('#a-form-wrap').hidden = !inc;
  $('#a-go').textContent = reserved ? 'Update details for the hospital' : 'Send report and book best hospital';
  $('#a-options').hidden = reserved;
  if (!A.drive) setMarker(A.map, A.markers, 'me', [a.lat, a.lon], 'amb', a.code);
  const pts = [[A.pos.lat, A.pos.lon]];
  let target = null;
  if (inc) {
    const sc = [inc.lat, inc.lon]; setMarker(A.map, A.markers, 'scene', sc, 'scene', 'Accident'); pts.push(sc);
    $('#c-title').textContent = 'Accident reported';
    $('#c-sub').textContent = (inc.location_text || 'Location shared') + ' · about ' + Math.round(inc.eta_to_scene_min) + ' min away';
    const pv = $('#a-prov'); const lk = (d.provisional || []);
    pv.hidden = !lk.length; pv.innerHTML = lk.length ? 'Likely hospitals (estimate, updates as hospitals confirm beds): ' + lk.map(o => `<b>${esc(o.name)}</b> (${Math.round(o.eta_min)} min)`).join(' · ') : '';
    $('#c-cancel').onclick = cancelCase; $('#b-cancel').onclick = cancelCase;
    if (inc.status === 'ASSESSED') { A.opts = d.options || []; renderOptions(); }     // reload ke baad bhi taaza options
    target = { kind: 'scene', key: 's' + inc.id, lat: inc.lat, lon: inc.lon, name: 'the accident' };
  } else dropMarker(A.markers, 'scene');
  if (d.hospital) {
    const h = d.hospital, ht = [h.lat, h.lon]; setMarker(A.map, A.markers, 'dest', ht, 'hosp', h.name); pts.push(ht);
    $('#b-name').textContent = h.name;
    const km = hav(A.pos.lat, A.pos.lon, h.lat, h.lon);
    if (!A.route || A.routeKey !== 'h' + inc.id + ':' + h.id) $('#b-meta').textContent = km.toFixed(1) + ' km away (straight line)';
    $('#b-items').innerHTML = Object.entries(inc.needs || {}).map(([k, q]) => `<span class="tag">${q} × ${esc(NEED_LABEL[k] || k)}</span>`).join('');
    const ph = (h.emergency_phone || h.phone || '').replace(/[^\d+]/g, ''); const call = $('#b-call');
    ph ? (call.href = 'tel:' + ph, call.hidden = false) : call.hidden = true;
    if (inc.status === 'RESERVED') target = { kind: 'hospital', key: 'h' + inc.id + ':' + h.id, lat: h.lat, lon: h.lon, name: h.name };
  } else dropMarker(A.markers, 'dest');
  syncRoute(target);
  if (!A.fitted && A.map) { fit(A.map, pts); A.fitted = true; }
}

/* road route + drive */
async function syncRoute(target) {
  A.target = target;
  if (!target) {
    A.routeSeq++; A.routeKey = ''; A.route = null; drawRoute(A.map, A.markers, null);
    setInfo($('#c-route-info'), ''); setInfo($('#b-route-info'), '');
    if (A.drive) stopDrive();
    return;
  }
  if (target.key === A.routeKey) return;
  A.routeKey = target.key; const seq = ++A.routeSeq, wasDriving = !!A.drive;
  const info = $(target.kind === 'hospital' ? '#b-route-info' : '#c-route-info');
  setInfo(info, 'Finding the road route…');
  const route = await fetchRoute(A.pos, target);
  if (seq !== A.routeSeq) return;                                  // beech mein target badal gaya
  A.route = route; drawRoute(A.map, A.markers, route);
  setInfo(info, route.approx ? 'Route service not reachable, showing a straight line.' : `Road route: ${route.km.toFixed(1)} km · about ${Math.ceil(route.min)} min`, route.approx);
  if (target.kind === 'hospital') $('#b-meta').textContent = route.km.toFixed(1) + ' km by road · about ' + Math.ceil(route.min) + ' min';
  if (wasDriving) { startDrive(route, target); toast('Route updated. Heading to ' + target.name + '.', 6000); }
}
const kmps = () => 40 * A.speed / 3600;                           // 40 km/h x demo speed
const driveDist = (D, now = performance.now()) => Math.min(D.path.total, D.base + D.speed * (now - D.t0) / 1000);
function startDrive(route, target) {
  stopDrive();
  const D = A.drive = { key: target.key, kind: target.kind, name: target.name, route, path: buildPath(route.coords), base: 0, t0: performance.now(),
    speed: kmps(), lastSend: 0, tick: null, raf: 0 };
  D.tick = setInterval(driveTick, 250);                            // logic: background tab mein bhi chalta hai
  D.raf = requestAnimationFrame(driveFrame);                       // sirf smooth drawing ke liye
  driveTick();
}
function driveFrame() {
  const D = A.drive; if (!D) return;
  const p = pointAt(D.path, driveDist(D)); A.pos = p;
  setMarker(A.map, A.markers, 'me', [p.lat, p.lon], 'amb', '');
  if (A.map && !A.map.getBounds().pad(-0.25).contains([p.lat, p.lon])) A.map.panTo([p.lat, p.lon], { animate: true, duration: .6 });
  D.raf = requestAnimationFrame(driveFrame);
}
function driveTick() {
  const D = A.drive; if (!D) return;
  const now = performance.now(), dist = driveDist(D, now), left = D.path.total - dist, done = left <= 0.005;
  const p = pointAt(D.path, dist); A.pos = p;
  const eta = D.path.total ? D.route.min * left / D.path.total : 0;
  const txt = done ? 'Reached ' + D.name + '.' : `Driving · ${left.toFixed(1)} km to go · about ${Math.ceil(eta)} min (sped up ${A.speed}× for the demo)`;
  $(D.kind === 'hospital' ? '#b-live' : '#c-live').textContent = txt;
  if (done || now - D.lastSend >= 1000) {
    D.lastSend = now;
    api('/ambulance/location', { method: 'PUT', body: { lat: p.lat, lon: p.lon, eta_min: +eta.toFixed(1), km_left: +left.toFixed(2), phase: D.kind, final: done } }).catch(() => { });
  }
  if (done) {
    setMarker(A.map, A.markers, 'me', [p.lat, p.lon], 'amb', '');
    stopDrive(); $(D.kind === 'hospital' ? '#b-live' : '#c-live').textContent = txt;
    toast(D.kind === 'hospital' ? 'You have reached the hospital. Tap “Arrived at hospital”.' : 'You have reached the accident. Report the patient condition.', 6000);
  }
}
function stopDrive() {
  if (!A.drive) return;
  clearInterval(A.drive.tick); cancelAnimationFrame(A.drive.raf); A.drive = null;
  $('#c-live').textContent = ''; $('#b-live').textContent = '';
}
async function driveNow() {
  const t = A.target; if (!t) return;
  if (A.drive && A.drive.key === t.key) return toast('Already driving.');
  let route = A.route;
  if (!route || A.routeKey !== t.key || hav(A.pos.lat, A.pos.lon, route.coords[0][0], route.coords[0][1]) > 0.15) route = await fetchRoute(A.pos, t);
  A.route = route; drawRoute(A.map, A.markers, route);
  startDrive(route, t); toast('Driving to ' + t.name + ' (sped up for the demo).');
}
$('#c-drive-scene').onclick = driveNow; $('#b-drive').onclick = driveNow;
$('#a-speed').onchange = e => {
  A.speed = +e.target.value; const D = A.drive;
  if (D) { const now = performance.now(); D.base = driveDist(D, now); D.t0 = now; D.speed = kmps(); }
};
$('#b-arrived').onclick = async () => {
  const inc = A.data && A.data.incident; if (!inc) return;
  try { await api(`/incidents/${inc.id}/arrived`, { method: 'POST' }); stopDrive(); toast('Marked as arrived. The hospital has been told.'); await ambRefresh(); }
  catch (e) { toast(e.message); }
};
async function cancelCase() {
  const inc = A.data && A.data.incident; if (!inc) return;
  if (!confirm('Cancel this case? Any booked bed will be released.')) return;
  try { await api(`/incidents/${inc.id}/cancel`, { method: 'POST' }); stopDrive(); toast('Case cancelled.'); ambRefresh(); } catch (e) { toast(e.message); }
}

/* voice + report */
$('#a-mic').addEventListener('click', () => {
  if (A.rec) { A.rec.stop(); return; }
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return toast('Voice input needs Chrome or Edge. Pick a quick place below, or type it.');
  const rec = new SR(); rec.lang = $('#a-lang').value; rec.interimResults = true; rec.maxAlternatives = 1;
  let text = '';
  rec.onstart = () => { A.rec = rec; $('#a-mic').classList.add('live'); $('#a-mic-t').textContent = 'Listening… tap to stop'; };
  rec.onresult = e => { text = [...e.results].map(r => r[0].transcript).join(' '); $('#a-mic-t').textContent = '“' + text + '”'; };
  rec.onerror = e => { toast(e.error === 'not-allowed' ? 'Microphone is blocked. Allow it in the browser.' : 'Could not hear that. Try again, or pick a quick place.'); };
  rec.onend = () => { A.rec = null; $('#a-mic').classList.remove('live'); $('#a-mic-t').textContent = 'Speak location'; if (text.trim()) resolveSpoken(text.trim()); };
  rec.start();
});
$('#a-find').onclick = () => { const q = $('#a-q').value.trim(); if (q) resolveSpoken(q); };
$('#a-q').onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); $('#a-find').click(); } };
async function resolveSpoken(text) {
  const known = SPOTS.find(s => text.toLowerCase().includes(s[0].split(',')[0].toLowerCase()));
  if (known) return queueReport({ lat: known[1], lon: known[2], label: known[0], spoken: text });
  try {
    const g = await geocode(text);
    g ? queueReport({ ...g, spoken: text }) : toast('Could not find “' + text + '”. Say a nearby landmark, or pick a quick place.');
  } catch (e) { toast('Place search is not reachable. Pick a quick place below.'); }
}
function queueReport(p) {
  clearInterval(A.pTimer); A.pending = p; let n = 3;
  const box = $('#a-pending'); box.hidden = false;
  const paint = () => {
    box.innerHTML = `<b>${esc(p.label)}</b><br>Sending in ${n} s <span class="row wrap" style="margin-top:8px"><button class="btn dark small" id="pp-now">Send now</button><button class="btn ghost small" id="pp-no">Cancel</button></span>`;
    $('#pp-now').onclick = () => { clearInterval(A.pTimer); submitReport(); }; $('#pp-no').onclick = () => { clearInterval(A.pTimer); A.pending = null; box.hidden = true; };
  };
  paint();
  A.pTimer = setInterval(() => { n--; if (n <= 0) { clearInterval(A.pTimer); submitReport(); } else paint(); }, 1000);
}
async function submitReport() {
  const p = A.pending; if (!p) return; A.pending = null; $('#a-pending').hidden = true;
  try { await api('/incidents', { method: 'POST', body: { lat: p.lat, lon: p.lon, location_text: p.spoken || p.label } }); toast('Accident reported. Hospitals are being alerted.'); A.key = ''; ambRefresh(); }
  catch (e) { toast(e.message); }
}

/* assessment */
$('#p-minus').onclick = () => { const o = $('#p-n'); o.textContent = Math.max(1, +o.textContent - 1); };
$('#p-plus').onclick = () => { const o = $('#p-n'); o.textContent = Math.min(20, +o.textContent + 1); };
/* ML advisory: vitals + red flags -> suggested severity (sirf sujhav, paramedic final) */
const SEV_NAME = { CRITICAL: 'Critical', MODERATE: 'Moderate', LOW: 'Low' };
function vitalsPayload() {
  const o = {}; const put = (k, id) => { const v = $(id).value; if (v !== '') o[k] = +v; };
  put('age', '#v-age'); put('rr', '#v-rr'); put('sbp', '#v-sbp'); put('pulse', '#v-hr'); put('spo2', '#v-spo2'); put('gcs', '#v-gcs');
  const on = n => !!$(`input[name=flag][value=${n}]:checked`);
  if (on('walking')) o.walking = true;
  if (on('no_obey')) o.obeys = false;
  ['penetrating', 'pelvis', 'flail', 'crush_amput', 'bleed', 'high_mech'].forEach(k => { if (on(k)) o[k] = true; });
  return o;
}
let mlTimer = 0, mlLast = null;
function mlSchedule() { clearTimeout(mlTimer); mlTimer = setTimeout(mlAsk, 350); }
async function mlAsk() {
  const box = $('#ml-box'); if (!box) return;
  const v = vitalsPayload();
  if (!Object.keys(v).length) { box.hidden = true; mlLast = null; return; }
  try { mlLast = await api('/ml/severity', { method: 'POST', body: v }); } catch { box.hidden = true; return; }
  const r = mlLast, pct = r.probabilities ? Math.round(r.probabilities[r.ml_only] * 100) : null;
  const why = r.reasons.length ? r.reasons.map(esc).join(' · ') : 'vitals look stable';
  box.hidden = false; box.className = 'mlbox ' + r.suggested.toLowerCase();
  box.innerHTML = `<div><b>Suggested: ${SEV_NAME[r.suggested]}</b>${pct !== null && !r.rule_floor ? ` <small>(${pct}% match)</small>` : ''}<span class="mlconf">${r.confidence} confidence</span></div>
    <p>${why}</p><p class="muted">A suggestion only. You decide. ${r.fields_known < 3 ? 'Add more vitals for a better suggestion.' : ''}</p>
    <button type="button" class="btn dark" id="ml-use">Use this suggestion</button>`;
  $('#ml-use').onclick = () => {
    const ri = $(`input[name=sev][value=${r.suggested}]`); if (ri) ri.checked = true;
    const n = r.needs; $$('input[name=need]').forEach(c => { c.checked = !!n[c.value]; });
    $$('input[name=spec]').forEach(c => { c.checked = n.specialties.includes(c.value); });
    toast('Suggestion applied. Check it and send.', 3500);
  };
}
document.addEventListener('input', e => { if (e.target.closest && e.target.closest('details.vitals')) mlSchedule(); });
document.addEventListener('change', e => { if (e.target.closest && e.target.closest('details.vitals')) mlSchedule(); });

function buildAssessment() {
  const sev = ($('input[name=sev]:checked') || {}).value;
  if (!sev) throw new Error('Choose how serious it is first.');
  const needs = $$('input[name=need]:checked').map(i => i.value);
  const num = id => { const v = $(id).value; return v === '' ? undefined : +v; };
  const report = vitalsPayload(); const m = $('#v-mech').value.trim(); if (m) report.mechanism = m;
  return { severity: sev, patients: +$('#p-n').textContent, icu: needs.includes('icu'), ventilator: needs.includes('ventilator'), surgery: needs.includes('surgery'),
    specialties: $$('input[name=spec]:checked').map(i => i.value), report };
}
async function postAssessment(body) { return api(`/incidents/${A.data.incident.id}/assessment`, { method: 'POST', body }); }
function showErr(msg) { const e = $('#a-err'); e.textContent = msg; e.hidden = !msg; }
$('#a-form').addEventListener('submit', async e => {
  e.preventDefault(); showErr('');
  const btn = $('#a-go'); btn.disabled = true;
  try {
    if (A.data.incident.status === 'RESERVED') {                  // bed pehle se held hai: sirf details bhejo
      const r = await api(`/incidents/${A.data.incident.id}/details`, { method: 'POST', body: buildAssessment() });
      toast(r.unmet.length ? 'Details saved. The hospital could not add: ' + r.unmet.map(k => NEED_LABEL[k] || k).join(', ') + '. Please call them.' : 'Details sent to the hospital.', 6000);
      await ambRefresh(); return;
    }
    await postAssessment(buildAssessment());
    const r = await api(`/incidents/${A.data.incident.id}/reserve`, { method: 'POST', body: {} });
    toast('Bed held at ' + r.hospital.name + (r.tried.length ? ` (${r.tried.length} hospital${r.tried.length > 1 ? 's' : ''} had just filled up)` : ''), 6000);
    A.key = ''; await ambRefresh();
  } catch (err) { showErr(err.message); } finally { btn.disabled = false; }
});
$('#a-options').onclick = async () => {
  showErr('');
  try { const r = await postAssessment(buildAssessment()); A.opts = r.options; A.soon = r.soon || []; renderOptions(); }
  catch (err) { showErr(err.message); }
};
function renderOptions() {
  const box = $('#a-opts'), list = $('#a-opts-list'); box.hidden = false;
  if (!A.opts.length) {
    const soon = (A.soon || []).map(o => `<li class="soon"><b>${esc(o.name)}</b><small>${o.eta_min} min away · beds likely free in about ${o.free_in_min} min${o.wait_after_arrival_min ? ` (you may wait ${o.wait_after_arrival_min} min)` : ' (likely ready when you arrive)'}</small></li>`).join('');
    list.innerHTML = '<li class="empty">No hospital nearby has everything needed right now. Try “Send report and book best hospital”, which also looks further away.</li>' + (soon ? '<li class="empty"><b>Likely to free up soon</b> (estimate)</li>' + soon : ''); return;
  }
  list.innerHTML = A.opts.map(o => `<li><button data-id="${o.hospital_id}"><b>${esc(o.name)}</b><small>${o.eta_min} min · ${esc(o.why.slice(1).join(' · ') || 'free beds available')}</small></button></li>`).join('');
  $$('button', list).forEach(b => b.onclick = async () => {
    try { await api(`/incidents/${A.data.incident.id}/reserve`, { method: 'POST', body: { hospital_id: +b.dataset.id } }); A.key = ''; A.opts = null; ambRefresh(); }
    catch (e) { showErr(e.message); }
  });
}

/* live gps: automatic, optional nahi (nearest ambulance aur hospital ko live location isi se milti hai) */
const inService = p => p.lat > 29.55 && p.lat < 30.75 && p.lon > 77.55 && p.lon < 78.65;     // Dehradun, Haridwar, Rishikesh, Roorkee
function gpsState(s) {
  const el = $('#a-gps-state'), bn = $('#a-gps-banner'); if (!el) return;
  const txt = { wait: 'Getting GPS…', ok: 'GPS live', outside: 'GPS outside service area', denied: 'GPS blocked', error: 'GPS unavailable' }[s];
  el.className = 'gps ' + (s === 'ok' ? 'ok' : s === 'wait' ? 'wait' : 'bad'); el.firstElementChild.nextElementSibling.textContent = txt;
  $('#a-gps-retry').hidden = !(s === 'denied' || s === 'error');
  bn.hidden = !(s === 'denied' || s === 'error' || s === 'outside');
  bn.textContent = s === 'outside' ? 'Your GPS is outside Dehradun, Haridwar, Rishikesh and Roorkee, so your base location is used. This is normal when testing from another city.'
    : 'MEDORA needs your live location to pick the nearest ambulance and to show your position to hospitals. Allow location access in the browser, then tap Retry.';
}
function startGps() {
  if (A.gps != null) return;
  if (!navigator.geolocation) return gpsState('error');
  gpsState('wait'); let last = 0;
  A.gps = navigator.geolocation.watchPosition(p => {
    const pos = { lat: p.coords.latitude, lon: p.coords.longitude };
    if (!inService(pos)) return gpsState('outside');
    gpsState('ok');
    if (A.drive || Date.now() - last < 2000) return;             // demo drive chal rahi ho to wahi position batati hai
    last = Date.now(); A.pos = pos;
    setMarker(A.map, A.markers, 'me', [pos.lat, pos.lon], 'amb', '');
    api('/ambulance/location', { method: 'PUT', body: { ...pos, phase: null } }).catch(() => { });
  }, err => gpsState(err.code === 1 ? 'denied' : 'error'), { enableHighAccuracy: true, maximumAge: 2000, timeout: 20000 });
}
function stopGps() { if (A.gps != null) { navigator.geolocation.clearWatch(A.gps); A.gps = null; } }
$('#a-gps-retry').onclick = () => { stopGps(); startGps(); };

/* ---------- pichhle 5 cases: table + timeline ---------- */
const fmtD = d => new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
const fmtHM = d => d ? new Date(d).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }) : '';
const prevOpen = new Set();                                       // kholi hui rows refresh ke baad bhi khuli rahein
function renderPrev(el, rows, kind) {
  if (!el) return;
  const sig = JSON.stringify(rows); if (el._sig === sig) return; el._sig = sig;
  if (!rows.length) { el.innerHTML = '<p class="muted small-t">No previous cases yet.</p>'; return; }
  const note = r => r.status === 'CANCELLED' ? ' <small class="muted">cancelled</small>' : r.status === 'PREEMPTED' ? ' <small class="muted">bed reassigned</small>' : '';
  el.innerHTML = `<table class="prev-t"><thead><tr><th>Case ID</th><th>Severity</th><th>${kind === 'amb' ? 'Hospital' : 'Ambulance'}</th><th>Date</th></tr></thead><tbody>` +
    rows.map(r => `<tr class="prow" data-k="${kind}${r.id}" tabindex="0" role="button" aria-expanded="${prevOpen.has(kind + r.id)}"><td><b>${esc(r.case_id)}</b>${note(r)}</td>
      <td><span class="sev-tag ${r.severity || 'NONE'}">${r.severity ? SEV_LABEL[r.severity] : '—'}</span></td>
      <td>${esc((kind === 'amb' ? r.hospital : r.ambulance) || '—')}</td><td>${fmtD(r.date)}</td></tr>
      <tr class="ptl" ${prevOpen.has(kind + r.id) ? '' : 'hidden'}><td colspan="4"><ol class="tl">${r.events.map(e => `<li><time>${fmtHM(e.at)}</time><span>${esc(e.label)}</span></li>`).join('')}</ol></td></tr>`).join('') + '</tbody></table>';
  $$('.prow', el).forEach(tr => {
    const tog = () => { const o = tr.nextElementSibling.hidden; tr.nextElementSibling.hidden = !o; tr.setAttribute('aria-expanded', o); o ? prevOpen.add(tr.dataset.k) : prevOpen.delete(tr.dataset.k); };
    tr.onclick = tog; tr.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); tog(); } };
  });
}
const loadPrevAmb = () => api('/ambulance/history').then(r => renderPrev($('#a-prev'), r, 'amb')).catch(() => { });
const loadPrevHosp = () => api('/hospital/history').then(r => renderPrev($('#h-prev'), r, 'hosp')).catch(() => { });

/* map par saare hospitals + ambulance bases */
let allBases = null;
async function loadBases() { if (!allBases) { try { allBases = await api('/ambulances/bases'); } catch (e) { allBases = []; } } return allBases; }
async function drawBackground(map, store, skipHospital) {
  if (!map) return;
  const [hs, bs] = await Promise.all([loadHospitals(), loadBases()]);
  hs.forEach(h => { if (h.id !== skipHospital) setMarker(map, store, 'h' + h.id, [h.lat, h.lon], 'other', h.name); });
  bs.forEach(b => setMarker(map, store, 'b' + b.id, [b.lat, b.lon], 'base', `${b.code} base · ${b.base_name}`));
}

/* ================= HOSPITAL ================= */
const Hh = { map: null, markers: {}, seen: null, ov: null, fitted: false, tick: null, skew: 0, bg: {} };
function hospitalStart() {
  if (!Hh.map) { Hh.map = makeMap($('#h-map')); Hh.markers = {}; Hh.bg = {}; Hh.fitted = false; }
  setTimeout(() => Hh.map && Hh.map.invalidateSize(), 50);
  Hh.seen = null;
  $$('#h-load button').forEach(b => b.onclick = () => putStatus({ load: b.dataset.load, diverting: $('#h-div').checked }));
  $('#h-div').onchange = () => putStatus({ load: ($('#h-load [aria-checked=true]') || { dataset: { load: 'NORMAL' } }).dataset.load, diverting: $('#h-div').checked });
  hospRefresh().then(() => { drawBackground(Hh.map, Hh.bg, Hh.ov.hospital.id); loginConfirm(); loadHist(); }).catch(e => toast(e.message));
  clearInterval(Hh.tick); Hh.tick = setInterval(confirmTick, 20000);
}
async function putStatus(s) { try { await api('/hospital/status', { method: 'PUT', body: s }); hospRefresh(); } catch (e) { toast(e.message); } }
async function hospRefresh() {
  const [ov, inc, rv] = await Promise.all([api('/hospital/overview'), api('/hospital/incoming'), api('/hospital/reservations')]);
  loadPrevHosp();
  Hh.ov = ov; Hh.skew = Date.parse(ov.status.server_now) - Date.now(); renderHosp(ov, inc, rv); updTick();
}
const liveText = (code, km, eta, phase) => phase === 'scene'
  ? `${code} is heading to the scene · ${km.toFixed(1)} km, about ${Math.ceil(eta)} min`
  : `${code} is ${km.toFixed(1)} km away · about ${Math.ceil(eta)} min`;
function hospLive(m) {                           // WebSocket se aayi ambulance ki live location
  const mk = Hh.markers['a' + m.incident_id];
  if (!mk) { onPush({ type: 'refresh' }); return; }
  glide(mk, [m.lat, m.lon], 1000);
  const el = document.querySelector(`[data-live="${m.incident_id}"]`);
  if (el && m.km_left != null && m.eta_min != null) el.textContent = liveText(m.code, m.km_left, m.eta_min, m.phase);
}
function beep() {
  try { const c = new (window.AudioContext || window.webkitAudioContext)(), o = c.createOscillator(), g = c.createGain(); o.connect(g); g.connect(c.destination); o.frequency.value = 880; g.gain.value = .15; o.start(); setTimeout(() => { o.stop(); c.close(); }, 350); } catch (e) { }
}
function needTags(needs) { return Object.entries(needs || {}).filter(([k]) => k !== 'ER_BED').map(([k, q]) => `<span class="tag">${esc(NEED_LABEL[k] || k)}</span>`).join(''); }
function renderHosp(ov, inc, rv) {
  const h = ov.hospital;
  $('#h-name').textContent = h.name; $('#h-city').textContent = h.city;
  $('#h-count').textContent = inc.inbound_ambulances;
  $$('#h-load button').forEach(b => b.setAttribute('aria-checked', b.dataset.load === ov.status.load));
  if (document.activeElement !== $('#h-div')) $('#h-div').checked = ov.status.diverting;

  // new alert
  const ids = new Set(inc.incidents.map(i => i.incident_id));
  if (Hh.seen) {
    const fresh = inc.incidents.filter(i => !Hh.seen.has(i.incident_id));
    if (fresh.length) {
      const f = fresh[0]; const al = $('#h-alert'); al.hidden = false;
      al.textContent = `New accident alert: ${fresh.length > 1 ? fresh.length + ' ambulances' : 'one ambulance'} about ${Math.round(f.eta_hospital_min)} min from the scene. Update your beds if needed.`;
      al.style.animation = 'none'; void al.offsetWidth; al.style.animation = ''; beep();
    }
  }
  Hh.seen = ids; if (!ids.size) $('#h-alert').hidden = true;

  // incoming
  const me = [h.lat, h.lon]; setMarker(Hh.map, Hh.markers, 'me', me, 'hosp', h.name);
  const pts = [me]; const keep = new Set(['me']);
  $('#h-in').innerHTML = inc.incidents.length ? inc.incidents.map(i => {
    const sev = i.severity || 'NONE'; let meta;
    if (i.my_status === 'RESERVED' && i.amb_lat != null) { const km = i.live_km != null ? i.live_km : hav(i.amb_lat, i.amb_lon, h.lat, h.lon) * 1.35; meta = esc(liveText(i.ambulance, km, i.live_eta_min != null ? i.live_eta_min : etaMin(km / 1.35), 'hospital')); }
    else meta = `Alerted · ${i.distance_km.toFixed(1)} km from the scene · about ${Math.round(i.eta_hospital_min)} min` + (i.ambulance ? ' · ' + esc(i.ambulance) + ' attending' : '');
    const rp = i.report || {}; const vit = [rp.gcs != null ? 'GCS ' + rp.gcs : '', rp.spo2 != null ? 'SpO₂ ' + rp.spo2 : '', rp.mechanism || ''].filter(Boolean).join(' · ');
    return `<li><span class="sev-tag ${sev}">${sev === 'NONE' ? 'Waiting' : SEV_LABEL[sev]}</span><div class="in-main"><b>${i.patients} patient${i.patients > 1 ? 's' : ''}</b> · ${esc(i.location_text || 'Location shared')}
      <div class="in-meta" data-live="${i.incident_id}">${meta}</div>${vit ? `<div class="in-meta">${esc(vit)}</div>` : ''}
      ${i.status === 'REPORTED' ? `<div class="in-meta prov">Possible patient${i.prov_rank ? ` · you rank <b>#${i.prov_rank}</b> of ${i.prov_total} likely hospitals` : ''} · update your beds within <b class="dl" data-end="${Date.now() + i.deadline_in_s * 1000}">--:--</b> (before the ambulance reaches the scene)</div>` : ''}
      <div class="in-tags">${i.my_status === 'RESERVED' ? '<span class="tag held">Bed held for this patient</span>' : ''}${needTags(i.needs)}</div></div></li>`;
  }).join('') : '<li class="empty">No ambulance is heading here right now.</li>';
  inc.incidents.forEach(i => {
    const sk = 's' + i.incident_id, ak = 'a' + i.incident_id; keep.add(sk); keep.add(ak);
    if (i.my_status === 'RESERVED' && i.amb_lat != null) { setMarker(Hh.map, Hh.markers, ak, [i.amb_lat, i.amb_lon], 'amb', i.ambulance); pts.push([i.amb_lat, i.amb_lon]); dropMarker(Hh.markers, sk); keep.delete(sk); }
    else { setMarker(Hh.map, Hh.markers, sk, [i.scene_lat, i.scene_lon], 'scene', 'Accident'); pts.push([i.scene_lat, i.scene_lon]); if (i.amb_lat != null) { setMarker(Hh.map, Hh.markers, ak, [i.amb_lat, i.amb_lon], 'amb', i.ambulance); } else { dropMarker(Hh.markers, ak); keep.delete(ak); } }
  });
  Object.keys(Hh.markers).forEach(k => { if (!keep.has(k)) dropMarker(Hh.markers, k); });
  if (Hh.map && (!Hh.fitted || ids.size !== Hh.lastN)) { fit(Hh.map, pts, 13); Hh.fitted = true; Hh.lastN = ids.size; }

  // resources
  const fcText = f => { if (!f || f.free_now || f.p50_min == null) return ''; const t = m => m < 90 ? m + ' min' : m < 2880 ? Math.round(m / 60) + ' h' : Math.round(m / 1440) + ' days';
    return ` · next one likely free in ~${t(f.p50_min)}${f.learned_from ? ` (learned from ${f.learned_from} cases)` : ' (estimate)'}`; };
  const order = ['ER_BED', 'ICU_BED', 'VENTILATOR', 'OT'];
  $('#h-res').innerHTML = order.map(k => ov.resources.find(r => r.resource_type === k)).filter(Boolean).map(r => `<li>
    <div><b>${r.available}</b> free of ${r.total}<small>${esc(RES_LABEL[r.resource_type])}${r.booked ? ` · ${r.booked} held for ambulances` : ''}${r.is_simulated ? ' · simulated' : ''}${fcText(ov.forecast && ov.forecast[r.resource_type])}</small></div>
    <div class="stepper"><button data-rt="${r.resource_type}" data-v="${r.available - 1}" aria-label="One fewer ${esc(RES_LABEL[r.resource_type])} free">−</button><output>${r.available}</output><button data-rt="${r.resource_type}" data-v="${r.available + 1}" data-max="${r.total - r.booked}" aria-label="One more ${esc(RES_LABEL[r.resource_type])} free">+</button></div></li>`).join('');
  $$('#h-res button').forEach(b => b.onclick = async () => {
    const v = +b.dataset.v; if (v < 0 || (b.dataset.max && v > +b.dataset.max)) return;
    try { await api('/hospital/resources', { method: 'PUT', body: { resource_type: b.dataset.rt, available: v } }); hospRefresh(); } catch (e) { toast(e.message); }
  });

  // reservations
  $('#h-resv').innerHTML = rv.length ? rv.map(r => {
    const items = Object.entries(r.items).map(([k, q]) => `<span class="tag">${q} × ${esc(NEED_LABEL[k] || k)}</span>`).join('');
    const acts = r.status === 'BOOKED'
      ? `<button class="btn dark small" data-act="admit" data-id="${r.id}">Patient arrived</button><button class="btn ghost small" data-act="free" data-id="${r.id}">Release booking</button>`
      : Object.keys(r.items).map(k => `<button class="btn ghost small" data-act="free" data-id="${r.id}" data-t="${k}">Free ${esc(NEED_LABEL[k] || k)}</button>`).join('') + `<button class="btn dark small" data-act="free" data-id="${r.id}">Free all</button>`;
    return `<li><span class="sev-tag ${r.severity || 'NONE'}">${r.status === 'BOOKED' ? 'Booked' : 'Admitted'}</span><div class="in-main"><b>${r.patients} patient${r.patients > 1 ? 's' : ''}</b><div class="in-tags">${items}</div></div><div class="actions">${acts}</div></li>`;
  }).join('') : '<li class="empty">Nothing booked.</li>';
  $$('#h-resv button').forEach(b => b.onclick = async () => {
    try {
      if (b.dataset.act === 'admit') await api(`/hospital/reservations/${b.dataset.id}/admit`, { method: 'POST' });
      else await api(`/hospital/reservations/${b.dataset.id}/release`, { method: 'POST', body: b.dataset.t ? { types: [b.dataset.t] } : {} });
      hospRefresh();
    } catch (e) { toast(e.message); }
  });
}


/* ---------- resource confirm: login par, har 15 min, naye alert par ---------- */
const cdlg = $('#confirm');
const CF = { mode: 'MANUAL', snooze: 0 };
const fmtT = d => new Date(d).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
const ageMin = () => { const c = Hh.ov && Hh.ov.status.confirmed_at; return c ? (Date.now() + Hh.skew - Date.parse(c)) / 60000 : Infinity; };
function updTick() {
  const el = $('#h-upd'), t = $('#h-upd-t'); if (!el || !Hh.ov) return;
  const a = ageMin(), every = Hh.ov.status.confirm_every_min || 15;
  t.textContent = a === Infinity ? 'Beds not confirmed yet. Numbers shown are simulated.' : `Beds last confirmed at ${fmtT(Hh.ov.status.confirmed_at)} (${Math.floor(a)} min ago). Next check in ${Math.max(0, Math.ceil(every - a))} min.`;
  el.classList.toggle('stale', a >= every);
}
function confirmTick() {
  if (view !== 'hospital' || !Hh.ov) return;
  updTick();
  if (!cdlg.open && ageMin() >= (Hh.ov.status.confirm_every_min || 15) && Date.now() > CF.snooze) openConfirm('PERIODIC', 'Routine check. It has been 15 minutes since you last confirmed your beds.');
}
async function openConfirm(mode, why) {
  if (cdlg.open) return;
  try { Hh.ov = await api('/hospital/overview'); Hh.skew = Date.parse(Hh.ov.status.server_now) - Date.now(); } catch (e) { return; }
  CF.mode = mode;
  $('#cf-title').textContent = mode === 'LOGIN' ? 'Confirm your beds to continue' : mode === 'ALERT' ? 'New accident alert: update your beds' : 'Are your beds still correct?';
  $('#cf-why').textContent = why || '';
  $('#cf-later').hidden = mode === 'LOGIN';
  $('#cf-err').hidden = true;
  $('#cf-rows').innerHTML = ['ER_BED', 'ICU_BED', 'VENTILATOR', 'OT'].map(k => Hh.ov.resources.find(r => r.resource_type === k)).filter(Boolean).map(r => `<div class="crow">
    <b>${esc(RES_LABEL[r.resource_type])}</b>
    <label class="mini">Total<input type="number" min="0" max="2000" required data-rt="${r.resource_type}" data-f="total" value="${r.total}"></label>
    <label class="mini">Free now<input type="number" min="0" max="2000" required data-rt="${r.resource_type}" data-f="avail" value="${r.available}"></label>
    ${r.booked ? `<small>${r.booked} held for incoming ambulances (not counted as free)</small>` : ''}</div>`).join('');
  cdlg.showModal();
}
cdlg.addEventListener('cancel', e => { if (CF.mode === 'LOGIN') e.preventDefault(); });
$('#confirm-form').addEventListener('submit', async e => {
  if (e.submitter && e.submitter.value === 'cancel') { CF.snooze = Date.now() + 5 * 60000; return; }     // Later: 5 min baad phir poochhenge
  e.preventDefault();
  const resources = {};
  $$('#cf-rows input').forEach(i => { const o = resources[i.dataset.rt] = resources[i.dataset.rt] || {}; o[i.dataset.f === 'total' ? 'total' : 'available'] = +i.value; });
  for (const [k, v] of Object.entries(resources)) if (v.available + (Hh.ov.resources.find(r => r.resource_type === k) || {}).booked > v.total) {
    $('#cf-err').textContent = `${RES_LABEL[k]}: free beds cannot be more than the total.`; $('#cf-err').hidden = false; return;
  }
  $('#cf-go').disabled = true;
  try {
    await api('/hospital/resources/confirm', { method: 'PUT', body: { resources, source: CF.mode } });
    if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission();   // click ke baad hi permission maang sakte hain
    saveSession({ ...session, confirmed: true }); CF.snooze = 0;
    cdlg.close(); toast('Thanks. Beds confirmed.'); await hospRefresh(); loadHist();
  } catch (err) { $('#cf-err').textContent = err.message; $('#cf-err').hidden = false; }
  finally { $('#cf-go').disabled = false; }
});
$('#h-upd-btn').onclick = () => openConfirm('MANUAL', 'Enter the current numbers.');
function loginConfirm() {                             // har naye sign in par asli ginti poochho (signup ke turant baad nahi)
  if (!session || session.confirmed || !Hh.ov) return;
  if (ageMin() < 2) { saveSession({ ...session, confirmed: true }); return; }
  openConfirm('LOGIN', 'Please enter your real bed and equipment numbers. Until you do, the numbers on MEDORA are only estimates.');
}
function hospAlert(m) {
  const where = m.location ? ' near ' + m.location : '';
  toast('New accident alert' + where + '. Please update your beds.', 8000);
  try { if ('Notification' in window && Notification.permission === 'granted') new Notification('MEDORA: accident alert', { body: 'An ambulance may come to you' + where + '. Update your beds.', tag: 'medora-alert' + m.incident_id }); } catch (_) { }
  openConfirm('ALERT', 'An ambulance may bring a patient to you' + where + '. Check the numbers so it picks the right hospital.');
}
async function loadHist() {
  try { const h = await api('/hospital/updates'); $('#h-hist').innerHTML = h.length ? h.map(x => `<li>${fmtT(x.at)} · ${({ LOGIN: 'sign in', PERIODIC: '15 min check', ALERT: 'accident alert', MANUAL: 'manual', SIGNUP: 'sign up' })[x.source] || x.source}</li>`).join('') : '<li>No updates yet.</li>'; } catch (e) { }
}

/* ---------- start ---------- */
updateNav();
route();
if (view === null) route();
/* hospital: "update beds within mm:ss" countdown (har second) */
setInterval(() => {
  $$('.dl').forEach(el => {
    const left = Math.max(0, Math.round((+el.dataset.end - Date.now()) / 1000));
    el.textContent = left ? String(Math.floor(left / 60)).padStart(2, '0') + ':' + String(left % 60).padStart(2, '0') : 'now';
  });
}, 1000);
})();
