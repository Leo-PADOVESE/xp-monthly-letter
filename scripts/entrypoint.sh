#!/bin/sh
# Container start. On Render, data/ lives on the persistent disk at /var/data: the first deploy
# seeds it with the data shipped in the image, and later deploys only add files that are
# missing, so the CRM and the letters already generated are never overwritten.
set -e
if [ -n "$RENDER" ] && [ -d /var/data ]; then
  cp -rn /app/data/. /var/data/
  rm -rf /app/data
  ln -s /var/data /app/data
fi
exec streamlit run app/streamlit_app.py --server.port "${PORT:-8501}" --server.address 0.0.0.0 --server.headless true
