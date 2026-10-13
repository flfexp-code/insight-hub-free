import copy
import json
from unittest.mock import patch

import pytest

from ai_insights import generate, ready, validate_output
from insights import DEFAULT_PROFILES, build_insights, related_articles
from test_insights import row


def output():
    return {'insights': [{'title': '검증용 연결', 'phenomenon': '기사 단서',
                         'impact': '조건부 영향', 'response': '대응 검토', 'counter': '예외 확인',
                         'news_ids': ['N1'], 'report_ids': ['bok_construction'], 'check_metrics': ['공정률']}]}


def test_no_key_or_confirmation_means_no_request():
    assert not ready({}) and not ready({'GEMINI_API_KEY': 'fake'})
    with patch('ai_insights.requests.post') as post:
        with pytest.raises(ValueError, match='요청을 보내지'):
            generate(DEFAULT_PROFILES[2], [], [], {})
        post.assert_not_called()


def test_unknown_source_is_rejected():
    value = output()
    value['insights'][0]['report_ids'] = ['invented']
    with pytest.raises(ValueError, match='없는 출처'):
        validate_output(value, {'N1'}, {'bok_construction'})
    assert validate_output(output(), {'N1'}, {'bok_construction'})


def test_personnel_never_sent_to_ai():
    with patch('ai_insights.requests.post') as post:
        with pytest.raises(ValueError, match='인사·승진'):
            generate(DEFAULT_PROFILES[1], [row('도로공사 승진 논란')], [{}],
                     {'GEMINI_API_KEY': 'fake', 'AI_FREE_TIER_CONFIRMED': 'true'})
        post.assert_not_called()


def test_rate_limit_has_no_retry_or_upgrade():
    profile = DEFAULT_PROFILES[2]
    rows = related_articles([row('LH 공사비 상승 우려')], profile)
    cards = build_insights(rows, profile)
    class Response:
        status_code = 429
    with patch('ai_insights.requests.post', return_value=Response()) as post:
        with pytest.raises(ValueError, match='유료 전환·재시도 없이'):
            generate(profile, rows, cards, {'GEMINI_API_KEY': 'fake', 'AI_FREE_TIER_CONFIRMED': 'true'})
        assert post.call_count == 1
        assert 'tools' not in post.call_args.kwargs['json']


def test_model_result_citations_are_validated():
    profile = DEFAULT_PROFILES[2]
    rows = related_articles([row('LH 공사비 상승 우려')], profile)
    cards = build_insights(rows, profile)
    class Response:
        status_code = 200
        def json(self):
            return {'candidates': [{'content': {'parts': [{'text': json.dumps(output())}]}}]}
    with patch('ai_insights.requests.post', return_value=Response()):
        result = generate(profile, rows, cards, {'GEMINI_API_KEY': 'fake', 'AI_FREE_TIER_CONFIRMED': 'true'})
    assert result[0]['report_ids'] == ['bok_construction']
