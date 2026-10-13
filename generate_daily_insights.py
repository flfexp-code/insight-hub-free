"""무료 AI 연결 후에만 기본 관심 기업의 일일 심층 초안을 생성한다."""
from datetime import datetime
import os

from ai_insights import MODEL, generate, ready
from insights import DEFAULT_PROFILES, build_insights, related_articles
from news_core import ROOT, UTC, atomic_json, filter_articles, load_json


def run():
    settings = {k: os.getenv(k, '') for k in ('GEMINI_API_KEY', 'AI_FREE_TIER_CONFIRMED')}
    if not ready(settings):
        print('자동 AI 미연결: API 요청 없음. 뉴스·근거 연결 초안은 정상 이용 가능합니다.')
        return 0
    news = load_json(ROOT / 'data/news.json')
    if load_json(ROOT / 'data/status.json').get('ok') is False:
        print('뉴스 수집 실패: 이전 AI 초안을 유지합니다.')
        return 0
    rows = filter_articles(news.get('articles', []), days=7)
    output, errors = {}, []
    for profile in DEFAULT_PROFILES:
        selected = related_articles(rows, profile)
        cards = build_insights(selected, profile)
        if not cards:
            continue
        try:
            result = generate(profile, selected, cards, settings)
            output[profile['name']] = {'items': result, 'news': selected[:18],
                                        'reports': {r['id']: r for c in cards for r in c['reports']},
                                        'sector': profile['sector']}
        except ValueError as exc:
            errors.append(profile['name'] + ': ' + str(exc))
            break
    now = datetime.now(UTC).isoformat()
    previous = load_json(ROOT / 'data/ai_insights.json')
    if output:
        atomic_json(ROOT / 'data/ai_insights.json',
                    {'updated_at': now, 'news_updated_at': news.get('updated_at', ''),
                     'model': MODEL, 'companies': output, 'errors': errors})
    atomic_json(ROOT / 'data/ai_status.json',
                {'attempted_at': now, 'ok': bool(output) and not errors,
                 'last_success': now if output else previous.get('updated_at', ''), 'errors': errors})
    return 0 if output and not errors else 1


if __name__ == '__main__':
    raise SystemExit(run())
