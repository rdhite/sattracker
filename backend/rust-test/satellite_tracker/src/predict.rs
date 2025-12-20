use crate::coords::{self, Observer};
use chrono::{DateTime, Duration, Utc};
use sgp4::{Constants, Elements, Prediction as Sgp4Prediction, MinutesSinceEpoch};

#[derive(Debug)]
pub struct SatellitePosition {
    pub time: DateTime<Utc>,
    pub azimuth: f64,   // degrees
    pub elevation: f64, // degrees
    pub range: f64,     // km
}

#[derive(Debug)]
pub struct Pass {
    pub aos: DateTime<Utc>,
    pub los: DateTime<Utc>,
    pub max_elevation: f64,
}

pub fn predict_position(
    sat: &Elements,
    observer: &Observer,
    time: DateTime<Utc>,
) -> anyhow::Result<SatellitePosition> {
    // SGP4 expects time in minutes since epoch.
    // However, sgp4-rust Elements struct has 'epoch' field.
    // The Constants::initial() creates a geopotential model (WGS72 or WGS84).
    // Usually WGS72 is used for TLEs but WGS84 is common.
    // sgp4 crate docs say: "The TLE standard requires WGS72."
    
    let constants = Constants::from_elements(sat)?;
    
    // Calculate minutes since satellite epoch
    
    // Calculate JD for target time.
    let jd_target = julian_date(time);
    let jd_epoch = sat.epoch();
    
    let minutes_since_epoch = (jd_target - jd_epoch) * 1440.0;
    
    let prediction: Sgp4Prediction = constants.propagate(MinutesSinceEpoch(minutes_since_epoch))?;
    
    // Prediction gives position/velocity in TEME frame (km, km/s)
    let teme_pos = prediction.position; // [f64; 3]
    
    // Convert TEME to ECEF
    let gmst = coords::gmst_from_datetime(time);
    let ecef_pos = coords::teme_to_ecef(teme_pos, gmst);
    
    // Convert ECEF to Topocentric (Az/El/Range)
    let obs_ecef = observer.to_ecef();
    let (az, el, range) = coords::ecef_to_topocentric(obs_ecef, ecef_pos, observer.lat, observer.lon);
    
    Ok(SatellitePosition {
        time,
        azimuth: az,
        elevation: el,
        range,
    })
}

fn julian_date(dt: DateTime<Utc>) -> f64 {
    use chrono::{Datelike, Timelike};
    let year = dt.year();
    let month = dt.month();
    let day = dt.day();
    
    let (y, m) = if month <= 2 {
        (year - 1, month + 12)
    } else {
        (year, month)
    };
    
    let a = (y as f64 / 100.0).floor();
    let b = 2.0 - a + (a / 4.0).floor();
    
    let jd_day = (365.25 * (y as f64 + 4716.0)).floor() +
                 (30.6001 * (m as f64 + 1.0)).floor() +
                 day as f64 + b - 1524.5;
                 
    let frac = (dt.hour() as f64 + dt.minute() as f64 / 60.0 + dt.second() as f64 / 3600.0 + (dt.timestamp_subsec_nanos() as f64 / 1e9) / 3600.0) / 24.0;
    
    jd_day + frac
}

pub fn find_passes(
    sat: &Elements,
    observer: &Observer,
    start_time: DateTime<Utc>,
    duration: Duration,
    min_elevation: f64,
) -> anyhow::Result<Vec<Pass>> {
    let end_time = start_time + duration;
    let mut current_time = start_time;
    let step = Duration::seconds(30); // 30 second steps for coarse search
    
    let mut passes = Vec::new();
    let mut in_pass = false;
    let mut aos_time = start_time;
    let mut max_el = 0.0;
    
    // Limit loop to avoid infinite
    while current_time < end_time {
        let pos = predict_position(sat, observer, current_time);
        if let Ok(p) = pos {
            if p.elevation >= min_elevation {
                if !in_pass {
                    // Refine AOS
                    aos_time = refine_aos_los(sat, observer, current_time - step, current_time, min_elevation, true)?;
                    in_pass = true;
                    max_el = p.elevation;
                } else {
                    if p.elevation > max_el {
                        max_el = p.elevation;
                    }
                }
            } else {
                if in_pass {
                    // Just lost signal
                    let los_time = refine_aos_los(sat, observer, current_time - step, current_time, min_elevation, false)?;
                    in_pass = false;
                    
                    passes.push(Pass {
                        aos: aos_time,
                        los: los_time,
                        max_elevation: max_el,
                    });
                    
                    max_el = 0.0;
                }
            }
        }
        
        current_time = current_time + step;
    }
    
    // If still in pass at end
    if in_pass {
        let mut extended_time = current_time;
        let limit = extended_time + Duration::minutes(60); // Max 1 hour pass?
        while extended_time < limit {
             let pos = predict_position(sat, observer, extended_time);
             if let Ok(p) = pos {
                 if p.elevation < min_elevation {
                     let los_time = refine_aos_los(sat, observer, extended_time - step, extended_time, min_elevation, false)?;
                     passes.push(Pass {
                        aos: aos_time,
                        los: los_time,
                        max_elevation: max_el,
                    });
                    break;
                 } else {
                     if p.elevation > max_el {
                         max_el = p.elevation;
                     }
                 }
             }
             extended_time = extended_time + step;
        }
    }
    
    Ok(passes)
}

// Binary search to find exact moment of AOS/LOS
fn refine_aos_los(
    sat: &Elements,
    observer: &Observer,
    mut t1: DateTime<Utc>,
    mut t2: DateTime<Utc>,
    min_el: f64,
    aos: bool,
) -> anyhow::Result<DateTime<Utc>> {
    for _ in 0..10 { // 10 iterations is ~1/1000 precision of step (30s -> 30ms)
        let mid = t1 + (t2 - t1) / 2;
        let pos = predict_position(sat, observer, mid)?;
        
        if aos {
            if pos.elevation >= min_el {
                t2 = mid; // event happened before mid
            } else {
                t1 = mid; // event happens after mid
            }
        } else {
             if pos.elevation >= min_el {
                t1 = mid; // still visible, LOS is after
            } else {
                t2 = mid; // not visible, LOS was before
            }
        }
    }
    
    Ok(t1 + (t2 - t1) / 2)
}
