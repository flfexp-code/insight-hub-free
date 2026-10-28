"""하루 한 번 생성·저장하는 짧은 뉴스·배경·논리 공부. 기관 자동 분석과 분리한다."""
import json
import re
from datetime import datetime

from insights import REPORTS, news_quality, signal_tags
from news_core import UTC, excluded_personnel, parse_time

CONCEPT_PAIRS = {
    'cost_price': ('비용', '생산·공급 과정에서 쓰는 자원과 지출.', '가격·요금', '상품·서비스를 제공하고 받는 대가.',
                   '비용 증가와 요금 인상은 별개다. 요금 조정 규칙과 비용 회수 시차에 따라 이익·현금흐름 영향이 달라진다.'),
    'policy_market_rate': ('기준금리', '중앙은행이 통화정책을 운용할 때 기준으로 삼는 금리.', '대출금리', '금융기관이 대출에 적용하는 금리.',
                           '대출금리에는 조달비용·신용위험·가산금리 등이 반영되므로 기준금리와 같은 폭·시점에 움직이지 않을 수 있다.'),
    'capacity_generation': ('설비용량', '발전설비가 낼 수 있는 전력의 규모. 보통 kW·MW 등으로 표시한다.', '발전량', '일정 시간 동안 생산한 전기에너지. 보통 kWh·MWh 등으로 표시한다.',
                            '설비용량이 늘어도 가동시간·연료·기상·전력망 제약에 따라 발전량이 같은 비율로 늘지는 않는다.'),
    'announcement_execution': ('정책 발표', '정부·기관이 추진 방향이나 계획을 공개한 단계.', '정책 시행', '필요한 절차를 거쳐 대상과 조건에 맞춰 정책을 적용하는 단계.',
                               '발표만으로 시행일·예산·적용 대상이 확정되는 것은 아니다. 법령·예산·후속 절차를 따로 확인한다.'),
    'liquidity_profit': ('유동성', '만기가 돌아온 지급 의무를 감당할 현금·자금조달 여력.', '수익성', '매출과 비용을 비교해 이익을 내는 정도.',
                        '차입 한도를 늘리면 지급 여력이 나아질 수 있지만 수입·비용 조건까지 바뀌지는 않는다. 이익과 현금흐름도 인식·지급 시차 때문에 다를 수 있다.'),
    'stock_flow': ('잔액', '특정 시점에 남아 있는 자산·부채 등의 규모.', '기간 중 증감', '일정 기간에 새로 발생하거나 줄어든 금액.',
                   '현재 부채 잔액과 올해 적자는 다른 수치다. 올해 흑자가 나더라도 과거에 쌓인 부채가 모두 없어지는 것은 아니다.'),
}


def learning_sources(brief, articles):
    news, reports, opinions = [], [], []
    topics = {topic for a in brief for topic in signal_tags(a['title'])}
    for i, article in enumerate(brief[:5], 1):
        evidence = article.get('evidence', {})
        news.append({'id': f'N{i}', 'article_id': article['id'], 'title': article['title'],
                     'published': article.get('published', ''), 'url': article.get('link', ''),
                     'source': article.get('source', ''), 'kind': '보도',
                     'status': evidence.get('status', '제목만 확인'), 'excerpt': evidence.get('excerpt', '')[:600],
                     'context': evidence.get('context', '')[:1800],
                     'mou_reason': article.get('mou_context', {}).get('reason', '')})
    for report in REPORTS:
        related_ids = [n['id'] for n in news if set(signal_tags(n['title'] + ' ' + n['context'])).intersection(report['topics'])]
        if report.get('reviewed') and related_ids:
            reports.append({'id': report['id'], 'kind': '공식 자료의 검토 요지',
                            'related_news_ids': related_ids,
                            'cautions': report.get('cautions', report['scope']),
                            **{k: report[k] for k in ('institution', 'title', 'published', 'url', 'summary', 'scope')}})
    now = datetime.now(UTC)
    for article in articles:
        date = parse_time(article.get('published', ''))
        evidence = article.get('evidence', {})
        if (date and 0 <= (now-date).total_seconds() <= 3*86400
                and not excluded_personnel(article['title']) and news_quality(article['title'], article)['include']
                and re.search(r'사설|칼럼|기고|오피니언', article['title'])
                and evidence.get('status') in ('본문 일부 확인', '공개 요약문 확인')
                and topics.intersection(signal_tags(article['title']))):
            opinions.append({'id': f'O{len(opinions)+1}', 'kind': '필자의 의견', 'title': article['title'],
                             'published': article.get('published', ''), 'url': article.get('link', ''),
                             'source': article.get('source', ''), 'status': evidence['status'],
                             'excerpt': evidence['excerpt'][:600], 'context': evidence.get('context', '')[:1800]})
            if len(opinions) == 2:
                break
    return {'news': news, 'reports': reports[:6], 'opinions': opinions}


def eligible_news(packet):
    return [n['id'] for n in packet['news'] if len(n.get('context', '')) >= 300
            and n.get('status') in ('본문 일부 확인', '공개 요약문 확인')
            and any(n['id'] in r.get('related_news_ids', []) for r in packet['reports'])]


def depth_schema(packet):
    def text(description='한글 문장으로 작성하며 입력에 없는 현재 사실은 만들지 않습니다.'):
        return {'type': 'STRING', 'description': description}
    refs = [s['id'] for group in packet.values() for s in group]
    def references(): return {'type': 'ARRAY', 'minItems': 1, 'maxItems': 4,
                              'items': {'type': 'STRING', 'enum': refs}}
    def obj(properties): return {'type': 'OBJECT', 'properties': properties, 'required': list(properties)}
    def rows(properties, minimum, maximum):
        return {'type': 'ARRAY', 'minItems': minimum, 'maxItems': maximum, 'items': obj(properties)}
    return obj({
        'event': obj({**{key: text() for key in ('who', 'when', 'where', 'what', 'why_known', 'how_known')}, 'source_ids': references()}),
        'why_now': obj({'explanation': text('왜 지금 부각됐는지 근거로 설명하는 120~300자 문단.'), 'source_ids': references()}),
        'foundations': rows({'concept_id': {'type': 'STRING', 'enum': list(CONCEPT_PAIRS)},
                             'term': text(), 'explanation': text('앱 개념 목록의 정의와 차이를 유지.'),
                             'application': text('개념을 이 기사에 적용하는 방법을 60~160자로 설명.')}, 3, 3),
        'mechanism': rows({'change': text('무엇이 변하는지 15~80자로 설명.'),
                          'because': text('다음 단계가 생기는 중간 경로를 100~220자로 구체적으로 설명. 화살표만 나열하거나 변화 내용을 반복하지 않음.'),
                          'condition': text('경로의 성립 조건을 40~120자로 설명.'), 'source_ids': references()}, 3, 4),
        'connections': rows({'kind': {'type': 'STRING', 'enum': ['산업', '사회', '거시경제']},
                             'target': text('연결할 다른 산업·사회문제·경제 변수의 이름.'),
                             'pathway': text('반드시 130~260자의 완결된 2~3문장. 출발 변화에서 중간 비용·수요·자금 경로를 거쳐 대상의 영향으로 넘어가는 이유를 설명. 짧은 화살표·단어 나열 금지.'),
                             'condition': text('언제 이 연결이 성립하는지 40~120자.'),
                             'limit': text('반대 효과 또는 아직 모르는 점을 40~120자로 설명.'),
                             'source_ids': references()}, 2, 3),
        'source_contributions': rows({'source_id': {'type': 'STRING', 'enum': refs}, 'supports': text(), 'does_not_prove': text()}, 2, 5),
        'thinking_questions': rows({'question': text(), 'hint': text()}, 2, 3),
    })


def learning_schema(packet):
    def text(): return {'type': 'STRING'}
    refs = [s['id'] for group in packet.values() for s in group]
    study = {key: text() for key in ('topic', 'background', 'term_a', 'meaning_a', 'term_b', 'meaning_b',
                                    'difference', 'claim', 'counter', 'condition', 'question')}
    study['concept_pair'] = {'type': 'STRING', 'enum': list(CONCEPT_PAIRS)}
    study['logic_chain'] = {'type': 'ARRAY', 'minItems': 3, 'maxItems': 3, 'items': text()}
    study['check_metrics'] = {'type': 'ARRAY', 'minItems': 1, 'maxItems': 3, 'items': text()}
    study['news_ids'] = {'type': 'ARRAY', 'minItems': 1, 'maxItems': 2, 'items': {'type': 'STRING',
        'enum': [s['id'] for s in packet['news'] if s['excerpt']]}}
    study['report_ids'] = {'type': 'ARRAY', 'minItems': 1, 'maxItems': 2, 'items': {'type': 'STRING',
        'enum': [s['id'] for s in packet['reports']]}}
    opinion_ids = [s['id'] for s in packet['opinions']]
    study['opinion_views'] = {'type': 'ARRAY', 'maxItems': 2, 'items': {'type': 'OBJECT', 'properties': {
        'source_id': {'type': 'STRING', 'enum': opinion_ids or ['사용안함']}, 'view': text()},
        'required': ['source_id', 'view']}}
    study['depth'] = depth_schema(packet)
    study['news_ids']['items']['enum'] = eligible_news(packet)
    return {'type': 'OBJECT', 'properties': {
        'briefs': {'type': 'ARRAY', 'minItems': len(packet['news']), 'maxItems': len(packet['news']),
                   'items': {'type': 'OBJECT', 'properties': {
                       'news_id': {'type': 'STRING', 'enum': [s['id'] for s in packet['news']]},
                       'summary': text(), 'why': text()}, 'required': ['news_id', 'summary', 'why']}},
        'study': {'type': 'OBJECT', 'properties': study, 'required': list(study)}}, 'required': ['briefs', 'study']}


def validate_learning(value, packet):
    if not isinstance(value, dict) or not isinstance(value.get('briefs'), list) or not isinstance(value.get('study'), dict):
        raise ValueError('학습 결과 형식 오류')
    def sentence(item, key, maximum=300):
        if not isinstance(item.get(key), str) or not 1 <= len(item[key]) <= maximum:
            raise ValueError('학습 문장 누락 또는 분량 초과')
    ids = {s['id'] for s in packet['news']}
    news_index = {s['id']: s for s in packet['news']}
    seen = set()
    for card in value['briefs']:
        if not isinstance(card, dict) or card.get('news_id') not in ids or card['news_id'] in seen:
            raise ValueError('기사 출처 중복·불일치')
        source = news_index[card['news_id']]
        if source.get('status') == '제목만 확인':
            card['summary'] = source['title']
            card['why'] = '제목 기준으로 선별한 현안입니다.'
        seen.add(card['news_id']); sentence(card, 'summary', 300); sentence(card, 'why', 180)
    if seen != ids:
        raise ValueError('핵심 기사 누락')
    study = value['study']
    if study.get('concept_pair') not in CONCEPT_PAIRS:
        raise ValueError('확인하지 않은 개념 비교는 표시하지 않습니다.')
    pair = CONCEPT_PAIRS[study['concept_pair']]
    for key, content in zip(('term_a', 'meaning_a', 'term_b', 'meaning_b', 'difference'), pair):
        study[key] = content
    for key in ('topic', 'background', 'term_a', 'meaning_a', 'term_b', 'meaning_b', 'difference',
                'claim', 'counter', 'condition', 'question'):
        sentence(study, key)
    for key, maximum in (('logic_chain', 3), ('check_metrics', 3)):
        if (not isinstance(study.get(key), list) or not 1 <= len(study[key]) <= maximum
                or any(not isinstance(x, str) or not 1 <= len(x) <= 120 for x in study[key])):
            raise ValueError('학습 논리·지표 분량 오류')
    if len(study['logic_chain']) != 3:
        raise ValueError('논리는 세 단계로 제한합니다.')
    source_index = {s['id']: s for group in packet.values() for s in group}
    article_refs, report_refs = study.get('news_ids'), study.get('report_ids')
    if not isinstance(article_refs, list) or not isinstance(report_refs, list) or not article_refs or not report_refs:
        raise ValueError('본문 기사와 공식 자료를 각각 인용해야 합니다.')
    if any(not isinstance(ref, str) or ref not in ids or not source_index.get(ref, {}).get('excerpt') for ref in article_refs):
        raise ValueError('본문·요약 근거와 공식 자료 요지를 함께 인용해야 합니다.')
    if any(not isinstance(ref, str) or ref not in {r['id'] for r in packet['reports']} for ref in report_refs):
        raise ValueError('입력에 없는 학습 출처 차단')
    refs = study.get('source_ids', [*article_refs, *report_refs])
    if not isinstance(refs, list) or not refs or any(not isinstance(ref, str) or ref not in source_index for ref in refs):
        raise ValueError('입력에 없는 학습 출처 차단')
    if not any(ref in ids and source_index[ref]['excerpt'] for ref in refs) or not any(ref in {r['id'] for r in packet['reports']} for ref in refs):
        raise ValueError('본문·요약 근거와 공식 자료 요지를 함께 인용해야 합니다.')
    study['source_ids'] = list(dict.fromkeys([*article_refs, *report_refs]))
    opinion_ids = {s['id'] for s in packet['opinions']}
    views = study.get('opinion_views')
    if not isinstance(views, list) or len(views) > 2:
        raise ValueError('오피니언 형식 오류')
    for view in views:
        if not isinstance(view, dict) or view.get('source_id') not in opinion_ids:
            raise ValueError('확인하지 않은 오피니언 인용 차단')
        sentence(view, 'view')
    if 'depth' in study:
        validate_depth(study, packet)
    return value


def validate_depth(study, packet):
    """출처가 있다는 사실과 그 출처가 해당 주제를 다룬다는 조건을 함께 확인한다."""
    depth = study.get('depth')
    if not isinstance(depth, dict):
        raise ValueError('학습의 배경·작동 경로가 빠졌습니다.')
    index = {s['id']: s for group in packet.values() for s in group}
    cited = set(study['source_ids'])
    selected = set(study['news_ids'])
    if not selected.intersection(eligible_news(packet)):
        raise ValueError('깊이 학습에 필요한 본문 맥락이 부족합니다.')
    for ref in study['report_ids']:
        if not selected.intersection(index[ref].get('related_news_ids', [])):
            raise ValueError('학습 주제와 관련 없는 보고서 인용 차단')

    def text(item, key, minimum=1, maximum=500):
        value = item.get(key) if isinstance(item, dict) else None
        if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
            length = len(value.strip()) if isinstance(value, str) else -1
            raise ValueError(f'학습 내용 누락·분량 오류: {key} ({length}자; 허용 {minimum}~{maximum}자)')

    def refs(item, news_required=False):
        values = item.get('source_ids') if isinstance(item, dict) else None
        if (not isinstance(values, list) or not 1 <= len(values) <= 4
                or any(not isinstance(r, str) or r not in cited for r in values)):
            raise ValueError('학습 문단의 출처 누락·불일치')
        if news_required and not set(values).intersection(selected):
            raise ValueError('사건 설명에는 확인한 기사 근거가 필요합니다.')

    event = depth.get('event')
    for key in ('who', 'when', 'where', 'what', 'why_known', 'how_known'):
        text(event, key, maximum=260)
    refs(event, news_required=True)
    text(depth.get('why_now'), 'explanation', 40, 500); refs(depth['why_now'])
    sizes = {'foundations': (3, 3), 'mechanism': (3, 4), 'connections': (2, 3),
             'source_contributions': (2, 5), 'thinking_questions': (2, 3)}
    for key, (minimum, maximum) in sizes.items():
        rows = depth.get(key)
        if not isinstance(rows, list) or not minimum <= len(rows) <= maximum:
            raise ValueError('학습 항목 수 오류: ' + key)
    for item in depth['foundations']:
        concept = CONCEPT_PAIRS.get(item.get('concept_id'))
        if not concept:
            raise ValueError('확인하지 않은 기초 개념 차단')
        item['term'] = concept[0] + ' · ' + concept[2]
        item['explanation'] = concept[0] + ': ' + concept[1] + ' ' + concept[2] + ': ' + concept[3] + ' ' + concept[4]
        text(item, 'term', maximum=50); text(item, 'explanation', 35, 350); text(item, 'application', 25, 350)
    if len({x['concept_id'] for x in depth['foundations']}) != 3:
        raise ValueError('서로 다른 기초 개념을 선택해야 합니다.')
    for item in depth['mechanism']:
        text(item, 'change', 10, 200); text(item, 'because', 40, 420); text(item, 'condition', 15, 250); refs(item)
        if item['change'].strip() == item['because'].strip():
            raise ValueError('변화를 반복하지 말고 중간 경로를 설명해야 합니다.')
    if len({item.get('kind') for item in depth['connections'] if isinstance(item, dict)}) < 2:
        raise ValueError('서로 다른 분야의 연결을 구분해야 합니다.')
    for item in depth['connections']:
        if item.get('kind') not in ('산업', '사회', '거시경제'):
            raise ValueError('연결 분야 오류')
        text(item, 'target', 2, 80); text(item, 'pathway', 60, 500)
        text(item, 'condition', 20, 250); text(item, 'limit', 20, 250); refs(item)
    contributed = set()
    for item in depth['source_contributions']:
        if not isinstance(item, dict) or item.get('source_id') not in cited:
            raise ValueError('출처가 뒷받침하는 범위 불일치')
        contributed.add(item['source_id']); text(item, 'supports', 15, 300); text(item, 'does_not_prove', 15, 300)
    if not cited.issubset(contributed):
        raise ValueError('인용한 각 출처의 기여와 한계를 표시해야 합니다.')
    for item in depth['thinking_questions']:
        text(item, 'question', 15, 200); text(item, 'hint', 15, 250)
    # 같은 말을 문단 수만 늘려 반복하는 출력은 표시하지 않는다.
    explanations = [x['because'].strip() for x in depth['mechanism']]
    if len(set(explanations)) != len(explanations):
        raise ValueError('동일한 작동 경로의 반복 차단')


def generate_learning(*args, **kwargs):
    """폐기된 생성 진입점은 재활성화할 수 없다."""
    raise ValueError('제미나이 생성 기능은 제거했습니다. ChatGPT 조사 자료를 사용하세요.')
