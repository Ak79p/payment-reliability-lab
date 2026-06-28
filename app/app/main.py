from fastapi import FastAPI

app = FastAPI(title = "Order Service")


@app.get("/")
async def root():
    return {"service": "order-service"}


@app.get("/health")
async def health():
    return {"status": "ok"}