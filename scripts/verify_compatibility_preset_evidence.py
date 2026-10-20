#!/usr/bin/env python3
"""Check collected preset obligations against executed JUnit and loopback facts.

Offline only: never invokes Codex, subprocesses, a provider, or a database.
"""

import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--loopback', type=Path, required=True)
    parser.add_argument('--junit', type=Path, action='append', required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    required = manifest['required_nodes']
    if not required or len(required) != len(set(required)):
        raise ValueError('Expected nonempty unique collected obligations')
    passed = set()
    for path in args.junit:
        for case in ET.parse(path).iter('testcase'):
            if any(case.find(kind) is not None for kind in ('failure', 'error', 'skipped')):
                continue
            filename = case.attrib.get('classname', '').replace('.', '/') + '.py'
            passed.add(filename + '::' + case.attrib['name'])
    loopback = json.loads(args.loopback.read_text())
    stages = [r for r in loopback['requests'] if r.get('main_passed')]
    expected = manifest['required_interactive_stages']
    missing = sorted(set(required) - passed)
    if any(loopback.get(key) != value
           for key, value in manifest['required_loopback_facts'].items()):
        missing.append('interactive-client-and-preset-identity')
    if [r['stage'] for r in stages] != expected:
        missing.append('interactive-stage-sequence')
    elif not (stages[1]['completed_assistant_messages'] >= 1
              and stages[1]['tool_outputs'] >= 1
              and stages[2]['completed_assistant_messages'] >= 2
              and stages[2]['empty_annotations_parts'] >= 2):
        missing.append('natural-history-replay')
    if any(not r.get('main_passed') and not (
        r.get('expected_auxiliary_rejection')
        and r.get('error_code') == 'responses_structured_streaming_not_supported'
    ) for r in loopback['requests']):
        missing.append('unexpected-interactive-rejection')
    print(json.dumps({'required':len(required), 'executed_passed':len(set(required) & passed),
                      'interactive_stages':len(stages), 'missing':missing}, indent=2))
    return int(bool(missing))


if __name__ == '__main__':
    raise SystemExit(main())
