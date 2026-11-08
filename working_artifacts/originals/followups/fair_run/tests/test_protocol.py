import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rq3_protocol import ARMS, SYSTEM_PROMPT, PROMPT_SHA256, render, validate
from lexical_checks import scan

class ProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=[json.loads(s) for s in (Path(__file__).resolve().parents[1]/'examples/cases_SYNTHETIC_DEMO.jsonl').read_text().splitlines()]
    def test_same_system_prompt_and_nested_information(self):
        for row in self.rows:
            d={a:render(row,a) for a in ARMS}
            self.assertEqual(len(set(d[a][0]['content'] for a in ARMS)),1)
            self.assertEqual(set(d[a][0]['role'] for a in ARMS),{'system'})
            for a in ARMS:self.assertIn(row['review_text'],d[a][1]['content'])
            self.assertNotIn('RAW TRACKER CLOSURE FIELDS',d['binary_state'][1]['content'])
            self.assertIn('RAW TRACKER CLOSURE FIELDS',d['raw_metadata'][1]['content'])
            self.assertIn('RAW TRACKER CLOSURE FIELDS',d['closure_aware'][1]['content'])
            self.assertNotIn('NORMALIZED TAXONOMY FIELDS',d['raw_metadata'][1]['content'])
            self.assertIn('NORMALIZED TAXONOMY FIELDS',d['closure_aware'][1]['content'])
            self.assertNotIn('ACTION-SPECIFIC GUIDANCE',d['closure_aware'][1]['content'])
    def test_validate(self):
        self.assertEqual(validate(self.rows,3,2)['requests'],9)
    def test_known_bug(self):
        self.assertIn('do not claim anyone is working on it',SYSTEM_PROMPT)
        self.assertNotIn('say the team is investigating',SYSTEM_PROMPT)
        self.assertNotIn('Treat a closed issue as resolved/closed',SYSTEM_PROMPT)
    def test_redirect_lexical(self):
        a=scan('This was closed as a duplicate.','duplicate','REDIRECTED','REDIRECTED')
        b=scan('This is now tracked in another issue.','duplicate','REDIRECTED','REDIRECTED')
        self.assertFalse(a['redirected_route_screen'])
        self.assertTrue(b['redirected_route_screen'])
    def test_needs_info_lexical(self):
        a=scan('Logs were mentioned.','NEEDS_INFO','ABANDONED','ABANDONED_NEEDS_INFO')
        b=scan('Please provide app version and logs.','NEEDS_INFO','ABANDONED','ABANDONED_NEEDS_INFO')
        self.assertFalse(a['needs_info_request_screen'])
        self.assertTrue(b['needs_info_request_screen'])

if __name__=='__main__': unittest.main()
