const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(__dirname+'/web/graph.js','utf8');
const tick=source.slice(source.indexOf('  function tick(){'),source.indexOf('  draw();graphFrame=requestAnimationFrame(tick);'));
function run({hidden=false,background=false,drag=false,moving=false,reduced=false,until=0,animated=false}={}){
 const c={performance:{now:()=>10000},document:{hidden},window:{boraBackground:background},previousFrame:0,frameTimes:[],workTimes:[],highlightWork:[],frames:0,graphFrame:0,graph:{dataset:{}},graphInteractionUntil:until,nodeDrag:drag,reduceGraphMotion:{matches:reduced},graphAnimated:()=>animated,points:[{x:moving?5:0,ax:0,y:0,ay:0,vx:0,vy:0}],pulses:[{dots:[{style:{}}]}],scheduled:0,drawn:0,springStep(){},draw(){c.drawn++},stepPulses(){},requestAnimationFrame(){c.scheduled++;return 99;}};
 vm.createContext(c);vm.runInContext(tick+';tick();',c);return c;
}
assert.equal(run().scheduled,0,'stable map must stop');
assert.equal(run().graph.dataset.renderState,'idle');
assert.equal(run({moving:true}).scheduled,1,'springs must settle');
assert.equal(run({drag:true}).scheduled,1,'drag must animate');
assert.equal(run({until:11000}).scheduled,1,'recent interaction must animate');
assert.equal(run({hidden:true}).drawn,0,'hidden map must not draw');
assert.equal(run({background:true}).drawn,0,'tray map must not draw');
assert.equal(run({reduced:true,moving:true}).scheduled,0,'reduced motion must stop');
assert.equal(run().pulses[0].dots[0].style.visibility,'hidden');
assert.equal(run({animated:true}).scheduled,1,'animated mode stays alive');
console.log('10 graph scheduling checks passed');
