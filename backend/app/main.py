from fastapi import FastAPI

app = FastAPI(title="Pangea 4.0 API")

@app.get("/health")
def health():
    return {"status": "ok"}