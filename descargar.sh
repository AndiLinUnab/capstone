#!/bin/bash
# Descarga el dataset UCI Air Quality (verificar su licencia en la pagina del dataset)
cd "$(dirname "$0")"
curl -fL -o air.zip "https://archive.ics.uci.edu/static/public/360/air+quality.zip"
python3 -m zipfile -e air.zip .
ls -la AirQualityUCI.csv
