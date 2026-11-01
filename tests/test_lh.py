from collections import Counter
from datetime import date
import io
import json
import unittest
from urllib.parse import parse_qs, urlsplit
import calendar_builder as c
import lh_source as lh


def notice(**changes):
    row = {'PAN_ID':'test-1','CCR_CNNT_SYS_DS_CD':'02','UPP_AIS_TP_CD':'05', 'SPL_INF_TP_CD':'050',
           'PAN_NM':'[합성] 성남 공공분양주택 입주자 모집', 'AIS_TP_CD_NM':'분양주택','PAN_NT_ST_DT':'2026.10.16',
           'CNP_CD_NM':'경기도','DTL_URL':'https://apply.lh.or.kr/','ALL_CNT':'1'}
    row.update(changes)
    return row


def detail():
    return {'dsSbd':[{'BZDT_NM':'[합성] 성남 분양 아파트','LCT_ARA_ADR':'경기도 성남시 분당구 테스트로 1'}],
            'dsCtrtPlc':[{'CTRT_PLC_ADR':'서울특별시 강남구 사무소'}],
            'dsSplScdl':[{'HS_SBSC_ACP_TRG_CD_NM':'특별공급',
            'ACP_DTTM':'2026.11.02 10:00 ~ 2026.11.03 17:00','PZWR_ANC_DT':'20261126'}]}


class LHTests(unittest.TestCase):
    def test_documented_response_envelope_and_errors(self):
        result = lh.unpack([{'dsSch':[]},{'resHeader':[{'SS_CODE':'Y'}],'dsList':[]}], c.BuildError)
        self.assertEqual(result['dsList'], [])
        for payload in ({'data':[]}, [{'resHeader':[{'SS_CODE':'N'}]}], []):
            with self.assertRaises(c.BuildError): lh.unpack(payload, c.BuildError)

    def test_list_uses_guide_parameters_and_pagination(self):
        calls=[]
        def request(url, params, key, error):
            calls.append(params)
            if params['UPP_AIS_TP_CD']=='39':return {'dsList':[]}
            return {'dsList':[notice(PAN_ID='test-'+str(params['PAGE']), ALL_CNT='2')]}
        rows=lh.list_notices('fake',date(2026,11,1),c.BuildError,request,lambda _:None)
        self.assertEqual(len(rows),2)
        self.assertEqual([x['PAGE'] for x in calls],[1,2,1])
        self.assertEqual(calls[0]['PAN_ED_DT'],'20261101')
        self.assertIn('PAN_ST_DT',calls[0])
        self.assertNotIn('PAN_NT_ST_DT',calls[0])

    def test_duplicate_list_page_rejected(self):
        def request(*args):return {'dsList':[notice(ALL_CNT='2')]}
        with self.assertRaises(c.BuildError):
            lh.list_notices('fake',date(2026,11,1),c.BuildError,request,lambda _:None)

    def test_key_encoding_is_compatible(self):
        urls=[]
        def opener(request,timeout):
            urls.append(request.full_url)
            return io.StringIO(json.dumps([{'resHeader':[{'SS_CODE':'Y'}]}]))
        for key in ('fake+/=','fake%2B%2F%3D'):
            lh.request_json(lh.LIST_URL,{},key,c.BuildError,opener)
        self.assertEqual(urls[0],urls[1])
        self.assertEqual(parse_qs(urlsplit(urls[0]).query)['serviceKey'],['fake+/='])

    def test_sale_filters_rental_and_officetel(self):
        self.assertTrue(lh.sale_candidate(notice()))
        for changes in ({'PAN_NM':'성남 오피스텔 분양'}, {'AIS_TP_CD_NM':'행복주택'},
                        {'PAN_NM':'10년 임대 분양전환'}, {'UPP_AIS_TP_CD':'06'}):
            self.assertFalse(lh.sale_candidate(notice(**changes)))
        self.assertTrue(lh.sale_candidate(notice(PAN_NM='토지임대부 분양주택')))

    def test_receipt_dates_reject_ambiguous_text(self):
        self.assertEqual(lh.receipt_dates('2026.11.02 10:00 ~ 2026.11.03 17:00',c.day),('2026-11-02','2026-11-03'))
        self.assertEqual(lh.receipt_dates('2026.11.2 (월) 10:00~17:00',c.day),('2026-11-02','2026-11-02'))
        for value in ('추후 공지','2026.11.02 ~ 11.03','2026.11.02부터 별도 통보','2026.11.02 ~'):
            self.assertIsNone(lh.receipt_dates(value,c.day))

    def test_exact_complex_address_and_not_office(self):
        events=lh.normalize_notice(notice(),detail(),c,Counter())
        self.assertEqual(len(events),3)
        self.assertEqual(events[1]['start'],'2026-11-02')
        self.assertEqual(events[1]['end'],'2026-11-03')
        data=detail();data['dsSbd'][0]['LCT_ARA_ADR']='경기도 수원시 테스트로 1'
        self.assertEqual(lh.normalize_notice(notice(),data,c,Counter()),[])

    def test_missing_schedule_dates_not_invented(self):
        data=detail();data['dsSplScdl'][0]['ACP_DTTM']='미정';counts=Counter()
        events=lh.normalize_notice(notice(),data,c,counts)
        self.assertEqual({e['kind'] for e in events},{'notice','winner'})
        self.assertEqual(counts['lh_unparsed_receipt_dates'],1)

    def test_collection_only_queries_supported_types(self):
        calls=[]
        def request(url,params,key,error):
            calls.append((url,params))
            if url==lh.LIST_URL:
                return {'dsList':[notice()]} if params['UPP_AIS_TP_CD']=='05' else {'dsList':[]}
            return detail()
        events=lh.collect('fake',date(2026,11,1),c,Counter(),request,lambda _:None)
        self.assertEqual(len(events),3)
        params=calls[-1][1]
        self.assertEqual(params,{'SPL_INF_TP_CD':'050','CCR_CNNT_SYS_DS_CD':'02','PAN_ID':'test-1','UPP_AIS_TP_CD':'05'})

    def test_missing_complex_info_is_reported_without_guessing_office_address(self):
        data=detail();del data['dsSbd'];counts=Counter()
        self.assertEqual(lh.normalize_notice(notice(),data,c,counts),[])
        self.assertEqual(counts['lh_missing_complex_info'],1)
        self.assertEqual(counts['lh_incomplete_detail_notices'],1)

    def test_missing_schedule_keeps_notice_and_does_not_invent_dates(self):
        data=detail();data['dsSplScdl']=None;counts=Counter()
        events=lh.normalize_notice(notice(),data,c,counts)
        self.assertEqual([event['kind'] for event in events],['notice'])
        self.assertEqual(counts['lh_missing_schedule_info'],1)
        self.assertIn('공고일만 표시',events[0]['note'])

    def test_malformed_dataset_still_fails(self):
        for name in ('dsSbd','dsSplScdl'):
            data=detail();data[name]={'unexpected':'shape'}
            with self.assertRaises(c.BuildError):lh.normalize_notice(notice(),data,c,Counter())

    def test_all_missing_complexes_blocks_publish_and_passes_subtype(self):
        calls=[]
        def request(url,params,key,error):
            if url==lh.LIST_URL:
                return {'dsList':[notice(AIS_TP_CD='05')]} if params['UPP_AIS_TP_CD']=='05' else {'dsList':[]}
            calls.append(params)
            return {'resHeader':[{'SS_CODE':'Y'}]}
        with self.assertRaises(c.BuildError):
            lh.collect('fake',date(2026,11,1),c,Counter(),request,lambda _:None)
        self.assertEqual(calls[0]['AIS_TP_CD'],'05')

    def test_partial_detail_gap_does_not_drop_valid_notice(self):
        def request(url,params,key,error):
            if url==lh.LIST_URL:
                return {'dsList':[notice(PAN_ID='one',ALL_CNT='2'),notice(PAN_ID='two',ALL_CNT='2')]} if params['UPP_AIS_TP_CD']=='05' else {'dsList':[]}
            return detail() if params['PAN_ID']=='two' else {'resHeader':[{'SS_CODE':'Y'}]}
        counts=Counter()
        events=lh.collect('fake',date(2026,11,1),c,counts,request,lambda _:None)
        self.assertEqual(len(events),3)
        self.assertEqual(counts['lh_missing_complex_info'],1)

    def test_land_lease_building_sale_in_existing_applyhome(self):
        from test_calendar import apt
        row=apt();row['HOUSE_NM']='고덕강일 토지임대부 분양주택'
        self.assertTrue(c.normalize(c.ENDPOINTS[0],[row],Counter()))
        row['RENT_SECD']='1'
        self.assertEqual(c.normalize(c.ENDPOINTS[0],[row],Counter()),[])


if __name__=='__main__':unittest.main()
