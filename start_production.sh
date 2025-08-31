#!/bin/bash

# Cilibit Backend Production Startup Script
echo "🚀 Starting Cilibit Backend in Production Mode..."

# Load production environment variables
if [ -f .env.production ]; then
    echo "📄 Loading production environment variables..."
    export $(cat .env.production | grep -v '^#' | xargs)
else
    echo "⚠️  No .env.production file found, using defaults..."
    export DEBUG=False
    export HOST=0.0.0.0
    export PORT=5000
fi

# Create and activate virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "🐍 Creating Python virtual environment..."
    python3 -m venv venv
fi

echo "🔄 Activating virtual environment..."
source venv/bin/activate

# Install/update dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt

# Create data directory if it doesn't exist
mkdir -p src/data

echo "🌟 Starting Cilibit Backend Server..."
echo "📡 Server will be accessible at: http://${HOST}:${PORT}"
echo "🔍 Debug mode: ${DEBUG}"
echo "🌍 CORS Origins: ${CORS_ORIGINS:-*}"

# Start the server
cd src
python main.py