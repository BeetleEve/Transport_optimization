const fs=require('fs'),vm=require('vm'),assert=require('assert');
class Element{constructor(){this.children=[];this.attrs={};this.value='';this.style={};this.clientWidth=1000;this.clientHeight=650;}appendChild(e){this.children.push(e);return e}replaceChildren(){this.children=[]}setAttribute(k,v){this.attrs[k]=String(v)}getAttribute(k){return this.attrs[k]}setPointerCapture(){}}
const elements=Object.fromEntries(['route','map','title','stats','paths','stops'].map(k=>[k,new Element()]));
const context={document:{getElementById:k=>elements[k],createElement:()=>new Element(),createElementNS:()=>new Element()},console};vm.createContext(context);
const html=fs.readFileSync('output/results.html','utf8');const code=html.match(/<script>([\s\S]*?)<\/script>/)[1];vm.runInContext(code,context);
assert.equal(elements.route.children.length,36);
for(let i=0;i<36;i++){elements.route.value=String(i);vm.runInContext('show()',context);assert(elements.paths.children.length>0);assert(elements.stops.children.length>0);assert(elements.title.textContent.length>0);const before=elements.map.attrs.viewBox;vm.runInContext('zoom(.7)',context);assert.notEqual(elements.map.attrs.viewBox,before);assert(!elements.map.attrs.viewBox.includes('NaN'));}
console.log('PASS: JavaScript executes; all 36 routes draw paths and stop rows; zoom works.');
