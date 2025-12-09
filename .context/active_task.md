# Current Task: Phase 2 - Implement Pass Prediction Logic

1.  **Load Satellite Data:**
    *   Create a service to download and cache satellite TLE data (e.g., from CelesTrak).
    *   Integrate `skyfield` to load the TLE data.

2.  **Calculate Satellite Passes:**
    *   Implement a function that takes a ground station (lat, lon) and a time window.
    *   Use `skyfield` to find all passes of the loaded satellites over the ground station within the time window.
    *   The function should return a list of events (AOS, TCA, LOS).

3.  **Integrate Pass Calculation into API:**
    *   Update the `/predict` endpoint to call the new pass calculation function.
    *   Temporarily disable terrain analysis.
    *   Adjust the API response model to return the actual satellite pass data instead of the dummy time windows.

4.  **Add Basic Configuration:**
    *   Create a configuration module to manage settings like the TLE data URL and cache duration.

5.  **Write Unit Tests:**
    *   Add basic unit tests for the pass calculation logic.
