"""Opt-in acceptance against a running Rex. Only creates/removes its own session."""
from http.server import BaseHTTPRequestHandler, HTTPServer
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
NATIVE_UI = os.environ.get('REX_LIVE_UI') == '1'


@unittest.skipUnless(os.environ.get('REX_LIVE') == '1', 'requires REX_LIVE=1 and running Rex')
class LiveTests(unittest.TestCase):
    def call(self, *args):
        return subprocess.check_output([REX, *args], text=True, timeout=90 if NATIVE_UI else 20)

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
            first, second = 'https://example.com/a', 'https://example.com/b'
            if NATIVE_UI:
                requests = []

                class Handler(BaseHTTPRequestHandler):
                    def do_GET(self):
                        requests.append(self.path)
                        self.send_response(204)
                        self.end_headers()

                server = HTTPServer(('127.0.0.1', 0), Handler)
                self.addCleanup(server.server_close)
                server.timeout = 8
                local = f'http://127.0.0.1:{server.server_port}'
                first, second = local + '/first', local + '/second'
            created = json.loads(self.call(
                'new', 'rex-open-url-test', '--json', '--shell=none', '--',
                sys.executable, '-c',
                'import sys, time; print(*sys.argv[1:], sep="\\n", flush=True); time.sleep(300)',
                first, second, long_url))
            session = created['session_id']
            source = created['initial_windows'][0]['block_ids'][0]
            try:
                self.wait_for(lambda: second in self.call('capture', '-s', session, '-b', source))
                snapshot = self.call('capture', '-s', session, '-b', source, '--format=vt', '--unwrap')
                self.assertEqual(extract(screen_text(snapshot, 24, 80)), [first, second, long_url])
                def window_state():
                    window = json.loads(self.call('session', 'inspect', session, '--json'))['windows'][0]
                    return window['focused_block_id'], window['layers']

                if NATIVE_UI:
                    input('Switch the Rex app to the rex-open-url-test session, then press Enter here. ')
                    baseline = window_state()
                    print('Filter for /second, then press Return on the highlighted URL.', flush=True)
                    self.call('do', 'open_url', '-s', session, '-b', source, '--timeout', '75s')
                    server.handle_request()
                    self.assertEqual(requests, ['/second'])
                    self.assertEqual(window_state(), baseline)
                    return

                baseline = window_state()
                entry = Path(temp) / 'entry.lua'
                # JSON string quoting is compatible for these paths and ASCII argv values.
                opener = [sys.executable, '-c',
                          'import sys; open(sys.argv[1],"a").write(sys.argv[2]+"\\n")', str(output)]
                copier = [sys.executable, '-c',
                          'import sys; open(sys.argv[1],"w").write(sys.stdin.read())', str(copied)]
                setup = (
                    'local p = dofile(' + json.dumps(str(ROOT / 'lua/rex-open-url/init.lua')) + ')\n'
                    'p.setup({python=' + json.dumps(sys.executable) + ', rex=' + json.dumps(REX)
                    + ', open_command={' + ','.join(map(json.dumps, opener))
                    + '}, copy_command={' + ','.join(map(json.dumps, copier)) + '}})\n')
                def launch(action, label, selected):
                    answer = ('nil, "cancelled"' if selected is None else
                              json.dumps(selected))
                    entry.write_text(setup + f'''
rex.ui.pick = function(prompt)
    assert(not prompt.multiple and prompt.confirm == {json.dumps(label)})
    assert(#prompt.items == 3)
    assert(prompt.items[1] == {json.dumps(first)})
    assert(prompt.items[2] == {json.dumps(second)})
    assert(prompt.items[3] == {json.dumps(long_url)})
    return {answer}
end
''')
                    self.call('do', str(entry), '--action', action, '-s', session, '-b', source)
                    self.assertEqual(window_state(), baseline)

                launch('open_url_copy', 'Copy', first)
                self.assertEqual(copied.read_text(), first)
                launch('open_url', 'Open', second)
                self.assertEqual(output.read_text().splitlines(), [second])
                launch('open_url', 'Open', None)
                self.assertEqual(output.read_text().splitlines(), [second])
                self.assertEqual(copied.read_text(), first)
            finally:
                self.call('kill', session)


if __name__ == '__main__':
    unittest.main()
