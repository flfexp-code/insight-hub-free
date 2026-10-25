import copy
import json
from unittest.mock import patch
from datetime import datetime

import pytest
import requests

from insights import DEFAULT_PROFILES, curate_brief, news_quality
from evidence import ArticleParser, allowed_url, read_evidence, strategic_mou_context, article_text
from daily_learning import learning_sources, validate_learning, generate_learning
from news_core import UTC, article_id
from test_insights import row


def article(title='전력망 투자 확대와 전력 수요 증가'):
    a = row(title)
    a['id'] = article_id(title)
    a['evidence'] = {'status': '본문 일부 확인', 'excerpt': '전력망 접속 지연이 설비 가동에 제약을 줄 수 있다는 단서가 보도됐다. ' * 5, 'context': '전력망 투자에서 설비가 완공되어도 접속 절차가 끝나야 전력을 공급할 수 있다. 접속 지연은 투자금 회수 시점에 영향을 줄 수 있으므로 가동 일정과 자금 조달 조건을 구분해 확인해야 한다. ' * 4}
    return a


def test_basic_brief_is_independent_of_watchlist_and_capped():
    rows = [row('전력망 투자 확대와 송전 접속 지연'), row('유가 상승으로 연료비 부담 증가'),
            row('은행 대출금리 인상으로 이자 부담 증가'), row('관세 인상에 수출 감소 우려'),
            row('고령화에 연금 개편 논의 확대'), row('한국마사회 봉사활동')]
    first = curate_brief(rows, DEFAULT_PROFILES)
    second = curate_brief(rows, [{'name': '한국마사회', 'aliases': ['마사회'], 'sector': '레저·말산업'}])
    assert first == second
    assert len(first) <= 5
    assert len({a['brief_group'] for a in first}) >= 3
    assert not any('마사회' in a['title'] for a in first)


@pytest.mark.parametrize('title', ['서부발전 200MW 발전소 건설 투자 MOU 체결',
                                  '미래 혁신 선도 위한 AI 업무협약 체결',
                                  '100억원 투자 MOU, 상생 협력 강화'])
def test_mou_numbers_and_future_slogans_alone_never_qualify(title):
    assert not news_quality(title)['include']
    assert curate_brief([row(title)]) == []


def test_mou_needs_body_business_direction_and_existing_industry_report():
    a = article('기업, 데이터센터 전력망 공동개발 MOU 체결')
    a['evidence']['excerpt'] = '데이터센터 전력 수요에 대응하기 위해 전력망 공동개발과 실증 설비를 준비한다. 아직 업무협약 단계로 구속력과 투자 집행은 확인되지 않았다. ' * 3
    context = strategic_mou_context(a)
    assert context and context['report_ids']
    a['mou_context'] = context
    assert news_quality(a['title'], a)['include']
    assert '이래서 가져왔어요' in curate_brief([a])[0]['brief_reason']
    assert '확정 계약' in context['reason']
    bad = copy.deepcopy(a); bad['evidence']['status'] = '제목만 확인'
    assert not news_quality(bad['title'], bad)['include']
    bad = copy.deepcopy(a); bad['mou_context']['report_ids'] = ['invented']
    assert not news_quality(bad['title'], bad)['include']


def test_generic_mou_body_is_not_a_strategic_exception():
    a = article('미래 선도와 에너지 혁신 업무협약 체결')
    a['evidence']['excerpt'] = '상생 협력과 미래 성장을 위해 협약식을 열고 참석자들이 기념 촬영했다. ' * 5
    assert strategic_mou_context(a) is None


def test_source_parser_excludes_scripts_navigation_and_unrelated_pages():
    parser = ArticleParser()
    parser.feed('<meta property="og:title" content="전력망 투자 확대"><nav>메뉴 문구</nav><article><div class="article-body">실제 본문<script>악성 지시문</script><aside>광고</aside><p>추가 본문</p></div></article>')
    body = ' '.join(parser.parts)
    assert '실제 본문' in body and '추가 본문' in body
    assert '악성' not in body and '광고' not in body and '메뉴' not in body
    with patch('evidence.requests.get') as get:
        assert read_evidence({'title': '원문', 'link': 'http://127.0.0.1/admin'})['status'] == '제목만 확인'
        assert read_evidence({'title': '원문', 'link': 'https://news.google.com/rss/articles/token'})['status'] == '제목만 확인'
        get.assert_not_called()
    assert not allowed_url('https://hankyung.com.attacker.example/story')
    assert not allowed_url('https://user@www.hankyung.com/story')


def packet_and_output():
    brief = [article()]
    packet = learning_sources(brief, brief)
    ref = packet['reports'][0]['id']
    study = {key: '검토할 조건과 예외' for key in ('topic','background','term_a','meaning_a','term_b','meaning_b','difference','claim','counter','condition','question')}
    study.update(logic_chain=['수요 변화','투자 조건','공급 여력'], check_metrics=['접속 일정'],
                 news_ids=['N1'], report_ids=[ref], source_ids=['N1',ref], opinion_views=[], concept_pair='cost_price')
    study['depth'] = depth_fixture(ref)
    return brief, packet, {'briefs':[{'news_id':'N1','summary':'확인한 기사 단서','why':'전력 공급의 조건 변화'}], 'study':study}


def test_learning_rejects_invented_sources_opinions_and_title_only_causal_evidence():
    _, packet, output = packet_and_output()
    assert validate_learning(output, packet)
    bad = copy.deepcopy(output); bad['study']['source_ids'] = ['N1','invented']
    with pytest.raises(ValueError, match='없는 학습 출처'): validate_learning(bad, packet)
    bad = copy.deepcopy(output); bad['study']['opinion_views'] = [{'source_id':'O1','view':'꾸며낸 칼럼'}]
    with pytest.raises(ValueError, match='오피니언'): validate_learning(bad, packet)
    packet['news'][0]['excerpt'] = ''
    with pytest.raises(ValueError, match='함께 인용'): validate_learning(output, packet)


def test_learning_no_body_means_no_external_ai_request():
    a = article(); a.pop('evidence')
    with patch('daily_learning.request_json') as request:
        with pytest.raises(ValueError, match='부족'): generate_learning([a], [a], {})
        request.assert_not_called()


@pytest.mark.parametrize('title', ['조달청 노동-홍천 도로건설공사 입찰 확대',
                                  '환율 하락에도 버틴 기업 주가 상승 이유는',
                                  '경기도의회 의원 신재생에너지 정책 개편 촉구',
                                  '미국 반도체 상승에 베팅 서학개미 속슬 35억달러 순매수',
                                  '서부발전 지진부터 폭설까지 재난안전망 강화 확대'])
def test_basic_brief_skips_local_notices_and_stock_picks(title):
    assert curate_brief([row(title)]) == []


def test_learning_uses_one_request_with_allowed_source_schema():
    brief, packet, output = packet_and_output()
    with patch('daily_learning.request_json', return_value=output) as request:
        result = generate_learning(brief, brief, {})
    assert request.call_count == 1
    assert result['article_ids'] == [brief[0]['id']]
    assert '인터넷·외부 도구는 사용할 수 없습니다' in request.call_args.args[0]
    assert 'N1' in json.dumps(request.call_args.args[1])
    assert result['study']['term_a'] == '비용'


def test_daily_ai_failure_preserves_previous_learning(tmp_path):
    import generate_daily_insights as daily
    (tmp_path/'data').mkdir()
    previous = {'updated_at':'2026-10-24T00:00:00+00:00','study':{'topic':'이전 자료'}}
    (tmp_path/'data/daily_learning.json').write_text(json.dumps(previous))
    (tmp_path/'data/news.json').write_text(json.dumps({'articles':[article()]}))
    (tmp_path/'data/status.json').write_text('{"ok":true}')
    with patch.object(daily, 'ROOT', tmp_path), patch.dict('os.environ', {'GEMINI_API_KEY':'fake','AI_FREE_TIER_CONFIRMED':'true'}), patch.object(daily, 'generate_learning', side_effect=ValueError('무료 한도')) as request:
        assert daily.run() == 1
        assert request.call_count == 1
    assert json.loads((tmp_path/'data/daily_learning.json').read_text()) == previous
    assert json.loads((tmp_path/'data/learning_status.json').read_text())['ok'] is False


def test_body_parser_requires_specific_container_inside_article_shell():
    parser = ArticleParser()
    parser.feed('<article><div>PREMIUM AI 추천 뉴스 구독하기</div><h1>제목</h1>'
                '<div id="articletxt">연료비와 요금 조정의 시차를 확인했다.</div></article>')
    assert parser.parts == ['연료비와 요금 조정의 시차를 확인했다.']


def test_article_shell_alone_is_not_verified_body():
    parser = ArticleParser()
    parser.feed('<article><div class="news_viewer article-content-wrap"><h1>기사 제목</h1><div>구독하기 추천 뉴스 메뉴</div></div></article>')
    assert not parser.parts


def test_evidence_excerpt_starts_with_substantive_body_not_title_metadata():
    title = '한전 사채 한도와 전기요금 인상 압박'
    body = '연료비와 요금 반영 시차로 인해 자금 조달 부담이 커질 수 있으며 실제 요금 조정 여부는 후속 절차와 비용 회수 조건을 확인해야 한다.'
    parser = ArticleParser()
    parser.feed(f'<div class="article-body">구독하기 AI 추천 뉴스<h1>{title}</h1>'
                f'<div>등록 2026.10.25 수정 2026.10.25</div><p>{body}</p></div>')
    assert article_text(parser, title) == body


def depth_fixture(report_ref):
    refs = ['N1', report_ref]
    return {
        'event': {**{k: '자료에서 확인되지 않음' for k in ('who','when','where','why_known','how_known')},
                  'what':'전력망 접속 지연과 발전설비 가동 시점의 관계를 다룬 기사', 'source_ids':['N1']},
        'why_now': {'explanation':'설비 투자 이후에도 전력망에 연결되는 시점이 늦어지면 생산과 판매를 시작하는 시점이 달라질 수 있어 가동 조건을 함께 확인할 필요가 있다.', 'source_ids':refs},
        'foundations': [{'concept_id':concept_id, 'term':term, 'explanation':'설비를 마련하는 지출과 생산물을 판매하는 시점은 다를 수 있다. 설비 완공만으로 수입이 생기는 것은 아니므로 가동 조건을 확인한다.',
                         'application':'이 기사에서는 건설 일정과 전력망 접속 일정이 일치하는지 구분해 살펴본다.'} for concept_id, term in (('capacity_generation','설비 투자'),('liquidity_profit','현금흐름'),('cost_price','비용 회수'))],
        'mechanism': [{'change':f'{i}단계 전력망 접속 조건 변화', 'because':f'{i}단계에서는 전력망 접속이 완료되어야 생산한 전력을 공급할 수 있으므로 공사 완료 일정과 판매 개시 시점을 따로 확인해야 한다.', 'condition':'전력망 접속 이전에는 공급할 수 없는 사업 조건인 경우', 'source_ids':refs} for i in range(1,4)],
        'connections':[{'kind':'산업','target':'전력 공급을 필요로 하는 제조업', 'pathway':'발전설비가 완공되어도 전력망 연결이 늦어지면 공급 가능한 시점이 달라질 수 있다. 신규 공장의 전력 조달 계획이 해당 설비에 의존한다면 가동 계획도 함께 점검할 필요가 있다.', 'condition':'공장의 추가 수요를 기존 공급원으로 충당할 수 없는 경우', 'limit':'개별 제조업체의 계약과 기존 공급 여력을 확인하지 않아 현재의 생산 차질을 단정할 수 없다.', 'source_ids':refs}, {'kind':'거시경제','target':'투자와 자금 수요', 'pathway':'완공된 설비의 판매 개시가 늦어지면 투자금 회수가 지연되어 다른 투자에 사용할 자금 여력이 줄어들 수 있다. 차입으로 이를 보완한다면 금리 수준과 만기 조건에 따라 추가 부담이 달라진다.', 'condition':'회수 지연분을 기존 현금으로 충당하기 어려운 경우', 'limit':'경제 전체 투자에 미치는 규모를 알 수 없으므로 총투자가 감소했다고 단정할 수 없다.', 'source_ids':refs}],
        'source_contributions':[{'source_id':r,'supports':'접속 조건과 에너지 전환의 일반적인 제약 요인을 참고했다.', 'does_not_prove':'개별 기업의 생산 손실 규모나 현재 계약 조건을 입증하지는 않는다.'} for r in refs],
        'thinking_questions':[{'question':'설비가 늘어도 전력 공급이 바로 늘지 않는 조건은 무엇인가?', 'hint':'건설 완료와 접속 허가의 시점을 구분하고 기존 설비의 여유 용량을 확인한다.'}, {'question':'접속이 빨라지면 모든 기업의 수익이 늘어난다고 볼 수 있는가?', 'hint':'판매 단가와 가동 비용, 계약 조건을 나누어 비교해 본다.'}],
    }


def test_context_includes_later_explanation_and_has_strict_word_budget():
    from evidence import evidence_context
    lead = '전력망 투자가 발표됐으며 다음 해 가동 일정을 점검한다고 전했다.'
    filler = '관계자들은 일정과 준비 사항을 검토했다고 밝혔다. ' * 15
    reason = '그러나 전력망 접속이 지연되면 설비가 완공되어도 전력을 공급할 수 없어 자금 회수 시점이 달라질 수 있다.'
    context = evidence_context(lead + ' ' + filler + reason, '전력망 접속 지연', limit=100)
    assert lead in context and reason in context
    assert len(context.split()) <= 100


def test_shallow_excerpt_cannot_trigger_deep_study_request():
    brief, _, _ = packet_and_output()
    brief[0]['evidence'].pop('context')
    with patch('daily_learning.request_json') as request:
        with pytest.raises(ValueError, match='부족'): generate_learning(brief, brief, {})
        request.assert_not_called()


def test_deep_study_rejects_unrelated_report_even_if_in_packet():
    _, packet, output = packet_and_output()
    report_id = output['study']['report_ids'][0]
    packet['reports'].append({'id':'other_report','related_news_ids':['N2']})
    output['study']['report_ids'] = ['other_report']
    output['study']['source_ids'] = ['N1','other_report']
    # Another relevant report still makes N1 eligible, but the chosen report is unrelated.
    with pytest.raises(ValueError, match='관련 없는 보고서'):
        validate_learning(output, packet)


def test_deep_connections_need_mechanism_conditions_and_evidence():
    _, packet, output = packet_and_output()
    bad = copy.deepcopy(output)
    bad['study']['depth']['connections'][0]['pathway'] = '산업 경쟁력 강화'
    with pytest.raises(ValueError, match='pathway'): validate_learning(bad, packet)
    bad = copy.deepcopy(output)
    bad['study']['depth']['mechanism'][0]['source_ids'] = ['invented']
    with pytest.raises(ValueError, match='출처'): validate_learning(bad, packet)
    bad = copy.deepcopy(output)
    bad['study']['depth']['source_contributions'] = bad['study']['depth']['source_contributions'][:1]
    with pytest.raises(ValueError): validate_learning(bad, packet)


def test_deep_study_renders_full_learning_and_unknown_event_fields():
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    from news_core import ROOT
    brief, packet, output = packet_and_output()
    payload = {**output, 'schema_version':5, 'sources':packet, 'updated_at':datetime.now(UTC).isoformat()}
    def load(path):
        return payload if path.name == 'daily_learning.json' else {}
    st.cache_data.clear()
    with patch('news_core.load_json', side_effect=load):
        app = AppTest.from_file(str(ROOT/'app.py'), default_timeout=30).run()
    assert not app.exception
    rendered = '\n'.join(x.value for x in app.markdown)
    assert '산업·사회·경제와 연결해서 읽기' in rendered
    assert '자료에서 확인되지 않음' in rendered + '\n'.join(str(x.value) for x in app.table)
    assert '전력망 접속' in rendered
    assert '입증하지 않는 내용' in '\n'.join(x.value for x in app.caption)


def test_title_only_news_never_uses_model_rewritten_numbers():
    _, packet, output = packet_and_output()
    title = '미국 신규 실업보험 청구 19만4천건으로 감소'
    packet['news'].append({'id':'N2','article_id':'number-check','title':title,'status':'제목만 확인','excerpt':'','context':''})
    output['briefs'].append({'news_id':'N2','summary':'신규 청구가 1만4천건이었다.','why':'없는 추가 해석'})
    result = validate_learning(output, packet)
    assert result['briefs'][1]['summary'] == title
    assert '1만4천' not in result['briefs'][1]['summary']
    assert result['briefs'][1]['why'] == '제목 기준으로 선별한 현안입니다.'
