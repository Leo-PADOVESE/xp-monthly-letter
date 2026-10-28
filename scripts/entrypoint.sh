#!/bin/sh
# Container start. On Render, data/ lives on the persistent disk at /var/data. Usually only files
# missing on the disk are copied from the image, so the CRM and the letters generated on the
# platform are kept across deploys. When data/SEED_VERSION changes (new demo letters shipped),
# the demo files are overwritten and the CRM is rebuilt from them on boot.
set -e
if [ -n "$RENDER" ] && [ -d /var/data ]; then
  if cmp -s /app/data/SEED_VERSION /var/data/SEED_VERSION; then
    cp -rn /app/data/. /var/data/
  else
    rm -f /var/data/crm.db
    cp -r /app/data/. /var/data/
  fi
  rm -rf /app/data
  ln -s /var/data /app/data
fi
exec streamlit run app/streamlit_app.py --server.port "${PORT:-8501}" --server.address 0.0.0.0 --server.headless true
