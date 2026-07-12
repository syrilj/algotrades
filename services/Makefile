# Makefile for running trading signals

.PHONY: start stop status

PORT ?= 5001

start:
	@echo "Starting live signal server on port $(PORT)..."
	python services/standalone_server.py &

stop:
	@pkill -f "standalone_server.py" || true

status:
	@curl -s http://localhost:$(PORT)/health | jq . || echo "Server not running"

test:
	@curl -s http://localhost:$(PORT)/signal/IONQ.US | jq .