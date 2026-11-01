import io
import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
import calendar_builder as c


def apt(**changes):
    return dict(HOUSE_MANAGE_NO='test-1', PBLANC_NO='test-1', HOUSE_NM='합성 테스트 아파트',
                HOUSE_SECD='01', RENT_SECD='0', HSSPLY_ADRES='서울특별시 강남구 테스트로 1',
                RCRIT_PBLANC_DE='2026-11-01', SPSPLY_RCEPT_BGNDE='2026-11-09',
                SPSPLY_RCEPT_ENDDE='2026-11-09', GNRL_RNK1_CRSPAREA_RCPTDE='2026-11-10',
                GNRL_RNK1_CRSPAREA_ENDDE='2026-11-10', PRZWNER_PRESNATN_DE='2026-11-20', **changes)


class CalendarTests(unittest.TestCase):
    def normalize(self, row, endpoint=c.ENDPOINTS[0]):
        return c.normalize(endpoint, [row], c.Counter())

    def test_geography_uses_address_not_brand(self):
        for address in ('서울특별시 강남구 역삼동', '서울 강남구 역삼동', '경기도 성남시 분당구 판교동', '성남시 수정구 창곡동'):
            self.assertTrue(c.region(address))
        for address in ('경기도 용인시 수지구 판교브랜드', '경기도 하남시 서울숲아파트', '충청남도 서산시', ''):
            self.assertIsNone(c.region(address))

    def test_rental_and_non_apartment_excluded(self):
        for change in ({'RENT_SECD': '1'}, {'RENT_SECD': None}, {'HOUSE_SECD': '02'}, {'HOUSE_NM': '테스트 임대'}):
            row = apt(); row.update(change)
            self.assertEqual(self.normalize(row), [])
        row = apt(); row['HOUSE_DTL_SECD_NM'] = '국민'
        self.assertEqual(len(self.normalize(row)), 4)

    def test_remainder_codes_and_distinct_receipts(self):
        for code in ('04', '06'):
            row = apt(); row.update(HOUSE_SECD=code, SUBSCRPT_RCEPT_BGNDE='20261110',
                                   SUBSCRPT_RCEPT_ENDDE='20261111', GNRL_RCEPT_BGNDE='20261110', GNRL_RCEPT_ENDDE='20261111')
            events = self.normalize(row, c.ENDPOINTS[1])
            self.assertEqual({e['kind'] for e in events}, {'notice', 'winner', 'special', 'general'})
        row['HOUSE_SECD'] = '03'
        self.assertEqual(self.normalize(row, c.ENDPOINTS[1]), [])

    def test_unranked_overall_fallback_and_apt_fallback(self):
        row = apt()
        row['HOUSE_SECD'] = '04'
        for k in list(row):
            if k.startswith('SPSPLY_'): del row[k]
        row.update(SUBSCRPT_RCEPT_BGNDE='20261110', SUBSCRPT_RCEPT_ENDDE='20261111')
        self.assertIn('receipt', {e['kind'] for e in self.normalize(row, c.ENDPOINTS[1])})
        row = apt()
        for k in list(row):
            if k.startswith('GNRL_'): del row[k]
        row.update(RCEPT_BGNDE='2026-11-09', RCEPT_ENDDE='2026-11-11')
        event = next(e for e in self.normalize(row) if e['kind'] == 'receipt')
        self.assertIn('세부 구분', event['label'])

    def test_malformed_date_and_range_fail(self):
        for change in ({'RCRIT_PBLANC_DE': '2026-02-30'}, {'SPSPLY_RCEPT_ENDDE': '2026-11-01'}):
            row = apt(); row.update(change)
            with self.assertRaises(c.BuildError): self.normalize(row)

    def test_pagination_and_service_error(self):
        calls = []
        def opener(request, timeout):
            calls.append(request.full_url)
            page = len(calls)
            records = [{'HOUSE_MANAGE_NO': str(page), 'PBLANC_NO': str(page)}]
            return io.StringIO(json.dumps({'data': records, 'matchCount': 2, 'currentCount': 1}))
        self.assertEqual(len(c.fetch(c.ENDPOINTS[0], 'fake+/=', opener, lambda _: None)), 2)
        self.assertIn('page=2', calls[1])
        self.assertIn('fake%2B%2F%3D', calls[0])
        for payload in ({'code': -4}, {'data': [], 'currentCount': 0, 'matchCount': 1}):
            with self.assertRaises(c.BuildError):
                c.fetch(c.ENDPOINTS[0], 'fake', lambda *a, **k: io.StringIO(json.dumps(payload)), lambda _: None)

    def test_duplicate_pages_fail(self):
        payload = {'data': [{'HOUSE_MANAGE_NO': '1', 'PBLANC_NO': '1'}], 'currentCount': 1, 'matchCount': 2}
        with self.assertRaises(c.BuildError):
            c.fetch(c.ENDPOINTS[0], 'fake', lambda *a, **k: io.StringIO(json.dumps(payload)), lambda _: None)

    def test_auth_error_redacted_and_not_retried(self):
        def opener(request, timeout):
            raise HTTPError(request.full_url, 401, 'private', {}, None)
        with self.assertRaises(c.BuildError) as result:
            c.fetch(c.ENDPOINTS[0], 'SECRET-VALUE', opener)
        self.assertNotIn('SECRET-VALUE', str(result.exception))

    def test_ics_bytes_end_date_alarms_escaping_and_stable_uid(self):
        row = apt(); row['HOUSE_NM'] = '합성,테스트;아파트\\\n' + '서울성남' * 40
        events = self.normalize(row)
        now = datetime(2026, 11, 1, tzinfo=timezone.utc)
        data = c.render_ics(events, now)
        self.assertTrue(data.endswith(b'END:VCALENDAR\r\n'))
        self.assertNotIn(b'\n', data.replace(b'\r\n', b''))
        self.assertTrue(all(len(line) <= 75 for line in data.split(b'\r\n')))
        unfolded = data.decode().replace('\r\n ', '')
        self.assertIn('DTEND;VALUE=DATE:20261111', unfolded)
        self.assertEqual(unfolded.count('BEGIN:VALARM'), 4)
        self.assertIn('\\,', unfolded); self.assertIn('\\;', unfolded)
        uid = [l for l in unfolded.splitlines() if l.startswith('UID:')]
        events[0]['start'] = '2026-11-02'
        changed = c.render_ics(events, now).decode().replace('\r\n ', '')
        self.assertEqual(set(uid), {l for l in changed.splitlines() if l.startswith('UID:')})

    def test_manual_and_host_validation(self):
        for url in ('https://applyhome.co.kr.evil.example/a', 'javascript:alert(1)', 'https://lh.or.kr/a\nUID:x'):
            with self.assertRaises(c.BuildError): c.official_url(url)
        self.assertEqual(c.official_url('https://apply.lh.or.kr/'), 'https://apply.lh.or.kr/')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'manual.json'
            path.write_text(json.dumps([{'id': 'x', 'name': '확인용', 'property_type': 'apartment', 'tenure': 'rent'}]))
            with self.assertRaises(c.BuildError): c.manual_events(path)

    def test_failed_collection_preserves_previous_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            calendar = Path(tmp) / 'calendar.ics'
            calendar.write_bytes(b'previous-success')
            with patch('sys.argv', ['calendar_builder.py', '--output', tmp]), patch.dict('os.environ', {'DATA_GO_KR_SERVICE_KEY': 'test-secret'}), patch.object(c, 'fetch', side_effect=c.BuildError('API unavailable')):
                self.assertEqual(c.main(), 1)
            self.assertEqual(calendar.read_bytes(), b'previous-success')

    def test_empty_calendar_and_cutoff_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(c.build(tmp, [], {}, datetime(2026, 11, 1, tzinfo=timezone.utc), 'live'), 0)
            self.assertNotIn('BEGIN:VEVENT', (Path(tmp) / 'calendar.ics').read_text())
            self.assertEqual(json.loads((Path(tmp) / 'status.json').read_text())['mode'], 'live')


if __name__ == '__main__':
    unittest.main()
