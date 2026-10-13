"""GitHub Actions 및 수동 실행용. 전체 실패 시 기존 기사 파일을 보존한다."""
import argparse
from datetime import datetime
from pathlib import Path

from news_core import ROOT, SEARCHES, UTC, atomic_json, company_query, fetch_news, load_json, merge_history
from insights import DEFAULT_PROFILES, curate_brief, discover_reports, normalize_profiles


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
    defaults = {p['name']: p for p in DEFAULT_PROFILES}
    profiles = normalize_profiles([defaults.get(name, {'name': name, 'sector': '기타'}) for name in companies])
    brief = curate_brief(merged, profiles)
    atomic_json(data_dir / 'brief.json', {'updated_at': now, 'purpose': '취업 준비·경제 현안',
                'articles': brief, 'selected_count': len(brief), 'candidate_count': len(articles)})
    atomic_json(data_dir / 'status.json', {'attempted_at': now, 'last_success': now, 'ok': True,
                'received': len(articles), 'stored': len(merged), 'brief_count': len(brief), 'errors': errors})
    # 새 공식 자료는 검토 전 후보로만 보관하며 이미 검토한 요지를 덮어쓰지 않는다.
    candidates, report_errors = discover_reports()
    if candidates:
        atomic_json(data_dir / 'report_updates.json', {'updated_at': now, 'reports': candidates, 'errors': report_errors})
    elif report_errors:
        previous = load_json(data_dir / 'report_updates.json')
        atomic_json(data_dir / 'report_updates.json', {**previous, 'attempted_at': now, 'errors': report_errors})
    print(f'핵심 {len(brief)}건 / 수집 후보 {len(articles)}건 / 누적 검색 자료 {len(merged)}건 / 실패 피드 {len(errors)}개')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='무료 RSS 뉴스 수집')
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'data')
    parser.add_argument('--config', type=Path, default=ROOT / 'config.json')
    args = parser.parse_args()
    raise SystemExit(collect(args.data_dir, args.config))
