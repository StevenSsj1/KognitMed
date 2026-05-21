"""Gradio chatbot frontend for the KognitMed chat API."""

from __future__ import annotations

import os
from collections.abc import Sequence
from html import escape
from typing import Any
from uuid import UUID

import httpx

DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
CHAT_PATH = "/api/v1/chat"
READY_PATH = "/api/v1/health/ready"
FRONTEND_CSS = """
html, body, .gradio-container { background: #081315; height: 100dvh; overflow: hidden; }
.gradio-container { --body-text-color: #edf5f3; --background-fill-primary: #0b171b; --background-fill-secondary: #122125; --block-background-fill: #122125; --border-color-primary: #2c4447; --border-color-accent-subdued: #226f60; --color-accent-soft: #075e54; --shadow-drop: none; }
.gradio-container { --km-bubble-width: 84%; --km-chat-font: 1.05rem; }
.kognitmed-shell { box-sizing: border-box; display: flex; height: 100dvh; max-width: 1320px; margin: 0 auto; overflow: hidden; padding: 16px; }
.kognitmed-frame { background: #0b171b; border: 1px solid #294447; border-radius: 18px; box-shadow: 0 24px 64px rgba(0, 0, 0, 0.36); display: flex; flex: 1 1 auto; flex-direction: column; height: 100%; min-height: 0; overflow: hidden; }
.kognitmed-header { align-items: center; background: #142221; border-bottom: 1px solid #294447; color: #eff7f4; display: flex; flex: 0 0 auto; justify-content: space-between; gap: 16px; min-height: 76px; padding: 14px 18px; }
.kognitmed-profile { align-items: center; display: flex; gap: 12px; min-width: 0; }
.kognitmed-avatar { align-items: center; background: #0d8e73; border: 1px solid #62dbc0; border-radius: 999px; color: #ecfffb; display: flex; flex: 0 0 48px; font-size: 1.15rem; font-weight: 700; height: 48px; justify-content: center; letter-spacing: 0; width: 48px; }
.kognitmed-brand { color: #f5fffc; font-size: 1.28rem; font-weight: 700; letter-spacing: 0; line-height: 1.08; margin: 0; }
.kognitmed-role { color: #b4c8c3; font-size: 0.92rem; line-height: 1.2; margin: 4px 0 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kognitmed-meta-bar { align-items: center; display: flex; flex-wrap: wrap; gap: 8px; justify-content: end; }
.kognitmed-api { background: #203432; border: 1px solid #355451; border-radius: 999px; color: #cde8e1; font-size: 0.82rem; line-height: 1.2; max-width: 340px; overflow-wrap: anywhere; padding: 8px 12px; }
.kognitmed-main { background: #0b171b; background-image: radial-gradient(rgba(151, 177, 183, 0.08) 1px, transparent 1px); background-size: 24px 24px; border-top: 1px solid #1a2e31; display: flex; flex: 1 1 auto; gap: 0; min-height: 0; overflow: hidden; }
.kognitmed-chat-panel { border-right: 1px solid #294447; display: flex; flex-direction: column; min-height: 0; min-width: 0; }
.kognitmed-chat { background: transparent; border: 0; color: #edf5f3; flex: 1 1 auto; height: 100%; min-height: 0; overflow: hidden; }
.kognitmed-chat > div { min-height: 0; }
.kognitmed-chat .bubble-wrap { background: transparent; height: 100%; padding: 16px 12px 10px; scrollbar-color: #38595d transparent; }
.kognitmed-chat .bubble { margin: 10px 14px 8px; }
.kognitmed-chat .bubble.bot-row, .kognitmed-chat .bubble.user-row { max-width: min(var(--km-bubble-width), 760px); }
.kognitmed-chat .bot { background: #18282d; border: 1px solid #335057; border-bottom-left-radius: 3px; box-shadow: 0 12px 28px rgba(0, 0, 0, 0.18); color: #edf5f3; }
.kognitmed-chat .user { background: #075e54; border: 1px solid #168874; border-bottom-right-radius: 3px; box-shadow: 0 12px 28px rgba(0, 0, 0, 0.18); color: #f4fffc; }
.kognitmed-chat .prose, .kognitmed-chat .message { color: inherit; font-size: var(--km-chat-font); opacity: 1; }
.kognitmed-chat .message-buttons button, .kognitmed-chat .scroll-down-button-container button { background: #1d3035; border-color: #38595d; color: #dcecea; }
.kognitmed-composer { align-items: center; background: #101f23; border-top: 1px solid #294447; flex: 0 0 auto; gap: 10px; margin: 0; padding: 10px 12px; }
.kognitmed-composer label { background: transparent; border: 0; box-shadow: none; }
.kognitmed-composer textarea { background: #1c2c31; border: 1px solid #365257; border-radius: 999px; color: #f0f7f5; letter-spacing: 0; min-height: 54px; padding-left: 16px; }
.kognitmed-composer textarea:focus { background: #20343a; border-color: #1cc894; }
.kognitmed-composer textarea::placeholder { color: #adbfbb; }
.kognitmed-composer button { background: #18c178; border: 0; border-radius: 999px; color: #062615; font-size: 1.22rem; font-weight: 800; height: 54px; min-height: 54px; min-width: 54px; padding: 0; width: 54px; }
.kognitmed-composer button:hover { background: #35d28c; }
.kognitmed-settings-panel { background: rgba(10, 20, 22, 0.9); display: flex; flex-direction: column; gap: 10px; min-height: 0; overflow: auto; padding: 12px; }
.kognitmed-settings-sticky { background: linear-gradient(to bottom, rgba(10, 20, 22, 1) 78%, rgba(10, 20, 22, 0)); margin-bottom: 2px; padding-bottom: 6px; position: sticky; top: 0; z-index: 3; }
.kognitmed-settings-title { color: #f4fbf9; font-size: 0.97rem; font-weight: 700; margin: 0 0 8px; text-transform: uppercase; }
.kognitmed-settings-subtitle { color: #a6c0ba; font-size: 0.8rem; margin-bottom: 12px; }
.kognitmed-settings-card { background: #112428; border: 1px solid #2e4f54; border-radius: 12px; padding: 10px; }
.kognitmed-gradio-meta { color: #d9ece8; display: flex; flex-direction: column; font-size: 0.82rem; gap: 6px; }
.kognitmed-gradio-meta span { border-bottom: 1px dashed #32575d; padding-bottom: 4px; }
.kognitmed-gradio-meta span:last-child { border-bottom: 0; padding-bottom: 0; }
.kognitmed-status-stack { display: flex; flex-direction: column; gap: 8px; }
.kognitmed-status { border: 1px solid transparent; border-radius: 12px; display: flex; gap: 8px; line-height: 1.3; margin-bottom: 0; min-height: 36px; max-width: 100%; padding: 8px 10px; }
.kognitmed-status:last-child { margin-bottom: 0; }
.kognitmed-status-mark { border-radius: 999px; flex: 0 0 9px; height: 9px; margin-top: 4px; width: 9px; }
.kognitmed-status strong { color: #f4fbf9; display: block; font-size: 0.82rem; white-space: normal; word-break: break-word; }
.kognitmed-status span { color: #c4d8d3; display: block; font-size: 0.76rem; overflow-wrap: anywhere; white-space: normal; word-break: break-word; }
.kognitmed-status.is-ready { background: #18372d; border-color: #2b6b52; }
.kognitmed-status.is-ready .kognitmed-status-mark { background: #197b49; }
.kognitmed-status.is-info { background: #182c3b; border-color: #315a78; }
.kognitmed-status.is-info .kognitmed-status-mark { background: #2a6fbb; }
.kognitmed-status.is-warn { background: #382716; border-color: #805126; }
.kognitmed-status.is-warn .kognitmed-status-mark { background: #bd6716; }
.kognitmed-status.is-error { background: #351b1d; border-color: #7b373c; }
.kognitmed-status.is-error .kognitmed-status-mark { background: #b33a3a; }
.kognitmed-actions { display: grid; gap: 8px; grid-template-columns: repeat(3, minmax(0, 1fr)); margin-top: 4px; }
.kognitmed-actions button { background: #193136; border: 1px solid #355b61; border-radius: 10px; color: #d9eeea; min-height: 40px; min-width: 0; width: 100%; }
.kognitmed-actions button:hover { background: #234248; border-color: #4c747a; color: #f3fffc; }
.kognitmed-config-controls { display: flex; flex-direction: column; gap: 8px; }
.kognitmed-config-controls label { background: transparent; border: 0; box-shadow: none; }
.kognitmed-config-controls [data-testid="number-input"], .kognitmed-config-controls input, .kognitmed-config-controls select { background: #172c30; border: 1px solid #355b61; color: #d9eeea; }
.kognitmed-config-controls button { background: #185969; border: 1px solid #2e7c8f; color: #e9fbff; }
.kognitmed-config-controls button:hover { background: #22748b; border-color: #46a2bb; }
.kognitmed-ui-status { margin-top: 6px; }
.kognitmed-coords { background: #101f23; border: 1px solid #2e4f54; border-radius: 10px; display: flex; flex-direction: column; gap: 8px; padding: 8px; }
.kognitmed-coords label { border: 0; box-shadow: none; }
.kognitmed-coords input { background: #172c30; border: 1px solid #355b61; color: #d9eeea; }
.kognitmed-coords p { color: #a9c2bc; font-size: 0.76rem; margin: 0; }
.gradio-container.km-theme-light { --body-text-color: #1a2a2d; --background-fill-primary: #f0f6f6; --background-fill-secondary: #e5eeee; --block-background-fill: #ffffff; --border-color-primary: #a8c3c9; --border-color-accent-subdued: #6aa5b1; --color-accent-soft: #d3f1f7; }
.gradio-container.km-theme-light .kognitmed-frame { background: #eef7f7; border-color: #9cbac0; }
.gradio-container.km-theme-light .kognitmed-header { background: #dff1f1; border-bottom-color: #9cbac0; }
.gradio-container.km-theme-light .kognitmed-brand { color: #16393f; }
.gradio-container.km-theme-light .kognitmed-role { color: #395f66; }
.gradio-container.km-theme-light .kognitmed-main { background: #eef7f7; background-image: radial-gradient(rgba(108, 157, 168, 0.13) 1px, transparent 1px); }
.gradio-container.km-theme-light .kognitmed-chat .bot { background: #ffffff; border-color: #9fc4ca; color: #173d44; }
.gradio-container.km-theme-light .kognitmed-chat .user { background: #3d8b9b; border-color: #2e7887; color: #f6ffff; }
.gradio-container.km-theme-light .kognitmed-composer { background: #dfeff1; border-top-color: #9cbac0; }
.gradio-container.km-theme-light .kognitmed-composer textarea { background: #ffffff; border-color: #8fb1b8; color: #174045; }
.gradio-container.km-theme-light .kognitmed-settings-panel { background: #e8f3f4; }
.gradio-container.km-theme-light .kognitmed-settings-sticky { background: linear-gradient(to bottom, rgba(232, 243, 244, 1) 78%, rgba(232, 243, 244, 0)); }
.gradio-container.km-theme-light .kognitmed-settings-card { background: #ffffff; border-color: #a5c2c8; }
.gradio-container.km-theme-light .kognitmed-settings-title { color: #14393f; }
.gradio-container.km-theme-light .kognitmed-settings-subtitle { color: #3f666d; }
.gradio-container.km-theme-light .kognitmed-gradio-meta { color: #1f464d; }
.gradio-container.km-theme-light .kognitmed-gradio-meta span { border-bottom-color: #aac9cf; }
@media (max-width: 980px) {
    .kognitmed-shell { padding: 0; }
    .kognitmed-frame { border-radius: 0; }
    .kognitmed-header { min-height: 68px; padding: 10px 12px; }
    .kognitmed-avatar { flex-basis: 42px; height: 42px; width: 42px; }
    .kognitmed-main { flex-direction: column; }
    .kognitmed-chat-panel { border-right: 0; border-bottom: 1px solid #294447; min-height: 0; }
    .kognitmed-settings-panel { max-height: 38dvh; }
    .kognitmed-actions { grid-template-columns: 1fr; }
    .kognitmed-api { display: none; }
    .kognitmed-chat .bubble.bot-row, .kognitmed-chat .bubble.user-row { max-width: calc(100% - 18px); }
    .kognitmed-composer { padding: 8px 10px; }
}
"""

LOCATION_JS = """
async () => {
    const status = (kind, title, detail) => `
        <div class="kognitmed-status is-${kind}">
            <i class="kognitmed-status-mark"></i>
            <div><strong>${title}</strong><span>${detail}</span></div>
        </div>
    `;
    const unavailable = status("warn", "Ubicacion", "Este navegador no expone geolocalizacion.");
    const insecure = status("warn", "Ubicacion", "Abre el chat en localhost o HTTPS.");

    if (!navigator.geolocation) {
        return ["", "", unavailable];
    }
    if (!window.isSecureContext) {
        return ["", "", insecure];
    }

    return await new Promise((resolve) => {
        navigator.geolocation.getCurrentPosition(
            (position) => {
                const latitude = position.coords.latitude.toFixed(6);
                const longitude = position.coords.longitude.toFixed(6);
                resolve([
                    latitude,
                    longitude,
                    status("ready", "Ubicacion compartida", `${latitude}, ${longitude}`),
                ]);
            },
            (error) => {
                const messages = {
                    1: "No se concedio permiso para leer la ubicacion.",
                    2: "No se pudo determinar la ubicacion actual.",
                    3: "La solicitud excedio el tiempo de espera.",
                };
                resolve([
                    "",
                    "",
                    status("warn", "Ubicacion pendiente", messages[error.code] || "Vuelve a intentarlo."),
                ]);
            },
            {
                enableHighAccuracy: false,
                maximumAge: 300000,
                timeout: 10000,
            },
        );
    });
}
"""

APPLY_UI_SETTINGS_JS = """
(themeName, bubbleWidth, fontSize) => {
    const container = document.querySelector(".gradio-container");
    if (!container) {
        return `
            <div class="kognitmed-status is-error">
                <i class="kognitmed-status-mark"></i>
                <div><strong>No se pudo aplicar</strong><span>No encontre el contenedor principal.</span></div>
            </div>
        `;
    }

    container.classList.remove("km-theme-light");
    if (themeName === "Claro") {
        container.classList.add("km-theme-light");
    }

    const bubble = Math.max(60, Math.min(94, Number(bubbleWidth) || 84));
    const font = Math.max(0.92, Math.min(1.28, Number(fontSize) || 1.05));
    container.style.setProperty("--km-bubble-width", `${bubble}%`);
    container.style.setProperty("--km-chat-font", `${font}rem`);

    return `
        <div class="kognitmed-status is-ready">
            <i class="kognitmed-status-mark"></i>
            <div><strong>UI actualizada</strong><span>Tema ${themeName}, burbuja ${bubble}% y fuente ${font.toFixed(2)}rem.</span></div>
        </div>
    `;
}
"""

WELCOME_HISTORY: list[dict[str, str]] = [
    {
        "role": "assistant",
        "content": (
            "Hola. Describe tu consulta: que sientes, desde cuando y si algo lo empeora."
        ),
    }
]


def api_base_url() -> str:
    """Return the backend base URL used by the Gradio frontend."""
    return os.getenv("KOGNITMED_API_BASE_URL", DEFAULT_API_BASE_URL).rstrip("/")


async def request_chat_response(
    message: str,
    conversation_id: str | None,
    *,
    base_url: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[str, str, str]:
    """Send one user message to FastAPI and return reply, conversation ID, provider."""
    payload: dict[str, str] = {"message": message}
    if conversation_id:
        payload["conversation_id"] = conversation_id

    async with httpx.AsyncClient(
        base_url=(base_url or api_base_url()),
        timeout=45.0,
        transport=transport,
    ) as client:
        response = await client.post(CHAT_PATH, json=payload)
        response.raise_for_status()
        data = response.json()

    return str(data["response"]), str(UUID(data["conversation_id"])), str(data["provider"])


def _status_markup(kind: str, title: str, detail: str) -> str:
    """Render a compact status block for the UI rail."""
    return (
        f'<div class="kognitmed-status is-{escape(kind)}">'
        '<i class="kognitmed-status-mark"></i>'
        f"<div><strong>{escape(title)}</strong><span>{escape(detail)}</span></div>"
        "</div>"
    )


def initial_chat_history() -> list[dict[str, str]]:
    """Return a new copy of the welcome transcript."""
    return [message.copy() for message in WELCOME_HISTORY]


def initial_chat_status() -> str:
    """Return the status shown before the first backend chat request."""
    return _status_markup("info", "Sesion nueva", "Lista para iniciar una conversacion.")


def initial_backend_status() -> str:
    """Return the status shown before the backend readiness check completes."""
    return _status_markup("info", "Backend", "Verificando conexion.")


def initial_location_status() -> str:
    """Return the location status shown before the user shares browser location."""
    return _status_markup("info", "Ubicacion", "Pulsa Ubicacion para compartirla.")


async def check_backend_status() -> str:
    """Check whether the configured FastAPI backend is reachable."""
    try:
        async with httpx.AsyncClient(base_url=api_base_url(), timeout=4.0) as client:
            response = await client.get(READY_PATH)
            response.raise_for_status()
    except httpx.HTTPError:
        return _status_markup("error", "Backend sin conexion", api_base_url())

    return _status_markup("ready", "Backend listo", api_base_url())


def _assistant_error(exc: httpx.HTTPError) -> str:
    """Build a compact user-facing message for API failures."""
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            api_message = exc.response.json()["error"]["message"]
        except (KeyError, TypeError, ValueError):
            api_message = ""
        if api_message:
            return f"El backend respondio: {api_message}"
        return (
            "El backend rechazo la solicitud. "
            f"Respuesta HTTP {exc.response.status_code}."
        )
    return "No pude conectar con el backend de KognitMed. Revisa que la API este activa."


async def submit_message(
    message: str,
    history: Sequence[dict[str, Any]] | None,
    conversation_id: str | None,
) -> tuple[str, list[dict[str, Any]], str | None, str]:
    """Update the visible Gradio history with one backend round trip."""
    clean_message = message.strip()
    next_history = list(history or [])
    if not clean_message:
        return (
            "",
            next_history,
            conversation_id,
            _status_markup("warn", "Mensaje vacio", "Escribe una consulta para continuar."),
        )

    next_history.append({"role": "user", "content": clean_message})

    try:
        reply, next_conversation_id, provider = await request_chat_response(
            clean_message,
            conversation_id,
        )
    except httpx.HTTPError as exc:
        next_history.append({"role": "assistant", "content": _assistant_error(exc)})
        return (
            "",
            next_history,
            conversation_id,
            _status_markup("error", "Respuesta no disponible", "Revisa el backend y el proveedor LLM."),
        )

    next_history.append({"role": "assistant", "content": reply})
    return (
        "",
        next_history,
        next_conversation_id,
        _status_markup("ready", "Conversacion activa", f"Proveedor {provider}."),
    )


def reset_chat() -> tuple[list[dict[str, Any]], None, str]:
    """Clear the Gradio chat transcript and backend conversation state."""
    return initial_chat_history(), None, initial_chat_status()


def gradio_settings_markup() -> str:
    """Render quick UI settings visible in the right-side panel."""
    return (
        '<div class="kognitmed-settings-card">'
        '<div class="kognitmed-settings-title">Settings de Gradio</div>'
        '<div class="kognitmed-settings-subtitle">Configuracion activa de la interfaz</div>'
        '<div class="kognitmed-gradio-meta">'
        "<span>Blocks.fill_height: <strong>true</strong></span>"
        "<span>Blocks.fill_width: <strong>true</strong></span>"
        "<span>Chatbot.layout: <strong>bubble</strong></span>"
        "<span>Input.submit: <strong>enter + boton</strong></span>"
        "</div>"
        "</div>"
    )


def build_demo() -> Any:
    """Create the Gradio app lazily so API-client tests do not need the UI import."""
    import gradio as gr

    with gr.Blocks(
        title="KognitMed Chat",
        fill_height=True,
        fill_width=True,
    ) as demo:
        with gr.Column(elem_classes=["kognitmed-shell"]):
            with gr.Column(elem_classes=["kognitmed-frame"]):
                gr.HTML(
                    f"""
                    <header class="kognitmed-header">
                        <div class="kognitmed-profile">
                            <div class="kognitmed-avatar">KM</div>
                            <div>
                                <h1 class="kognitmed-brand">KognitMed</h1>
                                <p class="kognitmed-role">Asistente medico conversacional</p>
                            </div>
                        </div>
                        <div class="kognitmed-meta-bar">
                            <div class="kognitmed-api">API: {escape(api_base_url())}</div>
                        </div>
                    </header>
                    """
                )

                with gr.Row(elem_classes=["kognitmed-main"]):
                    with gr.Column(elem_classes=["kognitmed-chat-panel"], scale=8):
                        chatbot = gr.Chatbot(
                            value=initial_chat_history(),
                            layout="bubble",
                            elem_classes=["kognitmed-chat"],
                            label=None,
                            show_label=False,
                            container=False,
                            placeholder="Describe tu consulta para iniciar la conversacion.",
                            buttons=["copy", "copy_all"],
                            feedback_options=None,
                            height="100%",
                            min_height=260,
                        )
                        with gr.Row(elem_classes=["kognitmed-composer"]):
                            message = gr.Textbox(
                                label="Mensaje",
                                show_label=False,
                                container=False,
                                placeholder="Describe sintomas, tiempo de inicio y cambios recientes...",
                                lines=1,
                                max_lines=1,
                                max_length=4096,
                                autofocus=True,
                                submit_btn=False,
                                scale=6,
                            )
                            send = gr.Button(">", variant="primary", scale=0, min_width=48)

                    with gr.Column(elem_classes=["kognitmed-settings-panel"], scale=3, min_width=292):
                        with gr.Column(elem_classes=["kognitmed-settings-sticky"]):
                            with gr.Column(elem_classes=["kognitmed-settings-card"]):
                                with gr.Column(elem_classes=["kognitmed-actions"]):
                                    refresh_backend = gr.Button("Backend", size="sm", min_width=90)
                                    location = gr.Button("Ubicacion", size="sm", min_width=96)
                                    clear = gr.Button("Nuevo", size="sm", min_width=74)
                            with gr.Column(elem_classes=["kognitmed-settings-card", "kognitmed-config-controls"]):
                                gr.Markdown("**Configuracion UI**", container=False)
                                theme_select = gr.Dropdown(
                                    choices=["Oscuro", "Claro"],
                                    value="Oscuro",
                                    label="Tema",
                                )
                                bubble_width = gr.Slider(
                                    minimum=60,
                                    maximum=94,
                                    step=1,
                                    value=84,
                                    label="Ancho maximo de burbuja (%)",
                                )
                                font_size = gr.Slider(
                                    minimum=0.92,
                                    maximum=1.28,
                                    step=0.01,
                                    value=1.05,
                                    label="Tamano base de texto (rem)",
                                )
                                apply_ui = gr.Button("Aplicar cambios", variant="secondary")
                                ui_status = gr.HTML(
                                    _status_markup("info", "UI lista", "Personaliza tema y estilo del chat."),
                                    elem_classes=["kognitmed-ui-status"],
                                )

                        gr.HTML(gradio_settings_markup())
                        with gr.Column(elem_classes=["kognitmed-status-stack"]):
                            backend_status = gr.HTML(initial_backend_status())
                            chat_status = gr.HTML(initial_chat_status())
                            location_status = gr.HTML(initial_location_status())
                        with gr.Column(elem_classes=["kognitmed-coords"]):
                            latitude = gr.Textbox(
                                label="Latitud",
                                value="",
                                interactive=False,
                                container=False,
                            )
                            longitude = gr.Textbox(
                                label="Longitud",
                                value="",
                                interactive=False,
                                container=False,
                            )
                            gr.Markdown(
                                "La ubicacion solo se comparte si pulsas `Ubicacion`.",
                                container=False,
                            )

        conversation_id = gr.State(value=None)

        send.click(
            submit_message,
            inputs=[message, chatbot, conversation_id],
            outputs=[message, chatbot, conversation_id, chat_status],
        )
        message.submit(
            submit_message,
            inputs=[message, chatbot, conversation_id],
            outputs=[message, chatbot, conversation_id, chat_status],
        )
        clear.click(
            reset_chat,
            outputs=[chatbot, conversation_id, chat_status],
            queue=False,
        )
        refresh_backend.click(
            check_backend_status,
            outputs=[backend_status],
            queue=False,
        )
        location.click(
            fn=None,
            outputs=[latitude, longitude, location_status],
            js=LOCATION_JS,
            queue=False,
        )
        apply_ui.click(
            fn=None,
            inputs=[theme_select, bubble_width, font_size],
            outputs=[ui_status],
            js=APPLY_UI_SETTINGS_JS,
            queue=False,
        )
        demo.load(
            check_backend_status,
            outputs=[backend_status],
            queue=False,
        )

    return demo


def main() -> None:
    """Launch the local Gradio frontend."""
    build_demo().launch(
        server_name="127.0.0.1",
        server_port=7860,
        css=FRONTEND_CSS,
        quiet=True,
    )


if __name__ == "__main__":
    main()
