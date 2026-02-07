# Agent Runtime Dashboard (local)

## Install deps (inside your venv)
source /home/hackerman/agent-runtime/.venv/bin/activate
python -m pip install streamlit requests

## Run
cd /home/hackerman/agent-runtime/workspace/projects/agent-dashboard
streamlit run app.py --server.port 8787

Open: http://localhost:8787
