# Coding Rules for Agents

1. **Simplicity First:** Always choose the vectorized numpy approach over looping.
2. **Type Hinting:** All Python code must use strictly typed arguments (e.g., `def calculate_mask(lat: float) -> list[float]:`).
3. **Comments:** Explain the *why*, specifically for the geometry math.
4. **Error Handling:** Gracefully handle "No DEM data available" errors (e.g., over the ocean).
5. **Testing:** Every geometric function (like azimuth calculation) requires a unit test.