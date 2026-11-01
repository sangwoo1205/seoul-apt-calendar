# 설정이 막힐 때

| 증상 | 확인할 것 |
|---|---|
| Actions 목록에 워크플로가 없음 | 파일 경로가 `.github/workflows/update-calendar.yml`이고 기본 브랜치에 있는지 확인 |
| 생성 실패/HTTP 401·403 | 정확한 서비스 활용신청 승인, Secrets 이름 `DATA_GO_KR_SERVICE_KEY`, Decoding 키인지 확인. 활성화 지연은 포털 안내 확인 |
| HTTP 429 | 포털의 승인된 일일 한도 확인. 반복 수동 실행을 중단하고 할당량 회복 후 재실행 |
| JSON/응답 구조/필드 오류 | 포털 점검 여부와 `docs/SOURCES.md`의 최신 공식 명세 확인. 키나 전체 요청 URL을 공개 이슈에 붙이지 않기 |
| 공고 ID 중복/건수 변경 | 수집 도중 API 원자료가 바뀌었을 수 있음. 다시 실행하고 반복되면 제공기관 응답 확인 |
| Pages 배포 실패 | Settings → Pages → Source가 GitHub Actions인지, 저장소/조직의 Actions 정책이나 github-pages 환경 승인이 막는지 확인 |
| 404 | deploy 성공 후 실제 배포 URL 확인. `/seoul-apt-calendar/calendar.ics` 경로와 대소문자 확인 |
| 일정이 0개 | `status.json`의 수집 건수/제외 건수 확인. 지역 판별 불가·유형 제외·제공기관 미등재 가능. 청약홈 원문과 대조 |
| 일정이 오래됨 | 사이트 최종 수집 성공 시각과 Actions 실패/예약 비활성화 상태 확인. 실패 시 이전 성공본이 유지됨 |
| 날짜가 하루 짧거나 길어 보임 | 소스의 end는 마지막 날 포함, ICS DTEND는 다음 날. 이는 표준 동작 |
| 알림/새 일정이 안 옴 | 일회성 가져오기가 아닌 URL 구독인지, 자동 새로 고침과 구독 알림 허용 옵션 확인 |

키를 실수로 공개한 경우 포털에서 재발급하고 GitHub Secret을 교체하세요. 파일 삭제만으로 과거 커밋의 키가 사라지지는 않습니다.
