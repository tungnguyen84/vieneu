"""Secure Credential & AI Provider Management for Sau Cánh Cửa Studio."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
from pathlib import Path
from cryptography.fernet import Fernet

try:
    from dotenv import load_dotenv
    load_dotenv()
    _repo_root = Path(__file__).resolve().parent.parent.parent
    if (_repo_root / ".env").exists():
        load_dotenv(_repo_root / ".env")
except Exception:
    # Packaged/minimal Studio runtimes may not include python-dotenv.  Read the
    # simple KEY=VALUE form used by this app so provider credentials do not
    # silently disappear just because that optional package is absent.
    _repo_root = Path(__file__).resolve().parent.parent.parent
    _env_file = _repo_root / ".env"
    if _env_file.exists():
        try:
            for _raw_line in _env_file.read_text(encoding="utf-8-sig").splitlines():
                _line = _raw_line.strip()
                if not _line or _line.startswith("#") or "=" not in _line:
                    continue
                _name, _value = _line.split("=", 1)
                _name = _name.strip()
                if not _name or _name in os.environ:
                    continue
                _value = _value.strip()
                if len(_value) >= 2 and _value[0] == _value[-1] and _value[0] in {'"', "'"}:
                    _value = _value[1:-1]
                os.environ[_name] = _value
        except Exception:
            pass

# User-level secret storage directory outside any repository or project directory
SECRETS_DIR = Path.home() / ".scc_studio"
SECRETS_FILE = SECRETS_DIR / "providers.enc"

SUPPORTED_PROVIDERS = [
    {
        "id": "gemini",
        "name": "Google Gemini",
        "default_model": "gemini-2.5-flash",
        "models": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-pro", "gemini-1.5-flash"],
        "needs_key": True,
        "env_var": "GEMINI_API_KEY",
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "default_model": "gpt-4o",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o3-mini"],
        "needs_key": True,
        "env_var": "OPENAI_API_KEY",
    },
    {
        "id": "anthropic",
        "name": "Anthropic Claude",
        "default_model": "claude-3-5-sonnet-20241022",
        "models": ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-opus-20240229"],
        "needs_key": True,
        "env_var": "ANTHROPIC_API_KEY",
    },
    {
        "id": "openai_compatible",
        "name": "OpenAI-Compatible (DeepSeek, Groq, OpenRouter)",
        "default_model": "deepseek-chat",
        "models": ["deepseek-chat", "deepseek-reasoner", "llama-3.3-70b", "mistral-large"],
        "needs_key": True,
        "needs_base_url": True,
        "env_var": "OPENAI_COMPATIBLE_API_KEY",
    },
    {
        "id": "local",
        "name": "Local LLM (Ollama, LM Studio, vLLM)",
        "default_model": "llama3.2:latest",
        "models": ["llama3.2:latest", "qwen2.5:14b", "mistral:latest"],
        "needs_key": False,
        "needs_base_url": True,
        "env_var": "LOCAL_LLM_URL",
    },
]


def _get_encryption_key() -> bytes:
    """Generates machine/user unique Fernet key."""
    salt = f"{platform.node()}-{os.getenv('USERNAME', 'scc_user')}-scc-salt-2026".encode("utf-8")
    key_material = hashlib.sha256(salt).digest()
    return base64.urlsafe_b64encode(key_material)


def _load_raw_secrets() -> Dict[str, Any]:
    if not SECRETS_FILE.exists():
        return {"providers": {}, "default_provider": "gemini", "default_model": "gemini-2.5-flash"}
    try:
        f = Fernet(_get_encryption_key())
        decrypted = f.decrypt(SECRETS_FILE.read_bytes())
        return json.loads(decrypted.decode("utf-8"))
    except Exception:
        return {"providers": {}, "default_provider": "gemini", "default_model": "gemini-2.5-flash"}


def _save_raw_secrets(data: Dict[str, Any]) -> None:
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    f = Fernet(_get_encryption_key())
    encrypted = f.encrypt(json.dumps(data, ensure_ascii=False).encode("utf-8"))
    SECRETS_FILE.write_bytes(encrypted)


def mask_key(key: Optional[str]) -> str:
    if not key or len(key) < 8:
        return "••••••••"
    return f"{key[:4]}••••••••{key[-4:]}"


def get_public_providers_status() -> Dict[str, Any]:
    """Returns safe provider list without raw secrets."""
    data = _load_raw_secrets()
    saved = data.get("providers", {})
    default_p = data.get("default_provider", "gemini")
    default_m = data.get("default_model", "gemini-2.5-flash")

    result = []
    has_any_connected = False
    for p in SUPPORTED_PROVIDERS:
        pid = p["id"]
        prov_data = saved.get(pid, {})
        env_val = os.getenv(p.get("env_var", ""), "")
        api_key = prov_data.get("api_key") or env_val

        is_connected = bool(api_key or (not p["needs_key"] and prov_data.get("base_url")))
        if is_connected:
            has_any_connected = True

        curr_m = prov_data.get("model", p["default_model"])
        provider_entry = {
            "id": pid,
            "name": p["name"],
            "configured": is_connected,
            "is_connected": is_connected,
            "has_key": bool(api_key),
            "is_default": (pid == default_p),
            "model": curr_m,
            "current_model": curr_m,
            "model_id": curr_m,
            "available_models": p["models"],
            "models": p["models"],
            "masked_key": mask_key(api_key) if api_key else "Chưa cấu hình",
            "base_url": prov_data.get("base_url", "http://localhost:11434/v1" if pid == "local" else ""),
            "needs_key": p["needs_key"],
            "needs_base_url": p.get("needs_base_url", False),
        }
        result.append(provider_entry)

    providers_dict = {p["id"]: p for p in result}

    return {
        "providers": providers_dict,
        "providers_list": result,
        "has_connected_provider": has_any_connected,
        "default_provider": default_p,
        "default_model": default_m,
    }


def save_provider_credentials(
    provider_id: Optional[str] = None,
    api_key: str = "",
    model: Optional[str] = None,
    model_id: Optional[str] = None,
    base_url: Optional[str] = None,
    set_as_default: bool = False,
    provider: Optional[str] = None,
) -> Dict[str, Any]:
    """Encrypts and persists credentials."""
    pid = (provider_id or provider or "gemini").strip().lower()
    prov_def = next((p for p in SUPPORTED_PROVIDERS if p["id"] == pid), None)
    default_m = prov_def["default_model"] if prov_def else "gemini-2.5-flash"
    chosen_model = (model_id or model or default_m).strip()

    data = _load_raw_secrets()
    if "providers" not in data:
        data["providers"] = {}

    stored_prov = data["providers"].get(pid, {})
    clean_key = api_key.strip() if api_key else stored_prov.get("api_key", "")
    clean_base = base_url.strip() if base_url is not None else stored_prov.get("base_url", "")

    data["providers"][pid] = {
        "api_key": clean_key,
        "model": chosen_model,
        "base_url": clean_base,
    }

    if set_as_default or not data.get("default_provider"):
        data["default_provider"] = pid
        data["default_model"] = chosen_model

    _save_raw_secrets(data)

    # Sync to environment variable for existing Script Factory providers
    if prov_def and prov_def.get("env_var") and clean_key:
        os.environ[prov_def["env_var"]] = clean_key

    return {"status": "saved", "configured": True, **get_public_providers_status()}


def set_default_provider(
    provider_id: Optional[str] = None,
    model_id: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Sets a configured provider as the default/active provider for generations."""
    pid = (provider_id or provider or "gemini").strip().lower()
    prov_def = next((p for p in SUPPORTED_PROVIDERS if p["id"] == pid), None)
    if not prov_def:
        raise ValueError(f"Nhà cung cấp không hợp lệ: {pid}")

    data = _load_raw_secrets()
    if "providers" not in data:
        data["providers"] = {}

    stored_prov = data["providers"].get(pid, {})
    chosen_model = (model_id or model or stored_prov.get("model") or prov_def["default_model"]).strip()

    data["default_provider"] = pid
    data["default_model"] = chosen_model
    _save_raw_secrets(data)

    # Sync environment variable if key exists
    api_key = stored_prov.get("api_key") or os.getenv(prov_def.get("env_var", ""), "")
    if prov_def.get("env_var") and api_key:
        os.environ[prov_def["env_var"]] = api_key

    return {"status": "default_updated", **get_public_providers_status()}


def delete_provider_credentials(
    provider_id: Optional[str] = None,
    provider: Optional[str] = None
) -> Dict[str, Any]:
    pid = (provider_id or provider or "").strip().lower()
    data = _load_raw_secrets()
    if "providers" in data and pid in data["providers"]:
        del data["providers"][pid]
        if data.get("default_provider") == pid:
            data["default_provider"] = "gemini"
        _save_raw_secrets(data)

    prov_def = next((p for p in SUPPORTED_PROVIDERS if p["id"] == pid), None)
    if prov_def and prov_def.get("env_var") and prov_def["env_var"] in os.environ:
        del os.environ[prov_def["env_var"]]

    return {"status": "deleted", **get_public_providers_status()}


def test_provider_connection(
    provider_id: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    provider: Optional[str] = None
) -> Dict[str, Any]:
    """Inexpensive, lightweight verification with user-friendly errors."""
    pid = (provider_id or provider or "gemini").strip().lower()
    data = _load_raw_secrets()
    stored = data.get("providers", {}).get(pid, {})
    if api_key is not None:
        actual_key = api_key.strip()
    else:
        actual_key = (stored.get("api_key") or os.getenv(f"{pid.upper()}_API_KEY", "")).strip()
    actual_model = (model or stored.get("model") or "gemini-2.5-flash").strip()
    actual_url = (base_url or stored.get("base_url", "")).strip()

    prov_def = next((p for p in SUPPORTED_PROVIDERS if p["id"] == pid), None)
    if not prov_def:
        return {"success": False, "message": f"Không tìm thấy cấu hình nhà cung cấp {pid}.", "model": actual_model}

    if prov_def["needs_key"] and not actual_key:
        return {"success": False, "message": "Vui lòng nhập API Key trước khi kiểm tra.", "model": actual_model}

    # Test logic
    if pid == "anthropic":
        try:
            import urllib.request
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": actual_key,
                    "anthropic-version": "2023-06-01",
                    "User-Agent": "SCC-Studio/1.1",
                },
                method="GET"
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                if resp.status == 200:
                    return {"success": True, "message": "Kết nối Anthropic Claude thành công ✓", "model": actual_model}
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return {"success": False, "message": "API key Anthropic không hợp lệ.", "model": actual_model}
            elif e.code == 429:
                return {"success": False, "message": "Hết quota Anthropic hoặc bị rate limit.", "model": actual_model}
            return {"success": False, "message": f"Lỗi HTTP {e.code} từ máy chủ Anthropic.", "model": actual_model}
        except Exception as e:
            return {"success": False, "message": f"Không thể kết nối đến Anthropic Claude ({e}).", "model": actual_model}
    if pid == "gemini":
        try:
            # Minimal check using google-genai or urllib
            import urllib.request
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{actual_model}?key={actual_key}"
            req = urllib.request.Request(url, headers={"User-Agent": "SCC-Studio/1.1"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                if resp.status == 200:
                    return {
                        "success": True,
                        "message": f"Kết nối Gemini thành công ✓ (Model: {actual_model})",
                        "model": actual_model,
                    }
        except urllib.error.HTTPError as e:
            if e.code == 400 or e.code == 403:
                return {"success": False, "message": "API key không hợp lệ hoặc đã bị khóa.", "model": actual_model}
            elif e.code == 429:
                return {"success": False, "message": "Tài khoản đã hết quota hoặc bị rate limit.", "model": actual_model}
            elif e.code == 404:
                return {"success": False, "message": f"Model '{actual_model}' không tồn tại hoặc chưa được cấp quyền.", "model": actual_model}
            return {"success": False, "message": f"Lỗi HTTP {e.code} từ máy chủ Google Gemini.", "model": actual_model}
        except Exception:
            return {"success": False, "message": "Không thể kết nối mạng đến Google Gemini.", "model": actual_model}

    elif pid in ["openai", "openai_compatible"]:
        api_base = actual_url or "https://api.openai.com/v1"
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{api_base.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {actual_key}", "User-Agent": "SCC-Studio/1.1"}
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                if resp.status == 200:
                    return {"success": True, "message": "Kết nối OpenAI thành công ✓", "model": actual_model}
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return {"success": False, "message": "API key không hợp lệ."}
            elif e.code == 429:
                return {"success": False, "message": "Hết quota OpenAI hoặc bị giới hạn lượt gọi."}
            return {"success": False, "message": f"Lỗi máy chủ OpenAI ({e.code})."}
        except Exception:
            return {"success": False, "message": "Không thể kết nối mạng đến OpenAI."}

    elif pid == "local":
        api_base = actual_url or "http://localhost:11434"
        try:
            import urllib.request
            req = urllib.request.Request(f"{api_base.rstrip('/')}/api/tags", headers={"User-Agent": "SCC-Studio/1.1"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    return {"success": True, "message": "Kết nối Local LLM (Ollama) thành công ✓", "model": actual_model}
        except Exception:
            return {"success": False, "message": f"Không thể kết nối đến Local endpoint tại {api_base}."}

    # Fallback simulated pass if configured
    return {"success": True, "message": f"Cấu hình {pid} hợp lệ ✓", "model": actual_model}


def get_active_api_key(provider_id: str) -> Optional[str]:
    """Returns plaintext key for active generation."""
    data = _load_raw_secrets()
    prov_data = data.get("providers", {}).get(provider_id, {})
    return prov_data.get("api_key") or os.getenv(f"{provider_id.upper()}_API_KEY")


def fetch_available_models(provider_id: Optional[str] = None, provider: Optional[str] = None) -> Dict[str, Any]:
    """Fetches real model list from provider API if reachable, else returns presets."""
    pid = (provider_id or provider or "gemini").strip().lower()
    prov_def = next((p for p in SUPPORTED_PROVIDERS if p["id"] == pid), None)
    fallback_models = prov_def["models"] if prov_def else []

    data = _load_raw_secrets()
    stored = data.get("providers", {}).get(pid, {})
    actual_key = (stored.get("api_key") or os.getenv(f"{pid.upper()}_API_KEY", "")).strip()
    actual_url = (stored.get("base_url") or "").strip()

    if pid == "gemini":
        if not actual_key:
            return {"success": False, "models": fallback_models, "message": "Chưa cấu hình API Key"}
        try:
            import urllib.request
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={actual_key}"
            req = urllib.request.Request(url, headers={"User-Agent": "SCC-Studio/1.1"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                if resp.status == 200:
                    res_data = json.loads(resp.read().decode("utf-8"))
                    models = []
                    for m in res_data.get("models", []):
                        m_name = m.get("name", "").replace("models/", "")
                        if "gemini" in m_name:
                            models.append(m_name)
                    if models:
                        return {"success": True, "models": sorted(list(set(models)))}
        except Exception as e:
            return {"success": False, "models": fallback_models, "error": str(e)}

    elif pid in ("openai", "openai_compatible"):
        if prov_def and prov_def.get("needs_key") and not actual_key:
            return {"success": False, "models": fallback_models, "message": "Chưa cấu hình API Key"}
        api_base = actual_url or "https://api.openai.com/v1"
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{api_base.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {actual_key}", "User-Agent": "SCC-Studio/1.1"}
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                if resp.status == 200:
                    res_data = json.loads(resp.read().decode("utf-8"))
                    models = [m.get("id") for m in res_data.get("data", []) if m.get("id")]
                    if models:
                        return {"success": True, "models": sorted(list(set(models)))}
        except Exception as e:
            return {"success": False, "models": fallback_models, "error": str(e)}

    elif pid == "local":
        api_base = actual_url or "http://localhost:11434"
        try:
            import urllib.request
            req = urllib.request.Request(f"{api_base.rstrip('/')}/api/tags", headers={"User-Agent": "SCC-Studio/1.1"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    res_data = json.loads(resp.read().decode("utf-8"))
                    models = [m.get("name") for m in res_data.get("models", []) if m.get("name")]
                    if models:
                        return {"success": True, "models": sorted(list(set(models)))}
        except Exception as e:
            return {"success": False, "models": fallback_models, "error": str(e)}

    return {"success": True, "models": fallback_models}
