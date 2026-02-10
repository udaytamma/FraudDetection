api: uvicorn src.api.main:app --host 0.0.0.0 --port $PORT --workers 2
web: sh -c 'streamlit run dashboard.py --server.port "$PORT" --server.address 0.0.0.0 --server.headless true'
