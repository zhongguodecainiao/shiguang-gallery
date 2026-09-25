'use strict';

(() => {
  const viewer = $('#viewer'), dock = $('#viewerDock'), info = $('#photoInfo'), toggle = $('#infoToggle');
  new ResizeObserver(() => viewer.style.setProperty('--viewer-dock-height', dock.offsetHeight + 'px')).observe(dock);
  new ResizeObserver(() => viewer.style.setProperty('--fullscreen-top-height', Math.ceil($('.viewer-top').getBoundingClientRect().height) + 'px')).observe($('.viewer-top'));
  const statusNodes = ['seekDate', 'seekHint', 'seekPosition', 'filmWindow', 'seekPreviewName', 'seekPreviewMeta', 'viewResolution']
    .map(id => document.getElementById(id)).concat($('.zoom-hint'));
  const statusAnchors = statusNodes.map(node => {
    const anchor = document.createComment('fullscreen status origin');
    node.before(anchor);
    return anchor;
  });
  function moveStatus(toTop) {
    statusNodes.forEach((node, index) => {
      if (toTop) $('#fullscreenMeta').append(node);
      else statusAnchors[index].after(node);
    });
  }
  let infoOpen = true, active = false, entering = false, controlsTimer, pointerDown = false, exitedAt = 0;
  let navigationStart = null, suppressPageClickUntil = 0;
  function paintInfo() {
    viewer.classList.toggle('info-collapsed', !infoOpen);
    info.inert = !infoOpen;
    toggle.setAttribute('aria-expanded', String(infoOpen));
    I18n.text(toggle, infoOpen ? '›' : '‹');
    I18n.attr(toggle, 'title', T(infoOpen ? '收起照片信息' : '展开照片信息'));
    I18n.attr(toggle, 'aria-label', T(infoOpen ? '收起照片信息' : '展开照片信息'));
  }
  toggle.onclick = () => {infoOpen = !infoOpen;paintInfo();};
  paintInfo();
  function scheduleHide(delay = 1100) {
    clearTimeout(controlsTimer);
    controlsTimer = setTimeout(hideControls,delay);
  }
  function hideControls() {
    controlsTimer = null;
    if (pointerDown || dock.matches(':hover') || $('.viewer-top').matches(':hover') ||
        $('.viewer-selection').matches(':hover') || viewer.querySelector(':focus-visible') ||
        $$('dialog[open]').some(d => d !== viewer)) {scheduleHide(500);return;}
    viewer.classList.remove('dock-visible','top-visible');
    hideSeekPreview();
  }
  function revealControls(stay = false) {
    clearTimeout(controlsTimer);controlsTimer = null;
    viewer.classList.add('dock-visible','top-visible');
    if (!stay) scheduleHide();
  }
  function nativeFullscreenApi() {
    return window.pywebview?.api?.enter_fullscreen ? window.pywebview.api : null;
  }
  function paintFullscreen(next) {
    if (active !== next) moveStatus(next);
    active = next;viewer.classList.toggle('fullscreen-preview', next);
    $('#viewerZoom').setAttribute('aria-pressed', String(next));
    I18n.attr($('#viewerZoom'), 'title', T(next ? '退出全屏预览' : '全屏预览'));
    I18n.attr($('#viewerZoom'), 'aria-label', T(next ? '退出全屏预览' : '全屏预览'));
    clearTimeout(controlsTimer);
    viewer.classList.remove('dock-visible','top-visible');
    if (next) hideSeekPreview();
    else exitedAt = performance.now();
  }
  async function exitFullscreen() {
    const native=nativeFullscreenApi();
    if (native) await native.exit_fullscreen();
    else if (document.fullscreenElement) await document.exitFullscreen();
    paintFullscreen(false);
  }
  $('#viewerZoom').onclick = guard(async () => {
    if (entering) return;
    if (active) return exitFullscreen();
    entering = true;
    try {
      const native=nativeFullscreenApi();
      if (native) await native.enter_fullscreen();
      // Browser-based development and QA continue to use the standards API.
      else await $('#viewerSurface').requestFullscreen();
      if (viewer.open) paintFullscreen(true);else await exitFullscreen();
    } catch {toast(T('无法进入全屏，请重试。'));}
    finally {entering = false;}
  });
  document.addEventListener('fullscreenchange', () => {
    if (!document.fullscreenElement && active) paintFullscreen(false);
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && active && !$$('dialog[open]').some(d => d !== viewer)) {
      // Handle the key before the dialog's close watcher, including repeated
      // fullscreen sessions where its cancel event may no longer be cancelable.
      e.preventDefault();e.stopPropagation();guard(exitFullscreen)();
    }
  }, true);
  viewer.addEventListener('cancel', e => {
    if (active) {e.preventDefault();guard(exitFullscreen)();}
    else if (performance.now() - exitedAt < 300) e.preventDefault();
  });
  viewer.addEventListener('close', () => {
    if (active) guard(exitFullscreen)();
    pointerDown = false;
    navigationStart = null;
  });
  viewer.addEventListener('pointermove', e => {
    if (!active || e.pointerType === 'touch') return;
    const stage=$('#imageStage');
    stage.classList.toggle('page-left',e.clientX<innerWidth/2);
    stage.classList.toggle('page-right',e.clientX>=innerWidth/2);
    if (navigationStart && e.pointerId===navigationStart.id && Math.hypot(e.clientX-navigationStart.x,e.clientY-navigationStart.y)>8) navigationStart.moved=true;
    const atControls = e.clientY < 80 || e.clientY >= innerHeight-54 ||
      !!e.target.closest('.viewer-top,.viewer-selection,.viewer-dock,#fullscreenReveal');
    if (atControls) revealControls(true);
    else if (viewer.classList.contains('dock-visible') && !controlsTimer) scheduleHide();
  });
  viewer.addEventListener('pointerleave', () => {if (active) scheduleHide();});
  viewer.addEventListener('pointerdown', e => {
    if (active && e.button===0 && e.target.closest('#imageStage')) navigationStart={id:e.pointerId,x:e.clientX,y:e.clientY,moved:false};
  });
  viewer.addEventListener('pointerup',e=>{
    if (navigationStart?.id===e.pointerId) {
      if (navigationStart.moved) suppressPageClickUntil=performance.now()+500;
      navigationStart=null;
    }
  });
  viewer.addEventListener('click',e=>{
    if (!active || e.button!==0 || e.detail>1 || performance.now()<suppressPageClickUntil ||
        $$('dialog[open]').some(d=>d!==viewer) || !e.target.closest('#imageStage')) return;
    (e.clientX<innerWidth/2 ? $('#previous') : $('#next')).click();
  });
  for(const control of [dock,$('.viewer-top'),$('.viewer-selection')]) {
    control.addEventListener('pointerdown',()=>{pointerDown=true;if(active)revealControls(true);});
    control.addEventListener('focusin',()=>{if(active)revealControls(true);});
    control.addEventListener('focusout',()=>{if(active)scheduleHide();});
  }
  document.addEventListener('pointerup',()=>{if(pointerDown){pointerDown=false;if(active)scheduleHide();}});
  document.addEventListener('pointercancel',()=>{if(pointerDown){pointerDown=false;if(active)scheduleHide();}});
  $('#fullscreenReveal').onclick = () => revealControls();
})();
