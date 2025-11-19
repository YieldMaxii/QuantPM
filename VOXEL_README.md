# Voxel Trading Interface

This is a new 3D Voxel-based frontend for the QuantPM trading competition.

## Architecture

- **Backend**: FastAPI server (`src/api/main.py`) that serves market data, trades, and system status.
- **Frontend**: React + Three.js application (`frontend/`) that visualizes markets as 3D buildings.

## Prerequisites

- Node.js (v18+)
- Python 3.10+
- `pip install -r requirements.txt`
- `cd frontend && npm install`

## Running the System

1. **Start the Backend API**:
   ```bash
   ./scripts/run_api.sh
   ```
   This will start the API server at `http://localhost:8000`.

2. **Start the Frontend**:
   ```bash
   cd frontend
   npm run dev
   ```
   This will start the React app at `http://localhost:5173`.

## Features

- **3D Market City**: Each market is a building. Height represents price/probability.
- **Live Updates**: The city updates in real-time as trading happens.
- **HUD**: Heads-up display for system status, total P&L, and recent trades.
- **Control**: Reset the system directly from the HUD.

## Navigation

- **Left Click + Drag**: Rotate camera
- **Right Click + Drag**: Pan camera
- **Scroll**: Zoom in/out

