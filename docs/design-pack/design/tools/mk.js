// usage: node mk.js <file.dc.html> <out.html>
const fs=require('fs');
const s=fs.readFileSync(process.argv[2],'utf8');
const style=s.slice(s.indexOf('<style>'), s.indexOf('</style>')+8);
const xa=s.indexOf('</helmet>')+9, xb=s.indexOf('</x-dc>');
const markup=s.slice(xa,xb);
const a=s.indexOf('>', s.indexOf('data-dc-script'))+1, b=s.indexOf('</script>', a);
const js=s.slice(a,b);
const html=`<!doctype html><html><head><meta charset="utf-8">${style}<style>body{margin:0}</style></head><body><template id="tpl">${markup}</template><div id="root"></div>
<script>
class DCLogic{constructor(p){this.props=p;}setState(p){Object.assign(this.state,p);}}
${js}
function get(path,scope){let o=scope;for(const k of path.trim().split('.')){o=o==null?undefined:o[k];}return o;}
function interp(str,scope){return str.replace(/\\{\\{\\s*([\\w.]+)\\s*\\}\\}/g,(m,p)=>{if(p==='true')return 'true';if(p==='false')return 'false';const v=get(p,scope);return v==null||typeof v==='function'?'':String(v);});}
function render(node,scope,parent){for(const ch of node.childNodes){if(ch.nodeType===3){parent.appendChild(document.createTextNode(interp(ch.textContent,scope)));continue;}if(ch.nodeType!==1)continue;const tag=ch.tagName.toLowerCase();
if(tag==='sc-if'){const m=ch.getAttribute('value').match(/\\{\\{\\s*([\\w.]+)\\s*\\}\\}/);if(get(m[1],scope))render(ch,scope,parent);continue;}
if(tag==='sc-for'){const m=ch.getAttribute('list').match(/\\{\\{\\s*([\\w.]+)\\s*\\}\\}/);const list=get(m[1],scope)||[];const as=ch.getAttribute('as');list.forEach(it=>{const sc=Object.create(scope);sc[as]=it;render(ch,sc,parent);});continue;}
const el=ch.namespaceURI==='http://www.w3.org/2000/svg'?document.createElementNS(ch.namespaceURI,ch.tagName):document.createElement(ch.tagName);
for(const at of ch.attributes){if(at.name.startsWith('on')||at.name.startsWith('hint-'))continue;el.setAttribute(at.name,interp(at.value,scope));}
render(ch,scope,el);parent.appendChild(el);}}
const c=new Component({});
let cfg={};try{cfg=JSON.parse(decodeURIComponent(location.hash.slice(1)||'{}'));}catch(e){}
Object.assign(c.state,cfg.state||{});
(cfg.calls||[]).forEach(f=>{const v=c.renderVals();const fn=get(f,v);if(typeof fn==='function')fn({target:{value:'0'}});});
for(let i=0;i<(cfg.ticks||0);i++){if(c.tick)c.tick();}
render(document.getElementById('tpl').content,c.renderVals(),document.getElementById('root'));
</script></body></html>`;
fs.writeFileSync(process.argv[3],html);
