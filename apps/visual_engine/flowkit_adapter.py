"""FlowKit Adapter for VieNeu TTS.

Acts as the abstraction layer between VieNeu TTS and Google Flow (via FlowKit API & Chrome Extension).
Guarantees zero coupling with internal FlowKit database or heavy dependencies.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_FLOWKIT_API_URL = os.environ.get("FLOWKIT_API_URL", "http://127.0.0.1:8100")


@dataclass
class FlowConnectionStatus:
    flowkit_server_running: bool = False
    extension_connected: bool = False
    flow_tab_ready: bool = False
    account_session_ready: bool = False
    extension_version: Optional[str] = None
    flow_project_id: Optional[str] = None
    error_message: Optional[str] = None

    @property
    def is_connected(self) -> bool:
        return (
            self.flowkit_server_running
            and self.extension_connected
            and self.flow_tab_ready
        )


@dataclass
class GeneratedMediaAsset:
    media_id: str
    url: str
    asset_type: str  # "image" or "video"
    aspect_ratio: str
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    local_path: Optional[str] = None


class FlowKitAdapter:
    """Client adapter communicating with local FlowKit service (default http://127.0.0.1:8100)."""

    def __init__(self, base_url: str = DEFAULT_FLOWKIT_API_URL, timeout_sec: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.timeout_sec = timeout_sec

    def _http_request(
        self,
        endpoint: str,
        method: str = "GET",
        data: Optional[dict] = None,
        timeout: Optional[float] = None
    ) -> dict:
        url = f"{self.base_url}{endpoint}"
        t = timeout or self.timeout_sec
        body = json.dumps(data).encode("utf-8") if data is not None else None
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "VieNeu-Production-Storytelling/1.0"
        }

        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=t) as resp:
                resp_text = resp.read().decode("utf-8")
                if not resp_text:
                    return {}
                return json.loads(resp_text)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            logger.error(f"[FlowKitAdapter] HTTP {e.code} on {endpoint}: {err_body}")
            try:
                err_json = json.loads(err_body)
                raise RuntimeError(f"FlowKit error ({e.code}): {err_json.get('detail', err_body)}")
            except json.JSONDecodeError:
                raise RuntimeError(f"FlowKit error ({e.code}): {err_body}")
        except urllib.error.URLError as e:
            raise ConnectionError(f"Cannot connect to FlowKit server at {self.base_url}: {e.reason}")
        except Exception as e:
            raise RuntimeError(f"FlowKit request failed: {e}")

    def get_connection_status(self) -> FlowConnectionStatus:
        """Check connection state across FlowKit server, Chrome Extension, and Google Flow tab."""
        status = FlowConnectionStatus()
        try:
            health = self._http_request("/health", timeout=3.0)
            status.flowkit_server_running = (health.get("status") == "ok")
            status.extension_connected = bool(health.get("extension_connected", False))

            ws_stats = health.get("ws") or {}
            versions = ws_stats.get("extension_versions") or []
            if versions:
                status.extension_version = versions[0]
            status.flow_tab_ready = bool(ws_stats.get("flow_url_supported", False)) and status.extension_connected

            # Check detailed flow status
            flow_st = self._http_request("/api/flow/status", timeout=3.0)
            status.account_session_ready = bool(flow_st.get("connected", False))
            session_proj = flow_st.get("session_project") or {}
            status.flow_project_id = flow_st.get("flow_project_id") or session_proj.get("project_id")

            return status
        except (ConnectionError, urllib.error.URLError):
            status.error_message = f"FlowKit server is not running on {self.base_url}"
            return status
        except Exception as e:
            status.error_message = str(e)
            return status

    def upload_image(
        self,
        image_bytes: bytes,
        mime_type: str = "image/png",
        project_id: str = ""
    ) -> str:
        """Upload a character or location reference image to Google Flow to get a persistent media_id (UUID)."""
        import base64
        b64_data = base64.b64encode(image_bytes).decode("ascii")

        payload = {
            "image_base64": b64_data,
            "mime_type": mime_type,
            "project_id": project_id
        }
        res = self._http_request("/api/flow/upload-image", method="POST", data=payload, timeout=60.0)
        media_id = res.get("mediaId") or res.get("media_id")
        if not media_id:
            raise RuntimeError(f"Flow upload_image failed: {res}")
        return media_id

    def upload_image_file(self, file_path: str | Path, project_id: str = "") -> str:
        """Upload an image file from disk to get its Flow media_id."""
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"Reference image not found: {file_path}")

        ext = p.suffix.lower()
        mime = "image/png" if ext == ".png" else "image/jpeg"
        with open(p, "rb") as f:
            data = f.read()
        return self.upload_image(data, mime_type=mime, project_id=project_id)

    def generate_image(
        self,
        prompt: str,
        project_id: str = "",
        aspect_ratio: str = "IMAGE_ASPECT_RATIO_LANDSCAPE",
        image_model: str = "NANO_BANANA_PRO",
        reference_media_ids: Optional[List[str]] = None,
        count: int = 1,
        seed: Optional[int] = None
    ) -> List[GeneratedMediaAsset]:
        """Generate 1-4 images via Nano Banana Pro on Google Flow."""
        payload = {
            "prompt": prompt,
            "project_id": project_id,
            "aspect_ratio": aspect_ratio,
            "image_model": image_model,
            "count": count,
            "reference_media_ids": reference_media_ids or []
        }
        if seed is not None:
            payload["seed"] = seed

        res = self._http_request("/api/flow/generate-image", method="POST", data=payload, timeout=120.0)
        media_list = res.get("media") or []
        assets: List[GeneratedMediaAsset] = []

        for item in media_list:
            gen_img = item.get("image", {}).get("generatedImage", {})
            m_id = gen_img.get("mediaId") or item.get("name")
            fife_url = gen_img.get("fifeUrl") or ""
            if m_id and fife_url:
                assets.append(GeneratedMediaAsset(
                    media_id=m_id,
                    url=fife_url,
                    asset_type="image",
                    aspect_ratio=aspect_ratio
                ))

        if not assets:
            raise RuntimeError(f"Flow generate-image did not return valid media: {res}")
        return assets

    def generate_video(
        self,
        start_image_media_id: str,
        prompt: str,
        project_id: str = "",
        scene_id: str = "",
        aspect_ratio: str = "VIDEO_ASPECT_RATIO_LANDSCAPE",
        duration_s: int = 4,
        resolution: str = "720p",
        model_family: str = "omni_flash"
    ) -> Dict[str, Any]:
        """Submit frame-conditioned video generation using Gemini Omni 1.1 Flash (or Veo)."""
        payload = {
            "start_image_media_id": start_image_media_id,
            "prompt": prompt,
            "project_id": project_id,
            "scene_id": scene_id,
            "aspect_ratio": aspect_ratio,
            "model_family": model_family,
            "duration_s": duration_s,
            "resolution": resolution
        }
        res = self._http_request("/api/flow/generate-video", method="POST", data=payload, timeout=90.0)
        return res

    def check_operation_status(self, operations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Poll status for ongoing video generation operations."""
        payload = {"operations": operations}
        return self._http_request("/api/flow/check-status", method="POST", data=payload, timeout=30.0)

    def download_asset(self, url: str, destination_path: str | Path, timeout_sec: float = 60.0) -> Path:
        """Download generated image or video asset from flow-content.google to local destination path."""
        dest = Path(destination_path)
        dest.parent.mkdir(parents=True, exist_ok=True)

        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            content = resp.read()
            with open(dest, "wb") as f:
                f.write(content)

        logger.info(f"[FlowKitAdapter] Downloaded asset ({len(content)} bytes) -> {dest}")
        return dest
