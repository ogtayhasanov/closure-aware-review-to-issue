"""Run resumable registered generators, then masked judges. No credentials saved."""
from concurrent.futures import ThreadPoolExecutor
import subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def run(*args):
    r=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'run_combined.py'),*args])
    if r.returncode:raise RuntimeError('Stage failed: '+str(args))
with ThreadPoolExecutor(max_workers=2) as pool:
    futures=[pool.submit(run,stage) for stage in ['A','B']]
    for f in futures:f.result()
subprocess.run([sys.executable,'-X','utf8',str(ROOT/'prepare_audit_inputs.py')],check=True)
for stage in ['core','routing','audit']:run(stage)
print('All generation and scoring stages complete.',flush=True)
