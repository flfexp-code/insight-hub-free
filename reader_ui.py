"""브라우저 안에서만 저장·읽음·메모를 관리한다. AI나 GitHub로 보내지 않는다."""
import streamlit.components.v2 as components

from news_core import safe_link


def reading_items(items, key, library=False):
    safe = []
    for item in items:
        safe.append({**item, 'url': safe_link(item.get('url', ''))})
    return components.component('insight_reading_v4',
        html='<div id="reading-root"></div>',
        css='''#reading-root{font:16px/1.65 system-ui,sans-serif;color:var(--st-text-color)}
        .read-card{border:1px solid #DDE5D1;border-left:4px solid #8BA667;border-radius:16px;padding:22px;margin:0 0 18px;background:#FFFFFA}
        .read-title{font-size:1.14rem;line-height:1.6;margin:.4rem 0 .8rem;font-weight:700}
        .read-meta{color:#576D3D;font-size:.88rem}.read-card[data-group="금융"]{border-left-color:#6A87A1}.read-card[data-group="경제"]{border-left-color:#A38B5E}.read-card[data-group="시사"]{border-left-color:#8A7D95}.read-reason{background:#EDF4E1;border-radius:8px;padding:10px 14px;color:#485F31}
        .read-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px} button,a{font:inherit}
        button{padding:7px 12px;border:1px solid #8aa5a8;background:var(--st-secondary-background-color);color:inherit;border-radius:8px;cursor:pointer}
        a{color:#4C6C2F;text-decoration:underline} textarea{box-sizing:border-box;width:100%;font:inherit;min-height:85px;background:var(--st-background-color);color:inherit;border:1px solid #9eafb4;border-radius:8px;padding:10px}
        .read-empty{padding:18px;border:1px dashed #9eafb4;border-radius:12px}.read-status{font-size:.85rem}
        p{margin:.5rem 0} summary{cursor:pointer} @media(max-width:600px){.read-card{padding:15px}.read-title{font-size:1.08rem}}''',
        js=r'''
        export default function({data,parentElement}) {
          const root=parentElement.querySelector('#reading-root'), storageKey='insight-hub-reading-v4';
          let warning='', store={saved:{},read:{}};
          const validUrl=(value)=>{try{const u=new URL(value);return ['http:','https:'].includes(u.protocol)&&!u.username?u.href:'';}catch{return '';}};
          const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
          const load=()=>{try{const v=JSON.parse(localStorage.getItem(storageKey)||'{}');store={saved:v.saved||{},read:v.read||{}};}catch{warning='이 브라우저에서 저장을 사용할 수 없습니다. 내보내기로 보관하세요.';}};
          const persist=()=>{try{localStorage.setItem(storageKey,JSON.stringify(store));}catch{warning='저장 공간이 부족합니다. 내보내기로 보관하세요.';}window.dispatchEvent(new Event('insight-reading-changed'));};
          const button=(label,action)=>{const b=node('button',label);b.type='button';b.onclick=action;return b;};
          const exportData=()=>{const blob=new Blob([JSON.stringify(store,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob),a=node('a');a.href=url;a.download='insight-reading-backup.json';a.click();URL.revokeObjectURL(url);};
          const draw=()=>{
            root.replaceChildren();
            const status=node('p',warning||'저장·읽음·내 메모는 이 브라우저에만 보관됩니다.','read-status');root.append(status);
            let rows=data.items;
            if(data.library){
              root.append(button('저장자료 내보내기',exportData));
              const label=node('label',' 백업 불러오기 '),file=document.createElement('input');file.type='file';file.accept='.json,application/json';file.setAttribute('aria-label','저장자료 백업 불러오기');
              file.onchange=async()=>{try{
                if(!file.files[0]||file.files[0].size>2000000)throw Error();
                const raw=JSON.parse(await file.files[0].text());if(!raw.saved||typeof raw.saved!=='object'||Array.isArray(raw.saved)||Object.keys(raw.saved).length>100)throw Error();
                const cleaned={};for(const [id,v] of Object.entries(raw.saved)){
                  if(!/^[A-Za-z0-9_.:-]{1,100}$/.test(id)||['__proto__','constructor','prototype'].includes(id))throw Error();
                  if(!v||typeof v.title!=='string'||v.title.length>250||typeof v.summary!=='string'||v.summary.length>1500||!['news','study'].includes(v.kind))throw Error();
                  cleaned[id]={...v,id,url:validUrl(v.url),note:typeof v.note==='string'?v.note.slice(0,1000):'',
                    details:Array.isArray(v.details)?v.details.filter(x=>typeof x==='string').slice(0,40).map(x=>x.slice(0,1200)):[],
                    savedAt:Number(v.savedAt)||Date.now()};
                }
                store={saved:cleaned,read:{}};persist();draw();
              }catch{status.textContent='올바른 2MB 이하 백업 파일을 선택하세요.';}};
              label.append(file);root.append(label);
              rows=Object.values(store.saved).sort((a,b)=>Number(Boolean(store.read[a.id]))-Number(Boolean(store.read[b.id]))||((store.read[a.id]||a.savedAt)-(store.read[b.id]||b.savedAt)));
              root.append(node('p','안 읽은 자료를 먼저, 읽은 자료는 마지막으로 읽은 날이 오래된 순서로 보여줍니다.'));
            }
            if(!rows.length)root.append(node('p',data.library?'뉴스나 오늘의 공부에서 저장을 누르면 여기에 모입니다.':'현재 읽을 새 자료가 없습니다.','read-empty'));
            rows.forEach(item=>{
              const card=node('article',undefined,'read-card'),read=store.read[item.id];
              card.dataset.group=item.group||'';
              card.append(node('div',(item.group||'오늘의 공부')+' · '+(item.date||'')+(read?' · 읽음':''),'read-meta'));
              card.append(node('h3',item.title,'read-title'));
              if(item.status)card.append(node('p',item.status,'read-meta'));
              card.append(node('p',item.summary));
              if(item.reason)card.append(node('p',item.reason,'read-reason'));
              if(item.details?.length){const details=node('details'),summary=node('summary','논리·근거 다시 보기');details.append(summary);item.details.forEach(x=>details.append(node('p',x)));card.append(details);}
              const actions=node('div',undefined,'read-actions');
              if(validUrl(item.url)){const a=node('a','원문 보기');a.href=validUrl(item.url);a.target='_blank';a.rel='noopener noreferrer';actions.append(a);}
              actions.append(button(store.saved[item.id]?'저장 해제':'저장',()=>{
                if(store.saved[item.id])delete store.saved[item.id];
                else if(Object.keys(store.saved).length>=100){status.textContent='최대 100개까지 저장할 수 있습니다. 일부 자료를 내보내거나 해제하세요.';return;}
                else store.saved[item.id]={...item,savedAt:Date.now(),note:''};
                persist();draw();
              }));
              actions.append(button(read?'읽음 취소':'읽음',()=>{if(read)delete store.read[item.id];else store.read[item.id]=Date.now();persist();draw();}));
              card.append(actions);
              if(store.saved[item.id]){
                const details=node('details'),summary=node('summary','내 생각 한 줄');details.append(summary);
                const note=document.createElement('textarea');note.maxLength=1000;note.setAttribute('aria-label',item.title+' 메모');note.value=store.saved[item.id].note||'';
                note.onchange=()=>{if(store.saved[item.id]){store.saved[item.id].note=note.value;persist();}};
                details.append(note);card.append(details);
              }
              root.append(card);
            });
          };
          load();draw();
          const refresh=()=>{if(root.isConnected){load();draw();}};
          window.addEventListener('insight-reading-changed',refresh);
          return ()=>window.removeEventListener('insight-reading-changed',refresh);
        }''')(
            data={'items': safe, 'library': library}, key=key)
