(function(){
  var root=document.getElementById('ng-root'); if(!root||root.dataset.ready) return; root.dataset.ready='1';
  var V=JSON.parse(document.getElementById('ng-variants').textContent);
  var CN=JSON.parse(document.getElementById('ng-colornames').textContent);
  var T=JSON.parse(document.getElementById('ng-i18n').textContent);
  var state={size:V.length?V[0].size:1,color:0,pairs:{}};
  var nmin=99;V.forEach(function(v){if(v.size<nmin)nmin=v.size;});
  var singles=[];V.forEach(function(v){if(v.size==nmin&&singles.indexOf(v.color)<0)singles.push(v.color);});
  var mixIdx=-1;V.forEach(function(v){if(v.code==='MIX')mixIdx=v.color;});
  var codeOf={};V.forEach(function(v){if(v.size==nmin)codeOf[v.color]=v.code;});
  var propEl=document.getElementById('ng-prop'),propCodes=document.getElementById('ng-prop-codes');
  var tiers=[].slice.call(root.querySelectorAll('.ng-tier'));
  var vid=document.getElementById('ng-vid'),priceEl=document.getElementById('ng-price'),strikeEl=document.getElementById('ng-strike'),pillEl=document.getElementById('ng-savepill'),atc=document.getElementById('ng-atc'),atcT=document.getElementById('ng-atc-t'),sbtn=document.getElementById('ng-sticky-btn'),sprice=document.getElementById('ng-sticky-price');
  var pre=root.querySelector('.ng-tier .ng-badge');
  if(pre){state.size=+pre.closest('.ng-tier').dataset.size;}
  function vfor(size,color){for(var i=0;i<V.length;i++){if(V[i].size==size&&V[i].color==color)return V[i];}return null;}
  function find(){
    var pr=state.pairs[state.size];
    if(pr&&pr.length){
      var same=pr.every(function(c){return c===pr[0];});
      var v=same?vfor(state.size,pr[0]):vfor(state.size,mixIdx);
      if(v)return v;
    }
    for(var i=0;i<V.length;i++){if(V[i].size==state.size&&V[i].color==state.color)return V[i];}for(i=0;i<V.length;i++){if(V[i].size==state.size){state.color=V[i].color;return V[i];}}return V[0];}
  function render(){
    var v=find();
    vid.value=v.id; priceEl.textContent=v.priceFmt;
    var pr=state.pairs[state.size];
    if(pr&&pr.length&&v.color===mixIdx){propEl.disabled=false;propEl.value=pr.map(function(c){return CN[c];}).join(', ');propCodes.disabled=false;propCodes.value=pr.map(function(c){return codeOf[c]||c;}).join(',');}
    else{propEl.disabled=true;propEl.value='';propCodes.disabled=true;propCodes.value='';} sprice.textContent=v.priceFmt;
    if(state.size>1&&v.pct>0){strikeEl.hidden=false;strikeEl.textContent=v.fullFmt;pillEl.hidden=false;pillEl.textContent=T.save+' '+v.pct+'%';}else{strikeEl.hidden=true;pillEl.hidden=true;}
    tiers.forEach(function(t){
      var on=(+t.dataset.size===state.size);
      t.dataset.active=on; t.querySelector('input').checked=on;
      var sel=t.querySelector('.ng-select:not(.ng-psel)'); if(sel) sel.value=String(state.color);
      var cn=t.querySelector('[data-cname]'); if(cn) cn.textContent='('+(CN[state.color]||'')+')';
    });
    atc.disabled=!v.available; sbtn.disabled=!v.available;
    atcT.textContent=v.available?T.cta:T.soldout; sbtn.textContent=v.available?T.cta:T.soldout;
  }
  tiers.forEach(function(t){
    var box=t.querySelector('.ng-pairs'); if(!box) return;
    var size=+t.dataset.size,np=+box.dataset.pairs,arr=[];
    for(var k=0;k<np;k++){
      var c=singles[k%singles.length];arr.push(c);
      var row=document.createElement('div');row.className='ng-prow';
      var lb=document.createElement('span');lb.textContent=(T.pair||'Pair')+' '+(k+1);
      var sl=document.createElement('select');sl.className='ng-select ng-psel';sl.setAttribute('aria-label',lb.textContent);
      singles.forEach(function(ci){var o=document.createElement('option');o.value=ci;o.textContent=CN[ci];sl.appendChild(o);});
      sl.value=String(c);
      (function(k,sl){sl.addEventListener('change',function(){state.pairs[size][k]=+sl.value;state.size=size;render();});})(k,sl);
      row.appendChild(lb);row.appendChild(sl);box.appendChild(row);
    }
    state.pairs[size]=arr;
  });
  tiers.forEach(function(t){
    t.addEventListener('click',function(e){
      if(e.target.closest('.ng-select')){return;}
      if(e.target.tagName==='INPUT'){return;}
      state.size=+t.dataset.size;render();
    });
    t.querySelector('input').addEventListener('change',function(){state.size=+t.dataset.size;render();});
    var sel=t.querySelector('.ng-select:not(.ng-psel)');
    if(sel){sel.addEventListener('change',function(){state.color=+sel.value;state.size=+t.dataset.size;render();});}
  });
  sbtn.addEventListener('click',function(){atc.click();});
  render();
  var track=document.getElementById('ng-track'),thumbs=[].slice.call(root.querySelectorAll('.ng-thumb')),cnt=document.getElementById('ng-count');
  function idx(){return Math.round(track.scrollLeft/track.clientWidth);}
  function go(i){i=Math.max(0,Math.min(thumbs.length-1,i));track.scrollTo({left:i*track.clientWidth,behavior:'smooth'});}
  track.addEventListener('scroll',function(){var i=idx();thumbs.forEach(function(t,k){t.setAttribute('aria-current',k===i?'true':'false');});cnt.textContent=(i+1)+' / '+thumbs.length;},{passive:true});
  thumbs.forEach(function(t,i){t.addEventListener('click',function(){go(i);});});
  document.getElementById('ng-prev').addEventListener('click',function(){go(idx()-1);});
  document.getElementById('ng-next').addEventListener('click',function(){go(idx()+1);});
  var sticky=document.getElementById('ng-sticky');
  if('IntersectionObserver' in window){
    var io=new IntersectionObserver(function(en){en.forEach(function(e){sticky.dataset.show=(!e.isIntersecting&&e.boundingClientRect.top<0)?'true':'false';});},{threshold:0});
    io.observe(atc);
    var reduce=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var tryPlay=function(v){var w=v.parentNode;v.muted=true;v.defaultMuted=true;v.playsInline=true;v.setAttribute('playsinline','');v.setAttribute('webkit-playsinline','');if(v.readyState===0){v.preload='auto';v.load();}var p=v.play();if(p&&p.then){p.then(function(){w.classList.remove('is-paused');}).catch(function(){w.classList.add('is-paused');});}};
    var vio=new IntersectionObserver(function(en){en.forEach(function(e){var v=e.target;if(e.isIntersecting&&!reduce){tryPlay(v);}else{v.pause();}});},{threshold:.5});
    [].forEach.call(root.querySelectorAll('.ng-slide video, .ng-vid video'),function(v){
      vio.observe(v);
      if(reduce){v.parentNode.classList.add('is-paused');}
      var b=v.parentNode.querySelector('.ng-play');
      if(b){b.addEventListener('click',function(){v.muted=true;v.play().then(function(){v.parentNode.classList.remove('is-paused');}).catch(function(){});});}
    });
  }
})();
