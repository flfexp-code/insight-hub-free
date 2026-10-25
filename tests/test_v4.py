import copy
import json
from unittest.mock import patch
from datetime import datetime

import pytest
import requests

from insights import DEFAULT_PROFILES, curate_brief, news_quality
from evidence import ArticleParser, allowed_url, read_evidence, strategic_mou_context
from daily_learning import learning_sources, validate_learning, generate_learning
from news_core import UTC, article_id
from test_insights import row


def article(title='전력망 투자 확대와 전력 수요 증가'):
    a = row(title)
    a['id'] = article_id(title)
    a['evidence'] = {'status': '본문 일부 확인', 'excerpt': '전력망 접속 지연이 설비 가동에 제약을 줄 수 있다는 단서가 보도됐다. ' * 5}
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
    parser.feed('<article><h1>기사 제목</h1><div>구독하기 추천 뉴스 메뉴</div></article>')
    assert not parser.parts
