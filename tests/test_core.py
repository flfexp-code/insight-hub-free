from datetime import datetime, timedelta
import json
from pathlib import Path
from unittest.mock import patch

import pytest
import requests

import collect_news
from news_core import (UTC, analysis_cards, atomic_json, canonical_link, classify, company_query,
                       deduplicate, fetch_news, filter_articles, format_kst, industry_tags, issue_tags,
                       merge_history, parse_feed, safe_link)

NOW = datetime(2026, 10, 12, 12, tzinfo=UTC)


def article(title='금리 인하에 은행 대출 증가', link='https://example.com/1', source='신문A', days=0):
    return {'title': title, 'link': link, 'source': source,
            'published': (NOW - timedelta(days=days)).isoformat(), 'collected_at': NOW.isoformat(),
            'categories': classify(title), 'industries': industry_tags(title),
            'issues': issue_tags(title), 'search_topics': ['경제']}


RSS = b'''<?xml version="1.0"?><rss version="2.0"><channel><title>Test</title>
<item><title>Samsung profit - Paper</title><link>https://example.com/a</link>
<source>Paper</source><pubDate>Mon, 12 Oct 2026 12:00:00 GMT</pubDate></item>
<item><title>Unknown date</title><link>javascript:alert(1)</link></item>
</channel></rss>'''


def test_rss_source_date_and_link():
    rows = parse_feed(RSS, '금융', 'fallback', 20)
    assert rows[0]['title'] == 'Samsung profit'
    assert format_kst(rows[0]['published']) == '2026-10-12 21:00'
    assert rows[1]['link'] == ''
    assert rows[1]['published'] == ''
    assert '금융' not in rows[0]['categories']  # 검색 경로만으로 잘못 분류하지 않는다.


def test_invalid_feed_rejected():
    with pytest.raises(ValueError):
        parse_feed(b'<html>blocked</html>', '경제', 'x', 10)


def test_normalized_titles_merge_sources_and_categories():
    a = article('금리 인하, 은행 대출 증가 - 신문A', source='신문A')
    b = article('[속보] 금리 인하 은행 대출 증가 - 신문B', 'https://example.com/2', source='신문B')
    b['search_topics'] = ['금융']
    assert len(deduplicate([a, b])) == 1
    assert deduplicate([a, b])[0]['search_topics'] == ['경제', '금융']
    assert a['search_topics'] == ['경제']


def test_same_url_tracking_dedup():
    assert canonical_link('https://x.com/a?utm_source=a&id=1#x') == 'https://x.com/a?id=1'
    a = article('금리 상승', 'https://x.com/a?id=1&utm_source=a')
    b = article('시장금리 상승세', 'https://x.com/a?id=1&utm_source=b')
    assert len(deduplicate([a, b])) == 1


def test_opposite_events_preserved():
    assert len(deduplicate([article('금리 인상', 'https://x.com/a'), article('금리 인하', 'https://x.com/b')])) == 2


def test_multiple_industries_and_issues():
    title = '데이터센터 전력 투자와 삼성전자 반도체 실적'
    assert set(industry_tags(title)) == {'전력·에너지', '반도체·IT'}
    assert set(issue_tags(title)) == {'설비·전력수요', '실적·수익성'}
    cards = analysis_cards([article(title)])
    assert all(c['evidence'] and c['questions'] for c in cards)


def test_ambiguous_match_words_and_saved_tags():
    sports = article('안세영 배드민턴 경기 일정·32강 대진표')
    sports['categories'] = ['거시경제']  # 과거 규칙으로 저장된 오분류
    assert deduplicate([sports])[0]['categories'] == ['기타']
    assert '거시경제' in classify('경기침체 우려와 경기부양 대책')
    title = '조선산업 발전에 기여한 외국인 명예시민'
    assert '에너지' not in classify(title)
    assert '전력·에너지' not in industry_tags(title)
    assert '설비·전력수요' not in issue_tags(title)
    assert '전력·에너지' in industry_tags('한국서부발전 태양광 발전설비 점검')


def test_filter_period_company_alias_and_unknown_date():
    a = article('서부발전 전력 투자')
    b = article('한국서부발전 발전설비 투자', 'https://x.com/b', days=20)
    c = article('은행 대출', 'https://x.com/c')
    assert filter_articles([a,b,c], company_names=['한국서부발전', '서부발전'], days=7, now=NOW) == [a]
    assert filter_articles([a,b,c], topics=[], now=NOW) == []
    assert filter_articles([a,b,c], industry='금융·보험', now=NOW) == [c]


def test_retention_and_limit():
    old = article('오래된 뉴스', 'https://x.com/a', days=31)
    undated = article('날짜없는 뉴스', 'https://x.com/b'); undated['published'] = ''
    assert merge_history([old], [undated], now=NOW) == deduplicate([undated])
    assert len(merge_history([], [article(), article('새 뉴스', 'https://x.com/c')], maximum=1, now=NOW)) == 1


@pytest.mark.parametrize('name', ['삼성전자', 'NH농협은행', 'LG에너지솔루션', 'S&P'])
def test_company_query_valid(name):
    assert company_query(name).startswith('"')


@pytest.mark.parametrize('name', ['', 'x'*61, '기업 OR site:evil.com', '<script>'])
def test_company_query_invalid(name):
    with pytest.raises(ValueError): company_query(name)


@pytest.mark.parametrize('url', ['javascript:alert(1)', 'file:///etc/passwd', 'https://user:pass@x.com', '//evil.com'])
def test_unsafe_link(url):
    assert safe_link(url) == ''


def test_fetch_partial_failure():
    class Response:
        content = RSS
        def raise_for_status(self): pass
    def fake(url, **kw):
        if 'bad' in url: raise requests.Timeout()
        return Response()
    with patch('news_core.requests.get', side_effect=fake):
        rows, errors = fetch_news({'ok': 'good', 'bad': 'bad'}, direct=False)
    assert len(rows) == 2 and len(errors) == 1
    assert fetch_news({}) == ([], [])


def test_failed_collect_preserves_bytes(tmp_path):
    atomic_json(tmp_path / 'news.json', {'articles':[article()], 'updated_at':'last-success'})
    original = (tmp_path/'news.json').read_bytes()
    config = tmp_path/'config.json'; atomic_json(config, {'companies':[]})
    with patch('collect_news.fetch_news', return_value=([], ['접속 실패'])):
        assert collect_news.collect(tmp_path, config) == 1
    assert (tmp_path/'news.json').read_bytes() == original
    assert json.loads((tmp_path/'status.json').read_text())['ok'] is False


def test_successful_collect_writes(tmp_path):
    config = tmp_path/'config.json'; atomic_json(config, {'companies':[]})
    with patch('collect_news.fetch_news', return_value=([article(days=0)], [])), patch('collect_news.discover_reports', return_value=([], [])), patch('news_core.datetime') as dt:
        dt.now.return_value = NOW
        dt.fromisoformat.side_effect = datetime.fromisoformat
        assert collect_news.collect(tmp_path, config) == 0
    assert json.loads((tmp_path/'news.json').read_text())['articles']
    assert json.loads((tmp_path/'status.json').read_text())['ok'] is True
