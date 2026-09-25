'use strict';

// The destination picker stays inside the app instead of waiting on an unowned native modal.
let folderRequest = 0,
  folderLocation = null,
  folderSelected = null;
async function loadFolder(path, initial = false) {
  const request = ++folderRequest;
  folderLocation = null;
  $('#useFolder').disabled = true;
  $('#folderUp').disabled = true;
  I18n.text($('#folderError'), '');
  $('#folderList').replaceChildren(el('p', '', T("正在读取文件夹\u2026")));
  try {
    const r = await api('/api/folders/list', {
      path,
      initial
    });
    if (request !== folderRequest || !$('#folderDialog').open) return;
    folderLocation = r;
    $('#folderPathInput').value = r.path;
    I18n.text($('#folderCurrent'), r.path || T("本机磁盘"));
    $('#folderUp').disabled = r.parent === null;
    $('#useFolder').disabled = !r.path;
    $('#folderRoots').replaceChildren();
    for (const drive of r.roots) {
      const b = el('button', 'secondary', drive);
      b.onclick = () => loadFolder(drive);
      $('#folderRoots').append(b);
    }
    $('#folderList').replaceChildren();
    for (const folder of r.folders) {
      const b = el('button', 'folder-row', '▱  ' + folder.name);
      I18n.attr(b, "title", folder.path);
      b.onclick = () => loadFolder(folder.path);
      $('#folderList').append(b);
    }
    if (!r.folders.length) $('#folderList').append(el('p', 'folder-empty', T("此处没有可浏览的子文件夹，可以直接使用当前文件夹。")));
    I18n.text($('#folderError'), T(r.notice));
  } catch (e) {
    if (request !== folderRequest) return;
    $('#folderList').replaceChildren();
    I18n.text($('#folderError'), I18n.errorText(e));
  }
}
function openFolderBrowser(options = {}) {
  folderSelected = options.onSelect || (path => {
    $('#destinationPath').value = path;
  });
  I18n.text($('#folderDialogTitle'), options.title || T("选择保存文件夹"));
  $('#folderDialog').showModal();
  loadFolder(options.value ?? $('#destinationPath').value, true);
}
$('#folderUp').onclick = () => {
  if (folderLocation) loadFolder(folderLocation.parent || '');
};
$('#folderPathForm').onsubmit = e => {
  e.preventDefault();
  loadFolder($('#folderPathInput').value);
};
$('#folderPathInput').oninput = () => {
  $('#useFolder').disabled = true;
};
$('#useFolder').onclick = () => {
  if (folderLocation?.path) {
    folderSelected?.(folderLocation.path);
    $('#folderDialog').close();
  }
};
$('#folderDialog').addEventListener('close', () => {
  folderRequest++;
  folderLocation = null;
  folderSelected = null;
});

// Decode on demand, retaining the quick image until the full image is ready.
const Q = {
  generation: 0,
  mode: 'quick',
  loader: null,
  pending100: false,
  loading: false,
  error: false,
  depth: null
};
function cancelQualityLoad() {
  Q.generation++;
  if (Q.loader) {
    Q.loader.onload = Q.loader.onerror = null;
    Q.loader.src = '';
    Q.loader = null;
  }
  Q.loading = false;
}
function paintQuality() {
  const output = $('#decodeOutput');
  if (output) {
    const native = ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.avif', '.bmp'].includes(S.viewerPhoto.extension.toLowerCase());
    I18n.text(output, Q.mode === 'full' ? S.viewerPhoto.kind === 'RAW' ? T("16 bit / 通道 \xB7 RGB PNG（48 bit）") : native ? I18n.concat(T("原文件 \xB7 "), T(Q.depth?.text || '位深待读取')) : T("8 bit / 通道 \xB7 原尺寸转换图像") : T("8 bit / 通道 \xB7 快速预览"));
  }
  $('#qualityFast').classList.toggle('active', Q.mode === 'quick' && !Q.loading);
  $('#qualityFull').classList.toggle('active', Q.mode === 'full' || Q.loading);
  $('#qualityFast').setAttribute('aria-pressed', String(Q.mode === 'quick' && !Q.loading));
  $('#qualityFull').setAttribute('aria-pressed', String(Q.mode === 'full' || Q.loading));
  $('#qualityFull').setAttribute('aria-busy', String(Q.loading));
  $('#viewResolution').classList.toggle('quality-error', Q.error);
  if (Q.error) {
    I18n.text($('#viewResolution'), T("原图细节读取失败，可点击重试"));
    return;
  }
  if (Q.loading) {
    I18n.text($('#viewResolution'), S.viewerPhoto.kind === 'RAW' ? T("正在完整解码 RAW，首次需要几秒\u2026") : T("正在读取原图\u2026"));
    return;
  }
  const img = $('#fullImage');
  I18n.text($('#viewResolution'), Z.ready ? I18n.concat(Q.mode === 'full' ? T("完整分辨率") : T("快速预览"), " \xB7 ", img.naturalWidth, " \xD7 ", img.naturalHeight) : T("正在读取预览\u2026"));
}
function beginPhotoQuality() {
  cancelQualityLoad();
  Q.mode = 'quick';
  Q.pending100 = false;
  Q.error = false;
  Q.depth = null;
  Z.ready = false;
  paintQuality();
}
function actualScale() {
  return fullImage.naturalWidth / (Math.max(.1, devicePixelRatio) * Z.width);
}
function showActualPixels() {
  const r = stage.getBoundingClientRect();
  zoomAt(actualScale(), r.left + r.width / 2, r.top + r.height / 2);
}
function qualityImageLoaded() {
  fullImage.classList.remove('hidden');
  $('#previewError').classList.add('hidden');
  if (Q.mode === 'full' && Q.pending100) {
    Q.pending100 = false;
    showActualPixels();
  }
  if (Q.mode === 'quick' && S.viewSizeMode === 'original' && !Q.loading) requestFullQuality(true);
  paintQuality();
}
function requestFullQuality(actual = false) {
  if (!$('#viewer').open || !S.viewerPhoto) return;
  Q.pending100 = Q.pending100 || actual;
  if (Q.mode === 'full' && !Q.loading) {
    if (Q.pending100) {
      Q.pending100 = false;
      showActualPixels();
    }
    return;
  }
  if (Q.loading) return;
  cancelQualityLoad();
  Q.error = false;
  Q.loading = true;
  paintQuality();
  const generation = Q.generation,
    request = viewerRequest,
    p = S.viewerPhoto,
    loader = new Image();
  Q.loader = loader;
  const current = () => generation === Q.generation && request === viewerRequest && $('#viewer').open && S.viewerPhoto.id === p.id;
  loader.onload = () => {
    if (!current()) return;
    Q.loader = null;
    Q.loading = false;
    Q.mode = 'full';
    fullImage.src = loader.src;
  };
  loader.onerror = () => {
    if (!current()) return;
    Q.loader = null;
    Q.loading = false;
    Q.pending100 = false;
    Q.error = true;
    paintQuality();
  };
  loader.src = thumb(p.id) + '?size=full&decoder=raw16-v2&v=' + p.mtime;
}
$('#qualityFull').onclick = () => requestFullQuality();
function paintViewerSizeMode() {
  const button=$('#viewerSizeMode');
  I18n.text(button,S.viewSizeMode==='original' ? T('100% 原图') : T('适应屏幕'));
  button.setAttribute('aria-pressed',String(S.viewSizeMode==='original'));
}
function setViewerSizeMode(mode) {
  S.viewSizeMode=mode;
  paintViewerSizeMode();
  if (!$('#viewer').open || !Z.ready) return;
  if (mode==='original') requestFullQuality(true);
  else {Q.pending100=false;resetViewerZoom(true);}
}
paintViewerSizeMode();
$('#viewerSizeMode').onclick=()=>setViewerSizeMode(S.viewSizeMode==='fit'?'original':'fit');
$('#zoomActual').onclick = () => {setViewerSizeMode('original');requestFullQuality(true);};
$('#qualityFast').onclick = () => {
  S.viewSizeMode='fit';paintViewerSizeMode();
  cancelQualityLoad();
  Q.mode = 'quick';
  Q.pending100 = false;
  Q.error = false;
  fullImage.src = thumb(S.viewerPhoto.id) + '?size=large&v=' + S.viewerPhoto.mtime;
  paintQuality();
};
$('#viewer').addEventListener('close', () => {
  cancelQualityLoad();
  Q.pending100 = false;
});

// Coordinates are stage-local; each wheel tick keeps the image point under the cursor fixed.
const Z = {
  scale: 1,
  x: 0,
  y: 0,
  width: 0,
  height: 0,
  ready: false,
  pan: null
};
const stage = $('#imageStage'),
  fullImage = $('#fullImage');
const zoomHint = el('div', 'zoom-hint', T("滚轮缩放 \xB7 放大后可拖动"));
stage.append(zoomHint);
fullImage.draggable = false;
function paintZoom() {
  const w = Z.width * Z.scale,
    h = Z.height * Z.scale;
  Z.x = Z.scale === 1 ? (stage.clientWidth - w) / 2 : Math.min(Math.max(0, stage.clientWidth - w), Math.max(Math.min(0, stage.clientWidth - w), Z.x));
  Z.y = Z.scale === 1 ? (stage.clientHeight - h) / 2 : Math.min(Math.max(0, stage.clientHeight - h), Math.max(Math.min(0, stage.clientHeight - h), Z.y));
  // Lay out the actual display dimensions. Scaling a small GPU layer can blur RAW detail.
  fullImage.style.width = w + 'px';
  fullImage.style.height = h + 'px';
  const dpr = Math.max(.1, devicePixelRatio),
    rect = stage.getBoundingClientRect();
  const x = Math.round((Z.x + rect.left) * dpr) / dpr - rect.left,
    y = Math.round((Z.y + rect.top) * dpr) / dpr - rect.top;
  fullImage.style.transform = `translate(${x}px,${y}px)`;
  stage.classList.toggle('can-pan', Z.scale > 1);
  stage.classList.toggle('panning', !!Z.pan);
  const amount = Q.mode === 'full' ? `${Math.round(Z.scale / actualScale() * 100)}%` : `${Z.scale.toFixed(1)}×`;
  I18n.text(zoomHint, Z.scale === 1 ? T("滚轮缩放 \xB7 放大后可拖动") : T("{0} \xB7 拖动查看 \xB7 双击复位", amount));
}
function resetViewerZoom(ready) {
  Z.pan = null;
  Z.ready = ready;
  Z.scale = 1;
  stage.classList.remove('zoomed', 'panning', 'can-pan');
  fullImage.style.visibility = ready ? 'visible' : 'hidden';
  zoomHint.classList.toggle('hidden', !ready);
  if (!ready || !fullImage.naturalWidth) return;
  const fit = Math.min(Math.max(1, stage.clientWidth - 44) / fullImage.naturalWidth, Math.max(1, stage.clientHeight - 44) / fullImage.naturalHeight, 1 / Math.max(.1, devicePixelRatio));
  Z.width = fullImage.naturalWidth * fit;
  Z.height = fullImage.naturalHeight * fit;
  paintZoom();
  if (S.viewSizeMode==='original' && Q.mode==='full' && !Q.loading) showActualPixels();
}
function zoomAt(next, clientX, clientY) {
  if (!Z.ready) return;
  next = Math.max(1, Math.min(Math.max(12, actualScale() * 2), next));
  const rect = stage.getBoundingClientRect(),
    x = clientX - rect.left,
    y = clientY - rect.top;
  const ratio = next / Z.scale;
  Z.x = x - (x - Z.x) * ratio;
  Z.y = y - (y - Z.y) * ratio;
  Z.scale = next;
  paintZoom();
}
stage.addEventListener('wheel', e => {
  if (!Z.ready || $$('dialog[open]').some(d => d !== $('#viewer'))) return;
  e.preventDefault();
  const delta = e.deltaY * (e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? stage.clientHeight : 1);
  zoomAt(Z.scale * Math.exp(-Math.max(-300, Math.min(300, delta)) * .0025), e.clientX, e.clientY);
}, {
  passive: false
});
stage.ondblclick = e => {
  if ($('#viewer').classList.contains('fullscreen-preview')) return;
  e.preventDefault();
  zoomAt(Z.scale > 1 ? 1 : 2, e.clientX, e.clientY);
};
document.addEventListener('keydown',e=>{
  if (e.key.toLowerCase()!=='f' || e.altKey || e.ctrlKey || e.metaKey || !$('#viewer').open ||
      $$('dialog[open]').some(d=>d!==$('#viewer')) || e.target.closest('input,textarea,select,[contenteditable]')) return;
  e.preventDefault();setViewerSizeMode(S.viewSizeMode==='fit'?'original':'fit');
});
stage.onpointerdown = e => {
  if (e.button !== 0 || !Z.ready || Z.scale <= 1) return;
  e.preventDefault();
  Z.pan = {
    id: e.pointerId,
    x: e.clientX,
    y: e.clientY,
    originX: Z.x,
    originY: Z.y
  };
  stage.setPointerCapture(e.pointerId);
  paintZoom();
};
stage.onpointermove = e => {
  if (Z.pan?.id === e.pointerId) {
    Z.x = Z.pan.originX + e.clientX - Z.pan.x;
    Z.y = Z.pan.originY + e.clientY - Z.pan.y;
    paintZoom();
  }
};
function endPan() {
  Z.pan = null;
  stage.classList.remove('panning');
}
stage.onpointerup = stage.onpointercancel = stage.onlostpointercapture = endPan;
new ResizeObserver(() => {
  if (Z.ready && $('#viewer').open) resetViewerZoom(true);
}).observe(stage);
$('#viewer').addEventListener('close', () => resetViewerZoom(false));

// Long-press range selection is strictly gated by the explicit selection mode.
let rangeGesture = null,
  rangeClickUntil = 0;
const content = $('#content');
const selectionHint = T("长按照片拖选 · 双击空白清空选择 · Ctrl+Z 撤销选择 · Esc 退出多选");
const rangeHint = el('span', 'range-hint', selectionHint);
$('#selectionBar').append(rangeHint);
const selectionUndo = {
  version: S.version,
  steps: []
};
function resetSelectionHistory() {
  selectionUndo.version = S.version;
  selectionUndo.steps = [];
}
function recordSelection(before) {
  if (selectionUndo.version !== S.version) resetSelectionHistory();
  if (before.size === S.selected.size && [...before].every(id => S.selected.has(id))) return;
  selectionUndo.steps.push(new Set(before));
  if (selectionUndo.steps.length > 50) selectionUndo.steps.shift();
}
function clearPhotoSelection() {
  const before = new Set(S.selected);
  S.selected.clear();
  recordSelection(before);
  paintSelectedCards();
}
function selectLoadedPhotos() {
  const before = new Set(S.selected);
  S.items.forEach(p => S.selected.add(p.id));
  recordSelection(before);
  paintSelectedCards();
}
function undoPhotoSelection() {
  if (rangeGesture?.active) {
    finishRange(true);
    toast(T("已撤销本次拖选"));
    return;
  }
  finishRange(true);
  if (selectionUndo.version !== S.version) resetSelectionHistory();
  const previous = selectionUndo.steps.pop();
  if (!previous) {
    toast(T("没有可撤销的选择"));
    return;
  }
  S.selected = previous;
  paintSelectedCards();
  toast(T("已撤销上一步选择"));
}
function paintSelectedCards() {
  selectionUI();
  for (const card of $$('.photo-card')) {
    const chosen = S.selected.has(Number(card.dataset.id));
    card.classList.toggle('selected', chosen);
    const b = card.querySelector('.select-check');
    I18n.text(b, chosen ? '✓' : '');
    b.setAttribute('aria-pressed', String(chosen));
  }
}
function rangeAtPointer() {
  const g = rangeGesture;
  if (!g?.active) return;
  const card = document.elementFromPoint(g.x, g.y)?.closest('.photo-card');
  if (!card) return;
  const index = S.items.findIndex(p => p.id === Number(card.dataset.id));
  if (index < 0 || index === g.end) return;
  g.end = index;
  S.selected = new Set(g.base);
  for (let i = Math.min(g.start, index); i <= Math.max(g.start, index); i++) {
    const photo = S.items[i];
    if (!collapsedDates.has(photo.taken.slice(0, 10))) S.selected.add(photo.id);
  }
  paintSelectedCards();
  I18n.text(rangeHint, T("正在连续选择 \xB7 已选 {0} 张 \xB7 松开完成", number(S.selected.size)));
}
function rangeFrame(time) {
  const g = rangeGesture;
  if (!g?.active) return;
  if (!S.selecting || g.version !== S.version) {
    finishRange(true);
    return;
  }
  const dt = Math.min(32, time - (g.frameTime || time));
  g.frameTime = time;
  const top = Math.max(65, $('#photoTools').getBoundingClientRect().bottom + 14),
    bottom = Math.max(top + 80, innerHeight - 65);
  const velocity = g.y < top ? -Math.min(900, (top - g.y) * 12) : g.y > bottom ? Math.min(900, (g.y - bottom) * 12) : 0;
  if (velocity) {
    window.scrollBy(0, velocity * dt / 1000);
    rangeAtPointer();
    if (velocity > 0 && innerHeight + scrollY >= document.documentElement.scrollHeight - 400 && S.items.length < S.total && !S.loading) guard(() => load())();
  }
  g.frame = requestAnimationFrame(rangeFrame);
}
function finishRange(cancel = false) {
  const g = rangeGesture;
  if (!g) return;
  clearTimeout(g.timer);
  cancelAnimationFrame(g.frame);
  rangeGesture = null;
  if (g.active) {
    rangeClickUntil = Date.now() + 650;
    if (g.version === S.version) {
      if (cancel) {
        S.selected = g.base;
        paintSelectedCards();
      } else recordSelection(g.base);
    }
  }
  if (content.hasPointerCapture(g.id)) content.releasePointerCapture(g.id);
  document.body.classList.remove('range-selecting');
  I18n.text(rangeHint, selectionHint);
}
content.addEventListener('pointerdown', e => {
  if (!S.selecting || e.button !== 0 || rangeGesture || $$('dialog[open]').length) return;
  const card = e.target.closest('.photo-card');
  if (!card) return;
  const start = S.items.findIndex(p => p.id === Number(card.dataset.id));
  if (start < 0) return;
  const g = rangeGesture = {
    id: e.pointerId,
    start,
    end: -1,
    base: new Set(S.selected),
    version: S.version,
    x: e.clientX,
    y: e.clientY,
    downX: e.clientX,
    downY: e.clientY,
    active: false
  };
  g.timer = setTimeout(() => {
    if (rangeGesture !== g || !S.selecting || g.version !== S.version) return;
    g.active = true;
    content.setPointerCapture(g.id);
    document.body.classList.add('range-selecting');
    rangeAtPointer();
    g.frame = requestAnimationFrame(rangeFrame);
  }, 380);
});
document.addEventListener('pointermove', e => {
  const g = rangeGesture;
  if (!g || e.pointerId !== g.id) return;
  g.x = e.clientX;
  g.y = e.clientY;
  if (!g.active) {
    if (Math.hypot(g.x - g.downX, g.y - g.downY) > 9) finishRange();
    return;
  }
  e.preventDefault();
  rangeAtPointer();
}, {
  passive: false
});
document.addEventListener('pointerup', e => {
  if (rangeGesture?.id === e.pointerId) finishRange();
});
document.addEventListener('pointercancel', e => {
  if (rangeGesture?.id === e.pointerId) finishRange(true);
});
content.addEventListener('lostpointercapture', () => {
  if (rangeGesture) finishRange(true);
});
content.addEventListener('click', e => {
  if (Date.now() < rangeClickUntil) {
    e.preventDefault();
    e.stopImmediatePropagation();
  }
}, true);
content.addEventListener('dragstart', e => {
  if (S.selecting) e.preventDefault();
});
content.addEventListener('contextmenu', e => {
  if (rangeGesture?.active) e.preventDefault();
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && rangeGesture) {
    e.preventDefault();
    finishRange(true);
  }
});
document.addEventListener('dblclick', e => {
  if (!S.selecting || $$('dialog[open]').length) return;
  const blank = e.target.matches('main,#content,.photo-grid,.date-group,.date-heading') || e.target === document.body && e.clientX >= $('main').getBoundingClientRect().left || !!e.target.closest('.date-heading') && !e.target.closest('button');
  if (!blank) return;
  e.preventDefault();
  window.getSelection()?.removeAllRanges();
  finishRange(true);
  clearPhotoSelection();
});
document.addEventListener('keydown', e => {
  if (!S.selecting || $$('dialog[open]').length || e.target.isContentEditable || e.target.closest('input,textarea,select')) return;
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z' && !e.altKey && !e.shiftKey) {
    e.preventDefault();
    undoPhotoSelection();
  }
});
window.addEventListener('blur', () => {
  endPan();
  finishRange(true);
});

// Reserve only the footer space needed by the floating controls; toggling mode
// updates existing cards rather than replacing thousands of DOM nodes.
new ResizeObserver(() => {
  const dock = $('#photoTools');
  if (!dock.classList.contains('hidden')) document.documentElement.style.setProperty('--photo-tools-space', Math.ceil(dock.getBoundingClientRect().height + 40) + 'px');
}).observe($('#photoTools'));
