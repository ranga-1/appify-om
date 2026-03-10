#!/bin/bash
set -e

echo "=== Starting appify-om in LOCAL mode ==="
echo ""

# Check if SSH tunnel is running
if ! nc -z localhost 5434 2>/dev/null; then
    echo "❌ ERROR: SSH tunnel not running on port 5434"
    echo "Please run: cd ../appify-unshackle && ./start-bastion-tunnel.sh"
    exit 1
fi

# Check if .env.local exists
if [ ! -f .env.local ]; then
    echo "❌ ERROR: .env.local not found"
    echo "Please create .env.local with database credentials"
    exit 1
fi

# Activate virtual environment
if [ ! -d .venv ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
uv pip install -e .

# Copy .env.local to .env
cp .env.local .env

echo ""
echo "✓ Configuration loaded from .env.local"
echo "✓ SSH tunnel: localhost:5434 → RDS"
echo "✓ Starting server on http://localhost:8000"
echo ""

# Run server with reload
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
