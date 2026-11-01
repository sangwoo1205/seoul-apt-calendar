# 공식 출처와 확인 범위

확인일: 2026-11-01 (한국시간). 날짜/주소/키를 임의로 만들어 실데이터처럼 사용하지 않습니다.

## 청약홈 공식 데이터

- [공공데이터포털 서비스 소개·활용신청](https://www.data.go.kr/data/15098547/openapi.do)
- [한국부동산원 기술문서 게시물 — 2026-01-29 수정](https://www.reb.or.kr/reb/na/ntt/selectNttInfo.do?bbsId=1268&mi=10251&nttSn=79889)
- [공공데이터포털 페이지가 연결하는 공식 Swagger JSON](https://infuser.odcloud.kr/api/stages/37000/api-docs?1643022751478)

`official-api-schema.json`은 위 Swagger JSON에서 사용한 두 작업과 관련 정의만 발췌한 스냅샷입니다. 구현 필드를 대조하기 위한 참고용이며 향후 명세 변경 시 공식 문서를 다시 확인합니다. 기술문서 DOCX 내용 전체를 읽었다는 의미가 아닙니다.

검증된 API 주소:

```text
https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/getAPTLttotPblancDetail
https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/getRemndrLttotPblancDetail
```

공통 쿼리: `serviceKey`, `page`, `perPage`, `returnType=JSON`. 인증키는 환경변수에서만 읽고 URL 인코딩합니다. 명세의 `ApiKeyAuth2`는 쿼리 `serviceKey`를 정의합니다. 데이터는 `data` 배열, 페이지 검사에는 `matchCount`와 `currentCount`를 사용합니다. 날짜 조건을 사용하지 않으므로 유형별 날짜 필터 형식 차이를 추측하지 않습니다.

## 실제 사용하는 필드

| 목적 | 공식 필드 |
|---|---|
| 공고 식별 | `HOUSE_MANAGE_NO`, `PBLANC_NO` |
| 단지/주소 | `HOUSE_NM`, `HSSPLY_ADRES` |
| 유형 | `HOUSE_SECD`, `HOUSE_SECD_NM`, APT의 `HOUSE_DTL_SECD_NM`, `RENT_SECD`, `RENT_SECD_NM` |
| 공고일/발표일 | `RCRIT_PBLANC_DE`, `PRZWNER_PRESNATN_DE` |
| 공식 공고 링크 | `PBLANC_URL` (없으면 청약홈 첫 화면 링크, 세부 주소를 조합하지 않음) |
| 특별공급 | `SPSPLY_RCEPT_BGNDE`, `SPSPLY_RCEPT_ENDDE` |
| APT 전체 접수 | `RCEPT_BGNDE`, `RCEPT_ENDDE` |
| APT 세부 접수 | `GNRL_RNK1_CRSPAREA_RCPTDE/ENDDE`, `GNRL_RNK1_ETC_GG_RCPTDE/ENDDE`, `GNRL_RNK1_ETC_AREA_RCPTDE/ENDDE`, `GNRL_RNK2_CRSPAREA_RCPTDE/ENDDE`, `GNRL_RNK2_ETC_GG_RCPTDE/ENDDE`, `GNRL_RNK2_ETC_AREA_RCPTDE/ENDDE` |
| 잔여세대 전체 접수 | `SUBSCRPT_RCEPT_BGNDE`, `SUBSCRPT_RCEPT_ENDDE` |
| 잔여세대 일반공급 | `GNRL_RCEPT_BGNDE`, `GNRL_RCEPT_ENDDE` |

APT `RENT_SECD=0`은 분양주택, `1`은 분양전환 가능임대이므로 `0`만 허용합니다. 잔여세대 API는 `HOUSE_SECD=04` 무순위, `06` 불법행위 재공급입니다. 별도 '취소후재공급 API'는 만들지 않았습니다. 2025-04-17 명칭 변경은 한국부동산원 기술문서 게시물에서도 안내합니다.

## 기관 자체 공공분양 보완

- [LH 청약플러스](https://apply.lh.or.kr/)
- [SH 서울주택도시개발공사](https://www.i-sh.co.kr/)
- [GH 경기주택도시공사](https://www.gh.or.kr/)

위는 사용자가 공고를 찾는 공식 홈페이지입니다. 이 프로젝트가 자동 호출하는 API가 아닙니다. 기관별 자체 접수의 전체 자동화는 별도 검증 후 추가해야 합니다. 임대 공고와 분양전환 임대를 수동 입력하지 않습니다.

## 운영 참고

- [GitHub Pages 사용자 지정 워크플로](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
- [GitHub Actions schedule의 UTC·지연·비활성화 안내](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- [Apple 캘린더 구독 안내](https://support.apple.com/guide/calendar/subscribe-to-calendars-icl1022/mac)
- [ICS 규격 RFC 5545](https://www.rfc-editor.org/rfc/rfc5545)

검증 결과: 오프라인 필터·페이징·실패 처리·ICS 형식 테스트 통과. 실제 승인된 인증키를 사용한 응답, GitHub 계정 배포, Apple 기기에서의 갱신·알림은 사용자 설정 후 확인해야 합니다.
