from collections import Counter
from datetime import date
import unittest
import calendar_builder as c
import sh_source as sh


def notice(**changes):
    row={'seq':'312005','title':'[정정] 고덕강일지구 3단지 토지임대부 분양주택 입주자모집공고',
         'posted':'2026-10-16','url':'https://www.i-sh.co.kr/main/lay2/program/S1T294C296/www/brd/m_244/view.do?seq=312005',
         'body':'''모집공고일: 2026.10.16.(금)
특별공급: 2026.11.02.(월) 10:00 ~ 11.03.(화) 17:00
일반공급
1순위자(서울 2년 이상 계속 거주자): 2026.11.04.(수) 10:00 ~ 17:00
1순위자(서울 2년 미만 거주자, 인천·경기 거주자): 2026.11.05.(목) 10:00 ~ 17:00
2순위자: 2026.11.06.(금) 10:00 ~ 17:00
당첨자 발표: 2026.11.26.(목) 16:00 이후
주택관리번호: 2026000373'''}
    row.update(changes)
    return row


class SHTests(unittest.TestCase):
    def test_date_same_year_end_and_single_day(self):
        self.assertEqual(sh.dates('2026.11.02.(월) 10:00 ~ 11.03.(화) 17:00',c),('2026-11-02','2026-11-03'))
        self.assertEqual(sh.dates('2026.11.04.(수) 10:00 ~ 17:00',c),('2026-11-04','2026-11-04'))
        for value in ('11.02~11.03','2026.12.31~1.2','추후 안내','2026.11.02 ~','2026.11.02 ~ 11.99'):
            self.assertIsNone(sh.dates(value,c))

    def test_verified_sh_format_produces_expected_six_events(self):
        row,reviews=sh.parse_notice(notice(),c)
        self.assertEqual(len(row['events']),6)
        self.assertEqual(reviews,[])
        special=next(e for e in row['events'] if '특별공급' in e['label'])
        self.assertEqual((special['start'],special['end']),('2026-11-02','2026-11-03'))
        self.assertTrue(special['application'])
        self.assertEqual(row['house_manage_no'],'2026000373')
        events=c.manual_events(None,[row])
        self.assertEqual(len(events),6)
        self.assertEqual(events[0]['source'],'SH 공식 홈페이지 자동 수집')

    def test_region_cannot_be_inferred_from_contact_office(self):
        row,reviews=sh.parse_notice(notice(title='위례지구 9단지 분양주택 입주자모집공고',body='접수처: 서울특별시 강남구\n모집공고일: 2026.10.16'),c)
        self.assertIsNone(row)
        self.assertIn('공급 지역',reviews[0]['reason'])

    def test_explicit_seongnam_supply_address_allowed(self):
        row,_=sh.parse_notice(notice(title='위례지구 9단지 분양주택 입주자모집공고',body='공급위치: 경기도 성남시 수정구 테스트로 1\n모집공고일: 2026.10.16'),c)
        self.assertTrue(row['address'].startswith('경기도 성남시'))

    def test_rental_and_non_housing_titles_rejected(self):
        for title in ('행복주택 입주자 모집공고','임대주택 입주자모집공고','고덕 단지 분양상가 모집공고','마곡 단지 오피스텔 분양주택 모집공고'):
            self.assertFalse(sh.sale_title(title))

    def test_latest_correction_replaces_original_with_missing_management_number(self):
        newer=notice(title='[정정] 마곡지구 17단지 토지임대부 분양주택 입주자모집공고',body='정정 상세는 첨부 공고문 확인',posted='2026-03-10')
        older=notice(title='마곡지구 17단지 토지임대부 분양주택 입주자모집공고',posted='2026-02-27')
        self.assertEqual(sh.latest_notices([older,newer]),[newer])
        row,reviews=sh.parse_notice(newer,c)
        self.assertEqual([e['kind'] for e in row['events']],['notice-posted'])
        self.assertTrue(reviews)

    def test_ambiguous_dates_are_reviewed_and_never_use_posted_as_receipt(self):
        row,reviews=sh.parse_notice(notice(body='특별공급: 추후 안내'),c)
        self.assertFalse(any(e.get('application') for e in row['events']))
        self.assertEqual(row['events'][0]['kind'],'notice-posted')
        self.assertTrue(reviews)

    def test_repeated_label_does_not_silently_pick_one_period(self):
        body='\n'.join(['특별공급: 2026.11.02','특별공급: 2026.11.03','특별공급: 2026.11.04'])
        row,reviews=sh.parse_notice(notice(body=body),c)
        self.assertFalse(any(e.get('application') for e in row['events']))
        self.assertTrue(reviews)

    def test_explicit_cancellation_does_not_keep_quoted_old_dates(self):
        row,reviews=sh.parse_notice(notice(title='[취소] 고덕강일지구 3단지 토지임대부 분양주택 입주자모집공고'),c)
        self.assertEqual(row['events'],[])
        self.assertEqual(row['house_manage_no'],'2026000373')

    def test_pagination_uses_actual_visible_count(self):
        self.assertEqual(sh.pagination('총 3 건 [1/1페이지]',c),(3,1,1))
        with self.assertRaises(c.BuildError):sh.pagination('점검 중',c)

    def test_collect_reports_review_counts(self):
        counts=Counter()
        rows,report=sh.collect(c,counts,lambda today,core:([notice()],1))
        self.assertEqual(counts['sh_enabled'],1)
        self.assertEqual(counts['sh_collected_notices'],1)
        self.assertEqual(report['reviews'],[])
        self.assertEqual(len(rows),1)

    def test_browser_failures_do_not_return_empty_success(self):
        def reader(*args):raise RuntimeError('private browser detail')
        with self.assertRaises(c.BuildError) as result:sh.collect(c,Counter(),reader)
        self.assertNotIn('private',str(result.exception))


if __name__=='__main__':unittest.main()
