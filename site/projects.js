const list=document.querySelector('#project-list');
const detail=document.querySelector('#project-detail');
function el(tag,text,cls){
  const node=document.createElement(tag);
  if(text) node.textContent=text;
  if(cls) node.className=cls;
  return node;
}
function detailUrl(item){return 'project.html?id='+encodeURIComponent(item.id)}
function link(text,url,cls){const a=el('a',text,cls);a.href=url;return a}
function cover(item){
  const img=el('img');img.src='art/'+item.id+'.png';img.alt='';img.width=800;img.height=460;
  return img;
}
function renderCards(data){
  for(const p of data){
    const card=el('article',null,'card');
    const poster=link('',detailUrl(p),'poster');poster.setAttribute('aria-label',p.name+' 자세히 보기');poster.append(cover(p));
    const body=el('div',null,'card-body');
    const title=el('h2');title.append(link(p.name,detailUrl(p)));
    body.append(el('p',p.context,'meta'),title,el('p',p.summary),el('p','담당 · '+p.role,'role'),link('자세히 보기 ↗',detailUrl(p),'more'));
    card.append(poster,body);list.append(card);
  }
}
function renderDetail(data){
  const id=new URLSearchParams(location.search).get('id');
  const i=data.findIndex(item=>item.id===id);
  if(i<0){detail.append(el('h1','프로젝트를 찾을 수 없습니다.'),link('목록으로','projects.html','button'));return}
  const p=data[i];document.title=p.name+' · 김영택';
  detail.append(el('p',p.context,'eyebrow'),el('h1',p.name),el('p',p.summary,'lede'));
  const layout=el('div',null,'detail-layout');const art=el('div',null,'detail-art');art.append(cover(p));const body=el('div',null,'detail-copy');
  for(const [title,text] of [['맡은 일',p.role],['진행 과정',p.process],['결과',p.result]]){body.append(el('h2',title),el('p',text))}
  layout.append(art,body);detail.append(layout);
  const nav=el('nav',null,'project-nav');nav.setAttribute('aria-label','프로젝트 이동');
  function adjacent(label,item){if(item)return link(label,detailUrl(item));const span=el('span',label);span.setAttribute('aria-disabled','true');return span}
  nav.append(adjacent('← 이전',data[i-1]),link('목록으로','projects.html'),adjacent('다음 →',data[i+1]));detail.append(nav);
}
async function load(){
  const host=list||detail;host.replaceChildren();
  try{const response=await fetch('projects.json');if(!response.ok)throw Error();const data=await response.json();if(list)renderCards(data);else renderDetail(data)}
  catch{const retry=el('button','다시 시도');retry.onclick=load;host.append(el('p','프로젝트를 불러오지 못했습니다.'),retry)}
}
load();
