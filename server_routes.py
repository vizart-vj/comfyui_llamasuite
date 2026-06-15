import requests
import threading
from server import PromptServer
from aiohttp import web
from .nodes import LlamaProcessManager

def setup_routes():
    @PromptServer.instance.routes.get("/llama_suite/models")
    async def get_models(request):
        url = request.query.get("url", "http://localhost:8080").rstrip("/")
        try:
            r = requests.get(f"{url}/v1/models", timeout=5)
            r.raise_for_status()
            models = [m["id"] for m in r.json().get("data", [])]
            return web.json_response({"models": models, "status": "ok"})
        except Exception as e:
            return web.json_response({"models": [], "status": "error", "error": str(e)})

    @PromptServer.instance.routes.get("/llama_suite/running")
    async def get_running(request):
        url = request.query.get("url", "http://localhost:8080").rstrip("/")
        try:
            r = requests.get(f"{url}/running", timeout=5)
            r.raise_for_status()
            return web.json_response(r.json())
        except Exception as e:
            return web.json_response({"running": [], "error": str(e)})

    @PromptServer.instance.routes.post("/llama_suite/unload")
    async def do_unload(request):
        url = request.query.get("url", "http://localhost:8080").rstrip("/")
        model = request.query.get("model", "")
        
        try:
            r = requests.post(
                f"{url}/models/unload", 
                json={"model": model}, 
                timeout=10
            )
            r.raise_for_status()
            return web.json_response({"status": "ok", "message": r.text.strip()})
        except Exception as e:
            return web.json_response({"status": "error", "error": str(e)})

    @PromptServer.instance.routes.post("/llama_suite/start")
    async def start_llama_server(request):
        try:
            body = await request.json()
        except:
            body = {}

        args = {
            "llama_path": body.get("llama_path", "llama-server"),
            "models_dir": body.get("models_dir", ""),
            "host": body.get("host", "0.0.0.0"),
            "port": body.get("port", 8080),
            "context_length": body.get("context_length", 120000),
            "flash_attention": body.get("flash_attention", True),
            "extra_args": body.get("extra_args", ""),
        }
        
        def run_start():
            try:
                LlamaProcessManager.start_server(args)
            except Exception as e:
                pass

        threading.Thread(target=run_start, daemon=True).start()
        return web.json_response({"status": "ok", "message": "Starting process... check console."})

    @PromptServer.instance.routes.post("/llama_suite/stop")
    async def stop_llama_server(request):
        def run_stop():
            try:
                LlamaProcessManager.stop_server()
            except Exception as e:
                pass
                
        threading.Thread(target=run_stop, daemon=True).start()
        return web.json_response({"status": "ok", "message": "Stopping process... check console."})
