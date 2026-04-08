from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import uvicorn


def _load_root_app():
	root_server = Path(__file__).resolve().parents[1] / "server.py"
	spec = importlib.util.spec_from_file_location("root_server_module", root_server)
	if spec is None or spec.loader is None:
		raise RuntimeError("Unable to load root server.py")
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module.app


def main() -> None:
	app = _load_root_app()
	port = int(os.getenv("PORT", "7860"))
	uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
	main()
