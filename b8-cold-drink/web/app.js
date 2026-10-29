/*
 * B8 cold drink simulator.
 *
 * Loads Pyodide (Python for the browser), copies in b8_model.py, b8_controls.py,
 * inputs.toml, inputs_original.toml and bridge.py unchanged, and runs the model
 * on whatever the page's controls say.  This file only does the page: the
 * controls, the drawing of the tank and the graphs.  All the physics is Python.
 */
'use strict';

const PYODIDE_URL = 'https://cdn.jsdelivr.net/npm/pyodide@0.28.3/';
const MODEL_FILES = ['../b8_model.py', '../b8_controls.py', '../inputs.toml', '../inputs_original.toml',
  '../box_test.toml', 'bridge.py'];
const PRESET_FILES = { inputs: 'inputs.toml', original: 'inputs_original.toml', box_test: 'box_test.toml' };
const PLAY_SPEED = 100;                                   // seconds of the run shown per real second
const OPEN_GROUPS = ['room', 'box', 'tank', 'water', 'ice', 'salt', 'drink', 'can', 'can_heat_transfer',
                     'heat_spreading', 'stirrer'];
const TODO_TAGS = ['MEASURE', 'CHECK', 'RIG NOTE', 'ASSUMED'];
const TAGS = {
  MEASURED: ['#15803D', 'measured on the rig'],
  MEASURE: ['#C2410C', 'a placeholder: measure it and put the real number in'],
  'RIG NOTE': ['#B45309', 'from the 20 Oct rig note: check it on the rig'],
  CHECK: ['#B91C1C', 'no record of where it came from: check it'],
  ASSUMED: ['#7C3AED', 'an estimate that fitting a real run would replace'],
  LITERATURE: ['#475569', 'a handbook or paper value'],
  CHOICE: ['#0F766E', 'you choose it when you set up a run'],
  MODEL: ['#1D4ED8', 'switches a piece of physics on or off'],
};
const COLOURS = { drink: '#C2410C', brine: '#0F766E', ice: '#1F2937', tank: '#6B7280', salt: '#7C3AED',
                  room: '#B45309', foam: '#A16207', near: '#0EA5E9' };
// matplotlib's 'coolwarm', 33 steps, so the page uses the same colours as the Python figures
const COOLWARM = [[59,76,192],[68,90,204],[78,104,216],[88,117,225],[98,130,234],[108,143,241],[119,154,247],
  [130,166,251],[141,176,254],[152,185,255],[163,194,254],[174,201,252],[185,208,249],[195,213,244],[204,217,237],
  [213,219,229],[221,220,220],[229,216,209],[236,211,197],[241,204,184],[245,196,172],[247,186,159],[247,176,147],
  [246,165,134],[244,152,122],[240,139,110],[235,125,98],[228,110,86],[221,95,75],[212,78,65],[202,59,55],
  [190,36,46],[180,4,38]];
const T_LOW = -22, T_HIGH = 30;                           // ends of the colour scale, degC

const state = {
  bridge: null, defaults: null, presets: {}, base: null, inputs: null, about: null, options: [],
  quick: [], fields: {}, charts: {}, run: null, runInputs: null, frame: 0, playing: false, playT: 0,
};

// =============================================================================
// Small helpers
// =============================================================================
const $ = (id) => document.getElementById(id);
const clone = (x) => JSON.parse(JSON.stringify(x));
const num = (v) => (v === 'inf' ? Infinity : v === '-inf' ? -Infinity : v);
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const tidy = (v) => Number(v.toPrecision(12));            // drop float noise such as 2.1500000000000004
const short = (v) => Number(v.toPrecision(3)).toString();

function el(tag, props = {}, children = []) {
  const node = Object.assign(document.createElement(tag), props);
  for (const child of [].concat(children)) node.append(child);
  return node;
}

function mmss(t) {
  const sign = t < 0 ? '-' : '';
  t = Math.abs(t);
  return `${sign}${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`;
}

/** Colour for a temperature: blue below 0 C, red above (TwoSlopeNorm(-22, 0, 30) + coolwarm, as in b8_plots.py). */
function tempColour(T, alpha = 1) {
  let x = T <= 0 ? 0.5 * (T - T_LOW) / -T_LOW : 0.5 + 0.5 * T / T_HIGH;
  x = Math.min(Math.max(x, 0), 1) * (COOLWARM.length - 1);
  const i = Math.min(Math.floor(x), COOLWARM.length - 2), f = x - i;
  const c = COOLWARM[i].map((v, k) => Math.round(v + f * (COOLWARM[i + 1][k] - v)));
  return `rgba(${c[0]},${c[1]},${c[2]},${alpha})`;
}

/** The same pseudo-random spots every time, so the ice does not jump about between frames. */
function spots(n, seed) {
  let a = seed;
  const rand = () => {
    a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  return Array.from({ length: n }, () => [rand(), rand()]);
}
const ICE_SPOTS = spots(400, 8), SALT_SPOTS = spots(160, 9);

function setStatus(text, kind = '') {
  $('status').textContent = text;
  $('status').className = 'status ' + kind;
}

// =============================================================================
// Start-up
// =============================================================================
async function start() {
  const say = (text) => { $('loading-text').textContent = text; };
  try {
    say('Loading Python for the browser (Pyodide: about 12 MB the first time, then cached)…');
    const py = await loadPyodide({ indexURL: PYODIDE_URL });
    say('Loading the B8 model…');
    py.FS.mkdirTree('/home/pyodide/b8');
    for (const file of MODEL_FILES) {
      const response = await fetch(file, { cache: 'no-cache' });
      if (!response.ok) throw new Error(`could not load ${file} (HTTP ${response.status})`);
      py.FS.writeFile('/home/pyodide/b8/' + file.split('/').pop(), await response.text());
    }
    py.runPython("import sys; sys.path.insert(0, '/home/pyodide/b8')");
    state.bridge = py.pyimport('bridge');
    const setup = JSON.parse(state.bridge.setup());
    state.defaults = setup.inputs;
    state.presets = { inputs: setup.inputs, original: setup.original, box_test: setup.box_test };
    state.about = setup.about;
    state.options = setup.options;
    state.base = setup.inputs;
    state.inputs = clone(setup.inputs);
    const linked = applyLink();

    buildQuickControls(setup);
    buildAllInputs();
    buildLegend();
    buildCharts();
    wireButtons();
    $('loading').hidden = true;
    $('app').hidden = false;
    new ResizeObserver(sizeTank).observe($('tank').parentElement);
    sizeTank();
    runNow(linked ? 'Opened with the inputs in the link.' : '');
  } catch (err) {
    console.error(err);
    $('loading').classList.add('error');
    say(`Could not start: ${err.message}. The page needs a recent browser, and an internet connection the first time.`);
  }
}

// =============================================================================
// Controls: the quick panel
// =============================================================================
function buildQuickControls(setup) {
  for (const [section, key, label, low, high, step, unit, show] of setup.sliders) {
    const id = `slider-${section}-${key}`;
    const range = el('input', { type: 'range', id, min: low, max: high, step });
    const box = el('input', { type: 'text', inputMode: 'decimal', spellcheck: false, className: 'num' });
    range.setAttribute('aria-label', label);
    box.setAttribute('aria-label', `${label} (${unit})`);
    $('sliders').append(el('div', { className: 'slider' }, [
      el('label', { htmlFor: id, textContent: label }),
      el('span', { className: 'entry' }, [box, el('span', { className: 'unit', textContent: unit })]),
      range]));
    const toShown = (v) => (show === 'log' ? Math.log10(v) : v * show);
    const fromShown = (x) => (show === 'log' ? 10 ** x : x / show);
    // the box holds the number in the unit shown (for a 'log' slider: the value itself)
    const boxText = (v) => (!Number.isFinite(v) ? 'inf'
      : show !== 'log' ? Number((v * show).toPrecision(4)).toString()
      : Math.abs(Math.log10(v)) < 4 ? short(v) : v.toExponential(2));
    const place = (v) => {                              // move the slider to v, widening it if need be
      const x = toShown(v);
      if (!Number.isFinite(x)) {                        // inf: the slider sits at its end
        range.value = range.max;
        return;
      }
      range.min = Math.min(low, x, Number(range.min));
      range.max = Math.max(high, x, Number(range.max));
      range.value = x;
    };
    range.addEventListener('input', () => {
      const v = tidy(fromShown(Number(range.value)));
      state.inputs[section][key] = v;
      box.value = boxText(v);
      box.classList.remove('invalid');
      refreshField(section, key);
    });
    range.addEventListener('change', () => scheduleRun());
    box.addEventListener('change', () => {              // Enter, or leaving the box
      const typed = parseValue(box.value, 0);           // a number, or inf
      if (typed === null || typed === '-inf' || (show === 'log' && typed <= 0)) {
        box.classList.add('invalid');
        setStatus(`${label}: "${box.value}" is not a number`, 'error');
        return;
      }
      box.classList.remove('invalid');
      const v = typed === 'inf' ? Infinity : show === 'log' ? typed : typed / show;
      state.inputs[section][key] = typed === 'inf' ? 'inf' : tidy(v);   // used exactly as typed
      place(v);                                         // the slider only follows
      refreshField(section, key);
      scheduleRun();
    });
    box.addEventListener('keydown', (event) => { if (event.key === 'Enter') box.blur(); });
    state.quick.push(() => {
      const v = num(state.inputs[section][key]);
      range.min = low;
      range.max = high;
      place(v);
      box.value = boxText(v);
      box.classList.remove('invalid');
    });
  }

  for (const [section, key, label] of setup.switches) {
    const box = el('input', { type: 'checkbox' });
    box.addEventListener('change', () => {
      state.inputs[section][key] = box.checked;
      refreshField(section, key);
      scheduleRun();
    });
    $('switches').append(el('label', {}, [box, label]));
    state.quick.push(() => { box.checked = Boolean(state.inputs[section][key]); });
  }

  for (const [section, key, label, values] of setup.options) {
    const radios = values.map((value) => {
      const radio = el('input', { type: 'radio', name: `option-${section}-${key}`, value });
      radio.addEventListener('change', () => {
        state.inputs[section][key] = value;
        refreshField(section, key);
        scheduleRun();
      });
      return radio;
    });
    $('options').append(el('fieldset', {}, [el('legend', { textContent: label }),
      ...radios.map((radio) => el('label', {}, [radio, ' ' + radio.value]))]));
    state.quick.push(() => radios.forEach((radio) => { radio.checked = radio.value === state.inputs[section][key]; }));
  }
  refreshQuick();
}

function refreshQuick() {
  state.quick.forEach((refresh) => refresh());
}

// =============================================================================
// Controls: every input, built from the comments in inputs.toml
// =============================================================================
function buildAllInputs() {
  const root = $('all-inputs');
  const choices = Object.fromEntries(state.options.map(([s, k, , values]) => [`${s}.${k}`, values]));
  for (const [section, info] of Object.entries(state.about)) {
    const group = el('details', { className: 'group', open: OPEN_GROUPS.includes(section) },
      [el('summary', {}, [`[${section}]`, el('small', { textContent: info.note })])]);
    for (const [key, meta] of Object.entries(info.keys)) {
      const value = state.inputs[section][key];
      let field;
      if (typeof value === 'boolean') {
        field = el('input', { type: 'checkbox', checked: value });
        field.addEventListener('change', () => setInput(section, key, field.checked));
      } else if (choices[`${section}.${key}`]) {
        field = el('select', {}, choices[`${section}.${key}`].map((v) => el('option', { value: v, textContent: v })));
        field.addEventListener('change', () => setInput(section, key, field.value));
      } else {
        field = el('input', { type: 'text', inputMode: 'decimal', spellcheck: false });
        field.setAttribute('aria-label', `${section} ${key}`);
        field.addEventListener('change', () => {
          const parsed = parseValue(field.value, state.inputs[section][key]);
          field.classList.toggle('invalid', parsed === null);
          if (parsed !== null) setInput(section, key, parsed);
          else setStatus(`[${section}] ${key}: "${field.value}" is not a number`, 'error');
        });
      }
      const tag = TAGS[meta.tag] || ['#9CA3AF', ''];
      const row = el('div', { className: 'row' }, [
        el('div', { className: 'name', textContent: key.replaceAll('_', ' ') }),
        field,
        el('div', { className: 'meta' }, [
          el('span', { className: 'unit', textContent: meta.unit && meta.unit !== '-' ? meta.unit : '' }),
          el('span', { className: 'tag', textContent: meta.tag, title: tag[1], style: `background:${tag[0]}` }),
          meta.note,
        ]),
      ]);
      row.dataset.search = `${section} ${key} ${meta.tag} ${meta.note}`.toLowerCase();
      row.dataset.tag = meta.tag;
      group.append(row);
      state.fields[`${section}.${key}`] = { row, field };
      refreshField(section, key);
    }
    root.append(group);
  }
  $('filter').addEventListener('input', filterRows);
  $('only-todo').addEventListener('change', filterRows);
}

function parseValue(text, current) {
  const one = (t) => {
    t = t.trim().toLowerCase();
    if (['inf', '+inf', 'infinity'].includes(t)) return 'inf';
    if (t === '-inf') return '-inf';
    const v = Number(t);
    return t !== '' && Number.isFinite(v) ? v : null;
  };
  if (Array.isArray(current)) {
    const parts = text.replace(/[[\]]/g, '').split(/[,;\s]+/).filter(Boolean).map(one);
    return parts.length === current.length && parts.every((v) => v !== null) ? parts : null;
  }
  return one(text);
}

function setInput(section, key, value) {
  state.inputs[section][key] = value;
  refreshField(section, key);
  refreshQuick();
  scheduleRun();
}

function refreshField(section, key) {
  const entry = state.fields[`${section}.${key}`];
  if (!entry) return;
  const value = state.inputs[section][key];
  const { field, row } = entry;
  if (field.type === 'checkbox') field.checked = value;
  else if (field.tagName === 'SELECT') field.value = value;
  else {
    field.value = Array.isArray(value) ? value.join(', ') : String(value);
    field.classList.remove('invalid');
  }
  row.classList.toggle('changed', !same(value, state.base[section][key]));
}

function refreshAllFields() {
  for (const name of Object.keys(state.fields)) {
    const [section, key] = name.split('.');
    refreshField(section, key);
  }
}

function filterRows() {
  const words = $('filter').value.toLowerCase().split(/\s+/).filter(Boolean);
  const todo = $('only-todo').checked;
  for (const group of document.querySelectorAll('#all-inputs details')) {
    let shown = 0;
    for (const row of group.querySelectorAll('.row')) {
      const show = words.every((w) => row.dataset.search.includes(w)) && (!todo || TODO_TAGS.includes(row.dataset.tag));
      row.hidden = !show;
      shown += show;
    }
    group.hidden = shown === 0;
    if ((words.length || todo) && shown) group.open = true;
  }
}

function buildLegend() {
  for (const [tag, [colour, text]] of Object.entries(TAGS)) {
    $('tags-legend').append(el('li', {}, [el('span', { className: 'tag', textContent: tag, style: `background:${colour}` }), text]));
  }
  const stops = [];
  for (let T = T_LOW; T <= T_HIGH; T += 2) stops.push(`${tempColour(T)} ${(100 * (T - T_LOW)) / (T_HIGH - T_LOW)}%`);
  document.querySelector('.scale .bar').style.background = `linear-gradient(to right, ${stops.join(', ')})`;
  document.querySelector('.scale span').textContent = `${T_LOW} °C`;
  document.querySelector('.scale span:nth-of-type(2)').textContent = `+${T_HIGH} °C`;
}

// =============================================================================
// Buttons, presets and shareable links
// =============================================================================
function wireButtons() {
  $('tab-quick-btn').addEventListener('click', () => showTab('quick'));
  $('tab-all-btn').addEventListener('click', () => showTab('all'));
  $('preset').addEventListener('change', () => {
    const preset = $('preset').value;
    if (preset === 'upload') return;
    state.base = state.presets[preset];
    useInputs(clone(state.base), `Started again from ${PRESET_FILES[preset]}.`);
  });
  $('reset').addEventListener('click', () => useInputs(clone(state.base), 'Back to the starting values.'));
  $('load').addEventListener('click', () => $('file').click());
  $('file').addEventListener('change', async () => {
    const file = $('file').files[0];
    if (!file) return;
    const out = JSON.parse(state.bridge.from_toml(await file.text()));
    $('file').value = '';
    if (out.error) { setStatus(`Could not read ${file.name}: ${out.error}`, 'error'); return; }
    state.base = state.defaults;
    const option = $('preset').querySelector('option[value="upload"]');
    option.hidden = false;
    option.textContent = file.name;
    $('preset').value = 'upload';
    useInputs(out.inputs, `Loaded ${file.name} (laid over inputs.toml).`);
  });
  $('download').addEventListener('click', () => {
    const note = `Saved from the B8 web simulator on ${new Date().toLocaleString('en-GB')}.\n` +
                 'Run it with:  python3 b8_simple.py --inputs b8_inputs.toml';
    const text = state.bridge.to_toml(JSON.stringify(state.inputs), note);
    const link = el('a', { href: URL.createObjectURL(new Blob([text], { type: 'text/plain' })), download: 'b8_inputs.toml' });
    document.body.append(link);
    link.click();
    link.remove();
    setStatus('Downloaded b8_inputs.toml.');
  });
  $('share').addEventListener('click', async () => {
    const changes = {};
    for (const [section, values] of Object.entries(state.inputs)) {
      for (const [key, value] of Object.entries(values)) {
        if (!same(value, state.defaults[section][key])) (changes[section] ||= {})[key] = value;
      }
    }
    const url = location.href.split('#')[0] + (Object.keys(changes).length
      ? '#inputs=' + encodeURIComponent(JSON.stringify(changes)) : '');
    history.replaceState(null, '', url);
    try {
      await navigator.clipboard.writeText(url);
      setStatus('Link copied: it holds every value you changed.');
    } catch {
      setStatus('The link in the address bar now holds every value you changed.');
    }
  });
  $('play').addEventListener('click', togglePlay);
  $('time').addEventListener('input', () => { stopPlay(); setFrame(Number($('time').value)); });
}

function showTab(which) {
  $('tab-quick').hidden = which !== 'quick';
  $('tab-all').hidden = which !== 'all';
  $('tab-quick-btn').setAttribute('aria-selected', which === 'quick');
  $('tab-all-btn').setAttribute('aria-selected', which === 'all');
}

function useInputs(inputs, message) {
  state.inputs = inputs;
  refreshQuick();
  refreshAllFields();
  scheduleRun(0, message);
}

/** Inputs carried in the address (#inputs=...), laid over inputs.toml.  Unknown names are ignored. */
function applyLink() {
  if (!location.hash.startsWith('#inputs=')) return false;
  try {
    const changes = JSON.parse(decodeURIComponent(location.hash.slice(8)));
    for (const [section, values] of Object.entries(changes)) {
      for (const [key, value] of Object.entries(values)) {
        if (state.inputs[section] && key in state.inputs[section]) state.inputs[section][key] = value;
      }
    }
    return true;
  } catch {
    return false;
  }
}

// =============================================================================
// Running the model
// =============================================================================
let runTimer = null;

function scheduleRun(delay = 120, message = '') {
  clearTimeout(runTimer);
  setStatus('running…', 'busy');
  // let the browser paint "running…" before Python takes the main thread for a moment
  runTimer = setTimeout(() => requestAnimationFrame(() => setTimeout(() => runNow(message), 0)), delay);
}

function runNow(message = '') {
  const t0 = performance.now();
  const out = JSON.parse(state.bridge.run(JSON.stringify(state.inputs)));
  if (out.error) {
    setStatus(`Cannot run these inputs: ${out.error}`, 'error');
    return;
  }
  state.run = out;
  state.runInputs = clone(state.inputs);
  const S = out.series, last = S.t.length - 1;
  $('time').max = last;
  const t5 = out.summary.time_to_target;
  const tShow = Math.min(num(state.runInputs.drink.goes_in_at) + (t5 ?? 180), S.t[last]);
  updateCharts();
  showSummary();
  stopPlay();
  setFrame(frameAt(tShow));
  const ms = Math.round(performance.now() - t0);
  setStatus(`${message ? message + ' ' : ''}Ran ${Math.round(S.t[last] / 60)} min of the experiment in ${ms} ms.`);
}

/** The last frame at or before time t (s). */
function frameAt(t) {
  const times = state.run.series.t;
  let lo = 0, hi = times.length - 1;
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2);
    if (times[mid] <= t) lo = mid; else hi = mid - 1;
  }
  return lo;
}

function showSummary() {
  const list = $('summary');
  list.replaceChildren();
  for (const line of state.run.lines) {
    list.append(el('li', { className: line.startsWith('warning') ? 'warning' : '', textContent: line }));
  }
  const rig = state.run.rig;
  list.append(el('li', { className: 'rig',
    textContent: `U across the can at a 25 K difference ${rig.U_can_at_25K.toFixed(0)} W/(m² K) · ` +
                 `heat leak through the box ${rig.UA_box.toFixed(2)} W/K` }));
}

function setFrame(i) {
  state.frame = i;
  $('time').value = i;
  const S = state.run.series, t = S.t[i];
  const tIn = num(state.runInputs.drink.goes_in_at);
  $('clock').textContent = `t = ${mmss(t)}  ` + (S.drink_in[i] ? `(drink in ${mmss(t - tIn)})`
    : Number.isFinite(tIn) ? `(drink in at ${mmss(tIn)})` : '(no drink in this run)');
  drawTank();
  for (const chart of Object.values(state.charts)) chart.draw();
}

// =============================================================================
// Play
// =============================================================================
function togglePlay() {
  if (state.playing) stopPlay(); else startPlay();
}

function startPlay() {
  if (!state.run) return;
  const S = state.run.series;
  if (state.frame >= S.t.length - 1) setFrame(0);
  state.playing = true;
  state.playT = S.t[state.frame];
  $('play').textContent = '❚❚ Pause';
  let before = performance.now();
  const tick = (now) => {
    if (!state.playing) return;
    state.playT += (PLAY_SPEED * (now - before)) / 1000;    // follow the real clock, however slow the drawing
    before = now;
    const end = S.t[S.t.length - 1];
    setFrame(frameAt(Math.min(state.playT, end)));
    if (state.playT >= end) stopPlay(); else requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

function stopPlay() {
  state.playing = false;
  $('play').textContent = '▶ Play';
}

// =============================================================================
// The tank, seen from the long side (the same drawing as b8_plots.TankView)
// =============================================================================
function sizeTank() {
  const canvas = $('tank'), dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(canvas.clientWidth * dpr);
  canvas.height = Math.round(canvas.clientHeight * dpr);
  canvas.getContext('2d').setTransform(dpr, 0, 0, dpr, 0, 0);
  drawTank();
}

let hatch = null;

function drawTank() {
  const canvas = $('tank'), ctx = canvas.getContext('2d');
  const W = canvas.clientWidth, Hpx = canvas.clientHeight;
  ctx.clearRect(0, 0, W, Hpx);
  if (!state.run) return;
  const p = state.runInputs, S = state.run.series, i = state.frame;
  const at = (name) => S[name][i];

  // sizes in cm, as in the Python drawing
  const L = 100 * p.tank.length, H = 100 * p.tank.height;
  const gl = Math.max(100 * p.tank.glass_thickness, 0.35), g = 100 * p.box.clearance, f = 100 * p.box.wall_thickness;
  // the can to scale, as it sits: lying along the tank (seen side on) or upright
  const lying = state.run.rig.can_lying, r = 50 * p.can.diameter;
  const canW = lying ? 100 * p.can.height : 2 * r, canH = lying ? 2 * r : 100 * p.can.height;
  const canX = 0.62 * L, waitX = L + gl + g + f + 2 + canW / 2;
  const x0 = -(gl + g + f) - 1, x1 = waitX + canW / 2 + 1, y0 = -(gl + f) - 1, y1 = H + gl + g + f + 1;
  const k = Math.min(W / (x1 - x0), Hpx / (y1 - y0));
  const ox = (W - k * (x1 - x0)) / 2, oy = (Hpx - k * (y1 - y0)) / 2;
  const X = (x) => ox + k * (x - x0);
  const Y = (y) => Hpx - oy - k * (y - y0);
  const font = Math.max(10.5, Math.min(14, 0.55 * k));
  const box = (x, y, w, h, fill, stroke, width = 1) => {
    ctx.beginPath();
    ctx.rect(X(x), Y(y + h), k * w, k * h);
    if (fill) { ctx.fillStyle = fill; ctx.fill(); }
    if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = width; ctx.stroke(); }
  };
  const label = (x, y, lines, { align = 'left', colour = COLOURS.ice, size = font, middle = false } = {}) => {
    ctx.font = `${size}px Inter, system-ui, sans-serif`;
    const lh = size * 1.25, w = Math.max(...lines.map((l) => ctx.measureText(l).width));
    let px = X(x), py = Y(y);
    if (align === 'right') px -= w; else if (align === 'center') px -= w / 2;
    if (middle) py -= (lines.length * lh) / 2;
    ctx.fillStyle = 'rgba(255,255,255,0.82)';
    ctx.beginPath();
    ctx.roundRect(px - 4, py - 3, w + 8, lines.length * lh + 6, 4);
    ctx.fill();
    ctx.fillStyle = colour;
    ctx.textBaseline = 'top';
    lines.forEach((line, n) => ctx.fillText(line, px, py + n * lh));
  };

  // styrofoam box, the air gap, and the glass coloured by its own temperature
  box(-gl - g - f, -gl - f, L + 2 * (gl + g + f), H + gl + g + 2 * f, '#F3E8C8', '#D6C79A');
  box(-gl - g, -gl, L + 2 * (gl + g), H + gl + g, '#F8FAFC');
  box(-gl, -gl, L + 2 * gl, H + gl, tempColour(at('T_tank')), '#475569');
  box(0, 0, L, H, '#F8FAFC');

  // brine up to the surface, ring by ring: the outermost ring fills the tank, then each
  // ring nearer the can is drawn on top of it: bands either side of an upright can,
  // shells round one lying down
  const level = Math.min(100 * at('level'), H + 1);
  const edges = state.run.rig.ring_edges.map((r) => 100 * r), rings = S.T_rings[i];
  const base = 100 * (S.drink_in[i] ? at('can_base') : p.can.base_height);
  box(0, 0, L, level, tempColour(rings[rings.length - 1], 0.85));
  ctx.save();
  ctx.beginPath();
  ctx.rect(X(0), Y(level), k * L, k * level);
  ctx.clip();
  for (let n = rings.length - 2; n >= 0; n--) {
    if (lying) {
      const pad = edges[n + 1] - r;
      ctx.beginPath();
      ctx.roundRect(X(canX - canW / 2 - pad), Y(base + canH + pad), k * (canW + 2 * pad), k * (canH + 2 * pad), k * pad);
      ctx.fillStyle = tempColour(rings[n], 0.85);
      ctx.fill();
    } else {
      const left = Math.max(canX - edges[n + 1], 0), right = Math.min(canX + edges[n + 1], L);
      box(left, 0, right - left, level, tempColour(rings[n], 0.85));
    }
  }
  ctx.restore();
  // how far a point is from the can's axis, measured as the rings are
  const distance = (x, y) => (lying
    ? r + Math.hypot(Math.max(Math.abs(x - canX) - canW / 2, 0), Math.max(Math.abs(y - base - r) - r, 0))
    : Math.abs(x - canX));
  ctx.strokeStyle = '#334155';
  ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(X(0), Y(level)); ctx.lineTo(X(L), Y(level)); ctx.stroke();

  // salt crystals on the floor, as a loose pile (~45 % gaps)
  const saltH = (100 * at('salt_solid')) / p.materials.salt_density / (0.55 * state.run.rig.floor_area);
  if (saltH > 0.02) {
    box(0, 0, L, saltH, '#E5E7EB');
    const n = Math.floor(SALT_SPOTS.length * Math.min(1, at('salt_solid') / Math.max(p.salt.mass, 1e-9)));
    for (const [u, v] of SALT_SPOTS.slice(0, n)) box(u * (L - 0.4), v * Math.max(saltH - 0.4, 0), 0.4, 0.4, 'white', '#9CA3AF', 0.5);
  }

  // crushed ice spread through the heap; each piece is drawn at the size of the pieces in
  // its own ring, so the ice next to the can is seen to shrink first
  if (at('ice') > 1e-6) {
    const side = 100 * at('ice_side'), bottom = 100 * at('heap_bottom'), top = 100 * at('heap_top');
    const sides = S.ice_sides[i].map((a) => 100 * a);
    const ringOf = (d) => { const k = edges.slice(1).findIndex((e) => d < e); return k < 0 ? sides.length - 1 : k; };
    const area = (1 - p.ice.heap_porosity) * L * (top - bottom);
    const n = Math.min(ICE_SPOTS.length, Math.max(1, Math.round(area / (side * side))));
    ctx.globalAlpha = 0.95;
    for (const [u, v] of ICE_SPOTS.slice(0, n)) {
      const x = u * L, a = sides[ringOf(distance(x, bottom + v * (top - bottom)))];
      if (a > 0) box(Math.min(Math.max(x - a / 2, 0), L - a), bottom + v * Math.max(top - bottom - a, 0), a, a, '#E0F2FE', '#7DD3FC', 0.8);
    }
    ctx.globalAlpha = 1;
    label(0.03 * L, Math.min(bottom + (top - bottom) / 2, H - 1), [`ice ${at('ice').toFixed(2)} kg`,
      `inside ${at('T_ice').toFixed(1)} °C`, `surface ${at('T_surface').toFixed(1)} °C`], { middle: true, size: font * 0.92 });
  }

  // the can: in the bath, or waiting beside the box
  const inBath = S.drink_in[i], frozen = at('drink_frozen');
  const cx = inBath ? canX : waitX, cy = inBath ? 100 * at('can_base') : -(gl + f);
  ctx.globalAlpha = inBath ? 1 : 0.6;
  ctx.beginPath();
  ctx.roundRect(X(cx - canW / 2), Y(cy + canH), canW * k, canH * k, 0.8 * k);
  ctx.fillStyle = frozen > 0 ? '#E0F2FE' : tempColour(at('T_drink'));
  ctx.fill();
  if (frozen > 0) {                                     // ice in the can is hatched; it grows in from the wall
    hatch ||= hatchPattern(ctx);
    ctx.fillStyle = hatch;
    ctx.fill();
    const s = Math.sqrt(1 - frozen);
    ctx.beginPath();
    ctx.roundRect(X(cx - s * canW / 2), Y(cy + (1 + s) * canH / 2), s * canW * k, s * canH * k, 0.5 * k);
    ctx.fillStyle = tempColour(at('T_drink'));
    ctx.fill();
  }
  const gas = 100 * state.run.rig.can_gas_depth;        // the gas above the drink: no heat through it
  if (gas > 0) {
    ctx.fillStyle = '#F8FAFC';
    ctx.fillRect(X(cx - canW / 2 + 0.25), Y(cy + canH - 0.25), (canW - 0.5) * k, (gas - 0.25) * k);
  }
  ctx.beginPath();
  ctx.roundRect(X(cx - canW / 2), Y(cy + canH), canW * k, canH * k, 0.8 * k);
  ctx.strokeStyle = '#475569';
  ctx.lineWidth = 1.2;
  ctx.stroke();
  if (lying) {                                          // the lid end, on the right
    ctx.beginPath();
    ctx.moveTo(X(cx + canW / 2 - 0.7), Y(cy + 0.4));
    ctx.lineTo(X(cx + canW / 2 - 0.7), Y(cy + canH - 0.4));
    ctx.lineWidth = 0.8;
    ctx.stroke();
  }
  ctx.globalAlpha = 1;
  const drinkLines = ['drink', `${at('T_drink').toFixed(1)} °C`];
  if (frozen > 0) drinkLines.push(`${Math.round(100 * frozen)} % frozen`);
  if (!inBath) drinkLines.push(Number.isFinite(num(p.drink.goes_in_at)) ? `in at ${mmss(num(p.drink.goes_in_at))}` : 'not in this run');
  label(cx, cy + canH / 2, drinkLines, { align: 'center', middle: true });
  if (inBath) label(cx + canW / 2 + 0.3, cy + (lying ? 0 : 0.2 * canH) + 3 * font / k, ['next to', 'the can', `${at('T_near').toFixed(1)} °C`],
    { colour: COLOURS.near, size: font * 0.9 });

  // brine, glass, foam and the clock
  label(L - 0.5, Math.max(level - 1, 0.8 + Math.max(saltH, 0)),
    [`brine ${at('T_brine').toFixed(1)} °C`, `${(100 * at('w')).toFixed(1)} % salt`], { align: 'right', colour: COLOURS.brine });
  if (saltH > 0.02) label(0.03 * L, saltH + 1.6, [`salt crystals ${Math.round(1000 * at('salt_solid'))} g`], { colour: '#4B5563', size: font * 0.9 });
  label(L + gl, -gl - 0.3 - font / k, [`glass ${at('T_tank').toFixed(1)} °C`], { align: 'right', colour: COLOURS.tank, size: font * 0.9 });
  ctx.save();
  ctx.translate(X(-gl - g - f / 2), Y(H / 2));
  ctx.rotate(-Math.PI / 2);
  ctx.font = `${font * 0.9}px Inter, system-ui, sans-serif`;
  ctx.fillStyle = '#8A7A4A';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(`styrofoam, middle ${at('T_foam').toFixed(0)} °C`, 0, 0);
  ctx.restore();
  ctx.textAlign = 'left';
}

function hatchPattern(ctx) {
  const tile = el('canvas', { width: 8, height: 8 });
  const g = tile.getContext('2d');
  g.strokeStyle = '#64748B';
  g.lineWidth = 1;
  g.beginPath();
  g.moveTo(0, 8); g.lineTo(8, 0);
  g.moveTo(-2, 2); g.lineTo(2, -2);
  g.moveTo(6, 10); g.lineTo(10, 6);
  g.stroke();
  return ctx.createPattern(tile, 'repeat');
}

// =============================================================================
// Graphs against time
// =============================================================================
const guides = {
  id: 'b8guides',
  afterDatasetsDraw(chart) {
    if (!state.run) return;
    const { ctx, chartArea: area, scales } = chart;
    const vline = (minutes, colour, dash) => {
      const x = scales.x.getPixelForValue(minutes);
      if (x < area.left || x > area.right) return;
      ctx.save();
      ctx.strokeStyle = colour;
      ctx.setLineDash(dash);
      ctx.beginPath(); ctx.moveTo(x, area.top); ctx.lineTo(x, area.bottom); ctx.stroke();
      ctx.restore();
    };
    for (const [y, colour] of chart.$hlines || []) {
      const py = scales.y.getPixelForValue(y);
      if (py < area.top || py > area.bottom) continue;
      ctx.save();
      ctx.strokeStyle = colour;
      ctx.setLineDash([3, 3]);
      ctx.beginPath(); ctx.moveTo(area.left, py); ctx.lineTo(area.right, py); ctx.stroke();
      ctx.restore();
    }
    const tIn = num(state.runInputs.drink.goes_in_at);
    if (Number.isFinite(tIn)) vline(tIn / 60, '#9CA3AF', [5, 4]);
    vline(state.run.series.t[state.frame] / 60, COLOURS.ice, []);
  },
};

function buildCharts() {
  Chart.defaults.font.family = 'Inter, system-ui, sans-serif';
  Chart.defaults.font.size = 11;
  Chart.defaults.color = '#4B5563';
  const make = (id, yTitle, extraScales = {}) => new Chart($(id), {
    type: 'line',
    data: { datasets: [] },
    plugins: [guides],
    options: {
      animation: false, parsing: false, normalized: true, responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'nearest', axis: 'x', intersect: false },
      elements: { point: { radius: 0 }, line: { borderWidth: 1.6 } },
      scales: {
        x: { type: 'linear', min: 0, title: { display: true, text: 'time (min)' }, grid: { color: '#F0F1F3' } },
        y: { title: { display: true, text: yTitle }, grid: { color: '#F0F1F3' } },
        ...extraScales,
      },
      plugins: {
        legend: { labels: { boxWidth: 14, boxHeight: 2 } },
        tooltip: { callbacks: { title: (items) => `t = ${mmss(60 * items[0].parsed.x)}` } },
      },
      onClick: (event, elements, chart) => {
        stopPlay();
        setFrame(frameAt(60 * chart.scales.x.getValueForPixel(event.x)));
      },
    },
  });
  state.charts.temperatures = make('chart-temperatures', 'temperature (°C)');
  state.charts.masses = make('chart-masses', 'ice in the bath (kg)', {
    y2: { position: 'right', min: 0, title: { display: true, text: 'grams' }, grid: { drawOnChartArea: false } },
  });
  state.charts.heat = make('chart-heat', 'heat flow (W)');
  state.charts.level = make('chart-level', 'height (cm)');
}

function updateCharts() {
  const S = state.run.series, p = state.runInputs;
  const minutes = S.t.map((t) => t / 60);
  const line = (label, values, colour, extra = {}) => ({
    label, borderColor: colour, backgroundColor: colour,
    data: values.map((y, n) => ({ x: minutes[n], y })), ...extra,
  });
  const scaled = (name, factor) => S[name].map((v) => v * factor);
  const c = state.charts;

  c.temperatures.data.datasets = [
    line('drink', S.T_drink.map((v, n) => (S.drink_in[n] ? v : null)), COLOURS.drink),
    line('brine (bulk)', S.T_brine, COLOURS.brine),
    line('brine next to the can', S.T_near.map((v, n) => (S.drink_in[n] ? v : null)), COLOURS.near, { borderWidth: 1.3 }),
    line('ice surface', S.T_surface.map((T, i) => (S.ice[i] > 0 ? T : null)), COLOURS.brine, { borderDash: [4, 3], borderWidth: 1.2 }),
    line('ice (inside)', S.T_ice.map((T, i) => (S.ice[i] > 0 ? T : null)), COLOURS.ice, { borderWidth: 1 }),
    line('tank glass', S.T_tank, COLOURS.tank, { borderWidth: 1 }),
    line('foam (middle)', S.T_foam, COLOURS.foam, { borderWidth: 1, borderDash: [2, 2] }),
  ];
  c.temperatures.$hlines = [[p.simulation.target_temperature, '#9CA3AF'], [p.phase_diagram.eutectic_temperature, COLOURS.brine]];

  c.masses.data.datasets = [
    line('ice in bath (kg)', S.ice, COLOURS.ice),
    line('salt crystals (g)', scaled('salt_solid', 1000), COLOURS.salt, { yAxisID: 'y2' }),
    line('ice in the drink (g)', scaled('drink_frozen', 1000 * state.run.rig.drink_water), COLOURS.drink,
      { yAxisID: 'y2', borderDash: [5, 3] }),
    line(`ice within ${(100 * (state.run.rig.ring_edges[1] - state.run.rig.ring_edges[0])).toFixed(1)} cm of the can (g)`,
      scaled('ice_near', 1000), COLOURS.near, { yAxisID: 'y2', borderWidth: 1.3 }),
  ];
  c.masses.options.scales.y.min = 0;

  c.heat.data.datasets = [
    line('drink → brine', S.Q_drink, COLOURS.drink),
    line('brine → ice (melting)', S.Q_ice, COLOURS.brine),
    line('from the can outwards', S.Q_spread, COLOURS.near, { borderWidth: 1.3 }),
    line('glass → brine', S.Q_tank, COLOURS.tank),
    line('room → box', S.Q_room, COLOURS.room, { borderDash: [2, 2] }),
  ];

  c.level.data.datasets = [
    line('liquid level', scaled('level', 100), COLOURS.brine),
    line('top of the ice', scaled('heap_top', 100), COLOURS.ice, { borderDash: [5, 3], borderWidth: 1.2 }),
  ];
  c.level.$hlines = [[100 * p.tank.height, COLOURS.ice], [100 * (p.can.base_height + p.can.height), COLOURS.drink]];

  for (const chart of Object.values(c)) {
    chart.options.scales.x.max = minutes[minutes.length - 1];
    chart.update('none');
  }
}

start();
