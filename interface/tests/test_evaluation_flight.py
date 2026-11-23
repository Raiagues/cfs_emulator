"""Unit evidence: stale UDP deliveries must not become successful Q1 measurements."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from validation.flight import Flight, fresh, sequence_after


def packet(mid=0x0883, sequence=10, event_id=8, at=8, counter=2, message=None):
    values = {'CommandCounter': counter, 'CommandErrorCounter': 0}
    if message is not None:
        values = {'PacketID.AppName': 'SAMPLE_APP', 'PacketID.EventID': 2, 'Message': message}
    return {'mid': mid, 'sequence': sequence, 'event_id': event_id, 'received_at': at,
            'errors': [], 'values': values, 'hex': f'{mid:04x}{sequence:04x}{counter:02x}',
            'app': 'cfe_evs' if message is not None else 'sample_app'}


class CommandLab:
    """One command, with earlier wire packets delivered again after the send."""
    def __init__(self, baseline_sequence=10, include_new=True):
        hk = packet(sequence=baseline_sequence)
        evs = packet(mid=0x0808, sequence=20, event_id=9, at=9, message='NOOP received')
        self.before = {'connected': True, 'packets': [hk], 'history': [hk, evs], 'events': [evs]}
        duplicate = {**evs, 'event_id': 11, 'received_at': 11}
        old_hk = packet(sequence=(baseline_sequence - 1) % 16384, event_id=13, at=13, counter=3)
        events, history, latest = [duplicate], [duplicate, old_hk], old_hk
        if include_new:
            reply = packet(mid=0x0808, sequence=21, event_id=12, at=12, message='NOOP received')
            latest = packet(sequence=(baseline_sequence + 1) % 16384, event_id=14, at=14, counter=3)
            events.append(reply); history.extend([reply, latest])
        self.after = {'connected': True, 'packets': [latest], 'history': sorted(history, key=lambda p:p['event_id']), 'events': events}
        self.calls = 0

    def ground_snapshot(self):
        return deepcopy(self.after if self.calls else self.before)

    def ground_send(self, body):
        self.calls += 1
        if self.calls > 1:
            raise RuntimeError('End of unit fixture after one command')
        return {'event_id': 10, 'sent_at': 10, 'app': 'sample_app', 'id': body['command_id'],
                'mid': 0x1882, 'code': 0, 'values': {}, 'hex': '1882c000000100ff'}


def controller(output, lab):
    flight = Flight.__new__(Flight)
    flight.output = Path(output)
    flight.target = 'native'
    flight.timeout = .01
    flight.private = []
    flight.lab = lab
    flight.catalog = {'packets': [
        {'id': 'SAMPLE_APP_HK_TLM_MID', 'app': 'sample_app', 'mid': 0x0883,
         'fields': [{'name': 'CommandCounter'}, {'name': 'CommandErrorCounter'}]},
        {'id': 'CFE_EVS_LONG_EVENT_MSG_MID', 'app': 'cfe_evs', 'mid': 0x0808,
         'fields': [{'name': 'PacketID.AppName'}, {'name': 'PacketID.EventID'}, {'name': 'Message'}]}]}
    return flight


class EvaluationFlightTest(unittest.TestCase):
    def test_sequence_progress_rejects_duplicates_and_backward_delivery_and_accepts_wrap(self):
        for new, old, expected in [(11, 10, True), (10, 10, False), (9, 10, False),
                                    (0, 16383, True), (16383, 0, False), (8192, 0, False)]:
            with self.subTest(new=new, old=old):
                self.assertEqual(sequence_after(new, old), expected)

    def test_host_reception_freshness_alone_does_not_prove_a_new_wire_packet(self):
        baseline = packet()
        sent = {'event_id': 10, 'sent_at': 10}
        valid = packet(sequence=11, event_id=11, at=11)
        self.assertTrue(fresh(valid, sent, baseline))
        for changes in ({'event_id': 10}, {'received_at': 9}, {'errors': ['decode']},
                        {'mid': 0x0999}, {'sequence': 10}, {'sequence': 9}):
            with self.subTest(changes=changes):
                self.assertFalse(fresh({**valid, **changes}, sent, baseline))

    def test_q1_uses_new_evs_and_forward_hk_for_each_actual_send(self):
        for baseline_sequence in (10, 16383):
            with self.subTest(baseline_sequence=baseline_sequence), tempfile.TemporaryDirectory() as directory:
                flight = controller(directory, CommandLab(baseline_sequence))
                with patch('validation.flight.SENSORS', ()), patch('validation.flight.time.sleep', lambda _: None):
                    with self.assertRaisesRegex(RuntimeError, 'End of unit fixture'):
                        flight.commands(1)
                first = json.loads((Path(directory) / 'commands.json').read_text())[0]
                self.assertEqual(first['event']['sequence'], 21, 'Repeated old EVS must not confirm the command')
                self.assertEqual(first['housekeeping']['sequence'], (baseline_sequence + 1) % 16384,
                                 'A different but backward HK sequence must not confirm the counter')
                self.assertEqual(first['expected_counter'], 3)
                self.assertEqual(first['sent']['event_id'], 10)

    def test_packets_replayed_before_send_cannot_roll_back_the_sequence_baselines(self):
        lab = CommandLab()
        old_hk = packet(sequence=9, event_id=1, at=1, counter=2)
        old_evs = packet(mid=0x0808, sequence=20, event_id=2, at=2, message='NOOP received')
        peak_hk = packet(sequence=10, event_id=3, at=3, counter=3)
        peak_evs = packet(mid=0x0808, sequence=21, event_id=4, at=4, message='NOOP received')
        replay_hk = {**old_hk, 'event_id': 5, 'received_at': 5}
        replay_evs = {**old_evs, 'event_id': 6, 'received_at': 6}
        lab.before = {'connected': True, 'packets': [replay_hk],
                      'history': [old_hk, old_evs, peak_hk, peak_evs, replay_hk, replay_evs],
                      'events': [old_evs, peak_evs, replay_evs]}
        stale_reply = {**peak_evs, 'event_id': 11, 'received_at': 11}
        stale_counter = {**peak_hk, 'event_id': 12, 'received_at': 12}
        new_reply = packet(mid=0x0808, sequence=22, event_id=13, at=13, message='NOOP received')
        new_counter = packet(sequence=11, event_id=14, at=14, counter=4)
        lab.after = {'connected': True, 'packets': [new_counter],
                     'history': [stale_reply, stale_counter, new_reply, new_counter],
                     'events': [stale_reply, new_reply]}
        with tempfile.TemporaryDirectory() as directory:
            flight = controller(directory, lab)
            with patch('validation.flight.SENSORS', ()), patch('validation.flight.time.sleep', lambda _: None):
                with self.assertRaisesRegex(RuntimeError, 'End of unit fixture'):
                    flight.commands(1)
            first = json.loads((Path(directory) / 'commands.json').read_text())[0]
            self.assertEqual(first['baseline']['sequence'], 10)
            self.assertEqual(first['event']['sequence'], 22)
            self.assertEqual(first['expected_counter'], 4)
            self.assertEqual(first['housekeeping']['sequence'], 11)

    def test_q1_times_out_when_only_replayed_packets_arrive(self):
        with tempfile.TemporaryDirectory() as directory:
            flight = controller(directory, CommandLab(include_new=False))
            with patch('validation.flight.SENSORS', ()), patch('validation.flight.time.sleep', lambda _: None):
                with self.assertRaisesRegex(RuntimeError, 'Timed out'):
                    flight.commands(1)
            records = json.loads((Path(directory) / 'commands.json').read_text())
            self.assertFalse(any(row.get('passed') for row in records))
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]['status'], 'failed')
            self.assertEqual(records[0]['sent']['event_id'], 10)
            self.assertIn('baseline', records[0])

    def test_collect_retains_distinct_consecutive_packets_including_a_bad_value(self):
        rows = [packet(sequence=1, at=9), packet(sequence=2, at=11),
                packet(sequence=2, at=12), packet(sequence=3, at=13, counter=99)]
        flight = controller('.', SimpleNamespace(ground_snapshot=lambda: {'history': rows}))
        with patch('validation.flight.time.sleep', lambda _: None):
            result = flight.collect(0x0883, 2, 10)
        self.assertEqual([row['sequence'] for row in result], [2, 3])
        self.assertEqual(result[1]['values']['CommandCounter'], 99)

    def test_collect_decoder_error_is_a_failure_not_a_discarded_sample(self):
        bad = {**packet(sequence=2, at=11), 'errors': ['payload truncated']}
        flight = controller('.', SimpleNamespace(ground_snapshot=lambda: {'history': [bad]}))
        with self.assertRaisesRegex(ValueError, 'decoder failed'):
            flight.collect(0x0883, 1, 10)


class EvaluationDropoutTest(unittest.TestCase):
    def test_valid_packet_during_outage_fails_and_restores_register_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = root / 'project/apps'; metadata.mkdir(parents=True)
            (metadata / 'fixture.json').write_text(json.dumps({'period_ticks': 10, 'sensors': [{'name': 'sample', 'tlm_mid': 0x0900}]}))
            registers = root / 'registers.bin'; registers.write_bytes(b'original registers')
            sensor = {'model': 'tmp105', 'app': 'fixture', 'device': 'fixture'}
            valid = {**packet(mid=0x0900), 'values': {'Valid': 1, 'Status': 0}}
            invalid = {**packet(mid=0x0900, sequence=11, at=11), 'values': {'Valid': 0, 'Status': -1}}
            bad = {**packet(mid=0x0900, sequence=12, at=12), 'values': {'Valid': 1, 'Status': 0}}
            lab = SimpleNamespace(workspace=SimpleNamespace(mission=SimpleNamespace(schedule_config=lambda: {'tick_hz': 10})))
            flight = controller(root, lab); flight.root = root
            flight.collect = Mock(side_effect=[[valid], [invalid], [bad]])
            config = {'board': 'fixture', 'devices': [{'id': 'fixture'}]}
            with patch('validation.flight.SENSORS', (sensor,)), patch('validation.flight.load_config', return_value=config), \
                 patch('validation.flight.board_catalog', return_value={}), patch('sensors.registers.register_file', return_value=registers):
                with self.assertRaisesRegex(ValueError, 'interleaved'):
                    flight.dropout(2)
            self.assertEqual(registers.read_bytes(), b'original registers')
            self.assertFalse(registers.with_suffix('.evaluation-disconnected').exists())
            record = json.loads((root / 'dropout.json').read_text())[0]
            self.assertFalse(record['passed'])
            self.assertEqual(record['status'], 'failed')
            self.assertEqual([row['values']['Valid'] for row in record['invalid']], [0, 1])
            # Only locating the transition may filter. Following packets are retained.
            self.assertEqual(len(flight.collect.call_args_list[2].args), 3)
            self.assertNotIn('predicate', flight.collect.call_args_list[2].kwargs)


class EvaluationTimingTest(unittest.TestCase):
    def fake_flight(self, output, *, guest=True, operational=True):
        result = {'elapsed_s': 5.0, 'status': 'succeeded'}
        if operational:
            result['operational_observed_s'] = 2.0
        return SimpleNamespace(output=Path(output),
            lab=SimpleNamespace(hardware=SimpleNamespace(_qemu_running=lambda: guest), ground=SimpleNamespace(stop=Mock())),
            job=Mock(return_value=result), connect=Mock(return_value={'elapsed_s': 3.0}),
            close=Mock(), redact=lambda text: text)

    def test_run_total_is_not_reported_as_time_of_the_operational_marker(self):
        from validation.metrics import starts
        with tempfile.TemporaryDirectory() as directory:
            flight = self.fake_flight(directory)
            with patch('validation.metrics.Flight', return_value=flight):
                report = starts('unused', directory, 'native', repetitions=1, leave_running=True)
            self.assertEqual(report['status'], 'passed')
            self.assertEqual(report['summary']['run_total_s']['median'], 5.0)
            self.assertEqual(report['summary']['operational_observed_s']['median'], 2.0)
            self.assertEqual(report['summary']['run_total_s']['n'], 1)
            flight.job.assert_called_once_with('run')
            flight.close.assert_called_once()

    def test_successful_job_without_operational_evidence_cannot_pass_the_measurement(self):
        from validation.metrics import starts
        with tempfile.TemporaryDirectory() as directory:
            flight = self.fake_flight(directory, operational=False)
            with patch('validation.metrics.Flight', return_value=flight):
                with self.assertRaisesRegex(ValueError, 'OPERATIONAL'):
                    starts('unused', directory, 'native', repetitions=1, leave_running=True)
            report = json.loads((Path(directory) / 'metrics.json').read_text())
            self.assertEqual(report['status'], 'failed')
            self.assertEqual(report['runs'], [])
            self.assertNotIn('summary', report)
            flight.connect.assert_not_called()
            flight.close.assert_called_once()

    def test_cfs_start_measurement_cannot_silently_include_qemu_boot(self):
        from validation.metrics import starts
        with tempfile.TemporaryDirectory() as directory:
            flight = self.fake_flight(directory, guest=False)
            with patch('validation.metrics.Flight', return_value=flight):
                with self.assertRaisesRegex(ValueError, 'already running'):
                    starts('unused', directory, 'qemu', repetitions=1, leave_running=True)
            report = json.loads((Path(directory) / 'metrics.json').read_text())
            self.assertEqual(report['status'], 'failed')
            self.assertEqual(report['runs'], [])
            flight.job.assert_not_called()
            flight.connect.assert_not_called()
            flight.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
