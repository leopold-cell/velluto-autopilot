const {chromium}=require('playwright');const fs=require('fs');
const css=`@font-face{font-family:I;src:url(file:///usr/share/fonts/opentype/inter/Inter-ExtraBold.otf);font-weight:800}
@font-face{font-family:I;src:url(file:///usr/share/fonts/opentype/inter/Inter-Bold.otf);font-weight:700}
@font-face{font-family:I;src:url(file:///usr/share/fonts/opentype/inter/Inter-SemiBold.otf);font-weight:600}
@font-face{font-family:I;src:url(file:///usr/share/fonts/opentype/inter/Inter-Medium.otf);font-weight:500}
html,body{margin:0;width:1080px;height:1350px;font-family:I,'Noto Color Emoji';background:#fcfcfc;overflow:hidden}
.ph{position:absolute;left:54px;top:150px;width:972px;height:1215px;object-fit:cover;-webkit-mask-image:linear-gradient(to right,transparent 0,#000 7%,#000 93%,transparent 100%),linear-gradient(to bottom,transparent 0,#000 7%,#000 90%,transparent 100%);-webkit-mask-composite:source-in;mask-composite:intersect}
.hd{position:absolute;left:0;right:0;top:92px;text-align:center;color:#111}
.br{font-weight:600;font-size:24px;letter-spacing:9px;color:#8a8a8a}
.h1{font-weight:800;font-size:104px;letter-spacing:-3px;line-height:1;margin-top:20px}
.tag{display:inline-block;margin-top:26px;padding:14px 30px;border-radius:999px;background:#111;color:#fff;font-weight:700;font-size:34px;letter-spacing:.3px}
.bd{display:inline-block;vertical-align:top;margin:26px 0 0 12px;padding:14px 26px;border-radius:999px;font-weight:800;font-size:30px;letter-spacing:.5px;text-transform:uppercase}
.red{background:#f01818;color:#fff}.blk{background:#111;color:#fff}
.ft{position:absolute;left:0;right:0;bottom:64px;text-align:center;font-weight:500;font-size:32px;color:#555}`;
const S=JSON.parse(fs.readFileSync(process.argv[2]));
(async()=>{const b=await chromium.launch();const p=await b.newPage({viewport:{width:1080,height:1350}});
for(const s of S){const html=`<html><head><meta charset=utf-8><style>${css}</style></head><body><img class=ph src="file:///tmp/claude-0/sets/${s.img}"><div class=hd><div class=br>VELLUTO NIGHT GLOW</div><div class=h1>${s.h}</div><div class=tag>${s.tag}</div>${s.badge?`<div class="bd ${s.bc}">${s.badge}</div>`:''}</div><div class=ft>${s.ft}</div></body></html>`;
fs.writeFileSync('/tmp/claude-0/sets/_s.html',html);await p.goto('file:///tmp/claude-0/sets/_s.html');await p.evaluate(()=>document.fonts.ready);await p.waitForTimeout(150);await p.screenshot({path:'/tmp/claude-0/sets/'+s.out,type:'jpeg',quality:92});}
await b.close();console.log('ok')})();
