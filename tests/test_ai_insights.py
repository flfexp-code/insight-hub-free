from unittest.mock import patch
import pytest
from ai_insights import generate, ready, request_json, validate_output


@pytest.mark.parametrize('settings', [{}, {'GEMINI_API_KEY': 'fake', 'AI_FREE_TIER_CONFIRMED': 'true'}])
def test_removed_provider_cannot_be_enabled_by_old_secrets(settings):
    with patch('requests.sessions.Session.request', side_effect=AssertionError('network call')) as request:
        assert ready(settings) is False
        with pytest.raises(ValueError, match='제거'):
            generate({}, [], [], settings)
        with pytest.raises(ValueError, match='제거'):
            request_json('prompt', {}, settings)
        request.assert_not_called()


def test_archived_draft_still_rejects_invented_sources():
    item = {'title':'제목', 'phenomenon':'현상', 'impact':'영향', 'response':'검토', 'counter':'조건',
            'news_ids':['N1'], 'report_ids':['invented']}
    with pytest.raises(ValueError, match='없는 출처'):
        validate_output({'insights':[item]}, {'N1'}, {'R1'})


def test_collection_workflow_does_not_pass_provider_secrets():
    from news_core import ROOT
    import yaml
    text = (ROOT / '.github/workflows/daily-news.yml').read_text()
    workflow = yaml.safe_load(text)
    assert 'GEMINI_API_KEY' not in text
    assert 'AI_FREE_TIER_CONFIRMED' not in text
    assert any(step.get('run') == 'python collect_news.py' for step in workflow['jobs']['collect']['steps'])
