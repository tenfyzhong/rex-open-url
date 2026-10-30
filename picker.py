#!/usr/bin/env python3
"""Rex URL picker. Runtime dependencies: Python standard library and Rex."""
import argparse
import curses
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata

URL = re.compile(r"""(?:https?|ftp|file)://[^\s<>"'`]+|ssh://git@[^\s<>"'`]+|git@[\w.-]+:[^\s<>"'`]+|\bwww\.[^\s<>"'`]+|\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?(?:/[^\s<>"'`]*)?""")
SHORTHAND = re.compile(r"""(?<!\S)["']?([\w.-]+/[\w.-]+)["']?(?!\S)""")


def clean(value):
    value = value.rstrip('.,;:!?')
    for left, right in [('(', ')'), ('[', ']'), ('{', '}')]:
        while value.endswith(right) and value.count(right) > value.count(left):
            value = value[:-1]
    return value


def extract(text, custom_pattern=None, custom_sub=None):
    matches = []
    for match in URL.finditer(text):
        value = clean(match.group())
        if value.startswith('git@'):
            value = 'https://' + value[4:].replace(':', '/', 1)
            value = re.sub(r'\.git$', '', value)
        elif value.startswith('ssh://git@'):
            value = re.sub(r'\.git$', '', 'https://' + value[10:])
        elif value.startswith('www.'):
            value = 'http://' + value
        elif re.match(r'^\d', value):
            try:
                ipaddress.IPv4Address(re.split('[:/]', value)[0])
            except ValueError:
                continue
            value = 'http://' + value
        matches.append((match.start(), value))
    for match in SHORTHAND.finditer(text):
        value = match.group(1)
        owner, repo = value.split('/')
        if owner not in ('.', '..') and repo not in ('.', '..'):
            matches.append((match.start(), 'https://github.com/' + value))
    if custom_pattern:
        for match in re.finditer(custom_pattern, text):
            value = match.expand(custom_sub) if custom_sub is not None else match.group()
            if value and not any(ord(c) < 32 for c in value):
                matches.append((match.start(), value))
    return list(dict.fromkeys(value for _, value in sorted(matches)))


def screen_text(text, rows, columns=None):
    # VT preserves blank bottom rows and joins soft wraps without a newline.
    text = re.sub(r'\x1b\].*?(?:\x07|\x1b\\)', '', text, flags=re.S)
    text = re.sub(r'\x1b\[[0-9;:]*m', '', text)
    text = re.sub(r'\x1b\[\d*X', '', text)
    text = re.sub(r'\x1b\[(\d*)C',
                  lambda m: ' ' * min(int(m[1] or 1), 4096), text)
    if '\x1b' in text:
        raise ValueError('Unsupported terminal snapshot sequence')
    # rex capture always adds one newline after the exported content.
    text = text.removesuffix('\n').replace('\r\n', '\n')
    lines = text.split('\n')
    if not columns:
        return '\n'.join(lines[-rows:])
    kept = []
    for line in reversed(lines):
        # Model terminal wrapping without a third-party wcwidth dependency.
        chunks, chunk, width = [], '', 0
        for char in line:
            size = 0 if unicodedata.combining(char) else (
                2 if unicodedata.east_asian_width(char) in ('W', 'F') else 1)
            if width + size > columns:
                chunks.append(chunk)
                chunk, width = '', 0
            chunk += char
            width += size
        chunks.append(chunk)
        kept.append(''.join(chunks[-rows:]))
        rows -= len(chunks)
        if rows <= 0:
            break
    return '\n'.join(reversed(kept))


class Selection:
    def __init__(self, urls):
        self.urls = urls
        self.query = ''
        self.index = 0
        self.selected = set()

    def visible(self):
        def matches(url):
            chars = iter(url.casefold())
            return all(any(c == q for c in chars) for q in self.query.casefold())
        return [url for url in self.urls if matches(url)]

    def current(self):
        visible = self.visible()
        self.index = min(max(self.index, 0), max(0, len(visible) - 1))
        return visible[self.index] if visible else None

    def toggle(self):
        current = self.current()
        if current in self.selected:
            self.selected.remove(current)
        elif current:
            self.selected.add(current)

    def chosen(self):
        if self.selected:
            return [url for url in self.urls if url in self.selected]
        current = self.current()
        return [current] if current else []


def open_urls(urls, command):
    for url in urls:
        subprocess.run([*command, url], check=True, timeout=15,
                       capture_output=True, text=True)


def copy_urls(urls, command):
    subprocess.run(command, input='\n'.join(urls), check=True, timeout=15,
                   capture_output=True, text=True)


def default_opener():
    if sys.platform == 'darwin':
        return ['open']
    for command in ('wslview', 'xdg-open'):
        if shutil.which(command):
            return [command]
    raise ValueError('No URL opener found; configure open_command')


def default_copier():
    for command in (['pbcopy'], ['wl-copy'], ['xclip', '-selection', 'clipboard'],
                    ['xsel', '--clipboard', '--input']):
        if shutil.which(command[0]):
            return command
    raise ValueError('No clipboard command found; configure copy_command')


def picker_ui(screen, urls, options):
    model = Selection(urls)
    message = ''
    curses.curs_set(0)
    curses.raw()
    curses.nonl()
    screen.keypad(True)
    while True:
        screen.erase()
        height, width = screen.getmaxyx()

        def line(row, text, style=0):
            if row < height:
                try:
                    screen.addnstr(row, 0, text, max(0, width - 1), style)
                except curses.error:
                    pass

        visible = model.visible()
        model.current()
        line(0, 'Open URL > ' + model.query, curses.A_BOLD)
        line(1, 'Enter open | Tab select | Ctrl-y copy | Esc cancel')
        count = max(1, height - 4)
        start = max(0, model.index - count + 1)
        for row, url in enumerate(visible[start:start + count], 2):
            marker = '[x] ' if url in model.selected else '[ ] '
            line(row, marker + url, curses.A_REVERSE if row - 2 + start == model.index else 0)
        line(height - 1, message or '{} URLs / {} selected'.format(len(visible), len(model.selected)))
        screen.refresh()
        key = screen.get_wch()
        if key in ('\x1b', '\x03'):
            return
        if key in (curses.KEY_DOWN, '\x0e', '\x0a'):
            # Ctrl-j is newline, same as Enter on some terminals: Enter uses CR.
            model.index = min(model.index + 1, max(0, len(visible) - 1))
        elif key in (curses.KEY_UP, '\x10', '\x0b'):
            model.index = max(0, model.index - 1)
        elif key == '\x01':
            model.index = 0
        elif key == '\x05':
            model.index = max(0, len(visible) - 1)
        elif key == '\t':
            model.toggle()
        elif key in ('\r', curses.KEY_ENTER, '\x19'):
            chosen = model.chosen()
            if not chosen:
                message = 'No URLs selected'
                continue
            try:
                if key == '\x19':
                    copy_urls(chosen, options.copy_command or default_copier())
                    message = 'Copied {} URL(s)'.format(len(chosen))
                else:
                    open_urls(chosen, options.open_command or default_opener())
                    return
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                message = 'Failed: ' + str(error)
        elif key == '\x15':
            model.query, model.index = '', 0
        elif key in (curses.KEY_BACKSPACE, '\x7f', '\b'):
            model.query, model.index = model.query[:-1], 0
        elif isinstance(key, str) and key.isprintable():
            model.query += key
            model.index = 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rex', required=True)
    parser.add_argument('--session', required=True)
    parser.add_argument('--pane', required=True)
    parser.add_argument('--rows', required=True, type=int)
    parser.add_argument('--columns', required=True, type=int)
    parser.add_argument('--options', default='{}')
    args = parser.parse_args()
    options = json.loads(args.options)
    args.open_command = options.get('open_command')
    args.copy_command = options.get('copy_command')
    capture = subprocess.run(
        [args.rex, 'capture', '-s', args.session, '-b', args.pane, '--format=vt', '--unwrap'],
        check=True, capture_output=True, text=True, timeout=15)
    text = screen_text(capture.stdout, options.get('history_limit') or args.rows,
                       None if options.get('history_limit') else args.columns)
    urls = extract(text, options.get('custom_pattern'), options.get('custom_sub'))
    os.environ.setdefault('ESCDELAY', '25')
    curses.wrapper(picker_ui, urls, args)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print('rex-open-url: ' + str(error), file=sys.stderr)
        sys.exit(1)
