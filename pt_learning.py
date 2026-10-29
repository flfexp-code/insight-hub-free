"""검증된 PT 자료를 표시한다. 생성 API나 답변 자동 전송 기능은 없다."""
import json
import math
from news_core import format_kst


def _plain(value):
    # Streamlit의 Markdown이 두 개 이상의 기간 표기 ~를 취소선으로 읽지 않게 한다.
    return value.replace('~', r'\~')


def validate_pt(pt, source_index):
    def text(item, key, low=1, high=3000):
        value = item.get(key) if isinstance(item, dict) else None
        if not isinstance(value, str) or not low <= len(value.strip()) <= high:
            raise ValueError('PT 항목 오류: ' + key)

    def texts(item, key, low=1, high=12):
        values = item.get(key)
        if not isinstance(values, list) or not low <= len(values) <= high:
            raise ValueError('PT 목록 오류: ' + key)
        for value in values:
            text({'value': value}, 'value', high=1500)

    if not isinstance(pt, dict) or pt.get('version') != 1:
        raise ValueError('PT 형식 오류')
    for key in ('role', 'task', 'conditions'):
        text(pt, key)
    for key in ('preparation_minutes', 'presentation_minutes'):
        number = pt.get(key)
        if type(number) is not int or not 1 <= number <= 120:
            raise ValueError('PT 시간 오류')
    texts(pt, 'deliverables', high=8)
    materials = pt.get('materials')
    if not isinstance(materials, list) or not 3 <= len(materials) <= 7:
        raise ValueError('PT 자료는 3~7개 필요합니다.')
    seen, chart_count = set(), 0
    for material in materials:
        for key in ('id', 'heading', 'body', 'provenance'):
            text(material, key, high=4000 if key == 'body' else 200)
        if material['id'] in seen:
            raise ValueError('PT 자료 식별자 중복')
        seen.add(material['id'])
        refs = material.get('source_ids')
        if not isinstance(refs, list) or not refs or any(not isinstance(r, str) or r not in source_index for r in refs):
            raise ValueError('PT 자료 출처 오류')
        chart = material.get('chart')
        if chart is None:
            continue
        chart_count += 1
        if not isinstance(chart, dict) or chart.get('kind') not in ('bar', 'table'):
            raise ValueError('PT 차트 형식 오류')
        for key in ('title', 'unit', 'period', 'note'):
            text(chart, key, high=1200)
        columns, rows = chart.get('columns'), chart.get('rows')
        if not isinstance(columns, list) or not 2 <= len(columns) <= 8 or any(not isinstance(c, str) or not 1 <= len(c) <= 120 for c in columns) or len(set(columns)) != len(columns):
            raise ValueError('PT 차트 열 오류')
        if not isinstance(rows, list) or not 1 <= len(rows) <= 100:
            raise ValueError('PT 차트 행 오류')
        for row in rows:
            if not isinstance(row, list) or len(row) != len(columns):
                raise ValueError('PT 차트 행 길이 오류')
            for cell in row:
                if isinstance(cell, str) and len(cell) <= 400:
                    continue
                if type(cell) in (int, float) and math.isfinite(cell) and abs(cell) <= 1e15:
                    continue
                raise ValueError('PT 차트 값 오류')
        if chart['kind'] == 'bar':
            if any(not isinstance(r[0], str) or any(type(n) not in (int, float) for n in r[1:]) for r in rows):
                raise ValueError('PT 막대그래프 숫자 오류')
            if len({r[0] for r in rows}) != len(rows):
                raise ValueError('PT 차트 범주 중복')
    if not chart_count:
        raise ValueError('PT에는 그래프 또는 도표가 필요합니다.')
    guide = pt.get('answer_guide')
    for key in ('reasoning', 'sample_script', 'script_notes'):
        text(guide, key, low=800 if key == 'sample_script' else 30, high=6000)
    texts(guide, 'contrasts', high=8)
    texts(guide, 'approaches', low=2, high=5)
    texts(guide, 'rubric', low=3, high=8)
    texts(guide, 'followups', low=2, high=6)
    return pt


def feedback_packet(value):
    """문제·수치·출처를 전부 담되 예시 답안은 포함하지 않는다."""
    pt = value['pt']
    validate_pt(pt, {s['id']: s for s in value['sources']})
    lines = ['[PT 문제] ' + value['topic'], '자료 작성: ' + value['updated_at'],
             '역할: ' + pt['role'], pt['task'], '조건: ' + pt['conditions'],
             f"준비 {pt['preparation_minutes']}분 / 발표 {pt['presentation_minutes']}분",
             '발표에 포함할 내용:\n' + '\n'.join(pt['deliverables'])]
    for material in pt['materials']:
        lines += [f"\n[{material['id']}] {material['heading']} ({material['provenance']})",
                  material['body'], '출처: ' + ', '.join(material['source_ids'])]
        if material.get('chart'):
            c = material['chart']
            lines += [c['title'], '단위: ' + c['unit'], '기간·대상: ' + c['period'],
                      json.dumps({'columns': c['columns'], 'rows': c['rows']}, ensure_ascii=False),
                      '주석: ' + c['note']]
    for source in value['sources']:
        lines += [f"\n{source['id']} | {source['publisher']} | {source['published']} | {source['title']}",
                  source['url'], '확인: ' + source['supports'], '한계: ' + source['limits']]
    lines += ['\n[피드백 요청]',
              '내 주장을 먼저 정확히 정리하고 근거→판단→대안→실행의 연결을 평가해주세요. '
              '내 결론과 달라도 근거·조건이 성립하면 인정하고 억지로 반반 절충하지 마세요. '
              '상반된 자료를 다뤘는지, 단순한 대상·시점 차이를 모순으로 오해하지 않았는지 확인해주세요. '
              '중요한 사실 오류와 비약은 구분해 고치되 제공되지 않은 세부 정보를 모른다고 감점하지 마세요. '
              '가정의 합리성과 결론 변경 조건도 평가하세요. 답변을 받기 전에 예시 발표문을 먼저 쓰지 마세요. '
              '답변 뒤에는 핵심 피드백 후 꼬리질문을 하나만 묻고 기다리세요. '
              '피드백 종료 뒤 내 논리를 유지한 수정 개요를 주세요.']
    return '\n'.join(lines)


def answer_editor(value, packet):
    import streamlit.components.v2 as components
    return components.component('insight_pt_answer_v1',
        html='<section id="pt-answer"></section>',
        css='''#pt-answer{font:16px/1.7 system-ui,sans-serif;color:var(--st-text-color)}
        textarea{box-sizing:border-box;width:100%;min-height:220px;padding:14px;border:1px solid #9aae80;border-radius:12px;font:inherit;color:inherit;background:#fffffa}
        button{font:inherit;padding:10px 16px;margin:10px 8px 8px 0;border:1px solid #76924f;border-radius:10px;background:#eaf1dd;color:#29352c;cursor:pointer}
        .hint{font-size:.88rem;color:#58674e} .packet{min-height:280px}''',
        js=r'''
        export default function({data,parentElement}) {
          const root=parentElement.querySelector('#pt-answer');root.replaceChildren();
          const el=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};
          const label=el('label','내 발표문·메모'),answer=el('textarea');
          answer.id='pt-draft';answer.maxLength=15000;answer.placeholder='결론과 근거, 실행 방법, 반론에 대한 생각을 적으세요.';
          label.htmlFor=answer.id;root.append(label,answer);
          const key='insight-pt-answer-v1:'+data.id,status=el('p');status.setAttribute('role','status');status.setAttribute('aria-live','polite');
          let storageOk=true;try{answer.value=localStorage.getItem(key)||'';}catch{storageOk=false;}
          const hint=el('p','답변은 이 브라우저에만 보관됩니다. 복사 버튼은 외부로 자동 전송하지 않습니다.');hint.className='hint';root.append(hint);
          answer.oninput=()=>{try{localStorage.setItem(key,answer.value);}catch{storageOk=false;status.textContent='답변을 저장할 수 없습니다. 복사하거나 내려받아 보관하세요.';}};
          const makePacket=()=>data.packet+'\n\n[내 답변]\n'+answer.value;
          const copy=el('button','GPT에게 자료주기 · 문제+내 답변 복사');copy.type='button';
          const manual=el('details'),summary=el('summary','복사가 안 되면 전체 텍스트 열기'),fallback=el('textarea');fallback.className='packet';fallback.readOnly=true;fallback.setAttribute('aria-label','GPT 전달용 전체 자료');manual.append(summary,fallback);
          manual.ontoggle=()=>{if(manual.open)fallback.value=makePacket();};
          copy.onclick=async()=>{const text=makePacket();try{await navigator.clipboard.writeText(text);status.textContent='복사했습니다. ChatGPT 대화에 붙여 넣으세요.';}catch{manual.open=true;fallback.value=text;fallback.focus();fallback.select();status.textContent='브라우저 복사 권한을 사용할 수 없어 전체 텍스트를 선택했습니다. 직접 복사하세요.';}};
          const save=el('button','문제+내 답변 TXT 내려받기');save.type='button';save.onclick=()=>{const blob=new Blob([makePacket()],{type:'text/plain;charset=utf-8'}),url=URL.createObjectURL(blob),a=el('a');a.href=url;a.download='pt-'+data.id+'.txt';root.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);};
          root.append(copy,save,status,manual);if(!storageOk)status.textContent='이 브라우저에서는 답변 저장을 사용할 수 없습니다.';
        }''')(data={'id': value['id'], 'packet': packet}, key='pt_answer_'+value['id'])


def render_pt(value):
    import streamlit as st
    from reader_ui import reading_items
    from pt_pages import practice_pages, guide_pages
    from pt_viewer import page_viewer
    from pt_pdf import export_pdf
    pt = value['pt']
    st.caption('ChatGPT 직접 조사 · PT 연습 · ' + format_kst(value['updated_at']) + ' KST')
    st.markdown('### ' + value['topic'])
    serialized=json.dumps(value,ensure_ascii=False)
    c1,c2=st.columns(2)
    c1.download_button('문제·자료집 PDF 저장',data=lambda:export_pdf(serialized,'practice'),
                       file_name=value['id']+'-problem.pdf',mime='application/pdf',on_click='ignore',key='pdf_problem_'+value['id'])
    c2.download_button('해설·예시 발표 PDF 저장',data=lambda:export_pdf(serialized,'guide'),
                       file_name=value['id']+'-guide.pdf',mime='application/pdf',on_click='ignore',key='pdf_guide_'+value['id'])
    page_viewer(value,practice_pages(value),'pt_material_pages')
    st.markdown('#### 내 답변과 피드백')
    answer_editor(value,feedback_packet(value))
    with st.expander('해설·예시 발표 스크립트 보기 · 답변 후 열기',expanded=False):
        page_viewer(value,guide_pages(value),'pt_guide_pages')
    with st.expander('출처와 확인 범위'):
        for s in value['sources']:
            st.markdown('**'+s['publisher']+' · '+s['title']+'**')
            st.caption(s['published']+' · '+s['checked'])
            st.write('확인: '+s['supports'])
            st.caption('한계: '+s['limits'])
            st.link_button('원문 보기',s['url'])
    details=[pt['task'],pt['conditions']]
    for m in pt['materials']:
        details.append(m['heading']+'\n'+m['body'])
        if m.get('chart'):details.append(json.dumps(m['chart'],ensure_ascii=False))
    details.append('예시 발표 스크립트\n'+pt['answer_guide']['sample_script'])
    reading_items([{'id':'pt:'+value['id'],'kind':'study','group':'PT 연습','title':value['topic'],
                   'date':format_kst(value['updated_at']),'summary':pt['task'],'details':details,'url':''}],'pt_bookmark')
