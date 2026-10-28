# Platform image: Python (pipeline + Streamlit) and Node (Rivet runner) in one container.
FROM node:20-slim AS rivet
WORKDIR /rivet
COPY rivet/package.json ./
RUN npm install --omit=dev

FROM python:3.12-slim
COPY --from=rivet /usr/local/bin/node /usr/local/bin/node
RUN node --version
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=rivet /rivet/node_modules rivet/node_modules
ENV PORT=8501 PYTHONUNBUFFERED=1
EXPOSE 8501
CMD streamlit run app/streamlit_app.py --server.port $PORT --server.address 0.0.0.0 --server.headless true
