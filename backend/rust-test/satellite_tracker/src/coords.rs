// use std::f64::consts::PI;

pub struct Observer {
    pub lat: f64, // degrees
    pub lon: f64, // degrees
    pub alt: f64, // meters
}

impl Observer {
    pub fn new(lat: f64, lon: f64, alt: f64) -> Self {
        Self { lat, lon, alt }
    }

    /// Convert geodetic coordinates to ECEF (Earth-Centered, Earth-Fixed)
    /// Returns (x, y, z) in km
    pub fn to_ecef(&self) -> [f64; 3] {
        let a = 6378.137; // Earth radius in km
        let f = 1.0 / 298.257223563; // Flattening factor
        let e2 = f * (2.0 - f);
        
        let lat_rad = self.lat.to_radians();
        let lon_rad = self.lon.to_radians();
        
        let n = a / (1.0 - e2 * lat_rad.sin().powi(2)).sqrt();
        let alt_km = self.alt / 1000.0;
        
        let x = (n + alt_km) * lat_rad.cos() * lon_rad.cos();
        let y = (n + alt_km) * lat_rad.cos() * lon_rad.sin();
        let z = (n * (1.0 - e2) + alt_km) * lat_rad.sin();
        
        [x, y, z]
    }
}

/// Calculate GMST in radians from a DateTime
pub fn gmst_from_datetime(dt: chrono::DateTime<chrono::Utc>) -> f64 {
    use chrono::{Datelike, Timelike};
    
    // Julian Date calculation
    // Valid for 1901-2099
    // Formula from "Astronomical Algorithms, 2nd Ed", Jean Meeus
    
    let mut year = dt.year();
    let mut month = dt.month();
    let day = dt.day();
    
    if month <= 2 {
        year -= 1;
        month += 12;
    }
    
    let a = (year as f64 / 100.0).floor();
    let b = 2.0 - a + (a / 4.0).floor();
    
    let jd = (365.25 * (year as f64 + 4716.0)).floor() +
             (30.6001 * (month as f64 + 1.0)).floor() +
             day as f64 + b - 1524.5;
             
    // Fraction of day
    let frac = (dt.hour() as f64 + dt.minute() as f64 / 60.0 + dt.second() as f64 / 3600.0 + (dt.timestamp_subsec_nanos() as f64 / 1_000_000_000.0) / 3600.0) / 24.0;
    
    let jd_ut1 = jd + frac;
    
    // Calculate GMST
    let t = (jd_ut1 - 2451545.0) / 36525.0;
    let mut gmst_deg = 280.46061837 + 360.98564736629 * (jd_ut1 - 2451545.0) + t*t*(0.000387933 - t/38710000.0);
    
    // Normalize to [0, 360]
    gmst_deg = gmst_deg % 360.0;
    if gmst_deg < 0.0 {
        gmst_deg += 360.0;
    }
    
    gmst_deg.to_radians()
}

/// Convert TEME (True Equator Mean Equinox) coordinates to ECEF
/// teme_pos: [x, y, z] in km
/// gmst_rad: Greenwich Mean Sidereal Time in radians
pub fn teme_to_ecef(teme_pos: [f64; 3], gmst_rad: f64) -> [f64; 3] {
    let cos_g = gmst_rad.cos();
    let sin_g = gmst_rad.sin();
    
    let x = teme_pos[0] * cos_g - teme_pos[1] * sin_g;
    let y = teme_pos[0] * sin_g + teme_pos[1] * cos_g;
    let z = teme_pos[2];
    
    [x, y, z]
}

/// Calculate Look Angles (Azimuth, Elevation, Range)
/// observer_ecef: Observer position in ECEF (km)
/// sat_ecef: Satellite position in ECEF (km)
/// obs_lat: Observer latitude (degrees)
/// obs_lon: Observer longitude (degrees)
/// 
/// Returns (Azimuth (deg), Elevation (deg), Range (km))
pub fn ecef_to_topocentric(observer_ecef: [f64; 3], sat_ecef: [f64; 3], obs_lat_deg: f64, obs_lon_deg: f64) -> (f64, f64, f64) {
    let rx = sat_ecef[0] - observer_ecef[0];
    let ry = sat_ecef[1] - observer_ecef[1];
    let rz = sat_ecef[2] - observer_ecef[2];
    
    let lat_rad = obs_lat_deg.to_radians();
    let lon_rad = obs_lon_deg.to_radians();
    
    let sin_lat = lat_rad.sin();
    let cos_lat = lat_rad.cos();
    let sin_lon = lon_rad.sin();
    let cos_lon = lon_rad.cos();
    
    // Convert ECEF vector to South-East-Zenith (SEZ) topocentric system
    let s = sin_lat * cos_lon * rx + sin_lat * sin_lon * ry - cos_lat * rz;
    let e = -sin_lon * rx + cos_lon * ry;
    let z = cos_lat * cos_lon * rx + cos_lat * sin_lon * ry + sin_lat * rz;
    
    let range = (s*s + e*e + z*z).sqrt();
    let elevation = (z / range).asin().to_degrees();
    let azimuth = (-e).atan2(s).to_degrees() + 180.0;
    
    (azimuth, elevation, range)
}
