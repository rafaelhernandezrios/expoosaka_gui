
# Immersive Relaxation Hub

A GUI-based application for managing and visualizing relaxation indices derived from EEG data streams.

## Table of Contents

- [Overview](#overview)
- [Requirements](#requirements)
- [Setup and Installation](#setup-and-installation)
- [Running the Application](#running-the-application)
- [How It Works](#how-it-works)
- [Important Notes](#important-notes)

## Overview

This application processes real-time EEG data from a stream (`AURA_Filtered`) and visualizes relaxation indices through:
1. A progress line graph with interactive visualization.
2. A topographic map for EEG signal channels.
3. A table summarizing video-by-video relaxation scores.

## Requirements

Before running the application, ensure the following dependencies are installed:

- Python 3.8 or later
- Required Python libraries (see `requirements.txt`):
  - `numpy`
  - `scipy`
  - `pylsl`
  - `matplotlib`
  - `mne`
  - `PyQt5`

Additionally, the application relies on the following executables:
1. `AURA.exe`: Required to process and filter EEG signals.
2. `ZenSync.exe`: Used for managing the carrusel functionality.

Both `AURA.exe` and `ZenSync.exe` must be available on your system. Ensure their paths are correctly set in the script.

## Setup and Installation

1. **Clone this repository**:
   ```bash
   git clone https://github.com/your-repo/immersive-relaxation-hub.git
   cd immersive-relaxation-hub
   ```

2. **Install dependencies**:
   Using `pip`, install all required Python libraries:
   ```bash
   pip install -r requirements.txt
   ```

3. **Verify executables**:
   Ensure `AURA.exe` and `ZenSync.exe` are installed and their paths are correctly set in the script:
   ```python
   aura_path = "C:/Users/edgar/AppData/Local/Programs/Aura/Aura.exe"
   zensync_path = "C:/Users/edgar/OneDrive/Escritorio/EXPOOSAKA/ZenSync2/ZenSync.exe"
   ```

## Running the Application

1. Start the application by running:
   ```bash
   python gui.py
   ```

2. The GUI will open automatically, showing options to:
   - Launch the required programs (`AURA.exe` and `ZenSync.exe`).
   - Start the relaxation carrusel.
   - Visualize relaxation indices through charts and tables.

## How It Works

- **EEG Data**: The application connects to the `AURA_Filtered` LSL stream and processes EEG data in real-time.
- **Relaxation Metrics**: Computes relaxation indices using bandpass filtering and power spectral density (PSD) analysis.
- **Visualizations**:
  - Progress line graph: Displays relaxation scores for videos.
  - Topomap: Visualizes EEG signal distribution.
  - Summary table: Shows relaxation indices per video.

## Important Notes

1. The application depends on the availability of `AURA_Filtered` LSL streams. Ensure the EEG system is correctly configured.
2. Make sure `AURA.exe` and `ZenSync.exe` are running properly before starting the carrusel.
3. If the application doesn't open maximized, manually adjust the window size to improve visualization.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.
