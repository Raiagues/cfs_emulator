"""Synthetic fixtures for analysis only; these are never study measurements."""
from copy import deepcopy
import csv
import json
from pathlib import Path
import tempfile
import unittest

from validation.protocol import LEVELS
from validation.summarize import APPS, MODEL_APPS, MODELS, TARGETS, CampaignError, stats, summarize


def write(root, name, value):
    path = root / name; path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def packet(mid=0x0883, sequence=1, event_id=2, at=2, values=None):
    return dict(mid=mid, sequence=sequence, event_id=event_id, received_at=at,
                errors=[], hex='0803c00100010000', values=values or {})


def campaign(root):
    write(root, 'prepare.json', dict(status='passed', protocol='final-technical-v1', platform_commit='a'*40,
        nasa_commit='b'*40, source_method='independent copy of official local checkout', nasa_originals_unchanged=True,
        sensors=[dict(app=app) for app in APPS[1:]], private='ssh-secret-must-not-be-exported'))
    units = {model: {channel:'fixture-unit' for channel in LEVELS[model][0]} for model in MODELS}
    runs = []
    for model in MODELS:
        for rep in range(1, 4):
            for scenario in ('constant', 'step', 'dropout'):
                samples = []
                for index in range(15):
                    values = LEVELS[model][index//5 if scenario=='step' else 0]
                    disconnected = scenario=='dropout' and 5 <= index < 10
                    samples.append(dict(index=index, disconnected=disconnected, input_scaled=values,
                        input={key:value/1000 for key,value in values.items()}, register_hex='00'*256,
                        status=-1 if disconnected else 0, read_scaled={} if disconnected else values,
                        read={} if disconnected else {key:value/1000 for key,value in values.items()},
                        tolerance={key:.002 for key in values}))
                runs.append(dict(model=model, repetition=rep, scenario=scenario, units=units[model], samples=samples,
                                 passed=True, checks={'valid':True, 'dropout':True, 'recovery':True}))
    write(root, 'registers/registers.json', dict(status='passed', repetitions=3, samples=405, runs=runs))
    for target in TARGETS:
        commands = []
        for app in APPS:
            counter = 5
            for rep in range(1, 4):
                for kind in ('NOOP_CC', 'RESET_COUNTERS_CC', 'NOOP_CC'):
                    index=len(commands); send_id=index*10+10; sequence=index*2
                    before=packet(sequence=sequence,event_id=send_id-2,at=send_id-2,
                                  values={'CommandCounter':counter,'CommandErrorCounter':0})
                    counter=0 if kind=='RESET_COUNTERS_CC' else (counter+1)%256
                    sent=dict(id=app.upper()+'_'+kind, app=app, mid=0x1882, code=1 if kind.startswith('RESET') else 0,
                              event_id=send_id, sent_at=send_id, hex='1882c000000100ff')
                    baseline_evs=packet(0x0808,sequence,event_id=send_id-1,at=send_id-1)
                    event=packet(0x0808,sequence+1,event_id=send_id+1,at=send_id+1,
                                 values={'PacketID.AppName':app.upper(),'Message':'RESET' if kind.startswith('RESET') else 'NOOP'})
                    hk=packet(sequence=sequence+1,event_id=send_id+2,at=send_id+2,
                              values={'CommandCounter':counter,'CommandErrorCounter':0})
                    commands.append(dict(app=app,repetition=rep,command=sent['id'],sent=sent,event=event,baseline=before,
                        housekeeping=hk,event_baselines={str(0x0808):baseline_evs},expected_counter=counter,
                        expected_error_counter=0,status='passed',passed=True))
        write(root,f'{target}/commands.json',commands)
        sensors=[]
        for level in range(1 if target=='physical' else 3):
            for model in MODELS:
                valid=target!='physical' or model=='mpu6050'; values=LEVELS[model][level]
                packets=[packet(mid=0x0900,sequence=i+1,event_id=i+1,at=i+11,
                    values={**values,'Valid':int(valid),'Status':0 if valid else -1}) for i in range(5)]
                raw={'status':'read' if valid else 'unavailable', 'operation':'linux_i2c_rdwr', 'bus':1, 'address':104,
                     'blocks':[{'register':59,'size':2,'hex':'1234'}], 'host':'ssh-secret-must-not-be-exported'}
                sensors.append(dict(model=model,app=MODEL_APPS[model],level=level,mid=0x0900,expected_scaled=None if target=='physical' else values,
                    tolerance_scaled=None if target=='physical' else {key:2 for key in values},units=units[model],field_mapping={key:key for key in values},
                    raw_registers=raw,packets=packets,passed=True,status='passed',valid_expected=valid,input_applied_at=10))
        write(root,f'{target}/sensors.json',sensors)
        write(root,f'{target}/target.json',dict(status='passed',target=target,command_repetitions=3,sensor_samples_per_level=5,
                                               commands=36,sensor_cases=len(sensors),dropout_cases=3 if target=='native' else 0))
        files={'core-cpu1':'c'*64,'cf/module.so':'d'*64,'cf/table.tbl':'e'*64,'cf/cfe_es_startup.scr':'f'*64}
        write(root,f'{target}/artifacts.json',dict(passed=True,build_fingerprint='f'*64,local=files,installed=files,differences=[]))
    dropout=[]
    for model in MODELS:
        before=packet(values={'Valid':1,'Status':0})
        invalid=[packet(sequence=i+2,at=i+4,values={'Valid':0,'Status':-1}) for i in range(5)]
        recovery=[packet(sequence=7,at=11,values={'Valid':0,'Status':-1}), packet(sequence=8,at=12,values={'Valid':1,'Status':0})]
        dropout.append(dict(model=model,status='passed',passed=True,before=before,invalid=invalid,removed_at=3,restored_at=10,
                            recovery_observations=recovery,recovery_latency_s=2,recovery_bound_s=5))
    write(root,'native/dropout.json',dropout)
    for target in ('native','qemu'):
        write(root,f'build-{target}/metrics.json',dict(kind='full_build',target=target,status='passed',n=1,
            measurement={'status':'succeeded','elapsed_s':10 if target=='native' else 20,'result':{'fingerprint':'f'*64}}))
    write(root,'cycles-native/metrics.json',dict(kind='development_cycles',target='native',planned_n=10,status='passed',
        cycles=[dict(repetition=i,create_s=i/10,build_s=i,delete_s=.05) for i in range(1,11)],restoration_build={'exit_code':0,'elapsed_s':999}))
    for target in TARGETS:
        for kind in (('cfs_starts','guest_boots') if target=='qemu' else ('cfs_starts',)):
            count=5 if kind=='guest_boots' else 10; rows=[]
            for rep in range(1,count+1):
                operation={'status':'succeeded','elapsed_s':2,'operational_observed_s':1.2,'phases':[]}
                if target!='native':operation['phases'].append({'phase':'payload_transfer','start_s':.2,'end_s':.7,'elapsed_s':.5})
                row=dict(repetition=rep,run_to_operational=operation,ground_to_first_hk={'elapsed_s':.5,
                    'enable':{'event_id':1,'sent_at':1},'first_hk':packet()},total_to_first_hk_s=5.7 if kind=='guest_boots' else 2.7)
                if kind=='guest_boots':row['guest_boot_to_ssh']={'status':'succeeded','elapsed_s':3,'guest_ssh_ready_observed_s':2}
                rows.append(row)
            folder='boots-qemu' if kind=='guest_boots' else 'starts-'+target
            write(root,f'{folder}/metrics.json',dict(kind=kind,target=target,planned_n=count,status='passed',runs=rows))


def table(output,name):
    with (output/(name+'.csv')).open() as stream:return list(csv.DictReader(stream))


class EvaluationSummaryTest(unittest.TestCase):
    def test_complete_fixture_counts_statistics_and_no_private_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'campaign'; root.mkdir(); campaign(root)
            output=Path(directory)/'tables'; result=summarize(root,output)
            self.assertTrue(result['publishable']);self.assertTrue(result['complete'])
            self.assertEqual(result['q1']['confirmed'],108)
            self.assertEqual(result['q3']['register_hal'],{'episodes':9,'invalid_readings':45})
            outages=table(output,'q3_hal_samples');self.assertEqual(len(outages),135)
            self.assertEqual(sum(row['valid']=='0' for row in outages),45)
            self.assertEqual(result['q3']['flight_telemetry'],{'episodes':3,'invalid_readings':15})
            self.assertEqual(result['q4']['arm_files'],4);self.assertTrue(result['q4']['identical'])
            self.assertEqual(result['q4']['categories'],{'executable':1,'loadable_module':1,'table':1,'startup':1})
            commands=table(output,'q1_commands')
            self.assertEqual({row['sent'] for row in commands if row['command']=='NOOP_CC'},{'6'})
            self.assertEqual({row['sent'] for row in commands if row['command']=='RESET_COUNTERS_CC'},{'3'})
            cycles=next(row for row in table(output,'q5_statistics') if row['kind']=='development_cycles' and row['stage']=='build_s')
            self.assertEqual((cycles['n'],float(cycles['median']),float(cycles['iqr'])),('10',5.5,4.5))
            build=next(row for row in table(output,'q5_statistics') if row['kind']=='full_build' and row['target']=='native')
            self.assertEqual((build['n'],build['iqr']),('1',''))
            self.assertNotIn('999',','.join(row['seconds'] for row in table(output,'q5_timings')))
            physical=table(output,'physical_readings')
            self.assertTrue(all(row['n']=='0' and row['median']=='' for row in physical if row['model']!='mpu6050'))
            self.assertTrue(all(row['target']!='physical' for row in table(output,'q2_errors')))
            exported=''.join(path.read_text() for path in output.iterdir())
            self.assertNotIn('ssh-secret-must-not-be-exported',exported)

    def test_missing_or_failed_campaign_never_creates_final_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'campaign'; root.mkdir(); campaign(root)
            report=json.loads((root/'native/target.json').read_text());report['status']='failed';write(root,'native/target.json',report)
            (root/'physical/commands.json').unlink()
            output=Path(directory)/'result'
            with self.assertRaisesRegex(CampaignError,'incomplete'):summarize(root,output)
            self.assertFalse(output.exists())
            partial=summarize(root,output,partial=True)
            self.assertEqual(partial['status'],'partial');self.assertFalse(partial['publishable']);self.assertFalse(partial['complete'])
            self.assertTrue(partial['issues'])
            with self.assertRaisesRegex(CampaignError,'publication'):summarize(root,Path(directory)/'final',partial=True)

    def test_flags_cannot_hide_bad_counter_error_or_incomplete_repetition(self):
        changes=[('native/commands.json',lambda rows:rows[0]['housekeeping']['values'].__setitem__('CommandCounter',99)),
                 ('qemu/sensors.json',lambda rows:rows[0]['packets'][0]['values'].__setitem__('temperature',999999)),
                 ('starts-native/metrics.json',lambda report:report['runs'].pop()),
                 ('physical/artifacts.json',lambda report:report['installed'].__setitem__('core-cpu1','0'*64)),
                 ('native/dropout.json',lambda rows:rows[0]['invalid'][2]['values'].__setitem__('Valid',1))]
        for filename,change in changes:
            with self.subTest(filename=filename),tempfile.TemporaryDirectory() as directory:
                root=Path(directory)/'campaign';root.mkdir();campaign(root)
                data=json.loads((root/filename).read_text());change(data);write(root,filename,data)
                output=Path(directory)/'result'
                with self.assertRaises(CampaignError):summarize(root,output)
                self.assertFalse(output.exists())

    def test_quartiles_and_nonfinite_values(self):
        self.assertEqual(stats([1,2,3,4]),dict(n=4,min=1,median=2.5,max=4,q1=1.75,q3=3.25,iqr=1.5))
        self.assertEqual(stats([9]),dict(n=1,min=9,median=9,max=9))
        with self.assertRaises(CampaignError):stats([float('nan')])


if __name__=='__main__':unittest.main()
