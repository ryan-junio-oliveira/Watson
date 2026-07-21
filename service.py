"""Watson RAG - Windows Service wrapper.

Instalar como servico (Admin):
    python service.py install

Iniciar/Parar:
    python service.py start
    python service.py stop

Remover:
    python service.py remove
"""
import os
import sys
import asyncio
import logging

# Caminho base: compativel com PyInstaller e execucao normal
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

os.chdir(BASE_DIR)

from dotenv import load_dotenv

load_dotenv(os.path.join(BASE_DIR, ".env"))

import win32serviceutil
import win32event
import win32service

import uvicorn

from api import app, cfg


class WatsonService(win32serviceutil.ServiceFramework):
    _svc_name_ = "WatsonRAG"
    _svc_display_name_ = "Watson RAG API"
    _svc_description_ = "Servico Watson RAG - API de Retrieval-Augmented Generation"

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.server = None
        self.loop = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        if self.server:
            self.server.should_exit = True
        if self.loop:
            self.loop.call_soon_threadsafe(self.stop_event.set)

    def SvcDoRun(self):
        log_dir = os.path.join(BASE_DIR, "logs")
        os.makedirs(log_dir, exist_ok=True)

        logging.basicConfig(
            filename=os.path.join(log_dir, "service.log"),
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(message)s",
        )
        logger = logging.getLogger("WatsonService")
        logger.info(f"Watson RAG service starting on port {cfg.api_port}...")

        config = uvicorn.Config(
            app,
            host=cfg.api_host,
            port=cfg.api_port,
            log_level="info",
        )
        self.server = uvicorn.Server(config)
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        try:
            self.loop.run_until_complete(self.server.serve())
        except Exception as e:
            logger.error(f"Service error: {e}")
        finally:
            self.loop.close()
            logger.info("Watson RAG service stopped")


if __name__ == "__main__":
    win32serviceutil.HandleCommandLine(WatsonService)
