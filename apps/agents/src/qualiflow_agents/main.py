from fastapi import FastAPI

from .hello_graph import hello_graph

app = FastAPI(title="QualiFlow Agents")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/hello/{name}")
def hello(name: str) -> dict:
    result = hello_graph.invoke({"name": name})
    return {"greeting": result["greeting"]}
