# Project Brief: Satellite Link Predictor

## Goal
Build a web application that determines if a ground operator has an effective communication link to a satellite constellation.

## Core Problem
An operator needs to know if terrain (mountains, canyons) blocks their view of a satellite.

## Definitions
1. **Effective Link:** The satellite is currently within the operator's line-of-sight (LOS) AND the satellite is within the beam's geometric footprint.
2. **Geometric Footprint:** Defined as the satellite being above a minimum elevation angle (e.g., > 25°) relative to the user.
3. **Terrain Masking:** Local terrain features that block the LOS.

## Key Deliverables
1. **Interactive Map:** User drags a marker to set location.
2. **Pass Prediction:** App lists "Effective Pass Windows" for the next 24 hours.
3. **Visual Feedback:** 3D visualization of the terrain and satellite cone.