from datetime import datetime
from unittest.mock import patch

import streamlit as st
from streamlit.testing.v1 import AppTest
from news_core import ROOT, UTC, classify, industry_tags, issue_tags


def seed():
    title = '한국서부발전 데이터센터 전력 투자 확대'
    return {'title':title, 'source':'검증용 출처', 'link':'https://example.com/news',
            'published':datetime.now(UTC).isoformat(), 'collected_at':datetime.now(UTC).isoformat(),
            'categories':classify(title), 'industries':industry_tags(title), 'issues':issue_tags(title),
            'search_topics':['에너지']}


def test_screen_filters_company_search_refresh():
    rows = [seed()]
    st.cache_data.clear()
    with patch('news_core.fetch_news', return_value=(rows, [])):
        at = AppTest.from_file(str(ROOT/'app.py'), default_timeout=30).run()
        assert not at.exception
        assert at.title[0].value == '경제·산업 인사이트 허브'
        at.sidebar.text_input[0].set_value('한국서부발전').run()
        assert not at.exception
        assert at.metric[1].value != '기업명 입력'
        at.button(key='search_company').click().run()
        assert not at.exception
        at.selectbox(key='industry').set_value('전력·에너지').run()
        assert not at.exception
        at.text_input(key='keyword').set_value('없는단어123').run()
        assert not at.exception
        assert at.metric[0].value == '0건'
        at.text_input(key='keyword').set_value('').run()
        at.button(key='refresh').click().run()
        assert not at.exception
        at.sidebar.multiselect[0].set_value([]).run()
        assert not at.exception
        assert at.metric[0].value == '0건'
        at.selectbox(key='watch_company').set_value('한국도로공사').run()
        assert not at.exception
        assert at.text_input(key='company').value == '한국도로공사'
        at.selectbox(key='watch_company').set_value('한국토지주택공사').run()
        assert not at.exception
        assert 'LH' in at.text_input(key='aliases').value


def test_all_network_failures_empty_saved_file():
    st.cache_data.clear()
    with patch('news_core.load_json', return_value={}), patch('pathlib.Path.exists', return_value=False), \
            patch('news_core.fetch_news', return_value=([], ['피드: Timeout'])):
        at = AppTest.from_file(str(ROOT/'app.py'), default_timeout=30).run()
    assert not at.exception
    assert at.metric[0].value == '0건'
