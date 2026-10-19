"""Logger sincronizado e thread-safe para registro de eventos do sistema."""

import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.config import RESULTS_DIR

_log_file = RESULTS_DIR / "events.log"
_log_lock = threading.Lock()


def log_event(event_type: str, message: str, use_lock: bool = True) -> None:
    """
    Registra um evento formatado em arquivo de log.
    Permite alternar o uso do lock para fins do experimento D (condição de corrida).
    """
    timestamp = datetime.utcnow().isoformat()
    line = f"[{timestamp}] [{event_type.upper()}] {message}\n"
    
    if use_lock:
        with _log_lock:
            with open(_log_file, "a", encoding="utf-8") as f:
                f.write(line)
    else:
        # Escrita propositalmente desprotegida para demonstrar intercalação/race condition
        with open(_log_file, "a", encoding="utf-8") as f:
            f.write(line)
