# 경제·산업 인사이트 허브 — 무료 2차 버전

경제·시사 뉴스를 모으고 산업별로 분류한 뒤, 관심 기업의 관련 기사와 확인 질문을 함께 보여주는 한글 웹앱입니다. `insight_hub_free_v1.zip`의 Streamlit 화면·RSS 수집 코드를 확장했습니다.

**사용자 PC에 Python 설치 없이 GitHub + Streamlit Community Cloud에서 운영합니다. 유료 API·유료 서비스·카드 등록을 사용하지 않습니다.**

## 운영 상태 (2026-10-13 한국시간)

- 앱: https://insight-app-free-jeaigezue99ssijooexnga.streamlit.app/
- 앱 접근: 비공개. 소유 계정으로 로그인해야 하며, 다른 열람자를 초대하지 않았습니다.
- GitHub 소스·기사 메타데이터: 공개. 앱의 비공개 설정과 별개입니다.
- 자동 수집 실행 성공: 660건 수집, 중복 제거·이력 병합 후 672건 저장, 피드 오류 0건.
- 최초 GitHub 검증: 25개 통과. 배포 화면에서 확인한 오분류를 수정한 추가 검증: 26개 통과.
- 로그인 없는 앱 요청: HTTP 303으로 Streamlit 인증 화면 이동 확인.

## 구현한 기능

| 기능 | 동작 |
|---|---|
| 뉴스 수집 | Google 뉴스 검색 RSS + 한국경제·뉴시스의 공개 RSS |
| 중복 제거 | 같은 URL 또는 출처를 제외한 정규화 제목 병합, 분야 태그 유지 |
| 뉴스 분야 | 거시경제, 금융, 에너지, 산업·통상, 고용·사회, 국제·정책 |
| 산업 분류 | 금융·보험, 전력·에너지, 반도체·IT, 바이오·제약, 자동차·배터리, 건설·부동산, 유통·식품 |
| 기업 검색 | 저장된 기사 제목 검색, 약칭 입력, Google RSS 추가 검색 |
| 분석 보조 | 쟁점별 영향 경로·확인 질문·연결 기사, 메모 내려받기 |
| 저장 | 최근 30일·최대 3,000건의 기사 메타데이터 |
| 자동 수집 | GitHub Actions, 매일 한국시간 오전 7:17 + 수동 실행 |
| 오류 대응 | 부분 실패 표시, 전체 실패 시 기존 기사 파일 보존 |
| 출력 | 한글 CSV, 쟁점 메모 Markdown |

분석 보조는 제목의 키워드를 고정 점검표와 연결합니다. 기사 내용을 AI가 요약하거나 기업의 재무수치를 계산하지 않습니다. 원문은 출처 링크에서 확인하세요. 제목이 다른 동일 사건은 중복으로 남을 수 있으며, 제목에 기업명이 없으면 기업 검색에서 누락될 수 있습니다.

## 브라우저에서 무료 배포

1. GitHub에 **공개** 저장소 `insight-hub-free`를 만들고 README 파일을 포함해 초기화합니다.
2. 압축을 풀고 `insight_hub` 폴더 **안의 파일과 폴더**를 저장소 최상위에 올립니다. `.github`, `.streamlit`도 포함해야 합니다. 코드가 폴더 안에 한 번 더 들어가면 경로를 조정해야 합니다.
3. GitHub `Actions`에서 `일일 뉴스 수집`을 선택하고 `Run workflow`를 누릅니다.
4. [Streamlit Community Cloud](https://share.streamlit.io/)에 GitHub 계정으로 로그인합니다.
5. `Create app` → `Deploy from repo` → 해당 저장소 / `main` / `app.py`를 지정합니다.
6. `Advanced settings`에서 **Python 3.12**를 선택하고 `Deploy`를 누릅니다. Secrets는 비워둡니다.
7. 개인용이라면 앱 `Share`에서 `Make this app public`을 끕니다. 공개 저장소의 앱은 처음 생성할 때 공개이므로 이 단계까지 접근 범위를 확인해야 합니다.
8. 앱에서 기사 표시·필터·기업명 검색·원문 링크를 확인합니다. 기본 저장본은 검증 시 수집한 기사이므로 날짜가 오래됐다면 수집을 다시 실행합니다.

처음 배포에는 GitHub와 Streamlit 계정 로그인 및 연동 승인이 필요합니다. 상세 내용은 [DEPLOYMENT_KO.md](DEPLOYMENT_KO.md)에 있습니다.

## 일일 수집 관심 기업 변경

GitHub에서 `config.json`을 편집하고 저장합니다. 기업은 최대 10개까지 입력할 수 있습니다.

```json
{
  "companies": ["한국서부발전", "한국가스공사", "NH농협은행"],
  "max_per_feed": 40
}
```

화면의 기업명·약칭 입력은 브라우저 세션 내 검색에만 적용됩니다. 예약 수집 설정을 바꾸려면 위 파일을 수정하세요. 공개 저장소이므로 이 기업 목록과 기사 데이터는 공개됩니다.

## 수집 상태 확인

- `data/news.json`: 마지막 성공 시각과 기사 목록
- `data/status.json`: 최근 시도 시각, 성공 여부, 피드별 오류
- 일부 피드 실패: 나머지 결과 저장, 오류 목록 표시
- 전체 피드 실패: `news.json` 유지, 상태 파일 업데이트, Actions 실패 표시
- 예약 수집은 기본 브랜치에서 실행됩니다. cron은 UTC `17 22 * * *`이며 한국시간 다음 날 오전 7:17입니다.
- Streamlit 앱이 잠든 동안에도 GitHub Actions 수집은 별도로 작동합니다.

## 개발·검증 (PC 설치 불필요)

개발과 검증은 이 작업 환경에서 수행했습니다. 이후 GitHub의 `앱 검증` Actions가 코드 변경 시 테스트합니다.

개발 환경에서 실행할 때의 명령은 다음과 같습니다. 사용자 PC에서 수행할 필요는 없습니다.

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python collect_news.py
python -m streamlit run app.py
```

## 비용과 운영 범위

공개 저장소의 표준 GitHub-hosted runner인 `ubuntu-latest`를 사용합니다. 비공개 저장소로 바꾸면 무료 사용량 초과 비용이 발생할 수 있으므로 두 워크플로는 비공개 저장소에서 작업을 실행하지 않게 설정했습니다. 유료 API, 유료 모델, 대형 runner, 외부 DB, Codespaces는 사용하지 않습니다.

공식 무료 조건은 바뀔 수 있습니다. 비공개 저장소, 유료 분석, 유료 호스팅을 원할 때는 비용과 대안을 확인한 뒤 변경해야 합니다.

## 현재 확인된 제약

- 이 개발 환경에서 일부 Google 뉴스 분야 검색이 503·시간 초과를 반환했습니다. 2차 수집에서는 설정한 관심 기업의 Google RSS 수집과 보완 RSS 수집에 성공했습니다. GitHub Actions에서는 전체 피드 오류 없이 수집했습니다. 연결 상태는 실행 시점에 따라 달라질 수 있습니다.
- RSS 연결은 출처·실행 환경·시점에 따라 달라질 수 있습니다. 접속 차단을 우회하지 않으며 이전 저장본을 표시합니다.
- 제목 기반 분류이므로 문맥에 따라 잘못된 태그나 누락이 생길 수 있습니다.
- 재무제표 자동 수집·AI 요약·알림 발송·개인 계정별 장기 저장은 포함하지 않습니다.
- GitHub 예약 실행은 지연될 수 있고 공개 저장소의 활동이 60일간 없으면 비활성화될 수 있습니다.
- Streamlit Community Cloud는 12시간 동안 방문이 없으면 앱을 재울 수 있습니다. 방문 시 깨워 사용합니다.
- 기사 전문과 RSS 설명 텍스트는 저장하지 않습니다. 출처명·제목·날짜·링크만 보관합니다.

## 파일 구성

```text
app.py                      한글 웹앱
news_core.py                수집·분류·중복 제거·점검표
collect_news.py             예약 수집 실행
config.json                 자동 수집 기업과 수집량
requirements.txt            웹앱 패키지
requirements-collector.txt  수집 전용 최소 패키지
requirements-dev.txt        검증 패키지
.github/workflows/          수집·검증 자동화
.streamlit/config.toml      화면 테마
data/                       실제 수집 저장본과 상태
tests/                      핵심 기능 및 화면 조작 검증
DEPLOYMENT_KO.md             설치 없이 배포하는 절차
REVIEW_AND_TESTS_KO.md       기존 코드 검토·수정 내용·검증 결과
```

## 공식 참고 자료

- [Streamlit 무료 Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud)
- [Streamlit 배포 절차](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)
- [Streamlit 앱 절전](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app)
- [GitHub Actions 무료 조건](https://docs.github.com/en/actions/concepts/billing-and-usage)
- [GitHub 예약 실행 조건](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- [한국경제 RSS 목록](https://www.hankyung.com/feed)
- [뉴시스 RSS 목록](https://nwww.newsis.com/RSS/)
