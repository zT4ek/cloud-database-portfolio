const $ = id => document.getElementById(id);
const fields = 'key nickname message createdAt mine';
const sessionKey = 'yt-guestbook-session';
const flowKey = 'yt-guestbook-flow';
const redirectUri = location.origin + '/guestbook.html';
let config, session, cursor, loading = false;
let listGeneration = 0;
const shown = new Set();
const status = (id, message) => { $(id).textContent = message; };
const encode = bytes => btoa(String.fromCharCode(...bytes)).replaceAll('+','-').replaceAll('/','_').replace(/=+$/,'');
const random = () => encode(crypto.getRandomValues(new Uint8Array(32)));

function updateControls() {
  $('form').hidden = !session;
  $('login').hidden = Boolean(session);
  $('logout').hidden = !session;
  $('login').disabled = !config;
  status('login-hint', session ? '닉네임과 메시지를 입력해 주세요.' : '로그인하면 메시지를 남길 수 있습니다.');
}
function signOutLocal() {
  session = null;
  sessionStorage.removeItem(sessionKey);
  for (const button of $('entries').querySelectorAll('article button')) button.remove();
  updateControls();
}
async function login() {
  const verifier=random(), state=random(), started=Date.now();
  const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(verifier));
  sessionStorage.setItem(flowKey,JSON.stringify({verifier,state,started}));
  const query=new URLSearchParams({client_id:config.clientId,response_type:'code',scope:'openid email',redirect_uri:redirectUri,
    state,code_challenge:encode(new Uint8Array(digest)),code_challenge_method:'S256'});
  location.assign(config.authUrl+'/oauth2/authorize?'+query);
}
async function restoreLogin() {
  const args=new URLSearchParams(location.search);
  if(args.has('code') || args.has('error')) {
    history.replaceState({},'',location.pathname);
    const flow=JSON.parse(sessionStorage.getItem(flowKey)||'null');
    sessionStorage.removeItem(flowKey);
    if(!flow || flow.state!==args.get('state') || Date.now()-flow.started>900000 || args.has('error')) {
      throw Error('로그인이 완료되지 않았습니다. 다시 로그인해 주세요.');
    }
    const response=await fetch(config.authUrl+'/oauth2/token',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},
      body:new URLSearchParams({grant_type:'authorization_code',client_id:config.clientId,redirect_uri:redirectUri,
          code:args.get('code'),code_verifier:flow.verifier})});
    if(!response.ok) throw Error('로그인 시간이 지났습니다. 다시 로그인해 주세요.');
    const value=await response.json();
    if(!value.id_token || !value.expires_in) throw Error('로그인 정보를 확인하지 못했습니다.');
    session={token:value.id_token,expires:Date.now()+value.expires_in*1000};
    sessionStorage.setItem(sessionKey,JSON.stringify(session));
  } else {
    session=JSON.parse(sessionStorage.getItem(sessionKey)||'null');
  }
  if(session && session.expires<=Date.now()) signOutLocal();
}
async function api(query, variables, needsLogin=false) {
  if(session && session.expires<=Date.now()){signOutLocal(); if(needsLogin) throw Error('다시 로그인해 주세요.');}
  if(needsLogin && !session) throw Error('로그인이 필요합니다.');
  const headers={'Content-Type':'application/json'};
  if(session) headers.Authorization=session.token;
  else headers['x-api-key']=config.readKey;
  const response=await fetch(config.apiUrl,{method:'POST',headers,body:JSON.stringify({query,variables})});
  if(response.status===401 && session) {signOutLocal();throw Error('로그인이 만료됐습니다. 다시 로그인해 주세요.');}
  const result=await response.json();
  if(!response.ok || result.errors?.length) throw Error(result.errors?.[0]?.errorType==='BadInput' ? '닉네임과 메시지 길이를 확인해 주세요.' : '요청을 처리하지 못했습니다. 다시 시도해 주세요.');
  return result.data;
}
function draw(entry,prepend=false) {
  if(shown.has(entry.key)) return;
  shown.add(entry.key);
  const card=document.createElement('article'),name=document.createElement('strong'),time=document.createElement('time'),message=document.createElement('p');
  name.textContent=entry.nickname;time.dateTime=entry.createdAt;
  time.textContent=new Intl.DateTimeFormat('ko-KR',{dateStyle:'medium',timeStyle:'short'}).format(new Date(entry.createdAt));
  message.textContent=entry.message;card.append(name,time,message);
  if(session && entry.mine){
    const remove=document.createElement('button');remove.textContent='삭제';
    remove.onclick=async()=>{
      if(!confirm('이 글을 삭제할까요?'))return;
      remove.disabled=true;
      try{
        await api('mutation Remove($key:String!){remove(key:$key)}',{key:entry.key},true);
        card.remove();shown.delete(entry.key);
        if(!shown.size&&!cursor)status('list-status','아직 등록된 글이 없습니다.');
      }catch(error){status('form-status',error.message);remove.disabled=false;}
    };
    card.append(remove);
  }
  if(prepend)$('entries').prepend(card);else $('entries').append(card);
}
async function read(reset=false, justSaved=null) {
  if(loading && !reset)return;
  const generation=++listGeneration;
  loading=true;$('more').disabled=true;$('retry').hidden=true;
  if(reset){cursor=null;$('more').hidden=true;}
  status('list-status','글을 불러오는 중입니다.');
  try{
    const data=await api('query List($before:String){entries(before:$before){items{'+fields+'} cursor}}',{before:cursor});
    if(generation!==listGeneration)return;
    if (reset) {
      shown.clear();
      $('entries').replaceChildren();
    }
    data.entries.items.forEach(row=>draw(row));
    cursor=data.entries.cursor;$('more').hidden=!cursor;
    status('list-status',shown.size?'':'아직 등록된 글이 없습니다.');
  }catch(error){
    if(generation===listGeneration){
      if(justSaved) draw(justSaved,true);
      status('list-status',error.message);
      $('retry').hidden=false;
    }
  }
  finally{if(generation===listGeneration){loading=false;$('more').disabled=false;}}
}
$('form').onsubmit=async event=>{
  event.preventDefault();
  const nickname=$('nickname').value.trim(),message=$('message').value.trim();
  if([...nickname].length<2||[...nickname].length>20||![...message].length||[...message].length>300){
    status('form-status','닉네임은 2~20자, 메시지는 1~300자로 입력해 주세요.');return;
  }
  const submit=$('form').querySelector('[type=submit]');submit.disabled=true;
  try{
    const saved = await api('mutation Write($nickname:String!,$message:String!){write(nickname:$nickname,message:$message){'+fields+'}}',{nickname,message},true);
    $('form').reset();status('form-status','등록했습니다.');await read(true,saved.write);
  }catch(error){status('form-status',error.message);}
  finally{submit.disabled=false;}
};
$('more').onclick=()=>read();
$('retry').onclick=()=>config?read(!cursor):location.reload();
$('login').onclick=()=>login().catch(()=>status('form-status','로그인을 시작하지 못했습니다.'));
$('logout').onclick=()=>{
  signOutLocal();
  location.assign(config.authUrl+'/logout?'+new URLSearchParams({client_id:config.clientId,logout_uri:redirectUri}));
};
async function start(){
  try{
    const res=await fetch('config.json',{cache:'no-store'});
    if(!res.ok)throw Error();
    config=await res.json();
    if (config.previewGuestbookUrl && ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname)) {
      const loginLink = document.createElement('a');
      loginLink.href = config.previewGuestbookUrl;
      loginLink.className = 'button';
      loginLink.textContent = '공개 방명록 열기';
      $('login').replaceWith(loginLink);
      status('login-hint', '미리보기에서는 글을 읽을 수 있습니다. 로그인과 글쓰기는 공개 방명록에서 이용해 주세요.');
      await read(true);
      return;
    }
    try{await restoreLogin();}catch(error){signOutLocal();status('form-status',error.message);}
    updateControls();await read(true);
  }catch{status('list-status','방명록에 연결할 수 없습니다.');$('retry').hidden=false;}
}
start();
