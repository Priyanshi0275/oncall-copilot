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
bug_on = False


@app.get("/health")
def health():
    return {"status": "ok", "version": VERSION}


@app.get("/checkout")
def checkout():
    if bug_on:
        log.error("checkout failed: database connection pool exhausted (version=%s)", VERSION)
        raise HTTPException(status_code=500, detail="Internal error")
    log.info("checkout ok (version=%s)", VERSION)
    return {"status": "paid"}


@app.post("/break")
def break_it():
    """Simulate a bad deploy: switch version and turn the bug on."""
    global bug_on, VERSION
    bug_on, VERSION = True, "v1.1"
    log.warning("deployed new version v1.1")
    return {"bug": "on", "version": VERSION}


@app.post("/fix")
def fix_it():
    """Roll back to the previous version."""
    global bug_on, VERSION
    bug_on, VERSION = False, "v1.0"
    log.warning("rolled back to v1.0")
    return {"bug": "off", "version": VERSION}