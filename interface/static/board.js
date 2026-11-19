/**
 * Workbench renderer for the local computer or the configured board and sensors.
 * The diagram routes each sensor signal to a compatible board pin.
 */
const viewModes = new Map();
export const sensorHeaderPins = {VCC:[1,17], GND:[6,9,14,20,25,30,34,39], SDA:[3], SCL:[5]};
const pinRoles = Object.keys(sensorHeaderPins);
const wireColors = ['#dc8277', '#a5b2c1', '#e8c476', '#81c5cd'];

export function mountBoard(container, options = {}) {
  let settings = {...options};
  let disposed = false;
  let frame = null;
  const modelParts = [];
  const modelLines = [];
  const modelTexts = [];
  let cameraAngle = .36;
  let cameraTilt = .64;
  let cameraZoom = 1;
  let mode = '3d';
  let pan = [0, 0];
  let positions = {};
  let selectedModel = settings.selected || null;
  let modelWidth = 700;
  let modelHeight = 397;
  let pointerStart = null;
  let modelDirty = true;
  const abort = new AbortController();
  const signal = abort.signal;
  const storageKey = () => 'flight-studio:board-layout:' + (settings.context || 'bench') + ':' + settings.board;
  function restoreLayout() {
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey()));
      mode = viewModes.get(storageKey()) || '3d';
      if (!saved) return;
      cameraAngle = Number.isFinite(saved.angle) ? saved.angle : .36;
      cameraTilt = Number.isFinite(saved.tilt) ? Math.max(.3, Math.min(1.35, saved.tilt)) : .64;
      cameraZoom = Number.isFinite(saved.zoom) ? Math.max(.5, Math.min(2.4, saved.zoom)) : 1;
      if (Array.isArray(saved.pan) && saved.pan.length === 2 && saved.pan.every(Number.isFinite)) pan = saved.pan;
      positions = Object.fromEntries(Object.entries(saved.positions || {}).filter(([, value]) =>
        Array.isArray(value) && value.length === 2 && value.every(Number.isFinite)));
    } catch { /* A new layout remains usable if browser storage is unavailable. */ }
  }
  function saveLayout() {
    try { localStorage.setItem(storageKey(), JSON.stringify({mode, angle:cameraAngle, tilt:cameraTilt, zoom:cameraZoom, pan, positions})); }
    catch { /* Layout persistence is optional. */ }
  }
  restoreLayout();

  container.classList.add('board-stage');
  container.replaceChildren();
  const boardCanvas = document.createElement('canvas');
  boardCanvas.setAttribute('aria-label', 'Workbench ' + (settings.board || ''));
  const labels = document.createElement('div');
  labels.className = 'model-labels';
  const controls = document.createElement('div');
  controls.className = 'board-view-controls';
  controls.setAttribute('role', 'group');
  controls.setAttribute('aria-label', 'Workbench view');
  container.append(boardCanvas, labels, controls);
  const boardContext = boardCanvas.getContext('2d');

  function visibleDevices() {
    return (settings.devices || []).filter(device => device.id && device.model);
  }
  function selectSensor(id) {
    if (!visibleDevices().some(device => device.id === id)) return;
    selectedModel = id;
    updateModel();
    settings.onSelect?.(id);
  }
function box(x, y, z, width, height, depth, color, group = 'board', edge = null) {
  modelParts.push({x, y, z, width, height, depth, color, group, edge})
}

function trace(points, color = '#78a990', width = 0.014, group = 'board') {
  modelLines.push({points, color, width, group})
}

function boardText(text, x, y, z, size, color = '#c3dbc8', group = 'board') {
  modelTexts.push({text, x, y, z, size, color, group})
}

function offset(group) {
  const move = positions[group] || [0, 0];
  if (group === 'board') return [-1.25 + move[0], 0, move[1]];
  const index = Math.max(0, visibleDevices().findIndex(sensor => sensor.id === group));
  return [5.5 + Math.floor(index/2)*2.6 + move[0], .3, (index % 2 ? 2.2 : -3) + move[1]];
}

function syncModelDevices() {
  for (const collection of [modelParts,modelLines,modelTexts]) {
    for (let i=collection.length-1;i>=0;i--) {
      if (collection[i].group !== 'board') collection.splice(i,1)
    }
  }
  labels.replaceChildren();
  for (const sensor of visibleDevices()) {
    addSensor(sensor.id, sensor.model === 'tmp105' ? '#8b7758' : '#625c53', sensor.model.toUpperCase());
    const label = document.createElement('button');
    label.type = 'button';
    label.className = 'model-label';
    label.dataset.sensor = sensor.id;
    label.textContent = sensor.name || sensor.model;
    label.title = [sensor.model, sensor.bus, Number.isInteger(sensor.address) ? '0x' + sensor.address.toString(16) : ''].filter(Boolean).join(' · ');
    label.addEventListener('pointerdown', event => beginDrag(event, sensor.id), {signal});
    label.addEventListener('click', event => { if (event.detail === 0) selectSensor(sensor.id); }, {signal});
    labels.append(label);
  }
  if (selectedModel !== 'board' && !visibleDevices().some(d => d.id === selectedModel)) selectedModel = null;
  updateModel();
}

function signalPin(group, index) {
  return settings.pinAssignments?.[group]?.[pinRoles[index]] || sensorHeaderPins[pinRoles[index]][0];
}
function boardConnector(group, index) {
  const pin = signalPin(group, index);
  const shift=offset('board');
  return [shift[0]-3+Math.floor((pin-1)/2)*.26, .8, shift[2]+(pin%2?-2.19:-2.43)];
}

function rotate(x, y, z, group) {
  return [x,y,z];
}

function point(x, y, z, group) {
  const shift = offset(group);
  return rotate(x, y, z, group).map((value, axis) => value + shift[axis]);
}

function scale() {
  return Math.min(modelWidth / 15.2, Math.max(130, modelHeight - 96) / 9.2) * cameraZoom;
}
function viewAngles() {
  return mode === '2d' ? [0, Math.PI / 2] : [cameraAngle, cameraTilt];
}
function project(vertex) {
  const [x, y, z] = vertex;
  const [angle, tilt] = viewAngles();
  const along = x * Math.sin(angle) + z * Math.cos(angle);
  const across = x * Math.cos(angle) - z * Math.sin(angle);
  return [modelWidth * .47 + across * scale() + pan[0],
    modelHeight * .49 + (along * Math.sin(tilt) - y * Math.cos(tilt)) * scale() + pan[1],
    along * Math.cos(tilt) + y * Math.sin(tilt)];
}
function planeDelta(dx, dy) {
  const [angle, tilt] = viewAngles();
  const across = dx / scale(), along = dy / (scale() * Math.sin(tilt));
  return [across * Math.cos(angle) + along * Math.sin(angle),
    -across * Math.sin(angle) + along * Math.cos(angle)];
}
function footprint(group, padding = 0) {
  const board = group === 'board', x = (board ? 4.5 : .95) + padding, z = (board ? 2.95 : .825) + padding;
  return [[-x,-z],[x,-z],[x,z],[-x,z]].map(([x,z]) => project(point(x,.18,z,group)));
}
function contains(points, x, y) {
  let inside = false;
  for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
    const [xi,yi] = points[i], [xj,yj] = points[j];
    if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}
function hitGroup(x, y) {
  for (const sensor of visibleDevices().toReversed()) {
    if (contains(footprint(sensor.id, .2), x, y)) return sensor.id;
  }
  return contains(footprint('board'), x, y) ? 'board' : null;
}

function shade(hex, factor) {
  const digits = hex.replace('#', '')
  const channels = [0, 2, 4].map(i => Math.min(255, Math.max(0, Math.round(parseInt(digits.slice(i, i + 2), 16) * factor))))
  return `rgb(${channels.join(',')})`
}

function addComputer() {
  // Local workstation, distinct from the Raspberry Pi and its peripheral buses.
  box(0, .12, 0, 7.2, .25, 4.6, '#56616c');
  box(0, .27, -.2, 6.6, .05, 3.9, '#151e29');
  box(0, .3, -.2, 6.1, .02, 3.35, '#263b4a');
  boardText('cFS', -1.3, .34, -.35, .75, '#c5d4df');
  boardText(settings.hostOS || 'Native', -.95, .34, .5, .26, '#95b4c5');
  box(0, .05, 3, 6, .18, 1.5, '#47525d');
  for(let row=0;row<3;row++)for(let col=0;col<12;col++)
    box(-2.6+col*.47, .16, 2.53+row*.35, .35, .04, .24, '#87939d');
}

function addBoard() {
  box(0, 0, 0, 8.5, 0.17, 5.6, '#3c634d')
  box(0, -0.1, 0, 8.44, 0.08, 5.54, '#294735')
  box(-0.5, 0.27, -0.25, 1.9, 0.3, 1.9, '#abb5ab', 'board', '#bdc6b7')
  box(-0.5, 0.44, -0.25, 1.6, 0.04, 1.6, '#bfc9be')
  boardText('BROADCOM', -1.2, 0.49, -0.5, 0.18, '#66796b')
  boardText('BCM2711', -1.15, 0.49, -0.18, 0.16, '#758675')
  box(-0.3, 0.22, 1.73, 1.3, 0.22, 0.82, '#283e37')
  boardText('MEMORY', -0.8, 0.35, 1.65, 0.11, '#83988a')
  box(1.75, 0.2, 0.05, 0.85, 0.23, 1, '#26372f')
  boardText('VIA', 1.5, 0.34, -0.05, 0.15, '#879a8c')
  box(2.2, 0.18, -1.7, 0.7, 0.18, 0.6, '#293b31')
  box(-2.8, 0.19, -0.8, 0.8, 0.2, 0.9, '#9fac9a')
  box(-2.8, 0.3, -0.8, 0.65, 0.035, 0.75, '#bcc9b7')
  box(3.55, 0.75, 1.72, 1.75, 1.35, 1.48, '#aebbb8', 'board', '#d0dad5')
  box(4.44, 0.67, 1.72, 0.025, 0.9, 1.16, '#203139')
  box(4.46, 0.95, 1.72, 0.035, 0.14, 0.67, '#82988a')
  box(3.72, 0.8, -0.09, 1.4, 1.45, 1.35, '#becac3', 'board', '#d1d9d3')
  box(4.44, 0.52, -0.09, 0.03, 0.42, 1.05, '#236c94')
  box(4.44, 1.13, -0.09, 0.03, 0.42, 1.05, '#236c94')
  box(4.46, 0.55, -0.09, 0.035, 0.09, 0.84, '#77a2b0')
  box(4.46, 1.16, -0.09, 0.035, 0.09, 0.84, '#77a2b0')
  box(3.72, 0.8, -1.64, 1.4, 1.45, 1.35, '#becac3', 'board', '#d1d9d3')
  box(4.44, 0.52, -1.64, 0.03, 0.42, 1.05, '#243331')
  box(4.44, 1.13, -1.64, 0.03, 0.42, 1.05, '#243331')
  box(4.46, 0.55, -1.64, 0.035, 0.09, 0.84, '#90a799')
  box(4.46, 1.16, -1.64, 0.035, 0.09, 0.84, '#90a799')
  box(-3.15, 0.35, 2.64, 0.9, 0.55, 0.65, '#b4c0b8')
  box(-3.15, 0.34, 2.98, 0.64, 0.22, 0.025, '#314840')
  for (const x of [-1.9, -0.7]) {
    box(x, 0.28, 2.65, 0.73, 0.4, 0.6, '#b8c5bc')
    box(x, 0.29, 2.97, 0.48, 0.18, 0.025, '#263a35')
  }
  box(0.85, 0.41, 2.63, 0.75, 0.65, 0.65, '#273b31')
  box(0.85, 0.43, 2.97, 0.38, 0.38, 0.025, '#142923')
  box(-0.55, 0.25, -2.3, 5.2, 0.33, 0.48, '#253c2d')
  for (const index of Array.from({length:20}, (_, i) => i)) {
    for (const row of [-2.43, -2.19]) box(-3 + index * 0.26, 0.55, row, 0.075, 0.5, 0.075, '#c9ad69')
  }
  box(-2.15, 0.18, 0.5, 0.19, 0.2, 1.8, '#d7d5b7')
  box(-2.11, 0.28, 0.5, 0.12, 0.06, 1.5, '#4c6750')
  box(1.35, 0.17, 1.57, 0.2, 0.18, 1.65, '#d2d4b4')
  box(1.34, 0.28, 1.57, 0.13, 0.05, 1.47, '#64765c')
  boardText('Raspberry Pi 4 Model B', -2.9, 0.11, -1.74, 0.15)
  boardText('GPIO', 1.6, 0.11, -1.87, 0.14)
  boardText('USB 3.0', 2.9, 1.55, -0.2, 0.14, '#667c73')
  boardText('ETHERNET', 2.87, 1.45, 1.65, 0.13, '#647b70')
  for (const i of Array.from({length:38}, (_, n) => n)) {
    const x = -3.65 + (i % 9) * 0.67
    const z = -1.38 + Math.floor(i / 9) * 0.8
    if ((x > -1.55 && x < 0.55 && z > -1.3 && z < 0.9) || (x > -1.0 && x < 0.5 && z > 1.0)) continue
    box(x, 0.15, z, 0.18, 0.11, 0.09, i % 3 ? '#a99d73' : '#455d40')
    box(x - 0.09, 0.15, z, 0.035, 0.12, 0.1, '#bed0b6')
    box(x + 0.09, 0.15, z, 0.035, 0.12, 0.1, '#bed0b6')
  }
  for (const i of Array.from({length:12}, (_, n) => n)) {
    const z = -1.08 + i * 0.135
    trace([[-1.48, 0.105, z], [-1.7 - i * 0.02, 0.105, z], [-2 - i * 0.02, 0.105, z + 0.33], [-3.7, 0.105, z + 0.33]], '#629c6e', 0.016)
    trace([[0.47, 0.105, z], [0.75 + i * 0.035, 0.105, z], [1.15 + i * 0.035, 0.105, z - 0.34], [2.8, 0.105, z - 0.34]], '#6ca477', 0.016)
  }
  for (const corner of [[-3.85, -2.4], [-3.85, 2.35], [2.55, -2.4], [2.55, 2.35]]) {
    const ring = Array.from({length:25}, (_, i) => [corner[0] + Math.cos(i * Math.PI / 12) * 0.16, 0.11, corner[1] + Math.sin(i * Math.PI / 12) * 0.16])
    trace(ring, '#c4be8b', 0.065)
  }
  box(-3.8, 0.16, 1.45, 0.12, 0.13, 0.2, '#acd87d')
  box(-3.8, 0.16, 1.12, 0.12, 0.13, 0.2, '#d5ad81')
}

function addSensor(group, color, title) {
  box(0, 0.08, 0, 1.9, 0.13, 1.65, color, group)
  box(0, 0.2, -0.12, 0.65, 0.17, 0.65, '#2e3440', group)
  box(0, 0.29, -0.12, 0.53, 0.015, 0.53, '#434a58', group)
  boardText(visibleDevices().find(sensor => sensor.id === group)?.model === 'lsm303dlhc_mag' ? 'XYZ' : visibleDevices().find(sensor => sensor.id === group)?.model === 'tmp105' ? '°C' : 'I2C', -0.18, 0.31, -0.1, 0.18, '#a2adba', group)
  boardText(title, -0.71, 0.16, 0.49, 0.13, '#e0d6eb', group)
  for (const x of [-0.65, -0.22, 0.22, 0.65]) {
    box(x, 0.15, -0.66, 0.2, 0.1, 0.2, '#c7ab72', group)
    box(x, 0.33, -0.66, 0.07, 0.35, 0.07, '#dbc493', group)
    trace([[x, 0.155, -0.6], [x, 0.155, -0.38], [x * 0.35, 0.155, -0.25]], group === 'mag' ? '#b49fc3' : '#cdb796', 0.025, group)
  }
  box(-0.65, 0.2, 0.1, 0.2, 0.12, 0.12, '#c4b893', group)
  box(0.65, 0.2, 0.1, 0.2, 0.12, 0.12, '#c4b893', group)
  for (const x of [-0.78, 0.78]) {
    const ring = Array.from({length:17}, (_, i) => [x + Math.cos(i * Math.PI / 8) * 0.09, 0.16, 0.61 + Math.sin(i * Math.PI / 8) * 0.09])
    trace(ring, '#ceb995', 0.04, group)
  }
}

function drawPolygon(vertices, color, edge) {
  boardContext.beginPath()
  vertices.forEach((vertex, index) => index ? boardContext.lineTo(vertex[0], vertex[1]) : boardContext.moveTo(vertex[0], vertex[1]))
  boardContext.closePath()
  boardContext.fillStyle = color
  boardContext.fill()
  boardContext.strokeStyle = edge || color
  boardContext.lineWidth = 0.45
  boardContext.stroke()
}

function drawFloor() {
  const center = project(point(0, -.6, 0, 'board'))
  boardContext.save()
  boardContext.translate(center[0], center[1] + 11)
  boardContext.scale(1, 0.42)
  const shadow = boardContext.createRadialGradient(0, 0, 10, 0, 0, modelWidth * 0.3)
  shadow.addColorStop(0, '#090c1280')
  shadow.addColorStop(1, '#090c1200')
  boardContext.fillStyle = shadow
  boardContext.fillRect(-modelWidth / 2, -modelWidth / 2, modelWidth, modelWidth)
  boardContext.restore()
}

function drawWires() {
  // The sensor connector follows the role order used by the pinout panel.
  const devices = visibleDevices();
  for (const sensor of devices) {
    if (!sensor.bus) continue;
    for (const [index, color] of wireColors.entries()) {
      const start = boardConnector(sensor.id, index);
      const end = point(-.65 + index * .43, .6, -.66, sensor.id);
      const span = Math.hypot(end[0] - start[0], end[2] - start[2]);
      const lift = Math.min(1.6, .55 + span * .1);
      const bend = .75 + index * .17;
      const a = [start[0], start[1] + lift, start[2] - bend];
      const outward = rotate(0, 0, -bend, sensor.id);
      const b = [end[0] + outward[0], end[1] + lift, end[2] + outward[2]];
      const source=project(start), sink=project(end);
      const lane=source[1]-(index+1)*9-(settings.pinAssignments?.[sensor.id]?.bend||0);
      const points = mode==='2d'?[source,[source[0],lane],[sink[0],lane],sink]:Array.from({length:41}, (_, i) => {
        const t = i / 40, u = 1 - t;
        return project(start.map((value, axis) => u*u*u*value + 3*u*u*t*a[axis] + 3*u*t*t*b[axis] + t*t*t*end[axis]));
      });
      const draw = (width, stroke) => {
        boardContext.beginPath();
        points.forEach((p, i) => i ? boardContext.lineTo(p[0], p[1]) : boardContext.moveTo(p[0], p[1]));
        boardContext.lineWidth = width;
        boardContext.strokeStyle = stroke;
        boardContext.stroke();
      };
      boardContext.save();
      boardContext.lineCap = boardContext.lineJoin = 'round';
      const width = Math.max(1.3, scale() * .045);
      draw(width + 1.8, '#11161dbc');
      draw(width, color);
      draw(Math.max(.45, width * .26), shade(color, 1.3));
      for (const end of [points[0], points.at(-1)]) {
        boardContext.beginPath();
        boardContext.arc(end[0], end[1], Math.max(1.5, width), 0, Math.PI * 2);
        boardContext.fillStyle = '#c1ac7e';
        boardContext.fill();
      }
      if (mode === '2d' && scale() >= 33) {
        const number = String(signalPin(sensor.id, index));
        boardContext.font = 'bold 11px monospace';
        boardContext.textAlign = 'center';
        boardContext.lineWidth = 3;
        boardContext.strokeStyle = '#182029';
        boardContext.strokeText(number, sink[0], sink[1] + 15);
        boardContext.fillStyle = color;
        boardContext.fillText(number, sink[0], sink[1] + 15);
      }
      boardContext.restore();
    }
  }
}

function renderModel() {
  if (disposed || !modelDirty || !boardCanvas.offsetParent) return
  modelDirty = false
  const ratio = Math.min(window.devicePixelRatio || 1, 2)
  modelWidth = boardCanvas.clientWidth
  modelHeight = boardCanvas.clientHeight
  if (boardCanvas.width !== Math.round(modelWidth * ratio) || boardCanvas.height !== Math.round(modelHeight * ratio)) {
    boardCanvas.width = Math.round(modelWidth * ratio)
    boardCanvas.height = Math.round(modelHeight * ratio)
  }
  boardContext.setTransform(ratio, 0, 0, ratio, 0, 0)
  boardContext.clearRect(0, 0, modelWidth, modelHeight)
  drawFloor()
  const shapes = []
  const [angle, tilt] = viewAngles();
  const view = [Math.sin(angle) * Math.cos(tilt), Math.sin(tilt), Math.cos(angle) * Math.cos(tilt)];
  const faceDefinitions = [{ids:[0,1,2,3],normal:[0,-1,0],light:0.5},{ids:[4,7,6,5],normal:[0,1,0],light:1.12},{ids:[0,4,5,1],normal:[0,0,-1],light:0.72},{ids:[3,2,6,7],normal:[0,0,1],light:0.82},{ids:[0,3,7,4],normal:[-1,0,0],light:0.68},{ids:[1,5,6,2],normal:[1,0,0],light:0.9}]
  for (const part of modelParts) {
    const {x,y,z,width:w,height:h,depth:d,group} = part
    const corners = [[x-w/2,y-h/2,z-d/2],[x+w/2,y-h/2,z-d/2],[x+w/2,y-h/2,z+d/2],[x-w/2,y-h/2,z+d/2],[x-w/2,y+h/2,z-d/2],[x+w/2,y+h/2,z-d/2],[x+w/2,y+h/2,z+d/2],[x-w/2,y+h/2,z+d/2]]
    const vertices = corners.map(p => project(point(p[0], p[1], p[2], group)))
    for (const face of faceDefinitions) {
      const normal = rotate(...face.normal, group);
      const visible = normal.reduce((sum, n, i) => sum + n * view[i], 0)
      if (visible <= 0) continue
      const points = face.ids.map(i => vertices[i])
      const depth = points.reduce((sum, p) => sum + p[2], 0) / 4
      const layer = part.width > 1.5 && part.height < 0.2 && part.y <= 0.08 ? 0 : 2
      shapes.push({type:'face',points,depth,layer,color:shade(part.color,face.light),edge:part.edge})
    }
  }
  for (const line of modelLines) {
    const points = line.points.map(p => project(point(p[0], p[1], p[2], line.group)))
    const depth = points.reduce((sum, p) => sum + p[2], 0) / points.length + 0.005
    shapes.push({type:'line',points,depth,layer:1,color:line.color,width:line.width * scale()})
  }
  for (const label of modelTexts) {
    const position = project(point(label.x, label.y, label.z, label.group))
    shapes.push({type:'text',label,depth:position[2] + 0.01,layer:label.y < 0.2 ? 1 : 3})
  }
  shapes.sort((a,b) => a.layer - b.layer || a.depth - b.depth)
  for (const shape of shapes) {
    if (shape.type === 'face') drawPolygon(shape.points, shape.color, shape.edge)
    if (shape.type === 'line') {
      boardContext.beginPath()
      shape.points.forEach((p,i) => i ? boardContext.lineTo(p[0],p[1]) : boardContext.moveTo(p[0],p[1]))
      boardContext.strokeStyle = shape.color
      boardContext.lineWidth = Math.max(.45,shape.width)
      boardContext.stroke()
    }
    if (shape.type === 'text') {
      const label = shape.label
      const origin = project(point(label.x,label.y,label.z,label.group))
      const right = project(point(label.x+1,label.y,label.z,label.group))
      const down = project(point(label.x,label.y,label.z+1,label.group))
      boardContext.save()
      boardContext.transform((right[0]-origin[0])/100,(right[1]-origin[1])/100,(down[0]-origin[0])/100,(down[1]-origin[1])/100,origin[0],origin[1])
      boardContext.font = `500 ${label.size*100}px monospace`
      boardContext.fillStyle = label.color
      boardContext.fillText(label.text,0,0)
      boardContext.restore()
    }
  }
  drawWires()
  if (selectedModel) {
    const points = footprint(selectedModel, .2);
    boardContext.beginPath();
    points.forEach((p,i) => i ? boardContext.lineTo(p[0],p[1]) : boardContext.moveTo(p[0],p[1]));
    boardContext.closePath();
    boardContext.strokeStyle = '#c7a17d';
    boardContext.lineWidth = 1.2;
    boardContext.stroke();
  }
  for (const sensor of visibleDevices()) {
    const group = sensor.id
    const label = [...labels.children].find(element => element.dataset.sensor === group)
    if (!label) continue
    label.classList.toggle('active', group === selectedModel)
    label.setAttribute('aria-pressed', String(group === selectedModel))
    const position = project(point(0,0.2,0,group))
    label.style.left = `${Math.max(15,Math.min(modelWidth-label.offsetWidth-15,position[0]-label.offsetWidth/2))}px`
    const top = Math.min(...footprint(group).map(p => p[1]));
    label.style.top = `${Math.max(12, Math.min(modelHeight - 80, top - 29))}px`;
    label.style.right = 'auto'
    label.style.bottom = 'auto'
  }
}

function updateModel() {
  modelDirty = true
  if (!frame) frame = requestAnimationFrame(() => { frame = null; renderModel(); })
}

function resetCamera() {
  cameraAngle = .36;
  cameraTilt = .64;
  cameraZoom = 1;
  positions = {};
  pan = [0, 0];
  saveLayout();
  updateModel();
}
function syncControls() {
  container.dataset.boardMode = mode;
  pinButton.hidden = mode !== '2d' || settings.board !== 'raspi4b';
  pinPanel.hidden = pinButton.hidden || pinButton.getAttribute('aria-pressed') !== 'true';
  if (!pinPanel.hidden) renderPinout();
  for (const button of controls.querySelectorAll('[data-board-mode]')) {
    const active = button.dataset.boardMode === mode;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  }

}
const modeControls = document.createElement('div');
modeControls.className = 'board-mode-switch';
for (const value of ['3d', '2d']) {
  const button = document.createElement('button');
  button.type = 'button';
  button.textContent = value.toUpperCase();
  button.dataset.boardMode = value;
  button.title = value === '2d' ? 'Top view' : 'Perspective view';
  button.addEventListener('click', () => { mode = value; viewModes.set(storageKey(), mode); syncControls(); saveLayout(); updateModel(); }, {signal});
  modeControls.append(button);
}
controls.append(modeControls);
const pinButton = document.createElement('button');
pinButton.type = 'button';
pinButton.textContent = 'Pinout';
pinButton.setAttribute('aria-pressed', 'false');
pinButton.setAttribute('aria-controls', 'workbench-pinout');
const pinPanel = document.createElement('section');
pinPanel.id = 'workbench-pinout';
pinPanel.className = 'board-pinout';
pinPanel.setAttribute('aria-label', 'Physical pin numbers');
controls.append(pinButton);
container.append(pinPanel);
function renderPinout() {
  const devices = visibleDevices();
  const connections = new Map();
  for (const sensor of devices) {
    pinRoles.forEach((role, i) => {
      const pin = signalPin(sensor.id, i);
      if (!connections.has(pin)) connections.set(pin, []);
      connections.get(pin).push(sensor.id + ' · ' + role);
    });
  }
  const heading = document.createElement('strong');
  heading.textContent = 'Raspberry Pi 4B · 40-pin header';
  const grid = document.createElement('div');
  grid.className = 'pinout-header';
  for (let number = 1; number <= 40; number++) {
    const pin = document.createElement('span');
    pin.style.gridColumn = Math.ceil(number / 2);
    pin.style.gridRow = number % 2 ? 2 : 1;
    pin.textContent = number;
    const role = pinRoles.find(role => sensorHeaderPins[role].includes(number));
    if (role) {
      const label = document.createElement('small');
      label.textContent = role === 'VCC' ? '3V3' : role;
      pin.append(label);
    }
    pin.classList.toggle('wired', connections.has(number));
    pin.title = ['Pin ' + number, ...(connections.get(number) || [])].join(' · ');
    grid.append(pin);
  }
  pinPanel.replaceChildren(heading, grid);
  for (const sensor of devices) {
    const row = document.createElement('div');
    row.className = 'pinout-device';
    const label = document.createElement('strong');
    label.textContent = sensor.name || sensor.id;
    row.append(label);
    pinRoles.forEach((role, i) => {
      const line = document.createElement('span');
      line.style.borderColor = wireColors[i];
      line.textContent = role + ' · ' + signalPin(sensor.id, i);
      row.append(line);
    });
    pinPanel.append(row);
  }
}
pinButton.addEventListener('click', () => {
  pinButton.setAttribute('aria-pressed', String(pinPanel.hidden));
  syncControls();
}, {signal});
const icons = {
  minus: '<path d="M5 12h14"/>',
  plus: '<path d="M5 12h14M12 5v14"/>',
  reset: '<path d="M3 10a9 9 0 1 1 2 8M3 4v6h6"/>'
};
for (const [action, title] of [['minus','Zoom out'], ['plus','Zoom in'], ['reset','Reset layout and view']]) {
  const button = document.createElement('button');
  button.type = 'button';
  button.title = title;
  button.setAttribute('aria-label', title);
  button.dataset.boardControl = action;
  button.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">' + icons[action] + '</svg>';
  button.addEventListener('click', () => {
    if (action === 'reset') { resetCamera(); return; }
    cameraZoom = Math.max(.5, Math.min(2.4, cameraZoom + (action === 'plus' ? .12 : -.12)));
    saveLayout();
    updateModel();
  }, {signal});
  controls.append(button);
}
syncControls();

function beginDrag(event, group) {
  if (event.button !== 0 || pointerStart) return;
  event.preventDefault();
  const rect = boardCanvas.getBoundingClientRect();
  group ??= hitGroup(event.clientX - rect.left, event.clientY - rect.top);
  pointerStart = {x:event.clientX, y:event.clientY, group, pointer:event.pointerId, travel:0};
  boardCanvas.setPointerCapture(event.pointerId);
  boardCanvas.style.cursor = 'grabbing';
}
boardCanvas.addEventListener('pointerdown', event => beginDrag(event), {signal});
window.addEventListener('pointermove', event => {
  if (!pointerStart) {
    if(event.target!==boardCanvas)return;
    const rect = boardCanvas.getBoundingClientRect();
    boardCanvas.style.cursor = hitGroup(event.clientX - rect.left, event.clientY - rect.top) ? 'move' : 'grab';
    return;
  }
  if (event.pointerId !== pointerStart.pointer) return;
  const dx = event.clientX - pointerStart.x, dy = event.clientY - pointerStart.y;
  if (!pointerStart.travel && Math.hypot(dx, dy) < 5) return;
  pointerStart.travel += Math.hypot(dx, dy);
  if (pointerStart.group) {
    const delta = planeDelta(dx, dy), previous = positions[pointerStart.group] || [0, 0];
    positions[pointerStart.group] = previous.map((value, index) => value + delta[index]);
  } else if (mode === '2d') {
    pan[0] += dx; pan[1] += dy;
  } else {
    cameraAngle += dx * .008;
    cameraTilt = Math.min(1.35, Math.max(.3, cameraTilt + dy * .005));
  }
  pointerStart.x = event.clientX;
  pointerStart.y = event.clientY;
  updateModel();
}, {signal});
function endDrag(event) {
  if (!pointerStart || event.pointerId !== pointerStart.pointer) return;
  const {group, pointer, travel} = pointerStart;
  pointerStart = null;
  if (boardCanvas.hasPointerCapture(pointer)) boardCanvas.releasePointerCapture(pointer);
  boardCanvas.style.cursor = 'grab';
  if (travel) saveLayout();
  if (event.type !== 'pointerup' || travel) return;
  if (group && group !== 'board') selectSensor(group);
  else settings.onInspect?.(group);
}
window.addEventListener('pointerup', endDrag, {signal});
window.addEventListener('pointercancel', endDrag, {signal});
boardCanvas.addEventListener('wheel', event => {
  event.preventDefault();
  cameraZoom = Math.min(2.4, Math.max(.5, cameraZoom - event.deltaY * .001));
  saveLayout();
  updateModel();
}, {passive:false, signal});
const resize = new ResizeObserver(updateModel);
resize.observe(container);

if (settings.board === 'native') addComputer();
else if (settings.board === 'raspi4b') addBoard();
syncModelDevices();
return {
  update(next) {
    const previousBoard = settings.board;
    const changedDevices = JSON.stringify(settings.devices) !== JSON.stringify(next.devices);
    settings = {...settings, ...next};
    if (previousBoard !== settings.board) {
      modelParts.length = modelLines.length = modelTexts.length = 0;
      cameraAngle = .36; cameraTilt = .64; cameraZoom = 1; positions = {}; pan = [0,0];
      restoreLayout(); syncControls();
      if (settings.board === 'native') addComputer();
      else if (settings.board === 'raspi4b') addBoard();
    }
    if (Object.hasOwn(next, 'selected')) selectedModel = next.selected;
    if (!pinPanel.hidden) renderPinout();
    if(changedDevices || previousBoard!==settings.board) syncModelDevices();
    else updateModel();
  },
  select(id) { selectedModel = visibleDevices().some(device => device.id === id) ? id : null; updateModel(); },
  reset: resetCamera,
  destroy() {
    disposed = true;
    if (frame) cancelAnimationFrame(frame);
    abort.abort();
    resize.disconnect();
    container.replaceChildren();
  }
};
}
