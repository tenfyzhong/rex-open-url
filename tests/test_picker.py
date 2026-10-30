import importlib.util
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


class SelectionTests(unittest.TestCase):
    def test_fuzzy_filter_and_selection_survive_query(self):
        model = picker.Selection(['https://a.test', 'https://b.test'])
        model.toggle()
        model.query = 'BT'
        self.assertEqual(model.visible(), ['https://b.test'])
        self.assertEqual(model.chosen(), ['https://a.test'])
        model.toggle()
        self.assertEqual(model.chosen(), model.urls)

    def test_empty_and_current(self):
        model = picker.Selection(['https://a.test'])
        self.assertEqual(model.chosen(), model.urls)
        model.query = 'absent'
        self.assertEqual(model.chosen(), [])


class ProcessTests(unittest.TestCase):
    @patch('picker.subprocess.run')
    def test_open_argv_never_shell(self, run):
        url = 'https://example.org/$(touch%20oops);x'
        picker.open_urls([url], ['browser', '--new-window'])
        run.assert_called_once_with(['browser', '--new-window', url], check=True,
                                    timeout=15, capture_output=True, text=True)

    @patch('picker.subprocess.run')
    def test_copy_stdin(self, run):
        picker.copy_urls(['https://a', 'https://b'], ['pbcopy'])
        run.assert_called_once_with(['pbcopy'], input='https://a\nhttps://b',
                                    check=True, timeout=15, capture_output=True, text=True)

    @patch('picker.subprocess.run', side_effect=subprocess.CalledProcessError(1, 'open'))
    def test_opener_failure_propagates(self, run):
        with self.assertRaises(subprocess.CalledProcessError):
            picker.open_urls(['https://a'], ['open'])


class LuaTests(unittest.TestCase):
    def test_registration_and_layer_target(self):
        subprocess.run(['lua', 'tests/plugin.lua'], cwd=ROOT, check=True)


if __name__ == '__main__':
    unittest.main()
