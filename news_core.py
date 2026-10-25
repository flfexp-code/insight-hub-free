"""v1의 RSS 수집을 확장한 무료 수집·분류·중복 제거 모듈."""
from __future__ import annotations

import copy
import hashlib
import html
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import requests

UTC = timezone.utc
KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent
SEARCHES = {
    '거시경제': '기준금리 OR 환율 OR 물가 OR 경제성장 OR 경기침체',
    '금융': '은행 OR 금융위원회 OR 금융시장 OR 보험',
    '에너지': '전력망 OR 발전공기업 OR 에너지 정책',
    '산업·통상': '수출 OR 관세 OR 반도체 OR 산업정책',
    '고용·사회': '고용률 OR 청년고용 OR 노동시장 OR 연금개혁 OR 고령화',
    '국제·정책': '국제경제 OR 재정정책 OR 경제정책',
    '주택·건설': '공공주택 OR 공사비 OR 부동산 PF OR 미분양',
    '교통·인프라': '고속도로 OR 통행료 OR 교통량 OR 도로 건설',
}
KEYWORDS = {
    '거시경제': ['금리', '환율', '물가', '통화정책', '경제성장', '경기침체', '한국은행', '국채', 'GDP', '경제', '경기부양', '경기회복', '경기둔화', '경기변동', '경기안정', '성장률', '소비', '유가'],
    '금융': ['은행', '금융', '보험', '대출', '채권', '증권', '신용보증', '자본시장'],
    '에너지': ['전력', '발전소', '발전공기업', '발전공사', '발전설비', '발전량', '발전사업', '서부발전', '남부발전', '중부발전', '동서발전', '남동발전', '태양광', '풍력', '에너지', '가스', '재생에너지', '전력망', '송전', '원전'],
    '산업·통상': ['산업', '수출', '수입', '관세', '무역', '반도체', '공급망', '제조업'],
    '고용·사회': ['고용', '취업', '채용', '실업', '노동', '인구', '저출생', '연금'],
    '국제·정책': ['정책', '정부', '재정', '미국', '중국', '유럽', '국회', '예산'],
    '주택·건설': ['공공주택', '주택', '분양', '부동산', '공사비', '시공사', '택지', '건설'],
    '교통·인프라': ['고속도로', '통행료', '교통량', '도로공사', '도로관리', '물동량'],
}
INDUSTRIES = {
    '금융·보험': ['은행', '보험', '증권', '금융', '신용보증', '대출'],
    '전력·에너지': [*KEYWORDS['에너지'], '석유', '한전', '가스공사'],
    '반도체·IT': ['반도체', '삼성전자', '하이닉스', '데이터센터', '인공지능', 'AI', '소프트웨어', 'HBM', '엔비디아', 'GPU'],
    '바이오·제약': ['바이오', '제약', '신약', '의약품', '임상', '셀트리온', '백신'],
    '자동차·배터리': ['자동차', '현대차', '기아', '전기차', '배터리', '이차전지', '리튬', '하이브리드', '르노', 'ESS'],
    '건설·부동산': ['건설', '부동산', '주택', '아파트', 'PF', '분양'],
    '유통·식품': ['유통', '식품', '농협', '소매', '마트', '물류', '농업'],
    '교통·인프라': ['고속도로', '도로공사', '통행료', '교통량', '화물', '물동량'],
}
ISSUES = {
    '금리·자금조달': {
        'keywords': ['금리', '대출', '채권', '국채', '자금조달'],
        'path': '기준금리·시장금리 → 차입비용 → 투자·이자부담',
        'questions': ['금리 변화가 신규 차입과 기존 차입 중 어디에 먼저 반영될까요?', '변동금리 차입 비중과 만기 도래 금액을 확인했나요?'],
    },
    '환율·원가': {
        'keywords': ['환율', '원화', '달러', '원자재', '유가'],
        'path': '환율·원자재 가격 → 수입원가·수출대금 → 이익률',
        'questions': ['수출대금 증가와 수입원가 상승 중 어느 영향이 클까요?', '달러 결제 비중과 환헤지 여부를 확인했나요?'],
    },
    '통상·공급망': {
        'keywords': ['관세', '수출', '무역', '공급망', '제재'],
        'path': '통상조치 → 판매시장·조달처 → 매출·생산비용',
        'questions': ['해당 국가의 매출 비중과 현지 생산 비중은 얼마나 될까요?', '적용 시점·예외 품목·대체 공급처를 확인했나요?'],
    },
    '설비·전력수요': {
        'keywords': ['전력', '발전소', '발전설비', '발전량', '발전사업', '서부발전', '태양광', '풍력', '데이터센터', '송전', '설비', '투자'],
        'path': '수요 증가 → 설비·망 투자 → 자금 소요·공급능력',
        'questions': ['수요가 늘어도 생산·공급을 늘릴 여력이 있을까요?', '투자금 회수 기간과 인허가·전력망 제약을 확인했나요?'],
    },
    '고용·운영': {
        'keywords': ['고용', '노동', '인건비', '채용', '임금', '인구'],
        'path': '노동시장·인구 변화 → 인력수급·수요 → 운영비용·서비스',
        'questions': ['인력 부족과 수요 감소가 같은 시점에 나타나나요?', '업종·지역·연령별 차이를 확인했나요?'],
    },
    '규제·재정': {
        'keywords': ['규제', '정책', '예산', '보조금', '법안', '정부'],
        'path': '규제·예산 변화 → 사업조건·지원대상 → 비용·사업기회',
        'questions': ['발표 단계와 시행 확정 단계를 구분했나요?', '적용 대상·시행일·유예기간은 무엇인가요?'],
    },
    '안전·운영관리': {
        'keywords': ['안전', 'CCTV', '관리소', '정전', '공급중단', '재난'],
        'path': '위험 징후·현장 사고 → 점검·대응 → 서비스 중단·운영비용',
        'questions': ['도입한 기술이 어떤 위험을 탐지하고, 탐지 뒤 누가 조치하나요?', '오탐·미탐·개인정보 처리와 현장 대응 시간을 확인했나요?'],
    },
    '실적·수익성': {
        'keywords': ['실적', '매출', '영업이익', '적자', '흑자', '수익'],
        'path': '판매량·단가·비용 → 영업이익 → 현금창출·투자여력',
        'questions': ['실적 변화가 판매량·단가·일회성 항목 중 무엇 때문인가요?', '영업현금흐름과 부채도 같은 방향으로 변했나요?'],
    },
}
DIRECT_FEEDS = [
    ('한국경제 오피니언', 'https://www.hankyung.com/feed/opinion', '오피니언'),
    ('한국경제 경제', 'https://www.hankyung.com/feed/economy', '거시경제'),
    ('한국경제 증권', 'https://www.hankyung.com/feed/finance', '금융'),
    ('한국경제 IT', 'https://www.hankyung.com/feed/it', '산업·통상'),
    ('한국경제 국제', 'https://www.hankyung.com/feed/international', '국제·정책'),
    ('한국경제 사회', 'https://www.hankyung.com/feed/society', '고용·사회'),
    ('뉴시스 경제', 'https://nwww.newsis.com/RSS/economy.xml', '거시경제'),
    ('뉴시스 산업', 'https://nwww.newsis.com/RSS/industry.xml', '산업·통상'),
    ('뉴시스 금융', 'https://nwww.newsis.com/RSS/bank.xml', '금융'),
]


def clean(value: str) -> str:
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]*>', '', value or ''))).strip()


def normalize_title(title: str, source: str = '') -> str:
    title = clean(title)
    if source:
        title = re.sub(r'\s*[-–—]\s*' + re.escape(source) + r'\s*$', '', title)
    title = re.sub(r'^\s*\[(속보|종합\d*|포토|영상)\]\s*', '', title)
    return re.sub(r'[^가-힣a-z0-9]', '', title.casefold())


def article_id(title: str, source: str = '') -> str:
    return hashlib.sha256(normalize_title(title, source).encode()).hexdigest()[:20]


def safe_link(url: str) -> str:
    try:
        p = urlsplit(url.strip())
        return url if p.scheme in ('http', 'https') and p.netloc and not p.username else ''
    except ValueError:
        return ''


def canonical_link(url: str) -> str:
    url = safe_link(url)
    if not url:
        return ''
    p = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(p.query) if not k.startswith('utm_') and k not in ('gclid', 'fbclid')]
    return urlunsplit((p.scheme, p.netloc.lower(), p.path.rstrip('/'), urlencode(sorted(query)), ''))


def classify(text: str, company: str = '') -> list[str]:
    text = text.casefold()
    cats = [cat for cat, words in KEYWORDS.items() if any(k.casefold() in text for k in words)]
    if company and company.casefold() in text:
        cats.append('관심 기업')
    return cats or ['기타']


def industry_tags(text: str) -> list[str]:
    return [cat for cat, words in INDUSTRIES.items() if any(k.casefold() in text.casefold() for k in words)] or ['기타']


def issue_tags(text: str) -> list[str]:
    return [name for name, spec in ISSUES.items() if any(k.casefold() in text.casefold() for k in spec['keywords'])]


def parse_time(value: str) -> datetime | None:
    try:
        d = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return d.replace(tzinfo=UTC) if d.tzinfo is None else d.astimezone(UTC)
    except (ValueError, AttributeError, TypeError):
        return None


def format_kst(value: str) -> str:
    d = parse_time(value)
    return d.astimezone(KST).strftime('%Y-%m-%d %H:%M') if d else '발행일 미제공'


def parse_feed(content: bytes, topic: str, feed_name: str, limit: int) -> list[dict]:
    feed = feedparser.parse(content)
    if not feed.get('version') or (feed.bozo and not feed.entries):
        raise ValueError('유효한 RSS/Atom 피드가 아닙니다')
    rows = []
    for e in feed.entries[:limit]:
        source = e.get('source', {}).get('title', '') or feed_name
        title = clean(e.get('title', ''))
        if not title or not normalize_title(title, source):
            continue
        if source and title.endswith(' - ' + source):
            title = title[:-(len(source) + 3)]
        # 전문·설명 텍스트는 저장하지 않고 제목/출처/링크/날짜만 사용한다.
        p = e.get('published_parsed') or e.get('updated_parsed')
        try:
            published = datetime(*p[:6], tzinfo=UTC).isoformat() if p else ''
        except (ValueError, TypeError):
            published = ''
        rows.append({
            'id': article_id(title, source), 'title': title, 'summary': '',
            'link': safe_link(e.get('link', '')), 'source': clean(source),
            'published': published, 'collected_at': datetime.now(UTC).isoformat(),
            'categories': classify(title), 'industries': industry_tags(title),
            'issues': issue_tags(title), 'search_topics': [topic],
        })
    return rows


def excluded_personnel(title: str) -> bool:
    """면접·경제 학습에서 제외하도록 요청한 내부 인사 기사."""
    return bool(re.search(r'인사(?!이트|이드)|승진|승격|전보|보직|블랙리스트|'
                          r'채용.{0,25}(?:비리|청탁|내정|논란)|(?:비리|청탁|내정).{0,25}채용|'
                          r'(?:임원|사장|부사장).{0,8}(?:인선|선임|임명|교체)', clean(title)))


def deduplicate(articles: list[dict]) -> list[dict]:
    """같은 URL 또는 정규화 제목만 병합. 다른 제목의 같은 사건은 유지한다."""
    result, titles, links = [], {}, {}
    for raw in articles:
        if excluded_personnel(raw['title']):
            continue  # 새 수집·과거 저장본·추가 검색에 모두 적용. 표시 토글로도 복원하지 않음.
        a = copy.deepcopy(raw)
        # 저장본도 최신 제목 규칙으로 재분류하여 이전 오분류를 남기지 않는다.
        a['categories'] = classify(a['title'])
        a['industries'] = industry_tags(a['title'])
        a['issues'] = issue_tags(a['title'])
        title = normalize_title(a['title'], a.get('source', ''))
        link = canonical_link(a.get('link', ''))
        idx = titles.get(title)
        if idx is None and link:
            idx = links.get(link)
        if idx is None:
            idx = len(result)
            a['id'] = article_id(a['title'], a.get('source', ''))
            result.append(a)
        else:
            target = result[idx]
            for field in ('categories', 'industries', 'issues', 'search_topics'):
                target[field] = list(dict.fromkeys(target.get(field, []) + a.get(field, [])))
            if a.get('published', '') > target.get('published', ''):
                target['published'] = a['published']
            if not target.get('link') and a.get('link'):
                target['link'] = a['link']
            target['collected_at'] = max(a.get('collected_at', ''), target.get('collected_at', ''))
        titles[title] = idx
        if link:
            links[link] = idx
    return sorted(result, key=lambda a: a.get('published', ''), reverse=True)


def _fetch(spec: tuple, limit: int, timeout: int) -> tuple[list[dict], str]:
    name, url, topic = spec
    try:
        response = requests.get(url, timeout=(min(timeout, 5), timeout), headers={'User-Agent': 'InsightHub/2.0 (personal RSS reader)'})
        response.raise_for_status()
        if len(response.content) > 5_000_000:
            raise ValueError('피드 크기 제한 초과')
        return parse_feed(response.content, topic, name, limit), ''
    except (requests.RequestException, ValueError) as exc:
        # URL/서버 원문은 표시하지 않는다.
        status = getattr(getattr(exc, 'response', None), 'status_code', None)
        return [], f'{name}: ' + (f'HTTP {status}' if status else type(exc).__name__)


def fetch_news(searches: dict[str, str] | None = None, max_per_topic: int = 40, timeout: int = 10,
               direct: bool = True) -> tuple[list[dict], list[str]]:
    searches = SEARCHES if searches is None else searches
    specs = []
    for topic, query in searches.items():
        params = urlencode({'q': query + ' when:7d', 'hl': 'ko', 'gl': 'KR', 'ceid': 'KR:ko'})
        specs.append((f'Google 뉴스 {topic}', f'https://news.google.com/rss/search?{params}', topic))
    if direct and searches:
        # 보완 피드는 검색 분야와 독립적으로 수집, 분류는 본문 제목 규칙만 적용.
        specs.extend(DIRECT_FEEDS)
    if not specs:
        return [], []
    with ThreadPoolExecutor(max_workers=min(6, len(specs))) as pool:
        results = list(pool.map(lambda s: _fetch(s, max_per_topic, timeout), specs))
    rows = [a for articles, _ in results for a in articles]
    errors = [err for _, err in results if err]
    return deduplicate(rows), errors


def company_query(name: str) -> str:
    name = clean(name).replace('"', '').strip()
    if not name or len(name) > 60 or not re.fullmatch(r'[가-힣a-zA-Z0-9 .&()·_-]+', name):
        raise ValueError('기업명은 한글·영문·숫자 등으로 1~60자 입력하세요')
    return '"' + name + '"'


def company_matches(article: dict, names: list[str]) -> bool:
    text = (article.get('title', '') + ' ' + article.get('summary', '')).casefold()
    for raw in names:
        word = raw.strip().casefold()
        if not word:
            continue
        # LH, AI, LNG 등을 다른 영문 단어의 일부와 매칭하지 않는다.
        if re.fullmatch(r'[a-z0-9]+', word):
            if re.search(r'(?<![a-z0-9])' + re.escape(word) + r'(?![a-z0-9])', text):
                return True
        elif word in text:
            return True
    return False


def filter_articles(articles: list[dict], topics=None, industry='전체', keyword='', days=7,
                    company_names=None, now=None) -> list[dict]:
    cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
    selected = []
    for a in articles:
        d = parse_time(a.get('published', ''))
        if d and (d < cutoff or d > (now or datetime.now(UTC)) + timedelta(days=1)):
            continue
        if topics is not None and not set(topics).intersection(a.get('categories', [])):
            continue
        if industry != '전체' and industry not in a.get('industries', []):
            continue
        if keyword and keyword.casefold() not in a['title'].casefold():
            continue
        if company_names and not company_matches(a, company_names):
            continue
        selected.append(a)
    return selected


def merge_history(old: list[dict], new: list[dict], days=30, maximum=3000, now=None) -> list[dict]:
    # 새 수집 결과를 먼저 두어 제목·분류의 현재 값을 우선한다.
    rows = deduplicate(new + old)
    cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
    def recent(a):
        date = parse_time(a.get('published', '')) or parse_time(a.get('collected_at', ''))
        return date is not None and cutoff <= date <= (now or datetime.now(UTC)) + timedelta(days=1)
    return [a for a in rows if recent(a)][:maximum]


def load_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {} if default is None else default


def atomic_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(path)


def analysis_cards(articles: list[dict]) -> list[dict]:
    cards = []
    for name, spec in ISSUES.items():
        evidence = [a for a in articles if name in a.get('issues', [])]
        if evidence:
            cards.append({'name': name, 'count': len(evidence), 'path': spec['path'],
                          'questions': spec['questions'], 'evidence': evidence[:3]})
    return sorted(cards, key=lambda c: c['count'], reverse=True)
