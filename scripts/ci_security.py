"""Fail closed on scanner errors and unapproved or expired advisory exceptions."""
import argparse
from datetime import date
import json
from pathlib import Path
import subprocess


def normalize(name):
    return name.lower().replace('_', '-')


def findings(scanner, report):
    if scanner == 'trivy':
        if not isinstance(report.get('Results'), list):
            raise ValueError('Trivy report has no Results array')
        return [dict(package=normalize(v['PkgName']), version=v['InstalledVersion'], ids=[v['VulnerabilityID']],
                     severity=v['Severity'], title=v['Title'])
                for result in report['Results'] for v in result.get('Vulnerabilities', [])]
    if scanner == 'pip':
        if not isinstance(report.get('dependencies'), list):
            raise ValueError('pip-audit report has no dependencies array')
        return [dict(package=normalize(d['name']), version=d['version'], ids=[v['id'], *v.get('aliases', [])],
                     severity='UNKNOWN', title=v.get('description', '').split('\n')[0])
                for d in report['dependencies'] for v in d.get('vulns', [])]
    raise ValueError('Unsupported scanner')


def evaluate(scanner, report, exceptions, today=None):
    today = today or date.today()
    for entry in exceptions:
        if date.fromisoformat(entry['review_date']) <= today:
            raise ValueError('Expired security exception: ' + entry['advisory'])
        if not all(entry.get(field) for field in ('package', 'version', 'advisory', 'reason', 'severity', 'reachability')):
            raise ValueError('Incomplete security exception')
    blocked, accepted = [], []
    for item in findings(scanner, report):
        if scanner == 'trivy' and item['severity'] not in {'HIGH', 'CRITICAL'}:
            continue
        matched = any(normalize(e['package']) == item['package'] and e['version'] == item['version']
                      and e['advisory'] in item['ids'] and scanner in e['scanners'] for e in exceptions)
        (accepted if matched else blocked).append(item)
    return blocked, accepted


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scanner', choices=['pip', 'trivy'], required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--exceptions', type=Path, default=Path('config/security-exceptions.json'))
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command:
        command = args.command[1:] if args.command[0] == '--' else args.command
        args.report.unlink(missing_ok=True)
        completed = subprocess.run(command, check=False)
        if completed.returncode not in (0, 1):
            raise SystemExit(completed.returncode)
    try:
        report = json.loads(args.report.read_text())
        if report.get('error'):
            raise ValueError('Scanner reported an error')
        if args.command and completed.returncode == 1 and not findings(args.scanner, report):
            raise ValueError('Scanner failed without advisory findings')
        exceptions = json.loads(args.exceptions.read_text())['exceptions']
        blocked, accepted = evaluate(args.scanner, report, exceptions)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise SystemExit('Security gate could not validate report: ' + str(exc)) from exc
    print(f'{args.scanner}: {len(blocked)} blocking findings; {len(accepted)} explicitly excepted findings (not fixed).')
    for item in blocked:
        print(f"BLOCK {item['package']} {item['version']} {','.join(item['ids'])} {item['severity']}")
    raise SystemExit(1 if blocked else 0)


if __name__ == '__main__':
    main()
