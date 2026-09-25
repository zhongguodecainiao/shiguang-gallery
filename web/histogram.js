'use strict';
(function(root){
  function bins(pixels){
    const r=new Array(256).fill(0),g=new Array(256).fill(0),b=new Array(256).fill(0),l=new Array(256).fill(0);
    for(let i=0;i<pixels.length;i+=4){
      if(pixels[i+3]===0)continue;
      r[pixels[i]]++;g[pixels[i+1]]++;b[pixels[i+2]]++;
      l[Math.round(.2126*pixels[i]+.7152*pixels[i+1]+.0722*pixels[i+2])]++;
    }
    return {r,g,b,l};
  }
  function sample(image){
    const factor=Math.min(1,640/Math.max(image.naturalWidth,image.naturalHeight));
    const surface=document.createElement('canvas');surface.width=Math.max(1,Math.round(image.naturalWidth*factor));surface.height=Math.max(1,Math.round(image.naturalHeight*factor));
    const ctx=surface.getContext('2d',{willReadFrequently:true});ctx.drawImage(image,0,0,surface.width,surface.height);
    return bins(ctx.getImageData(0,0,surface.width,surface.height).data);
  }
  function draw(canvas,data,logarithmic=false){
    const ctx=canvas.getContext('2d'),w=canvas.width,h=canvas.height,pad=10;
    ctx.clearRect(0,0,w,h);ctx.fillStyle='#131315';ctx.fillRect(0,0,w,h);
    ctx.strokeStyle='#ffffff12';ctx.lineWidth=1;
    for(let i=1;i<4;i++){ctx.beginPath();ctx.moveTo(w*i/4,0);ctx.lineTo(w*i/4,h);ctx.stroke();ctx.beginPath();ctx.moveTo(0,h*i/4);ctx.lineTo(w,h*i/4);ctx.stroke()}
    if(!data)return;
    const scale=n=>logarithmic?Math.log1p(n):n;
    const peak=Math.max(1,...data.r,...data.g,...data.b,...data.l),max=scale(peak);
    function curve(values,color,fill){
      ctx.beginPath();ctx.moveTo(0,h-pad);
      for(let i=0;i<256;i++)ctx.lineTo(i*(w-1)/255,h-pad-scale(values[i])/max*(h-pad*2));
      if(fill){ctx.lineTo(w-1,h-pad);ctx.closePath();ctx.fillStyle=color;ctx.fill()}
      else{ctx.strokeStyle=color;ctx.lineWidth=1.5;ctx.stroke()}
    }
    ctx.globalCompositeOperation='screen';
    curve(data.r,'rgba(243,88,88,.56)',true);curve(data.g,'rgba(98,220,129,.52)',true);curve(data.b,'rgba(91,142,255,.65)',true);
    ctx.globalCompositeOperation='source-over';curve(data.l,'rgba(238,241,235,.8)',false);
  }
  const api={bins,sample,draw};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.PhotoHistogram=api;
})(typeof window!=='undefined'?window:this);
