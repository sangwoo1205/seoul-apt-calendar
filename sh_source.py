"""SH 공개 주택분양 게시판을 일반 브라우저로 읽는 선택 기능. API/로그인 불필요."""
from datetime import datetime, timedelta, timezone
import hashlib
import os
import re
from urllib.parse import parse_qs, urlsplit

LIST_URL = 'https://www.i-sh.co.kr/main/lay2/program/S1T294C296/www/brd/m_244/list.do'
LIST_NAME = '주택분양 공고 및 공지 목록'
DATE = re.compile(r'(?<!\d)(?:(\d{4})\s*[.\-/]\s*)?(\d{1,2})\s*[.\-/]\s*(\d{1,2})(?:\.)?(?!\d)')


def dates(value, core):
    """시작 연도는 필수. 종료 월일만 있는 경우 같은 해만 허용(연도 경계 추측 금지)."""
    hits = list(DATE.finditer(value))
    if not hits or len(hits) > 2 or not hits[0].group(1):
        return None
    year = int(hits[0].group(1))
    result = []
    for hit in hits:
        y, m, d = hit.groups()
        try:
            result.append(core.day(f'{int(y or year):04d}-{int(m):02d}-{int(d):02d}').isoformat())
        except core.BuildError:
            return None
    if result[-1] < result[0]:
        return None
    # 남은 문구는 시간·요일·일반 안내만 허용. 미정/변경 가능/중간 날짜 생략은 검토 대상.
    remainder = DATE.sub('', value)
    remainder = re.sub(r'\([월화수목금토일](?:요일)?\)', '', remainder)
    remainder = re.sub(r'\d{1,2}:\d{2}', '', remainder)
    remainder = re.sub(r'이후|부터|까지', '', remainder)
    if re.sub(r'[\s~∼〜.\-–—:()]', '', remainder):
        return None
    if len(hits) == 1 and re.search(r'[~∼〜]', remainder) and not re.search(r'\d{1,2}:\d{2}\s*[~∼〜]\s*\d{1,2}:\d{2}', value):
        return None
    return result[0], result[-1]


def clean_title(title):
    return re.sub(r'\s+', '', re.sub(r'\[[^\]]*\]', '', title)).replace('정정', '').replace('취소', '')


def sale_title(title):
    stripped = re.sub(r'토지\s*임대부\s*분양', '분양', title)
    return ('분양주택' in stripped and '모집공고' in stripped and '단지' in stripped
            and not any(word in stripped for word in ('임대', '오피스텔', '도시형', '상가', '단독주택')))


def supply_address(title, body, core):
    # 접수처/본사 주소를 공급지로 오인하지 않도록 공급위치라고 명시된 행만 허용.
    match = re.search(r'(?:공급위치|단지주소|공급대상\s*위치)\s*[:：]\s*([^\n]+)', body)
    if match and core.region(match.group(1).strip()):
        return match.group(1).strip()
    # 공식 확인된 서울 사업지 2곳. 위례 등 여러 시에 걸친 지명은 추측하지 않음.
    compact = re.sub(r'\s+', '', title)
    if '고덕강일' in compact:
        return '서울특별시 고덕강일지구 (단지 상세주소는 원문 확인)'
    if '마곡지구' in compact:
        return '서울특별시 마곡지구 (단지 상세주소는 원문 확인)'
    return None


def latest_notices(raw):
    """같은 주택관리번호/정확히 같은 정규화 제목이면 최신 공고를 선택."""
    latest, seen_titles, seen_manage = [], set(), set()
    for item in sorted(raw, key=lambda n: (n['posted'], n['seq']), reverse=True):
        manage = re.search(r'주택관리번호\s*[:：]\s*(\d{10})', item['body'])
        title_key = clean_title(item['title'])
        number = manage.group(1) if manage else None
        if title_key in seen_titles or (number and number in seen_manage):
            continue
        seen_titles.add(title_key)
        if number:
            seen_manage.add(number)
        latest.append(item)
    return latest



def parse_notice(item, core):
    title, body = item['title'], item['body']
    if not sale_title(title):
        return None, []
    address = supply_address(title, body, core)
    if not address:
        return None, [{'url': item['url'], 'title': title, 'reason': '공급 지역을 확정할 수 없음'}]
    manage = re.search(r'주택관리번호\s*[:：]\s*(\d{10})', body)
    row = {'id': 'sh-' + item['seq'], 'name': re.sub(r'^\s*\[[^\]]*\]\s*', '', title),
           'address': address, 'property_type': 'apartment', 'tenure': 'sale',
           'source': 'SH 공식 홈페이지 자동 수집', 'source_url': core.official_url(item['url']),
           'supply': 'SH 토지임대부 분양(건물 분양·토지 임대)' if '토지임대부' in title.replace(' ', '') else 'SH 분양',
           'events': [], 'note': 'SH 공식 본문에서 자동 추출한 종일 일정입니다. 정확한 시간·자격은 원문 확인.'}
    if manage:
        row['house_manage_no'] = manage.group(1)
    if '취소' in title or re.search(r'본\s*(?:입주자)?\s*모집공고[를을]?\s*취소', body):
        row['note'] += '\n공식 공고에서 취소가 확인되어 접수 일정을 생성하지 않습니다.'
        return row, []
    reviews, original_lines = [], []
    lines = [re.sub(r'\s+', ' ', line).strip(' \t-■○·') for line in body.splitlines() if line.strip()]
    blocked_kinds = set()
    for line in lines:
        if ':' not in line and '：' not in line:
            continue
        label, value = re.split(r'[:：]', line, maxsplit=1)
        label = label.strip()
        application = False
        if re.fullmatch(r'모집공고일', label):
            kind = 'notice'
        elif re.fullmatch(r'당첨자\s*발표(?:일)?', label):
            kind = 'winner'
        elif (re.match(r'특별공급|일반공급|[12]순위자?|무순위|사전청약 당첨자$', label)
              and not re.search(r'발표|포기|서류|결과', label)):
            kind = 'receipt-' + hashlib.sha256(label.encode()).hexdigest()[:16]
            application = True
        else:
            continue
        parsed = dates(value, core)
        if not parsed:
            reviews.append({'url':item['url'], 'title':title, 'reason':'날짜 형식 확인 필요', 'label':label})
            continue
        if kind in blocked_kinds:
            continue
        if any(event['kind'] == kind for event in row['events']):
            blocked_kinds.add(kind)
            reviews.append({'url':item['url'], 'title':title, 'reason':'같은 접수 구분이 반복되어 원문 확인 필요','label':label})
            # 어느 한 기간만 남기는 대신 이 접수 유형은 전부 제외.
            row['events'] = [event for event in row['events'] if event['kind'] != kind]
            continue
        row['events'].append({'kind':kind, 'label':'SH ' + label + (' 접수' if application else ''),
                              'start':parsed[0], 'end':parsed[1], 'application':application})
        original_lines.append(label + ': ' + value)
    if not any(event['kind'] == 'notice' for event in row['events']):
        # 게시일은 접수일이나 모집공고일로 바꿔 부르지 않음.
        row['events'].append({'kind':'notice-posted','label':'SH 공고 게시(일정은 원문 확인)','start':item['posted']})
    if not any(event.get('application') for event in row['events']):
        reviews.append({'url':item['url'], 'title':title, 'reason':'접수일 자동 추출 불가. 첨부 공고문 확인 필요'})
    if reviews:
        row['note'] += '\n일부 일정을 읽지 못했습니다. sh_review.json의 확인 대상을 참조하세요.'
    if '토지임대부' in title.replace(' ', ''):
        row['note'] += '\n건물은 분양, 토지는 임대하는 방식으로 토지임대료가 별도 발생합니다.'
    row['note'] += '\n' + '\n'.join(original_lines)
    return row, reviews


def pagination(text, core):
    match = re.search(r'총\s*([\d,]+)\s*건\s*\[(\d+)\s*/\s*(\d+)\s*페이지\]', text)
    if not match:
        raise core.BuildError('SH: 게시판 건수/페이지 표시가 바뀌었습니다.')
    return tuple(int(value.replace(',', '')) for value in match.groups())


def read_browser(today, core):
    from playwright.sync_api import sync_playwright
    raw = []
    with sync_playwright() as p:
        # 사용자 브라우저/로그인 정보/인증키를 사용하지 않는 매 실행 새 브라우저.
        env = {k:v for k,v in os.environ.items() if k != 'DATA_GO_KR_SERVICE_KEY'}
        browser = p.chromium.launch(headless=True, env=env)
        page = browser.new_page(locale='ko-KR', timezone_id='Asia/Seoul')
        page.set_default_timeout(45000)
        stage = '공식 게시판 접속'
        try:
            page.goto(LIST_URL, wait_until='domcontentloaded')
            stage = '주택분양 분류 선택'
            page.get_by_role('combobox',name='공지분류 선택',exact=True).select_option(label='주택분양')
            stage = '모집공고 및 기간 선택'
            page.get_by_role('radio',name='모집공고',exact=True).check()
            page.get_by_role('textbox',name='등록기간 시작 년월일 입력. 예) 2021-01-01',exact=True).fill((today-timedelta(days=730)).isoformat())
            page.get_by_role('textbox',name='등록기간 끝 년월일 입력. 예) 2021-01-01',exact=True).fill(today.isoformat())
            stage = '검색 실행'
            with page.expect_navigation(wait_until='domcontentloaded'):
                page.get_by_role('link',name='조회',exact=True).click()
            stage = '주택분양 목록 확인'
            table = page.get_by_role('table',name=LIST_NAME,exact=True)
            table.wait_for()
            total, current, pages = pagination(page.locator('body').inner_text(),core)
            if pages > 20:
                raise core.BuildError('SH: 최근 2년 모집공고 20페이지 안전한도 초과.')
            titles, fingerprints = [], set()
            for number in range(1,max(pages,1)+1):
                table = page.get_by_role('table',name=LIST_NAME,exact=True)
                observed_total, observed_page, observed_pages = pagination(page.locator('body').inner_text(),core)
                if (observed_total, observed_page, observed_pages) != (total,number,pages):
                    raise core.BuildError('SH: 수집 중 목록 건수/페이지가 바뀌었습니다.')
                titles_on_page = [re.sub(r'\s+', ' ', title).strip()
                                  for title in table.get_by_role('link').all_text_contents()]
                fingerprint = tuple(titles_on_page)
                if fingerprint in fingerprints:
                    raise core.BuildError('SH: 같은 목록 페이지가 반복되었습니다.')
                fingerprints.add(fingerprint)
                titles.extend(titles_on_page)
                for title in titles_on_page:
                    if not sale_title(title):
                        continue
                    link = page.get_by_role('table',name=LIST_NAME,exact=True).get_by_role('link',name=title,exact=True)
                    stage = '공고 상세 열기'
                    with page.expect_navigation(wait_until='domcontentloaded'):
                        link.click()
                    stage = '공고 본문 읽기'
                    notice = page.get_by_role('table',name=title,exact=True).filter(has_text=re.compile(r'등록일\s*[:：]'))
                    notice.wait_for()
                    cells = notice.get_by_role('cell').evaluate_all('(els) => els.map(el => el.innerText)')
                    body = max(cells,key=len) if cells else ''
                    preview = notice.get_by_role('link',name='미리보기',exact=True).first.get_attribute('href')
                    seq = parse_qs(urlsplit(preview or '').query).get('seq',[''])[0]
                    posted = re.search(r'등록일\s*[:：]\s*(\d{4}-\d{2}-\d{2})',notice.inner_text())
                    if not seq.isdigit() or not posted:
                        raise core.BuildError('SH: 공고 고유번호/게시일 확인 불가.')
                    url = page.url.split('?')[0] + '?seq=' + seq
                    raw.append({'seq':seq,'title':title,'body':body,'posted':posted.group(1),'url':url})
                    stage = '검색 목록으로 복귀'
                    page.go_back(wait_until='domcontentloaded')
                    page.get_by_role('table',name=LIST_NAME,exact=True).wait_for()
                if number < pages:
                    with page.expect_navigation(wait_until='domcontentloaded'):
                        page.get_by_role('link',name=str(number+1),exact=True).click()
            if len(titles) != total or len(titles) != len(set(titles)):
                raise core.BuildError('SH: 목록 건수/중복 제목 확인 필요. 원문과 대조하세요.')
            return raw, total
        except core.BuildError:
            raise
        except Exception as exc:
            # 공개 UI의 실패 단계/오류 종류만 남김. 예외 원문·환경·키는 출력하지 않음.
            codes = re.findall(r'net::ERR_[A-Z_]+|strict mode violation', str(exc))
            category = type(exc).__name__ + (' / ' + ','.join(sorted(set(codes))) if codes else '')
            raise core.BuildError('SH: ' + stage + ' 실패 (' + category + ').') from None
        finally:
            browser.close()


def collect(core, counts, reader=read_browser):
    today = datetime.now(timezone(timedelta(hours=9))).date()
    try:
        raw, total = reader(today,core)
    except core.BuildError:
        raise
    except Exception:
        # 인증키·환경정보·브라우저 세부 오류를 출력하지 않음.
        raise core.BuildError('SH: 브라우저 수집 실패. 사이트 점검/접근 차단/화면 변경 여부를 확인하세요.') from None
    rows, reviews = [], []
    for item in latest_notices(raw):
        row, review = parse_notice(item,core)
        if row:
            rows.append(row)
        reviews.extend(review)
    counts['sh_listed_notices'] = total
    counts['sh_collected_notices'] = len(rows)
    counts['sh_review_items'] = len(reviews)
    counts['sh_enabled'] = 1
    print(f'SH 수집 요약: 목록={total}, 분양공고={len(rows)}, 확인필요={len(reviews)}')
    return rows, {'collected_at':datetime.now(timezone.utc).isoformat(), 'reviews':reviews,
                  'coverage':'SH 주택분양 모집공고 게시판, 최근 730일. 본문에서 확인되는 일정만 자동 추출.'}
