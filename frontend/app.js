/* Plan2Walk frontend: F1 chat, F2 vision import, F3 report, F4 SVG editor, F5 launch. */
(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const svg = $('plan');
  const NS = 'http://www.w3.org/2000/svg';

  const state = {
    plan: null,
    report: null,
    selected: null,       // {kind:'room'|'opening', id:number}
    adding: null,         // 'door' | 'window'
    view: null,           // {x,y,w,h} in metres
    viewPlanId: null,
    drag: null,
    pan: null,
    lastPrompt: '',
    seed: 0,
    busy: false,
  };

  const ROOM_FILL = {
    living_room: '#dbeafe',
    kitchen: '#fde68a',
    bedroom: '#dcfce7',
    bathroom: '#cffafe',
    hall: '#f3e8ff',
    other: '#fee2e2',
  };
  const ROOM_TYPES = ['living_room', 'kitchen', 'bedroom', 'bathroom', 'hall', 'other'];
  const CANVAS_BG = '#f5f1e9';

  // ------------------------------------------------------------------ utils
  const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), hi);
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));

  let toastTimer = null;
  function toast(message, isError = false) {
    const el = $('toast');
    el.textContent = message;
    el.classList.toggle('error', isError);
    el.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove('show'), isError ? 5200 : 2600);
  }

  function addMessage(role, text) {
    const box = $('messages');
    const el = document.createElement('div');
    el.className = `msg ${role}`;
    el.textContent = text;
    box.appendChild(el);
    box.scrollTop = box.scrollHeight;
    return el;
  }

  async function api(method, path, body) {
    const opts = { method, headers: {} };
    if (body instanceof FormData) {
      opts.body = body;
    } else if (body !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(path, opts);
    let data = null;
    try { data = await res.json(); } catch { /* empty body */ }
    if (!res.ok) {
      const detail = data && data.detail;
      throw new Error(typeof detail === 'string' ? detail : (detail ? JSON.stringify(detail) : `${res.status} ${res.statusText}`));
    }
    return data;
  }

  // --------------------------------------------------------------- plan maths
  const scale = () => (state.plan && state.plan.units === 'm')
    ? 1
    : ((state.plan && state.plan.plan_width_m) || 15) / ((state.plan && state.plan.grid) || 1000);

  function wallGeom(w) {
    const S = scale();
    const a = state.plan.vertices[w.a];
    const b = state.plan.vertices[w.b];
    const ax = a[0] * S, ay = a[1] * S;
    const bx = b[0] * S, by = b[1] * S;
    const len = Math.hypot(bx - ax, by - ay) || 1e-6;
    const dx = (bx - ax) / len, dy = (by - ay) / len;
    return { ax, ay, bx, by, len, dx, dy, nx: -dy, ny: dx };
  }

  function wallThickness(w) {
    const S = scale();
    const raw = (w.thickness || state.plan.wall_thickness || 6) * S;
    return clamp(raw, 0.06, 0.4);
  }

  function pointAt(g, offsetM) {
    return { x: g.ax + g.dx * offsetM, y: g.ay + g.dy * offsetM };
  }

  function polygonAreaM2(poly) {
    const S = scale();
    let area = 0;
    for (let i = 0; i < poly.length; i++) {
      const [x0, y0] = poly[i];
      const [x1, y1] = poly[(i + 1) % poly.length];
      area += x0 * y1 - x1 * y0;
    }
    return Math.abs(area / 2) * S * S;
  }

  function roomBounds(room) {
    const S = scale();
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const [x, y] of room.polygon || []) {
      x0 = Math.min(x0, x * S); y0 = Math.min(y0, y * S);
      x1 = Math.max(x1, x * S); y1 = Math.max(y1, y * S);
    }
    return { x0, y0, x1, y1, w: x1 - x0, h: y1 - y0 };
  }

  function planBounds() {
    const S = scale();
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const [x, y] of state.plan.vertices || []) {
      x0 = Math.min(x0, x * S); y0 = Math.min(y0, y * S);
      x1 = Math.max(x1, x * S); y1 = Math.max(y1, y * S);
    }
    if (!Number.isFinite(x0)) return { x0: 0, y0: 0, x1: 12, y1: 10 };
    return { x0, y0, x1, y1 };
  }

  function fitView() {
    if (!state.plan) { state.view = null; return; }
    const b = planBounds();
    const pad = Math.max(0.6, Math.max(b.x1 - b.x0, b.y1 - b.y0) * 0.06);
    let x = b.x0 - pad, y = b.y0 - pad;
    let w = (b.x1 - b.x0) + pad * 2, h = (b.y1 - b.y0) + pad * 2;
    const rect = svg.getBoundingClientRect();
    const aspect = (rect.width || 800) / (rect.height || 520);
    if (w / h > aspect) h = w / aspect; else w = h * aspect;
    state.view = { x: x + ((b.x1 - b.x0) + pad * 2 - w) / 2, y: y + ((b.y1 - b.y0) + pad * 2 - h) / 2, w, h };
  }

  function setViewBox() {
    if (!state.view) return;
    const v = state.view;
    svg.setAttribute('viewBox', `${v.x} ${v.y} ${v.w} ${v.h}`);
  }

  function screenToPlan(event) {
    const pt = svg.createSVGPoint();
    pt.x = event.clientX; pt.y = event.clientY;
    const m = svg.getScreenCTM();
    if (!m) return { x: 0, y: 0 };
    const p = pt.matrixTransform(m.inverse());
    return { x: p.x, y: p.y };
  }

  // ------------------------------------------------------------------- render
  function el(name, attrs, parent) {
    const node = document.createElementNS(NS, name);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v !== null && v !== undefined) node.setAttribute(k, v);
    }
    if (parent) parent.appendChild(node);
    return node;
  }

  function renderAll() {
    renderHeader();
    renderSvg();
    renderInspector();
    renderReport();
    renderButtons();
  }

  function renderHeader() {
    const p = state.plan;
    if (!p) {
      $('planTitle').textContent = 'No plan loaded';
      $('planSub').textContent = 'generate or import a plan to begin';
      return;
    }
    const metrics = (state.report && state.report.metrics) || {};
    const plot = p.plot ? `${p.plot.width_m} × ${p.plot.depth_m} m plot` : '';
    $('planTitle').innerHTML = `${esc(p.title || p.plan_id)}<small id="planSub">${esc(
      [plot, `${p.rooms.length} rooms`, metrics.area_m2 ? `${metrics.area_m2} m²` : '', p.source || '']
        .filter(Boolean).join(' · ')
    )}</small>`;
  }

  function renderButtons() {
    const has = !!state.plan;
    const opening = selectedOpening();
    $('open3dBtn').disabled = !has;
    $('exportBtn').disabled = !has;
    $('exportGlbBtn').disabled = !has;
    $('validateBtn').disabled = !has;
    $('repairBtn').disabled = !has;
    $('deleteOpeningBtn').disabled = !opening;
    $('addDoorBtn').classList.toggle('active', state.adding === 'door');
    $('addWindowBtn').classList.toggle('active', state.adding === 'window');
    svg.classList.toggle('adding', !!state.adding);
  }

  function renderSvg() {
    svg.innerHTML = '';
    if (!state.plan) {
      $('emptyState').style.display = 'grid';
      svg.style.display = 'none';
      return;
    }
    $('emptyState').style.display = 'none';
    svg.style.display = 'block';
    if (!state.view) fitView();
    setViewBox();

    const p = state.plan;
    const S = scale();
    const walls = new Map(p.walls.map((w) => [w.id, w]));
    const geom = new Map(p.walls.map((w) => [w.id, wallGeom(w)]));

    const bg = el('rect', { x: -1000, y: -1000, width: 3000, height: 3000, fill: CANVAS_BG }, svg);
    bg.dataset.bg = '1';

    // Rooms
    for (const room of p.rooms) {
      const pts = (room.polygon || []).map(([x, y]) => `${x * S},${y * S}`).join(' ');
      const node = el('polygon', {
        points: pts,
        fill: ROOM_FILL[room.type] || ROOM_FILL.other,
        stroke: '#ffffff',
        'stroke-width': 0.01,
        'data-rid': room.id,
      }, svg);
      node.style.cursor = 'pointer';
    }

    // Room labels
    for (const room of p.rooms) {
      const b = roomBounds(room);
      const cx = (b.x0 + b.x1) / 2;
      const cy = (b.y0 + b.y1) / 2;
      const small = Math.min(b.w, b.h) < 1.5;
      const text = el('text', {
        x: cx, y: cy,
        'text-anchor': 'middle',
        'dominant-baseline': 'middle',
        fill: '#1f2937',
        'font-family': 'ui-sans-serif, system-ui, sans-serif',
        'font-size': small ? 0.19 : 0.26,
        'font-weight': 650,
        'pointer-events': 'none',
      }, svg);
      text.textContent = room.name || room.type;
      if (!small) {
        const t2 = el('tspan', {
          x: cx, dy: 0.24, 'font-size': 0.18, 'font-weight': 450, fill: '#4b5563',
        }, text);
        t2.textContent = `${b.w.toFixed(1)} × ${b.h.toFixed(1)} m`;
        const t3 = el('tspan', {
          x: cx, dy: 0.19, 'font-size': 0.16, 'font-weight': 450, fill: '#6b7280',
        }, text);
        t3.textContent = `${polygonAreaM2(room.polygon || []).toFixed(1)} m²`;
      }
    }

    // Walls
    for (const w of p.walls) {
      const g = geom.get(w.id);
      const t = wallThickness(w);
      el('line', {
        x1: g.ax, y1: g.ay, x2: g.bx, y2: g.by,
        stroke: w.cls === 'exterior' ? '#27272a' : '#3f3f46',
        'stroke-width': t,
        'stroke-linecap': 'square',
        'pointer-events': 'none',
      }, svg);
    }

    // Openings
    for (const o of p.openings || []) {
      const w = walls.get(o.wall);
      const g = geom.get(o.wall);
      if (!w || !g) continue;
      const off = (o.offset || 0) * S;
      const width = (o.width || 0) * S;
      const p0 = pointAt(g, off);
      const p1 = pointAt(g, off + width);
      const t = wallThickness(w);

      // erase the wall inside the opening
      el('line', {
        x1: p0.x, y1: p0.y, x2: p1.x, y2: p1.y,
        stroke: CANVAS_BG, 'stroke-width': t * 1.25, 'pointer-events': 'none',
      }, svg);

      if (o.kind === 'window') {
        el('line', {
          x1: p0.x, y1: p0.y, x2: p1.x, y2: p1.y,
          stroke: '#7fb3e0', 'stroke-width': Math.max(t * 0.55, 0.07), 'pointer-events': 'none',
        }, svg);
        el('line', {
          x1: p0.x, y1: p0.y, x2: p1.x, y2: p1.y,
          stroke: '#2f6fa8', 'stroke-width': Math.max(t * 0.16, 0.025), 'pointer-events': 'none',
        }, svg);
      } else {
        const leaf = { x: p0.x + g.nx * width, y: p0.y + g.ny * width };
        el('line', {
          x1: p0.x, y1: p0.y, x2: leaf.x, y2: leaf.y,
          stroke: '#6b7280', 'stroke-width': Math.max(t * 0.22, 0.035), 'pointer-events': 'none',
        }, svg);
        el('path', {
          d: `M ${leaf.x} ${leaf.y} A ${width} ${width} 0 0 1 ${p1.x} ${p1.y}`,
          fill: 'none', stroke: '#9ca3af', 'stroke-width': Math.max(t * 0.14, 0.02),
          'pointer-events': 'none',
        }, svg);
      }

      // hit target (transparent, wide)
      el('line', {
        x1: p0.x, y1: p0.y, x2: p1.x, y2: p1.y,
        stroke: 'transparent',
        'stroke-width': Math.max(t + 0.22, 0.34),
        'data-oid': o.id,
      }, svg).style.cursor = 'pointer';
    }

    // Selection overlays
    const sel = state.selected;
    if (sel && sel.kind === 'room') {
      const room = p.rooms.find((r) => r.id === sel.id);
      if (room) {
        el('polygon', {
          points: (room.polygon || []).map(([x, y]) => `${x * S},${y * S}`).join(' '),
          fill: 'none', stroke: '#2563eb', 'stroke-width': 0.07,
          'stroke-dasharray': '0.22 0.14', 'pointer-events': 'none',
        }, svg);
      }
    } else if (sel && sel.kind === 'opening') {
      const o = (p.openings || []).find((x) => x.id === sel.id);
      const g = o && geom.get(o.wall);
      if (o && g) {
        const off = (o.offset || 0) * S, width = (o.width || 0) * S;
        const p0 = pointAt(g, off), p1 = pointAt(g, off + width);
        el('line', {
          x1: p0.x, y1: p0.y, x2: p1.x, y2: p1.y,
          stroke: '#2563eb', 'stroke-width': Math.max(wallThickness(walls.get(o.wall)) * 1.8, 0.16),
          'stroke-linecap': 'round', opacity: 0.35, 'pointer-events': 'none',
        }, svg);
      }
    }

    // Wall hit targets (only while adding)
    if (state.adding) {
      for (const w of p.walls) {
        const g = geom.get(w.id);
        el('line', {
          x1: g.ax, y1: g.ay, x2: g.bx, y2: g.by,
          stroke: 'transparent', 'stroke-width': 0.55, 'data-wid': w.id,
        }, svg).style.cursor = 'crosshair';
      }
    }

    // Delegated handlers
    svg.querySelectorAll('[data-rid]').forEach((node) => {
      node.addEventListener('pointerdown', (e) => {
        if (state.adding) return;
        e.stopPropagation();
        select({ kind: 'room', id: Number(node.dataset.rid) });
      });
    });
    svg.querySelectorAll('[data-oid]').forEach((node) => {
      node.addEventListener('pointerdown', (e) => {
        if (state.adding) return;
        e.stopPropagation();
        const id = Number(node.dataset.oid);
        select({ kind: 'opening', id });
        startOpeningDrag(e, id);
      });
    });
    svg.querySelectorAll('[data-wid]').forEach((node) => {
      node.addEventListener('pointerdown', (e) => {
        if (!state.adding) return;
        e.stopPropagation();
        placeOpening(Number(node.dataset.wid), e);
      });
    });
  }

  // ---------------------------------------------------------------- selection
  function selectedRoom() {
    const s = state.selected;
    if (!state.plan || !s || s.kind !== 'room') return null;
    return state.plan.rooms.find((r) => r.id === s.id) || null;
  }
  function selectedOpening() {
    const s = state.selected;
    if (!state.plan || !s || s.kind !== 'opening') return null;
    return (state.plan.openings || []).find((o) => o.id === s.id) || null;
  }

  function select(sel) {
    state.selected = sel;
    renderSvg();
    renderInspector();
    renderButtons();
  }

  // --------------------------------------------------------------- inspector
  function renderInspector() {
    const body = $('inspectorBody');
    const room = selectedRoom();
    const opening = selectedOpening();
    if (!state.plan) {
      body.innerHTML = '<div class="empty-note">Select a room, door or window on the plan to rename it or change its size and position.</div>';
      return;
    }
    if (room) {
      const b = roomBounds(room);
      body.innerHTML = `
        <h3>${esc(room.name || 'Room')}</h3>
        <div class="sub">Room ${room.id} · ${esc(room.type)} · ${b.w.toFixed(2)} × ${b.h.toFixed(2)} m · ${polygonAreaM2(room.polygon || []).toFixed(1)} m²</div>
        <div class="fields">
          <label class="field wide">Room name
            <input id="roomName" maxlength="80" value="${esc(room.name || '')}">
          </label>
          <label class="field wide">Room type
            <select id="roomType">${ROOM_TYPES.map((t) => `<option value="${t}"${t === room.type ? ' selected' : ''}>${t.replace('_', ' ')}</option>`).join('')}</select>
          </label>
        </div>
        <div class="selection-actions">
          <button class="primary" id="applyRoomBtn">Save room</button>
        </div>`;
      $('applyRoomBtn').addEventListener('click', applyRoom);
      $('roomName').addEventListener('keydown', (e) => { if (e.key === 'Enter') applyRoom(); });
      return;
    }
    if (opening) {
      const wall = state.plan.walls.find((w) => w.id === opening.wall);
      const g = wall ? wallGeom(wall) : null;
      const isDoor = opening.kind === 'door';
      body.innerHTML = `
        <h3>${isDoor ? 'Door' : 'Window'}</h3>
        <div class="sub">Opening ${opening.id} · wall ${opening.wall}${wall ? ` · ${g.len.toFixed(2)} m long` : ''}</div>
        <div class="fields">
          <label class="field">Kind
            <select id="opKind">
              <option value="door"${isDoor ? ' selected' : ''}>door</option>
              <option value="window"${!isDoor ? ' selected' : ''}>window</option>
            </select>
          </label>
          <label class="field">Wall
            <input id="opWall" type="number" min="0" step="1" value="${opening.wall}">
          </label>
          <label class="field">Offset (m)
            <input id="opOffset" type="number" min="0" step="0.05" value="${((opening.offset || 0) * scale()).toFixed(2)}">
          </label>
          <label class="field">Width (m)
            <input id="opWidth" type="number" min="0.3" step="0.05" value="${((opening.width || 0) * scale()).toFixed(2)}">
          </label>
          <label class="field">Sill (m)
            <input id="opSill" type="number" min="0" step="0.05" value="${(opening.sill || 0).toFixed(2)}">
          </label>
          <label class="field">Height (m)
            <input id="opHeight" type="number" min="0.4" step="0.05" value="${(opening.height || 0).toFixed(2)}">
          </label>
        </div>
        <div class="selection-actions">
          <button class="primary" id="applyOpeningBtn">Save opening</button>
          <button class="danger" id="deleteOpeningBtn2">Delete</button>
        </div>
        <div class="examples"><span style="font-size:10.5px;color:var(--muted)">Tip: drag the opening on the plan to slide it along its wall.</span></div>`;
      $('applyOpeningBtn').addEventListener('click', applyOpening);
      $('deleteOpeningBtn2').addEventListener('click', deleteSelectedOpening);
      return;
    }
    body.innerHTML = '<div class="empty-note">Select a room, door or window on the plan to rename it or change its size and position.</div>';
  }

  async function applyRoom() {
    const room = selectedRoom();
    if (!room) return;
    const name = $('roomName').value.trim();
    const type = $('roomType').value;
    try {
      const data = await api('PATCH', `/api/plans/${state.plan.plan_id}/rooms/${room.id}`, { name, type });
      applyPlan(data.plan, data.validation);
      toast(`Renamed to “${name}”.`);
    } catch (err) { toast(err.message, true); }
  }

  async function applyOpening() {
    const opening = selectedOpening();
    if (!opening) return;
    const body = {
      kind: $('opKind').value,
      wall: Number($('opWall').value),
      offset: Number($('opOffset').value),
      width: Number($('opWidth').value),
      sill: Number($('opSill').value),
      height: Number($('opHeight').value),
    };
    try {
      const data = await api('PATCH', `/api/plans/${state.plan.plan_id}/openings/${opening.id}`, body);
      applyPlan(data.plan, data.validation);
      toast('Opening updated.');
    } catch (err) { toast(err.message, true); }
  }

  async function deleteSelectedOpening() {
    const opening = selectedOpening();
    if (!opening) return;
    try {
      const data = await api('DELETE', `/api/plans/${state.plan.plan_id}/openings/${opening.id}`);
      state.selected = null;
      applyPlan(data.plan, data.validation);
      toast('Opening deleted.');
    } catch (err) { toast(err.message, true); }
  }

  // -------------------------------------------------------------- add opening
  function setAdding(kind) {
    state.adding = state.adding === kind ? null : kind;
    renderButtons();
    renderSvg();
    if (state.adding) toast(`Click a wall to place a ${state.adding}.`, false);
  }

  async function placeOpening(wallId, event) {
    const wall = state.plan.walls.find((w) => w.id === wallId);
    if (!wall) return;
    if (state.adding === 'window' && wall.cls !== 'exterior') {
      toast('Windows go on exterior walls — pick an outside wall.', true);
      return;
    }
    const g = wallGeom(wall);
    const pt = screenToPlan(event);
    const along = clamp((pt.x - g.ax) * g.dx + (pt.y - g.ay) * g.dy, 0, g.len);
    const width = state.adding === 'door' ? 0.9 : 1.2;
    const offset = clamp(along - width / 2, 0.05, Math.max(0.05, g.len - width - 0.05));
    try {
      const data = await api('POST', `/api/plans/${state.plan.plan_id}/openings`, {
        kind: state.adding, wall: wallId, offset, width,
      });
      const newId = data.opening && data.opening.id;
      state.adding = null;
      applyPlan(data.plan, data.validation);
      if (newId !== undefined) select({ kind: 'opening', id: newId });
      toast('Opening added and validated.');
    } catch (err) { toast(err.message, true); }
  }

  // --------------------------------------------------------------- drag opening
  function startOpeningDrag(event, id) {
    const opening = (state.plan.openings || []).find((o) => o.id === id);
    if (!opening) return;
    const wall = state.plan.walls.find((w) => w.id === opening.wall);
    if (!wall) return;
    const g = wallGeom(wall);
    const pt = screenToPlan(event);
    const along = (pt.x - g.ax) * g.dx + (pt.y - g.ay) * g.dy;
    state.drag = {
      id,
      wall,
      grab: along - (opening.offset || 0) * scale(),
      moved: false,
    };
    svg.classList.add('panning');
  }

  function moveDrag(event) {
    const d = state.drag;
    if (!d) return;
    const opening = (state.plan.openings || []).find((o) => o.id === d.id);
    if (!opening) return;
    const g = wallGeom(d.wall);
    const pt = screenToPlan(event);
    const along = (pt.x - g.ax) * g.dx + (pt.y - g.ay) * g.dy;
    const width = (opening.width || 0) * scale();
    const offset = clamp(along - d.grab, 0.03, Math.max(0.03, g.len - width - 0.03));
    opening.offset = Number((offset / scale()).toFixed(4));
    d.moved = true;
    renderSvg();
  }

  async function endDrag() {
    const d = state.drag;
    state.drag = null;
    svg.classList.remove('panning');
    if (!d || !d.moved) return;
    const opening = (state.plan.openings || []).find((o) => o.id === d.id);
    if (!opening) return;
    try {
      const data = await api('PATCH', `/api/plans/${state.plan.plan_id}/openings/${d.id}`, {
        offset: opening.offset * scale(),
      });
      applyPlan(data.plan, data.validation, { keepSelection: true });
    } catch (err) {
      toast(err.message, true);
      try {
        const plan = await api('GET', `/api/plans/${state.plan.plan_id}`);
        applyPlan(plan, plan.validation, { keepSelection: true });
      } catch { /* ignore */ }
    }
  }

  // ------------------------------------------------------------------- report
  function renderReport() {
    const pill = $('okPill');
    const list = $('issues');
    const metrics = $('metrics');
    const report = state.report;
    metrics.innerHTML = '';
    if (!state.plan || !report) {
      pill.className = 'pill';
      pill.textContent = 'not run';
      list.innerHTML = '<li><small>No plan loaded.</small></li>';
      return;
    }
    const errors = report.errors || [];
    const warnings = report.warnings || [];
    const repairs = report.repairs || [];
    if (report.ok) {
      pill.className = 'pill ok';
      pill.textContent = errors.length ? 'valid' : 'valid';
    } else {
      pill.className = 'pill bad';
      pill.textContent = `${errors.length} error${errors.length === 1 ? '' : 's'}`;
    }
    const items = [];
    for (const issue of repairs) items.push({ cls: 'repair', code: issue.code, message: issue.message });
    for (const issue of errors) items.push({ cls: 'error', code: issue.code, message: issue.message, entity: issue.entity });
    for (const issue of warnings) items.push({ cls: 'warning', code: issue.code, message: issue.message, entity: issue.entity });
    if (!items.length) {
      list.innerHTML = '<li class="repair"><small>All geometry checks passed: rooms closed, no overlaps, openings on walls, every room reachable.</small></li>';
    } else {
      list.innerHTML = items.map((it, i) =>
        `<li class="${it.cls}" data-i="${i}"><code>${esc(it.code)}</code><br>${esc(it.message)}</li>`
      ).join('');
      list.querySelectorAll('li').forEach((node) => {
        node.addEventListener('click', () => {
          const it = items[Number(node.dataset.i)];
          if (it && it.entity !== undefined && it.entity !== null) focusEntity(it.entity);
        });
      });
    }
    const m = report.metrics || {};
    metrics.innerHTML = [
      ['Rooms', m.rooms], ['Floor area', `${m.area_m2 ?? 0} m²`],
      ['Doors', m.doors], ['Windows', m.windows],
    ].map(([label, value]) => `<div class="metric"><b>${esc(value ?? '–')}</b><span>${label}</span></div>`).join('');
  }

  function focusEntity(entity) {
    if (!state.plan) return;
    const id = Array.isArray(entity) ? entity[0] : entity;
    if (state.plan.rooms.some((r) => r.id === id)) {
      select({ kind: 'room', id });
    } else if ((state.plan.openings || []).some((o) => o.id === id)) {
      select({ kind: 'opening', id });
    }
  }

  // -------------------------------------------------------------- plan loading
  function applyPlan(plan, report, opts = {}) {
    if (!plan) return;
    const changed = !state.plan || state.plan.plan_id !== plan.plan_id;
    state.plan = plan;
    state.report = report || plan.validation || null;
    if (changed) {
      state.selected = null;
      state.view = null;
      state.viewPlanId = plan.plan_id;
      state.adding = null;
    } else if (!opts.keepSelection) {
      // keep selection if the entity still exists
      const sel = state.selected;
      if (sel && sel.kind === 'room' && !plan.rooms.some((r) => r.id === sel.id)) state.selected = null;
      if (sel && sel.kind === 'opening' && !(plan.openings || []).some((o) => o.id === sel.id)) state.selected = null;
    }
    renderAll();
    refreshPlans();
  }

  async function loadPlan(planId) {
    try {
      const plan = await api('GET', `/api/plans/${encodeURIComponent(planId)}`);
      applyPlan(plan, plan.validation);
      const url = new URL(location.href);
      url.searchParams.set('plan', planId);
      history.replaceState(null, '', url);
    } catch (err) { toast(err.message, true); }
  }

  async function refreshPlans() {
    try {
      const data = await api('GET', '/api/plans');
      renderPlanList(data.plans || []);
    } catch { /* offline list */ }
  }

  function renderPlanList(items) {
    const list = $('planList');
    if (!items.length) {
      list.innerHTML = '<li><small>No plans yet.</small></li>';
      return;
    }
    list.innerHTML = items.map((it) => {
      const active = state.plan && state.plan.plan_id === it.plan_id;
      const m = it.metrics || {};
      return `<li data-id="${esc(it.plan_id)}" class="${active ? 'active' : ''}">
        <span>${esc(it.title)}<br><small>${m.rooms || 0} rooms · ${m.area_m2 || 0} m² · ${esc(it.source || '')}</small></span>
        <button class="ghost" data-del="${esc(it.plan_id)}" title="Delete plan" style="padding:2px 7px;font-size:14px;line-height:1">×</button>
      </li>`;
    }).join('');
    list.querySelectorAll('li[data-id]').forEach((node) => {
      node.addEventListener('click', (e) => {
        if (e.target.closest('[data-del]')) return;
        loadPlan(node.dataset.id);
      });
    });
    list.querySelectorAll('[data-del]').forEach((btn) => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const id = btn.dataset.del;
        if (!confirm('Delete this plan?')) return;
        try {
          await api('DELETE', `/api/plans/${encodeURIComponent(id)}`);
          if (state.plan && state.plan.plan_id === id) {
            state.plan = null; state.report = null; state.selected = null; state.view = null;
            renderAll();
            const url = new URL(location.href);
            url.searchParams.delete('plan');
            history.replaceState(null, '', url);
          }
          refreshPlans();
          toast('Plan deleted.');
        } catch (err) { toast(err.message, true); }
      });
    });
  }

  // ------------------------------------------------------------------ actions
  async function withBusy(btn, label, fn) {
    if (state.busy) return;
    state.busy = true;
    const original = btn.innerHTML;
    btn.innerHTML = `<span class="spinner"></span> ${esc(label)}`;
    [$('generateBtn'), $('anotherBtn'), $('uploadBtn')].forEach((b) => { b.disabled = true; });
    try {
      await fn();
    } finally {
      state.busy = false;
      btn.innerHTML = original;
      [$('generateBtn'), $('anotherBtn'), $('uploadBtn')].forEach((b) => { b.disabled = false; });
      renderButtons();
    }
  }

  async function generate(seed, useLast) {
    const prompt = useLast ? state.lastPrompt : $('prompt').value.trim();
    if (!prompt) { toast('Describe the home you want first.', true); return; }
    state.lastPrompt = prompt;
    state.seed = seed || 0;
    const btn = seed ? $('anotherBtn') : $('generateBtn');
    addMessage('user', seed ? `Another option please.\n${prompt}` : prompt);
    const thinking = addMessage('assistant', seed ? 'Designing another arrangement…' : 'Designing your layout…');
    await withBusy(btn, seed ? 'Re-planning' : 'Designing', async () => {
      const started = Date.now();
      try {
        const data = await api('POST', '/api/chat', { message: prompt, seed: state.seed });
        const secs = ((Date.now() - started) / 1000).toFixed(1);
        thinking.textContent = `${data.message}\n\n— ${data.provider} · ${secs} s`;
        applyPlan(data.plan, data.validation);
      } catch (err) {
        thinking.textContent = `Could not generate the plan: ${err.message}`;
        toast(err.message, true);
      }
    });
  }

  async function uploadPlan() {
    const input = $('planFile');
    const file = input.files && input.files[0];
    if (!file) { toast('Choose a PNG, JPG or PDF first.', true); return; }
    const width = Number($('scaleInput').value);
    const fd = new FormData();
    fd.append('file', file);
    if (Number.isFinite(width) && width > 0) fd.append('width_m', String(width));
    addMessage('user', `Uploaded ${file.name}${Number.isFinite(width) && width > 0 ? ` (${width} m wide)` : ''}.`);
    const thinking = addMessage('assistant', 'Reading the plan with the vision model… this can take a minute.');
    await withBusy($('uploadBtn'), 'Reading plan', async () => {
      const started = Date.now();
      try {
        const data = await api('POST', '/api/upload', fd);
        const secs = ((Date.now() - started) / 1000).toFixed(1);
        thinking.textContent = `${data.message}\n\n— ${data.provider} · ${secs} s`;
        applyPlan(data.plan, data.validation);
      } catch (err) {
        thinking.textContent = `Could not read the plan: ${err.message}`;
        toast(err.message, true);
      }
    });
  }

  async function validatePlan(repair) {
    if (!state.plan) return;
    try {
      const data = await api('POST', `/api/plans/${state.plan.plan_id}/validate`, { repair });
      applyPlan(data.plan, data.validation, { keepSelection: true });
      const r = data.validation;
      toast(repair
        ? (r.repairs.length ? `Repaired ${r.repairs.length} issue(s); ${r.errors.length} left.` : `Nothing to repair; ${r.errors.length} error(s) left.`)
        : (r.ok ? 'Validation passed.' : `${r.errors.length} error(s) found.`), !r.ok);
    } catch (err) { toast(err.message, true); }
  }

  function open3d() {
    if (!state.plan) return;
    const model = `/api/plans/${encodeURIComponent(state.plan.plan_id)}/scene.glb`;
    const name = state.plan.title || state.plan.plan_id;
    window.open(`/frontend/viewer.html?model=${encodeURIComponent(model)}&name=${encodeURIComponent(name)}`, '_blank');
  }

  function downloadJson() {
    if (!state.plan) return;
    window.location.href = `/api/plans/${encodeURIComponent(state.plan.plan_id)}/export.json`;
  }

  async function downloadGlb() {
    if (!state.plan) return;
    try {
      const res = await fetch(`/api/plans/${encodeURIComponent(state.plan.plan_id)}/scene.glb`);
      if (!res.ok) throw new Error(`GLB export failed (${res.status})`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${state.plan.plan_id}.glb`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 3000);
      toast('GLB downloaded.');
    } catch (err) { toast(err.message, true); }
  }

  // -------------------------------------------------------------------- health
  async function loadHealth() {
    const pill = $('providerPill');
    try {
      const info = await api('GET', '/api/health');
      const ok = info.available;
      pill.classList.toggle('offline', !ok);
      if (ok) {
        pill.innerHTML = `<b>●</b> ${esc(info.provider)} · ${esc(info.text_model)}${info.vision_model ? ` / ${esc(info.vision_model)}` : ''}`;
      } else {
        pill.innerHTML = `<b>●</b> no GenAI provider · deterministic fallback`;
        pill.title = 'Start Ollama (ollama serve) or set OPENAI_API_KEY for the full GenAI path.';
      }
    } catch {
      pill.classList.add('offline');
      pill.innerHTML = '<b>●</b> backend unreachable';
    }
  }

  // ------------------------------------------------------------------- events
  function initEvents() {
    $('generateBtn').addEventListener('click', () => generate(0, false));
    $('anotherBtn').addEventListener('click', () => {
      if (!state.lastPrompt) { toast('Generate a plan first, then ask for another option.', true); return; }
      generate(state.seed + 1, true);
    });
    $('prompt').addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') generate(0, false);
    });
    $('examples').addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-prompt]');
      if (!btn) return;
      $('prompt').value = btn.dataset.prompt;
      $('prompt').focus();
    });
    $('uploadBtn').addEventListener('click', uploadPlan);
    $('addDoorBtn').addEventListener('click', () => setAdding('door'));
    $('addWindowBtn').addEventListener('click', () => setAdding('window'));
    $('deleteOpeningBtn').addEventListener('click', deleteSelectedOpening);
    $('validateBtn').addEventListener('click', () => validatePlan(false));
    $('repairBtn').addEventListener('click', () => validatePlan(true));
    $('open3dBtn').addEventListener('click', open3d);
    $('exportBtn').addEventListener('click', downloadJson);
    $('exportGlbBtn').addEventListener('click', downloadGlb);
    $('docsBtn').addEventListener('click', () => window.open('/docs', '_blank'));

    // background pan + wheel zoom
    svg.addEventListener('pointerdown', (e) => {
      if (e.button !== 0) return;
      if (e.target.closest('[data-rid],[data-oid],[data-wid]')) return;
      state.pan = {
        x: e.clientX,
        y: e.clientY,
        view: { ...state.view },
        start: screenToPlan(e),
        rect: svg.getBoundingClientRect(),
      };
      svg.classList.add('panning');
    });
    svg.addEventListener('wheel', (e) => {
      if (!state.view) return;
      e.preventDefault();
      const v = state.view;
      const rect = svg.getBoundingClientRect();
      const unit = Math.min(rect.width / v.w, rect.height / v.h);
      const offsetX = (rect.width - v.w * unit) / 2;
      const offsetY = (rect.height - v.h * unit) / 2;
      const px = (e.clientX - rect.left - offsetX) / unit;
      const py = (e.clientY - rect.top - offsetY) / unit;
      const factor = Math.exp(e.deltaY * 0.0015);
      const w = clamp(v.w * factor, 1, 260);
      const h = w * (v.h / v.w);
      const unit2 = Math.min(rect.width / w, rect.height / h);
      const offsetX2 = (rect.width - w * unit2) / 2;
      const offsetY2 = (rect.height - h * unit2) / 2;
      state.view = {
        x: v.x + px - (e.clientX - rect.left - offsetX2) / unit2,
        y: v.y + py - (e.clientY - rect.top - offsetY2) / unit2,
        w, h,
      };
      setViewBox();
    }, { passive: false });

    window.addEventListener('pointermove', (e) => {
      if (state.pan) {
        const rect = state.pan.rect;
        const v0 = state.pan.view;
        const unit = Math.min(rect.width / v0.w, rect.height / v0.h);
        const offsetX = (rect.width - v0.w * unit) / 2;
        const offsetY = (rect.height - v0.h * unit) / 2;
        state.view = {
          ...state.view,
          x: state.pan.start.x - (e.clientX - rect.left - offsetX) / unit,
          y: state.pan.start.y - (e.clientY - rect.top - offsetY) / unit,
        };
        setViewBox();
      } else if (state.drag) {
        moveDrag(e);
      }
    });
    window.addEventListener('pointerup', () => {
      if (state.pan) {
        state.pan = null;
        svg.classList.remove('panning');
      }
      if (state.drag) endDrag();
    });

    window.addEventListener('keydown', (e) => {
      const tag = (e.target.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
      if (e.key === 'Escape') {
        state.adding = null;
        renderButtons();
        renderSvg();
      }
      if ((e.key === 'Delete' || e.key === 'Backspace') && selectedOpening()) {
        e.preventDefault();
        deleteSelectedOpening();
      }
    });

    window.addEventListener('resize', () => {
      if (!state.plan || !state.view) return;
      const rect = svg.getBoundingClientRect();
      const aspect = rect.width / Math.max(1, rect.height);
      const v = state.view;
      const cx = v.x + v.w / 2, cy = v.y + v.h / 2;
      let w = v.w, h = v.h;
      if (w / h > aspect) h = w / aspect; else w = h * aspect;
      state.view = { x: cx - w / 2, y: cy - h / 2, w, h };
      setViewBox();
    });
  }

  // --------------------------------------------------------------------- boot
  async function boot() {
    initEvents();
    loadHealth();
    refreshPlans();
    const planId = new URLSearchParams(location.search).get('plan');
    if (planId) {
      await loadPlan(planId);
    } else {
      try {
        const data = await api('GET', '/api/plans');
        if (data.plans && data.plans.length) {
          await loadPlan(data.plans[0].plan_id);
        } else {
          renderAll();
        }
      } catch {
        renderAll();
      }
    }
  }

  boot();
})();
