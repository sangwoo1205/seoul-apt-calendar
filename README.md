# 서울·성남 아파트 분양 청약 캘린더

청약홈과 LH 공식 API, SH 공식 주택분양 모집공고 게시판을 매일 한국시간 오전 9시 목표로 조회하고 Apple Calendar 구독용 ICS를 GitHub Pages에 공개합니다. 서울·성남(분당·판교 포함)의 아파트 분양을 대상으로 일반 임대·분양전환 임대·오피스텔·상가는 제외합니다. 토지임대부 건물 분양은 별도로 표시합니다.

- [캘린더 안내 페이지](https://sangwoo1205.github.io/seoul-apt-calendar/)
- [Apple Calendar 구독 주소](https://sangwoo1205.github.io/seoul-apt-calendar/calendar.ics)
- [현재 수집 상태](https://sangwoo1205.github.io/seoul-apt-calendar/status.json)
- [SH 원문 확인 대상](https://sangwoo1205.github.io/seoul-apt-calendar/sh_review.json)

## SH 수집에 실패할 때

SH 페이지 변경, 브라우저 설치/실행 실패, 잘못된 SH 일정 데이터가 발생해도 **청약홈·LH의 새 결과는 계속 반영**합니다. SH는 이전에 공개된 `calendar.ics`에서 마지막 성공 SH 일정만 가져와 UID·날짜·내용을 유지합니다. 새 SH 접수일을 추정해 만들지 않습니다.

안내 페이지에는 **SH 갱신 실패 — 이전 일정 유지 중** 배너와 SH 마지막 성공 시각이 표시됩니다. 전체 캘린더 갱신 시각과 SH 마지막 성공 시각은 따로 관리합니다. 회복하면 새 SH 결과로 교체되고 배너가 사라집니다.

새 SH 오류가 발생하면 **캘린더 배포가 끝난 뒤** 별도 `SH update needs attention (calendar already deployed)` 단계가 실패 상태를 남깁니다. 이때 build와 deploy가 초록색이어도 전체 실행이 빨간색일 수 있습니다. **캘린더 갱신은 완료됐고 SH에만 확인이 필요하다는 뜻**입니다. 같은 오류가 계속되면 알림을 반복하지 않고, 오류 원인이 바뀌거나 회복 후 다시 실패하면 새로 알립니다.

이전 캘린더까지 읽지 못해 SH 일정을 보존할 수 없으면 예외적으로 새 배포를 중단해 기존 공개 일정을 보호합니다. 청약홈·LH 자체 수집 실패도 기존 정책대로 전체 새 배포를 중단합니다.

## GitHub 알림 받기

GitHub 계정의 [알림 설정](https://github.com/settings/notifications)에서 **System → Actions**의 수신 경로를 **On GitHub** 또는 **Email**로 선택하고, **Only notify for failed workflows**를 선택한 뒤 저장합니다. 이 저장소의 Watch 설정도 확인하세요. 예약 실행 알림의 수신자는 GitHub의 실행자/예약 수정자 규칙에 따릅니다.

프로그램은 별도 이메일 비밀번호나 새 API 키를 요구하지 않습니다. 계정의 알림 수신 설정을 자동 변경하지 않습니다. 실제 이메일 수신은 본인 GitHub 알림 설정과 메일함에서 확인해야 합니다.

공식 안내: [GitHub Actions 알림 관리](https://docs.github.com/en/subscriptions-and-notifications/how-tos/managing-github-actions-notifications), [실행 알림 대상](https://docs.github.com/en/actions/concepts/workflows-and-actions/notifications-for-workflow-runs).

## 설정 유지

- Secret: `DATA_GO_KR_SERVICE_KEY` — 공공데이터포털 일반 인증키. Encoding/Decoding 둘 다 지원.
- Variables: `ENABLE_LH=true`, `ENABLE_SH=true`.
- Pages 배포 Source: GitHub Actions.
- 수동 실행: Actions → Update apartment calendar → Run workflow.
- Apple Calendar 주소는 기존과 같으므로 다시 구독하지 않습니다.

## 수집 범위와 한계

청약홈은 APT/잔여세대 API를 사용합니다. LH는 최근 730일 공고의 상세 단지주소와 공급일정을 확인합니다. SH는 최근 730일 주택분양 모집공고의 **본문**에서 읽을 수 있는 일정만 자동 추출하며, 첨부파일에만 있는 일정이나 새 사업지의 지역을 판단하지 못한 공고는 확인 대상으로 남깁니다. GH 및 모든 기관 공고 전수 수집은 아닙니다.

지역·유형·날짜·자격은 최종적으로 공식 원문을 확인하세요. 같은 주택관리번호의 청약홈/SH 중복은 조정하지만 LH와의 모든 중복을 자동 연결하지는 않습니다. 접수 일정은 종일이며 3일 전·1일 전 알림을 포함합니다. GitHub 예약 실행과 Apple Calendar 갱신에는 지연이 있을 수 있습니다.

로컬 검증: `python3 -m unittest discover -s tests -v`.
