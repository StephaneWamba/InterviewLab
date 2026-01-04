#!/bin/bash
# Railway CLI Deployment Script for InterviewLab

set -e

echo "🚀 InterviewLab Railway Deployment"
echo "=================================="

# Check if Railway CLI is installed
if ! command -v railway &> /dev/null; then
    echo "❌ Railway CLI not found. Install with: npm i -g @railway/cli"
    exit 1
fi

# Check if logged in
if ! railway whoami &> /dev/null; then
    echo "⚠️  Not logged in. Run: railway login"
    exit 1
fi

echo ""
echo "📦 Step 1: Initialize Railway project (if not already)"
echo "Run: railway init"
echo ""

echo "🗄️  Step 2: Add PostgreSQL database"
echo "Run: railway add postgresql"
echo ""

echo "💾 Step 3: Add Redis cache"
echo "Run: railway add redis"
echo ""

echo "🔧 Step 4: Set environment variables"
echo "Run these commands:"
echo ""
echo "railway variables set SECRET_KEY=\$(openssl rand -hex 32)"
echo "railway variables set OPENAI_API_KEY=your-openai-key"
echo "railway variables set LIVEKIT_URL=wss://your-project.livekit.cloud"
echo "railway variables set LIVEKIT_API_KEY=your-livekit-key"
echo "railway variables set LIVEKIT_API_SECRET=your-livekit-secret"
echo "railway variables set ENVIRONMENT=production"
echo "railway variables set LOG_LEVEL=INFO"
echo ""

echo "🚀 Step 5: Deploy API service"
echo "Run: railway up"
echo ""

echo "✅ Deployment complete!"
echo "Check logs with: railway logs"
echo "View service: railway open"


