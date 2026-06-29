"""Intentionally vulnerable sample handler — test fixture for source_audit.

NOT a real application: a minimal but genuine set of insecure sinks so the
white-box ``code_audit`` profile has a真实漏洞源码样例 to scan end-to-end. Uses
Python sinks (pickle / subprocess / yaml / SQL string concat) rather than PHP
webshell signatures, which on-host AntiVirus tends to quarantine (see the
P10/P11 blood lesson in test_source_audit_wiring.py).
"""

import pickle
import subprocess

import yaml

from config import DB_DSN  # noqa: F401


def load_session(blob):
    # CWE-502: untrusted deserialization of a request-supplied blob.
    return pickle.loads(blob)


def run_report(report_name):
    # CWE-78: shell execution with a tainted argument.
    return subprocess.run("generate_report " + report_name, shell=True)


def load_settings(raw):
    # CWE-502: yaml.load without SafeLoader can instantiate arbitrary objects.
    return yaml.load(raw)


def find_user(conn, user_id):
    # CWE-89: SQL assembled by string concatenation instead of parameters.
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = " + str(user_id))
    return cur.fetchone()
