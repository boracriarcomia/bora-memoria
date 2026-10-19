const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const s=fs.readFileSync(__dirname+'/web/graph.js','utf8'),c={};vm.createContext(c);vm.runInContext(s.slice(s.indexOf('function spaceGraphNodes('),s.indexOf('// Visual categories never move')),c);
for(const N of [20,50,80]){const X=Array(N).fill(400),Y=Array(N).fill(280),R=Array.from({length:N},(_,i)=>i<3?29:6),W=Array(N).fill(1);c.spaceGraphNodes(X,Y,R,W);for(let i=0;i<N;i++)for(let j=i+1;j<N;j++)assert.ok(Math.hypot(X[i]-X[j],Y[i]-Y[j])>=R[i]+R[j]+3.7,'node clearance lost');}
console.log('3 spacing scenarios passed with large hubs and small nodes');
