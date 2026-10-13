"""별도 DB·계정 없이 현재 브라우저에 관심 기업을 보관하는 작은 컴포넌트."""
import json

import streamlit as st
import streamlit.components.v2 as components

from insights import DEFAULT_PROFILES, SECTORS, normalize_profiles

def watchlist_component(**kwargs):
    # AppTest와 재실행에서도 현재 런타임에 등록한 뒤 마운트한다.
    return components.component(
    'insight_watchlist_v3',
    html='<div id="watchlist-root"></div>',
    css="""#watchlist-root {font:inherit;color:var(--st-text-color);}
    .wl-row {display:flex;gap:.7rem;align-items:center;margin:.5rem 0;flex-wrap:wrap;}
    input,select,button {font:inherit;padding:.55rem;border:1px solid #b8c6ce;border-radius:7px;}
    input {width:min(100%,340px);} button {cursor:pointer;background:var(--st-secondary-background-color);}
    .wl-status {font-size:.85rem;margin:.5rem 0;color:var(--st-text-color);}""",
    js="""
    export default function({data,parentElement,setStateValue}) {
      const root=parentElement.querySelector('#watchlist-root');
      const storageKey='insight-hub-watchlist-v3';
      let profiles=data.current;
      let error='';
      try {
        const raw=localStorage.getItem(storageKey);
        if(raw) profiles=JSON.parse(raw);
      } catch(e) {error='브라우저 저장을 사용할 수 없습니다. 목록을 내려받아 보관하세요.';}
      if(!Array.isArray(profiles)) profiles=data.current;
      if(JSON.stringify(profiles)!==JSON.stringify(data.current)) setStateValue('profiles',profiles);
      root.replaceChildren();
      const status=document.createElement('p'); status.className='wl-status';
      status.textContent=error || '이 브라우저에 자동 저장됩니다. 다른 기기에서는 목록 파일로 불러오세요.';
      root.append(status);
      const save=(next)=>{
        try {localStorage.setItem(storageKey,JSON.stringify(next)); status.textContent='관심 기업을 이 브라우저에 저장했습니다.';}
        catch(e) {status.textContent='브라우저 저장이 차단돼 이번 접속에만 적용됩니다. 목록을 내려받아 보관하세요.';}
        setStateValue('profiles',next);
      };
      profiles.forEach((p,i)=>{
        const row=document.createElement('div');row.className='wl-row';
        const text=document.createElement('span');text.textContent=p.name+' · '+p.sector;
        const remove=document.createElement('button');remove.textContent='등록 해제';
        remove.setAttribute('aria-label',p.name+' 등록 해제');
        remove.onclick=()=>save(profiles.filter((_,j)=>i!==j));
        row.append(text,remove);root.append(row);
      });
      const form=document.createElement('form');form.setAttribute('aria-label','관심 기업 등록');
      const controls={};
      const addInput=(key,label,placeholder)=>{
        const row=document.createElement('div');row.className='wl-row';
        const input=document.createElement('input');input.placeholder=placeholder;
        input.setAttribute('aria-label',label);input.maxLength=key==='business'?300:150;
        controls[key]=input;row.append(input);form.append(row);
      };
      addInput('name','등록할 기업명','기업명 (예: 한국가스공사)');
      addInput('aliases','등록할 기업 약칭','약칭, 다른 이름 (쉼표 구분)');
      const sector=document.createElement('select');sector.setAttribute('aria-label','등록할 기업 사업 분야');
      data.sectors.forEach(s=>{const o=document.createElement('option');o.value=s;o.textContent=s;sector.append(o);});
      controls.sector=sector;form.append(sector);
      addInput('business','등록할 기업 주요 사업','주요 사업 (선택)');
      addInput('keywords','등록할 기업 사업 키워드','사업 키워드 (예: 가스, LNG, 저장시설)');
      const submit=document.createElement('button');submit.type='submit';submit.textContent='관심 기업 등록';form.append(submit);
      form.onsubmit=(e)=>{
        e.preventDefault();const name=controls.name.value.trim();
        if(!name || name.length>60 || !/^[가-힣A-Za-z0-9 .&()·_-]+$/.test(name)) {status.textContent='기업명은 한글·영문·숫자 등 1~60자로 입력하세요.';return;}
        if(profiles.some(p=>p.name.toLowerCase()===name.toLowerCase())) {status.textContent='이미 등록한 기업입니다.';return;}
        if(profiles.length>=10) {status.textContent='관심 기업은 최대 10개까지 등록할 수 있습니다.';return;}
        const split=(v)=>v.split(',').map(s=>s.trim()).filter(s=>s.length>=2);
        const next={name,aliases:split(controls.aliases.value),sector:sector.value,
          business:controls.business.value.trim(),keywords:split(controls.keywords.value),source_url:''};
        save([...profiles,next]);
      };root.append(form);
      const importLabel=document.createElement('label');importLabel.textContent='목록 파일 불러오기 ';
      const file=document.createElement('input');file.type='file';file.accept='.json,application/json';
      file.setAttribute('aria-label','관심 기업 목록 파일 불러오기');
      file.onchange=async()=>{
        if(!file.files[0] || file.files[0].size>50000) {status.textContent='50KB 이하의 목록 파일을 선택하세요.';return;}
        try {
          const value=JSON.parse(await file.files[0].text());
          if(!Array.isArray(value) || value.length>10 || value.some(p=>!p || typeof p.name!=='string' || !data.sectors.includes(p.sector))) throw Error();
          save(value);
        } catch(e) {status.textContent='올바른 관심 기업 목록 JSON 파일을 선택하세요.';}
      };importLabel.append(file);root.append(importLabel);
    }""")(**kwargs)


def render_watchlist():
    st.session_state.setdefault('profiles', normalize_profiles(DEFAULT_PROFILES))
    result = watchlist_component(data={'current': st.session_state['profiles'], 'sectors': SECTORS},
                                default={'profiles': st.session_state['profiles']},
                                on_profiles_change=lambda: None, key='watchlist_store')
    try:
        profiles = normalize_profiles(result.profiles)
        if profiles != st.session_state['profiles']:
            st.session_state['profiles'] = profiles
    except (ValueError, TypeError):
        st.warning('저장된 목록 형식이 올바르지 않습니다. 등록 화면에서 목록을 다시 확인하세요.')
    return st.session_state['profiles']


def watchlist_download(profiles):
    st.download_button('관심 기업 목록 내려받기',
                       json.dumps(profiles, ensure_ascii=False, indent=2), 'my_companies.json', 'application/json')
