"""경제·시사 뉴스와 산업·기업 쟁점을 함께 확인하는 한글 Streamlit 앱."""
from datetime import datetime
import html
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from news_core import (ROOT, SEARCHES, INDUSTRIES, UTC, analysis_cards, company_query,
                       deduplicate, fetch_news, filter_articles, format_kst, load_json, parse_time)

st.set_page_config(page_title='경제·산업 인사이트 허브', page_icon='📰', layout='wide')
st.markdown('''<style>
.block-container {max-width:1200px; padding-top:2rem;}
html, body, [class*="css"] {font-size:16px;}
.news-title {font-size:1.08rem;font-weight:650;line-height:1.55;margin:0 0 .5rem;}
.hero-tag {color:#147D73; font-weight:700;letter-spacing:.06em;font-size:.85rem;}
[data-testid="stMetric"] {background:white;border:1px solid #E0E8ED;padding:1rem;border-radius:12px;}
</style>''', unsafe_allow_html=True)
st.markdown('<div class="hero-tag">뉴스에서 쟁점으로</div>', unsafe_allow_html=True)
st.title('경제·산업 인사이트 허브')
st.caption('경제·시사 뉴스 → 산업별 분류 → 관심 기업의 확인할 쟁점 · 무료 RSS · 유료 API 없음')

config = load_json(ROOT / 'config.json')
with st.sidebar:
    st.header('관심 설정')
    topics = st.multiselect('뉴스 분야', [*SEARCHES, '기타'], default=list(SEARCHES))
    industry = st.selectbox('산업 선택', ['전체', *INDUSTRIES, '기타'])
    days = st.selectbox('조회 기간', [1, 3, 7, 14, 30], index=2, format_func=lambda n: f'최근 {n}일')
    company = st.text_input('관심 기업명', placeholder='예: 한국서부발전', max_chars=60, key='company').strip()
    alias = st.text_input('다른 표기 (쉼표 구분)', placeholder='예: 서부발전, KOWEPO', max_chars=150, key='aliases').strip()
    st.caption('기업 이름은 기사 제목에서 찾습니다. 약칭을 추가하면 검색 범위를 넓힐 수 있습니다.')
    search_company = st.button('관심 기업 뉴스 추가 검색', disabled=not company, use_container_width=True)
    refresh = st.button('최신 뉴스 수집', use_container_width=True)
    st.divider()
    st.caption('일일 자동 수집 관심 기업')
    st.write(' · '.join(config.get('companies', [])) or '설정 없음')
    st.caption('이 목록은 GitHub의 config.json에서 수정합니다. 화면 검색은 현재 브라우저 세션에만 적용됩니다.')
    st.caption('자동 수집 예정: 매일 오전 7:17 (한국시간)')

@st.cache_data(ttl=900, show_spinner=False)
def latest_news():
    return fetch_news()

@st.cache_data(ttl=1800, show_spinner=False)
def extra_company(name):
    return fetch_news({'관심 기업': company_query(name)}, max_per_topic=40, direct=False)

news_path = ROOT / 'data/news.json'
try:
    saved = json.loads(news_path.read_text(encoding='utf-8')) if news_path.exists() else {}
    if not isinstance(saved, dict) or not isinstance(saved.get('articles', []), list):
        raise ValueError('저장 파일 형식 오류')
except (OSError, ValueError) as exc:
    saved = {}
    st.warning('저장된 기사 파일을 읽지 못했습니다. 최신 뉴스 수집으로 다시 시도하세요.')
status = load_json(ROOT / 'data/status.json')
articles = saved.get('articles', [])
errors = []
mode = '일일 수집 저장본'
if refresh:
    latest_news.clear()
    extra_company.clear()
if refresh or not articles:
    with st.spinner('공개 RSS에서 최신 뉴스를 확인하고 있습니다...'):
        rows, errors = latest_news()
    st.session_state['live_news'] = rows
    st.session_state['live_errors'] = errors
    st.session_state['live_time'] = datetime.now(UTC).isoformat()
if st.session_state.get('live_news'):
    articles = deduplicate(st.session_state['live_news'] + articles)
    mode = '저장본 + 이번 접속 수집'
errors = st.session_state.get('live_errors', errors)
if search_company:
    try:
        with st.spinner('관심 기업의 추가 뉴스를 찾고 있습니다...'):
            rows, company_errors = extra_company(company)
        st.session_state['company_news'] = rows
        st.session_state['company_errors'] = company_errors
        st.session_state['searched_company'] = company
        if not rows and not company_errors:
            st.info('추가 검색에서 기사를 찾지 못했습니다.')
    except ValueError as exc:
        st.warning(str(exc))
if company == st.session_state.get('searched_company'):
    articles = deduplicate(st.session_state.get('company_news', []) + articles)
    errors = [*errors, *st.session_state.get('company_errors', [])]

last_update = saved.get('updated_at', '')
st.caption(f"데이터: {mode} · 저장본 갱신: {format_kst(last_update)} (한국시간)")
if st.session_state.get('live_time'):
    st.caption('이번 접속 수집 시도: ' + format_kst(st.session_state['live_time']) + ' (한국시간)')
if status.get('ok') is False:
    st.warning('최근 예약 수집이 실패했습니다. 마지막으로 저장된 기사를 표시합니다.')
if (d := parse_time(last_update)) and (datetime.now(UTC) - d).total_seconds() > 172800:
    st.warning('저장본이 48시간 이상 갱신되지 않았습니다. GitHub Actions 실행 상태를 확인하세요.')
all_errors = list(dict.fromkeys([*status.get('errors', []), *errors]))
if all_errors:
    with st.expander(f'수집 상태 · 접속 실패 피드 {len(all_errors)}개'):
        st.write('일부 출처의 결과가 누락될 수 있습니다. 저장본과 접속 가능한 피드의 기사는 계속 표시합니다.')
        for err in all_errors:
            st.caption(err)

keyword = st.text_input('기사 제목 검색', placeholder='금리, 관세, 데이터센터 등', max_chars=80, key='keyword')
base = filter_articles(articles, topics=topics, industry=industry, keyword=keyword, days=days)
names = [company, *[s.strip() for s in alias.split(',') if s.strip()]] if company else []
company_rows = filter_articles(base, days=days, company_names=names) if names else []
active = company_rows if company else base
m1, m2, m3 = st.columns(3)
m1.metric('기간·분류에 맞는 뉴스', f'{len(base):,}건')
m2.metric('관심 기업 뉴스', f'{len(company_rows):,}건' if company else '기업명 입력')
m3.metric('산업·기업 쟁점', f'{len(analysis_cards(active))}개')
if not topics:
    st.info('뉴스 분야를 한 개 이상 선택하세요.')


def render_news(rows, key):
    if not rows:
        st.info('조건에 맞는 기사가 없습니다. 기간·분야·기업명과 약칭을 확인하세요.')
        return
    page_size = 15
    pages = max(1, (len(rows) + page_size - 1) // page_size)
    page = st.selectbox('페이지', range(1, pages + 1), key=key,
                        format_func=lambda n: f'{n} / {pages}')
    for a in rows[(page - 1) * page_size:page * page_size]:
        with st.container(border=True):
            st.markdown('<p class="news-title">' + html.escape(a['title']) + '</p>', unsafe_allow_html=True)
            st.caption(' · '.join([a.get('source', ''), format_kst(a.get('published', '')) + ' KST']))
            st.caption('분야: ' + ', '.join(a.get('categories', [])) + ' / 산업: ' + ', '.join(a.get('industries', [])))
            if a.get('link'):
                st.link_button('출처 기사 열기', a['link'])
    csv = pd.DataFrame([{'제목': a['title'], '발행일(한국시간)': format_kst(a.get('published', '')),
                        '언론사': a.get('source', ''), '분야': ', '.join(a.get('categories', [])),
                        '산업': ', '.join(a.get('industries', [])), '링크': a.get('link', '')} for a in rows])
    st.download_button('조회 결과 CSV 내려받기', csv.to_csv(index=False).encode('utf-8-sig'),
                       file_name='insight_news.csv', mime='text/csv', key=key + '_csv')


news_tab, analysis_tab, company_tab, guide_tab = st.tabs(['뉴스 모아보기', '산업·기업 쟁점', '관심 기업', '수집·이용 안내'])
with news_tab:
    st.subheader('경제·시사 뉴스')
    st.caption('제목·출처·날짜만 모아 보여줍니다. 기사 내용은 출처에서 확인하세요.')
    render_news(base, 'news_page')
with analysis_tab:
    st.subheader(f'{company} 관련 쟁점' if company else '선택한 산업의 쟁점')
    st.info('아래 영향 경로와 질문은 키워드별 고정 점검표입니다. 기사 내용이나 기업 실적을 AI가 분석한 결과가 아닙니다.')
    cards = analysis_cards(active)
    if not cards:
        st.info('현재 뉴스에서 점검표와 연결되는 쟁점을 찾지 못했습니다.')
    for c in cards:
        with st.container(border=True):
            st.markdown(f"### {c['name']} · 관련 기사 {c['count']}건")
            st.write(c['path'])
            for q in c['questions']:
                st.write('• ' + q)
            with st.expander('연결된 기사 근거'):
                for a in c['evidence']:
                    st.write(a['title'])
                    if a.get('link'):
                        st.link_button('출처 확인', a['link'])
    if active:
        note = '\n'.join(['# 산업·기업 쟁점 점검', f'대상: {company or industry}',
                          f'작성 시각: {format_kst(datetime.now(UTC).isoformat())} KST',
                          '키워드 기반 점검표이며, 영향 방향·실적은 원문과 공시에서 확인해야 합니다.',
                          *[f"\n## {c['name']}\n{c['path']}\n" + '\n'.join('- ' + q for q in c['questions']) +
                            '\n근거 기사:\n' + '\n'.join(a['title'] + '\n' + a.get('link', '') for a in c['evidence']) for c in cards]])
        st.download_button('쟁점·질문 메모 내려받기', note, 'issue_notes.md', 'text/markdown')
with company_tab:
    st.subheader('관심 기업 뉴스와 확인 자료')
    if not company:
        st.info('왼쪽에서 관심 기업명을 입력하세요.')
    else:
        st.write(f'검색 이름: {", ".join(names)}')
        st.caption('제목에 이름이 없는 기사는 누락될 수 있습니다. 뉴스 추가 검색은 기업명으로 Google RSS를 조회합니다.')
        c1, c2 = st.columns(2)
        c1.link_button('전자공시 DART', 'https://dart.fss.or.kr/')
        c2.link_button('공공기관 경영정보 ALIO', 'https://www.alio.go.kr/')
        render_news(company_rows, 'company_page')
with guide_tab:
    st.markdown('''### 어떻게 작동하나요?
- Google 뉴스 검색 RSS와 한국경제·뉴시스의 공개 RSS에서 기사 제목·출처·날짜·링크를 수집합니다.
- URL 또는 출처명을 제외한 정규화 제목이 같으면 하나로 합칩니다. 서로 다른 제목의 같은 사건은 남을 수 있습니다.
- 뉴스 분야·산업·쟁점은 제목의 키워드 규칙으로 여러 개를 붙입니다. 검색한 분야를 강제로 분류에 넣지 않습니다.
- GitHub Actions가 매일 오전 7:17에 수집합니다. 최근 30일, 최대 3,000건을 저장합니다.
- 수집이 모두 실패하면 이전 기사는 보존합니다. 화면의 새로 수집한 결과는 세션에만 남습니다.
- 산업·기업 쟁점은 영향 경로와 확인 질문을 제공하는 점검표입니다. 재무수치 추출·AI 요약·투자추천은 포함하지 않습니다.

### 무료 운영 범위
공개 GitHub 저장소 + 표준 ubuntu-latest 실행 환경 + Streamlit Community Cloud를 사용합니다.
API 키·카드 등록·유료 서비스가 필요 없습니다. 관심 기업 설정과 수집 데이터는 공개 저장소에 공개됩니다.

### 예약 수집과 접속 제한
GitHub 예약 실행은 지연될 수 있고, 공개 저장소에 60일간 활동이 없으면 비활성화될 수 있습니다.
앱은 장시간 방문이 없으면 잠들 수 있습니다. 다시 열 때 깨우면 됩니다. 예약 수집은 GitHub에서 별도로 실행됩니다.
RSS 제공처 사정에 따라 연결 실패나 기사 누락이 생길 수 있습니다.
''')
    st.link_button('GitHub Actions 무료 조건', 'https://docs.github.com/en/actions/concepts/billing-and-usage')
    st.link_button('Streamlit 배포 안내', 'https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy')
