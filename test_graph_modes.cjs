const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const src=fs.readFileSync(__dirname+'/web/graph.js','utf8');
const nodes=new Map(),classes=new Set(),stored={};let wakes=0;
const $=id=>{if(!nodes.has(id))nodes.set(id,{attrs:{},setAttribute(k,v){this.attrs[k]=v},focus(){}});return nodes.get(id)};
$('map')._wake=()=>wakes++;
const c={$,document:{body:{classList:{contains:x=>classes.has(x),add:x=>classes.add(x),remove:x=>classes.delete(x)}},addEventListener(){}},localStorage:{setItem(k,v){stored[k]=v}},reduceGraphMotion:{matches:false,addEventListener(){}}};
vm.createContext(c);vm.runInContext("let graphMode='light',graphModeBeforeExpand='light';"+src.slice(src.indexOf('function syncGraphModeControls(){')),c);
$('mapModeAnimated').onclick();assert.equal($('mapModeAnimated').attrs['aria-pressed'],'true');assert.equal(stored['bora.mapMode'],'animated');
$('mapModeLight').onclick();assert.equal($('mapModeLight').attrs['aria-pressed'],'true');
$('mapExpand').onclick();assert.ok(classes.has('map-expanded'));assert.equal($('mapModeAnimated').attrs['aria-pressed'],'true');assert.equal(stored['bora.mapMode'],'light','recording must not overwrite saved preference');
$('mapExpand').onclick();assert.ok(!classes.has('map-expanded'));assert.equal($('mapModeLight').attrs['aria-pressed'],'true');assert.ok(wakes>=4);
const org=fs.readFileSync(__dirname+'/web/organization.js','utf8');
const colors={notes:[{id:'A/file.md'},{id:'B/file.md'}],organizationData:{folders:['A','B'],colors:{}}};vm.createContext(colors);
vm.runInContext(org.slice(org.indexOf('const contentRootColors='),org.indexOf("$('folderColors').onclick="))+';syncContentColors();',colors);
assert.notEqual(colors.folderColor('A','fallback'),colors.folderColor('B','fallback'));
assert.equal(colors.folderColor('A/sub','fallback'),colors.folderColor('A','fallback'));
colors.organizationData.colors.A='#123456';assert.equal(colors.folderColor('A/sub','fallback'),'#123456');
console.log('12 mode/color behavioral checks passed');

