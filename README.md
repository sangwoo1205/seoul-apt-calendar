# 서울·성남 아파트 분양 청약 → Apple Calendar

서울 전체와 **성남시 전체(분당·판교·수정구·중원구 포함)**의 분양 청약 일정을 `calendar.ics`로 만드는 프로젝트입니다. Python 3.12 이상, 추가 설치 패키지 없이 실행합니다.

**현재 상태: 업로드용 준비본입니다. API 키 등록·실데이터 수집·GitHub 배포는 아직 하지 않았습니다.** 포함된 예시 일정은 합성 테스트 자료입니다.

## 포함하는 것

- 청약홈 APT API의 민영/국민 아파트 분양: 일반공급 1·2순위와 해당/경기/기타 지역 구분, 특별공급.
- 같은 APT API의 민간사전청약·신혼희망타운도 분양주택으로 분류된 경우 포함.
- 잔여세대 API의 무순위(`04`), 취소 후 재공급에 해당하는 불법행위 재공급(`06`).
- 모집공고일, 접수기간, 당첨자 발표일을 종일 일정으로 기록. 접수 일정에는 3일 전·1일 전 알림 포함.
- 임대·분양전환 임대 제외. 오피스텔·도시형생활주택·공공지원민간임대 API는 호출하지 않음.
- 공급위치 주소로 지역을 판정. 단지 이름의 '서울/판교'만 보고 넣지 않음. 주소가 없거나 행정구역을 판정할 수 없으면 제외 건수에 집계.

**공공분양 전수 자동수집은 아닙니다.** 청약홈에 등록된 공공분양을 포함하지만 LH·SH·GH 자체 접수 공고, 청약홈 별도 임의공급 API는 자동 수집하지 않습니다. 해당 공고는 공식 원문을 확인해 `data/manual_notices.json`에 추가할 수 있습니다. 기관별 API 주소를 추측해 넣지 않았습니다.

## 3단계 — GitHub에 파일 올리기

1. ZIP을 내려받아 압축을 풉니다. `seoul-apt-calendar` 폴더를 엽니다.
2. GitHub의 기존 `seoul-apt-calendar` 저장소 → **Code → Add file → Upload files**를 선택합니다.
3. 폴더 자체가 아니라 **폴더 안의 내용물**을 올립니다. `calendar_builder.py`, `README.md`, `data`, `docs`, `examples`, `tests`를 끌어놓으세요. 기존 README는 이 파일로 교체합니다.
4. **Commit changes**를 눌러 기본 브랜치에 저장합니다. 업로드 후 최상위에 `calendar_builder.py`가 보여야 합니다. `seoul-apt-calendar/seoul-apt-calendar/...`로 중첩되면 잘못 올라간 것입니다.
5. 숨김 파일 `.gitignore`도 올립니다. Mac Finder에서 **Command+Shift+.**로 숨김 파일을 표시하거나, GitHub **Add file → Create new file**에서 파일 이름 `.gitignore`로 만들고 제공 파일 내용을 복사합니다.
6. `.github/workflows/update-calendar.yml`도 필요합니다. 웹 업로드에서 숨김 폴더가 빠졌다면 **Add file → Create new file**에서 파일 이름에 정확히 `.github/workflows/update-calendar.yml`을 입력하고, ZIP에 든 동일 파일의 전체 내용을 붙여넣은 뒤 저장합니다. **경로와 파일명이 핵심입니다.** Finder에서 숨김 파일을 표시하면 제공 파일을 열 수 있습니다.

3단계는 여기까지입니다. 인증키는 파일·대화·README에 적지 마세요. 자동 실행 설정 파일은 수동 실행과 예약 실행만 포함하여, 업로드 직후 push로 배포되지는 않습니다.

## 4단계 — API 키와 자동 실행·Pages 설정

1. [공공데이터포털 공식 서비스](https://www.data.go.kr/data/15098547/openapi.do)에서 **한국부동산원_청약홈 분양정보 조회 서비스** 활용신청을 합니다. 내 계정의 승인 상태와 호출 한도를 확인합니다.
2. 발급된 **일반 인증키(Decoding)**를 복사합니다. Encoding 키를 넣지 마세요. 프로그램이 URL 인코딩을 처리합니다.
3. GitHub 저장소 → **Settings → Secrets and variables → Actions → New repository secret**.
   - Name: `DATA_GO_KR_SERVICE_KEY`
   - Secret: 본인의 Decoding 인증키
4. 저장소 → **Settings → Pages → Build and deployment → Source: GitHub Actions**로 선택합니다. branch 배포는 선택하지 않습니다.
5. **Actions → Update apartment calendar → Run workflow → Run workflow**를 누릅니다. Actions 활성화 안내가 있으면 허용합니다.
6. `build`, `deploy`가 모두 초록색인지 확인합니다. 배포 결과의 사이트 주소를 열어 **최종 수집 성공 시각**, 일정 개수, `status.json`의 `mode: live`를 확인합니다. 합성 예시가 운영 사이트에 올라가면 안 됩니다.

매일 한국시간 **오전 9시 목표**로 실행합니다(`0 0 * * *`, UTC). GitHub 사정에 따라 지연/누락될 수 있습니다. 기본 브랜치에 파일이 있어야 하며, 공개 저장소는 60일 동안 활동이 없으면 예약 실행이 비활성화될 수 있으므로 주기적으로 Actions를 확인합니다. 수동 실행도 가능합니다.

실패 시 새 Pages 배포를 하지 않아 이전 성공 결과가 유지됩니다. 사이트의 마지막 성공 시각은 오래된 데이터인지 판단하는 기준입니다. GitHub 계정 알림 설정에서 Actions 실패 알림도 켜 두세요. 자동으로 재시도하는 것은 HTTP 429/일시적 서버·네트워크 오류에 한해 최대 3회입니다.

## 5단계 — Apple Calendar 구독

배포가 성공하면 실제 주소는 보통 다음 형태입니다. **`YOUR_GITHUB_USERNAME`은 본인 GitHub 사용자 이름으로 바꾸세요. 아직 만들어진 주소가 아닙니다.** GitHub 배포 화면의 실제 URL을 우선 사용하세요.

```text
https://YOUR_GITHUB_USERNAME.github.io/seoul-apt-calendar/calendar.ics
```

Mac 캘린더 → **파일 → 새로운 캘린더 구독** → 위 주소 입력 → 구독 → 위치를 iCloud로 선택할 수 있으면 선택 → 자동 새로 고침 간격 설정. 메뉴명은 OS 버전에 따라 다를 수 있습니다. 파일 다운로드 후 가져오기는 일회성 복사이므로 **URL 구독**을 사용합니다. iPhone에서는 설정에서 '구독 캘린더 추가'를 검색해 같은 주소를 넣을 수도 있습니다.

종일 접수 시작일 기준 `-P3D`, `-P1D` 알림입니다. 정확한 접수 시작/마감 시각은 API 날짜만으로 추측하지 않습니다. 구독 캘린더 알림을 제거하는 옵션이 켜져 있으면 알림이 안 올 수 있으며, Apple의 갱신/알림 정책에 따라 표시가 달라집니다. 설정 후 실제 기기에서 확인하세요.

## 로컬 실행 (선택)

프로젝트 폴더 안에서:

```sh
python3 -m unittest discover -s tests -v
python3 calendar_builder.py --demo --output demo-site
```

실데이터 실행 시 환경변수 `DATA_GO_KR_SERVICE_KEY`를 설정한 뒤:

```sh
python3 calendar_builder.py --output site
```

프로그램은 `.env`를 읽지 않습니다. 키를 코드나 터미널 명령 이력에 직접 적기보다 GitHub Secrets를 권장합니다. `site`에는 `calendar.ics`, `index.html`, `status.json`, `.nojekyll`이 생성됩니다. Pages는 이 폴더만 공개하며 원본 응답이나 인증키는 배포하지 않습니다.

## 갱신 방식과 한계

- 두 API를 매번 전체 페이지 조회합니다. 모집공고일 기준 짧은 기간만 조회해 예전 공고의 변경을 놓치는 일을 줄입니다. 페이지당 100건, API당 최대 500페이지입니다. 실제 승인된 호출 한도 내에서 사용하세요.
- 매 수집 결과로 완전히 재생성합니다. 원본에서 사라진 공고는 다음 구독 갱신에서 빠집니다. API가 변경·취소를 반영하지 않으면 이 프로젝트도 이를 알 수 없습니다. 데이터가 수집 중 변경되어 건수가 맞지 않으면 실패 처리 후 재실행합니다.
- 완료 후 365일 지난 일정은 출력에서 빠집니다. 미래 일정은 유지합니다. 동일 공고+일정 유형은 날짜가 바뀌어도 같은 UID이므로 구독에서 수정으로 인식할 수 있습니다.
- 세부 1·2순위 날짜가 있으면 각각 표시합니다. 없으면 전체 접수기간을 '세부 구분 원문 확인'으로 표시하며 일반공급 날짜라고 추측하지 않습니다. 특별공급 세부 자격별 기관추천 사전접수일은 별도 수집하지 않습니다.
- 대상 지역이라도 분양 코드가 없거나 허용되지 않은 유형이면 제외합니다. `status.json`에서 원본 건수와 제외 건수를 확인하세요. 일정이 0개인 결과도 가능하며, 0개가 모든 공고가 없다는 보장은 아닙니다.
- 공식 API 명세는 확인했지만 **인증키를 사용한 실제 요청은 아직 검증하지 않았습니다.** 첫 Run workflow의 성공과 공식 공고와의 대조 확인이 남아 있습니다.

출처·필드: [docs/SOURCES.md](docs/SOURCES.md). 수동 보완: [docs/MANUAL.md](docs/MANUAL.md). 문제 해결: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).
