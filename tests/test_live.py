"""Opt-in acceptance against a running Rex. Only creates/removes its own session."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from picker import extract, screen_text
REX = os.environ.get('REX', 'rex')


@unittest.skipUnless(os.environ.get('REX_LIVE') == '1', 'requires REX_LIVE=1 and running Rex')
class LiveTests(unittest.TestCase):
    def call(self, *args):
        return subprocess.check_output([REX, *args], text=True, timeout=20)

    def wait_for(self, callback):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if callback():
                return
            time.sleep(0.1)
        self.fail('Timed out waiting for Rex acceptance condition')

    def test_picker_selection_copy_open_cancel_and_layout(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'opened'
            copied = Path(temp) / 'copied'
            long_url = 'https://long.example/' + 'segment/' * 24
            created = json.loads(self.call(
                'new', 'rex-open-url-test', '--json', '--shell=none', '--',
                sys.executable, '-c',
                'import time; print("https://example.com/a https://example.com/b"); '
                'print(' + repr(long_url) + ', flush=True); time.sleep(120)'))
            session = created['session_id']
            source = created['initial_windows'][0]['block_ids'][0]
            try:
                self.wait_for(lambda: 'https://example.com/b' in self.call('capture', '-s', session, '-b', source))
                snapshot = self.call('capture', '-s', session, '-b', source, '--format=vt', '--unwrap')
                self.assertEqual(extract(screen_text(snapshot, 24, 80)),
                                 ['https://example.com/a', 'https://example.com/b', long_url])
                baseline = json.loads(self.call('session', 'inspect', session, '--json'))['windows'][0]['layers'][0]
                entry = Path(temp) / 'entry.lua'
                # JSON string quoting is compatible for these paths and ASCII argv values.
                opener = [sys.executable, '-c',
                          'import sys; open(sys.argv[1],"a").write(sys.argv[2]+"\\n")', str(output)]
                copier = [sys.executable, '-c',
                          'import sys; open(sys.argv[1],"w").write(sys.stdin.read())', str(copied)]
                entry.write_text(
                    'local p = dofile(' + json.dumps(str(ROOT / 'lua/rex-open-url/init.lua')) + ')\n'
                    'p.setup({python=' + json.dumps(sys.executable) + ', rex=' + json.dumps(REX)
                    + ', open_command={' + ','.join(map(json.dumps, opener))
                    + '}, copy_command={' + ','.join(map(json.dumps, copier)) + '}})\n')

                def launch():
                    result = json.loads(self.call('do', str(entry), '--action', 'open_url',
                                                  '-s', session, '-b', source, '--json'))
                    block = result['block_ids'][0]
                    self.wait_for(lambda: 'https://example.com/b' in
                                  self.call('capture', '-s', session, '-b', block))
                    return block

                block = launch()
                self.call('send-key', '-s', session, '-b', block, 'tab')
                self.call('send-key', '-s', session, '-b', block, 'down')
                self.call('send-key', '-s', session, '-b', block, 'tab')
                self.call('send-key', '-s', session, '-b', block, 'ctrl+y')
                try:
                    self.wait_for(copied.exists)
                except AssertionError:
                    self.fail(self.call('capture', '-s', session, '-b', block))
                self.assertEqual(copied.read_text(), 'https://example.com/a\nhttps://example.com/b')
                self.call('send-key', '-s', session, '-b', block, 'enter')
                self.wait_for(lambda: output.exists() and len(output.read_text().splitlines()) == 2)
                self.assertEqual(output.read_text().splitlines(), ['https://example.com/a', 'https://example.com/b'])

                def restored():
                    window = json.loads(self.call('session', 'inspect', session, '--json'))['windows'][0]
                    return len(window['layers']) == 1 and window['focused_block_id'] == source

                self.wait_for(restored)
                entry.write_text('dofile(' + json.dumps(str(ROOT / 'lua/rex-open-url/init.lua')) + ')\n')
                block = launch()
                self.call('send', '-s', session, '-b', block, 'example.com/b')
                self.wait_for(lambda: '1 URLs' in self.call('capture', '-s', session, '-b', block))
                self.call('send-key', '-s', session, '-b', block, 'escape')
                self.wait_for(restored)
                final = json.loads(self.call('session', 'inspect', session, '--json'))['windows'][0]['layers'][0]
                self.assertEqual(final['layout'], baseline['layout'])
                self.assertEqual(final['bounds'], baseline['bounds'])
            finally:
                self.call('kill', session)


if __name__ == '__main__':
    unittest.main()
