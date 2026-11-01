"""청약홈 공식 API → 서울·성남 아파트 분양 ICS. Python 3.12+, 표준 라이브러리만 사용."""
import argparse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlencode, urlsplit
from urllib.request import Request, urlopen

BASE = 'https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/'
ENDPOINTS = ('getAPTLttotPblancDetail', 'getRemndrLttotPblancDetail')
OFFICIAL_HOSTS = ('applyhome.co.kr', 'lh.or.kr', 'i-sh.co.kr', 'gh.or.kr')


class BuildError(Exception):
    pass


def text(row, key):
    value = row.get(key)
    return '' if value is None else str(value).strip()


def region(address):
    """단지 이름 대신 공급위치 행정구역으로 판정. 판교 명칭만으로 포함하지 않음."""
    if re.match(r'^서울(?:특별시|시)?\s', address):
        return '서울'
    if re.match(r'^(?:경기도?\s+)?성남시\s', address):
        return '성남'
    return None


def day(value):
    if value in (None, '', '-'):
        return None
    value = str(value).strip()
    if re.fullmatch(r'\d{8}', value):
        value = f'{value[:4]}-{value[4:6]}-{value[6:]}'
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise BuildError('날짜 형식 오류: 원자료와 공식 명세를 확인하세요.') from None


def official_url(value):
    parts = urlsplit(value)
    host = parts.hostname or ''
    if (parts.scheme not in ('https', 'http') or parts.username or parts.password
            or any(c in value for c in '\r\n')
            or not any(host == h or host.endswith('.' + h) for h in OFFICIAL_HOSTS)):
        raise BuildError('공고 URL은 청약홈/LH/SH/GH 공식 도메인이어야 합니다.')
    return value


def fetch(endpoint, key, opener=urlopen, pause=time.sleep):
    """전체 이력을 재조회해 오래된 공고의 일정 변경도 반영. URL/키는 로그에 출력하지 않음."""
    # 포털에서 Encoding 키만 보이는 경우도 지원. '+'는 키의 일부이므로
    # 공백으로 바꾸는 unquote_plus 대신 unquote로 한 번만 복원한다.
    key = unquote(key.strip())
    rows, seen, expected = [], set(), None
    for page in range(1, 501):
        query = urlencode({'page': page, 'perPage': 100, 'returnType': 'JSON', 'serviceKey': key})
        request = Request(BASE + endpoint + '?' + query, headers={'Accept': 'application/json'})
        for attempt in range(3):
            try:
                with opener(request, timeout=45) as response:
                    payload = json.load(response)
                break
            except HTTPError as exc:
                if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                    raise BuildError(f'{endpoint}: HTTP {exc.code}. 키 승인/호출 한도/서버 상태 확인.') from None
            except (URLError, TimeoutError, OSError):
                if attempt == 2:
                    raise BuildError(f'{endpoint}: 네트워크 요청 실패.') from None
            except (ValueError, UnicodeError):
                raise BuildError(f'{endpoint}: JSON 응답이 아닙니다.') from None
            pause(2 ** attempt)
        if not isinstance(payload, dict) or not isinstance(payload.get('data'), list):
            raise BuildError(f'{endpoint}: 응답 구조 오류. 인증/명세 확인.')
        batch = payload['data']
        count = payload.get('matchCount')
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise BuildError(f'{endpoint}: matchCount 오류.')
        if expected is None:
            expected = count
        if count != expected or payload.get('currentCount') != len(batch):
            raise BuildError(f'{endpoint}: 수집 중 데이터 건수가 바뀌었습니다. 다시 실행하세요.')
        for row in batch:
            if not isinstance(row, dict):
                raise BuildError(f'{endpoint}: 잘못된 레코드.')
            identity = (text(row, 'HOUSE_MANAGE_NO'), text(row, 'PBLANC_NO'))
            if not all(identity) or identity in seen:
                raise BuildError(f'{endpoint}: 공고 ID 누락/페이지 중복.')
            seen.add(identity)
            rows.append(row)
        if len(rows) == expected:
            return rows
        if not batch or len(rows) > expected:
            raise BuildError(f'{endpoint}: 페이지가 불완전합니다.')
        pause(0.15)
    raise BuildError(f'{endpoint}: 500페이지 안전 한도 초과.')


def add_event(events, base, kind, label, start, end=None, application=False):
    start, end = day(start), day(end)
    if start is None:
        if end is not None:
            raise BuildError('접수 종료일만 있고 시작일이 없습니다.')
        return False
    end = end or start
    if end < start:
        raise BuildError('접수 종료일이 시작일보다 빠릅니다.')
    events.append(dict(base, kind=kind, label=label, start=start.isoformat(),
                       end=end.isoformat(), application=application))
    return True


def normalize(endpoint, rows, counts):
    events = []
    for row in rows:
        address = text(row, 'HSSPLY_ADRES')
        if not region(address):
            counts['outside_or_unknown_address'] += 1
            continue
        code = text(row, 'HOUSE_SECD').zfill(2)
        apt = endpoint == ENDPOINTS[0]
        if (apt and (code not in ('01', '09', '10') or text(row, 'RENT_SECD') != '0')) or (
                not apt and code not in ('04', '06')):
            counts['excluded_tenure_or_type'] += 1
            continue
        if any('임대' in re.sub(r'토지\s*임대부\s*분양', '분양', text(row, k))
               for k in ('HOUSE_NM', 'RENT_SECD_NM', 'HOUSE_SECD_NM')):
            counts['excluded_rental_text'] += 1
            continue
        if not text(row, 'HOUSE_NM') or not text(row, 'PBLANC_NO') or not text(row, 'HOUSE_MANAGE_NO'):
            raise BuildError('대상 공고의 이름/고유번호 누락.')
        supply = ('민간/공공 APT' if apt else {'04': '무순위', '06': '취소 후 재공급(불법행위 재공급)'}[code])
        base = {'id': endpoint + ':' + text(row, 'HOUSE_MANAGE_NO') + ':' + text(row, 'PBLANC_NO'),
                'name': text(row, 'HOUSE_NM'), 'address': address,
                'supply': text(row, 'HOUSE_DTL_SECD_NM') or supply,
                'url': official_url(text(row, 'PBLANC_URL')) if text(row, 'PBLANC_URL') else 'https://www.applyhome.co.kr/',
                'source': '한국부동산원 청약홈', 'note': supply}
        before = len(events)
        add_event(events, base, 'notice', '모집공고', row.get('RCRIT_PBLANC_DE'))
        add_event(events, base, 'winner', '당첨자 발표', row.get('PRZWNER_PRESNATN_DE'))
        special = add_event(events, base, 'special', '특별공급 접수',
                            row.get('SPSPLY_RCEPT_BGNDE'), row.get('SPSPLY_RCEPT_ENDDE'), True)
        detailed = False
        if apt:
            for rank in (1, 2):
                for area, label in (('CRSPAREA', '해당지역'), ('ETC_GG', '경기지역'), ('ETC_AREA', '기타지역')):
                    prefix = f'GNRL_RNK{rank}_{area}'
                    added = add_event(events, base, prefix, f'일반 {rank}순위 {label} 접수',
                                      row.get(prefix + '_RCPTDE'), row.get(prefix + '_ENDDE'), True)
                    detailed = detailed or added
            if not detailed:
                # 전체 접수기간은 특별공급도 포함할 수 있어 일반공급이라고 단정하지 않음.
                add_event(events, base, 'receipt', '청약 접수기간(세부 구분 원문 확인)',
                          row.get('RCEPT_BGNDE'), row.get('RCEPT_ENDDE'), True)
        else:
            general = add_event(events, base, 'general', supply + ' 일반공급 접수',
                                row.get('GNRL_RCEPT_BGNDE'), row.get('GNRL_RCEPT_ENDDE'), True)
            if not special and not general:
                add_event(events, base, 'receipt', supply + ' 접수',
                          row.get('SUBSCRPT_RCEPT_BGNDE'), row.get('SUBSCRPT_RCEPT_ENDDE'), True)
        if len(events) == before:
            raise BuildError('대상 공고의 일정이 모두 비어 있습니다.')
        counts['included_notices'] += 1
    return events


def manual_events(path, records=None):
    if records is None:
        records = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(records, list):
        raise BuildError('수동 공고 파일은 JSON 배열이어야 합니다.')
    events, seen = [], set()
    for row in records:
        if row.get('property_type') != 'apartment' or row.get('tenure') != 'sale':
            raise BuildError('수동 공고는 apartment/sale만 허용합니다.')
        if not region(row.get('address', '')):
            raise BuildError('수동 공고 주소는 서울 또는 성남이어야 합니다.')
        identity = row.get('id')
        if not identity or identity in seen or not row.get('name'):
            raise BuildError('수동 공고 ID 중복/필수값 누락.')
        seen.add(identity)
        base = {'id': 'manual:' + identity, 'name': row['name'], 'address': row['address'],
                'supply': row.get('supply', '공공/민간 분양'), 'source': row.get('source', '공식 공고 수동 확인'),
                'url': official_url(row['source_url']),
                'note': '공식 원문 확인 일정. ' + row.get('note', '')}
        kinds = set()
        for event in row['events']:
            kind = event['kind']
            if kind in kinds:
                raise BuildError('수동 공고 내 일정 kind가 중복됩니다.')
            kinds.add(kind)
            if not add_event(events, base, kind, event['label'], event['start'], event.get('end'),
                             event.get('application') is True):
                raise BuildError('수동 일정 시작일 누락.')
    return events


def escape(value):
    return str(value).replace('\\', '\\\\').replace('\r\n', '\n').replace('\r', '\n').replace('\n', '\\n').replace(';', '\\;').replace(',', '\\,')


def fold(line):
    """RFC 5545: UTF-8 문자를 자르지 않고 물리적 줄을 75 octets 이하로 접음."""
    parts, current = [], ''
    for char in line:
        if len((current + char).encode('utf-8')) > 75:
            parts.append(current)
            current = ' '
        current += char
    parts.append(current)
    return '\r\n'.join(parts)


def render_ics(events, now):
    stamp = now.strftime('%Y%m%dT%H%M%SZ')
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//seoul-apt-calendar//KO',
             'CALSCALE:GREGORIAN', 'METHOD:PUBLISH', 'X-WR-CALNAME:서울·성남 아파트 분양 청약',
             'X-WR-TIMEZONE:Asia/Seoul']
    for event in sorted(events, key=lambda e: (e['start'], e['id'], e['kind'])):
        uid = hashlib.sha256((event['id'] + ':' + event['kind']).encode()).hexdigest() + '@seoul-apt-calendar'
        description = (f"{event['source']} / {event['supply']}\n{event['note']}\n"
                       '종일 일정이며 실제 접수시간·자격·변경/취소 여부는 공고 원문을 확인하세요.\n' + event['url'])
        lines.extend(['BEGIN:VEVENT', 'UID:' + uid, 'DTSTAMP:' + stamp,
                      'DTSTART;VALUE=DATE:' + day(event['start']).strftime('%Y%m%d'),
                      'DTEND;VALUE=DATE:' + (day(event['end']) + timedelta(days=1)).strftime('%Y%m%d'),
                      'SUMMARY:' + escape(event['name'] + ' | ' + event['label']),
                      'DESCRIPTION:' + escape(description), 'LOCATION:' + escape(event['address']),
                      'URL:' + event['url'], 'TRANSP:TRANSPARENT'])
        if event['application']:
            for days in (3, 1):
                lines.extend(['BEGIN:VALARM', f'TRIGGER:-P{days}D', 'ACTION:DISPLAY',
                              'DESCRIPTION:' + escape(f"청약 접수 {days}일 전: {event['name']}"), 'END:VALARM'])
        lines.append('END:VEVENT')
    lines.append('END:VCALENDAR')
    return ('\r\n'.join(fold(line) for line in lines) + '\r\n').encode('utf-8')


def previous_site():
    value = os.environ.get('PREVIOUS_SITE_URL', '').strip()
    if not value:
        repo = os.environ.get('GITHUB_REPOSITORY', '')
        if re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
            owner, name = repo.split('/')
            value = f'https://{owner}.github.io/{name}/'
    if not value:
        return ''
    parts = urlsplit(value)
    if (parts.scheme != 'https' or not (parts.hostname or '').endswith('.github.io')
            or parts.username or parts.password or parts.query or parts.fragment
            or parts.port not in (None, 443)):
        raise BuildError('이전 캘린더 주소는 공개 GitHub Pages HTTPS 주소여야 합니다.')
    return value.rstrip('/') + '/'


def read_previous(base, filename, opener=None):
    if not base:
        return None
    opener = opener or urlopen
    try:
        with opener(Request(base + filename, headers={'Accept': '*/*'}), timeout=20) as response:
            value = response.read(2_000_001)
        if len(value) > 2_000_000:
            return None
        return value.decode('utf-8')
    except (OSError, URLError, UnicodeError, TimeoutError):
        return None


def previous_json(base, filename):
    value = read_previous(base, filename)
    try:
        result = json.loads(value) if value is not None else None
        return result if isinstance(result, dict) else None
    except (ValueError, TypeError):
        return None


def retained_sh_components(calendar):
    if calendar is None or 'BEGIN:VCALENDAR' not in calendar or 'END:VCALENDAR' not in calendar:
        raise BuildError('SH 수집 실패 후 이전 캘린더도 읽지 못했습니다. 일정 보존을 위해 배포를 중단합니다.')
    result, seen = [], set()
    blocks = re.findall(r'BEGIN:VEVENT\r?\n.*?\r?\nEND:VEVENT', calendar, re.S)
    for block in blocks:
        plain = re.sub(r'\r?\n[ \t]', '', block)
        if not re.search(r'^DESCRIPTION:SH 공식 홈페이지 자동 수집 /', plain, re.M):
            continue
        uid = re.search(r'^UID:([a-f0-9]{64}@seoul-apt-calendar)\r?$', plain, re.M)
        start = re.search(r'^DTSTART;VALUE=DATE:(\d{8})\r?$', plain, re.M)
        end = re.search(r'^DTEND;VALUE=DATE:(\d{8})\r?$', plain, re.M)
        url = re.search(r'^URL:(https?://[^\r\n]+)', plain, re.M)
        if not all((uid, start, end, url)) or uid.group(1) in seen:
            raise BuildError('이전 SH 일정 형식/중복 검증 실패. 기존 배포를 유지합니다.')
        if day(end.group(1)) <= day(start.group(1)):
            raise BuildError('이전 SH 일정 기간 검증 실패.')
        official_url(url.group(1))
        seen.add(uid.group(1))
        result.append(block.replace('\r\n', '\n').replace('\n', '\r\n') + '\r\n')
    return result


def sh_source_with_fallback(core, counts, collect_sh, now, base, prior):
    previous_sources = (prior or {}).get('sources', {})
    previous = previous_sources.get('sh', {}) if isinstance(previous_sources, dict) else {}
    if not isinstance(previous, dict):
        previous = {}
    try:
        rows, report = collect_sh(core, counts)
        source_events = manual_events(None, rows)  # SH 수집 결과의 날짜/주소/공식 링크도 이 단계에서 검증
        health = {'state':'fresh', 'last_success_at':now.isoformat(), 'last_attempt_at':now.isoformat(),
                  'message':'SH 공식 게시판 수집 성공', 'notify_failure':False,
                  'house_manage_numbers':sorted({str(row['house_manage_no']) for row in rows if row.get('house_manage_no')}),
                  'event_ids':sorted({event['id'] for event in source_events}),
                  'review_count':len(report.get('reviews', []))}
        return source_events, [], report, health
    except Exception as exc:
        # SH만 실패해도 다른 출처의 새 결과는 유지. 원문 예외는 키가 포함될 가능성이 있어 출력하지 않음.
        message = str(exc) if isinstance(exc, BuildError) else 'SH 수집 결과 검증 실패'
        calendar = read_previous(base, 'calendar.ics')
        components = retained_sh_components(calendar)
        old_counts = (prior or {}).get('counts', {})
        expected_sh = (len(previous.get('event_ids', [])) or previous.get('retained_event_count', 0)
                       or (old_counts.get('sh_collected_notices', 0) if isinstance(old_counts, dict) else 0))
        if expected_sh and not components:
            raise BuildError('이전 배포에 있던 SH 일정을 복원하지 못했습니다. 기존 배포를 보호합니다.')
        last_success = previous.get('last_success_at')
        if not last_success and prior and previous.get('state') != 'stale':
            last_success = prior.get('updated_at')  # 이전 버전 배포에서 최초 전환
        old_report = previous_json(base, 'sh_review.json') or {'reviews': []}
        report = dict(old_report, state='stale', message='SH 수집 실패로 이전 확인 목록을 유지합니다.')
        health = {'state':'stale', 'last_success_at':last_success, 'last_attempt_at':now.isoformat(),
                  'message':message,
                  'notify_failure':previous.get('state') != 'stale' or previous.get('message') != message,
                  'house_manage_numbers':previous.get('house_manage_numbers', []),
                  'event_ids':previous.get('event_ids', []), 'retained_event_count':len(components),
                  'review_count':None}
        counts['sh_stale'] = 1
        counts['sh_retained_events'] = len(components)
        print('::warning::SH 갱신 실패. 마지막 성공 SH 일정을 유지하고 청약홈/LH는 갱신합니다.', file=sys.stderr)
        return [], components, report, health


def write_health_outputs(health):
    sh = health.get('sh', {})
    notify = 'true' if sh.get('notify_failure') else 'false'
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
            output.write('sh_alert=' + notify + '\n')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as summary:
            summary.write('캘린더 생성 완료. SH 상태: ' + sh.get('state', 'disabled') + '\n')
            if sh.get('state') == 'stale':
                summary.write('SH 갱신 실패로 이전 SH 일정을 유지했습니다. 청약홈·LH는 정상 수집 결과를 반영했습니다.\n')
                summary.write('SH 마지막 성공: ' + str(sh.get('last_success_at') or '확인 불가') + '\n')


def build(output, events, counts, now, mode, sources=None, retained_sh=()):
    # 최근 1년의 완료 일정 + 미래 일정. API 수집 자체에는 날짜 제한 없음.
    cutoff = (now.astimezone(timezone(timedelta(hours=9))).date() - timedelta(days=365)).isoformat()
    events = [e for e in events if e['end'] >= cutoff]
    identities = [(e['id'], e['kind']) for e in events]
    if len(identities) != len(set(identities)):
        raise BuildError('중복 일정 ID.')
    data = render_ics(events, now)  # 검증을 마친 후에만 출력
    current_uids = set(re.findall(r'^UID:([^\r\n]+)', data.decode('utf-8'), re.M))
    components = []
    cutoff_date = day(cutoff)
    for block in retained_sh:
        plain = re.sub(r'\r?\n[ \t]', '', block)
        uid = re.search(r'^UID:([^\r\n]+)', plain, re.M).group(1)
        end = re.search(r'^DTEND;VALUE=DATE:(\d{8})', plain, re.M).group(1)
        if uid not in current_uids and day(end) > cutoff_date:
            components.append(block)
            current_uids.add(uid)
    data = data.removesuffix(b'END:VCALENDAR\r\n') + ''.join(components).encode('utf-8') + b'END:VCALENDAR\r\n'
    event_count = len(events) + len(components)
    sources = sources or {}
    sh_health = sources.get('sh', {})
    notice = ''
    if sh_health.get('state') == 'stale':
        notice = ('<section role="alert" style="border:2px solid #b45309;padding:16px">'
                  '<h2>SH 갱신 실패 — 이전 일정 유지 중</h2>'
                  '<p>청약홈·LH는 새 결과를 반영했습니다. SH 일정은 최신 정보가 아닐 수 있습니다.</p>'
                  '<p>SH 마지막 성공: ' + html.escape(str(sh_health.get('last_success_at') or '확인 불가')) + '</p></section>')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'calendar.ics').write_bytes(data)
    status = {'mode': mode, 'updated_at': now.isoformat(), 'event_count': event_count, 'counts': dict(counts), 'sources': sources,
              'coverage': '청약홈 + LH(별도 활성화 시 최근 2년 공고) + SH(별도 활성화 시 최근 2년 모집공고 본문) + 수동 공고. GH 전수 자동수집 아님.'}
    (output / 'status.json').write_text(json.dumps(status, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    title = '테스트 예시 — 실제 공고 아님' if mode == 'demo' else '서울·성남 아파트 분양 청약'
    (output / 'index.html').write_text('<!doctype html><html lang="ko"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width"><title>' + title + '</title><body><h1>' + title + '</h1>' + notice
        + '<p><a href="calendar.ics">Apple Calendar 구독용 ICS</a></p><p>캘린더 갱신 시각: ' + html.escape(now.isoformat()) + '</p>'
        '<p>일정 ' + str(event_count) + '개. <a href="status.json">수집 상태</a></p>'
        '<p><a href="sh_review.json">SH 확인 대상(수집 활성화 시)</a></p><p>청약홈 등록 공고와 추가 수집 공고를 제공합니다. LH는 공식 API, SH는 활성화 시 최근 2년 모집공고 본문을 자동 수집합니다. 첨부파일에만 있는 일정과 GH는 포함되지 않을 수 있습니다.</p>'
        '<p>실제 접수 시간·자격·변경 사항은 공식 모집공고문을 확인하세요. SH 장애 시 마지막 성공 SH 일정을 보존하며 다른 출처는 갱신합니다. 청약홈·LH 수집 실패 시에는 기존 배포가 유지됩니다.</p></body></html>', encoding='utf-8')
    (output / '.nojekyll').touch()
    return event_count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='site')
    parser.add_argument('--manual', default='data/manual_notices.json')
    parser.add_argument('--demo', action='store_true', help='합성 테스트 데이터. 실시간 데이터 아님.')
    args = parser.parse_args()
    try:
        counts = Counter()
        if args.demo:
            raw = json.loads(Path('examples/demo_api.json').read_text(encoding='utf-8'))
        else:
            key = os.environ.get('DATA_GO_KR_SERVICE_KEY', '').strip()
            if not key:
                raise BuildError('DATA_GO_KR_SERVICE_KEY가 없습니다. GitHub Secrets에 일반 인증키를 등록하세요.')
            raw = {endpoint: fetch(endpoint, key) for endpoint in ENDPOINTS}
            if any(not rows for rows in raw.values()):
                raise BuildError('전국 전체이력 API가 0건입니다. 비정상 응답 가능성으로 배포를 중단합니다.')
        events = []
        for endpoint in ENDPOINTS:
            counts[endpoint + '_fetched'] = len(raw[endpoint])
            events.extend(normalize(endpoint, raw[endpoint], counts))
        # 명시한 주택관리번호가 자동 수집 결과에 있으면 같은 수동 공고는 중복 추가하지 않음.
        manual_rows = json.loads(Path(args.manual).read_text(encoding='utf-8'))
        manual = manual_events(args.manual)
        skip_ids = {'manual:' + row['id'] for row in manual_rows
                    if row.get('house_manage_no') and any(
                        e['id'].startswith(ENDPOINTS[0] + ':' + str(row['house_manage_no']) + ':')
                        for e in events)}
        counts['manual_notices_already_in_applyhome'] = len(skip_ids)
        events.extend(e for e in manual if e['id'] not in skip_ids)
        lh_enabled = os.environ.get('ENABLE_LH', '').strip().lower() == 'true'
        if lh_enabled and not args.demo:
            from lh_source import collect
            today_kst = datetime.now(timezone(timedelta(hours=9))).date()
            events.extend(collect(key, today_kst, sys.modules[__name__], counts))
        counts['lh_enabled'] = int(lh_enabled and not args.demo)
        now = datetime.now(timezone.utc)
        sources = {'applyhome':{'state':'fresh','last_success_at':now.isoformat()},
                   'lh':{'state':'fresh' if lh_enabled and not args.demo else 'disabled',
                         'last_success_at':now.isoformat() if lh_enabled and not args.demo else None},
                   'sh':{'state':'disabled'}}
        sh_report, retained_sh = None, []
        sh_enabled = os.environ.get('ENABLE_SH', '').strip().lower() == 'true' and not args.demo
        if sh_enabled:
            from sh_source import collect as collect_sh
            base = previous_site()
            prior = previous_json(base, 'status.json')
            sh_events, retained_sh, sh_report, sh_health = sh_source_with_fallback(
                sys.modules[__name__], counts, collect_sh, now, base, prior)
            sources['sh'] = sh_health
            sh_ids = set(sh_health.get('event_ids', []))
            manage_numbers = set(sh_health.get('house_manage_numbers', []))
            old_manual_ids = {'manual:sh-312005'} | {'manual:' + row['id'] for row in manual_rows
                              if str(row.get('house_manage_no', '')) in manage_numbers}
            events = [event for event in events
                      if event['id'] not in sh_ids | old_manual_ids
                      and not any(event['id'].startswith(ENDPOINTS[0] + ':' + number + ':')
                                  for number in manage_numbers)]
            events.extend(sh_events)
        counts['sh_enabled'] = int(sh_enabled)
        count = build(args.output, events, counts, now, 'demo' if args.demo else 'live', sources, retained_sh)
        if sh_report is not None:
            Path(args.output, 'sh_review.json').write_text(json.dumps(sh_report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        write_health_outputs(sources)
        print(f'완료: {count}개 일정 → {args.output}/calendar.ics')
    except BuildError as exc:
        print('생성 실패: ' + str(exc) + ' 기존 배포는 유지됩니다.', file=sys.stderr)
        return 1
    except (ValueError, KeyError, TypeError, OSError):
        # 예외 원문/요청 URL에는 인증키가 섞일 수 있어 출력하지 않음.
        print('생성 실패: 인증키 승인, 공식 API 구조, 공고 필수값/날짜, 수동 JSON을 확인하세요. 기존 배포는 유지됩니다.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
