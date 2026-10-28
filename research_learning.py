"""ChatGPT가 직접 조사한 학습자료를 검증하고 읽는다. 외부 AI를 호출하지 않는다."""
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from news_core import UTC, atomic_json, format_kst, parse_time


def validate_research(value):
    if not isinstance(value, dict) or value.get('schema_version') != 1:
        raise ValueError('조사 학습자료의 형식이 맞지 않습니다.')

    def sentence(item, key, low=1, high=2000):
        text = item.get(key) if isinstance(item, dict) else None
        if not isinstance(text, str) or not low <= len(text.strip()) <= high:
            raise ValueError('조사 학습자료 항목 오류: ' + key)

    for key in ('id', 'topic', 'overview', 'question', 'authoring_method'):
        sentence(value, key, high=600)
    if not value['id'].replace('-', '').replace('_', '').isalnum():
        raise ValueError('학습자료 식별자 오류')
    stamp = parse_time(value.get('updated_at', ''))
    if not stamp or (stamp - datetime.now(UTC)).total_seconds() > 900:
        raise ValueError('조사 학습자료 작성 시각 오류')
    sources = value.get('sources')
    if not isinstance(sources, list) or not 2 <= len(sources) <= 8:
        raise ValueError('조사 학습자료는 확인한 출처가 두 개 이상 필요합니다.')
    index = {}
    for source in sources:
        for key in ('id', 'kind', 'title', 'publisher', 'published', 'url', 'supports', 'limits'):
            sentence(source, key, high=800)
        if source['id'] in index or source['kind'] not in ('보도', '공식 보고서', '기관 발표', '필자의 의견'):
            raise ValueError('출처 식별자·유형 오류')
        try:
            url = urlsplit(source['url'])
            valid = url.scheme == 'https' and bool(url.hostname) and not url.username and not url.password and url.port in (None, 443)
        except ValueError:
            valid = False
        if not valid or url.hostname in ('localhost', '127.0.0.1', '::1'):
            raise ValueError('안전하지 않은 출처 주소')
        if source.get('checked') != '본문 확인':
            raise ValueError('제목만 확인한 출처로 조사 본문을 작성할 수 없습니다.')
        index[source['id']] = source
    if not any(s['kind'] == '공식 보고서' for s in sources):
        raise ValueError('확인한 공식 보고서가 필요합니다.')
    sections = value.get('sections')
    if not isinstance(sections, list) or not 3 <= len(sections) <= 9:
        raise ValueError('조사 본문 구성이 누락됐습니다.')
    cited = set()
    for section in sections:
        sentence(section, 'heading', high=100); sentence(section, 'body', low=100, high=2600)
        if section.get('kind') not in ('사실 확인', '기초와 적용', '연결 해석', '비교와 반론'):
            raise ValueError('사실과 해석 구분이 필요합니다.')
        refs = section.get('source_ids')
        if not isinstance(refs, list) or not refs or any(not isinstance(r, str) or r not in index for r in refs):
            raise ValueError('본문과 출처 연결 오류')
        cited.update(refs)
    if set(index) != cited:
        raise ValueError('읽은 자료와 본문에서 사용한 자료를 일치시켜야 합니다.')
    questions = value.get('questions')
    if not isinstance(questions, list) or not 1 <= len(questions) <= 3:
        raise ValueError('생각할 질문이 필요합니다.')
    for question in questions:
        sentence(question, 'question', high=250); sentence(question, 'hint', high=450)
    return value


def load_research(path):
    try:
        return validate_research(json.loads(Path(path).read_text(encoding='utf-8')))
    except (OSError, ValueError, TypeError):
        return {}


def publish_research(value, destination):
    """잘못된 자료는 이전 저장본을 덮어쓰지 않는다."""
    validate_research(value)
    atomic_json(Path(destination), value)


def render_research(value):
    import streamlit as st
    from reader_ui import reading_items
    validate_research(value)
    st.caption('ChatGPT 직접 조사 · ' + format_kst(value['updated_at']) + ' KST')
    if (datetime.now(UTC) - parse_time(value['updated_at'])).total_seconds() > 3 * 86400:
        st.warning('3일 이상 지난 조사 자료입니다. 작성일을 기준으로 읽어 주세요.')
    st.markdown('### ' + value['topic'])
    st.write(value['overview'])
    st.info('핵심 질문 · ' + value['question'])
    index = {s['id']: s for s in value['sources']}
    details = []
    for number, section in enumerate(value['sections'], 1):
        st.caption(f"{number:02d} · {section['kind']}")
        with st.container(border=True):
            st.markdown('#### ' + section['heading'])
            st.write(section['body'])
            st.caption('읽은 근거: ' + ' · '.join(dict.fromkeys(index[r]['publisher'] for r in section['source_ids'])))
        details.append(section['heading'] + '\n' + section['body'])
    st.markdown('#### 생각할 질문')
    for question in value['questions']:
        st.markdown('**' + question['question'] + '**')
        with st.expander('생각할 단서'):
            st.write(question['hint'])
        details.append(question['question'] + '\n' + question['hint'])
    with st.expander('읽은 원문과 각각의 확인 범위'):
        for source in value['sources']:
            st.markdown('**' + source['publisher'] + ' · ' + source['title'] + '**')
            st.caption(source['kind'] + ' · ' + source['published'] + ' · ' + source['checked'])
            st.write('확인한 내용: ' + source['supports'])
            st.caption('이 자료만으로 알 수 없는 내용: ' + source['limits'])
            st.link_button('출처 원문', source['url'])
    reading_items([{'id': 'research:' + value['id'], 'kind': 'study', 'group': '조사 학습',
                   'title': value['topic'], 'date': format_kst(value['updated_at']),
                   'summary': value['overview'], 'details': details, 'url': ''}], 'research_bookmark')
