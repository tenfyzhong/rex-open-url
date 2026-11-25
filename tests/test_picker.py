import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('picker', ROOT / 'picker.py')
picker = importlib.util.module_from_spec(spec)
sys.modules['picker'] = picker
spec.loader.exec_module(picker)


class ExtractionTests(unittest.TestCase):
    def test_patterns_and_deduplication(self):
        self.assertEqual(picker.extract(
            'https://example.org/a https://example.org/a '
            'git@github.com:user/repo.git ssh://git@github.com/user/repo.git '
            'www.example.com 127.0.0.1:8080/a "other/project" ftp://ftp.test/x file:///tmp/a'
        ), ['https://example.org/a', 'https://github.com/user/repo',
            'http://www.example.com', 'http://127.0.0.1:8080/a',
            'https://github.com/other/project', 'ftp://ftp.test/x', 'file:///tmp/a'])

    def test_punctuation_balanced_parentheses_and_no_partial_paths(self):
        self.assertEqual(picker.extract(
            '(https://example.org/a_(b)). /usr/bin ./src/file user/repo/file '
            '999.1.1.1 javascript:alert(1)'
        ), ['https://example.org/a_(b)'])

    def test_custom_regex(self):
        self.assertEqual(picker.extract('BUG-123 BUG-123', r'BUG-\d+',
                                       r'https://tracker/\g<0>'), ['https://tracker/BUG-123'])

    def test_ansi_visible_rows_and_wrap(self):
        self.assertEqual(picker.screen_text(
            'old\r\n\x1b[31mhttps://example.org/\x1b[0mwrapped\r\n\n', 2),
            'https://example.org/wrapped\n')

    def test_unwrapped_lines_count_physical_rows(self):
        self.assertEqual(picker.screen_text('hidden\nabcdefghij\n\n', 3, 5),
                         'abcdefghij\n')
        self.assertEqual(picker.screen_text('hidden\nabcdefghij\n\n', 2, 5),
                         'fghij\n')


class ProcessTests(unittest.TestCase):
    @patch('picker.subprocess.run')
    def test_collect_outputs_links_as_json(self, run):
        run.return_value.stdout = 'https://example.org/a BUG-23\n\n'
        with patch.object(sys, 'argv', [
            'picker.py', 'collect', '--rex', '/rex', '--session', 's', '--pane', 'p',
            '--rows', '2', '--columns', '80',
            '--options', json.dumps({'custom_pattern': r'BUG-\d+'}),
        ]), patch('sys.stdout', new_callable=io.StringIO) as output:
            picker.main()
        self.assertEqual(json.loads(output.getvalue()), ['https://example.org/a', 'BUG-23'])
        run.assert_called_once_with(
            ['/rex', 'capture', '-s', 's', '-b', 'p', '--format=vt', '--unwrap'],
            check=True, capture_output=True, text=True, timeout=15)

    @patch('picker.subprocess.run')
    def test_open_argv_never_shell(self, run):
        url = 'https://example.org/$(touch%20oops);x'
        with patch.object(sys, 'argv', [
            'picker.py', 'open', '--options', '{"open_command":["browser","--new-window"]}',
        ]), patch('sys.stdin', io.StringIO(url)):
            picker.main()
        run.assert_called_once_with(['browser', '--new-window', url], check=True,
                                    timeout=15, capture_output=True, text=True)

    @patch('picker.subprocess.run')
    def test_copy_stdin(self, run):
        url = 'https://example.org/路径'
        with patch.object(sys, 'argv', [
            'picker.py', 'copy', '--options', '{"copy_command":["clipboard"]}',
        ]), patch('sys.stdin', io.StringIO(url)):
            picker.main()
        run.assert_called_once_with(['clipboard'], input=url,
                                    check=True, timeout=15, capture_output=True, text=True)

    @patch('picker.subprocess.run', side_effect=subprocess.CalledProcessError(1, 'open'))
    def test_opener_failure_propagates(self, run):
        with self.assertRaises(subprocess.CalledProcessError):
            picker.open_url('https://a', ['open'])


class LuaTests(unittest.TestCase):
    def test_native_selection_and_dispatch(self):
        subprocess.run(['lua', 'tests/plugin.lua'], cwd=ROOT, check=True)


if __name__ == '__main__':
    unittest.main()
