#!/bin/bash

# Start Ollama server in the background
ollama serve &

# Wait for Ollama to be ready (up to 10 seconds)
for i in {1..10}; do
    if curl -s http://127.0.0.1:11434 > /dev/null; then
        echo "Ollama is up!"
        break
    fi
    echo "Waiting for Ollama... ($i/10)"
    sleep 1
done

# Pull DeepSeek-R1 if not present
if ! ollama list | grep -q "deepseek-r1:7b"; then
    echo "Pulling deepseek-r1:7b..."
    ollama pull deepseek-r1:7b
fi

# Start Gunicorn with Flask-SocketIO
exec gunicorn --workers 1 --threads 8 --timeout 0 app:app -b 0.0.0.0:5000