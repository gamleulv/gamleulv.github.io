/* Statistikk er deaktivert inntil en egen GA4-strøm er konfigurert. */
const gaId = '';
const $ = id => document.getElementById(id);
const dialog = $('visning');
let key, items, current = 0, sw, measuring = false, counted = false, started = false;
let lastButton;
const sealUrl = 'data/manifest.bin';
const viewUrls = new Map();
const pending = new Map();
function event(name, data = {}) {
  if (measuring) window.gtag('event', name, {
    page_location: location.origin + '/Media/galleri/',
    page_title: 'Bildegalleri', page_referrer: '', ...data
  });
}
function startAnalytics() {
  if (!/^G-[A-Z0-9]+$/.test(gaId)) return;
  window['ga-disable-' + gaId] = false;
  if (!started) {
    started = true;
    window.dataLayer = window.dataLayer || [];
    window.gtag = function(){ window.dataLayer.push(arguments); };
    gtag('consent','default',{analytics_storage:'denied',ad_storage:'denied',ad_user_data:'denied',ad_personalization:'denied'});
    gtag('js',new Date());
    gtag('consent','update',{analytics_storage:'granted'});
    gtag('config',gaId,{send_page_view:false,allow_google_signals:false,allow_ad_personalization_signals:false,
      page_location:location.origin+'/Media/galleri/',page_referrer:'',page_title:'Bildegalleri'});
    const tag = document.createElement('script');
    tag.async = true;
    tag.src = 'https://www.googletagmanager.com/gtag/js?id=' + gaId;
    document.head.append(tag);
  } else gtag('consent','update',{analytics_storage:'granted'});
  measuring = true;
  $('statstatus').textContent = 'Statistikk er på for denne visningen.';
  if (!counted) { event('page_view'); counted = true; }
}
$('ja').onclick = startAnalytics;
$('nei').onclick = () => {
  measuring = false;
  if (started) {
    gtag('consent','update',{analytics_storage:'denied'});
    window['ga-disable-' + gaId] = true;
  }
  $('statstatus').textContent = 'Statistikk er av.';
};
async function read(path) {
  const response = await fetch(path, {referrerPolicy:'no-referrer'});
  if (!response.ok) throw Error('Kunne ikke hente filen');
  return new Uint8Array(await response.arrayBuffer());
}
async function decrypt(data, useKey, label) {
  return crypto.subtle.decrypt({name:'AES-GCM',iv:data.slice(0,12),additionalData:new TextEncoder().encode(label)},useKey,data.slice(12));
}
function picture(index) {
  if (viewUrls.has(index)) return Promise.resolve(viewUrls.get(index));
  if (pending.has(index)) return pending.get(index);
  const file = items[index].id;
  const result = read('data/'+file+'.bin').then(data=>decrypt(data,key,file)).then(clear=>{
    const url = URL.createObjectURL(new Blob([clear],{type:'image/jpeg'}));
    viewUrls.set(index,url);
    return url;
  }).finally(()=>pending.delete(index));
  pending.set(index,result);
  return result;
}
function render() {
  $('antall').textContent = `${items.length} bilder. Trykk på et bilde for å se det i stort format.`;
  const observer = new IntersectionObserver(entries=>{
    for (const {target,isIntersecting} of entries) if (isIntersecting) {
      observer.unobserve(target);
      picture(Number(target.dataset.index)).then(url=>target.src=url).catch(()=>target.alt='Bildet kunne ikke lastes');
    }
  },{rootMargin:'300px'});
  items.forEach(({date},index)=>{
    const button = document.createElement('button');
    button.className = 'bilde';
    button.setAttribute('aria-label',`Åpne bilde ${index+1}${date?', '+date:''}`);
    const figure = document.createElement('figure'), img = new Image(), cap = document.createElement('figcaption');
    img.alt = ''; img.dataset.index=index;
    cap.textContent = date || `Bilde ${index+1}`;
    figure.append(img,cap); button.append(figure);
    button.onclick=()=>{lastButton=button; show(index);};
    $('bilder').append(button);
    observer.observe(img);
  });
}
async function show(index) {
  current = (index+items.length)%items.length;
  const n=current, item=items[n], pos=`Bilde ${n+1} av ${items.length}`;
  $('stort').removeAttribute('src');
  $('stort').alt=pos;
  $('bildetekst').textContent = pos+(item.date?' · '+item.date:'');
  if (!dialog.open) dialog.showModal();
  try {
    const url=await picture(n);
    if (current===n && dialog.open) $('stort').src=url;
  } catch {
    if (current===n && dialog.open) $('bildetekst').textContent='Bildet kunne ikke lastes';
  }
  event('gallery_image_open',{image_id:item.id});
}
$('forrige').onclick=()=>show(current-1);
$('neste').onclick=()=>show(current+1);
$('lukk').onclick=()=>dialog.close();
dialog.addEventListener('click',e=>{if(e.target===dialog)dialog.close();});
dialog.addEventListener('close',()=>{ $('stort').removeAttribute('src'); lastButton?.focus(); });
dialog.addEventListener('keydown',e=>{
  if(e.key==='ArrowRight'||e.key==='ArrowLeft'){e.preventDefault();show(current+(e.key==='ArrowRight'?1:-1));}
});
$('stort').addEventListener('touchstart',e=>{sw=e.changedTouches[0].clientX;},{passive:true});
$('stort').addEventListener('touchend',e=>{const delta=e.changedTouches[0].clientX-sw;if(Math.abs(delta)>45)show(current+(delta<0?1:-1));},{passive:true});
$('form').addEventListener('submit',async e=>{
  e.preventDefault();
  const submit=e.target.querySelector('button'), pass=$('passord');
  if (submit.disabled) return;
  submit.disabled=true;
  $('status').textContent='Åpner galleriet …';
  try {
    const data=await read(sealUrl);
    const base=await crypto.subtle.importKey('raw',new TextEncoder().encode(pass.value),'PBKDF2',false,['deriveKey']);
    key=await crypto.subtle.deriveKey({name:'PBKDF2',salt:data.slice(0,16),iterations:600000,hash:'SHA-256'},base,{name:'AES-GCM',length:256},false,['decrypt']);
    items=JSON.parse(new TextDecoder().decode(await decrypt(data.slice(16),key,'manifest-v1')));
    if (!Array.isArray(items)||!items.length||!items.every(x=>/^[a-f0-9]{24}$/.test(x.id))) throw Error('Galleri');
    render();
    pass.value='';
    $('laas').hidden=true;
    $('innhold').hidden=false;
    $('valg').hidden=!/^G-[A-Z0-9]+$/.test(gaId);
    $('antall').tabIndex=-1;
    $('antall').focus();
  } catch { $('status').textContent='Kunne ikke åpne galleriet. Kontroller passordet og prøv igjen.'; }
  finally { submit.disabled=false; }
});
