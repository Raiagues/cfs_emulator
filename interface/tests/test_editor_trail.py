import tempfile
import unittest
from pathlib import Path

from interface.backend.architecture_details import Constants, _calls, _command_sources, _read, _ref


class EditorTrailTests(unittest.TestCase):
    def test_prototypes_tags_and_evs_come_from_the_handlers_real_c(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            header = '''#ifdef __cplusplus
extern "C" {
#endif
/** @brief Set the sample period */
#define PERIOD_CC 4
#define PERIOD_EID 37
void SetPeriod(const Payload *p);
static inline void Other(Payload *p) { if (p) { use(p); } SetPeriod(p); }
#ifdef __cplusplus
}
#endif
struct Payload { unsigned interval; /**< @unit ms @range 1..200 */ };
'''
            source = '''void SetPeriod(const Payload *p)
{
    /* @check Validate the requested period */
    const char *text = "CFE_EVS_SendEvent(FAKE, INFO)";
    // CFE_EVS_SendEvent(FAKE_COMMENT, INFO)
    CFE_EVS_SendEvent(PERIOD_EID, INFO, "period");
    CFE_EVS_SendTimedEvent(now, PERIOD_EID, DEBUG, "time");
    CFE_EVS_SendEventWithAppID(PERIOD_EID, ERROR, app, "app");
}
'''
            files = {}
            for path, text in [('period.h', header), ('period.c', source)]:
                (root / path).write_text(text)
                files[path] = _read(root, root / path)
            constants = Constants(list(files.values()))
            handler = dict(id='period.c#SetPeriod', symbol='SetPeriod', path='period.c',
                           line=1, end_line=len(source.splitlines()))
            implementation = files['period.c']
            calls = [dict(api=name, args=args, function=handler, source=_ref(implementation, pos, name))
                     for name, pos, _, args in _calls(implementation) if name.startswith('CFE_EVS_')]
            row = dict(handler=handler, cc=constants.reference('PERIOD_CC'),
                       fields=[dict(source=dict(path='period.h', line=12))])
            _command_sources([{'handlers': [row]}], files, calls, constants)
            self.assertEqual([(r['path'], r['line']) for r in row['prototypes']], [('period.h', 7)])
            self.assertEqual([event['severity'] for event in row['events']], ['INFO', 'DEBUG', 'ERROR'])
            self.assertTrue(all(event['id']['value'] == 37 and event['id']['source']['line'] == 6 for event in row['events']))
            self.assertEqual([(a['tag'], a['line']) for a in row['annotations']], [('brief', 4), ('check', 3)])
            self.assertEqual([(a['tag'], a['value']) for a in row['fields'][0]['annotations']],
                             [('unit', 'ms'), ('range', '1..200')])


if __name__ == '__main__':
    unittest.main()
