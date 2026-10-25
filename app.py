"""경제·시사 뉴스와 산업·기업 쟁점을 함께 확인하는 한글 Streamlit 앱."""
from datetime import datetime
import html
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from news_core import (ROOT, SEARCHES, INDUSTRIES, UTC, analysis_cards, company_query,
                       deduplicate, fetch_news, filter_articles, format_kst, load_json, parse_time)
from insights import (DEFAULT_PROFILES, REPORTS, SECTORS, analysis_packet, build_insights,
                      cross_connections, curate_brief, curate_company_brief, news_quality, normalize_profiles, related_articles)
from watchlist_ui import render_watchlist, watchlist_download
from ai_insights import generate as generate_ai, ready as ai_ready
from reader_ui import reading_items

st.set_page_config(page_title='경제·산업 인사이트 허브', page_icon='📰', layout='wide')
st.markdown('''<style>
:root {--ink:#303A2A;--muted:#617052;--sage:#5B783D;--line:#DDE5D1;--paper:#FFFFFA;}
.block-container {max-width:1120px;padding-top:2rem;padding-bottom:4rem;}
html,body,[class*="css"] {font-size:16px;}
[data-testid="stMain"] {background:#F7F8F2;}
[data-testid="stSidebar"] {background:#EEF3E5;border-right:1px solid var(--line);}
[data-testid="stMarkdownContainer"] p {line-height:1.85;}
h1 {font-size:2.1rem!important;letter-spacing:-.045em;color:var(--ink);}
h2 {font-size:1.65rem!important;letter-spacing:-.025em;}
h3 {font-size:1.25rem!important;line-height:1.55!important;}
.hero-tag {display:inline-block;color:#5B783D;background:#E8F0DA;border:1px solid #D3E0BC;border-radius:20px;padding:5px 12px;font-size:.85rem;font-weight:650;}
[data-testid="stMetric"] {background:var(--paper);border:1px solid var(--line);padding:1rem 1.2rem;border-radius:16px;}
[data-testid="stMetricValue"] {color:var(--sage);}
[data-testid="stTabs"] [role="tablist"] {gap:8px;border-bottom:1px solid var(--line);padding:8px 0 12px;}
[data-testid="stTabs"] [role="tab"] {border-radius:10px;padding:9px 17px;height:auto;color:#637154;}
[data-testid="stTabs"] [aria-selected="true"] {background:#E2EDCE;color:#415E2D;font-weight:700;}
[data-testid="stTabs"] [data-baseweb="tab-highlight"] {background:transparent;}
[data-testid="stVerticalBlockBorderWrapper"]>div {border-color:var(--line)!important;border-radius:16px!important;}
[data-testid="stExpander"] {background:var(--paper);border-radius:12px;}
[data-testid="stAlert"] {border-radius:12px;}
[data-testid="stTable"] {font-size:1rem;}
.section-tag {display:inline-block;margin:1.5rem 0 .55rem;padding:4px 10px;border-radius:7px;font-size:.85rem;font-weight:700;background:#E8F0DA;color:#486431;}
.section-tag.blue {background:#E6ECF3;color:#405C76;}
.section-tag.sand {background:#F0E9DB;color:#75603B;}
.news-title {font-size:1.1rem;font-weight:650;line-height:1.6;margin:0 0 .5rem;}
@media(max-width:640px){.block-container{padding:1.2rem 1rem 3rem;}h1{font-size:1.65rem!important;}[data-testid="stTabs"] [role="tab"]{padding:8px 10px;}html,body{font-size:16px;}}
</style>''', unsafe_allow_html=True)
st.markdown('<div class="hero-tag">뉴스에서 쟁점으로</div>', unsafe_allow_html=True)
st.title('경제·산업 인사이트 허브')
st.caption('에너지 · 경제 · 시사 · 금융  ·  뉴스 5개, 깊이 읽는 주제 하나')
status_area = st.container()

brief_tab, study_tab, company_tab, library_tab = st.tabs(
    ['오늘의 브리핑', '오늘의 공부', '관심기업', '저장·복습'])
with company_tab:
    st.caption('기관 준비가 필요할 때 찾아보세요. 등록한 기업은 기본 브리핑의 기사 수·분야를 바꾸지 않습니다.')
    insight_tab, related_tab, watch_tab = st.tabs(['기업 인사이트', '관련 뉴스', '관심 기업 등록'])
with brief_tab:
    news_tab = st.expander('더 찾아보기 · 전체 검색 자료')
    guide_tab = st.expander('수집·이용 안내')
with study_tab:
    reports_tab = st.expander('공식 자료와 새 보고서 후보')
with watch_tab:
    st.subheader('관심 기업 등록과 보관')
    st.caption('기본 기업: 한국서부발전 · 한국도로공사 · 한국토지주택공사(LH). 최대 10개까지 등록할 수 있습니다.')
    profiles = render_watchlist()
    watchlist_download(profiles)
    st.caption('기업 목록은 이 브라우저에 저장됩니다. 등록만으로 기관별 기사를 매일 모으지는 않습니다. 준비가 필요할 때 왼쪽에서 기업을 선택하고 뉴스 추가 검색을 누르세요.')

config = load_json(ROOT / 'config.json')
profile_names = [p['name'] for p in profiles]
if st.session_state.get('watch_company') not in ['직접 입력', *profile_names]:
    st.session_state['watch_company'] = profile_names[0] if profile_names else '직접 입력'

def select_registered_company():
    selected = next((p for p in profiles if p['name'] == st.session_state['watch_company']), None)
    st.session_state['company'] = selected['name'] if selected else ''
    st.session_state['aliases'] = ', '.join(selected['aliases']) if selected else ''

if 'company' not in st.session_state:
    select_registered_company()

with st.sidebar:
    st.header('읽기 설정')
    selected_name = st.selectbox('등록 기업 선택', ['직접 입력', *profile_names],
                                key='watch_company', on_change=select_registered_company)
    topics = st.multiselect('뉴스 분야', [*SEARCHES, '기타'], default=list(SEARCHES))
    industry = st.selectbox('산업 선택', ['전체', *INDUSTRIES, '기타'], key='industry')
    days = st.selectbox('조회 기간', [1, 3, 7, 14, 30], index=1, format_func=lambda n: f'최근 {n}일', key='days')
    company = st.text_input('관심 기업명', placeholder='예: 한국서부발전', max_chars=60, key='company').strip()
    alias = st.text_input('다른 표기 (쉼표 구분)', placeholder='예: 서부발전, KOWEPO', max_chars=150, key='aliases').strip()
    st.caption('등록한 사업 분야를 이용해 기업명 없는 기사도 연결합니다. 단순 협약·행사·지원 홍보는 기본 제외합니다.')
    show_promo = False
    search_company = st.button('관심 기업 뉴스 추가 검색', disabled=not company, use_container_width=True, key='search_company')
    refresh = st.button('최신 뉴스 수집', use_container_width=True, key='refresh')
    st.divider()
    st.caption('매일 자동 수집: 에너지·경제·시사·금융 등 일반 현안')
    st.caption('관심기업 등록은 면접 준비용입니다. 기본 화면에는 기업별 기사 정원을 두지 않습니다.')
    st.caption('자동 수집 예정: 매일 오전 7:17 (한국시간)')
    if selected_name == '직접 입력':
        manual_sector = st.selectbox('직접 입력 기업의 사업 분야', SECTORS, index=len(SECTORS)-1)

profile = next((p for p in profiles if p['name'] == company), None)
if profile is None and company:
    try:
        profile = normalize_profiles([{'name': company, 'aliases': [x.strip() for x in alias.split(',')],
                                      'sector': locals().get('manual_sector', '기타'), 'keywords': []}])[0]
    except ValueError:
        st.warning('기업명에 허용되지 않은 문자가 있습니다. 한글·영문·숫자로 입력하세요.')
if profile:
    profile = {**profile, 'aliases': list(dict.fromkeys([*profile['aliases'], *[x.strip() for x in alias.split(',') if x.strip()]]))}

@st.cache_data(ttl=900, show_spinner=False)
def latest_news():
    return fetch_news()

@st.cache_data(ttl=1800, show_spinner=False)
def extra_company(name, sector='기타'):
    searches = {'관심 기업': company_query(name)}
    related_searches = {
        '발전·에너지': '전력망 OR 연료비 OR 유연탄 OR LNG OR 출력제어',
        '도로·교통': '고속도로 OR 통행료 OR 교통량 OR 도로 공사비',
        '토지·주택': '공공주택 OR 미분양 OR 공사비 OR 부동산 PF',
        '금융·보험': '은행 금리 OR 연체율 OR 부동산 PF',
        '제조·수출': '관세 OR 수출 OR 공급망 OR 원자재',
    }
    if sector in related_searches:
        searches['기업 파급 경로'] = related_searches[sector]
    return fetch_news(searches, max_per_topic=40, direct=False)

news_path = ROOT / 'data/news.json'
try:
    saved = json.loads(news_path.read_text(encoding='utf-8')) if news_path.exists() else {}
    if not isinstance(saved, dict) or not isinstance(saved.get('articles', []), list):
        raise ValueError('저장 파일 형식 오류')
except (OSError, ValueError) as exc:
    saved = {}
    st.warning('저장된 기사 파일을 읽지 못했습니다. 최신 뉴스 수집으로 다시 시도하세요.')
status = load_json(ROOT / 'data/status.json')
articles = deduplicate(saved.get('articles', []))
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
general_articles = list(articles)
if search_company:
    try:
        with st.spinner('관심 기업의 추가 뉴스를 찾고 있습니다...'):
            rows, company_errors = extra_company(company, profile['sector'] if profile else '기타')
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
with status_area:
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
omitted = [a for a in base if not news_quality(a['title'], a)['include']]
if not show_promo:
    base = [a for a in base if news_quality(a['title'], a)['include']]
names = [company, *[s.strip() for s in alias.split(',') if s.strip()]] if company else []
company_rows = filter_articles(base, days=days, company_names=names) if names else []
related = related_articles(base, profile, include_promo=show_promo) if profile else []
cards = build_insights(related, profile) if profile else []
connections = cross_connections(cards, profile) if profile else []
daily_base = filter_articles(general_articles, topics=topics, industry=industry, keyword=keyword, days=days)
brief = curate_brief(daily_base)
learning = load_json(ROOT / 'data/daily_learning.json')
learning_status = load_json(ROOT / 'data/learning_status.json')
with status_area:
    m1, m2, m3 = st.columns(3)
    m1.metric('오늘의 이슈', f'{len(brief)}건')
    m2.metric('오늘의 공부', '1주제' if learning.get('study') else '생성 대기')
    m3.metric('하루 읽기', '약 10분')
    if not topics:
        st.info('뉴스 분야를 한 개 이상 선택하세요.')

with brief_tab:
    st.subheader('짧게 읽는 오늘 · 최대 5개 이슈')
    st.caption('최근 3일의 에너지·경제·시사·금융 현안을 고르게 추립니다. 같은 논점은 줄이고 부족하면 채우지 않습니다. 관심기업 등록과 독립적입니다.')
    st.caption('MOU는 기본 제외합니다. 산업 흐름과 사업 방향을 공개 본문·공식 자료로 연결한 경우만 선정 이유와 함께 보여줍니다.')
    summaries = {x['news_id']: x for x in learning.get('briefs', [])}
    source_ids = {x.get('article_id'): x['id'] for x in learning.get('sources', {}).get('news', [])}
    items = []
    for article in brief:
        summary = summaries.get(source_ids.get(article['id']), {})
        evidence = article.get('evidence', {})
        title_only = evidence.get('status', '제목만 확인') == '제목만 확인'
        items.append({'id': article['id'], 'kind': 'news', 'title': article['title'],
                      'group': article['brief_group'], 'date': format_kst(article.get('published', '')),
                      'url': article.get('link', ''),
                      'status': evidence.get('status', '제목만 확인') + ' · ' + article.get('source', ''),
                      'summary': '' if title_only else summary.get('summary') or '공개 근거를 확인한 기사입니다. 원문에서 배경을 살펴보세요.',
                      'reason': article['brief_reason'] if article.get('mou_context') or title_only else summary.get('why', article['brief_reason']),
                      'details': ['생각할 질문: ' + article['brief_question']]})
    reading_items(items, 'daily_reader')
    if summaries:
        st.caption('AI 요약 작성: ' + format_kst(learning.get('updated_at', '')) + ' KST · 확인 범위 밖의 수치·인과관계는 원문 대조가 필요합니다.')

with study_tab:
    st.subheader('하나의 이슈로 배경과 논리 공부')
    if learning_status.get('ok') is False:
        st.warning('최근 학습자료 작성에 실패해 이전 자료를 유지합니다. ' + learning_status.get('error', ''))
    study = learning.get('study', {})
    if study:
        st.caption('작성: ' + format_kst(learning.get('updated_at', '')) + ' KST · 공개 근거를 연결한 AI 학습 초안')
        if (stamp := parse_time(learning.get('updated_at', ''))) and (datetime.now(UTC)-stamp).total_seconds() > 3*86400:
            st.warning('3일 이상 지난 학습자료입니다. 새 이슈로 갱신되기 전까지 과거 자료로 참고하세요.')
        st.markdown('### ' + study['topic'])
        st.write(study['background'])
        st.info('생각할 질문: ' + study['question'])
        source_index = {x['id']: x for group in learning.get('sources', {}).values() for x in group}
        def source_names(refs):
            return ', '.join(dict.fromkeys(source_index.get(ref, {}).get('institution') or source_index.get(ref, {}).get('source') or '기사 자료' for ref in refs))
        if learning.get('editorial_review'):
            st.caption('편집 검토 예시 · ' + learning['editorial_review']['notes'])
        depth = study.get('depth', {})
        if depth:
            def section(number, title, tone=''):
                st.markdown(f'<div class="section-tag {tone}">{number} · {title}</div>', unsafe_allow_html=True)
            section('01', '사건을 먼저 파악하기')
            event = depth['event']
            with st.container(border=True):
                labels = [('누가', 'who'), ('언제', 'when'), ('어디·적용 범위', 'where'),
                          ('무엇을', 'what'), ('확인된 이유', 'why_known'), ('확인된 진행 방식', 'how_known')]
                st.table({'항목': [label for label, _ in labels], '확인한 내용': [event[key] for _, key in labels]})
                st.caption('사건 근거: ' + source_names(event['source_ids']))
            st.markdown('**왜 지금 이 문제인가**'); st.write(depth['why_now']['explanation'])
            section('02', '이 뉴스를 읽는 데 필요한 기초', 'blue')
            for concept in depth['foundations']:
                with st.container(border=True):
                    st.markdown('#### ' + concept['term'])
                    st.write(concept['explanation'])
                    st.markdown('**이 사건에 적용하면**'); st.write(concept['application'])
            with st.expander('개념 두 개를 나란히 비교하기'):
                st.table({'개념': [study['term_a'], study['term_b']], '뜻': [study['meaning_a'], study['meaning_b']]})
                st.write(study['difference'])
            section('03', '왜 그런 영향이 생기는가')
            st.caption('아래 경로와 연결 해석은 앱의 학습용 조건부 설명입니다. 출처가 현재 효과의 크기까지 입증한 것은 아닙니다.')
            for i, step in enumerate(depth['mechanism'], 1):
                with st.container(border=True):
                    st.markdown('**' + str(i) + '. ' + step['change'] + '**')
                    st.write(step['because'])
                    st.caption('성립 조건: ' + step['condition'] + ' · 근거: ' + source_names(step['source_ids']))
            section('04', '산업·사회·경제와 연결해서 읽기', 'sand')
            for connection in depth['connections']:
                with st.container(border=True):
                    st.caption(connection['kind'] + ' 연결 · 조건부 해석')
                    st.markdown('#### ' + connection['target'])
                    st.write(connection['pathway'])
                    st.markdown('**이 연결이 성립하려면**'); st.write(connection['condition'])
                    st.markdown('**반대로 볼 점·아직 모르는 점**'); st.write(connection['limit'])
                    st.caption('출발 근거: ' + source_names(connection['source_ids']))
            section('05', '판단을 바꾸는 조건', 'blue')
            for label, field in [('한쪽 논리', 'claim'), ('반론', 'counter'), ('판단 조건', 'condition')]:
                st.markdown('**' + label + '**'); st.write(study[field])
            st.caption('확인할 지표: ' + ' · '.join(study['check_metrics']))
            section('06', '내 생각으로 정리하기')
            for exercise in depth['thinking_questions']:
                st.markdown('**' + exercise['question'] + '**')
                with st.expander('생각할 단서'):
                    st.write(exercise['hint'])
        else:
            st.caption('이 자료는 이전 형식입니다. 다음 자동 생성부터 사건·기초·인과 경로·연결 학습을 제공합니다.')
            with st.expander('배경지식 · 헷갈리는 개념 비교', expanded=True):
                st.table({'개념': [study['term_a'], study['term_b']], '뜻': [study['meaning_a'], study['meaning_b']]})
                st.write('다른 점: ' + study['difference'])
            with st.expander('논리·반론·판단 조건 보기', expanded=True):
                for i, step in enumerate(study['logic_chain'], 1):
                    st.write(f'{i}. {step}')
                for label, field in [('한쪽 논리', 'claim'), ('반론', 'counter'), ('판단 조건', 'condition')]:
                    st.markdown('**' + label + '**'); st.write(study[field])
        source_index = {x['id']: x for group in learning.get('sources', {}).values() for x in group}
        with st.expander('뉴스·연구자료·오피니언 근거와 각각의 한계'):
            contributions = {x['source_id']: x for x in depth.get('source_contributions', [])}
            for ref in study['source_ids']:
                source = source_index.get(ref, {})
                if source:
                    st.write(ref + ' · ' + source.get('kind', '') + ' · ' + source['title'])
                    st.caption(source.get('published', '') + ' · ' + source.get('status', '발행 당시 요지를 검토한 자료'))
                    st.write(source.get('summary', source.get('excerpt', '')))
                    contribution = contributions.get(ref)
                    if contribution:
                        st.write('확인한 내용: ' + contribution['supports'])
                        st.caption('입증하지 않는 내용: ' + contribution['does_not_prove'])
                    if source.get('context'):
                        with st.expander('확인한 공개 문맥 발췌'):
                            st.write(source['context'])
                    if source.get('scope'): st.caption(source['scope'])
                    if source.get('url'): st.link_button('출처 원문', source['url'])
            views = study.get('opinion_views', [])
            if not views:
                st.caption('이번 주제와 연결해 확인한 공개 오피니언이 없습니다. 가상의 전문가 의견으로 채우지 않습니다.')
            for view in views:
                source = source_index.get(view['source_id'], {})
                st.markdown('**필자의 의견 · 보도 사실과 구분**'); st.write(view['view'])
                if source.get('url'): st.link_button(source['title'], source['url'])
        details = ['배경: ' + study['background'], ' → '.join(study['logic_chain']),
                   '논리: ' + study['claim'], '반론: ' + study['counter'], '조건: ' + study['condition']]
        if depth:
            details += ['기초 · ' + x['term'] + ': ' + x['explanation'] + ' 적용: ' + x['application'] for x in depth['foundations']]
            details += ['작동 경로 · ' + x['change'] + ': ' + x['because'] + ' 조건: ' + x['condition'] for x in depth['mechanism']]
            details += ['연결 · ' + x['target'] + ': ' + x['pathway'] + ' 조건: ' + x['condition'] + ' 한계: ' + x['limit'] for x in depth['connections']]
            details += ['질문 · ' + x['question'] + ' 단서: ' + x['hint'] for x in depth['thinking_questions']]
        reading_items([{'id': 'study:' + learning.get('updated_at', '')[:10], 'kind': 'study', 'group': '논리 공부',
                        'title': study['topic'], 'date': format_kst(learning.get('updated_at', '')),
                        'summary': study['question'], 'details': details, 'url': ''}], 'study_bookmark')
        st.caption('하루 한 주제를 충분히 읽고, 마지막 질문은 내 생각으로 정리해 보세요. 메모는 아래 저장 후 남길 수 있습니다.')
    else:
        st.info('본문·공개 요약문과 공식 자료를 확인한 뒤 하루 한 주제를 생성합니다. 자료가 없으면 만든 것처럼 표시하지 않습니다.')
        for report in REPORTS[:1]:
            st.markdown('**배경 읽기 · ' + report['institution'] + '**')
            st.write(report['summary']); st.caption(report['published'] + ' · ' + report['scope'])
            st.link_button('배경 자료 원문', report['url'])

with library_tab:
    st.subheader('저장한 뉴스와 논리 · 복습')
    st.caption('안 읽은 자료부터 확인하고, 읽음 취소로 다시 복습할 수 있습니다. 메모는 외부 AI로 전송하지 않습니다.')
    reading_items([], 'reading_library', library=True)


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
            if a.get('relation'):
                st.caption('연결 이유: ' + a['relation'])
            quality = news_quality(a['title'], a)
            if quality['label'] != '분석 후보':
                st.caption(quality['label'] + ' · ' + quality['reason'])
            if a.get('link'):
                st.link_button('출처 기사 열기', a['link'])
    csv = pd.DataFrame([{'제목': a['title'], '발행일(한국시간)': format_kst(a.get('published', '')),
                        '언론사': a.get('source', ''), '분야': ', '.join(a.get('categories', [])),
                        '산업': ', '.join(a.get('industries', [])), '링크': a.get('link', '')} for a in rows])
    st.download_button('조회 결과 CSV 내려받기', csv.to_csv(index=False).encode('utf-8-sig'),
                       file_name='insight_news.csv', mime='text/csv', key=key + '_csv')


with news_tab:
    st.subheader('경제·시사 뉴스')
    st.caption('제목·출처·날짜만 모아 보여줍니다. 기사 내용은 출처에서 확인하세요.')
    st.caption(f'홍보·일상 공지 후보 {len(omitted)}건 ' + ('포함 중' if show_promo else '기본 제외 중') + ' · 제목 기준이며 원문 의도를 판정한 결과는 아닙니다.')
    render_news(base, 'news_page')
with insight_tab:
    st.subheader(f'{company} · 기관 준비용 인사이트' if company else '기업을 선택하세요')
    st.info('아래 기본 인사이트는 검토한 공식 자료 요지와 기사 제목의 단서를 연결한 규칙 기반 초안입니다. 대응·교차 해석은 앱의 조건부 제안이며 연구기관의 직접 권고와 구별합니다. 별도의 AI 심층 초안도 같은 공개 근거를 사용하며, 새 보고서 전문을 자동으로 읽지는 않습니다.')
    if profile:
        st.caption(profile['sector'] + ' · ' + (profile['business'] or '직접 등록한 사업 분야'))
    if not cards:
        st.info('공식 자료와 연결할 기사 단서가 부족합니다. 뉴스 추가 검색·기간 확대 또는 사업 분야 등록을 확인하세요. 근거 없는 인사이트를 만들지 않습니다.')
    for c in cards:
        with st.container(border=True):
            st.markdown(f"### {c['topic']} · 기사 단서 {c['count']}건")
            st.write(c['path'])
            st.markdown('**기업 영향 · 조건부 해석**')
            st.write(c['impact'])
            st.markdown('**대응 제안 · 앱의 해석**')
            st.write(c['response'])
            st.markdown('**반대 경로·예외**')
            st.write(c['counter'])
            st.caption('확인할 지표: ' + ' · '.join(c['metrics']))
            with st.expander('기사 단서와 공식 자료 근거'):
                for a in c['news']:
                    st.write(a['title'])
                    st.caption(a.get('relation', '') + ' · ' + format_kst(a.get('published', '')))
                    if a.get('link'):
                        st.link_button('기사 원문', a['link'])
                for r in c['reports']:
                    st.markdown('**' + r['institution'] + ' · ' + r['title'] + '**')
                    st.caption('발행: ' + r['published'] + ' · 참조 위치: ' + r['locator'])
                    st.write('자료의 진단: ' + r['summary'])
                    st.caption('적용 범위: ' + r['scope'])
                    st.link_button('공식 자료 확인', r['url'])
            st.caption(c['limits'])
    if connections:
        st.subheader('현상과 현상 연결 · 조건부 가설')
        for c in connections:
            with st.container(border=True):
                st.markdown('**' + c['title'] + '**')
                st.caption(c['basis'])
                st.write(c['connection'])
                st.write('대응 검토: ' + c['response'])
                with st.expander('두 현상의 기사·보고서 근거'):
                    for a in c['news']:
                        st.write(a['title'])
                        if a.get('link'):
                            st.link_button('연결 기사 원문', a['link'])
                    for r in c['reports']:
                        st.link_button(r['institution'] + ' · ' + r['published'] + ' 자료', r['url'])
    if profile and related:
        packet = analysis_packet(profile, related, cards)
        try:
            ai_settings = {k: st.secrets.get(k, '') for k in ('GEMINI_API_KEY', 'AI_FREE_TIER_CONFIRMED')}
        except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
            ai_settings = {}
        st.subheader('AI 심층 초안')
        st.caption('이 버튼을 누를 때만 기관 분석을 요청합니다. 최근 관련 기사 최대 4개와 검토한 공식 자료 요지·공개 사업정보를 Google Gemini에 전달합니다.')
        st.caption('기사 제목과 검토한 보고서 요지를 바탕으로 관계·예외·대응을 종합합니다. 기사 원문 전체나 기업 노출 수치를 검증한 결과는 아닙니다.')
        if not ai_ready(ai_settings):
            st.caption('현재 무료 AI 계정 연결 전입니다. 자동 AI 요청이나 과금은 발생하지 않습니다. 아래 근거 자료를 현재 ChatGPT에서 분석할 수 있습니다.')
        else:
            st.caption('무료 AI 연결됨 · 핵심 기사와 검토한 보고서 요지만 사용 · 한도·서버 오류 시 자동 재시도 없음')
        ai_status = load_json(ROOT / 'data/ai_status.json')
        if ai_status.get('ok') is False and ai_status.get('errors'):
            st.warning('최근 일일 AI 분석을 완료하지 못했습니다. 시도: ' + format_kst(ai_status.get('attempted_at', '')) + ' KST')
            st.caption(' · '.join(ai_status['errors']))
        ai_clicked = st.button('AI 심층 초안 작성', disabled=not ai_ready(ai_settings), key='ai_generate')
        if ai_clicked:
            try:
                with st.spinner('자료의 근거를 연결해 AI 초안을 작성합니다...'):
                    ai_rows = curate_company_brief(base, profile)
                    ai_cards = build_insights(ai_rows, profile)
                    result = generate_ai(profile, ai_rows, ai_cards, ai_settings)
                st.session_state['ai_draft'] = {'company': company, 'items': result,
                    'news': ai_rows[:18], 'reports': {r['id']: r for c in ai_cards for r in c['reports']},
                    'created_at': datetime.now(UTC).isoformat()}
            except ValueError as exc:
                st.warning(str(exc))
        saved_ai = load_json(ROOT / 'data/ai_insights.json')
        draft = st.session_state.get('ai_draft', {})
        if draft.get('company') != company:
            draft = saved_ai.get('companies', {}).get(company, {})
            if draft:
                st.caption('일일 AI 초안 작성: ' + format_kst(saved_ai.get('updated_at', '')) + ' KST · 입력 뉴스 갱신: ' + format_kst(saved_ai.get('news_updated_at', '')))
        if draft:
            st.warning('AI가 작성한 검토 전 초안입니다. 인용한 자료의 존재는 확인하지만 모든 주장의 사실성·인과관계를 자동 검증하지는 않습니다.')
            for item in draft['items']:
                with st.container(border=True):
                    st.markdown('### ' + item['title'])
                    for label, field in [('현상·근거 구분', 'phenomenon'), ('기업 영향', 'impact'), ('대응 제안', 'response'), ('예외·추가 확인', 'counter')]:
                        st.markdown('**' + label + '**')
                        st.write(item[field])
                    st.caption('확인 지표: ' + ' · '.join(item.get('check_metrics', [])))
                    with st.expander('AI가 연결한 입력 출처'):
                        for ref in item['news_ids']:
                            a = draft['news'][int(ref[1:])-1]
                            if a.get('link'):
                                st.link_button(ref + ' · ' + a['title'], a['link'])
                        for ref in item['report_ids']:
                            r = draft['reports'][ref]
                            st.link_button(r['institution'] + ' · ' + r['published'] + ' · ' + r['title'], r['url'])
        st.download_button('심층 분석용 근거 자료 내려받기', packet, 'company_analysis_packet.txt', 'text/plain')
        with st.expander('ChatGPT에서 더 깊이 분석하기'):
            st.caption('아래 자료를 복사하거나 내려받아 현재 ChatGPT 대화에 붙여 넣으면 근거를 확인하며 심층 분석할 수 있습니다. 앱에서 자동으로 보내지는 않습니다.')
            st.code(packet, language=None)
with related_tab:
    st.subheader('기업명 기사 + 사업에 영향을 주는 기사')
    if not company:
        st.info('왼쪽에서 관심 기업명을 입력하세요.')
    else:
        st.write(f'검색 이름: {", ".join(names)}')
        st.caption(f'기업명 직접 등장 {len(company_rows)}건 · 사업·파급 경로 연결 {len(related)}건. 관계는 제목 단서로 찾으며 실제 노출은 공시·원문에서 확인합니다.')
        c1, c2 = st.columns(2)
        c1.link_button('전자공시 DART', 'https://dart.fss.or.kr/')
        c2.link_button('공공기관 경영정보 ALIO', 'https://www.alio.go.kr/')
        render_news(related, 'company_page')
with reports_tab:
    st.subheader('공식 보고서 · 검토한 근거')
    st.caption('검토일 2026-10-13. 아래 요지는 자동 갱신되지 않으며 발행 당시의 진단입니다. 새 목록 후보를 확인된 분석으로 사용하지 않습니다.')
    for r in REPORTS:
        with st.expander(r['institution'] + ' · ' + r['title'] + ' (' + r['published'] + ')'):
            st.write(r['summary'])
            st.caption('참조 위치: ' + r['locator'] + ' · ' + r['scope'])
            st.link_button('기관 원문 확인', r['url'])
    updates = load_json(ROOT / 'data/report_updates.json')
    if updates.get('reports'):
        st.subheader('새 공식 자료 후보 · 본문 검토 전')
        st.caption('목록 갱신: ' + format_kst(updates.get('updated_at', '')) + ' KST')
        for r in updates['reports'][:15]:
            st.link_button(r['institution'] + ' · ' + r['title'], r['url'])
    for err in updates.get('errors', []):
        st.caption(err)
with guide_tab:
    st.markdown('''### 어떻게 작동하나요?
- Google 뉴스 검색 RSS와 한국경제·뉴시스의 공개 RSS에서 기사 제목·출처·날짜·링크를 수집합니다.
- URL 또는 출처명을 제외한 정규화 제목이 같으면 하나로 합칩니다. 서로 다른 제목의 같은 사건은 남을 수 있습니다.
- 뉴스 분야·산업·쟁점은 제목의 키워드 규칙으로 여러 개를 붙입니다. 검색한 분야를 강제로 분류에 넣지 않습니다.
- GitHub Actions가 매일 오전 7:17에 수집합니다. 최근 30일, 최대 3,000건을 저장합니다.
- 수집이 모두 실패하면 이전 기사는 보존합니다. 화면의 새로 수집한 결과는 세션에만 남습니다.
- 기업 인사이트는 기업의 사업 분야, 기사 제목의 단서와 검토한 공식 자료의 일반 경로를 연결하는 규칙 기반 초안입니다.
- 보고서의 진단과 앱의 기업 영향·대응 제안을 구분합니다. AI 심층 초안은 기사 제목·검토한 보고서 요지·공개 사업정보를 종합하며, 새 보고서 전문이나 기업 재무수치를 자동 검증하지 않습니다.
- MOU는 금액만으로 통과시키지 않습니다. 공개 본문 일부·산업 변화·사업 방향·검토한 공식 자료를 연결할 때만 이유를 붙여 예외로 선정합니다. 협약을 확정 계약·매출로 간주하지 않습니다.
- 관심 기업은 이 브라우저에 저장하며 목록 파일로 다른 기기에 옮길 수 있습니다. 목록은 GitHub에 자동 공개되지 않습니다.
- 매일 일반 현안을 수집하고 핵심 이슈 최대 5개·학습 주제 1개를 저장합니다. 기관명 수집과 기업별 AI 분석은 기본 자동 실행에서 제외합니다. 관심기업은 필요할 때 추가 검색합니다.
- 공식 기관 목록의 새 자료 후보는 매일 갱신합니다. 본문 검토 전에는 검토한 근거와 구분합니다.

### 무료 운영 범위
공개 GitHub 저장소 + 표준 ubuntu-latest 실행 환경 + Streamlit Community Cloud를 사용합니다.
기사 목록은 키 없이 이용할 수 있습니다. 선택 AI는 결제 미연결 무료 프로젝트의 키와 무료 확인값이 있어야 실행하며, 한도·오류 시 유료 승격·자동 재시도하지 않습니다. 기본 자동 수집 기업과 기사 메타데이터는 공개 저장소에 공개되며 앱 접근은 비공개입니다.

### 예약 수집과 접속 제한
GitHub 예약 실행은 지연될 수 있고, 공개 저장소에 60일간 활동이 없으면 비활성화될 수 있습니다.
앱은 장시간 방문이 없으면 잠들 수 있습니다. 다시 열 때 깨우면 됩니다. 예약 수집은 GitHub에서 별도로 실행됩니다.
RSS 제공처 사정에 따라 연결 실패나 기사 누락이 생길 수 있습니다.
''')
    st.link_button('GitHub Actions 무료 조건', 'https://docs.github.com/en/actions/concepts/billing-and-usage')
    st.link_button('Streamlit 배포 안내', 'https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy')
