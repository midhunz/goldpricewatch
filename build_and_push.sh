#!/bin/bash

# Configuration
NAMESPACE="midhunpottammal"
BACKEND_IMAGE="gold-price-watch-backend"
FRONTEND_IMAGE="gold-price-watch-frontend"
TAG="latest"

echo "🚀 Starting Docker Build & Push for platform: linux/amd64"
echo "--------------------------------------------------------"

# Check if logged in
if ! docker system info | grep -q "Username"; then
    echo "⚠️  You are strictly NOT logged in to Docker Hub."
    echo "👉 Please run 'docker login' first."
    exit 1
fi

# Create builder if not exists
if ! docker buildx ls | grep -q "gold-price-watch-builder"; then
    echo "🛠️  Creating new buildx builder..."
    docker buildx create --name gold-price-watch-builder --use
else
    docker buildx use gold-price-watch-builder
fi

echo "📦 Building and Pushing BACKEND..."
docker buildx build --platform linux/amd64 \
    -t $NAMESPACE/$BACKEND_IMAGE:$TAG \
    ./backend \
    --push

if [ $? -eq 0 ]; then
    echo "✅ Backend pushed successfully: $NAMESPACE/$BACKEND_IMAGE:$TAG"
else
    echo "❌ Backend build failed!"
    exit 1
fi

echo "📦 Building and Pushing FRONTEND..."
# Frontend needs ARG for build
docker buildx build --platform linux/amd64 \
    --build-arg NEXT_PUBLIC_API_URL=http://goldpricewatch.com:8000 \
    -t $NAMESPACE/$FRONTEND_IMAGE:$TAG \
    ./frontend \
    --push

if [ $? -eq 0 ]; then
    echo "✅ Frontend pushed successfully: $NAMESPACE/$FRONTEND_IMAGE:$TAG"
else
    echo "❌ Frontend build failed!"
    exit 1
fi

echo "--------------------------------------------------------"
echo "🎉 All images pushed successfully!"
echo "   - $NAMESPACE/$BACKEND_IMAGE:$TAG"
echo "   - $NAMESPACE/$FRONTEND_IMAGE:$TAG"
