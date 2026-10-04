"""Vérifie que l'application utilise la SHA du commit CI comme identité de release."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

expected = os.environ.get('GIT_COMMIT', '').strip()
if not expected:
    raise SystemExit('GIT_COMMIT absent dans le CI')

env = os.environ.copy()
env['ENVIRONNEMENT'] = 'developpement'
env['SESSION_SECRET_KEY'] = 'ci-release-identity'
env['DATABASE_URL'] = 'sqlite:///./release-identity-ci.db'
code = 'from app.config import parametres; print(parametres.release_commit)'
result = subprocess.run(
    [sys.executable, '-c', code],
    cwd=ROOT, env=env, text=True, capture_output=True, check=True
)
actual = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ''
if actual != expected:
    raise SystemExit(f'Release identity mismatch: expected {expected}, got {actual}')
print(f'RELEASE_IDENTITY_OK {expected}')