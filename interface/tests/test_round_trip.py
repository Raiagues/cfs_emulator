import tempfile
import unittest
from unittest.mock import Mock, patch
from ground_station.round_trip import RoundTrips, TestPlans
from ground_station.station import GroundStation


CATALOG = {'commands': [{'id':'DEMO_NOOP_CC','app':'demo'}],
           'packets': [{'id':'DEMO_HK','fields':[{'name':'Count'}], 'mid':2049}]}
PLAN = {'name':'NOOP acknowledgement','command':'DEMO_NOOP_CC','timeout':5,
        'steps':[{'kind':'event','app':'DEMO','event_id':12,'message':'noop'},
                 {'kind':'packet','packet':'DEMO_HK','field':'Count','op':'increased'}]}
BASE = {2049:{'values':{'Count':7}}}
EVENT = {'mid':2056,'name':'EVS','app':'cfe_evs','event_id':2,'sequence':43,'received_at':8,'bytes':176,'errors':[],
         'values':{'PacketID.AppName':'DEMO','PacketID.EventID':12,'Message':'Demo NOOP received'}}
HK = dict(EVENT, mid=2049, app='demo', name='DEMO_HK',values={'Count':8})


class RoundTripTest(unittest.TestCase):
    def test_arm_catalog_keeps_receipts_on_the_requested_board(self):
        from interface.server import Studio, CATALOG_VERSION
        studio = Mock()
        stored = {'build_target': 'qemu', 'catalog_version': CATALOG_VERSION}
        studio.hardware._load.return_value = stored
        state = {'target': 'physical', 'fingerprint': 'a' * 64}
        self.assertEqual(Studio.freeze_catalog(studio, state)['build_target'], 'physical')
        self.assertEqual(stored['build_target'], 'qemu')

    def test_downlink_retries_only_setup_when_flight_receiver_starts_late(self):
        with tempfile.TemporaryDirectory() as root:
            station = GroundStation(root)
            station._connected = Mock(return_value=True)
            def observe_after_retry(*_, **kwargs):
                if station.send.call_count == 2:
                    station._received += 1
            station.send = Mock()
            with patch.object(station._updates, 'wait_for', side_effect=observe_after_retry):
                station._enable_downlink('TO_LAB_OUTPUT_ENABLE_CC', '127.0.0.1')
            self.assertEqual(station.send.call_count, 2)
            station.send.assert_called_with('TO_LAB_OUTPUT_ENABLE_CC', {'dest_IP':'127.0.0.1'}, automatic=True)

    def test_only_matching_ordered_evidence_advances(self):
        trips=RoundTrips()
        trips.start(trips.prepare(PLAN,CATALOG,BASE), {'event_id':1}, 'demo')
        for unrelated in (HK, dict(EVENT,event_id=0), dict(EVENT,app='other'),dict(EVENT, errors=['bad checksum']),
                          dict(EVENT,values=dict(EVENT['values'],Message='other')),
                          dict(EVENT,values=dict(EVENT['values'],**{'PacketID.AppName':'OTHER'}))):
            trips.observe(unrelated)
        self.assertEqual(trips.active['matched'],0)
        trips.observe(EVENT)
        trips.observe(dict(HK,event_id=3,values={'Count':7}))
        self.assertEqual(trips.active['matched'],1)
        trips.observe(dict(HK,event_id=4))
        self.assertEqual(trips.runs[-1]['status'],'passed')
        self.assertEqual(trips.runs[-1]['steps'][0]['observation']['sequence'],43)
        self.assertEqual(trips.runs[-1]['steps'][1]['baseline'],7)

    def test_timeout_missing_baseline_and_disconnect(self):
        trips=RoundTrips()
        with self.assertRaisesRegex(ValueError,'baseline'):
            trips.prepare(PLAN,CATALOG,{})
        with self.assertRaisesRegex(ValueError,'baseline'):
            trips.prepare(PLAN,CATALOG,{2049:dict(BASE[2049], errors=['truncated packet'])})
        with patch('ground_station.round_trip.time.monotonic',return_value=4):
            trips.start(trips.prepare(PLAN,CATALOG,BASE),{'event_id':1},'demo')
            with self.assertRaisesRegex(ValueError,'waiting'): trips.prepare(PLAN,CATALOG,BASE)
        with patch('ground_station.round_trip.time.monotonic',return_value=10):
            trips.observe(EVENT)
        self.assertEqual(trips.runs[-1]['status'],'timed_out')
        self.assertEqual(trips.runs[-1]['matched'],0)
        trips.start(trips.prepare(PLAN,CATALOG,BASE),{'event_id':2},'demo')
        trips.finish('disconnected')
        self.assertEqual(trips.runs[-1]['status'],'disconnected')

    def test_saved_suite_revisions_and_schema_changes(self):
        with tempfile.TemporaryDirectory() as root:
            plans=TestPlans(root)
            initial=plans.read()
            saved=plans.save({'plan':PLAN,'revision':initial['revision']},CATALOG)
            self.assertEqual(TestPlans(root).read()['plans'][0]['id'],saved['id'])
            with self.assertRaisesRegex(ValueError,'changed'):
                plans.save({'delete':True,'revision':initial['revision'],'id':saved['id']},CATALOG)
            altered={'commands':CATALOG['commands'],'packets':[]}
            with self.assertRaisesRegex(ValueError,'unavailable'):
                RoundTrips().prepare(saved['plans'][0],altered,BASE)
            self.assertEqual(plans.save({'delete':True,'id':saved['id'],'revision':saved['revision']},altered)['plans'],[])
