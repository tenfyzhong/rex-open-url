#!/usr/bin/env python3
"""Collect URLs from Rex or send one URL to an opener or clipboard command."""
import argparse
import ipaddress
import json
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


def open_url(url, command):
    subprocess.run([*command, url], check=True, timeout=15,
                   capture_output=True, text=True)


def copy_url(url, command):
    subprocess.run(command, input=url, check=True, timeout=15,
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    operations = parser.add_subparsers(dest='operation', required=True)
    collect = operations.add_parser('collect')
    collect.add_argument('--rex', required=True)
    collect.add_argument('--session', required=True)
    collect.add_argument('--pane', required=True)
    collect.add_argument('--rows', required=True, type=int)
    collect.add_argument('--columns', required=True, type=int)
    for operation in (collect, operations.add_parser('open'), operations.add_parser('copy')):
        operation.add_argument('--options', default='{}')
    args = parser.parse_args()
    options = json.loads(args.options)

    if args.operation == 'open':
        open_url(sys.stdin.read(), options.get('open_command') or default_opener())
        return
    if args.operation == 'copy':
        copy_url(sys.stdin.read(), options.get('copy_command') or default_copier())
        return

    capture = subprocess.run(
        [args.rex, 'capture', '-s', args.session, '-b', args.pane, '--format=vt', '--unwrap'],
        check=True, capture_output=True, text=True, timeout=15)
    history_limit = options.get('history_limit')
    text = screen_text(capture.stdout, history_limit or args.rows,
                       None if history_limit else args.columns)
    print(json.dumps(extract(text, options.get('custom_pattern'), options.get('custom_sub'))))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print('rex-open-url: ' + str(error), file=sys.stderr)
        sys.exit(1)
