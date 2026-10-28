import copy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from news_core import ROOT
from research_learning import load_research, publish_research, validate_research


@pytest.fixture
def pack():
    return json.loads((ROOT / 'data/chatgpt_research.json').read_text())


def test_research_pack_and_real_screen_render_without_ai(pack):
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    validate_research(pack)
    st.cache_data.clear()
    with patch('ai_insights.requests.post', side_effect=AssertionError('AI request in reader')) as request:
        app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=30).run()
    assert not app.exception
    content = '\n'.join(x.value for x in app.markdown)
    assert pack['topic'] in content
    assert pack['sections'][2]['heading'] in content
    assert pack['sections'][0]['body'].split('\n')[0] in content
    assert request.call_count == 0


@pytest.mark.parametrize('damage', ['unknown_ref', 'unread', 'no_official_report', 'unsafe_url', 'future_date'])
def test_bad_research_never_overwrites_previous_file(tmp_path, pack, damage):
    destination = tmp_path / 'research.json'
    publish_research(pack, destination)
    original = destination.read_bytes()
    broken = copy.deepcopy(pack)
    if damage == 'unknown_ref':
        broken['sections'][0]['source_ids'] = ['invented']
    elif damage == 'unread':
        broken['sources'][0]['checked'] = '제목만 확인'
    elif damage == 'no_official_report':
        for source in broken['sources']:
            source['kind'] = '보도'
    elif damage == 'unsafe_url':
        broken['sources'][0]['url'] = 'https://user:password@example.com/private'
    else:
        broken['updated_at'] = '2099-01-01T00:00:00+00:00'
    with pytest.raises(ValueError):
        publish_research(broken, destination)
    assert destination.read_bytes() == original


def test_invalid_saved_research_falls_back_without_crashing(tmp_path):
    path = tmp_path / 'research.json'
    path.write_text('{broken json')
    assert load_research(path) == {}


def test_chatgpt_provider_skips_gemini_requests(tmp_path):
    import generate_daily_insights as daily
    (tmp_path / 'config.json').write_text('{"learning_provider":"chatgpt_work"}')
    with patch.object(daily, 'ROOT', tmp_path), patch.object(daily, 'generate_learning') as generate:
        assert daily.run() == 0
        generate.assert_not_called()
