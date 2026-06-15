import re
import base64
import requests
import numpy as np
import subprocess
import platform
import sys
import os
import threading
import time
from io import BytesIO
from PIL import Image

DEFAULT_URL = "http://localhost:8080"

# Глобальные переменные для управления процессом
_server_process = None
_server_thread = None

class LlamaProcessManager:
    @staticmethod
    def build_command(args: dict) -> list:
        exe_path = args.get("llama_path", "llama-server")
        if not exe_path:
            exe_path = "llama-server"
        
        cmd = [exe_path]
        
        # --- Models Dir ---
        if args.get("models_dir"):
            cmd.append("--models-dir")
            models_dir = args["models_dir"]
            # Экранирование backslash для Windows
            escaped_path = models_dir.replace('\\', '\\\\')
            cmd.append(f'{escaped_path}')

        # --- Host ---
        if args.get("host"):
            cmd.append("--host")
            cmd.append(args["host"])

        # --- Port ---
        if args.get("port"):
            cmd.append("--port")
            cmd.append(str(args["port"]))

        # --- Context Length ---
        if args.get("context_length"):
            cmd.append("-c")
            cmd.append(str(args["context_length"]))

        # --- Flash Attention ---
        fa_enabled = args.get("flash_attention", True) 
        if fa_enabled:
            cmd.append("-fa")
            cmd.append("on")

        # --- Extra Arguments ---
        if args.get("extra_args"):
            extra_str = args["extra_args"]
            lines = [line.strip() for line in extra_str.split('\n') if line.strip()]
            for line in lines:
                try:
                    import shlex
                    extra_list = shlex.split(line)
                    cmd.extend(extra_list)
                except:
                    cmd.extend(line.split())

        return cmd

    @staticmethod
    def start_server(args: dict):
        global _server_process, _server_thread
        
        if _server_process and _server_process.poll() is None:
            return "Server is already running"
        
        try:
            cmd = LlamaProcessManager.build_command(args)
            print(f"[LlamaSuite] Starting server with command: {' '.join(cmd)}")
            
            kwargs = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "text": True,
                "universal_newlines": True
            }
            
            if platform.system() == "Windows":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            
            _server_process = subprocess.Popen(cmd, **kwargs)
            
            # Запуск мониторинга процесса
            _server_thread = threading.Thread(target=LlamaProcessManager._monitor_process, daemon=True)
            _server_thread.start()
            
            return "Server process started"
        except Exception as e:
            return f"Error starting server: {str(e)}"

    @staticmethod
    def _monitor_process():
        global _server_process
        if not _server_process: return
        
        def read(pipe):
            if pipe:
                for line in iter(pipe.readline, ''):
                    sys.stderr.write(f"[Llama-Server] {line.strip()}\n")
                    sys.stderr.flush()

        t_stdout = threading.Thread(target=read, args=(_server_process.stdout,), daemon=True)
        t_stderr = threading.Thread(target=read, args=(_server_process.stderr,), daemon=True)
        t_stdout.start()
        t_stderr.start()
        
        _server_process.wait()
        
        t_stdout.join(timeout=1)
        t_stderr.join(timeout=1)
        _server_process = None

    @staticmethod
    def stop_server():
        global _server_process
        if _server_process and _server_process.poll() is None:
            try:
                if platform.system() == "Windows":
                    subprocess.call(['taskkill', '/F', '/T', '/PID', str(_server_process.pid)], 
                                    shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    _server_process.terminate()
                
                try:
                    _server_process.wait(timeout=3)
                except:
                    _server_process.kill()
                
                _server_process = None
                print("[LlamaSuite] Server stopped successfully.")
                return "Server stopped"
            except Exception as e:
                return f"Error stopping: {str(e)}"
        return "Server is not running"

    @staticmethod
    def is_running():
        if _server_process and _server_process.poll() is None:
            return True
        return False


def _extract_thinking(text: str) -> tuple[str, str]:
    # Извлекает содержимое тегов <think> или <thinking>
    pattern = re.compile(r"<think(?:ing)?>(.*?)</think(?:ing)?>", re.DOTALL | re.IGNORECASE)
    thinking_parts = pattern.findall(text)
    thinking_text = "\n\n".join(p.strip() for p in thinking_parts)
    clean_text = pattern.sub("", text).strip()
    return clean_text, thinking_text


def _tensor_to_base64(image_tensor) -> str:
    img_np = (image_tensor.numpy() * 255).clip(0, 255).astype(np.uint8)
    pil_img = Image.fromarray(img_np, mode="RGB")
    buf = BytesIO()
    pil_img.save(buf, format="JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


class LlamaSuiteClient:
    CATEGORY = "llama-suite"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("response", "thinking")
    OUTPUT_TOOLTIPS = ("Clean response text", "Extracted thinking/reasoning content")
    FUNCTION = "generate"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "server_url": ("STRING", {
                    "default": DEFAULT_URL,
                    "tooltip": "Base URL for llama-suite server (http://host:port)"
                }),
                # --- Параметры запуска сервера ---
                "llama_path": ("STRING", {
                    "default": "llama-server", 
                    "tooltip": "Path to llama-server executable."
                }),
                "models_dir": ("STRING", {
                    "default": "",
                    "tooltip": "Path to models directory (--models-dir)."
                }),
                "host": ("STRING", {
                    "default": "0.0.0.0",
                    "tooltip": "Host to bind to (--host)"
                }),
                "port": ("INT", {
                    "default": 8080,
                    "min": 1025,
                    "max": 65535,
                    "tooltip": "Port to listen on (--port)"
                }),
                "context_length": ("INT", {
                    "default": 8192,
                    "min": 8,
                    "max": 128000,
                    "tooltip": "Context window size (-c)"
                }),
                "flash_attention": ("BOOLEAN", {
                    "default": True,
                    "label_on":  "Flash Attn ON",
                    "label_off": "Flash Attn OFF",
                    "tooltip": "Enable Flash Attention (-fa on)"
                }),
                "extra_args": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "Extra arguments for llama-server (e.g. -ngl 99)"
                }),
                # --- Параметры запроса ---
                "model": ("STRING", {
                    "default": "",
                    "tooltip": "Model ID — click 'Fetch' to pick"
                }),
                "system_prompt": ("STRING", {
                    "default": "You are a helpful assistant.",
                    "multiline": True,
                    "tooltip": "System prompt"
                }),
                "prompt": ("STRING", {
                    "default": "Hello!",
                    "multiline": True,
                    "tooltip": "User message"
                }),
                "unload_after_generate": ("BOOLEAN", {
                    "default": False,
                    "label_on":  "Unload model after ✓",
                    "label_off": "Keep model loaded",
                    "tooltip": "Unload model from GPU after generation"
                }),
                "seed": ("INT", {
                    "default": 0,
                    "tooltip": "Random seed"
                }),
            },
            "optional": {
                "image": ("IMAGE", {"tooltip": "Optional image for vision models"}),
            },
        }

    def generate(self, server_url, model, system_prompt, prompt, unload_after_generate, seed, image=None, **kwargs):
        base_url = server_url.rstrip("/")
        messages = []

        if system_prompt.strip():
            messages.append({"role": "system", "content": system_prompt.strip()})

        if image is not None:
            img_b64 = _tensor_to_base64(image[0])
            user_content = [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
            ]
        else:
            user_content = prompt

        messages.append({"role": "user", "content": user_content})

        payload = {
            "model": model, 
            "messages": messages, 
            "stream": False, 
            "seed": seed
        }

        try:
            r = requests.post(
                f"{base_url}/v1/chat/completions",
                json=payload,
                timeout=300,
            )
            r.raise_for_status()
            full_text = r.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            err = f"[LlamaSuite ERROR] {exc}"
            if unload_after_generate:
                try: 
                    requests.post(f"{base_url}/models/unload", json={"model": model}, timeout=5)
                except Exception: pass
            return (err, "")

        clean_text, thinking_text = _extract_thinking(full_text)

        if unload_after_generate:
            try: 
                requests.post(f"{base_url}/models/unload", json={"model": model}, timeout=5)
            except Exception: pass

        return (clean_text, thinking_text)


NODE_CLASS_MAPPINGS = {
    "LlamaSuiteClient": LlamaSuiteClient,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LlamaSuiteClient": "🦙 LlamaSuite Client",
}
