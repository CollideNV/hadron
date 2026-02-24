"""Minimal FastAPI app for testing the Hadron pipeline."""

from fastapi import FastAPI

app = FastAPI(title="Test App")


@app.get("/")
async def root():
    return {"message": "Hello, World!"}


@app.get("/items")
async def list_items():
    return {"items": [{"id": 1, "name": "Widget"}, {"id": 2, "name": "Gadget"}]}
