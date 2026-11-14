const esc=s=>String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
const CRAFT_HOST="https://secure-res.craft.do/v2/KKdjWM1GarHjR8pWHQiahg2EC5oR7Tbfvk28C3KUK4UBtHDE3JfwJpHEUVV7A4APhhZJNaRvGDkiVC479Kn5V68NjLL1sLwWzhZ6S5F8v6PSLhiqbQxdqqoR4mZAECK8kXkkwpieVopeVtdKd8rv12wWh";
const MALER=[
 {navn:"Høstblader (Craft)",title:"Høstblader",
  top:CRAFT_HOST+"dw9XdFPbE3FikoTquhhoMo4i1Nej8zt7FGLWB4Knodb6kyranf6rjwBmehzznFmZ7jbptgoFLH2D56FEvSdy2WRbki4mnk8LchgDoV8vJLD1rz2wjX1yiULRJDgVBSKTnkyRL3jWJHo3hjyHytcbTKi6n/Image.jpg",
  mid:CRAFT_HOST+"897PQ7qcS8CAHN6pW35hgywG7Ta9i6HtWBnunbPX8YNJ9ghhWd427TFQNhZtgtfQG1V8DhkWXJw2njQaSuemLTQHHXVrujURGN9HQM6TvouQoKMSYHHiUruk9YtSfnPVbH7is7FCyTBr9L1cNdGRux6mJ/bg.jpg",
  bot:CRAFT_HOST+"G5wByDdqf2AF3xBbGrDfxCWv3kMHJbmWBuctZk8h8bXC7F9H88neSRVZ4MD4a5K1DSoNLTedmYTzoZ3bzS9o7xfniav79CfrFm3E7CgCuTxynnbsXATDU6bLUqNm8bJTnEfQo4Xgrc2XeMVBbRCzvruKn/bottom.jpg",
  bg:"#b2dcc8",bg2:"#b2dcc8",fg:"#081b12"}
];
MALER[0].kat="Standard";
CRAFT_MALER.forEach(m=>MALER.push(Object.assign({},m,{title:m.navn,bg2:m.bg})));
const D=Object.assign({mal:"0",bc:"#000000",font:"'Palatino-Roman', Palatino, 'Palatino Linotype', Georgia, 'Times New Roman', serif",fs:"18",bw:"2",auto:true,autoFg:true,
 txt:"Kjære deg,\n\nHer kommer innholdet i e-posten.\n\nHilsen meg"},MALER[0]);delete D.navn;
const K=["mal","title","top","mid","bot","auto","bg","bg2","bc","autoFg","fg","font","fs","bw","txt"],$=id=>document.getElementById(id);
let S=Object.assign({},D);
{const g={};MALER.forEach((m,i)=>(g[m.kat]=g[m.kat]||[]).push(`<option value="${i}">${esc(m.navn)}</option>`));
 $("mal").innerHTML=Object.keys(g).map(k=>`<optgroup label="${esc(k)}">${g[k].join("")}</optgroup>`).join("");}
const isChk=k=>$(k).type==="checkbox";
function fill(){K.forEach(k=>{if(isChk(k))$(k).checked=!!S[k];else $(k).value=S[k]});$("bg").disabled=$("bg2").disabled=S.auto;$("fg").disabled=S.autoFg}
K.forEach(k=>$(k).addEventListener(isChk(k)||k==="mal"?"change":"input",()=>{
 S[k]=isChk(k)?$(k).checked:$(k).value;
 if(k==="mal"){const m=MALER[+S.mal];["title","top","mid","bot"].forEach(x=>S[x]=m[x]||"");
  if(m.bg){S.bg=m.bg;S.bg2=m.bg2||m.bg}if(m.fg){S.fg=m.fg;S.autoFg=false}else S.autoFg=true;
  if(m.font){const o=[...$("font").options].find(o=>o.value.toLowerCase().includes(m.font.toLowerCase().split(",")[0].replace(/['"]/g,"").trim()));if(o)S.font=o.value}}
 fill();if(["mal","top","mid","bot","auto","autoFg"].includes(k))autoColors();else render()}));

/* ---------- Fargeuttak ---------- */
const hex=c=>"#"+c.map(v=>Math.round(v).toString(16).padStart(2,"0")).join("");
const rgb=h=>[1,3,5].map(i=>parseInt(h.slice(i,i+2),16));
const lum=h=>{const[r,g,b]=rgb(h).map(v=>{v/=255;return v<=.03928?v/12.92:Math.pow((v+.055)/1.055,2.4)});return .2126*r+.7152*g+.0722*b};
const mix=(a,b)=>hex(rgb(a).map((v,i)=>(v+rgb(b)[i])/2));
const cache={};
function loadImg(u){if(cache[u])return cache[u];return cache[u]=new Promise((res,rej)=>{const im=new Image();im.crossOrigin="anonymous";
 im.onload=()=>res(im);im.onerror=()=>{delete cache[u];rej()};im.src="https://wsrv.nl/?url="+encodeURIComponent(u)+"&n=1&output=png&w=400"})}
async function sample(u,where){const im=await loadImg(u);const c=document.createElement("canvas");c.width=im.naturalWidth;c.height=im.naturalHeight;
 const x=c.getContext("2d");x.drawImage(im,0,0);const h=Math.max(1,Math.round(c.height*.03));
 const y=where==="bottom"?c.height-h:0,hh=where==="all"?c.height:h;const d=x.getImageData(0,y,c.width,hh).data;let r=0,g=0,b=0,n=0;
 for(let i=0;i<d.length;i+=4){if(d[i+3]<128)continue;r+=d[i];g+=d[i+1];b+=d[i+2];n++}if(!n)throw 0;return hex([r/n,g/n,b/n])}
let job=0;
async function autoColors(){const my=++job;render();
 try{if(S.auto){
  if(S.mid){const c=await sample(S.mid,"all");S.bg=S.bg2=c;info("Bakgrunnsfarge hentet fra bakgrunnsbildet: "+c)}
  else{const t=S.top?await sample(S.top,"bottom"):null,b=S.bot?await sample(S.bot,"top"):null;S.bg=t||b||S.bg;S.bg2=b||t||S.bg2;
   info(S.bg===S.bg2?"Bakgrunnsfarge hentet fra bildene: "+S.bg:"Overgang fra "+S.bg+" (toppbildet) til "+S.bg2+" (bunnbildet)")}}
  if(S.autoFg){const L=lum(mix(S.bg,S.bg2));S.fg=L>.35?"#1a1a1a":"#f5f0e6"}
  if(my===job){fill();render()}}
 catch(e){if(my===job)info("Kunne ikke lese fargene fra bildene. Velg fargene manuelt.")}}
const info=t=>$("info").textContent=t;

/* ---------- E-post-HTML ---------- */
const esc0=s=>String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
function fmt(t,s){return t.trim().split(/\n\s*\n/).map(p=>{let h=esc(p).replace(/\*\*(.+?)\*\*/g,"<b>$1</b>").replace(/\*(.+?)\*/g,"<i>$1</i>")
 .replace(/(https?:\/\/[^\s<]+)/g,`<a href="$1" style="color:${s.fg};text-decoration:underline;">$1</a>`).replace(/\n/g,"<br>");
 return `<p style="margin:0 0 1em 0;font-family:${s.font.replace(/"/g,"'")};color:${s.fg};font-size:${+s.fs||18}px;line-height:1.5;">${h}</p>`}).join("\n")}
function build(s){const bw=+s.bw||0,fs=+s.fs||18,grad=!s.mid&&s.bg!==s.bg2,flat=grad?mix(s.bg,s.bg2):s.bg;
 const img=(u,a,c)=>u?`<tr><td bgcolor="${c}" style="padding:0;background-color:${c};line-height:0;font-size:0;"><img src="${esc(u)}" width="600" alt="${a}" style="width:100%;max-width:100%;height:auto;display:block;border:0;"></td></tr>`:"";
 const bgcss=s.mid?`background-image:url('${esc(s.mid)}');background-repeat:repeat;`:grad?`background-image:linear-gradient(to bottom, ${s.bg}, ${s.bg2});`:"";
 const vml=s.mid?`<!--[if gte mso 9]><v:rect xmlns:v="urn:schemas-microsoft-com:vml" fill="true" stroke="false" style="mso-width-percent:1000;"><v:fill type="tile" src="${esc(s.mid)}" color="${flat}"/><v:textbox inset="0,0,0,0"><![endif]-->`:"";
 const vmlEnd=s.mid?`<!--[if gte mso 9]></v:textbox></v:rect><![endif]-->`:"";
 return `<!DOCTYPE html>
<html lang="no" xmlns="http://www.w3.org/1999/xhtml" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><meta name="x-apple-disable-message-reformatting">
<title>${esc(s.title)}</title><meta property="og:title" content="${esc(s.title)}">${s.top?`<meta property="og:image" content="${esc(s.top)}">`:""}
<!--[if mso]><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml><![endif]-->
<style>html,body{margin:0 auto!important;padding:0!important;height:100%!important;width:100%!important;background-color:#ffffff;}
*{-ms-text-size-adjust:100%;-webkit-text-size-adjust:100%;}table,td{mso-table-lspace:0pt!important;mso-table-rspace:0pt!important;}
table{border-spacing:0!important;border-collapse:collapse!important;margin:0 auto!important;}img{-ms-interpolation-mode:bicubic;border:0;outline:none;text-decoration:none;}
@media screen and (min-width:600px){.txt p{font-size:${fs+2}px!important;}}</style></head>
<body bgcolor="#ffffff" style="margin:0;padding:0!important;mso-line-height-rule:exactly;background-color:#ffffff;">
<div style="width:100%;background-color:#ffffff;">
<table role="presentation" align="center" cellspacing="0" cellpadding="0" border="0" width="100%" bgcolor="#ffffff" style="width:100%;margin:auto;border:${bw}px solid ${s.bc};">
${img(s.top,"topp",s.bg)}
<tr><td class="txt" bgcolor="${flat}" style="background-color:${flat};${bgcss}text-align:left;padding:0;">${vml}
<div style="padding:24px 20px 8px 20px;">
${fmt(s.txt,s)}
</div>${vmlEnd}</td></tr>
${img(s.bot,"bunn",s.bg2)}
</table></div></body></html>`}
function render(){$("pv").srcdoc=build(S)}

/* ---------- Knapper ---------- */
const say=m=>{$("msg").textContent=m;setTimeout(()=>$("msg").textContent="",4000)};
$("copyRich").onclick=async()=>{const h=build(S);try{await navigator.clipboard.write([new ClipboardItem({"text/html":new Blob([h],{type:"text/html"}),"text/plain":new Blob([S.txt],{type:"text/plain"})})]);say("Kopiert – lim inn i en ny e-post i Mail/Outlook.")}
 catch(e){const d=$("pv").contentDocument;const r=d.createRange();r.selectNodeContents(d.body);const sel=d.getSelection();sel.removeAllRanges();sel.addRange(r);d.execCommand("copy");say("Kopiert (reservemetode).")}};
$("copyCode").onclick=async()=>{await navigator.clipboard.writeText(build(S));say("HTML-koden er kopiert.")};
const file=()=>new File([build(S)],(S.title||"epost").replace(/[^\wæøåÆØÅ-]+/g,"_")+".html",{type:"text/html"});
$("dl").onclick=()=>{const f=file(),a=document.createElement("a");a.href=URL.createObjectURL(f);a.download=f.name;a.click()};
$("share").onclick=async()=>{const f=file();if(navigator.canShare&&navigator.canShare({files:[f]}))await navigator.share({files:[f],title:S.title});else say("Deling støttes ikke her – bruk Last ned.")};
$("reset").onclick=()=>{S=Object.assign({},D);fill();autoColors()};
fill();autoColors();
