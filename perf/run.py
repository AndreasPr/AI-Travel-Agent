"""Run k6 locally only against the isolated synthetic Compose project."""
import json
import os
from pathlib import Path
import platform
import secrets
import subprocess
from datetime import datetime, timezone


def finalize_report(output, returncode):
    """A zero-sample or aborted run is never successful performance evidence."""
    if not output.exists():
        return returncode or 1
    report = json.loads(output.read_text())
    metrics = report.get('metrics', {})
    completed = metrics.get('sse_completed_sessions', {}).get('values', {}).get('count', 0)
    errors = metrics.get('sse_error_rate', {}).get('values', {})
    valid = completed > 0 and errors.get('passes', 0) + errors.get('fails', 0) > 0
    passed = returncode == 0 and valid and errors.get('rate') == 0
    report['status'] = 'passed' if passed else 'failed'
    report['k6_exit_code'] = returncode
    report['completed_sessions'] = completed
    output.write_text(json.dumps(report, indent=2) + '\n')
    return 0 if passed else (returncode or 1)


def main():
    environment = dict(os.environ)
    # Verify the configured stack before traffic; never accept a generic live target.
    inspected = subprocess.check_output(['docker', 'compose', '-f', 'compose.test.yaml', 'config', '--format', 'json'], env=environment)
    config = json.loads(inspected)
    if config['services']['api']['environment'].get('LLM_STUB') != '1':
        raise SystemExit('Refusing performance run without the synthetic stub')
    api_port = environment.get('TEST_API_PORT', '18100')
    web_port = environment.get('TEST_WEB_PORT', '13100')
    environment['TEST_API_URL'] = 'http://localhost:' + api_port
    environment['TEST_WEB_URL'] = 'http://localhost:' + web_port
    ids = subprocess.check_output(['docker', 'compose', '-f', 'compose.test.yaml', 'ps', '-q', 'api'], env=environment).decode().strip()
    if not ids:
        raise SystemExit('Start compose.test.yaml first')
    container = json.loads(subprocess.check_output(['docker', 'inspect', ids]))[0]
    if not {'LLM_STUB=1', 'TEST_SUITE_MODE=1'} <= set(container['Config']['Env']):
        raise SystemExit('Running API is not the isolated synthetic provider')
    bindings = container['NetworkSettings']['Ports'].get('8080/tcp') or []
    if not any(row['HostPort'] == api_port and row['HostIp'] == '127.0.0.1' for row in bindings):
        raise SystemExit('Requested port does not belong to the verified synthetic API')
    hardware = {'os': platform.system(), 'release': platform.release(), 'architecture': platform.machine(), 'logical_cpus': os.cpu_count(),
                'description': environment.get('PERF_HARDWARE_DESCRIPTION', 'local load generator; Docker resources depend on Docker settings')}
    environment['PERF_HARDWARE'] = json.dumps(hardware)
    environment['PERF_RUN_ID'] = secrets.token_hex(6)
    output = Path('perf/results') / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-synthetic.json')
    output.parent.mkdir(exist_ok=True)
    environment['PERF_OUTPUT'] = str(output)
    if not environment.get('K6_BROWSER_EXECUTABLE_PATH'):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            environment['K6_BROWSER_EXECUTABLE_PATH'] = playwright.chromium.executable_path
    result = subprocess.run(['k6', 'run', 'perf/synthetic_sse.js'], env=environment)
    exit_code = finalize_report(output, result.returncode)
    print(f'Synthetic performance run {"FAILED" if exit_code else "PASSED"}; report: {output}')
    raise SystemExit(exit_code)


if __name__ == '__main__':
    main()
