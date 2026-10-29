"""화면과 PDF에서 함께 사용하는 PT 페이지 구성."""
import copy
import re


def split_text(text, limit=820):
    """문단/문장 경계를 우선하여 나누되 원문 문자를 모두 보존한다."""
    if not text:
        return ['']
    parts=[]
    while len(text)>limit:
        cut=text.rfind('\n\n', 0, limit)
        if cut < limit//3:
            matches=list(re.finditer(r'[.!?。]\s+', text[:limit]))
            cut=matches[-1].end() if matches else limit
        else:
            cut+=2
        if cut<=0:
            cut=limit
        parts.append(text[:cut]);text=text[cut:]
    if text:
        parts.append(text)
    return parts


def practice_pages(value):
    pt=value['pt']
    pages=[{'label':'문제','heading':'PT 문제','body':pt['task'],
            'blocks':[{'heading':'역할·조건','body':pt['role']+'\n\n'+pt['conditions']},
                      {'heading':'발표에 포함할 내용','body':'\n'.join('• '+s for s in pt['deliverables'])}],
            'meta':f"준비 {pt['preparation_minutes']}분 · 발표 {pt['presentation_minutes']}분"}]
    sources={s['id']:s for s in value['sources']}
    for material in pt['materials']:
        bodies=split_text(material['body'],650 if material.get('chart') else 1100)
        chart=material.get('chart')
        refs=' · '.join(sources[s]['publisher'] for s in material['source_ids'])
        for i,body in enumerate(bodies):
            pages.append({'label':material['id']+(f'-{i+1}' if len(bodies)>1 else ''),
                          'heading':material['heading']+(' · 계속' if i else ''),
                          'body':body,'meta':material['provenance'],'source':'근거: '+refs})
        if chart:
            # 그래프와 설명이 각각 너무 길 때 분리한다. 짧은 설명은 그래프와 같은 페이지에 둔다.
            cap=max(2, min(8, 12//max(1,len(chart['columns'])-1))) if chart['kind']=='bar' else 5
            for start in range(0,len(chart['rows']),cap):
                c=copy.deepcopy(chart);c['rows']=chart['rows'][start:start+cap]
                if start==0 and len(bodies)==1 and len(bodies[0])<=420:
                    target=pages[-1]
                else:
                    target={'label':material['id']+f'·표{start//cap+1}','heading':material['heading'],
                            'body':'','meta':material['provenance'],'source':'근거: '+refs};pages.append(target)
                target['chart']=c
                if len(chart['rows'])>cap:
                    target['meta']+=f" · 전체 {len(chart['rows'])}행 중 {start+1}~{start+len(c['rows'])}행"
    grouped=[]
    for page in pages:
        previous=grouped[-1] if grouped else None
        if (previous and '기사' in page.get('meta','') and '기사' in previous.get('meta','')
                and not previous.get('chart') and not page.get('chart') and not previous.get('blocks')
                and len(previous.get('body',''))+len(page.get('body',''))<=720):
            grouped[-1]={'label':previous['label']+'·'+page['label'],'heading':'기사 발췌 비교','body':'',
                         'meta':'기사 일부 직접 발췌','blocks':[{'heading':previous['heading'],'body':previous['body']+'\n'+previous.get('source','')},
                         {'heading':page['heading'],'body':page['body']+'\n'+page.get('source','')}]}
        else:
            grouped.append(page)
    return grouped


def guide_pages(value):
    g=value['pt']['answer_guide'];pages=[]
    sections=[('해설','자료를 연결하는 방법',g['reasoning']),
              ('자료 비교','다른 관점·범위 차이','\n\n'.join('• '+s for s in g['contrasts'])),
              ('대안','다른 결론이 성립하는 조건','\n\n'.join('• '+s for s in g['approaches'])),
              ('예시 발표','예시 발표 스크립트',g['sample_script']),
              ('피드백','피드백에서 확인할 내용','\n\n'.join('• '+s for s in g['rubric'])),
              ('질문','꼬리질문 예시','\n\n'.join('• '+s for s in g['followups']))]
    for label,heading,body in sections:
        chunks=split_text(body,900)
        for i,chunk in enumerate(chunks):
            pages.append({'label':label+(f' {i+1}' if len(chunks)>1 else ''),
                          'heading':heading+(f' ({i+1}/{len(chunks)})' if len(chunks)>1 else ''),
                          'body':chunk,'meta':g['script_notes'] if label=='예시 발표' else '해설 · 답변 후 확인'})
    return pages
