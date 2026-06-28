from fastapi import FastAPI

app = FastAPI(title = "Fake Gateway")


@app.get("/")
async def root():
    return {"service": "fake-gateway"}


@app.get("/health")
async def health():
    return {"status": "ok"}