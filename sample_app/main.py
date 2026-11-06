import logging

from fastapi import FastAPI, HTTPException

logging.basicConfig(
    filename="app.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("shop")

app = FastAPI()
VERSION = "v1.0"
MODE = "healthy"  # healthy, bad_deploy, memory_leak or high_latency


@app.get("/health")
def health():
    return {"status": "ok", "version": VERSION, "mode": MODE}


@app.get("/checkout")
def checkout():
    if MODE == "bad_deploy":
        log.error("checkout failed: database connection pool exhausted (version=%s)", VERSION)
        raise HTTPException(status_code=500, detail="Internal error")
    if MODE == "memory_leak":
        log.warning("memory usage at 94 percent and still climbing (version=%s)", VERSION)
        log.error("container OOMKilled: out of memory, restarting (version=%s)", VERSION)
        raise HTTPException(status_code=500, detail="Internal error")
    if MODE == "high_latency":
        log.warning("slow response: /checkout took 4800 ms, normal is 120 ms (version=%s)", VERSION)
        return {"status": "paid"}
    log.info("checkout ok (version=%s)", VERSION)
    return {"status": "paid"}


@app.post("/break")
def break_it():
    """Simulate a bad deploy: switch version and start failing."""
    global MODE, VERSION
    MODE, VERSION = "bad_deploy", "v1.1"
    log.warning("deployed new version v1.1")
    return {"mode": MODE, "version": VERSION}


@app.post("/break/memory")
def break_memory():
    """Simulate a memory leak that is not related to any deploy."""
    global MODE
    MODE = "memory_leak"
    return {"mode": MODE, "version": VERSION}


@app.post("/break/latency")
def break_latency():
    """Simulate a slow dependency: no errors, only slow responses."""
    global MODE
    MODE = "high_latency"
    return {"mode": MODE, "version": VERSION}


@app.post("/fix")
def fix_it():
    """Restore the service. Only a bad deploy is a real rollback."""
    global MODE, VERSION
    if MODE == "bad_deploy":
        log.warning("rolled back to v1.0")
    else:
        log.info("service restored to normal")
    MODE, VERSION = "healthy", "v1.0"
    return {"mode": MODE, "version": VERSION}