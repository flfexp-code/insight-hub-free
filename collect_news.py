"""GitHub Actions 및 수동 실행용. 전체 실패 시 기존 기사 파일을 보존한다."""
import argparse
from datetime import datetime
from pathlib import Path

from news_core import ROOT, SEARCHES, UTC, atomic_json, company_query, fetch_news, load_json, merge_history


def collect(data_dir: Path, config_path: Path):
    config = load_json(config_path)
    searches = dict(SEARCHES)
    companies = config.get('companies', [])
    if not isinstance(companies, list) or len(companies) > 10:
        raise ValueError('관심 기업은 목록 형태로 최대 10개까지 설정하세요')
    for company in companies:
        searches['기업: ' + company] = company_query(company)
    articles, errors = fetch_news(searches, int(config.get('max_per_feed', 40)))
    old = load_json(data_dir / 'news.json').get('articles', [])
    now = datetime.now(UTC).isoformat()
    if not articles:
        atomic_json(data_dir / 'status.json', {'attempted_at': now, 'ok': False, 'received': 0,
                    'errors': errors or ['수집 결과가 없습니다'], 'last_success': load_json(data_dir / 'status.json').get('last_success', '')})
        print('수집 실패: 기존 news.json을 보존했습니다.')
        return 1
    merged = merge_history(old, articles, days=30, maximum=3000)
    # 기사 전문과 RSS 설명은 저장하지 않는다.
    payload = {'schema_version': 2, 'updated_at': now, 'articles': merged}
    atomic_json(data_dir / 'news.json', payload)
    atomic_json(data_dir / 'status.json', {'attempted_at': now, 'last_success': now, 'ok': True,
                'received': len(articles), 'stored': len(merged), 'errors': errors})
    print(f'신규 피드 {len(articles)}건 / 누적 {len(merged)}건 / 실패 피드 {len(errors)}개')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='무료 RSS 뉴스 수집')
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'data')
    parser.add_argument('--config', type=Path, default=ROOT / 'config.json')
    args = parser.parse_args()
    raise SystemExit(collect(args.data_dir, args.config))
