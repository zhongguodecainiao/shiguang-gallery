'use strict';

const FILTER_SPEC = {
  origin: {label:'照片来源',options:[['screenshot','屏幕截图'],['wechat','微信照片'],['qq','QQ 照片'],['download','下载图片']]},
  camera: {label:'拍摄相机',options:[]},
  extension: {label:'文件类型',options:[]},
  focal: {label:'焦距',options:[['wide','小于 24 mm'],['normal','24–69 mm'],['tele','70–199 mm'],['long','200 mm 及以上']]},
  aperture: {label:'光圈',options:[['fast','f/1–f/2.8'],['medium','f/2.9–f/5.6'],['narrow','f/5.7 及以上']]}
};
let filterTimer = null;
let filterWasIndexing = false;
let openFacet = null;
function facetSummary(key) {
  const state = S.filters[key], count = state.values.length;
  if (!count) return T('全部');
  if (count === 1) {
    const option = FILTER_SPEC[key].options.find(row => row[0] === state.values[0]);
    return T(state.mode === 'exclude' ? '排除：{0}' : '只看：{0}', option ? (key==='camera'||key==='extension' ? option[1] : T(option[1])) : state.values[0]);
  }
  return T(state.mode === 'exclude' ? '排除所选（{0}）' : '只看所选（{0}）', number(count));
}
function positionFacet(key) {
  const facet = $(`#filterFacets [data-facet="${key}"]`), popover = facet?.querySelector('.facet-popover');
  if (!popover || popover.classList.contains('hidden')) return;
  const rect = facet.querySelector('.facet-trigger').getBoundingClientRect();
  popover.style.left = Math.max(8,Math.min(rect.left,innerWidth-popover.offsetWidth-8))+'px';
  popover.style.top = Math.max(48,Math.min(rect.bottom+6,innerHeight-popover.offsetHeight-8))+'px';
}
function closeFacet() {
  openFacet = null;
  $$('#filterFacets .facet-popover').forEach(node => node.classList.add('hidden'));
  $$('#filterFacets .facet-trigger').forEach(node => node.setAttribute('aria-expanded','false'));
}
function applyFilters() {
  $('#filterToggle').classList.toggle('filter-active', Object.values(S.filters).some(state => state.values.length));
  guard(() => load(true))();
}
function drawFacet(key) {
  const spec = FILTER_SPEC[key], state = S.filters[key];
  let facet = $(`#filterFacets [data-facet="${key}"]`);
  if (!facet) {facet=el('div','filter-facet');facet.dataset.facet=key;$('#filterFacets').append(facet);}
  const oldScroll = facet.querySelector('.facet-options')?.scrollTop || 0;
  const trigger = el('button','facet-trigger');trigger.type='button';
  trigger.setAttribute('aria-haspopup','true');trigger.setAttribute('aria-expanded',String(openFacet===key));
  trigger.append(el('span','facet-label',T(spec.label)),el('span','facet-summary',facetSummary(key)),el('span','material-symbols-outlined','expand_more'));
  trigger.onclick = () => {openFacet === key ? closeFacet() : (openFacet=key,drawAllFacets());};
  const popover = el('div','facet-popover'+(openFacet===key?'':' hidden'));
  popover.append(el('div','facet-title',T(spec.label)),el('div','facet-help',T('勾选多个选项，然后选择只看或排除')));
  const modes=el('div','facet-modes');
  for(const [mode,label] of [['include','只看所选'],['exclude','排除所选']]) {
    const button=el('button','facet-mode'+(state.mode===mode?' active':''),T(label));
    button.type='button';button.setAttribute('aria-pressed',String(state.mode===mode));
    button.onclick=()=>{state.mode=mode;drawFacet(key);applyFilters();};modes.append(button);
  }
  popover.append(modes);
  const options=el('div','facet-options');
  const entries=[...spec.options];
  for(const value of state.values) if(!entries.some(row=>row[0]===value)) entries.push([value,value]);
  for(const [value,label,count] of entries) {
    const row=el('div','facet-option');
    const checkLabel=el('label','facet-check'), check=el('input');
    check.type='checkbox';check.value=value;check.checked=state.values.includes(value);
    check.onchange=()=>{
      state.values=check.checked ? [...state.values,value] : state.values.filter(item=>item!==value);
      drawFacet(key);applyFilters();
    };
    checkLabel.append(check,el('span','',key==='camera'||key==='extension' ? label : T(label)));
    if(count!==undefined)checkLabel.append(el('small','',number(count)));
    row.append(checkLabel);
    for(const [mode,caption] of [['include','仅此'],['exclude','排除']]) {
      const button=el('button','facet-quick',T(caption));button.type='button';
      I18n.attr(button,'aria-label',T(mode==='include'?'仅查看：{0}':'排除选项：{0}',label));
      button.onclick=()=>{state.mode=mode;state.values=[value];drawFacet(key);applyFilters();};
      row.append(button);
    }
    options.append(row);
  }
  if(!entries.length)options.append(el('div','facet-empty',T('暂无可选项目')));
  popover.append(options);
  const clear=el('button','facet-clear',T('清除此项筛选'));
  clear.type='button';clear.onclick=()=>{state.mode='include';state.values=[];drawFacet(key);applyFilters();};
  popover.append(clear);
  facet.replaceChildren(trigger,popover);
  options.scrollTop=oldScroll;
  positionFacet(key);
}
function drawAllFacets() {for(const key of Object.keys(FILTER_SPEC))drawFacet(key);}
drawAllFacets();
async function refreshFilterOptions() {
  const result = await api('/api/filters');
  FILTER_SPEC.camera.options=result.cameras.map(row=>[row.camera,row.camera,row.count]);
  FILTER_SPEC.extension.options=result.extensions.map(row=>[row.extension,row.extension.toUpperCase(),row.count]);
  drawFacet('camera');drawFacet('extension');
  I18n.text($('#filterIndexStatus'), result.index.running ? T('正在读取拍摄参数：{0} / {1}', number(result.index.processed), number(result.index.total)) :
    result.index.error ? T('部分拍摄参数读取失败') : T('相机、焦距和光圈按原文件信息筛选'));
  if (filterWasIndexing && !result.index.running && ['camera','focal','aperture'].some(key => S.filters[key].values.length)) guard(() => load(true))();
  filterWasIndexing = result.index.running;
  if (result.index.running && !$('#filterPanel').classList.contains('hidden')) {
    clearTimeout(filterTimer);
    filterTimer = setTimeout(() => guard(refreshFilterOptions)(), 3000);
  }
}
$('#filterToggle').onclick = () => {
  const open = $('#filterToggle').getAttribute('aria-expanded') !== 'true';
  $('#filterToggle').setAttribute('aria-expanded', String(open));
  $('#filterPanel').classList.toggle('hidden', !open);
  if (open) guard(refreshFilterOptions)();else {clearTimeout(filterTimer);closeFacet();}
};
$('#clearFilters').onclick = () => {
  for (const state of Object.values(S.filters)) {state.mode='include';state.values=[];}
  drawAllFacets();applyFilters();
};
document.addEventListener('pointerdown',event=>{if(openFacet&&!event.target.closest('.filter-facet'))closeFacet();});
window.addEventListener('scroll',event=>{if(event.target===document||event.target===document.documentElement)closeFacet();},true);
window.addEventListener('resize',closeFacet);

const photoMenu = $('#photoContextMenu');
let photoMenuId = null;
function closePhotoMenu() {photoMenu.classList.add('hidden');photoMenuId = null;}
function menuAction(label, icon, action, dangerous=false) {
  const button = el('button', dangerous ? 'danger' : '');
  button.type = 'button';button.setAttribute('role','menuitem');
  const symbol = el('span','material-symbols-outlined',icon);
  symbol.setAttribute('aria-hidden','true');
  button.append(symbol,el('span','',T(label)));
  button.onclick = () => {closePhotoMenu();guard(action)();};
  photoMenu.append(button);
}
document.addEventListener('contextmenu', event => {
  const card = event.target.closest('.photo-card');
  if (!card || ['albums','folders'].includes(S.view)) {closePhotoMenu();return;}
  event.preventDefault();
  const photo = S.items.find(item => item.id === Number(card.dataset.id));
  if (!photo)return;
  photoMenuId = photo.id;
  S.inspectedId = photo.id;
  paintGalleryInspector(photo);
  $$('.photo-card.inspected').forEach(node => node.classList.remove('inspected'));
  card.classList.add('inspected');
  photoMenu.replaceChildren();
  menuAction('查看大图','open_in_full',() => showViewer(S.items.findIndex(item => item.id === photo.id)));
  menuAction('加入相册','add_to_photos',() => chooseAlbum([photo.id]));
  menuAction(photo.favorite ? '取消收藏' : '收藏照片', photo.favorite ? 'heart_minus' : 'favorite', async () => {
    await api('/api/favorite',{ids:[photo.id],value:!photo.favorite});
    photo.favorite = photo.favorite ? 0 : 1;
    await overview();await load(true);
  });
  menuAction('复制照片','content_copy',() => chooseCopy([photo.id]));
  menuAction('分享 ZIP','ios_share',() => openFileAction('share',[photo.id]));
  menuAction('在文件夹中显示','folder_open',() => api('/api/reveal',{id:photo.id}));
  menuAction('删除原照片','delete',() => openFileAction('recycle',[photo.id]),true);
  photoMenu.classList.remove('hidden');
  photoMenu.style.left = Math.max(8,Math.min(event.clientX,innerWidth-photoMenu.offsetWidth-8))+'px';
  photoMenu.style.top = Math.max(8,Math.min(event.clientY,innerHeight-photoMenu.offsetHeight-8))+'px';
  photoMenu.querySelector('button')?.focus();
});
document.addEventListener('pointerdown',event => {if (!event.target.closest('#photoContextMenu'))closePhotoMenu();});
document.addEventListener('keydown',event => {
  if (event.key !== 'Escape') return;
  if (openFacet) {closeFacet();event.preventDefault();return;}
  if (!photoMenu.classList.contains('hidden')) {closePhotoMenu();event.preventDefault();return;}
  if (!S.selecting || $$('dialog[open]').length) return;
  event.preventDefault();
  finishRange(true);
  resetSelectionHistory();
  S.selecting=false;S.selected.clear();
  paintSelectedCards();
});
window.addEventListener('scroll',closePhotoMenu,true);
window.addEventListener('resize',closePhotoMenu);
