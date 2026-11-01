from collections import Counter
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import calendar_builder as c
from test_sh import notice
from test_calendar import apt
import sh_source as sh

NOW=datetime(2026,11,2,tzinfo=timezone.utc)
OLD=datetime(2026,11,1,tzinfo=timezone.utc)


def old_calendar():
    row,_=sh.parse_notice(notice(),c)
    return c.render_ics(c.manual_events(None,[row]),OLD).decode('utf-8')


def fail(*args):
    raise c.BuildError('SH: 목록 읽기 실패 (TimeoutError).')


class ResilienceTests(unittest.TestCase):
    def test_previous_real_format_recovers_only_sh_with_same_uids(self):
        data=old_calendar()
        extra=c.normalize(c.ENDPOINTS[0],[apt()],Counter())
        mixed=c.render_ics(extra,OLD).decode().replace('END:VCALENDAR\r\n','')
        mixed+=''.join(c.retained_sh_components(data))+'END:VCALENDAR\r\n'
        components=c.retained_sh_components(mixed)
        self.assertEqual(len(components),6)
        self.assertEqual(components,c.retained_sh_components(data))

    def test_sh_failure_keeps_new_other_events_and_old_sh(self):
        prior={'updated_at':OLD.isoformat()}
        with patch.object(c,'read_previous',return_value=old_calendar()),patch.object(c,'previous_json',return_value={'reviews':[]}):
            events,components,report,health=c.sh_source_with_fallback(c,Counter(),fail,NOW,'https://example.github.io/repo/',prior)
        self.assertEqual(events,[])
        self.assertTrue(health['notify_failure'])
        self.assertEqual(health['last_success_at'],OLD.isoformat())
        self.assertEqual(health['state'],'stale')
        new=c.normalize(c.ENDPOINTS[0],[apt()],Counter())
        with tempfile.TemporaryDirectory() as tmp:
            total=c.build(tmp,new,{},NOW,'live',{'sh':health},components)
            self.assertEqual(total,10)
            data=Path(tmp,'calendar.ics').read_bytes().decode()
            for component in components:self.assertIn(component,data)
            status=json.loads(Path(tmp,'status.json').read_text())
            self.assertEqual(status['sources']['sh']['state'],'stale')
            self.assertIn('SH 갱신 실패',Path(tmp,'index.html').read_text())
            self.assertIn('캘린더 갱신 시각',Path(tmp,'index.html').read_text())

    def test_repeated_same_failure_is_quiet_and_timestamp_stays_old(self):
        previous={'state':'stale','message':'SH: 목록 읽기 실패 (TimeoutError).','last_success_at':OLD.isoformat()}
        prior={'updated_at':NOW.isoformat(),'sources':{'sh':previous}}
        with patch.object(c,'read_previous',return_value=old_calendar()),patch.object(c,'previous_json',return_value={'reviews':[]}):
            _,_,_,health=c.sh_source_with_fallback(c,Counter(),fail,NOW,'https://example.github.io/repo/',prior)
        self.assertFalse(health['notify_failure'])
        self.assertEqual(health['last_success_at'],OLD.isoformat())

    def test_recovery_is_fresh_and_does_not_reuse_old_components(self):
        row,_=sh.parse_notice(notice(),c)
        prior={'sources':{'sh':{'state':'stale','last_success_at':OLD.isoformat()}}}
        events,components,report,health=c.sh_source_with_fallback(c,Counter(),lambda *a:([row],{'reviews':[]}),NOW,'',prior)
        self.assertEqual(len(events),6)
        self.assertEqual(components,[])
        self.assertEqual(health['state'],'fresh')
        self.assertEqual(health['last_success_at'],NOW.isoformat())
        self.assertFalse(health['notify_failure'])

    def test_missing_browser_dependency_can_fall_back(self):
        def unavailable(*args):raise ImportError('private error')
        with patch.object(c,'read_previous',return_value=old_calendar()),patch.object(c,'previous_json',return_value={'reviews':[]}):
            _,components,_,health=c.sh_source_with_fallback(c,Counter(),unavailable,NOW,'https://example.github.io/repo/',{})
        self.assertEqual(len(components),6)
        self.assertNotIn('private',health['message'])

    def test_bad_sh_dates_also_isolated(self):
        row,_=sh.parse_notice(notice(),c);row['events'][0]['start']='not-a-date'
        with patch.object(c,'read_previous',return_value=old_calendar()),patch.object(c,'previous_json',return_value={}):
            _,components,_,health=c.sh_source_with_fallback(c,Counter(),lambda *a:([row],{}),NOW,'https://example.github.io/repo/',{})
        self.assertEqual(len(components),6)
        self.assertEqual(health['state'],'stale')

    def test_missing_backup_does_not_publish_calendar_without_previous_sh(self):
        with patch.object(c,'read_previous',return_value=None):
            with self.assertRaises(c.BuildError):c.sh_source_with_fallback(c,Counter(),fail,NOW,'',{})
        with self.assertRaises(c.BuildError):c.retained_sh_components('not an ICS')

    def test_unsupported_or_duplicate_retained_event_rejected(self):
        data=old_calendar()
        with self.assertRaises(c.BuildError):c.retained_sh_components(data.replace('DTEND;VALUE=DATE:', 'BROKEN:'))
        component=c.retained_sh_components(data)[0]
        with self.assertRaises(c.BuildError):c.retained_sh_components(data.replace('END:VCALENDAR',component+'END:VCALENDAR'))

    def test_github_outputs_report_alert_without_failing_calendar_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp,'output');summary=Path(tmp,'summary')
            with patch.dict(os.environ,{'GITHUB_OUTPUT':str(output),'GITHUB_STEP_SUMMARY':str(summary)}):
                c.write_health_outputs({'sh':{'state':'stale','notify_failure':True,'last_success_at':OLD.isoformat()}})
            self.assertEqual(output.read_text(),'sh_alert=true\n')
            self.assertIn('이전 SH 일정',summary.read_text())

    def test_previous_url_is_public_github_pages_only(self):
        with patch.dict(os.environ,{'PREVIOUS_SITE_URL':'https://someone.github.io/calendar/'}):
            self.assertEqual(c.previous_site(),'https://someone.github.io/calendar/')
        for url in ('http://someone.github.io/x','https://someone.github.io.evil.example/x','https://user:password@someone.github.io/x'):
            with patch.dict(os.environ,{'PREVIOUS_SITE_URL':url}):
                with self.assertRaises(c.BuildError):c.previous_site()

    def test_bootstrap_works_with_status_from_current_deployed_version(self):
        prior={'updated_at':OLD.isoformat(),'counts':{'sh_enabled':1,'sh_collected_notices':2}}
        with patch.object(c,'read_previous',return_value=old_calendar()),patch.object(c,'previous_json',return_value={}):
            _,components,_,health=c.sh_source_with_fallback(c,Counter(),fail,NOW,'https://example.github.io/repo/',prior)
        self.assertEqual(len(components),6)
        self.assertEqual(health['last_success_at'],OLD.isoformat())


if __name__=='__main__':unittest.main()
