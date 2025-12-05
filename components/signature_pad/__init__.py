import os
from pathlib import Path
import streamlit.components.v1 as components

_COMPONENT_DIR = Path(os.path.dirname(__file__)).resolve()

signature_pad_component = components.declare_component(
    "signature_pad",
    path=str(_COMPONENT_DIR),
)


def signature_pad(key: str, default=None):
    """
    Wrapper del componente de firma.
    """
    return signature_pad_component(key=key, default=default or {"dataUrl": None})
