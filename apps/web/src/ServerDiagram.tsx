// Geometry/colors ported from quote Demo 65e4650 dist/app.js box()/draw().
// Counts and state now come from actual selected SKU data, never Demo prices.
import {useState} from 'react';
export const quoteCategories={host:'主机',psu:'电源',cpu:'CPU',gpu:'GPU',memory:'内存',system_disk:'系统盘',nic:'网卡',ib:'IB 卡',data_disk:'数据盘'};
export type PartCategory=keyof typeof quoteCategories;
export function ServerDiagram({counts,invalid,onSelect}:{counts:Record<string,number>;invalid:Set<string>;onSelect:(key:PartCategory)=>void}){
 const [selected,setSelected]=useState<PartCategory>('gpu'),[expanded,setExpanded]=useState(false);
 const required=new Set(['host','psu','cpu','memory','system_disk']);
 function box(id:PartCategory,x:number,y:number,w:number,d:number,h:number,color:string,label:string,key=id as string){
  const absent=!counts[id],bad=invalid.has(id),status=bad?'异常':absent?(required.has(id)?'缺失':'未选'):'已选';const py=y+(expanded&&id!=='host'?-38:0);
  const fill=bad?'#efc6b4':absent?'#e4e9e5':color;
  const choose=()=>{setSelected(id);onSelect(id);};
  return <g key={key} className="part" role="button" tabIndex={0} aria-label={`配置${quoteCategories[id]} · ${status} · 数量 ${counts[id]??0}`} onClick={choose} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();choose();}}} opacity={absent?.6:1}>
   <polygon points={`${x},${py} ${x+w},${py-w*.38} ${x+w+d*.65},${py-w*.38+d*.42} ${x+d*.65},${py+d*.42}`} fill={fill} stroke={selected===id?'#276744':bad?'#a34e2d':'#fff'} strokeWidth={selected===id?3:1} strokeDasharray={absent?'4 3':undefined}/>
   <polygon points={`${x},${py} ${x+d*.65},${py+d*.42} ${x+d*.65},${py+d*.42+h} ${x},${py+h}`} fill={fill} style={{filter:'brightness(.8)'}}/>
   <polygon points={`${x+d*.65},${py+d*.42} ${x+w+d*.65},${py-w*.38+d*.42} ${x+w+d*.65},${py-w*.38+d*.42+h} ${x+d*.65},${py+d*.42+h}`} fill={fill} style={{filter:'brightness(.62)'}}/>
   <text x={x+w*.5+d*.3} y={py-w*.19+d*.2+5} textAnchor="middle" fontSize={id==='host'?17:12} fill="#163d32" fontWeight="700" transform={`rotate(-21 ${x+w*.5+d*.3} ${py-w*.19+d*.2})`}>{label}</text>
  </g>;
 }
 return <section className="visual"><div className="panel-top"><div><span className="eyebrow">YOUR SERVER</span><h2>服务器结构</h2></div><span className="pill">部件示意</span></div><div className="stage"><svg viewBox="0 0 560 465" aria-label="可点击的服务器部件等距结构图">
 <defs><filter id="quote-shadow"><feGaussianBlur stdDeviation="15"/></filter></defs><ellipse cx="290" cy="374" rx="174" ry="36" fill="#214332" opacity=".13" filter="url(#quote-shadow)"/>
 {box('host',57,235,296,220,49,'#c2d2c8','')}{box('psu',67,199,69,71,34,'#cfdec2','PSU')}{box('cpu',155,193,64,59,29,'#c7d5e0','CPU')}
 {box('memory',225,165,18,78,24,'#b4cdaa','RAM')}{box('memory',249,157,18,78,24,'#b4cdaa','', 'memory2')}
 {Array.from({length:Math.max(1,Math.min(counts.gpu??0,4))},(_,i)=>box('gpu',110+i*47,258-i*18,37,129,38,'#a7c8b0',i===0?'GPU':'','gpu'+i))}
 {(counts.gpu??0)>4&&<text x="335" y="200" fill="#356348" fontSize="14">+{counts.gpu-4} GPU</text>}
 {box('system_disk',290,188,47,54,16,'#e8ce96','SSD')}{box('nic',316,232,27,62,18,'#b8cddd','NET')}{box('ib',345,221,27,62,18,'#bab9d9','IB')}{box('data_disk',311,279,55,53,18,'#e8ce96','DATA')}
 <text x="94" y="391" fontSize="13" letterSpacing="3" fill="#536d5b" transform="rotate(-21 94 391)">SILICON / COMPUTE NODE</text></svg></div>
 <div className="visual-bottom"><span>点击部件定位配置</span><button onClick={()=>setExpanded(!expanded)}>{expanded?'⇩ 合拢部件':'⇧ 展开部件'}</button></div>
 <div className="detail">{quoteCategories[selected]} · 数量 {counts[selected]??0}<small>{invalid.has(selected)?'异常 · 请查看后端提示':counts[selected]?'已选 · 兼容性以后端为准':'未选 / 缺失'}</small></div>
 <p className="caption">虚线为未选 / 缺失；橙色为停用或异常。<br/>示意图非精确装配模型，不表示兼容认证。</p></section>;
}
