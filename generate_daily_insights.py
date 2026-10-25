"""기본 뉴스와 하루 한 주제만 AI로 작성한다. 기관 분석은 화면 요청 시 실행한다."""
from datetime import datetime
import os

from ai_insights import MODEL, ready
from daily_learning import generate_learning
from insights import curate_brief
from news_core import ROOT, UTC, atomic_json, load_json


def run():
    settings = {k: os.getenv(k, '') for k in ('GEMINI_API_KEY', 'AI_FREE_TIER_CONFIRMED')}
    if not ready(settings):
        print('무료 AI 미연결: API 요청 없음. 기사 목록은 이용할 수 있습니다.')
        return 0
    if load_json(ROOT / 'data/status.json').get('ok') is False:
        print('뉴스 수집 실패: 이전 학습자료를 유지합니다.')
        return 0
    news = load_json(ROOT / 'data/news.json')
    previous = load_json(ROOT / 'data/daily_learning.json')
    now = datetime.now(UTC).isoformat()
    try:
        rows = curate_brief(news.get('articles', []))
        output = generate_learning(rows, news.get('articles', []), settings)
        atomic_json(ROOT / 'data/daily_learning.json', {**output, 'updated_at': now,
                    'news_updated_at': news.get('updated_at', ''), 'model': MODEL})
    except ValueError as exc:
        atomic_json(ROOT / 'data/learning_status.json', {'attempted_at': now, 'ok': False,
                    'last_success': previous.get('updated_at', ''), 'error': str(exc)})
        print('하루 학습자료 작성 중단: 이전 자료 유지. ' + str(exc))
        return 1
    atomic_json(ROOT / 'data/learning_status.json', {'attempted_at': now, 'ok': True,
                'last_success': now, 'error': '', 'requests': 1})
    print(f'기본 뉴스 {len(rows)}개·학습 주제 1개 저장 완료. 기업별 자동 AI 요청 없음.')
    return 0


if __name__ == '__main__':
    raise SystemExit(run())
