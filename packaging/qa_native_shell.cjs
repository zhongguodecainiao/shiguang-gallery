const {chromium}=require('C:/Users/LENOVO/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert=require('assert');
(async()=>{
 const browser=await chromium.connectOverCDP(process.argv[2]);
 try{
  const contexts=browser.contexts();
  assert.equal(contexts.length,1);
  const pages=contexts[0].pages();
  assert.equal(pages.length,1);
  const page=pages[0],errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.locator('.photo-card').first().waitFor({timeout:30000});
  if(await page.locator('#releaseDialog').isVisible())await page.locator('#releaseDone').click();
  assert.equal(await page.evaluate(()=>typeof window.chrome?.webview),'object');
  assert.equal(await page.locator('.photo-card').count(),2);
  await page.locator('.photo-card').first().click();
  assert.equal(await page.locator('#viewer').isVisible(),false);
  await page.locator('.photo-card').first().dblclick();
  await page.locator('#viewer').waitFor({state:'visible'});
  await page.waitForFunction(()=>document.querySelector('#fullImage').naturalWidth>0);
  if(await page.evaluate(()=>S.viewSizeMode!=='original'))await page.locator('#viewerSizeMode').click();
  await page.waitForFunction(()=>S.viewSizeMode==='original'&&Q.mode==='full');
  await page.locator('#viewerZoom').click();
  await page.waitForFunction(()=>document.querySelector('#viewer').classList.contains('fullscreen-preview')&&innerWidth>=screen.width-2&&innerHeight>=screen.height-2);
  const fullscreen=await page.evaluate(()=>({full:document.fullscreenElement?.id,viewer:document.querySelector('#viewer').classList.contains('fullscreen-preview'),inner:[innerWidth,innerHeight],screen:[screen.width,screen.height]}));
  assert.equal(fullscreen.full,undefined);assert.equal(fullscreen.viewer,true);
  assert(fullscreen.inner[0]>=fullscreen.screen[0]-2&&fullscreen.inner[1]>=fullscreen.screen[1]-2,JSON.stringify(fullscreen));
  await page.keyboard.press('Escape');
  await page.waitForFunction(()=>!document.querySelector('#viewer').classList.contains('fullscreen-preview')&&innerWidth<screen.width-2);
  await page.locator('#viewerClose').click();
  await page.waitForFunction(()=>!document.querySelector('#viewer').open);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({passed:true,checks:['WebView2 loaded the real gallery without an external browser','Inspector, large-photo viewer and original-size mode work in the embedded window','Native fullscreen fills the display and exits with Escape'],errors},null,2));
  process.exit(0);
 }finally{/* Let the native host own and close its WebView2 process. */}
})().catch(error=>{console.error(error);process.exit(1)});
