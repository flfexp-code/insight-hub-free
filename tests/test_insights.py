from datetime import datetime
from unittest.mock import patch

import pytest

from insights import (DEFAULT_PROFILES, REPORTS, analysis_packet, build_insights,
                      cross_connections, discover_reports, news_quality, normalize_profiles,
                      related_articles)
from news_core import UTC, classify, company_matches, industry_tags, issue_tags


def row(title):
    return {'title': title, 'source': '검증용 기사', 'link': 'https://example.com/' + str(abs(hash(title))),
            'published': datetime.now(UTC).isoformat(), 'collected_at': datetime.now(UTC).isoformat(),
            'categories': classify(title), 'industries': industry_tags(title), 'issues': issue_tags(title)}


@pytest.mark.parametrize('title', [
    '한국도로공사 업무협약 체결', '서부발전 이웃돕기 성금 2억원 전달',
    'LH 봉사활동', '도로공사 우수기관 표창', '서부발전 지원금 1억원 전달',
    'LH 청년 지원금 지급', '서부발전 신입사원 채용 공고',
])
def test_promotion_and_transfer_omitted(title):
    assert not news_quality(title)['include']


@pytest.mark.parametrize('title', [
    '정부 전기차 보조금 20% 삭감', '태양광 보조금 지원대상 변경 시행',
    '서부발전 200MW 발전소 건설 투자 MOU 체결',
])
def test_material_policy_and_agreement_kept_for_review(title):
    q = news_quality(title)
    assert q['include'] and '확인' in q['label']


def test_english_alias_boundaries():
    assert company_matches(row('LH가 공공주택 공급'), ['LH'])
    assert not company_matches(row('LHC 연구 발표'), ['LH'])
    assert not company_matches(row('Thailand 관광'), ['AI'])


def test_indirect_business_connection_and_unrelated_news():
    road = DEFAULT_PROFILES[1]
    items = [row('고속도로 통행료 인상 검토'), row('도로공사 봉사활동'), row('제약사 임상시험 성공')]
    result = related_articles(items, road)
    assert len(result) == 1
    assert not result[0]['direct'] and result[0]['signals']
    assert len(related_articles(items, road, include_promo=True)) == 2


def test_grounded_cards_need_both_news_and_reports():
    lh = DEFAULT_PROFILES[2]
    assert build_insights([], lh) == []
    rows = related_articles([row('LH 공사비 상승으로 착공 지연'), row('시장금리 상승으로 차입 부담')], lh)
    cards = build_insights(rows, lh)
    assert cards and all(c['news'] and c['reports'] and c['counter'] for c in cards)
    assert any('입주' in c['response'] for c in cards)
    assert all(r in REPORTS for c in cards for r in c['reports'])
    connections = cross_connections(cards, lh)
    assert connections and connections[0]['news'] and connections[0]['reports']
    packet = analysis_packet(lh, rows, cards)
    assert '원문에 없는 수치' in packet and '기본' not in packet[:5]
    assert 'https://www.bok.or.kr/' in packet and '"id": "N1"' in packet


def test_same_construction_event_has_company_specific_response():
    news = [row('공사비 상승과 시공사 부도 우려')]
    road, lh = DEFAULT_PROFILES[1:]
    road_card = build_insights(related_articles(news, road), road)[0]
    lh_card = build_insights(related_articles(news, lh), lh)[0]
    assert '유지관리' in road_card['response']
    assert '입주' in lh_card['response']
    assert road_card['response'] != lh_card['response']


@pytest.mark.parametrize('bad', [None, [{}], DEFAULT_PROFILES * 4,
                               [DEFAULT_PROFILES[0], DEFAULT_PROFILES[0]]])
def test_invalid_profiles_rejected(bad):
    with pytest.raises(ValueError):
        normalize_profiles(bad)


def test_valid_profile_serialization():
    p = normalize_profiles([{'name': '한국가스공사', 'aliases': ['가스공사'], 'sector': '발전·에너지',
                             'keywords': ['LNG'], 'source_url': 'javascript:alert(1)'}])[0]
    assert p['source_url'] == '' and p['aliases'] == ['가스공사']


def test_official_discovery_does_not_promote_unreviewed_text():
    class Response:
        content = b'valid'
        text = '<a href="/research/economyDetailView?detail_no=9999">새 에너지 산업 보고서</a>'
        def raise_for_status(self): pass
    with patch('insights.requests.get', return_value=Response()):
        candidates, errors = discover_reports()
    assert candidates
    assert len(errors) == 2  # 다른 기관의 응답에는 해당 기관 자료 링크가 없음
    assert all('검토 전' in r['status'] for r in candidates)
    assert all('summary' not in r for r in candidates)
    assert not any(r['url'].endswith('9999') for r in REPORTS)


def test_official_discovery_skips_navigation_and_reports_empty_listing():
    class Response:
        content = b'valid'
        text = '<a href="/trends/ecotrendsList">KIET 경제 산업 동향 목록</a>'
        def raise_for_status(self): pass
    with patch('insights.requests.get', return_value=Response()):
        candidates, errors = discover_reports()
    assert candidates == []
    assert len(errors) == 3
    assert all('자료 후보를 찾지 못함' in error for error in errors)
