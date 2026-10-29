import copy
import json
from unittest.mock import patch

import pytest

from news_core import ROOT
from pt_learning import feedback_packet
from research_learning import publish_research, validate_research


@pytest.fixture
def pack():
    return json.loads((ROOT / 'data/chatgpt_research.json').read_text())


def test_packet_keeps_chart_scope_and_sources_but_excludes_answer_key(pack):
    packet = feedback_packet(pack)
    assert '1,000명당' in packet and '2023~2026년' in packet
    assert '121' in packet and '-3.5' in packet
    assert pack['sources'][0]['url'] in packet
    assert pack['pt']['task'] in packet
    assert pack['pt']['answer_guide']['sample_script'] not in packet
    assert '정확히 정리' in packet and '꼬리질문을 하나만' in packet


@pytest.mark.parametrize('damage', ['source', 'nan', 'bool', 'shape', 'no_chart', 'no_script', 'duplicate', 'version'])
def test_invalid_pt_does_not_replace_valid_pack(tmp_path, pack, damage):
    path = tmp_path / 'pack.json'
    publish_research(pack, path)
    original = path.read_bytes()
    bad = copy.deepcopy(pack)
    pt = bad['pt']
    if damage == 'source':
        pt['materials'][0]['source_ids'] = ['missing']
    elif damage in ('nan', 'bool', 'shape'):
        chart = pt['materials'][2]['chart']
        if damage == 'shape':
            chart['rows'][0].pop()
        else:
            chart['rows'][0][1] = float('nan') if damage == 'nan' else True
    elif damage == 'no_chart':
        for material in pt['materials']:
            material.pop('chart', None)
    elif damage == 'no_script':
        pt['answer_guide']['sample_script'] = ''
    elif damage == 'duplicate':
        pt['materials'][1]['id'] = pt['materials'][0]['id']
    else:
        pt['version'] = 99
    with pytest.raises(ValueError):
        publish_research(bad, path)
    assert path.read_bytes() == original


def test_legacy_learning_pack_still_valid(pack):
    pack.pop('pt')
    validate_research(pack)


def test_pt_screen_renders_script_collapsed_and_charts_without_network(pack):
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    st.cache_data.clear()
    with patch('news_core.fetch_news', return_value=([], [])), patch('requests.sessions.Session.request', side_effect=AssertionError('unexpected network')) as request:
        app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=30).run()
    assert not app.exception
    content = '\n'.join(item.value for item in app.markdown)
    assert pack['pt']['task'] in '\n'.join(item.value for item in app.info)
    assert pack['pt']['answer_guide']['sample_script'] in content
    guide = next(e for e in app.expander if '예시 발표' in e.label)
    assert not guide.proto.expanded
    assert len(app.get('vega_lite_chart')) == 2
    assert request.call_count == 0
