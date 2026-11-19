#!/usr/bin/env python3
"""Read-only, preliminary source audit. Not an automated kernel porter or builder."""
from __future__ import annotations
import argparse
import csv
import json
import re
from pathlib import Path

KEYWORDS = [
    'a21s', 'a217', 'boe_8a6220', '8a6220',
    'synaptics_tcm_spi', 'syna_tcm', 'td4150', 'hx83104',
    'nt36575', 'exynos850', 'exynos3830'
]
SCAN_ROOTS = [
    'arch/arm64/boot/dts', 'arch/arm64/configs',
    'drivers/video/fbdev/exynos', 'drivers/input/touchscreen',
    'drivers/sensors', 'firmware'
]
TEXT_EXT = {'.c','.h','.dts','.dtsi','.defconfig','.mk','.txt','.cfg','.config','.sh','.inc','.its','.yaml','.yml'}
MAX_BYTES = 1_500_000
MAX_ROWS_PER_KEY = 500
KCONFIG_RE = re.compile(r'^\s*(?:menu)?config\s+([A-Za-z0-9_]+)\s*$', re.M)


def eligible(path: Path) -> bool:
    return path.name in ('Kconfig','Makefile','Kbuild') or path.suffix.lower() in TEXT_EXT or path.name.endswith('_defconfig')


def scan(repo: Path):
    found = {k: [] for k in KEYWORDS}
    syms = set()
    files_scanned = 0
    for root in SCAN_ROOTS:
        folder = repo/root
        if not folder.is_dir():
            continue
        for path in folder.rglob('*'):
            if not path.is_file() or path.is_symlink() or not eligible(path):
                continue
            if path.stat().st_size > MAX_BYTES:
                continue
            files_scanned += 1
            relative = path.relative_to(repo).as_posix()
            try:
                source = path.read_text(encoding='utf-8', errors='replace')
            except OSError:
                continue
            if path.name == 'Kconfig':
                syms.update(KCONFIG_RE.findall(source))
            if not any(term in (relative + source).lower() for term in KEYWORDS):
                continue
            for n, line in enumerate(source.splitlines(), start=1):
                hay = f'{relative} {line}'.lower()
                for term in KEYWORDS:
                    if term in hay and len(found[term]) < MAX_ROWS_PER_KEY:
                        found[term].append([term, relative, n, line.strip()[:220]])
    return found, syms, files_scanned


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--a12s', type=Path, required=True)
    parser.add_argument('--a21s', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    for repo in (args.a12s,args.a21s):
        if not repo.is_dir() or not (repo/'drivers').is_dir():
            parser.error(f'Invalid or missing checked-out source: {repo}')
    args.output.mkdir(parents=True, exist_ok=True)
    a12s, sym_a12s, count_a12s = scan(args.a12s)
    a21s, sym_a21s, count_a21s = scan(args.a21s)
    with (args.output/'source_matches.csv').open('w',newline='',encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['tree','term','file','line','excerpt'])
        for tree,matches in (('A12s-5.10',a12s),('A21s-4.19',a21s)):
            for term in KEYWORDS:
                for row in matches[term]:
                    writer.writerow([tree]+row)
    with (args.output/'kconfig_symbols_a21s_only.txt').open('w') as f:
        f.write('\n'.join(sorted(sym_a21s - sym_a12s))+'\n')
    report = [
        '# A21s Linux 5.10 — source comparison (NOT flash-ready)',
        '',
        'Source A12s: rsuntk/android_kernel_samsung_a12s-5.10 @ 8e38b803532cf77a80e4a6b2f5e92be7612edb0f',
        'Source A21s: samsungexynos850/atlas @ master (4.19 tree; commit varies with run)',
        '',
        '## Important',
        'This checks references in **sparse source trees**. Missing matches do not prove a missing driver;',
        'matching strings do not prove hardware compatibility. No compiling, porting, booting or flashing occurs.',
        '',
        f'Files scanned: A12s={count_a12s}; A21s={count_a21s}.',
        '',
        '| Token | A12s lines | A21s lines |', '|---|---:|---:|'
    ]
    for key in KEYWORDS:
        report.append(f'| `{key}` | {len(a12s[key])} | {len(a21s[key])} |')
    report += [
        '',
        f'Kconfig symbols: A12s={len(sym_a12s)}, A21s={len(sym_a21s)}, A21s-only={len(sym_a21s - sym_a12s)}.',
        '',
        '## Required manual work before any flashable image',
        '1. Identify precise BOE panel *driver filename* and its DTS/DSI sequence from running device and A21s 4.19 tree.',
        '2. Port needed A21s DTB, DECON/DSIM/panel and Synaptics TCM SPI support to 5.10 with dependencies.',
        '3. Port remaining board peripherals and verify vendor-module ABI, drivers, regulators, clocks and modem.',
        '4. Build uncompressed ARM64 kernel + correct board DTB and confirm boot image <= 37,748,736 bytes.',
        '5. Obtain a recoverable hardware-test setup; boot has NOT been tested.',
        '',
        'Always keep the working A21s boot/DTBO backups. **DO NOT FLASH** hybrid or audit outputs.'
    ]
    (args.output/'A21s-5.10-source-audit.md').write_text('\n'.join(report)+'\n', encoding='utf-8')
    (args.output/'summary.json').write_text(json.dumps({
        'status':'NOT_PORTED_NOT_FLASHABLE',
        'source_sha':'8e38b803532cf77a80e4a6b2f5e92be7612edb0f',
        'matches': {'a12s':{k:len(v) for k,v in a12s.items()},'a21s':{k:len(v) for k,v in a21s.items()}},
        'files_scanned':{'a12s':count_a12s,'a21s':count_a21s},
        'kconfig_a21s_only':len(sym_a21s-sym_a12s)
    },indent=2)+'\n',encoding='utf-8')
    print('Created report in',args.output)

if __name__ == '__main__':
    main()
  
