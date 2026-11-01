"""LH 공식 2026년 활용 가이드 기반. 실응답 검증은 서비스 활용승인 후 필요."""
from datetime import timedelta
import hashlib
import json
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlencode
from urllib.request import Request, urlopen

LIST_URL = 'https://apis.data.go.kr/B552555/lhLeaseNoticeInfo1/lhLeaseNoticeInfo1'
DETAIL_URL = 'https://apis.data.go.kr/B552555/lhLeaseNoticeDtlInfo1/getLeaseNoticeDtlInfo1'


def unpack(payload, error):
    """배열 형식 응답에서 dsSch와 결과 dataset을 분리."""
    if not isinstance(payload, list):
        raise error('LH: JSON 배열 응답이 아닙니다. 인증/서비스 명세 확인.')
    data = {}
    for block in payload:
        if not isinstance(block, dict):
            raise error('LH: 응답 dataset 오류.')
        for key, value in block.items():
            if key in data:
                raise error('LH: 중복 dataset.')
            data[key] = value
    headers = data.get('resHeader')
    if not isinstance(headers, list) or not headers or headers[0].get('SS_CODE') != 'Y':
        raise error('LH: 결과코드가 성공(Y)이 아닙니다. 두 서비스의 활용승인 확인.')
    return data


def request_json(url, params, key, error, opener=urlopen, pause=time.sleep):
    query = dict(params, serviceKey=unquote(key.strip()))
    request = Request(url + '?' + urlencode(query), headers={'Accept': 'application/json'})
    for attempt in range(3):
        try:
            with opener(request, timeout=45) as response:
                return unpack(json.load(response), error)
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise error(f'LH: HTTP {exc.code}. 공고목록/상세정보 서비스 활용승인 확인.') from None
        except (URLError, OSError, TimeoutError):
            if attempt == 2:
                raise error('LH: 네트워크 실패.') from None
        except (ValueError, UnicodeError):
            raise error('LH: JSON 응답이 아닙니다.') from None
        pause(2 ** attempt)
    raise error('LH: 요청 실패.')


def list_notices(key, today, error, request=request_json, pause=time.sleep):
    rows = []
    for code in ('05', '39'):
        collected, expected, seen = [], None, set()
        for page in range(1, 101):
            params = {'UPP_AIS_TP_CD': code, 'PG_SZ': 100, 'PAGE': page,
                      'PAN_ST_DT': (today - timedelta(days=730)).strftime('%Y%m%d'),
                      'PAN_ED_DT': today.strftime('%Y%m%d')}
            data = request(LIST_URL, params, key, error)
            batch = data.get('dsList')
            if not isinstance(batch, list):
                raise error('LH: dsList가 없습니다.')
            if not batch:
                if page == 1:
                    break
                raise error('LH: 수집 도중 페이지가 비었습니다.')
            for row in batch:
                try:
                    count = int(row['ALL_CNT'])
                    identity = (str(row['PAN_ID']), str(row['CCR_CNNT_SYS_DS_CD']))
                except (KeyError, TypeError, ValueError):
                    raise error('LH: 공고번호/전체건수 누락.') from None
                if expected is None:
                    expected = count
                if count != expected or identity in seen:
                    raise error('LH: 전체건수 변경/중복 페이지. 재실행하세요.')
                seen.add(identity)
                collected.append(row)
            if len(collected) == expected:
                break
            if len(collected) > expected:
                raise error('LH: 전체건수보다 많은 공고가 반환됐습니다.')
            pause(0.15)
        else:
            raise error('LH: 유형당 100페이지 안전 한도 초과.')
        rows.extend(collected)
    return rows


def sale_candidate(row):
    """39에는 행복주택도 섞이므로 상위 유형만으로 분양이라고 단정하지 않음."""
    upper, detail = str(row.get('UPP_AIS_TP_CD', '')).zfill(2), str(row.get('SPL_INF_TP_CD', ''))
    if (upper, detail) not in (('05', '050'), ('39', '390')):
        return False
    words = ' '.join(str(row.get(k) or '') for k in ('PAN_NM', 'AIS_TP_CD_NM'))
    # 토지임대부 분양은 건물 소유권을 분양하는 방식. 일반 임대와 구분.
    words = re.sub(r'토지\s*임대부\s*분양', '분양', words)
    if any(word in words for word in ('임대', '행복주택', '오피스텔', '도시형', '상가', '토지공급', '분양전환')):
        return False
    return bool(re.search(r'분양|아파트', words))


def normalized_date(value, day):
    if not value:
        return None
    result = day(str(value).strip().replace('.', '-'))
    return result.isoformat() if result else None


def receipt_dates(value, day):
    """완전한 연월일 1~2개만 허용. 날짜 생략/미정 문구는 추정하지 않음."""
    if not value:
        return None
    # 공식 가이드 ACP_DTTM: 2019.11.11 12:00 ~ 2019.11.12 12:00
    pattern = r'\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}'
    matches = re.findall(pattern, value)
    if not 1 <= len(matches) <= 2:
        return None
    rest = re.sub(pattern, '', value)
    rest = re.sub(r'\d{1,2}:\d{2}(?::\d{2})?', '', rest)
    rest = re.sub(r'\([월화수목금토일](?:요일)?\)', '', rest)
    if re.sub(r'[\s~∼〜.\-–—:()]', '', rest):
        return None
    if (len(matches) == 1 and re.search(r'[~∼〜]', rest)
            and not re.search(r'\d{1,2}:\d{2}\s*[~∼〜]\s*\d{1,2}:\d{2}', value)):
        return None
    dates = []
    for value in matches:
        y, m, d = re.split(r'[.\-/]', value)
        dates.append(day(f'{int(y):04d}-{int(m):02d}-{int(d):02d}').isoformat())
    return dates[0], dates[-1]


def normalize_notice(row, detail, core, counts):
    if not sale_candidate(row):
        counts['lh_excluded_type'] += 1
        return []
    # 접수처(dsCtrtPlc)의 주소는 LH 사무소 주소이므로 절대로 지역 판정에 사용하지 않음.
    complexes = detail.get('dsSbd')
    schedules = detail.get('dsSplScdl')
    # 성공 응답이라도 공고에 따라 dataset이 없거나 null일 수 있다.
    # 주소 없는 공고는 지역을 추측하지 않고 확인 대상으로 집계한다.
    missing = [key for key in ('dsSbd', 'dsSplScdl') if detail.get(key) is None]
    if missing:
        counts['lh_incomplete_detail_notices'] += 1
        if counts['lh_incomplete_detail_notices'] <= 20:
            print('LH 확인 필요: ' + str(row.get('PAN_ID', '')) +
                  ' / 누락=' + ','.join(missing) +
                  ' / 반환항목=' + ','.join(sorted(detail)), file=sys.stderr)
    if complexes is None or complexes == []:
        counts['lh_missing_complex_info'] += 1
        return []
    if schedules is None:
        counts['lh_missing_schedule_info'] += 1
        schedules = []
    if not isinstance(complexes, list) or not isinstance(schedules, list):
        raise core.BuildError('LH: 단지정보/공급일정 dataset 형식 오류. PAN_ID=' + str(row.get('PAN_ID', '')))
    events = []
    for complex_ in complexes:
        address = str(complex_.get('LCT_ARA_ADR') or '').strip()
        if not core.region(address):
            counts['lh_outside_or_unknown_address'] += 1
            continue
        name = str(complex_.get('BZDT_NM') or '').strip()
        if not name:
            raise core.BuildError('LH: 대상 단지명이 없습니다.')
        words = re.sub(r'토지\s*임대부\s*분양', '분양', name)
        if any(word in words for word in ('임대', '행복주택', '오피스텔', '상가', '도시형')):
            counts['lh_excluded_type'] += 1
            continue
        token = hashlib.sha256((name + '|' + address).encode()).hexdigest()[:16]
        base = {'id': f"lh:{row['CCR_CNNT_SYS_DS_CD']}:{row['PAN_ID']}:{token}",
                'name': name, 'address': address, 'supply': 'LH 공공분양',
                'url': core.official_url(str(row.get('DTL_URL') or '').strip()),
                'source': 'LH 청약플러스 공식 API',
                'note': '공고: ' + str(row.get('PAN_NM') or '') + '\n공고 공통일정입니다. 단지별 적용과 정확한 접수시간은 원문 확인.' +
                        ('\nAPI가 공급일정을 제공하지 않아 공고일만 표시합니다.' if not schedules else '')}
        core.add_event(events, base, 'notice', 'LH 모집공고', normalized_date(row.get('PAN_NT_ST_DT'), core.day))
        groups, winners = {}, set()
        for schedule in schedules:
            label = str(schedule.get('HS_SBSC_ACP_TRG_CD_NM') or '접수 구분 원문 확인').strip()
            # 같은 구분이 여러 번 나오면 행 순서 대신 날짜를 붙여 안정적인 kind 생성.
            groups.setdefault(label, []).append(schedule)
        for label, group in groups.items():
            for schedule in group:
                raw = str(schedule.get('ACP_DTTM') or '').strip()
                dates = receipt_dates(raw, core.day)
                if dates:
                    discriminator = label if len(group) == 1 else label + '|' + raw
                    kind = 'receipt-' + hashlib.sha256(discriminator.encode()).hexdigest()[:16]
                    note = dict(base, note=base['note'] + '\n공식 신청일시: ' + raw)
                    core.add_event(events, note, kind, 'LH ' + label + ' 접수', *dates, True)
                elif raw:
                    counts['lh_unparsed_receipt_dates'] += 1
                winner = normalized_date(schedule.get('PZWR_ANC_DT'), core.day)
                if winner:
                    winners.add(winner)
        for winner in sorted(winners):
            kind = 'winner' if len(winners) == 1 else 'winner-' + winner
            core.add_event(events, base, kind, 'LH 당첨자 발표', winner)
        counts['lh_included_complexes'] += 1
    return events


def collect(key, today, core, counts, request=request_json, pause=time.sleep):
    rows = list_notices(key, today, core.BuildError, request, pause)
    counts['lh_fetched_notices'] = len(rows)
    events = []
    attempted = 0
    missing_before = counts['lh_missing_complex_info']
    for row in rows:
        if not sale_candidate(row):
            counts['lh_excluded_type'] += 1
            continue
        area = str(row.get('CNP_CD_NM') or '')
        if area and not any(part in area for part in ('서울', '경기', '전국')):
            counts['lh_outside_province'] += 1
            continue
        params = {}
        for field in ('SPL_INF_TP_CD', 'CCR_CNNT_SYS_DS_CD', 'PAN_ID', 'UPP_AIS_TP_CD'):
            if not row.get(field):
                raise core.BuildError('LH: 상세 조회 식별자 누락.')
            params[field] = row[field]
        if row.get('AIS_TP_CD'):
            params['AIS_TP_CD'] = row['AIS_TP_CD']
        detail = request(DETAIL_URL, params, key, core.BuildError)
        attempted += 1
        events.extend(normalize_notice(row, detail, core, counts))
        pause(0.15)
    if attempted and counts['lh_missing_complex_info'] - missing_before == attempted:
        raise core.BuildError('LH: 조회한 모든 후보 공고에 단지정보가 없습니다. 확인 필요 로그를 점검하세요.')
    print('LH 수집 요약: 상세조회=' + str(attempted) +
          ', 단지정보없음=' + str(counts['lh_missing_complex_info']) +
          ', 공급일정없음=' + str(counts['lh_missing_schedule_info']) +
          ', 생성일정=' + str(len(events)))
    return events
