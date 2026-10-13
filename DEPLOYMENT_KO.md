# PC에 Python 설치 없이 배포하기

필요한 계정은 GitHub와 Streamlit Community Cloud 두 개입니다. 결제 정보를 등록하지 않습니다. GitHub Codespaces도 필요 없습니다.

## 1. GitHub 저장소 생성

https://github.com/new 에서 아래 값으로 생성합니다.

- Repository name: `insight-hub-free`
- Description: `경제·시사 뉴스와 산업·기업 쟁점을 연결하는 무료 한글 웹앱`
- Visibility: `Public`
- Add README: 켬 (기본 브랜치를 초기화)

공개 저장소에 기사 메타데이터와 관심 기업 설정이 공개됩니다.

## 2. 파일 올리기

저장소에서 `Add file` → `Upload files`를 엽니다. 압축 내부 `insight_hub`의 파일을 저장소 최상위에 올립니다. `app.py`가 최상위에 있어야 합니다.

파일 탐색기에서 `.github`와 `.streamlit` 폴더가 안 보이면 숨김 항목 표시를 켭니다. 업로드 목록에 `.github/workflows/daily-news.yml`, `.github/workflows/checks.yml`, `.streamlit/config.toml`이 포함됐는지 확인합니다.

브라우저 업로드가 숨김 폴더를 받지 못하면 `Add file` → `Create new file`로 아래 경로를 직접 입력하고 해당 파일 내용을 붙여넣습니다.

- `.github/workflows/daily-news.yml`
- `.github/workflows/checks.yml`
- `.streamlit/config.toml`

`Commit changes`로 저장합니다.

## 3. 자동 수집 확인

1. 저장소 상단 `Actions`를 엽니다.
2. `일일 뉴스 수집` → `Run workflow` → 브랜치 `main` → 실행합니다.
3. 초록색 성공 표시와 `data/news.json` 갱신 시각을 확인합니다.
4. `앱 검증`도 통과했는지 확인합니다.

저장 단계에 403 오류가 나오면 `Settings` → `Actions` → `General` → `Workflow permissions`에서 쓰기 권한 정책을 확인합니다. 워크플로 파일에는 `contents: write`가 선언돼 있습니다. 보호 브랜치 정책이나 계정 정책으로 차단됐다면 정책을 무작정 해제하지 말고 오류 내용을 확인합니다.

무료 조건을 지키기 위해 비공개 저장소에서는 두 워크플로 작업을 실행하지 않도록 했습니다. 대형 runner나 유료 서비스로 전환하지 않습니다.

## 4. Streamlit 배포

1. https://share.streamlit.io/ 에서 GitHub 계정으로 로그인합니다.
2. GitHub 연결 승인이 나오면 공개 저장소에 필요한 권한을 확인합니다.
3. `Create app` → `Deploy from repo`을 선택합니다.
4. Repository: 본인 계정의 `insight-hub-free`
5. Branch: `main`
6. Main file path: `app.py`
7. `Advanced settings` → Python version: `3.12`, Secrets는 빈칸
8. `Deploy`를 누릅니다.

앱 URL은 배포 화면에서 확정됩니다. URL을 미리 만들어 두지 않습니다.

## 개인용 비공개 설정

운영 앱은 https://insight-app-free-jeaigezue99ssijooexnga.streamlit.app/ 입니다.
공개 저장소에서 만든 앱은 최초에 공개됩니다. 생성 직후 앱 상단 `Share` → `Make this app public` 끄기로 비공개 전환을 마쳤습니다. 다시 열어 꺼짐 상태를 확인했으며, 로그인 없는 요청은 HTTP 303으로 인증 화면에 이동했습니다. 다른 열람자는 초대하지 않았습니다.

계정의 앱 설정 `Sharing`에서 `Who can view this app`을 `Only specific people can view this app`으로 선택해도 같은 설정을 변경할 수 있습니다. 앱을 공개로 전환하거나 열람자를 추가하지 마세요. GitHub 코드·기사 데이터·기업 설정은 계속 공개입니다.

## 5. 배포 후 확인

- 한글 제목과 뉴스 목록이 보이는가?
- 산업을 `전력·에너지` 등으로 바꾸면 해당 기사만 남는가?
- 기업명과 약칭 검색 시 제목에 해당 이름이 있는 기사만 표시되는가?
- `관심 기업 뉴스 추가 검색`이 성공하는가? 실패하면 수집 상태에 피드 오류가 표시되는가?
- CSV 내려받기 시 한글이 깨지지 않는가?
- 원문 버튼이 출처 기사로 이동하는가?
- `산업·기업 쟁점`에서 영향 경로·확인 질문·근거 기사가 보이는가?

Google RSS는 개발 중 연결 실패와 성공을 모두 확인했습니다. 배포 환경에서도 기업 추가 검색과 피드 오류 표시를 확인합니다.

## 매일 자동 수집

UTC `22:17`은 다음 날 한국시간 `07:17`입니다. GitHub 예약 실행은 시각이 지연될 수 있습니다. 앱에 접속하지 않아도 수집합니다. GitHub Actions를 쓰므로 ChatGPT의 별도 예약 작업은 필요하지 않습니다.

## 무료 사용을 유지하는 설정

- GitHub 저장소는 공개 유지
- runner는 `ubuntu-latest` 유지
- Streamlit은 Community Cloud 사용
- API 키·결제카드 입력 없음
- Codespaces·대형 runner·유료 데이터·유료 모델 사용 없음

유료 기능이 필요한 요구가 생기면 먼저 비용과 무료 대안을 확인합니다.

## 3차 기능 사용과 선택 AI 연결

기본 기업은 한국서부발전·한국도로공사·한국토지주택공사(LH)입니다. 개인 등록 목록은 브라우저에 저장되며 공개 저장소에 자동 저장하지 않습니다. 목록 파일 내려받기·불러오기로 기기를 옮길 수 있습니다.

현재 무료 AI 프로젝트 연결과 서버 비밀설정 등록을 완료했습니다. 새로 설치할 경우 Google AI Studio에서 결제 미연결·무료 등급을 확인한 프로젝트만 사용하세요. 키를 채팅이나 코드에 넣지 않습니다.

- 앱의 수동 AI: Streamlit 앱 Secrets에 GEMINI_API_KEY 및 AI_FREE_TIER_CONFIRMED = true를 설정
- 일일 AI: GitHub 저장소 Actions Secret GEMINI_API_KEY와 Actions Variable AI_FREE_TIER_CONFIRMED=true 설정
- 결제가 활성화된 프로젝트나 무료 요금이 없는 모델에는 연결하지 않음
- 무료 연결값만으로 결제 상태를 검증할 수 없음. 연결 시 계정의 Billing 상태 확인이 선행되어야 함
- 모델은 공식 무료 요금이 확인된 gemini-3.5-flash-lite로 고정. 유료 검색·배치·외부 도구·유료 승격 없음
- 한도·접속·출처 검증 실패 시 새 초안을 만들지 않고 기존 자료 유지
- 입력·출력의 제품 개선 이용 여부는 Google 무료 API 약관과 가격표에서 확인

2026-10-13 19:37 KST 실제 무료 API의 서부발전·도로공사·LH 분석 생성·저장과 일일 자동 실행의 AI 오류 0건을 확인했습니다. 등록·검색·규칙 기반 근거 연결은 키 없이 작동하며, AI 오류는 앱과 data/ai_status.json에 표시됩니다.
