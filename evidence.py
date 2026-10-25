"""공개 원문의 짧은 근거만 보관한다. 로그인·유료벽·Google 경유 링크를 우회하지 않는다."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlsplit

import requests

from news_core import UTC, clean, company_matches

PUBLISHERS = ('hankyung.com', 'newsis.com', 'yna.co.kr', 'mk.co.kr', 'sedaily.com',
              'bok.or.kr', 'kdi.re.kr', 'kiet.re.kr', 'keei.re.kr', 'koti.re.kr')
MOU = re.compile(r'\bMOU\b|업무협약|협약\s*체결|협약식', re.I)
OPINION = re.compile(r'사설|칼럼|기고|오피니언')


def allowed_url(url):
    try:
        p = urlsplit(url)
        host = (p.hostname or '').lower()
        return (p.scheme == 'https' and not p.username and p.port in (None, 443)
                and any(host == domain or host.endswith('.' + domain) for domain in PUBLISHERS))
    except (ValueError, TypeError):
        return False


class ArticleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack, self.parts, self.page_title = [], [], ''
        self.description, self.title_parts = '', []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta':
            name = attrs.get('property', attrs.get('name', ''))
            if name == 'og:title':
                self.page_title = clean(attrs.get('content', ''))
            if name in ('og:description', 'description') and not self.description:
                self.description = clean(attrs.get('content', ''))
        if tag in ('meta', 'link', 'img', 'br', 'hr', 'input', 'source', 'wbr', 'area', 'base', 'embed', 'param', 'track'):
            return
        marker = ' '.join((attrs.get('id', ''), attrs.get('class', ''), attrs.get('itemprop', '')))
        parent_active = bool(self.stack and self.stack[-1][1])
        blocked = tag in ('script', 'style', 'nav', 'aside', 'footer', 'form', 'button', 'noscript') or bool(self.stack and self.stack[-1][2])
        active = parent_active or bool(re.search(
            r'article[-_]?body|articleBody|article[-_]?txt|article[-_]?content|article-view-content|textBody|newsct_article|read-body', marker, re.I))
        self.stack.append((tag, active, blocked))

    def handle_endtag(self, tag):
        for index in range(len(self.stack)-1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, value):
        if self.stack and self.stack[-1][0] == 'title':
            self.title_parts.append(value)
        if self.stack and self.stack[-1][1] and not self.stack[-1][2]:
            text = clean(value)
            if text:
                self.parts.append(text)


def _title_matches(expected, actual):
    words = set(re.findall(r'[가-힣A-Za-z0-9]{2,}', expected))
    other = set(re.findall(r'[가-힣A-Za-z0-9]{2,}', actual))
    return len(words & other) >= min(3, len(words)) and bool(words)


def read_evidence(article):
    url = article.get('link', '')
    result = {'status': '제목만 확인', 'url': url, 'excerpt': '',
              'checked_at': datetime.now(UTC).isoformat(), 'kind': '오피니언' if OPINION.search(article['title']) else '보도'}
    if not allowed_url(url):
        result['reason'] = '공개 원문 직접 링크를 확인하지 못함'
        return result
    try:
        for _ in range(4):
            response = requests.get(url, timeout=(4, 8), allow_redirects=False, stream=True,
                                    headers={'User-Agent': 'InsightHub/4.0 public-source reader'})
            if response.status_code in (301, 302, 303, 307, 308):
                destination = urljoin(url, response.headers.get('Location', ''))
                response.close()
                if not allowed_url(destination):
                    result['reason'] = '로그인·외부 경유 링크로 이동하지 않음'
                    return result
                url = destination
                continue
            response.raise_for_status()
            if 'html' not in response.headers.get('Content-Type', '').lower():
                response.close()
                result['reason'] = '공개 HTML 본문이 아님'
                return result
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > 2_500_000:
                    raise ValueError('원문 크기 제한')
                chunks.append(chunk)
            encoding = response.encoding if response.encoding and response.encoding.lower() != 'iso-8859-1' else 'utf-8'
            source = b''.join(chunks).decode(encoding, errors='replace')
            response.close()
            if re.search(r'"isAccessibleForFree"\s*:\s*(?:false|"false")', source, re.I):
                result['reason'] = '접근 제한이 표시된 원문'
                return result
            parser = ArticleParser(); parser.feed(source)
            title = parser.page_title or clean(' '.join(parser.title_parts))
            if not _title_matches(article['title'], title):
                result['reason'] = '기사 제목과 원문 페이지가 일치하지 않음'
                return result
            body = clean(' '.join(parser.parts))
            result['url'], result['page_title'] = url, title
            if len(body) >= 120:
                result.update(status='본문 일부 확인', excerpt=' '.join(body.split()[:24])[:480])
            elif len(parser.description) >= 60:
                result.update(status='공개 요약문 확인', excerpt=' '.join(parser.description.split()[:24])[:300])
            else:
                result['reason'] = '기사 본문을 식별하지 못함'
            return result
        result['reason'] = '이동 횟수 제한'
    except (requests.RequestException, ValueError, LookupError):
        result['reason'] = '공개 원문 확인 실패 · 저장된 제목 유지'
    return result


def strategic_mou_context(article):
    """금액·미래형 구호만으로 통과시키지 않는다. 확인한 본문과 검토 보고서를 연결한다."""
    from insights import REPORTS
    title = article['title']
    evidence = article.get('evidence', {})
    if not MOU.search(title) or evidence.get('status') != '본문 일부 확인':
        return None
    body = evidence.get('excerpt', '')
    if len(body) < 120 or not re.search(r'공동개발|공동 개발|실증|생산시설|저장시설|공급망|연료.{0,10}조달|PPA|장기.{0,10}조달|설비|연구개발|전력망|송전', body, re.I):
        return None
    trends = [
        ('전력 수요와 전력망 투자', r'전력망|송전|데이터센터|전력수요|전력 수요', '전력망·수요', '전력 공급·망 연계 역량을 준비하는 사업 방향'),
        ('에너지 전환과 공급 안정', r'수소|해상풍력|재생에너지|탈탄소|탄소중립|에너지 안보', '탄소·전환', '전원·연료 전환 역량을 준비하는 사업 방향'),
        ('에너지 조달 다변화', r'LNG|천연가스|연료.{0,10}조달|유연탄', '연료·환율', '연료 조달·공급망을 넓히려는 사업 방향'),
    ]
    for trend, pattern, topic, direction in trends:
        if not re.search(pattern, title, re.I) or not re.search(pattern, body, re.I):
            continue
        refs = [r['id'] for r in REPORTS if topic in r['topics'] and r.get('reviewed')]
        if refs:
            return {'reviewed': True, 'trend': trend, 'direction': direction, 'report_ids': refs[:1],
                    'reason': f'이래서 가져왔어요: {trend}와 맞물려 {direction}을 보여주는 단서. 공개 본문 일부와 공식 자료의 일반 경로를 연결했으며, 협약은 확정 계약·매출이 아님.'}
    return None


def enrich_articles(articles, selected, maximum=9):
    """핵심 기사 5개 + 산업 변화가 있는 협약 후보 2개 + 오피니언 2개만 확인한다."""
    by_id = {a['id']: a for a in articles}
    targets = list(selected[:5])
    targets += [a for a in articles if MOU.search(a['title']) and not OPINION.search(a['title'])
                and re.search(r'전력망|송전|데이터센터|재생에너지|수소|LNG|유연탄|탄소|에너지', a['title'], re.I)][:2]
    targets += [a for a in articles if OPINION.search(a['title'])][:2]
    targets = list({a['id']: a for a in targets}.values())[:maximum]
    with ThreadPoolExecutor(max_workers=4) as pool:
        checked = list(pool.map(read_evidence, targets))
    for article, evidence in zip(targets, checked):
        item = by_id[article['id']]
        item['evidence'] = evidence
        context = strategic_mou_context(item)
        if context:
            item['mou_context'] = context
        else:
            item.pop('mou_context', None)
    return list(by_id.values())
