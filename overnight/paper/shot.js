const {chromium}=require('playwright');(async()=>{const b=await chromium.launch();const p=await b.newPage({viewport:{width:1280,height:860}});
const errs=[];p.on('pageerror',e=>errs.push(e.message));p.on('console',m=>{if(m.type()==='error')errs.push(m.text())});
await p.goto('file://'+process.argv[2]);await p.waitForTimeout(1500);
for(const i of process.argv.slice(3)){await p.evaluate(i=>document.querySelectorAll('.dots button')[i].click(),+i);await p.waitForTimeout(2600);await p.locator('#stage').screenshot({path:`/tmp/claude-0/s${i}.png`});}
console.log(errs.join('\n')||'no errors');await b.close();})();
