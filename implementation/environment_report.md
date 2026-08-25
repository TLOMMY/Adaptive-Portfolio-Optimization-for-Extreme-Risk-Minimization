# Environment and Reproducibility

- Workspace: `C:\Users\LiuBW\Documents\Amazon`
- Execution is sandboxed to the workspace; remote Git metadata updates require
  explicit escalation and were completed for the read-only fetch.
- Python runtime: `C:\Users\LiuBW\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`
- Installed and verified: NumPy, pandas, SciPy 1.18.1, CVXPY 1.9.2.
- Available CVXPY solvers: CLARABEL, SCS, SCIPY, HiGHS, and OSQP.
- Reinstall for another machine with:

```text
python -m pip install -r implementation/requirements.txt
```

The current model tests and synthetic integration benchmark run without
network data. Yahoo/yfinance and Parquet support are not assumed by the local
adapter; Yesh's branch retains those as separate presentation-backend
dependencies.
