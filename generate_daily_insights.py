"""저장된 ChatGPT 조사 학습자료를 확인한다. 생성 API를 호출하지 않는다."""
from datetime import datetime

from news_core import ROOT, UTC, atomic_json
from research_learning import load_research


def run():
    research = load_research(ROOT / 'data/chatgpt_research.json')
    now = datetime.now(UTC).isoformat()
    atomic_json(ROOT / 'data/learning_status.json', {
        'attempted_at': now, 'ok': bool(research), 'provider': 'chatgpt_work',
        'last_success': research.get('updated_at', ''), 'requests': 0,
        'error': '' if research else '검증된 ChatGPT 조사 자료가 없습니다. 이전 파일은 보존합니다.'})
    print('ChatGPT 조사 자료 확인 완료. 외부 생성 API 요청 없음.' if research
          else 'ChatGPT 조사 자료 대기 중. 외부 생성 API 요청 없음.')
    return 0


if __name__ == '__main__':
    raise SystemExit(run())
